"""The vendored axe-core is the version the scan is said to use, byte for byte.

The README next to the file names the version and the checksum; the file on
disk must match both, and the licence next to it must be the one its banner
names. The file is the one `a11y.axe` reads, wherever the package sits, so an
installed package is checked the same way as a checkout.
"""
from __future__ import annotations

import hashlib
import re

from a11y.axe import AXE

VENDOR = AXE.parent

#: The one version the scan runs. Moving to another means a new file, a new checksum in the README, and this.
VERSION = "4.13.0"


def banner_of(script: str) -> str:
    """The comment a minified library opens with (its name, version and licence), as one line of words."""
    match = re.match(r"/\*!(.*?)\*/", script, flags=re.S)
    assert match, "axe.min.js does not open with a /*! … */ banner"
    lines = (line.strip().lstrip("*").strip() for line in match.group(1).splitlines())
    return " ".join(line for line in lines if line)


def test_axe_min_js_matches_the_checksum_in_the_readme() -> None:
    readme = (VENDOR / "README.md").read_text(encoding="utf-8")
    [pinned] = re.findall(r"\b[0-9a-f]{64}\b", readme)  # exactly one checksum is written there
    assert hashlib.sha256(AXE.read_bytes()).hexdigest() == pinned


def test_the_banner_and_the_readme_name_the_pinned_version() -> None:
    banner = banner_of(AXE.read_text(encoding="utf-8"))
    assert f"axe v{VERSION}" in banner
    assert f"axe-core {VERSION}" in (VENDOR / "README.md").read_text(encoding="utf-8")


def test_the_licence_is_the_one_the_banner_names() -> None:
    banner = banner_of(AXE.read_text(encoding="utf-8"))
    assert "Mozilla Public License" in banner and "v. 2.0" in banner
    licence = (VENDOR / "axe-core-LICENSE.txt").read_text(encoding="utf-8")
    assert licence.startswith("Mozilla Public License, version 2.0")
