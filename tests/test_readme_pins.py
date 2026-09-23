"""The README says only what the repository can check, and these tests hold it to that.

The README is read once, and each pin protects one line of it: the block
between the markers is what `tools.report` renders from the committed results
file; the counts of tests are what `pytest --collect-only` collects; "four,
four and two" come from the registry; every relative link points at a file;
the badges name this repository and its page; the first screen has the shape
it was asked to have, in sentences of at most 25 words; the workflow, the
Dockerfile and the compose file do what the README says they do; and neither
the README, the checklist nor the workflow carries a word this repository
keeps out or a claim a scan cannot make.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from a11y.keyboard import CRITERIA
from app.violations import VIOLATIONS
from tests.test_vendor import VERSION as AXE_VERSION
from tools.report import END, README, ROOT, START, load, readme_block, update_readme

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CHECKLIST = ROOT / "docs" / "manual-checklist.md"
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "docker-compose.yml"
MAKEFILE = ROOT / "Makefile"

REPOSITORY = "WolfGung/Accessibility-Test-Automation-Framework"
PAGE = "https://wolfgung.github.io/Accessibility-Test-Automation-Framework/"
TITLE = "# Accessibility Test Automation Framework"

#: The most words a sentence on the first screen may have.
LONGEST = 25

#: The number words the README uses where it counts what the registry holds.
WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")

#: The actions the workflow may use, each at the one version it is pinned to.
ACTIONS = frozenset(
    {
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/upload-artifact@v4",
        "actions/download-artifact@v4",
        "actions/upload-pages-artifact@v3",
        "actions/deploy-pages@v4",
    }
)

# Words that never appear in this repository: names of tools it does not use,
# and claims a scan cannot make about a page. Each is written as two adjacent
# string literals, so that the list itself does not put the word in whole.
KEPT_OUT = (
    "a" "i",
    "l" "lm",
    "pro" "mpt",
    "g" "pt",
    "co" "pilot",
    "cl" "aude",
    "chatg" "pt",
    "anth" "ropic",
    "compl" "iant",
    "compl" "iance",
    "cert" "ified",
    "cert" "ification",
    "conf" "orms",
    "conf" "ormance",
    "conf" "ormant",
    "guar" "antee",
    "guar" "anteed",
    "guar" "antees",
)

TEXT = README.read_text(encoding="utf-8")


# --- reading the README ------------------------------------------------------


def section(heading: str) -> str:
    """The text under `## heading`, up to the next `## ` heading or the end."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", TEXT, flags=re.M | re.S)
    assert match, f"README: no section '## {heading}'"
    return match.group(1)


def sentences(prose: str) -> list[str]:
    """The sentences of a passage: split where `.`, `!` or `?` is followed by a space or the end."""
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", prose.strip()) if part.strip()]


def prose_of(bullet: str) -> str:
    """A bullet's words without the `- ` and the bold marks."""
    assert bullet.startswith("- "), f"README: not a bullet: {bullet!r}"
    return bullet[2:].replace("**", "")


def cells(line: str) -> list[str]:
    """The cells of a Markdown table row: `| a | b |` → `["a", "b"]`."""
    assert line.startswith("| ") and line.endswith(" |"), line
    return line[2:-2].split(" | ")


def collected() -> Counter[str]:
    """How many tests `pytest --collect-only` collects, per module, from a run of this repository's suite."""
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, f"pytest --collect-only failed:\n{run.stdout}\n{run.stderr}"
    return Counter(line.partition("::")[0] for line in run.stdout.splitlines() if "::" in line)


# --- the block ---------------------------------------------------------------


def test_the_block_between_the_markers_is_the_results_file_s() -> None:
    block = readme_block(load())
    start, end = TEXT.index(START) + len(START), TEXT.index(END)
    assert TEXT[start:end].strip("\n") == block.strip("\n"), (
        "README: the block between the markers is not what `python -m tools.report --readme` prints for "
        "results/a11y.json; run `python -m tools.report --update-readme`"
    )
    assert update_readme(TEXT, block) == TEXT, "README: `--update-readme` would change the file"


