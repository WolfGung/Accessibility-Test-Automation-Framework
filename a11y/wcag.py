"""WCAG success criteria as axe writes them.

axe tags each rule with the criteria it checks, without the dots: `wcag111`
is 1.1.1, `wcag2411` is 2.4.11. Its other tags name no criterion: a level
(`wcag2a`, `wcag21aa`), a category (`cat.forms`), another standard
(`section508`, `EN-9.1.1.1`) or a kind of rule (`best-practice`).
"""
from __future__ import annotations

import re

# A principle, a guideline and a criterion number. Every guideline of WCAG 2.x is
# one digit (1.1 to 4.1), so the digits after the second belong to the criterion.
_CRITERION = re.compile(r"wcag(\d)(\d)(\d+)")


def criteria_from_tags(tags: list[str]) -> tuple[str, ...]:
    """The success criteria among these tags, in the tags' order: `["wcag2a", "wcag143"]` → `("1.4.3",)`."""
    found = (_CRITERION.fullmatch(tag) for tag in tags)
    return tuple(".".join(match.groups()) for match in found if match)
