"""The results file, and the tables rendered from it.

A run of the suite collects every finding the scan and the keyboard checks
produce — `tests/conftest.py` gathers them, one record per mode, layer, page
state and check — and, when the run was complete, writes `results/a11y.json`
through `summarize`. The README's block between `<!-- a11y:start -->` and
`<!-- a11y:end -->` and the published page are rendered from that file, never
from a run of their own: `readme_block` gives the block, `update_readme` puts
it in place.

    python -m tools.report --readme          # print the block
    python -m tools.report --update-readme   # write it between the README's markers

The file holds counts only, no finding and no time: the same run writes the
same bytes, and a change in it is a change in what was found.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from a11y.keyboard import CRITERIA
from app.main import MODES
from app.violations import VIOLATIONS

if TYPE_CHECKING:
    from a11y.axe import Finding
    from a11y.keyboard import KeyFinding

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "a11y.json"
README = ROOT / "README.md"

#: The README's markers: the block goes between them, on lines of its own.
START, END = "<!-- a11y:start -->", "<!-- a11y:end -->"

#: The scan's name as a check, next to the keyboard checks' names in `a11y.keyboard.CRITERIA`.
AXE = "axe"

#: The two layers of checks a record belongs to.
LAYERS = ("axe", "keyboard")

#: How axe grades a finding, worst first.
IMPACTS = ("critical", "serious", "moderate", "minor")

#: The shops as the tables show them: the broken one first.
COLUMNS = ("broken", "fixed")

#: What a finding of each keyboard check is, in words, for the tables.
CHECKS = {
    "checkout_by_keyboard": "stops on the way to an order with the keyboard alone",
    "focus_order": "forms whose fields Tab reaches out of their order",
    "focus_visible": "Tab stops with no visible focus",
    "dialog_escape": "dialogs Escape does not close, or closes without returning focus",
    "dialog_trap": "dialogs focus cannot leave",
}

#: What found each planted violation, in words, by the registry's `detected_by`.
FOUND_BY = {"axe": "axe-core scan", "keyboard": "keyboard checks", "manual": "manual checklist"}

FINDINGS_HEADER = ("Findings", "Broken shop", "Fixed shop")
REGISTRY_HEADER = ("Criterion", "What is wrong in the broken shop", "Found by")


# --- what a run collects -----------------------------------------------------


def layer_of(check: str) -> str:
    """The layer a check belongs to: the scan, or the keyboard checks."""
    if check == AXE:
        return "axe"
    if check in CRITERIA:
        return "keyboard"
    raise ValueError(f"no such check: {check!r} (the scan is {AXE!r}; the keyboard checks are {', '.join(CRITERIA)})")


class Key(NamedTuple):
    """What tells one record from another: the shop's mode, the layer, the page state and the check."""

    mode: str
    layer: str
    state: str
    check: str

    @classmethod
    def of(cls, mode: str, state: str, check: str) -> Key:
        return cls(mode, layer_of(check), state, check)


@dataclass(frozen=True)
class Record:
    """One check's findings on one page state of one shop: what a run collects, one record per key."""

    mode: str  # fixed or broken
    state: str  # the page state, as `tests.helpers.PAGES` names them
    check: str  # `AXE` for the scan, or a keyboard check's name
    findings: tuple[Finding | KeyFinding, ...]

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"no such mode: {self.mode!r} (the shop runs as {' or '.join(MODES)})")
        layer_of(self.check)  # refuses a check the suite does not have

    @property
    def layer(self) -> str:
        return layer_of(self.check)

    @property
    def key(self) -> Key:
        return Key.of(self.mode, self.state, self.check)


def summarize(records: Iterable[Record]) -> dict:
    """The results file's content: per mode, the scan's findings by impact, every finding by criterion and the
    keyboard checks' findings per check; and the registry with what finds each entry.

    Counts only. A finding with two criteria counts under each. Every mode, impact and check has an entry, zero when
    nothing was found; a criterion appears only when something was found under it. The order of the records does not
    matter.
    """
    by_impact = {mode: dict.fromkeys(IMPACTS, 0) for mode in MODES}
    by_check = {mode: dict.fromkeys(CRITERIA, 0) for mode in MODES}
    by_criterion: dict[str, Counter[str]] = {mode: Counter() for mode in MODES}
    for record in records:
        for finding in record.findings:
            if record.layer == "axe":
                impact = finding.impact
                if impact not in IMPACTS:
                    raise ValueError(f"axe grades a finding {', '.join(IMPACTS)}, not {impact!r}")
                by_impact[record.mode][impact] += 1
            else:
                by_check[record.mode][record.check] += 1
            by_criterion[record.mode].update(finding.criteria)
    return {
        "modes": {
            mode: {
                "axe": {"by_impact": by_impact[mode]},
                "keyboard": {"by_check": by_check[mode]},
                # In the file's order, which `to_json` makes the sorted one (lexical, and today also numeric).
                "by_criterion": dict(sorted(by_criterion[mode].items())),
            }
            for mode in MODES
        },
        "registry": [
            {
                "id": violation.id,
                "title": violation.title,
                "criteria": list(violation.criteria),
                "page": violation.page,
                "detected_by": violation.detected_by,
            }
            for violation in VIOLATIONS
        ],
    }