# --- the numbers -------------------------------------------------------------


def test_the_counts_of_tests_are_what_pytest_collects() -> None:
    counts = collected()
    rows = [cells(line) for line in section("How the repository is put together").splitlines() if line.startswith("| ")]
    listed: dict[str, int] = {}
    for module, _, count in rows[2:-1]:
        [path] = set(re.findall(r"tests/test_\w+\.py", module))  # the link's text and its target name the same file
        listed[path] = int(count)
    assert listed == dict(counts), "README: the table of tests does not say what `pytest --collect-only` collects"
    total = sum(counts.values())
    assert rows[-1][0].startswith("the whole suite") and int(rows[-1][-1]) == total, (
        "README: the last row of the table of tests is not the whole suite's count"
    )
    for number in re.findall(r"\b(\d+) tests\b", TEXT):
        assert int(number) == total, f"README says '{number} tests'; the suite has {total}"


def test_the_registry_s_counts_are_the_readme_s() -> None:
    found = Counter(violation.detected_by for violation in VIOLATIONS)
    line = (
        f"Of the {WORDS[len(VIOLATIONS)]} planted violations, the scan finds {WORDS[found['axe']]}, "
        f"the keyboard checks find {WORDS[found['keyboard']]}, and {WORDS[found['manual']]} are left to the "
        "manual checklist."
    )
    cannot = section("What automated checks cannot tell you")
    assert line in cannot, (
        f"README: 'What automated checks cannot tell you' does not open with the registry's counts:\n{line}"
    )
    for number in re.findall(rf"\b({'|'.join(WORDS)}|\d+) planted violations\b", TEXT):
        assert number == WORDS[len(VIOLATIONS)], (
            f"README says '{number} planted violations'; the registry has {len(VIOLATIONS)}"
        )
    for violation in VIOLATIONS:
        if violation.detected_by == "manual":
            assert f"({', '.join(violation.criteria)})" in cannot, (
                f"README: the manual entry {violation.id} is not named with its criteria under "
                "'What automated checks cannot tell you'"
            )
    assert f"{WORDS[len(CRITERIA)]} checks (" in TEXT, f"README: the keyboard layer has {len(CRITERIA)} checks"
    assert f"axe-core {AXE_VERSION}" in TEXT, f"README: the vendored axe-core is {AXE_VERSION}"


# --- the links and the badges ------------------------------------------------


def test_every_relative_link_points_at_something_in_the_repository() -> None:
    for target in re.findall(r"\]\(([^)\s]+)\)", TEXT):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = target.partition("#")[0]
        assert (ROOT / path).exists(), f"README links to {target}, which is not in the repository"


def test_the_badges_name_this_repository_and_its_page() -> None:
    badges = [line for line in TEXT.splitlines() if line.startswith("[![")]
    assert len(badges) == 4, "README: four badges, CI, live report, Python and licence"
    ci, live, python, licence = badges
    workflow = f"https://github.com/{REPOSITORY}/actions/workflows/ci.yml"
    assert ci == f"[![CI]({workflow}/badge.svg)]({workflow})", "README: the CI badge is not this repository's workflow"
    assert live.startswith("[![live report]") and live.endswith(f"]({PAGE})"), "README: the live report is the page"
    [version] = re.findall(r'requires-python = ">=(\d+\.\d+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert python == f"[![Python {version}](https://img.shields.io/badge/Python-{version}-blue)](pyproject.toml)", (
        f"README: the Python badge is not pyproject's {version}"
    )
    assert licence.startswith("[![license: MIT]") and licence.endswith("](LICENSE)"), "README: the licence badge"
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")


