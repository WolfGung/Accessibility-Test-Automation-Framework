"""The shop's behaviour over HTTP, without a browser.

Each test gets a fresh shop in the `fixed` mode and a client that keeps its
cookies, like one browser would. The pages are read with the standard library's
HTML parser, through `data-testid` and `id` attributes rather than layout.
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app import checkout
from app.catalog import PRODUCTS, format_price
from app.main import create_app

pytestmark = pytest.mark.anyio

VALID_DETAILS = {
    "name": "Jana Novak",
    "email": "jana@example.com",
    "address": "12 Example Street",
    "city": "Berlin",
    "postcode": "10115",
    "country": "DE",
}

TOTE_BAG, MUG, NOTEBOOK = PRODUCTS[:3]


# --- reading pages ---------------------------------------------------------

VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
)


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None]
    raw_text: str = field(default="", repr=False)

    @property
    def text(self) -> str:
        """The element's text with its descendants', whitespace collapsed."""
        return " ".join(self.raw_text.split())


class Page(HTMLParser):
    """Every element of a page, in document order, with its attributes and text."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self._open: list[Element] = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, dict(attrs))
        self.elements.append(element)
        if tag not in VOID_ELEMENTS:
            self._open.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append(Element(tag, dict(attrs)))

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

    @property
    def heading(self) -> str:
        return self.one("h1").text

    @property
    def title(self) -> str:
        return self.one("title").text


def page_of(response: httpx.Response) -> Page:
    return Page(response.text)


STYLESHEET = Path(__file__).resolve().parents[1] / "app" / "static" / "shop.css"


def css_rule(selectors: str) -> dict[str, str]:
    """The declarations of the stylesheet's top-level rule for exactly these selectors."""
    css = re.sub(r"/\*.*?\*/", "", STYLESHEET.read_text(encoding="utf-8"), flags=re.S)
    css = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)  # rules inside @media are not top-level
    wanted = [part.strip() for part in selectors.split(",")]
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if [part.strip() for part in match.group(1).split(",")] == wanted:
            pairs = (declaration.split(":", 1) for declaration in match.group(2).split(";") if ":" in declaration)
            return {name.strip(): value.strip() for name, value in pairs}
    raise AssertionError(f"no top-level rule for {selectors!r} in {STYLESHEET.name}")


# --- fixtures and steps ----------------------------------------------------


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://shop.test")


@pytest.fixture
async def shop() -> AsyncIterator[httpx.AsyncClient]:
    """A fresh shop and one browser session on it."""
    async with client_for(create_app("fixed")) as client:
        yield client


async def add(
    client: httpx.AsyncClient, product_id: int, quantity: int = 1, return_to: str = "product"
) -> httpx.Response:
    return await client.post(
        "/cart/add", data={"product_id": str(product_id), "quantity": str(quantity), "return_to": return_to}
    )


async def remove(client: httpx.AsyncClient, product_id: int) -> httpx.Response:
    return await client.post("/cart/remove", data={"product_id": str(product_id)})


async def submit_checkout(client: httpx.AsyncClient, details: dict[str, str]) -> httpx.Response:
    return await client.post("/checkout", data=details)


def without(field_name: str) -> dict[str, str]:
    return {name: value for name, value in VALID_DETAILS.items() if name != field_name}


# --- pages -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "heading", "title"),
    [
        ("/", "Products", "Products – Example Shop"),
        ("/product/1", "Canvas tote bag", "Canvas tote bag – Example Shop"),
        ("/cart", "Your cart", "Your cart – Example Shop"),
        ("/checkout", "Checkout", "Checkout – Example Shop"),
    ],
)
async def test_each_page_answers_with_its_heading_and_title(
    shop: httpx.AsyncClient, path: str, heading: str, title: str
) -> None:
    response = await shop.get(path)
    assert response.status_code == 200
    page = page_of(response)
    assert page.heading == heading
    assert page.title == title