def total_findings(data: dict, mode: str) -> int:
    """How many findings the run had on this shop, from both layers."""
    counts = data["modes"][mode]
    return sum(counts["axe"]["by_impact"].values()) + sum(counts["keyboard"]["by_check"].values())


# --- the file ----------------------------------------------------------------


def to_json(data: dict) -> str:
    """The file's text: sorted keys, two-space indent, a newline at the end. The same data gives the same bytes."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(data: dict, path: Path | None = None) -> None:
    """Write the results file (`RESULTS` unless another path is given), making its directory if need be."""
    path = RESULTS if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(data), encoding="utf-8")


def load(path: Path | None = None) -> dict:
    """The results file's content (`RESULTS` unless another path is given)."""
    path = RESULTS if path is None else path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"{path} is missing: a complete run of the suite writes it") from None


# --- the tables --------------------------------------------------------------


def findings_rows(data: dict) -> list[tuple[str, ...]]:
    """The findings table's rows: one per impact of the scan, then one per keyboard check; the counts per shop."""
    modes = data["modes"]
    for mode in COLUMNS:
        _same(f"the impacts of the {mode} shop", modes[mode]["axe"]["by_impact"], IMPACTS)
        _same(f"the checks of the {mode} shop", modes[mode]["keyboard"]["by_check"], CRITERIA)
    rows = [
        (f"Scan, {impact}", *(str(modes[mode]["axe"]["by_impact"][impact]) for mode in COLUMNS)) for impact in IMPACTS
    ]
    rows += [
        (
            f"Keyboard, {CHECKS[check]} ({', '.join(CRITERIA[check])})",
            *(str(modes[mode]["keyboard"]["by_check"][check]) for mode in COLUMNS),
        )
        for check in CRITERIA
    ]
    return rows


def _same(what: str, found: Iterable[str], known: Iterable[str]) -> None:
    """The file names the impacts and checks the code knows, or it is stale: say which side has what."""
    found, known = set(found), set(known)
    if found != known:
        raise ValueError(
            f"{what} in the results file are not the code's: the file has {sorted(found - known) or 'nothing'} "
            f"the code does not, the code has {sorted(known - found) or 'nothing'} the file does not; re-run the suite"
        )


def registry_rows(data: dict) -> list[tuple[str, ...]]:
    """The registry table's rows: each planted violation's criteria, title and what found it."""
    return [
        (", ".join(entry["criteria"]), entry["title"], FOUND_BY[entry["detected_by"]]) for entry in data["registry"]
    ]


def markdown_table(header: Sequence[str], rows: Iterable[Sequence[str]], numbers_from: int | None = None) -> str:
    """A Markdown table; the columns from `numbers_from` on are right-aligned."""
    align = ["---"] * len(header)
    if numbers_from is not None:
        align[numbers_from:] = ["---:"] * (len(header) - numbers_from)
    lines = [_row(header), _row(align), *(_row(row) for row in rows)]
    return "\n".join(lines) + "\n"


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def readme_block(data: dict) -> str:
    """The README's block, without its markers: the findings on both shops, then the planted violations."""
    findings = markdown_table(FINDINGS_HEADER, findings_rows(data), numbers_from=1)
    registry = markdown_table(REGISTRY_HEADER, registry_rows(data))
    return f"{findings}\n{registry}"


def update_readme(text: str, block: str) -> str:
    """The README's text with the block between its markers, each marker on a line of its own; nothing else changes."""
    start, end = text.find(START), text.find(END)
    if start < 0 or end < start:
        raise ValueError(f"no {START} … {END} markers, in that order, to put the block between")
    return f"{text[: start + len(START)]}\n{block.rstrip()}\n{text[end:]}"


# --- the command -------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.report", description="Render the README's tables from the results file of a run."
    )
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--readme", action="store_true", help="print the block that goes between the README's markers")
    what.add_argument("--update-readme", action="store_true", help="write the block between the README's markers")
    parser.add_argument("--file", type=Path, default=README, help="the README to update (default: the repository's)")
    args = parser.parse_args(argv)
    try:
        block = readme_block(load())
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1
    except ValueError as error:  # the file names impacts or checks the code does not: stale
        print(f"{RESULTS}: {error}", file=sys.stderr)
        return 1
    if args.readme:
        sys.stdout.write(block)
        return 0
    try:
        text = args.file.read_text(encoding="utf-8")
        args.file.write_text(update_readme(text, block), encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"{args.file}: {error}", file=sys.stderr)
        return 1
    print(f"{args.file}: the block between {START} and {END} is now the results file's")
    return 0


if __name__ == "__main__":
    sys.exit(main())