def test_every_make_target_the_readme_names_exists() -> None:
    targets = set(re.findall(r"^([a-z][\w-]*):", MAKEFILE.read_text(encoding="utf-8"), flags=re.M))
    for named in re.findall(r"\bmake ([a-z][\w-]*)", TEXT):
        assert named in targets, f"README names `make {named}`, which the Makefile does not have"


# --- the first screen --------------------------------------------------------


def test_the_first_screen_is_the_title_one_sentence_the_badges_the_block_and_three_bullets() -> None:
    before = [part for part in TEXT[: TEXT.index(START)].split("\n\n") if part.strip()]
    assert len(before) == 3, "README: before the block come the title, one sentence and the badges, nothing else"
    title, sentence, badges = before
    assert title == TITLE, "README: the first line is the title"
    assert sentences(sentence) == [sentence], "README: the second paragraph is one sentence"
    assert all(line.startswith("[![") for line in badges.splitlines()), "README: the badges come third"
    after = TEXT[TEXT.index(END) + len(END) :]
    assert after.lstrip("\n").startswith("## What this shows\n"), "README: 'What this shows' follows the block"
    bullets = [line for line in section("What this shows").splitlines() if line.strip()]
    assert len(bullets) == 3 and all(bullet.startswith("- **") for bullet in bullets), (
        "README: 'What this shows' is three bold-led bullets"
    )
    for found in sentences(sentence) + [part for bullet in bullets for part in sentences(prose_of(bullet))]:
        assert len(found.split()) <= LONGEST, (
            f"README: a first-screen sentence has more than {LONGEST} words: {found!r}"
        )


# --- the files the README describes ------------------------------------------


def test_the_workflow_does_what_the_readme_says() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    uses = set(re.findall(r"^\s*-?\s*uses:\s*(\S+)", workflow, flags=re.M))
    assert uses <= ACTIONS, f"ci.yml uses an action that is not allowed here: {sorted(uses - ACTIONS)}"
    assert {"actions/upload-pages-artifact@v3", "actions/deploy-pages@v4"} <= uses, "ci.yml publishes the page"
    assert "git diff --exit-code results/a11y.json" in workflow, "ci.yml fails on a stale results file"
    assert "playwright install --with-deps chromium" in workflow, "ci.yml runs the suite with Chromium"
    assert "python -m tools.site" in workflow and "site/report" in workflow, "ci.yml builds the page and the report"


def test_the_docker_files_are_what_the_readme_says() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-slim", dockerfile, flags=re.M), "Dockerfile: Python 3.12 slim"
    assert "pip install" in dockerfile and "[dev]" not in dockerfile, "Dockerfile: the package, without the dev extra"
    compose = COMPOSE.read_text(encoding="utf-8")
    assert set(re.findall(r"^  (\w+):$", compose, flags=re.M)) == {"shop", "tests"}, "compose: two services"
    assert "A11Y_MODE: ${A11Y_MODE:-fixed}" in compose, "compose: A11Y_MODE passed through, fixed when unset"
    assert "127.0.0.1:8000:8000" in compose, "compose: the shop on http://127.0.0.1:8000"
    assert "mcr.microsoft.com/playwright/python:" in compose, "compose: the tests on Playwright's Python image"
    assert "[dev]" in compose, "compose: the tests install the dev extra"
    if "dockerfile_inline" in compose:
        assert "Compose 2.17" in TEXT, "README: the tests service's inline Dockerfile takes Compose 2.17 or newer"


# --- the words ---------------------------------------------------------------


@pytest.mark.parametrize("path", [README, CHECKLIST, WORKFLOW], ids=lambda path: path.name)
def test_no_word_this_repository_keeps_out_and_no_claim(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for word in KEPT_OUT:
        assert not re.search(rf"\b{word}\b", text, flags=re.I), (
            f"{path.name} carries {word!r}, which this repository keeps out"
        )
    assert not re.search(r"[Ѐ-ӿ]", text), f"{path.name} is not all in English"