async def test_the_confirmation_page_answers_with_its_heading_after_an_order(shop: httpx.AsyncClient) -> None:
    await add(shop, 1)
    await submit_checkout(shop, VALID_DETAILS)
    response = await shop.get("/confirmation")
    assert response.status_code == 200
    page = page_of(response)
    assert page.heading == "Thank you for your order"
    assert page.title == "Order placed – Example Shop"


async def test_the_list_shows_six_products_with_image_name_price_link_and_button(shop: httpx.AsyncClient) -> None:
    page = page_of(await shop.get("/"))
    cards = page.all("li", class_="product-card")
    assert [card.attrs["id"] for card in cards] == [f"product-{number}" for number in range(1, 7)]
    for product in PRODUCTS:
        image = page.testid(f"product-image-{product.id}")
        assert image.attrs["src"] == f"/static/img/{product.image}"
        assert image.attrs["alt"] == product.alt
        link = page.testid(f"product-link-{product.id}")
        assert (link.tag, link.attrs["href"], link.text) == ("a", f"/product/{product.id}", product.name)
        assert page.testid(f"product-price-{product.id}").text == format_price(product.price_cents)
        button = page.testid(f"add-to-cart-{product.id}")
        assert (button.tag, button.attrs["type"]) == ("button", "submit")
        assert button.text == f"Add to cart: {product.name}"


async def test_every_product_image_is_served(shop: httpx.AsyncClient) -> None:
    for product in PRODUCTS:
        response = await shop.get(f"/static/img/{product.image}")
        assert response.status_code == 200, product.image
        assert response.headers["content-type"].startswith("image/svg+xml")


async def test_a_product_page_shows_image_description_price_and_a_labelled_quantity(shop: httpx.AsyncClient) -> None:
    product = PRODUCTS[3]
    page = page_of(await shop.get(f"/product/{product.id}"))
    assert page.testid("product-image").attrs["alt"] == product.alt
    assert product.description in page.one("main").text
    assert page.testid("product-price").text == format_price(product.price_cents)
    quantity = page.testid("quantity")
    assert (quantity.attrs["id"], quantity.attrs["name"], quantity.attrs["type"]) == ("quantity", "quantity", "number")
    assert page.one("label", for_="quantity").text == "Quantity"
    button = page.testid("add-to-cart")
    assert (button.tag, button.attrs["type"], button.attrs["id"], button.text) == (
        "button",
        "submit",
        "add-to-cart",
        "Add to cart",
    )


async def test_an_unknown_product_is_not_found(shop: httpx.AsyncClient) -> None:
    assert (await shop.get("/product/999")).status_code == 404


async def test_health_reports_the_mode(shop: httpx.AsyncClient) -> None:
    assert (await shop.get("/healthz")).json() == {"status": "ok", "mode": "fixed"}


# --- the cart --------------------------------------------------------------


async def test_adding_on_the_product_page_comes_back_with_the_dialog(shop: httpx.AsyncClient) -> None:
    response = await add(shop, 2, quantity=2)
    assert response.status_code == 303
    assert response.headers["location"] == "/product/2?added=1"

    page = page_of(await shop.get(response.headers["location"]))
    dialog = page.testid("added-dialog")
    assert dialog.attrs["role"] == "dialog"
    assert dialog.attrs["aria-modal"] == "true"
    assert page.one(id=dialog.attrs["aria-labelledby"]).text == "Added to cart"
    assert page.one(id=dialog.attrs["aria-describedby"]).text == "Ceramic mug is in your cart. Quantity: 2."
    assert dialog.attrs["data-opener"] == page.testid("add-to-cart").attrs["id"]
    continue_shopping = page.testid("continue-shopping")
    assert (continue_shopping.tag, continue_shopping.attrs["type"], continue_shopping.text) == (
        "button",
        "button",
        "Continue shopping",
    )
    go_to_cart = page.testid("go-to-cart")
    assert (go_to_cart.tag, go_to_cart.attrs["href"], go_to_cart.text) == ("a", "/cart", "Go to cart")
    # Focus comes back to "Add to cart" when the dialog closes; the button then says what is in the cart.
    described_by = page.testid("add-to-cart").attrs["aria-describedby"]
    assert page.one(id=described_by).text == "In your cart: 2"


