"""The ten planted violations, as the markup the shop sends shows them, in both modes.

Every entry of `app.violations.VIOLATIONS` has one test here, run against a
fixed shop and against a broken one: the markup behind the violation is there in
the broken mode and absent in the fixed mode. Next to that, each test holds what
must not change with the mode, so a branch that took more than its violation
shows up here. No browser runs: this is what the markup says, not what a browser
or a screen reader makes of it.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from app import checkout
from app.catalog import PRODUCTS
from app.violations import VIOLATIONS
from tests.helpers import VALID_DETAILS, Element, Page, add, client_for, page_of, rule_in

APP = Path(__file__).resolve().parents[1] / "app"

MUG, NOTEBOOK = PRODUCTS[1], PRODUCTS[2]

LABELS = {
    "name": "Full name",
    "email": "Email address",
    "address": "Street address",
    "city": "Town or city",
    "postcode": "Postal code",
    "country": "Country",
}

#: Every page, and the two states that change one: the product page with its dialog open, the checkout with errors.
EVERY_PAGE = ("list", "product", "dialog", "cart", "checkout", "checkout-errors", "confirmation")


# --- fixtures and steps ----------------------------------------------------


@pytest.fixture
def client(shop: str) -> Iterator[httpx.Client]:
    """One browser session on the shop in the mode under test, with a cart of its own."""
    with client_for(shop) as client:
        yield client


def visit(client: httpx.Client, state: str) -> Page:
    """The page in this state, after the steps a shopper takes to get there."""
    match state:
        case "list":
            response = client.get("/")
        case "product":
            response = client.get(f"/product/{MUG.id}")
        case "dialog":
            assert add(client, MUG.id).status_code == 303
            response = client.get(f"/product/{MUG.id}?added=1")
        case "cart":
            assert add(client, NOTEBOOK.id).status_code == 303
            response = client.get("/cart")
        case "checkout":
            response = client.get("/checkout")
        case "checkout-errors":
            response = client.post("/checkout", data={})
        case "confirmation":
            assert add(client, MUG.id).status_code == 303
            client.post("/checkout", data=VALID_DETAILS)
            response = client.get("/confirmation")
        case _:
            raise ValueError(f"no such page state: {state!r}")
    assert response.status_code == 200, (state, response.status_code)
    return page_of(response)


# --- what the markup says --------------------------------------------------


def tab_index(element: Element) -> int | None:
    """The element's tabindex as the markup sets it: 0 for a control without one, None when Tab passes it by."""
    if "tabindex" in element.attrs:
        index = int(element.attrs["tabindex"] or "0")
        return index if index >= 0 else None
    control = (
        (element.tag == "a" and "href" in element.attrs)
        or element.tag in {"button", "select", "textarea"}
        or (element.tag == "input" and element.attrs.get("type") != "hidden")
    )
    return 0 if control and "disabled" not in element.attrs else None


def tab_order(page: Page) -> list[str]:
    """What Tab stops on as the page loads, in order.

    Positive tabindex values come first, the lowest first; then everything else
    Tab can reach, in document order. Anything under `hidden` is skipped.
    """
    stops = [
        (index, position, element)
        for position, element in enumerate(page.elements)
        if (index := tab_index(element)) is not None
        and not any("hidden" in each.attrs for each in (element, *element.ancestors))
    ]
    stops.sort(key=lambda stop: (stop[0] == 0, stop[0], stop[1]))
    return [element.attrs.get("data-testid") or element.tag for _, _, element in stops]


def data_testids(page: Page) -> list[str]:
    return [value for element in page.elements if (value := element.attrs.get("data-testid"))]


def style_of(page: Page) -> str:
    """The page's own style block (the price colour and the focus indicator)."""
    return page.one("style").raw_text


def contrast_ratio(foreground: str, background: str) -> float:
    """The contrast ratio of two `#rrggbb` colours, as WCAG 2.1 defines it."""

    def luminance(colour: str) -> float:
        channels = (int(colour[start : start + 2], 16) / 255 for start in (1, 3, 5))
        red, green, blue = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


# --- the registry ----------------------------------------------------------

#: Which test below pins which violation, filled in as the tests are defined.
PINNED: dict[str, str] = {}


def pins[T: Callable[..., object]](violation_id: str) -> Callable[[T], T]:
    """Mark a test as the one that pins this violation's markup."""

    def mark(test: T) -> T:
        assert violation_id not in PINNED, f"{violation_id} is pinned twice"
        PINNED[violation_id] = getattr(test, "__name__", repr(test))
        return test

    return mark


