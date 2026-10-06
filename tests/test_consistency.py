from argus import consistency

# An abstract value that survived a revision only in the abstract.
DESYNCED = """\
# Title

## Abstract
The tetragonal-to-cubic transition occurs at 849 K, a key result.

## Introduction
Here we report the transition. Our joint fit places it at 912.6 ± 20.5 K, revised
upward from earlier estimates.

## References
1. Author, A. Something, 2020, 849.
"""

CONSISTENT = DESYNCED.replace("849 K, a key result", "912 K, a key result")


def test_desynced_abstract_value_flagged():
    r = consistency.check_consistency(DESYNCED)
    assert r.status == "suspect"
    assert any(m.value == 849 for m in r.mismatches)


def test_consistent_abstract_passes():
    r = consistency.check_consistency(CONSISTENT)
    assert r.status == "ok"


def test_reference_years_not_counted_as_body_match():
    # 849 appears in the reference list only; the reference section is excluded, so the
    # abstract's 849 is still not found in the body.
    r = consistency.check_consistency(DESYNCED)
    assert any(m.value == 849 for m in r.mismatches)


def test_small_integers_not_tracked():
    text = (
        "## Abstract\nWe study 3 phases and 2 sublattices.\n\n"
        "## Introduction\nThe system has many phases.\n"
    )
    r = consistency.check_consistency(text)
    assert r.abstract_quantities == []  # 3 and 2 are not distinctive


def test_uncertainty_value_tracked_and_matched():
    text = (
        "## Abstract\nThe rate is 88.3 ± 1.2 J/mol here.\n\n"
        "## Introduction\nWe compute 88.3 J/mol for the rate.\n"
    )
    r = consistency.check_consistency(text)
    assert "88.3" in " ".join(r.abstract_quantities)
    assert r.status == "ok"


def test_tolerance_matches_rounded_body_value():
    text = (
        "## Abstract\nThe eutectic is at 912 K.\n\n"
        "## Introduction\nRefined to 912.6 K in this work.\n"
    )
    r = consistency.check_consistency(text)
    assert r.status == "ok"  # 912 within tolerance of 912.6


def test_no_introduction_means_not_checked():
    r = consistency.check_consistency("Just some text with 505 K and no headings.\n")
    assert r.checked is False
    assert r.status == "ok"
