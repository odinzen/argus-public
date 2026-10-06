from argus.anchors import Anchor, find_numeric_anchors
from argus.ordering import check, first_appearance, numbered_entries, renumber


def _anchors(*pairs):
    return [Anchor(pos, nums) for pos, nums in pairs]


def test_find_numeric_anchors_expands_ranges_and_lists():
    found = find_numeric_anchors("text [1] more [3, 5] and [4-6] end")
    assert [a.numbers for a in found] == [[1], [3, 5], [4, 5, 6]]
    assert [a.position for a in found] == sorted(a.position for a in found)


def test_first_appearance_is_distinct_and_ordered():
    anchors = _anchors((50, [2]), (10, [1]), (90, [2, 3]))
    assert first_appearance(anchors) == [1, 2, 3]


def test_clean_document_passes():
    anchors = _anchors((1, [1]), (2, [2]), (3, [3]))
    report = check(anchors, [1, 2, 3])
    assert report.status == "ok"
    assert report.issues() == []


def test_truncated_list_flags_missing_entry():
    # Body cites [22]; the list stops at [18] -- the Fe-Al Paper A bug.
    anchors = _anchors((1, [1]), (2, [18]), (3, [22]))
    report = check(anchors, list(range(1, 19)))
    assert report.status == "suspect"
    assert 22 in report.missing_entries


def test_orphan_entry_flagged():
    # [8] is in the list but never cited -- the Fe-Al Paper B bug.
    anchors = _anchors((1, [1]), (2, [2]))
    report = check(anchors, [1, 2, 8])
    assert 8 in report.orphans
    assert report.status == "suspect"


def test_out_of_order_list_flagged_and_remapped():
    # Body cites 2 before 1; a citation-order list should renumber them.
    anchors = _anchors((10, [2]), (20, [1]))
    report = check(anchors, [1, 2])
    assert report.out_of_order is True
    assert report.remap == {2: 1, 1: 2}


def test_gaps_and_duplicates_flagged():
    anchors = _anchors((1, [1]), (2, [2]), (3, [4]))
    report = check(anchors, [1, 2, 2, 4])
    assert 3 in report.gaps
    assert 2 in report.duplicates


def test_renumber_from_first_appearance():
    anchors = _anchors((30, [3]), (10, [7]), (20, [3]))
    assert renumber(anchors) == {7: 1, 3: 2}


def test_numbered_entries_reads_leading_numbers():
    section = "[1] First ref.\n[2] Second ref.\n3. Third ref.\n"
    assert numbered_entries(section) == [1, 2, 3]
