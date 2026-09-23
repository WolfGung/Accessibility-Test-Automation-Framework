"""The automated scan, run in Chromium against both shops.

The fixed shop carries no serious or critical finding on any page. On the
broken shop axe finds each planted violation the registry says it finds, on
that violation's page, and reports nothing serious that the registry does not
explain: so `detected_by="axe"` in `app.violations` stays what a run shows.
Every scan's findings go on the report.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from a11y.axe import SERIOUS, Finding, describe, scan
from app.violations import VIOLATIONS, Violation
from tests.helpers import PAGES, attach_findings

if TYPE_CHECKING:
    from tests.conftest import Pages

#: The planted violations a run of axe has shown it reports.
AXE_FINDS = tuple(violation for violation in VIOLATIONS if violation.detected_by == "axe")

#: Each of them with each page state it is looked for on: its page as it opens, or every state for a violation on
#: every page. Not the `dialog` state for one on the product page: while the dialog is open the rest of the page is
#: `inert`, and axe then leaves the product's price out as not applicable to color-contrast.
AXE_FINDS_ON = [
    (violation, state)
    for violation in AXE_FINDS
    for state in (PAGES if violation.page == "every page" else (violation.page,))
]


def serious(findings: list[Finding]) -> list[Finding]:
    return [finding for finding in findings if finding.impact in SERIOUS]


def explains(violation: Violation, finding: Finding) -> bool:
    """Whether the planted violation accounts for the finding: they share a success criterion."""
    return bool(set(violation.criteria) & set(finding.criteria))


def lines(findings: list[Finding]) -> str:
    return "\n".join(describe(finding) for finding in findings) or "(nothing)"


def test_the_fixed_shop_has_no_serious_finding(pages: Pages, fixed_shop: str, state: str) -> None:
    findings = scan(pages.visit(fixed_shop, state))
    attach_findings(f"axe on the fixed shop: {state}", findings)
    assert serious(findings) == [], f"serious findings on the fixed shop's {state}:\n{lines(serious(findings))}"


@pytest.mark.parametrize(("violation", "state"), AXE_FINDS_ON, ids=[f"{v.id}-{state}" for v, state in AXE_FINDS_ON])
def test_axe_finds_each_violation_the_registry_says_it_finds(
    pages: Pages, broken_shop: str, violation: Violation, state: str
) -> None:
    findings = scan(pages.visit(broken_shop, state))
    attach_findings(f"axe on the broken shop: {state}", findings)
    assert any(explains(violation, finding) for finding in findings), (
        f"axe did not report {violation.id} ({', '.join(violation.criteria)}) on {state}; it reported:\n"
        f"{lines(findings)}"
    )


def test_every_serious_finding_on_the_broken_shop_is_a_planted_violation(
    pages: Pages, broken_shop: str, state: str
) -> None:
    findings = scan(pages.visit(broken_shop, state))
    attach_findings(f"axe on the broken shop: {state}", findings)
    planted = [violation for violation in AXE_FINDS if state in pages.showing(violation.page)]
    unexplained = [finding for finding in serious(findings) if not any(explains(v, finding) for v in planted)]
    assert unexplained == [], (
        f"axe reports on the broken shop's {state} what no registry entry with detected_by='axe' explains:\n"
        f"{lines(unexplained)}"
    )


def test_the_scan_puts_the_pinned_axe_into_each_document_once(pages: Pages, fixed_shop: str) -> None:
    page = pages.visit(fixed_shop, "list")
    scripts = page.locator("script").count()
    scan(page)
    assert page.evaluate("axe.version") == "4.13.0"
    assert page.locator("script").count() == scripts + 1
    scan(page)  # the same document again: nothing is added
    assert page.locator("script").count() == scripts + 1
    pages.visit(fixed_shop, "product")  # a new document starts without it
    assert page.evaluate("typeof axe") == "undefined"
    scan(page)
    assert page.evaluate("axe.version") == "4.13.0"
