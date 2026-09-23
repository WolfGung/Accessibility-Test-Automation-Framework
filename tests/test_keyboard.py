"""The keyboard checks, run in Chromium against both shops.

Each check drives a page with Tab, Shift+Tab, Enter, Space, Escape and typing
alone, never a pointer, and answers with findings instead of asserting. On the
fixed shop every check comes back empty. On the broken shop each check reports
the planted violation the registry says it reports, on that violation's page,
and nothing a keyboard entry of the registry does not explain: so
`detected_by="keyboard"` in `app.violations` stays what a run shows. Every
check's findings go on the report.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from a11y.keyboard import (
    CRITERIA,
    KeyFinding,
    checkout_by_keyboard,
    describe,
    dialog_escape,
    dialog_trap,
    focus_order,
    focus_visible,
)
from app import checkout
from app.catalog import PRODUCTS
from app.violations import VIOLATIONS, Violation
from tests.helpers import attach_findings

if TYPE_CHECKING:
    from tests.conftest import Pages

MUG = PRODUCTS[1]

#: The planted violations a run of the keyboard checks has shown they report.
KEYBOARD_FINDS = tuple(violation for violation in VIOLATIONS if violation.detected_by == "keyboard")

#: The checkout form's controls in the order they are shown, which is the order Tab should follow.
CHECKOUT_ORDER = [f"checkout-{name}" for name in checkout.FIELDS] + ["place-order"]


@dataclass(frozen=True)
class Run:
    """One check on one page of the shop: how the test gets the browser there and runs the check."""

    check: str
    page: str  # the page of the shop, as the registry names pages
    go: Callable[[Pages, str], list[KeyFinding]]

    @property
    def id(self) -> str:
        return f"{self.check}-{self.page}"

    def __call__(self, pages: Pages, shop: str) -> list[KeyFinding]:
        return self.go(pages, shop)


def visible_on(page_name: str) -> Callable[[Pages, str], list[KeyFinding]]:
    """`focus_visible` on this page, at the address the shopper's steps reach it by."""
    return lambda pages, shop: focus_visible(pages.page, pages.visit(shop, page_name).url)


#: Every check on every page it runs on. `focus_visible` walks each page of the shop; the journey starts on the
#: list; `focus_order` reads the checkout form; the two dialog checks open the product page's dialog.
RUNS = (
    Run("checkout_by_keyboard", "list", lambda pages, shop: checkout_by_keyboard(pages.page, shop)),
    Run(
        "focus_order",
        "checkout",
        lambda pages, shop: focus_order(pages.page, pages.visit(shop, "checkout").url, CHECKOUT_ORDER),
    ),
    *(Run("focus_visible", page_name, visible_on(page_name)) for page_name in ("list", "product", "cart", "checkout")),
    Run("dialog_escape", "product", lambda pages, shop: dialog_escape(pages.page, f"{shop}/product/{MUG.id}")),
    Run("dialog_trap", "product", lambda pages, shop: dialog_trap(pages.page, f"{shop}/product/{MUG.id}")),
)

#: Each keyboard-detected violation with each run that is to report it: a run on its page whose check tests one of
#: its criteria.
PREDICTED = [
    (violation, run)
    for violation in KEYBOARD_FINDS
    for run in RUNS
    if violation.page in (run.page, "every page") and set(CRITERIA[run.check]) & set(violation.criteria)
]


def explains(violation: Violation, finding: KeyFinding) -> bool:
    """Whether the planted violation accounts for the finding: they share a success criterion."""
    return bool(set(violation.criteria) & set(finding.criteria))


def lines(findings: list[KeyFinding]) -> str:
    return "\n".join(describe(finding) for finding in findings) or "(nothing)"


@pytest.mark.parametrize("run", RUNS, ids=[run.id for run in RUNS])
def test_the_fixed_shop_passes_every_check(pages: Pages, fixed_shop: str, run: Run) -> None:
    findings = run(pages, fixed_shop)
    attach_findings(f"{run.check} on the fixed shop: {run.page}", findings)
    assert findings == [], f"{run.check} reports on the fixed shop's {run.page}:\n{lines(findings)}"


@pytest.mark.parametrize(("violation", "run"), PREDICTED, ids=[f"{v.id}-{run.id}" for v, run in PREDICTED])
def test_the_checks_find_each_violation_the_registry_says_they_find(
    pages: Pages, broken_shop: str, violation: Violation, run: Run
) -> None:
    findings = run(pages, broken_shop)
    attach_findings(f"{run.check} on the broken shop: {run.page}", findings)
    assert any(explains(violation, finding) for finding in findings), (
        f"{run.check} did not report {violation.id} ({', '.join(violation.criteria)}) on the broken shop's "
        f"{run.page}; it reported:\n{lines(findings)}"
    )


@pytest.mark.parametrize("run", RUNS, ids=[run.id for run in RUNS])
def test_every_finding_on_the_broken_shop_is_a_planted_violation(pages: Pages, broken_shop: str, run: Run) -> None:
    findings = run(pages, broken_shop)
    attach_findings(f"{run.check} on the broken shop: {run.page}", findings)
    planted = [violation for violation in KEYBOARD_FINDS if violation.page in (run.page, "every page")]
    unexplained = [finding for finding in findings if not any(explains(v, finding) for v in planted)]
    assert unexplained == [], (
        f"{run.check} reports on the broken shop's {run.page} what no registry entry with detected_by='keyboard' "
        f"explains:\n{lines(unexplained)}"
    )


def test_each_keyboard_entry_has_a_run_that_looks_for_it() -> None:
    """A violation the registry hands to the keyboard checks is looked for: a run on its page tests its criterion."""
    assert {violation.id for violation in KEYBOARD_FINDS} == {violation.id for violation, _ in PREDICTED}


def test_no_violation_is_left_unknown() -> None:
    """With the scan and the keyboard checks run, each violation names the layer that finds it or the checklist."""
    left = {violation.id: violation.detected_by for violation in VIOLATIONS if violation.detected_by == "unknown"}
    assert left == {}, f"still unknown: {left}"
    assert all(violation.detected_by in {"axe", "keyboard", "manual"} for violation in VIOLATIONS)