async def test_the_dialog_needs_the_product_to_be_in_the_cart(shop: httpx.AsyncClient) -> None:
    assert not page_of(await shop.get("/product/2")).has_testid("added-dialog")
    assert not page_of(await shop.get("/product/2?added=1")).has_testid("added-dialog")
    await add(shop, 2)
    assert not page_of(await shop.get("/product/2")).has_testid("added-dialog")


async def test_adding_on_the_list_comes_back_to_the_button_that_was_used(shop: httpx.AsyncClient) -> None:
    response = await add(shop, 3, return_to="list")
    assert response.status_code == 303
    assert response.headers["location"] == "/#add-to-cart-3"

    page = page_of(await shop.get("/"))
    button = page.one(id="add-to-cart-3")  # the element the fragment names, which the browser focuses
    assert button.attrs["data-testid"] == "add-to-cart-3"
    assert page.one(id=button.attrs["aria-describedby"]).text == "In your cart: 1"
    assert "aria-describedby" not in page.one(id="add-to-cart-1").attrs
    assert not page.has_testid("in-cart-1")


async def test_lines_quantities_and_the_total_add_up(shop: httpx.AsyncClient) -> None:
    await add(shop, TOTE_BAG.id, quantity=2)
    await add(shop, NOTEBOOK.id)
    await add(shop, TOTE_BAG.id)  # the same product again: its line grows

    page = page_of(await shop.get("/cart"))
    assert [line.attrs["data-testid"] for line in page.all("li") if "data-testid" in line.attrs] == [
        f"cart-line-{TOTE_BAG.id}",
        f"cart-line-{NOTEBOOK.id}",
    ]
    assert page.testid(f"line-price-{TOTE_BAG.id}").text == f"{format_price(TOTE_BAG.price_cents)} each"
    assert page.testid(f"line-quantity-{TOTE_BAG.id}").text == "3"
    assert page.testid(f"line-quantity-{NOTEBOOK.id}").text == "1"
    assert page.testid(f"line-subtotal-{TOTE_BAG.id}").text == format_price(3 * TOTE_BAG.price_cents)
    assert page.testid(f"line-subtotal-{NOTEBOOK.id}").text == format_price(NOTEBOOK.price_cents)
    assert page.testid("cart-total").text == format_price(3 * TOTE_BAG.price_cents + NOTEBOOK.price_cents)
    assert page.testid("cart-count").text == "(4 items)"
    assert page.testid("checkout-link").attrs["href"] == "/checkout"


async def test_removing_a_line_takes_it_out_of_the_total(shop: httpx.AsyncClient) -> None:
    await add(shop, TOTE_BAG.id, quantity=2)
    await add(shop, MUG.id)

    response = await remove(shop, TOTE_BAG.id)
    assert response.status_code == 303
    assert response.headers["location"] == f"/cart?removed={TOTE_BAG.id}"
    page = page_of(await shop.get(response.headers["location"]))
    assert not page.has_testid(f"cart-line-{TOTE_BAG.id}")
    assert page.testid("cart-total").text == format_price(MUG.price_cents)
    assert page.testid("cart-count").text == "(1 item)"

    await remove(shop, MUG.id)
    page = page_of(await shop.get("/cart"))
    assert page.testid("cart-empty").text == "Your cart is empty."
    assert not page.has_testid("checkout-link")
    assert page.testid("cart-count").text == "(0 items)"


async def test_after_a_remove_focus_lands_on_a_line_saying_what_was_removed(shop: httpx.AsyncClient) -> None:
    await add(shop, TOTE_BAG.id)
    await add(shop, MUG.id)
    response = await remove(shop, MUG.id)
    page = page_of(await shop.get(response.headers["location"]))
    notice = page.testid("removed-notice")
    assert notice.text == "Ceramic mug was removed from your cart."
    assert (notice.attrs["tabindex"], "autofocus" in notice.attrs) == ("-1", True)
    assert [element.attrs.get("data-testid") for element in page.all() if "autofocus" in element.attrs] == [
        "removed-notice"
    ]


