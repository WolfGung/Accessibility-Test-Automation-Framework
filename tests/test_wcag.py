"""How axe's rule tags are read as WCAG success criteria."""
from __future__ import annotations

import pytest

from a11y.wcag import criteria_from_tags


@pytest.mark.parametrize(
    ("tag", "criterion"),
    [
        ("wcag111", "1.1.1"),
        ("wcag143", "1.4.3"),
        ("wcag2411", "2.4.11"),
        ("wcag412", "4.1.2"),
        ("wcag1412", "1.4.12"),
    ],
)
def test_a_criterion_tag_is_read_as_principle_guideline_and_number(tag: str, criterion: str) -> None:
    assert criteria_from_tags([tag]) == (criterion,)


@pytest.mark.parametrize("tag", ["wcag2a", "wcag2aa", "wcag2aaa", "wcag21a", "wcag21aa", "wcag22aa"])
def test_a_level_tag_names_no_criterion(tag: str) -> None:
    assert criteria_from_tags([tag]) == ()


@pytest.mark.parametrize(
    "tag",
    ["cat.forms", "best-practice", "experimental", "ACT", "section508", "section508.22.a", "TTv5", "TT7.a"]
    + ["EN-301-549", "EN-9.1.1.1", "wcag2a-obsolete", "wcag"],
)
def test_a_tag_that_is_not_a_criterion_is_passed_over(tag: str) -> None:
    assert criteria_from_tags([tag]) == ()


def test_the_criteria_of_a_rule_come_out_in_the_tags_order_and_nothing_else() -> None:
    # The tags of axe's `label` rule, as a rule carries them: category, level, criteria and other standards mixed.
    tags = ["cat.forms", "wcag2a", "wcag412", "wcag131", "section508", "section508.22.n", "TTv5", "EN-9.4.1.2", "ACT"]
    assert criteria_from_tags(tags) == ("4.1.2", "1.3.1")


def test_no_tags_give_no_criteria() -> None:
    assert criteria_from_tags([]) == ()