def test_the_registry_names_the_ten_violations_in_order() -> None:
    assert [(violation.id, violation.criteria, violation.page) for violation in VIOLATIONS] == [
        ("img-alt", ("1.1.1",), "list"),
        ("field-label", ("1.3.1", "4.1.2"), "checkout"),
        ("contrast", ("1.4.3",), "product"),
        ("mouse-only", ("2.1.1",), "list"),
        ("keyboard-trap", ("2.1.2",), "product"),
        ("focus-order", ("2.4.3",), "checkout"),
        ("focus-visible", ("2.4.7",), "every page"),
        ("page-lang", ("3.1.1",), "every page"),
        ("error-identification", ("3.3.1",), "checkout"),
        ("div-button", ("4.1.2",), "cart"),
    ]


def test_each_entry_says_what_is_wrong_and_where_and_cannot_be_changed() -> None:
    for violation in VIOLATIONS:
        assert violation.title and violation.where, violation.id
        assert violation.detected_by in {"unknown", "axe", "keyboard", "manual"}, violation.id
    with pytest.raises(dataclasses.FrozenInstanceError):
        VIOLATIONS[0].detected_by = "manual"


def test_each_violation_is_one_marked_branch_in_the_templates() -> None:
    """`broken` is used in the templates only as `{% if broken %}`, right under a comment naming a violation."""
    named: list[str] = []
    for template in sorted((APP / "templates").glob("*.html")):
        source = template.read_text(encoding="utf-8")
        uses = [tag for tag in re.findall(r"\{[{%].*?[%}]\}", source, flags=re.S) if re.search(r"\bbroken\b", tag)]
        assert uses == ["{% if broken %}"] * len(uses), f"{template.name}: {uses}"
        branches = re.findall(r"\{#\s*Violation ([a-z-]+):(?:(?!#\}).)*#\}\s*\{% if broken %\}", source, flags=re.S)
        assert len(branches) == len(uses), f"{template.name}: a branch without a comment naming its violation"
        named += branches
    assert sorted(named) == sorted(violation.id for violation in VIOLATIONS)


def test_every_violation_has_its_markup_pinned_here() -> None:
    assert set(PINNED) == {violation.id for violation in VIOLATIONS}


# --- the ten, one test each ------------------------------------------------


@pins("img-alt")
def test_list_images_have_alt_text_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    images = visit(client, "list").all("img")
    assert [image.attrs["data-testid"] for image in images] == [f"product-image-{p.id}" for p in PRODUCTS]
    if mode == "broken":
        assert [image.attrs.get("alt") for image in images] == [None] * len(PRODUCTS)  # no alt attribute at all
    else:
        assert [image.attrs.get("alt") for image in images] == [product.alt for product in PRODUCTS]
    # The product page's photo is not part of it: it keeps its text in both modes.
    assert visit(client, "product").testid("product-image").attrs["alt"] == MUG.alt


@pins("field-label")
def test_the_email_field_has_a_label_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    page = visit(client, "checkout")
    email = page.one(id="email")
    wrapper = email.parent
    assert wrapper is not None and "field" in wrapper.classes
    # Nothing but a label could name it, in either mode: no label around it, no aria-label, no title, no placeholder.
    assert not {"aria-label", "aria-labelledby", "title", "placeholder"} & email.attrs.keys()
    assert "label" not in [outer.tag for outer in email.ancestors]
    inside = [(element.tag, element.text) for element in page.within(wrapper)]
    if mode == "broken":
        assert page.all("label", for_="email") == []
        # The words are still shown above the field, as plain text that nothing ties to it.
        assert inside == [("span", "Email address"), ("input", "")]
        assert page.within(wrapper)[0].classes == ["field-text"]
    else:
        assert page.one("label", for_="email").text == "Email address"
        assert inside == [("label", "Email address"), ("input", "")]
    # The other five fields keep their labels, and nothing on the page has a placeholder, in both modes.
    for name, label in LABELS.items():
        if name != "email":
            assert page.one("label", for_=name).text == label
    assert [element.attrs.get("id") for element in page.elements if "placeholder" in element.attrs] == []