async def test_the_removed_line_is_not_claimed_once_it_is_untrue(shop: httpx.AsyncClient) -> None:
    await add(shop, MUG.id)
    await remove(shop, MUG.id)
    await add(shop, MUG.id)  # back in the cart: "was removed" would be wrong now
    assert not page_of(await shop.get(f"/cart?removed={MUG.id}")).has_testid("removed-notice")
    assert not page_of(await shop.get("/cart?removed=999")).has_testid("removed-notice")
    assert not page_of(await shop.get("/cart")).has_testid("removed-notice")


async def test_removing_what_is_not_in_the_cart_changes_nothing(shop: httpx.AsyncClient) -> None:
    await add(shop, MUG.id)
    for product_id in (TOTE_BAG.id, 999):
        response = await remove(shop, product_id)
        assert (response.status_code, response.headers["location"]) == (303, "/cart")
    page = page_of(await shop.get("/cart"))
    assert page.testid("cart-total").text == format_price(MUG.price_cents)
    assert not page.has_testid("removed-notice")


async def test_the_remove_control_is_a_button_named_after_its_product(shop: httpx.AsyncClient) -> None:
    await add(shop, NOTEBOOK.id)
    page = page_of(await shop.get("/cart"))
    button = page.testid(f"remove-{NOTEBOOK.id}")
    assert (button.tag, button.attrs["type"], button.attrs["aria-label"]) == (
        "button",
        "submit",
        "Remove Dotted notebook",
    )
    assert page.one("svg").attrs["aria-hidden"] == "true"


@pytest.mark.parametrize("quantity", ["0", "11", "-1", "two", ""])
async def test_a_quantity_outside_one_to_ten_is_refused(shop: httpx.AsyncClient, quantity: str) -> None:
    response = await shop.post("/cart/add", data={"product_id": "1", "quantity": quantity})
    assert response.status_code == 422
    assert page_of(await shop.get("/cart")).has_testid("cart-empty")


async def test_adding_an_unknown_product_is_not_found(shop: httpx.AsyncClient) -> None:
    assert (await add(shop, 999)).status_code == 404


async def test_each_browser_session_has_its_own_cart() -> None:
    app = create_app("fixed")
    async with client_for(app) as first, client_for(app) as second:
        await add(first, MUG.id, quantity=3)
        assert page_of(await first.get("/cart")).testid(f"line-quantity-{MUG.id}").text == "3"
        assert page_of(await second.get("/cart")).has_testid("cart-empty")


async def test_an_altered_cart_cookie_is_not_honoured() -> None:
    """The cookie is signed: change one character of what it says and the shop ignores it."""
    app = create_app("fixed")
    async with client_for(app) as owner:
        await add(owner, MUG.id)
        cookie = owner.cookies["shop_session"]
    altered = ("f" if cookie[0] != "f" else "g") + cookie[1:]
    async with client_for(app) as other:
        as_sent = page_of(await other.get("/cart", headers={"Cookie": f"shop_session={cookie}"}))
        as_altered = page_of(await other.get("/cart", headers={"Cookie": f"shop_session={altered}"}))
    assert as_sent.testid(f"line-quantity-{MUG.id}").text == "1"
    assert as_altered.has_testid("cart-empty")


def test_prices_are_written_in_euros_with_two_decimals() -> None:
    assert format_price(700) == "€7.00"
    assert format_price(4590) == "€45.90"
    assert format_price(5) == "€0.05"
    assert format_price(123456) == "€1,234.56"


# --- checkout --------------------------------------------------------------


