"""The keyboard checks: what a shopper meets when the mouse is out of reach, on the page each check is given.

Each check drives the browser with `Tab`, `Shift+Tab`, `Enter`, `Space`,
`Escape` and typing alone, never a pointer and never a script that moves focus
for it, and answers with a list of `KeyFinding`: empty when the page passes. The checks
know where focus is by the `data-testid` of the focused element, so a finding
names elements the way the templates do. Every loop is bounded: a page that
holds focus or never reaches a control ends a check with a finding, not a hang.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlsplit

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

#: The success criterion each check tests.
CRITERIA: dict[str, tuple[str, ...]] = {
    "checkout_by_keyboard": ("2.1.1",),
    "focus_order": ("2.4.3",),
    "focus_visible": ("2.4.7",),
    "dialog_escape": ("2.1.2",),
    "dialog_trap": ("2.1.2",),
}

#: The most presses of Tab one walk through a page makes. Focus comes round long before that on any page here.
TAB_LIMIT = 40

#: How many times each key is tried on an open dialog before it is called a trap.
TRAP_PRESSES = 20

#: How long, in milliseconds, a page gets to arrive after Enter, or the dialog to open.
PAGE_TIMEOUT = 5_000

#: The journey a shopper makes to buy the first product, stop by stop: the page each stop is on, the control Tab must
#: reach, and what to do there — press Enter on a link or Space on a button and wait for the address the shop must
#: answer with, or type a value. The country is typed into its `select`, which picks the option those letters start.
STEPS: tuple[tuple[str, str, str, str], ...] = (
    ("the product list", "add-to-cart-1", "Space", "/#add-to-cart-1"),
    ("the product list, with the product in the cart", "cart-link", "Enter", "/cart"),
    ("the cart", "checkout-link", "Enter", "/checkout"),
    ("the checkout", "checkout-name", "type", "Jana Novak"),
    ("the checkout", "checkout-email", "type", "jana@example.com"),
    ("the checkout", "checkout-address", "type", "12 Example Street"),
    ("the checkout", "checkout-city", "type", "Berlin"),
    ("the checkout", "checkout-postcode", "type", "10115"),
    ("the checkout", "checkout-country", "type", "Germany"),
    ("the checkout", "place-order", "Space", "/confirmation"),
)


@dataclass(frozen=True)
class KeyFinding:
    """One thing a keyboard check found: which check, the criteria it bears on, and what happened, in words."""

    check: str
    criteria: tuple[str, ...]
    detail: str


def describe(finding: KeyFinding) -> str:
    """One line for a report or an assertion message: check, criteria and detail."""
    return f"{finding.check} ({', '.join(finding.criteria)}): {finding.detail}"


def _finding(check: str, detail: str) -> KeyFinding:
    return KeyFinding(check=check, criteria=CRITERIA[check], detail=detail)


# --- where focus is ----------------------------------------------------------


@dataclass(frozen=True)
class _Stop:
    """Where a press of Tab landed: the element, its `data-testid` if it has one, and how it is drawn with focus."""

    key: int  # its place among the document's elements, which tells a second visit from a first
    tag: str
    testid: str | None
    outline_style: str
    outline_width: str
    box_shadow: str

    @property
    def name(self) -> str:
        return self.testid or self.tag

    @property
    def shows_focus(self) -> bool:
        """Whether an outline is drawn or a shadow cast: the two indicators the check reads.

        The style decides, not the width alone: `outline: none` leaves a computed width behind it.
        """
        return (self.outline_style != "none" and self.outline_width != "0px") or self.box_shadow != "none"


# The focused element: its place in the document, its tag, its data-testid, and the computed styles read for 2.4.7.
_FOCUSED = """() => {
  const element = document.activeElement;
  const style = getComputedStyle(element);
  return {
    key: Array.prototype.indexOf.call(document.querySelectorAll("*"), element),
    tag: element.tagName.toLowerCase(),
    testid: element.dataset.testid ?? null,
    outline_style: style.outlineStyle,
    outline_width: style.outlineWidth,
    box_shadow: style.boxShadow,
  };
}"""


def _focused(page: Page) -> _Stop:
    return _Stop(**page.evaluate(_FOCUSED))


def _tabs(page: Page) -> Iterator[_Stop]:
    """Each press of Tab and where it lands, until focus returns to an element it has been on (where it started
    counts, and so does the body, where focus rests between the last control and the first) or `TAB_LIMIT` is spent.
    """
    seen = {_focused(page).key}
    for _ in range(TAB_LIMIT):
        page.keyboard.press("Tab")
        stop = _focused(page)
        if stop.key in seen:
            return
        seen.add(stop.key)
        yield stop


def _names(stops: list[_Stop]) -> str:
    return ", ".join(stop.name for stop in stops if stop.tag != "body") or "nothing"


def _reach(page: Page, testid: str) -> str | None:
    """Press Tab until focus is on the element with this `data-testid`; when it never is, where Tab went, in words."""
    stops: list[_Stop] = []
    for stop in _tabs(page):
        if stop.testid == testid:
            return None
        stops.append(stop)
    return f"Tab reaches {_names(stops)}, never {testid}"


def _leave(page: Page, key: str, to: str) -> bool:
    """Press the key on the focused control and wait for a page whose address ends with `to`; False when none comes."""
    page.keyboard.press(key)
    try:
        page.wait_for_url(re.compile(re.escape(to) + "$"), timeout=PAGE_TIMEOUT)
    except PlaywrightTimeout:
        return False
    return True


def _path(url: str) -> str:
    return urlsplit(url).path


# --- the checks --------------------------------------------------------------


def checkout_by_keyboard(page: Page, base_url: str) -> list[KeyFinding]:
    """Buy the first product with the keyboard alone: from the list, add it, go to the cart and on to the checkout,
    fill in the details and place the order. Tab reaches each control in turn, Enter follows links, Space presses
    buttons, and the details are typed. The finding says where the journey stopped (2.1.1).
    """
    page.goto(f"{base_url}/")
    for where, testid, action, value in STEPS:
        if missed := _reach(page, testid):
            return [_finding("checkout_by_keyboard", f"On {where}, {missed}")]
        if action == "type":
            page.keyboard.type(value)
            if not page.evaluate("document.activeElement.value"):
                return [_finding("checkout_by_keyboard", f"On {where}, typing into {testid} leaves it empty")]
        elif not _leave(page, action, value):
            detail = f"On {where}, {action} on {testid} does not lead to {value}: the page stays at {_path(page.url)}"
            return [_finding("checkout_by_keyboard", detail)]
    return []


def focus_order(page: Page, url: str, expected: list[str]) -> list[KeyFinding]:
    """Tab through the page at `url` and compare where focus goes with `expected`, the `data-testid`s of the form's
    controls in the order they are shown. A finding when Tab does not visit them in that order, one after another
    (2.4.3).
    """
    page.goto(url)
    observed = [stop.name for stop in _tabs(page) if stop.tag != "body"]
    expected = list(expected)
    if any(observed[start : start + len(expected)] == expected for start in range(len(observed) - len(expected) + 1)):
        return []
    detail = (
        f"On {_path(url)}, Tab moves through {', '.join(observed)}; "
        f"expected {', '.join(expected)}, one after another"
    )
    return [_finding("focus_order", detail)]


def focus_visible(page: Page, url: str) -> list[KeyFinding]:
    """Tab through the page at `url` and read how each element is drawn while it has focus: its computed
    `outline-style`, `outline-width` and `box-shadow`. A finding for each element with no outline drawn and no shadow
    cast (2.4.7).
    """
    page.goto(url)
    return [
        _finding(
            "focus_visible",
            f"On {_path(url)}, {stop.name} ({stop.tag}) shows no focus indicator: outline-style {stop.outline_style}, "
            f"outline-width {stop.outline_width}, box-shadow {stop.box_shadow}",
        )
        for stop in _tabs(page)
        if stop.tag != "body" and not stop.shows_focus
    ]


@dataclass(frozen=True)
class _Dialog:
    """The "Added to cart" dialog as it stands: shown or not, whether focus is inside it, and what has focus."""

    open: bool
    inside: bool
    focused: str


_DIALOG = """() => {
  const dialog = document.querySelector('[data-testid="added-dialog"]');
  const focused = document.activeElement;
  return {
    open: dialog !== null && dialog.getClientRects().length > 0,
    inside: dialog !== null && dialog.contains(focused),
    focused: focused.dataset.testid ?? focused.tagName.toLowerCase(),
  };
}"""


def _dialog(page: Page) -> _Dialog:
    return _Dialog(**page.evaluate(_DIALOG))


def _open_dialog(page: Page, url: str, check: str) -> KeyFinding | None:
    """From the product page at `url`, add the product with the keyboard and wait for the "Added to cart" dialog;
    the finding when that cannot be done.
    """
    page.goto(url)
    if missed := _reach(page, "add-to-cart"):
        return _finding(check, f"On the product page, {missed}")
    page.keyboard.press("Enter")
    try:
        page.get_by_test_id("added-dialog").wait_for(state="visible", timeout=PAGE_TIMEOUT)
    except PlaywrightTimeout:
        return _finding(check, "On the product page, Enter on add-to-cart does not open the dialog")
    return None


def dialog_escape(page: Page, url: str) -> list[KeyFinding]:
    """Open the "Added to cart" dialog with the keyboard and press Escape. A finding when the dialog stays open, or
    closes without putting focus back on the control that opened it (2.1.2).
    """
    if stuck := _open_dialog(page, url, "dialog_escape"):
        return [stuck]
    page.keyboard.press("Escape")
    dialog = _dialog(page)
    if dialog.open:
        return [_finding("dialog_escape", f"Escape leaves the dialog open, with focus on {dialog.focused}")]
    if dialog.focused != "add-to-cart":
        detail = f"Escape closes the dialog, but focus goes to {dialog.focused} instead of back to add-to-cart"
        return [_finding("dialog_escape", detail)]
    return []


def dialog_trap(page: Page, url: str) -> list[KeyFinding]:
    """Open the "Added to cart" dialog with the keyboard and try to get out of it: Tab, then Shift+Tab, then Escape,
    each up to `TRAP_PRESSES` times. A finding when none of them moves focus out of the dialog or closes it (2.1.2).
    """
    if stuck := _open_dialog(page, url, "dialog_trap"):
        return [stuck]
    for key in ("Tab", "Shift+Tab", "Escape"):
        for _ in range(TRAP_PRESSES):
            page.keyboard.press(key)
            dialog = _dialog(page)
            if not dialog.open or not dialog.inside:
                return []
    detail = (
        f"{TRAP_PRESSES} presses each of Tab, Shift+Tab and Escape leave the dialog open, with focus on "
        f"{_dialog(page).focused}"
    )
    return [_finding("dialog_trap", detail)]