@pins("contrast")
def test_the_product_price_has_enough_contrast_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    stylesheet = (APP / "static" / "shop.css").read_text(encoding="utf-8")
    # Prices sit on the page's white, nothing under them paints another colour, and only the page's own style
    # block colours them.
    assert rule_in(stylesheet, "body")["background"] == "#ffffff"
    assert "background" not in rule_in(stylesheet, ".product-card")
    assert "color" not in rule_in(stylesheet, ".price") and "color" not in rule_in(stylesheet, ".product-price")
    product, listing = visit(client, "product"), visit(client, "list")
    style = style_of(product)
    assert style == style_of(listing)  # one style block, from base.html, on every page
    # `product-price` is on the product page's price alone; the list's prices carry `price` only.
    assert product.testid("product-price").classes == ["price", "product-price"]
    with_class = [each.attrs.get("data-testid") for each in product.elements if "product-price" in each.classes]
    assert with_class == ["product-price"]
    assert [listing.testid(f"product-price-{p.id}").classes for p in PRODUCTS] == [["price"]] * len(PRODUCTS)
    assert [each for each in listing.elements if "product-price" in each.classes] == []
    # `.price`, the colour of the list's prices, keeps its contrast in both modes.
    assert contrast_ratio(rule_in(style, ".price")["color"], "#ffffff") >= 4.5
    if mode == "broken":
        colour = rule_in(style, ".product-price")["color"]
        ratio = contrast_ratio(colour, "#ffffff")
        assert (colour, round(ratio, 2)) == ("#b8bec6", 1.87)
        assert ratio < 3  # below even the 3:1 that large text, like this 24px bold price, needs
        # The same specificity as `.price`, so it wins on the product page only by coming later.
        assert style.index(".price {") < style.index(".product-price {")
    else:
        assert ".product-price" not in style


@pins("mouse-only")
def test_add_to_cart_on_the_list_is_a_button_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    page = visit(client, "list")
    for product in PRODUCTS:
        control = page.testid(f"add-to-cart-{product.id}")
        form = control.parent
        assert form is not None and (form.tag, form.attrs["action"]) == ("form", "/cart/add")
        assert control.text == f"Add to cart: {product.name}"  # the same words in both modes
        if mode == "broken":
            assert (control.tag, "add" in control.classes, bool(control.attrs.get("onclick"))) == ("div", True, True)
            assert not {"tabindex", "role", "onkeydown", "onkeyup", "onkeypress"} & control.attrs.keys()
            # Nothing else in its form takes focus either: the keyboard cannot add from the list.
            assert [element.tag for element in page.within(form) if tab_index(element) is not None] == []
        else:
            assert (control.tag, control.attrs["type"]) == ("button", "submit")


@pins("keyboard-trap")
def test_the_added_dialog_can_be_left_with_the_keyboard_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    page = visit(client, "dialog")
    dialog = page.testid("added-dialog")
    # The same dialog in both modes: a modal, named by its heading and described by its message.
    assert (dialog.attrs["role"], dialog.attrs["aria-modal"]) == ("dialog", "true")
    assert page.one(id=dialog.attrs["aria-labelledby"]).text == "Added to cart"
    assert page.one(id=dialog.attrs["aria-describedby"]).text == f"{MUG.name} is in your cart. Quantity: 1."
    inside = [element.attrs.get("data-testid") for element in page.within(dialog) if tab_index(element) is not None]
    actions = [page.testid("continue-shopping"), page.testid("go-to-cart")]
    inline_scripts = [script.raw_text for script in page.all("script") if "src" not in script.attrs]
    if mode == "broken":
        assert inside == []  # nothing inside to Tab to, to close it or to leave by
        assert [action.tag for action in actions] == ["div", "div"]
        # Not marked data-dialog, so shop.js leaves it alone.
        assert (dialog.attrs["tabindex"], "data-dialog" in dialog.attrs) == ("-1", False)
        # Its own script puts focus on the dialog and holds Tab there; Escape is not handled.
        [script] = inline_scripts
        assert "dialog.focus()" in script and '"Tab"' in script and "Escape" not in script
    else:
        assert inside == ["continue-shopping", "go-to-cart"]
        assert [(action.tag, action.attrs.get("type") or action.attrs.get("href")) for action in actions] == [
            ("button", "button"),
            ("a", "/cart"),
        ]
        assert ("tabindex" in dialog.attrs, "data-dialog" in dialog.attrs) == (False, True)
        assert inline_scripts == []


@pins("focus-order")
def test_tab_follows_the_checkout_form_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    page = visit(client, "checkout")
    fields_on_screen = [f"checkout-{name}" for name in checkout.FIELDS]
    # The fields stand in the same order in the document in both modes; that is the order on screen.
    assert [testid for testid in data_testids(page) if testid in fields_on_screen] == fields_on_screen
    positive = {each.attrs["id"]: each.attrs["tabindex"] for each in page.elements if (tab_index(each) or 0) > 0}
    order = tab_order(page)
    fields_by_tab = [stop for stop in order if stop in fields_on_screen]
    if mode == "broken":
        assert positive == {"address": "3", "city": "1", "postcode": "2"}
        # Tab goes to them before the skip link, and not in the order they are shown.
        assert order[:4] == ["checkout-city", "checkout-postcode", "checkout-address", "skip-link"]
        assert fields_by_tab != fields_on_screen
    else:
        assert positive == {}
        assert order[0] == "skip-link"
        assert fields_by_tab == fields_on_screen