async def test_an_empty_submit_reports_every_field_next_to_it_and_in_the_summary(shop: httpx.AsyncClient) -> None:
    response = await submit_checkout(shop, {})
    assert response.status_code == 200
    page = page_of(response)
    assert page.title == "Error: Checkout – Example Shop"

    for name in checkout.FIELDS:
        message = checkout.MISSING[name]
        assert page.testid(f"error-{name}").text == f"Error: {message}"
        control = page.one(id=name)
        assert control.attrs["aria-invalid"] == "true"
        assert control.attrs["aria-describedby"] == f"{name}-error"
        assert page.one(id=f"{name}-error").attrs["data-testid"] == f"error-{name}"

    summary = page.testid("error-summary")
    assert summary.attrs["tabindex"] == "-1"
    assert "autofocus" in summary.attrs
    # Focus lands on the summary, so it has a role and a name: "There is a problem", group.
    assert summary.attrs["role"] == "group"
    assert page.one(id=summary.attrs["aria-labelledby"]).text == "There is a problem"
    links = [link for link in page.all("a") if link.attrs.get("data-testid", "").startswith("error-link-")]
    assert [(link.attrs["href"], link.text) for link in links] == [
        (f"#{name}", checkout.MISSING[name]) for name in checkout.FIELDS
    ]


@pytest.mark.parametrize("missing", checkout.FIELDS)
async def test_a_missing_field_is_reported_on_that_field_alone(shop: httpx.AsyncClient, missing: str) -> None:
    response = await submit_checkout(shop, without(missing))
    assert response.status_code == 200
    page = page_of(response)

    assert page.testid(f"error-{missing}").text == f"Error: {checkout.MISSING[missing]}"
    assert page.one(id=missing).attrs["aria-invalid"] == "true"
    assert page.one(id=missing).attrs["aria-describedby"] == f"{missing}-error"
    assert [element.attrs["id"] for element in page.all(aria_invalid="true")] == [missing]
    assert [link.attrs["href"] for link in page.all("a") if "error-link-" in link.attrs.get("data-testid", "")] == [
        f"#{missing}"
    ]
    # What was typed stays in the form.
    for name in checkout.FIELDS:
        if name not in (missing, "country"):
            assert page.one(id=name).attrs["value"] == VALID_DETAILS[name]


@pytest.mark.parametrize(
    "email",
    ["jana", "jana@", "@example.com", "jana@example", "jana@example.", "jana @example.com", "jana@@example.com"],
)
async def test_an_email_of_the_wrong_shape_is_reported(shop: httpx.AsyncClient, email: str) -> None:
    response = await submit_checkout(shop, {**VALID_DETAILS, "email": email})
    assert response.status_code == 200
    page = page_of(response)
    assert page.testid("error-email").text == f"Error: {checkout.EMAIL_FORMAT}"
    assert page.one(id="email").attrs["aria-invalid"] == "true"
    assert page.one(id="email").attrs["value"] == email


async def test_a_country_the_shop_does_not_list_is_reported(shop: httpx.AsyncClient) -> None:
    page = page_of(await submit_checkout(shop, {**VALID_DETAILS, "country": "XX"}))
    assert page.testid("error-country").text == "Error: Select your country"


async def test_the_chosen_country_stays_selected_when_the_form_comes_back(shop: httpx.AsyncClient) -> None:
    page = page_of(await submit_checkout(shop, without("name")))
    selected = [option for option in page.all("option") if "selected" in option.attrs]
    assert [(option.attrs["value"], option.text) for option in selected] == [("DE", "Germany")]


async def test_a_valid_order_goes_to_the_confirmation_and_empties_the_cart(shop: httpx.AsyncClient) -> None:
    await add(shop, MUG.id, quantity=2)
    await add(shop, NOTEBOOK.id)

    response = await submit_checkout(shop, {**VALID_DETAILS, "email": "  jana@example.com  "})
    assert response.status_code == 303
    assert response.headers["location"] == "/confirmation"

    confirmation = page_of(await shop.get("/confirmation"))
    assert confirmation.testid("order-total").text == format_price(2 * MUG.price_cents + NOTEBOOK.price_cents)
    assert confirmation.testid("order-lines").text == (
        f"2 × Ceramic mug {format_price(2 * MUG.price_cents)} 1 × Dotted notebook {format_price(NOTEBOOK.price_cents)}"
    )
    assert confirmation.testid("delivery-address").text == "Jana Novak 12 Example Street 10115 Berlin Germany"
    assert "jana@example.com" in confirmation.one("main").text

    cart = page_of(await shop.get("/cart"))
    assert cart.has_testid("cart-empty")
    assert cart.testid("cart-count").text == "(0 items)"


