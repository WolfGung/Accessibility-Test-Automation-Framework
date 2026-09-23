"""What the test modules share: a client for a running shop, the page states the checks visit, a step a shopper
takes, a reader for the pages, and a way to put a check's findings on the report.

Pages are read with the standard library's HTML parser, through `data-testid`
and `id` attributes rather than layout.
"""
from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import TYPE_CHECKING

import allure
import httpx

if TYPE_CHECKING:
    from a11y.axe import Finding


def client_for(shop: str) -> httpx.Client:
    """A client for the running shop at this base URL that keeps its cookies, like one browser would.

    Redirects are not followed: a test sees each 303 and its `Location` as the shop sent them.
    """
    return httpx.Client(base_url=shop, follow_redirects=False)


# --- the page states -------------------------------------------------------

#: The page states the browser checks visit: every page, and the two states that change one (the product page
#: with its dialog open, the checkout after an empty submit).
PAGES = ("list", "product", "dialog", "cart", "checkout", "checkout-errors")

#: The page of the shop each state shows, as the registry of violations names pages.
PAGE_OF = {
    "list": "list",
    "product": "product",
    "dialog": "product",
    "cart": "cart",
    "checkout": "checkout",
    "checkout-errors": "checkout",
}


# --- a step a shopper takes ------------------------------------------------

#: Details the checkout accepts.
VALID_DETAILS = {
    "name": "Jana Novak",
    "email": "jana@example.com",
    "address": "12 Example Street",
    "city": "Berlin",
    "postcode": "10115",
    "country": "DE",
}


def add(client: httpx.Client, product_id: int, quantity: int = 1, return_to: str = "product") -> httpx.Response:
    """Add a product to the cart, as the form on the product page does (or the list's, with `return_to="list"`)."""
    return client.post(
        "/cart/add", data={"product_id": str(product_id), "quantity": str(quantity), "return_to": return_to}
    )


# --- reading pages ---------------------------------------------------------

VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
)


@dataclass(eq=False)  # an element is itself, not any element that looks the same
class Element:
    tag: str
    attrs: dict[str, str | None]
    parent: Element | None = field(default=None, repr=False)
    raw_text: str = field(default="", repr=False)

    @property
    def text(self) -> str:
        """The element's text with its descendants', whitespace collapsed."""
        return " ".join(self.raw_text.split())

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    @property
    def ancestors(self) -> list[Element]:
        """The elements this one sits in, nearest first."""
        found: list[Element] = []
        element = self.parent
        while element is not None:
            found.append(element)
            element = element.parent
        return found


class Page(HTMLParser):
    """Every element of a page, in document order, with its attributes, its text and where it sits."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self._open: list[Element] = []
        self.feed(html)
        self.close()

    def _start(self, tag: str, attrs: list[tuple[str, str | None]]) -> Element:
        element = Element(tag, dict(attrs), parent=self._open[-1] if self._open else None)
        self.elements.append(element)
        return element

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = self._start(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self._open.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index].tag == tag:
                del self._open[index:]
                return

    def handle_data(self, data: str) -> None:
        for element in self._open:
            element.raw_text += data

    def all(self, tag: str | None = None, **attrs: str) -> list[Element]:
        """Elements with this tag (any tag when None) whose attributes have these values.

        Attribute names are written the Python way: `data_testid="x"` matches
        `data-testid="x"`, and `for_="x"` matches `for="x"`.
        """
        wanted = {name.rstrip("_").replace("_", "-"): value for name, value in attrs.items()}
        return [
            element
            for element in self.elements
            if (tag is None or element.tag == tag)
            and all(element.attrs.get(name) == value for name, value in wanted.items())
        ]

    def one(self, tag: str | None = None, **attrs: str) -> Element:
        found = self.all(tag, **attrs)
        assert len(found) == 1, f"expected one {tag or 'element'} with {attrs}, found {len(found)}"
        return found[0]

    def testid(self, value: str) -> Element:
        return self.one(data_testid=value)

    def has_testid(self, value: str) -> bool:
        return bool(self.all(data_testid=value))

    def within(self, container: Element) -> list[Element]:
        """The elements inside this one, in document order."""
        return [element for element in self.elements if any(outer is container for outer in element.ancestors)]

    @property
    def heading(self) -> str:
        return self.one("h1").text

    @property
    def title(self) -> str:
        return self.one("title").text


def page_of(response: httpx.Response) -> Page:
    return Page(response.text)


# --- reading styles --------------------------------------------------------


def rule_in(css: str, selectors: str) -> dict[str, str]:
    """The declarations of the top-level rule for exactly these selectors in this CSS."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)  # rules inside @media are not top-level
    wanted = [part.strip() for part in selectors.split(",")]
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if [part.strip() for part in match.group(1).split(",")] == wanted:
            pairs = (declaration.split(":", 1) for declaration in match.group(2).split(";") if ":" in declaration)
            return {name.strip(): value.strip() for name, value in pairs}
    raise AssertionError(f"no top-level rule for {selectors!r}")


# --- the report ------------------------------------------------------------


def attach_findings(name: str, findings: list[Finding]) -> None:
    """Put a check's findings on the Allure report as a JSON list: rule, impact, criteria, selector, help and link."""
    body = json.dumps([dataclasses.asdict(finding) for finding in findings], indent=2)
    allure.attach(body, name=name, attachment_type=allure.attachment_type.JSON)
