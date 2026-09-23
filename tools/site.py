"""The published page, rendered from the results file.

    python -m tools.site                   # writes site/index.html for the current commit and today's date
    python -m tools.site --commit 0123abc  # the same, where there is no checkout to ask for the commit

The page carries the README's two tables, a link to the Allure report the
workflow puts next to it under `report/`, and the date and commit of the run
it was built from — both given to `build`, because the file itself carries
no time. The commit is the one given, else the workflow's `GITHUB_SHA`, else
git's `HEAD` here. It is a plain document, held to what the shop is held to:
its own language, one heading level after another, tables with a caption and
header cells, text with contrast above 4.5:1 and a visible focus style; a test
runs the same scan on it as on the shop.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import jinja2

from tools.report import (
    FINDINGS_HEADER,
    REGISTRY_HEADER,
    ROOT,
    findings_rows,
    load,
    registry_rows,
    total_findings,
)

HERE = Path(__file__).resolve().parent

#: Where the page goes; the workflow publishes the directory.
SITE = ROOT / "site" / "index.html"

#: Where the Allure report sits next to the page.
REPORT = "report/"


def build(data: dict, *, commit: str, date: str) -> str:
    """The page's HTML, from the results file's content and the run it came from."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(HERE),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template("site.html").render(
        commit=commit,
        date=date,
        report=REPORT,
        findings={"header": FINDINGS_HEADER, "rows": findings_rows(data)},
        registry={"header": REGISTRY_HEADER, "rows": registry_rows(data)},
        totals={mode: total_findings(data, mode) for mode in ("broken", "fixed")},
    )


def commit_of(given: str | None = None) -> str:
    """The commit the page is built from, shortened: the one given, else the workflow's `GITHUB_SHA`, else what git
    says here. Without any of them (an archive without `.git`, or no git on the machine) a `ValueError` names the
    way out."""
    sha = given or os.environ.get("GITHUB_SHA")
    if sha:
        return sha[:7]
    try:
        found = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise ValueError(
            "not a git checkout (or no git on PATH) and GITHUB_SHA is not set: pass the commit with --commit"
        ) from None
    return found.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.site", description="Build the page from the results file.")
    parser.add_argument("--out", type=Path, default=SITE, help=f"where to write the page (default: {SITE})")
    parser.add_argument("--commit", help="the commit the page is built from (default: GITHUB_SHA, or else git's HEAD)")
    args = parser.parse_args(argv)
    try:
        html = build(load(), commit=commit_of(args.commit), date=date.today().isoformat())
    except (OSError, ValueError) as error:  # no results file, a stale one, or no commit to name
        print(error, file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"{args.out} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
