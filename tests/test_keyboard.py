"""The keyboard checks, run in Chromium against both shops.

Each check drives a page with Tab, Shift+Tab, Enter, Space, Escape and typing
alone, never a pointer, and answers with findings instead of asserting. On the
fixed shop every check comes back empty. On the broken shop each check reports
the planted violation the registry says it reports, on that violation's page,
and nothing a keyboard entry of the registry does not explain: so
`detected_by="keyboard"` in `app.violations` stays what a run shows. Every
check's findings go on the report and, at the end of a complete run, into the
results file.
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
from app.main import MODES
from app.violations import VIOLATIONS, Violation
from tests.helpers import PAGE_OF, attach_findings
from tools.report import Key

if TYPE_CHECKING:
    from tests.conftest import Pages

MUG = PRODUCTS[1]

#: The planted violations a run of the keyboard checks has shown they report.
KEYBOARD_FINDS = tuple(violation for violation in VIOLATIONS if violation.detected_by == "keyboard")

#: The checkout form's controls in the order they are shown, which is the order Tab should follow.
CHECKOUT_ORDER = [f"checkout-{name}" for name in checkout.FIELDS] + ["place-order"]


@dataclass(frozen=True)
class Run:
    """One check on one page state of the shop: how the test gets the browser there and runs the check."""

    check: str
    state: str  # the page state, as `tests.helpers.PAGES` names them
    go: Callable[[Pages, str], list[KeyFinding]]
    looks_for_plants: bool = True  # whether a planted violation on its page can show in this run's findings

    @property
    def page(self) -> str:
        """The page of the shop the state shows, as the registry names pages."""
        return PAGE_OF[self.state]

    @property
    def id(self) -> str:
        return f"{self.check}-{self.state}"

    def __call__(self, pages: Pages, shop: str) -> list[KeyFinding]:
        return self.go(pages, shop)


def visible_on(page_name: str) -> Callable[[Pages, str], list[KeyFinding]]:
    """`focus_visible` on this page, at the address the shopper's steps reach it by."""
    return lambda pages, shop: focus_visible(pages.page, pages.visit(shop, page_name).url)


def visible_as_it_stands(state: str) -> Callable[[Pages, str], list[KeyFinding]]:
    """`focus_visible` on the page as the shopper's steps leave it: a state that is not an address of its own."""

    def go(pages: Pages, shop: str) -> list[KeyFinding]:
        pages.visit(shop, state)
        return focus_visible(pages.page)

    return go


#: Every check on every page state it runs on. `focus_visible` walks each page of the shop and the two states that
#: change one; the journey starts on the list; `focus_order` reads the checkout form; the two dialog checks open the
#: product page's dialog themselves.
RUNS = (
    Run("checkout_by_keyboard", "list", lambda pages, shop: checkout_by_keyboard(pages.page, shop)),
    Run(
        "focus_order",
        "checkout",
        lambda pages, shop: focus_order(pages.page, pages.visit(shop, "checkout").url, CHECKOUT_ORDER),
    ),
    *(Run("focus_visible", page_name, visible_on(page_name)) for page_name in ("list", "product", "cart", "checkout")),
    # The broken dialog puts focus on itself and takes it back on every Tab, so nothing there is a Tab stop and
    # `focus_visible` has nothing to read: the trap checks carry the verdict on that dialog. The run stays, for the
    # fixed dialog's controls and so that nothing unexplained can appear on the broken one.
    Run("focus_visible", "dialog", visible_as_it_stands("dialog"), looks_for_plants=False),
    Run("focus_visible", "checkout-errors", visible_as_it_stands("checkout-errors")),
    Run("dialog_escape", "product", lambda pages, shop: dialog_escape(pages.page, f"{shop}/product/{MUG.id}")),
    Run("dialog_trap", "product", lambda pages, shop: dialog_trap(pages.page, f"{shop}/product/{MUG.id}")),
)

#: What a complete run of this module records for the results file: every run, on both shops.
EXPECTED_RECORDS = frozenset(Key.of(mode, run.state, run.check) for mode in MODES for run in RUNS)

#: Each keyboard-detected violation with each run that is to report it: a run on its page whose check tests one of
#: its criteria, where a plant can show.
PREDICTED = [
    (violation, run)
    for violation in KEYBOARD_FINDS
    for run in RUNS
    if run.looks_for_plants
    and violation.page in (run.page, "every page")
    and set(CRITERIA[run.check]) & set(violation.criteria)
]


def stopped_on(finding: KeyFinding) -> str | None:
    """The page a journey's finding names first (`page: what happened`); None for the other checks, which stay on
    the page their run is on.
    """
    return finding.detail.partition(":")[0] if finding.check == "checkout_by_keyboard" else None


def explains(violation: Violation, finding: KeyFinding, run: Run) -> bool:
    """Whether the planted violation accounts for the finding: they share a success criterion, and the violation is
    on the page the finding is about — the page the journey stopped on, or the page the run is on.
    """
    on = stopped_on(finding) or run.page
    return bool(set(violation.criteria) & set(finding.criteria)) and violation.page in (on, "every page")


def lines(findings: list[KeyFinding]) -> str:
    return "\n".join(describe(finding) for finding in findings) or "(nothing)"


@pytest.mark.parametrize("run", RUNS, ids=[run.id for run in RUNS])
def test_the_fixed_shop_passes_every_check(pages: Pages, fixed_shop: str, run: Run) -> None:
    findings = run(pages, fixed_shop)
    attach_findings(run.check, "fixed", run.state, findings)
    assert findings == [], f"{run.check} reports on the fixed shop's {run.state}:\n{lines(findings)}"


@pytest.mark.parametrize(("violation", "run"), PREDICTED, ids=[f"{v.id}-{run.id}" for v, run in PREDICTED])
def test_the_checks_find_each_violation_the_registry_says_they_find(
    pages: Pages, broken_shop: str, violation: Violation, run: Run
) -> None:
    findings = run(pages, broken_shop)
    attach_findings(run.check, "broken", run.state, findings)
    assert any(explains(violation, finding, run) for finding in findings), (
        f"{run.check} did not report {violation.id} ({', '.join(violation.criteria)}) on the broken shop's "
        f"{run.state}; it reported:\n{lines(findings)}"
    )


@pytest.mark.parametrize("run", RUNS, ids=[run.id for run in RUNS])
def test_every_finding_on_the_broken_shop_is_a_planted_violation(pages: Pages, broken_shop: str, run: Run) -> None:
    findings = run(pages, broken_shop)
    attach_findings(run.check, "broken", run.state, findings)
    unexplained = [finding for finding in findings if not any(explains(v, finding, run) for v in KEYBOARD_FINDS)]
    assert unexplained == [], (
        f"{run.check} reports on the broken shop's {run.state} what no registry entry with detected_by='keyboard' "
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
