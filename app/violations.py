"""The ten accessibility violations the shop carries when it runs with `A11Y_MODE=broken`.

Each one is a single `{% if broken %}` branch in the templates, under a comment
that names its id; with `A11Y_MODE=fixed` the other side of every branch is
rendered, without the violation. This registry is the one list of them:
anything that needs the list reads it from here.

`criteria` are WCAG 2.1 success criteria. `page` is where the violation shows,
by the shop's own names for its pages (`list`, `product`, `cart`, `checkout`),
or `every page`. `where` points at the element and says what is wrong with it.
`detected_by` names the layer of checks that finds it (`axe`, `keyboard` or
`manual`); it is `unknown` until a run of those checks has shown which one does.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    id: str
    title: str
    criteria: tuple[str, ...]
    page: str
    where: str
    detected_by: str


VIOLATIONS: tuple[Violation, ...] = (
    Violation(
        id="img-alt",
        title="Product images on the list have no text alternative",
        criteria=("1.1.1",),
        page="list",
        where="Each product card's `img`, which has no `alt` attribute",
        detected_by="axe",
    ),
    Violation(
        id="field-label",
        title="The email field has no label, only words above it",
        criteria=("1.3.1", "4.1.2"),
        page="checkout",
        where=(
            'The email address field: "Email address" stands above it as plain text that nothing ties to it; '
            "no `label`, no `aria-label`, no `aria-labelledby`, no `title` and no `placeholder`"
        ),
        detected_by="axe",
    ),
    Violation(
        id="contrast",
        title="The product page's price is light grey on white, 1.87:1",
        criteria=("1.4.3",),
        page="product",
        where=(
            "The price on the product page, `#b8bec6` on `#ffffff`, from a rule on `.product-price`; "
            "the list's prices keep the colour of `.price`"
        ),
        detected_by="axe",
    ),
    Violation(
        id="mouse-only",
        title='"Add to cart" on the product list works only with a mouse',
        criteria=("2.1.1",),
        page="list",
        where='Each card\'s "Add to cart": a `div` with a click handler, no `tabindex` and no key handler',
        detected_by="unknown",
    ),
    Violation(
        id="keyboard-trap",
        title='The "Added to cart" dialog cannot be left with the keyboard',
        criteria=("2.1.2",),
        page="product",
        where=(
            "The dialog after an add: focus moves into it and Tab keeps it there, Escape does nothing, "
            "and both of its actions are `div`s with click handlers"
        ),
        detected_by="unknown",
    ),
    Violation(
        id="focus-order",
        title="Tab reaches three checkout fields first, out of their visual order",
        criteria=("2.4.3",),
        page="checkout",
        where="Street address, Town or city and Postal code, which carry `tabindex` 3, 1 and 2",
        detected_by="unknown",
    ),
    Violation(
        id="focus-visible",
        title="Links and buttons show no focus indicator",
        criteria=("2.4.7",),
        page="every page",
        where="All links and buttons: `a:focus, button:focus { outline: none; }`, with nothing in its place",
        detected_by="unknown",
    ),
    Violation(
        id="page-lang",
        title="Pages do not say what language they are in",
        criteria=("3.1.1",),
        page="every page",
        where="The `html` element, which has no `lang` attribute",
        detected_by="axe",
    ),
    Violation(
        id="error-identification",
        title="Checkout errors are shown only as a red border",
        criteria=("3.3.1",),
        page="checkout",
        where=(
            "Each field in error after a submit: no error text, no `aria-invalid`, no `aria-describedby`, "
            'no error summary and no "Error:" in the title'
        ),
        detected_by="unknown",
    ),
    Violation(
        id="div-button",
        title="The cart's remove control has no role and no name",
        criteria=("4.1.2",),
        page="cart",
        where=(
            "Each line's remove control: a `div` holding only an icon that is hidden from assistive technology; "
            "it takes focus and answers Enter and Space"
        ),
        detected_by="unknown",
    ),
)
