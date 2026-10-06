from argus.anchors import find_numeric_anchors
from argus.audit import main_text_start
from argus.ordering import check
from argus.renumbering import renumber_markdown

# An abstract that cites [1] and [2] in order, but whose main text first mentions the
# works in the opposite order. The old numbering looks fine only because the abstract
# masks it; counting from the Introduction, [2] should be [1].
MASKED = """\
# Title

## Abstract

We rely on method A [1] and dataset B [2].

## 1. Introduction

The dataset B [2] came first here, then method A [1] was applied [3].

## References

[1] Author A. Method A. J 2020;1:1.
[2] Author B. Dataset B. J 2019;2:2.
[3] Author C. Tool C. J 2021;3:3.
"""


def test_main_text_start_finds_introduction():
    assert main_text_start(MASKED) > 0
    assert MASKED[main_text_start(MASKED) :].startswith("## 1. Introduction")


def test_main_text_start_zero_without_introduction():
    assert main_text_start("just some text with [1] and no headings") == 0


def test_abstract_does_not_drive_numbering():
    # Counting from the Introduction: B [2]->1, A [1]->2, C [3]->3.
    r = renumber_markdown(MASKED)
    assert r.remap == {2: 1, 1: 2, 3: 3}
    assert r.changed


def test_abstract_markers_are_remapped_too():
    r = renumber_markdown(MASKED)
    # The abstract cited "A [1] and dataset B [2]"; after renumber A is 2, B is 1.
    assert "method A [2] and dataset B [1]" in r.text


def test_reference_list_reordered_and_relabelled():
    r = renumber_markdown(MASKED)
    lines = [ln for ln in r.text.splitlines() if ln.startswith("[")]
    assert lines[0].startswith("[1] Author B")  # B is first in the main text
    assert lines[1].startswith("[2] Author A")
    assert lines[2].startswith("[3] Author C")


def test_reference_text_is_preserved():
    r = renumber_markdown(MASKED)
    assert "Dataset B. J 2019;2:2." in r.text
    assert "Method A. J 2020;1:1." in r.text


def test_renumbered_output_is_in_order_per_ordering_check():
    # The whole point: after renumbering, argus order must read clean.
    r = renumber_markdown(MASKED)
    body_start = main_text_start(r.text)
    body = r.text[body_start : r.text.find("## References")]
    anchors = find_numeric_anchors(body)
    listed = [1, 2, 3]
    assert check(anchors, listed).status == "ok"


def test_already_ordered_manuscript_is_unchanged():
    clean = """\
## 1. Introduction

First [1], then [2], then [3].

## References

[1] A. one. J 2020;1:1.
[2] B. two. J 2020;2:2.
[3] C. three. J 2020;3:3.
"""
    r = renumber_markdown(clean)
    assert not r.changed
    assert r.remap == {1: 1, 2: 2, 3: 3}


def test_grouped_and_range_citations_remap_and_recollapse():
    text = """\
## 1. Introduction

Start [6-9], then [1] and [2,3].

## References

[1] A. a. J 2020;1:1.
[2] B. b. J 2020;2:2.
[3] C. c. J 2020;3:3.
[6] F. f. J 2020;6:6.
[7] G. g. J 2020;7:7.
[8] H. h. J 2020;8:8.
[9] I. i. J 2020;9:9.
"""
    r = renumber_markdown(text)
    # 6,7,8,9 -> 1,2,3,4 ; then 1->5, 2->6, 3->7
    assert "[1-4]" in r.text
    assert "[5] and [6,7]" in r.text


def test_abstract_only_citation_is_flagged():
    text = """\
## Abstract

An aside cites [9] which never returns.

## 1. Introduction

Body cites [1] and [2].

## References

[1] A. a. J 2020;1:1.
[2] B. b. J 2020;2:2.
[9] Z. z. J 2020;9:9.
"""
    r = renumber_markdown(text)
    assert any("only before the Introduction" in w for w in r.warnings)