@pins("focus-visible")
def test_links_and_buttons_keep_a_focus_outline_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    # One page stands for all: the style block comes from base.html, which every page extends and none can change.
    style = style_of(visit(client, "list"))
    # Whatever else takes focus (fields, for one) keeps the indicator in both modes.
    assert rule_in(style, ":focus-visible") == {"outline": "3px solid #1a56db", "outline-offset": "2px"}
    outlines = re.findall(r"\boutline\s*:\s*([^;}]+?)\s*[;}]", style)
    if mode == "broken":
        assert rule_in(style, "a:focus, button:focus") == {"outline": "none"}  # and nothing in its place
        assert outlines == ["3px solid #1a56db", "none"]
    else:
        assert outlines == ["3px solid #1a56db"]


@pins("page-lang")
def test_pages_say_they_are_in_english_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    # One page stands for all: the html element comes from base.html, which every page extends and none can change.
    html = visit(client, "list").one("html")
    if mode == "broken":
        assert not {"lang", "xml:lang"} & html.attrs.keys()
    else:
        assert html.attrs["lang"] == "en"


@pins("error-identification")
def test_checkout_errors_are_put_into_words_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    page = visit(client, "checkout-errors")
    for name in checkout.FIELDS:
        control = page.one(id=name)
        # The red border is there in both modes: in the broken mode it is the only sign.
        assert control.parent is not None and "field-with-error" in control.parent.classes
        if mode == "broken":
            assert not {"aria-invalid", "aria-describedby"} & control.attrs.keys()
            assert page.all(id=f"{name}-error") == []
        else:
            assert control.attrs["aria-invalid"] == "true"
            assert page.one(id=control.attrs["aria-describedby"]).text == f"Error: {checkout.MISSING[name]}"
    words = page.one("main").text
    if mode == "broken":
        assert not page.has_testid("error-summary")
        assert page.title == "Checkout – Example Shop"
        assert not [message for message in checkout.MISSING.values() if message in words]
        assert "Error" not in words and "There is a problem" not in words
    else:
        assert page.testid("error-summary").attrs["role"] == "group"
        assert page.title == "Error: Checkout – Example Shop"


@pins("div-button")
def test_the_remove_control_has_a_role_and_a_name_only_in_the_fixed_mode(client: httpx.Client, mode: str) -> None:
    page = visit(client, "cart")
    control = page.testid(f"remove-{NOTEBOOK.id}")
    form = control.parent
    assert form is not None and (form.tag, form.attrs["action"]) == ("form", "/cart/remove")
    # It holds the same icon in both modes, hidden from assistive technology.
    icon, *_ = inside = page.within(control)
    assert [element.tag for element in inside] == ["svg", "path"]
    assert icon.attrs["aria-hidden"] == "true"
    if mode == "broken":
        assert (control.tag, "remove" in control.classes) == ("div", True)
        assert not {"role", "aria-label", "aria-labelledby", "title"} & control.attrs.keys()
        assert control.text == ""  # nothing a screen reader could say for it
        # Still reached and worked with the keyboard: what it lacks is a role and a name, not keyboard access.
        assert control.attrs["tabindex"] == "0"
        assert control.attrs.get("onclick") and control.attrs.get("onkeydown")
    else:
        assert (control.tag, control.attrs["type"], control.attrs["aria-label"]) == (
            "button",
            "submit",
            f"Remove {NOTEBOOK.name}",
        )


# --- what stays the same in both modes -------------------------------------


@pytest.mark.parametrize("state", EVERY_PAGE)
def test_every_page_starts_with_a_link_to_its_main_content(client: httpx.Client, mode: str, state: str) -> None:
    page = visit(client, state)
    skip_link = page.testid("skip-link")
    assert (skip_link.tag, skip_link.attrs["href"], skip_link.text) == ("a", "#main", "Skip to main content")
    assert next(element for element in page.elements if tab_index(element) is not None) is skip_link
    assert page.one("main").attrs["id"] == "main"


ERROR_DISPLAY = {"error-summary"} | {f"error-{name}" for name in checkout.FIELDS} | {
    f"error-link-{name}" for name in checkout.FIELDS
}


@pytest.mark.parametrize("state", EVERY_PAGE)
def test_both_modes_render_the_same_elements_in_the_same_order(fixed_shop: str, broken_shop: str, state: str) -> None:
    """What the checks look up by data-testid is there in both modes, except the error text the broken mode drops."""
    with client_for(fixed_shop) as fixed, client_for(broken_shop) as broken:
        in_fixed = data_testids(visit(fixed, state))
        in_broken = data_testids(visit(broken, state))
    assert in_broken == [testid for testid in in_fixed if testid not in ERROR_DISPLAY]
