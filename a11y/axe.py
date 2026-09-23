"""The automated scan: axe-core, pinned in `vendor/`, run in the browser on the page it is given.

`scan` puts the vendored script into the page once per document and runs the
rules tagged for WCAG 2.1 level A and AA, nothing more: no best practices, no
experimental rules. Each element axe reports becomes one `Finding`, so a page's
findings can be put on a report, matched against the registry of planted
violations, or required to be empty.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page

from a11y.wcag import criteria_from_tags

AXE = Path(__file__).resolve().parents[1] / "vendor" / "axe.min.js"

#: The rules that run: those tagged for WCAG 2.1 level A and AA (the criteria of 2.0 carry the 2.0 tags).
TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa")

#: The impacts a fixed page must not carry. axe grades each finding minor, moderate, serious or critical.
SERIOUS = frozenset({"serious", "critical"})

# Runs axe on the context it is given (a selector, or the whole document) and answers with the violations only.
_RUN = "([context, options]) => axe.run(context ?? document, options).then((results) => results.violations)"


@dataclass(frozen=True)
class Finding:
    """One element axe reports: the rule it fails, how badly, which criteria, where, and where the rule is explained."""

    rule: str
    impact: str
    criteria: tuple[str, ...]
    selector: str
    help: str
    help_url: str


def describe(finding: Finding) -> str:
    """One line for a report or an assertion message: rule, impact, criteria, selector, help and link."""
    criteria = ", ".join(finding.criteria) or "no criterion"
    return f"{finding.rule} [{finding.impact}] ({criteria}) at {finding.selector}: {finding.help} — {finding.help_url}"


def scan(page: Page, *, include: str | None = None) -> list[Finding]:
    """The violations axe finds on the page, or inside `include` (a CSS selector), one finding per element."""
    if page.evaluate("typeof axe === 'undefined'"):
        page.add_script_tag(path=str(AXE))
    options = {"runOnly": {"type": "tag", "values": list(TAGS)}, "resultTypes": ["violations"]}
    violations = page.evaluate(_RUN, [include, options])
    return [
        Finding(
            rule=violation["id"],
            impact=node.get("impact") or violation["impact"],
            criteria=criteria_from_tags(violation["tags"]),
            selector=_selector(node["target"]),
            help=violation["help"],
            help_url=violation["helpUrl"],
        )
        for violation in violations
        for node in violation["nodes"]
    ]


def _selector(target: list[str | list[str]]) -> str:
    """The element's selector. axe writes one per frame or shadow root on the way in; they are joined outer to inner."""
    return " ".join(" ".join(part) if isinstance(part, list) else part for part in target)
