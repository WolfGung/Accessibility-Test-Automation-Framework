"""The results file, the tables rendered from it, the published page and the manual checklist.

`summarize` turns the records a run collects into the results file's content;
`readme_block` and `tools.site.build` render the committed file, never a run of
their own. The committed `results/a11y.json` is pinned to the registry, so a
registry change without a re-run fails here; whether its counts are fresh
against a new run is the workflow's check (`git diff --exit-code results/`),
not a test. The page is scanned with axe the way the shop is.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import Page as BrowserPage

from a11y.axe import Finding, describe, scan
from a11y.keyboard import CRITERIA, KeyFinding
from app.main import MODES
from app.violations import VIOLATIONS
from tests.helpers import Element, Ledger, Page
from tools import report, site
from tools.report import IMPACTS, Record, readme_block, summarize, to_json, update_readme

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "docs" / "manual-checklist.md"

#: The registry as the results file carries it.
REGISTRY = [
    {"id": v.id, "title": v.title, "criteria": list(v.criteria), "page": v.page, "detected_by": v.detected_by}
    for v in VIOLATIONS
]


# --- a synthetic run ---------------------------------------------------------


def finding(rule: str, impact: str, *criteria: str) -> Finding:
    return Finding(rule=rule, impact=impact, criteria=criteria, selector=f"#{rule}", help=rule, help_url=f"u/{rule}")


def key_finding(check: str, detail: str) -> KeyFinding:
    return KeyFinding(check=check, criteria=CRITERIA[check], detail=detail)


RECORDS = (
    Record(
        "broken",
        "list",
        "axe",
        (
            finding("image-alt", "critical", "1.1.1"),
            finding("image-alt", "critical", "1.1.1"),
            finding("html-has-lang", "serious", "3.1.1"),
        ),
    ),
    # A finding with two criteria counts under each; one with none counts under none.
    Record(
        "broken",
        "checkout",
        "axe",
        (finding("label", "critical", "4.1.2", "1.3.1"), finding("region", "moderate")),
    ),
    Record(
        "broken",
        "list",
        "focus_visible",
        (key_finding("focus_visible", "skip-link"), key_finding("focus_visible", "home-link")),
    ),
    Record("broken", "product", "dialog_trap", (key_finding("dialog_trap", "the dialog stays open"),)),
    Record("fixed", "list", "axe", ()),
    Record("fixed", "product", "dialog_trap", ()),
)

ZEROS = {
    "axe": {"by_impact": dict.fromkeys(IMPACTS, 0)},
    "keyboard": {"by_check": dict.fromkeys(CRITERIA, 0)},
    "by_criterion": {},
}


def cells(line: str) -> list[str]:
    """The cells of a Markdown table row: `| a | b |` → `["a", "b"]`."""
    assert line.startswith("| ") and line.endswith(" |"), line
    return line[2:-2].split(" | ")


# --- summarize ---------------------------------------------------------------


def test_summarize_counts_the_scan_by_impact_every_finding_by_criterion_and_the_keyboard_checks_per_check() -> None:
    data = summarize(RECORDS)
    broken = data["modes"]["broken"]
    assert broken["axe"]["by_impact"] == {"critical": 3, "serious": 1, "moderate": 1, "minor": 0}
    assert broken["keyboard"]["by_check"] == {
        "checkout_by_keyboard": 0,
        "focus_order": 0,
        "focus_visible": 2,
        "dialog_escape": 0,
        "dialog_trap": 1,
    }
    assert broken["by_criterion"] == {"1.1.1": 2, "1.3.1": 1, "2.1.2": 1, "2.4.7": 2, "3.1.1": 1, "4.1.2": 1}
    assert data["modes"]["fixed"] == ZEROS
    assert set(data["modes"]) == set(MODES)


def test_summarize_carries_the_registry_with_what_finds_each_entry() -> None:
    assert summarize(RECORDS)["registry"] == REGISTRY


def test_summarize_gives_every_mode_impact_and_check_a_count_even_from_no_records() -> None:
    assert summarize([]) == {"modes": dict.fromkeys(MODES, ZEROS), "registry": REGISTRY}


def test_summarize_does_not_depend_on_the_order_of_the_records() -> None:
    assert to_json(summarize(reversed(RECORDS))) == to_json(summarize(RECORDS))


def test_the_file_text_is_sorted_indented_and_ends_with_a_newline() -> None:
    text = to_json(summarize(RECORDS))
    assert text.endswith("}\n")
    assert json.loads(text) == summarize(RECORDS)
    assert re.findall(r'^  "(\w+)"', text, flags=re.M) == ["modes", "registry"]
    assert text.index('"broken"') < text.index('"fixed"')
    assert text.index('"axe"') < text.index('"by_criterion"') < text.index('"keyboard"')


def test_the_criteria_come_out_in_the_file_s_sorted_order_which_is_the_text_s() -> None:
    # `to_json` sorts every key, so the file's order of criteria is the text's: "2.4.11" before "2.4.3". `summarize`
    # gives them in that order too, so what is read back from the file is what was summarized, key for key.
    data = summarize([Record("broken", "checkout", "axe", (finding("late", "minor", "2.4.3", "2.4.11", "1.4.3"),))])
    keys = list(data["modes"]["broken"]["by_criterion"])
    assert keys == ["1.4.3", "2.4.11", "2.4.3"] == sorted(keys)
    assert keys == list(json.loads(to_json(data))["modes"]["broken"]["by_criterion"])


def test_a_record_names_a_shop_and_a_check_the_suite_has() -> None:
    with pytest.raises(ValueError, match="mode"):
        Record("loud", "list", "axe", ())
    with pytest.raises(ValueError, match="check"):
        Record("fixed", "list", "hover", ())
    assert Record("fixed", "list", "axe", ()).key == ("fixed", "axe", "list", "axe")
    assert Record("broken", "cart", "dialog_trap", ()).key == ("broken", "keyboard", "cart", "dialog_trap")


def test_an_impact_axe_does_not_grade_is_refused() -> None:
    with pytest.raises(ValueError, match="severe"):
        summarize([Record("broken", "list", "axe", (finding("x", "severe", "1.1.1"),))])


def test_the_totals_add_the_scan_and_the_keyboard_checks_up() -> None:
    data = summarize(RECORDS)
    assert report.total_findings(data, "broken") == 8
    assert report.total_findings(data, "fixed") == 0


# --- the ledger every finding passes through ---------------------------------


def test_the_ledger_keeps_one_copy_of_a_record_and_refuses_a_different_copy() -> None:
    ledger = Ledger()
    first = Record("broken", "list", "axe", (finding("image-alt", "critical", "1.1.1"),))
    ledger.record(first)
    ledger.record(Record("broken", "list", "axe", (finding("image-alt", "critical", "1.1.1"),)))  # an equal copy
    assert ledger.records == {first.key: first}
    with pytest.raises(AssertionError, match=r"axe on the broken shop's list .*different findings"):
        ledger.record(Record("broken", "list", "axe", ()))
    assert ledger.records == {first.key: first}  # the first copy stays
    assert ledger.keys() == {first.key}


# --- the README block --------------------------------------------------------


def test_every_keyboard_check_impact_and_layer_has_words_for_the_tables() -> None:
    assert list(report.CHECKS) == list(CRITERIA)
    assert set(report.FOUND_BY) == {"axe", "keyboard", "manual"}
    assert set(report.FOUND_BY) >= {violation.detected_by for violation in VIOLATIONS}
    assert report.COLUMNS == ("broken", "fixed") and set(report.COLUMNS) == set(MODES)


def test_the_readme_block_renders_the_two_tables_from_the_committed_file() -> None:
    data = report.load()
    block = readme_block(data)
    assert report.START not in block and report.END not in block  # the markers stay in the README
    findings, registry = (table.splitlines() for table in block.strip().split("\n\n"))

    assert findings[:2] == ["| Findings | Broken shop | Fixed shop |", "| --- | ---: | ---: |"]
    rows = [cells(line) for line in findings[2:]]
    broken, fixed = data["modes"]["broken"], data["modes"]["fixed"]
    assert [row[0] for row in rows] == [f"Scan, {impact}" for impact in IMPACTS] + [
        f"Keyboard, {report.CHECKS[check]} ({', '.join(CRITERIA[check])})" for check in CRITERIA
    ]
    assert [row[1:] for row in rows] == [
        [str(broken["axe"]["by_impact"][impact]), str(fixed["axe"]["by_impact"][impact])] for impact in IMPACTS
    ] + [[str(broken["keyboard"]["by_check"][check]), str(fixed["keyboard"]["by_check"][check])] for check in CRITERIA]

    assert registry[:2] == ["| Criterion | What is wrong in the broken shop | Found by |", "| --- | --- | --- |"]
    assert [cells(line) for line in registry[2:]] == [
        [", ".join(entry["criteria"]), entry["title"], report.FOUND_BY[entry["detected_by"]]]
        for entry in data["registry"]
    ]


def test_a_cell_keeps_a_bar_from_breaking_the_table() -> None:
    assert report.markdown_table(("a | b",), [("c|d",)]) == "| a \\| b |\n| --- |\n| c\\|d |\n"


def test_a_file_whose_checks_or_impacts_differ_from_the_code_is_refused() -> None:
    data = summarize(RECORDS)
    del data["modes"]["broken"]["keyboard"]["by_check"]["dialog_trap"]
    with pytest.raises(ValueError, match="dialog_trap"):
        readme_block(data)
    data = summarize(RECORDS)
    data["modes"]["fixed"]["axe"]["by_impact"]["severe"] = 1
    with pytest.raises(ValueError, match="severe"):
        readme_block(data)


BLOCK = "| a |\n| --- |\n| 1 |\n"


def test_update_readme_puts_the_block_between_the_markers_and_changes_nothing_else() -> None:
    text = "# Title\n\nIntro.\n\n<!-- a11y:start -->\nold\n<!-- a11y:end -->\n\nAfter.\n"
    updated = update_readme(text, BLOCK)
    assert updated == "# Title\n\nIntro.\n\n<!-- a11y:start -->\n| a |\n| --- |\n| 1 |\n<!-- a11y:end -->\n\nAfter.\n"
    assert update_readme(updated, BLOCK) == updated
    markers_only = "<!-- a11y:start --><!-- a11y:end -->"
    assert update_readme(markers_only, BLOCK) == f"<!-- a11y:start -->\n{BLOCK}<!-- a11y:end -->"


@pytest.mark.parametrize(
    "text",
    ["# Title\n", "<!-- a11y:start -->\n", "<!-- a11y:end -->\n", "<!-- a11y:end -->\n<!-- a11y:start -->\n"],
)
def test_update_readme_refuses_a_readme_without_both_markers_in_order(text: str) -> None:
    with pytest.raises(ValueError, match=r"a11y:start.*a11y:end"):
        update_readme(text, BLOCK)


def test_the_command_prints_the_block_and_updates_a_readme(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert report.main(["--readme"]) == 0
    assert capsys.readouterr().out == readme_block(report.load())

    readme = tmp_path / "README.md"
    readme.write_text("# T\n\n<!-- a11y:start -->\n<!-- a11y:end -->\n", encoding="utf-8")
    assert report.main(["--update-readme", "--file", str(readme)]) == 0
    block = readme_block(report.load())
    assert readme.read_text(encoding="utf-8") == f"# T\n\n<!-- a11y:start -->\n{block}<!-- a11y:end -->\n"
    assert str(readme) in capsys.readouterr().out


def test_the_command_says_when_a_readme_has_no_markers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# T\n", encoding="utf-8")
    assert report.main(["--update-readme", "--file", str(readme)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(readme) in captured.err and "<!-- a11y:start -->" in captured.err
    assert readme.read_text(encoding="utf-8") == "# T\n"


# --- the committed file ------------------------------------------------------


def test_the_committed_file_loads_and_its_registry_is_the_code_s() -> None:
    data = report.load()
    assert data["registry"] == REGISTRY
    assert set(data["modes"]) == set(MODES)
    for mode in MODES:
        assert set(data["modes"][mode]["axe"]["by_impact"]) == set(IMPACTS)
        assert set(data["modes"][mode]["keyboard"]["by_check"]) == set(CRITERIA)


def test_the_committed_file_is_written_the_way_a_run_writes_it() -> None:
    text = report.RESULTS.read_text(encoding="utf-8")
    assert text == to_json(json.loads(text))


def test_a_missing_file_says_what_writes_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="complete run"):
        report.load(tmp_path / "a11y.json")


# --- the published page ------------------------------------------------------

RUN = {"commit": "0123abc", "date": "2026-09-23"}


def rows_of(page: Page, table: Element) -> list[list[str]]:
    """Each row of the table as the texts of its cells, the header row first."""
    return [
        [cell.text for cell in page.within(row) if cell.tag in {"th", "td"}]
        for row in page.within(table)
        if row.tag == "tr"
    ]


def test_the_page_carries_the_tables_the_report_link_and_the_run() -> None:
    data = report.load()
    page = Page(site.build(data, **RUN))
    assert page.one("html").attrs["lang"] == "en"
    assert page.heading == page.title
    assert page.one("a", href="report/").text
    words = page.one("main").text
    assert RUN["commit"] in words and RUN["date"] in words
    assert page.one("time").attrs["datetime"] == RUN["date"]

    findings, registry = page.all("table")
    for table in (findings, registry):
        assert page.within(table)[0].tag == "caption" and page.within(table)[0].text
    assert all(th.attrs.get("scope") in {"col", "row"} for th in page.all("th"))
    header, *rows = rows_of(page, findings)
    assert header == list(report.FINDINGS_HEADER)
    assert rows == [list(row) for row in report.findings_rows(data)]
    header, *rows = rows_of(page, registry)
    assert header == list(report.REGISTRY_HEADER)
    assert rows == [list(row) for row in report.registry_rows(data)]


def test_the_page_passes_the_scan_the_shop_passes(page: BrowserPage, tmp_path: Path) -> None:
    path = tmp_path / "index.html"
    path.write_text(site.build(report.load(), **RUN), encoding="utf-8")
    page.goto(path.as_uri())
    findings = scan(page)
    assert findings == [], "the page has findings of its own:\n" + "\n".join(describe(f) for f in findings)


def test_the_command_writes_the_page_for_the_commit_and_today(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef0123456789abcdef01234567")
    out = tmp_path / "site" / "index.html"
    assert site.main(["--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == site.build(report.load(), commit="0123456", date=date.today().isoformat())


def test_the_commit_comes_from_the_command_line_the_workflow_or_else_from_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef0123456789abcdef01234567")
    assert site.commit_of() == "0123456"
    assert site.commit_of("fedcba9876543210fedcba9876543210fedcba98") == "fedcba9"  # the command line comes first

    # No checkout to ask (a downloaded archive, the compose image without `.git`) and no `GITHUB_SHA`: one sentence
    # that names the way out, not a traceback; with the commit given, the page is written all the same.
    monkeypatch.delenv("GITHUB_SHA")
    monkeypatch.setattr(site, "ROOT", tmp_path)
    with pytest.raises(ValueError, match=r"GITHUB_SHA.*--commit"):
        site.commit_of()
    out = tmp_path / "index.html"
    assert site.main(["--out", str(out)]) == 1
    assert "--commit" in capsys.readouterr().err and not out.exists()
    assert site.main(["--out", str(out), "--commit", "0123abc"]) == 0
    assert out.read_text(encoding="utf-8") == site.build(report.load(), commit="0123abc", date=date.today().isoformat())

    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))  # no git binary at all: the same sentence
    with pytest.raises(ValueError, match=r"GITHUB_SHA.*--commit"):
        site.commit_of()

    asked: list[list[str]] = []

    def git(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        asked.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="987611e\n", stderr="")

    monkeypatch.setattr(site.subprocess, "run", git)
    assert site.commit_of() == "987611e"
    assert asked == [["git", "rev-parse", "--short", "HEAD"]]


def test_the_commands_say_when_the_results_file_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(report, "RESULTS", tmp_path / "a11y.json")
    assert report.main(["--readme"]) == 1
    assert "complete run" in capsys.readouterr().err
    assert site.main(["--out", str(tmp_path / "index.html")]) == 1
    assert "complete run" in capsys.readouterr().err
    assert not (tmp_path / "index.html").exists()


# --- the manual checklist ----------------------------------------------------

#: Words each section the brief asks for carries in its heading.
SECTIONS = ("alt text", "screen reader", "200%", "320", "error message")


def sections() -> dict[str, str]:
    """Each `## ` section of the checklist by its heading, with its text."""
    text = CHECKLIST.read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.M)[1:]
    return {part.partition("\n")[0].strip(): part for part in parts}


def test_the_checklist_names_the_sections_the_brief_asks_for() -> None:
    headings = [heading.lower() for heading in sections()]
    for words in SECTIONS:
        assert any(words in heading for heading in headings), f"no section about {words!r}: {headings}"


def test_every_manual_registry_entry_has_a_section_naming_its_criterion() -> None:
    found = sections()
    for violation in VIOLATIONS:
        if violation.detected_by != "manual":
            continue
        [heading] = [heading for heading in found if f"`{violation.id}`" in heading]
        assert all(criterion in found[heading] for criterion in violation.criteria), violation.id


def test_every_section_says_how_to_check_and_what_counts_as_a_failure() -> None:
    for heading, text in sections().items():
        assert "### How to check" in text and "### What counts as a failure" in text, heading


def test_the_checklist_mentions_the_screen_readers_and_browsers_the_brief_names() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for words in ("NVDA", "Windows", "Firefox", "Chrome", "VoiceOver", "macOS", "Safari", "320 CSS px", "200%"):
        assert words in text, words