async def test_valid_details_with_an_empty_cart_go_back_to_the_cart(shop: httpx.AsyncClient) -> None:
    response = await submit_checkout(shop, VALID_DETAILS)
    assert (response.status_code, response.headers["location"]) == (303, "/cart")


async def test_the_confirmation_without_an_order_goes_to_the_products(shop: httpx.AsyncClient) -> None:
    response = await shop.get("/confirmation")
    assert (response.status_code, response.headers["location"]) == (303, "/")


async def test_the_checkout_page_shows_what_is_being_ordered(shop: httpx.AsyncClient) -> None:
    await add(shop, TOTE_BAG.id, quantity=2)
    page = page_of(await shop.get("/checkout"))
    assert page.testid("checkout-total").text == format_price(2 * TOTE_BAG.price_cents)


# --- styles only a browser shows working (checked there; pinned here) -------


def test_the_dialog_scrolls_inside_its_backdrop_when_it_is_taller_than_the_window() -> None:
    backdrop = css_rule(".dialog-backdrop")
    assert backdrop["overflow-y"] == "auto"
    # Centring with place-items would push the top of a tall dialog out of reach; auto margins do not.
    assert not {"place-items", "align-items", "align-content"} & backdrop.keys()
    assert css_rule(".dialog")["margin"] == "auto"


def test_the_dialog_keeps_an_edge_in_forced_colours() -> None:
    # A transparent border is drawn in forced-colours mode, where the box shadow is dropped.
    assert css_rule(".dialog")["border"] == "2px solid transparent"


def test_a_field_reached_from_the_error_summary_keeps_its_label_and_error_in_view() -> None:
    # 9rem holds the label and a three-line error at 320 CSS px with WCAG text spacing (8.25rem measured).
    assert css_rule("input, select")["scroll-margin-top"] == "9rem"


# --- the mode --------------------------------------------------------------


@pytest.mark.parametrize("mode", ["loud", "Fixed", "BROKEN", ""])
def test_an_unknown_mode_fails_create_app(mode: str) -> None:
    with pytest.raises(ValueError, match=r"A11Y_MODE must be 'fixed' or 'broken'") as failure:
        create_app(mode)
    assert repr(mode) in str(failure.value)


def test_an_unknown_mode_in_the_environment_fails_create_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A11Y_MODE", "sometimes")
    with pytest.raises(ValueError, match=r"A11Y_MODE must be 'fixed' or 'broken', not 'sometimes'"):
        create_app()


def test_the_mode_is_fixed_when_nothing_names_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A11Y_MODE", raising=False)
    app = create_app()
    assert app.state.mode == "fixed"
    assert app.state.templates.env.globals["broken"] is False


def test_the_environment_names_the_mode_when_the_caller_does_not(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A11Y_MODE", "broken")
    app = create_app()
    assert app.state.mode == "broken"
    assert app.state.templates.env.globals["broken"] is True


def test_a_mode_given_to_create_app_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A11Y_MODE", "broken")
    assert create_app("fixed").state.mode == "fixed"


def test_two_shops_in_one_process_keep_their_own_mode() -> None:
    fixed, broken = create_app("fixed"), create_app("broken")
    assert fixed.state.templates.env.globals["broken"] is False
    assert broken.state.templates.env.globals["broken"] is True


def test_the_module_exposes_an_app() -> None:
    from app.main import app

    assert isinstance(app, FastAPI)
    assert app.state.mode in ("fixed", "broken")
