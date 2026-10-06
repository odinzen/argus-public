from argus.floats import (
    check_floats,
    find_captions,
    find_float_references,
)


def test_find_captions_in_document_order():
    text = "Figure 1. First.\nFigure 2. Second.\nFigure 3. Third.\n"
    assert find_captions(text, "figure") == [1, 2, 3]


def test_caption_needs_line_start_and_punctuation():
    # A sentence that merely opens with a reference is not a caption.
    text = "As Figure 5 shows, the trend holds.\nFigure 5. The real caption.\n"
    assert find_captions(text, "figure") == [5]


def test_references_exclude_the_caption_itself():
    text = "See Table 1 below.\nTable 1. The caption.\nTable 1 again later.\n"
    assert find_float_references(text, "table") == [1]


def test_reference_runs_expand_ranges_and_lists():
    text = "Compare Figures 1-3 with Figs. 5 and 7.\n"
    assert find_float_references(text, "figure") == [1, 2, 3, 5, 7]


def test_word_boundary_ignores_substring_keywords():
    # "Configuration 5" must not read as a figure reference.
    text = "The operational window of Configuration 5 is wide.\n"
    assert find_float_references(text, "figure") == []


def test_clean_sequence_passes():
    text = (
        "Table 1 and Table 2 and Table 3 are discussed.\n"
        "Table 1. One.\nTable 2. Two.\nTable 3. Three.\n"
    )
    report = check_floats(text, "table")
    assert report.status == "ok"
    assert report.issues() == []
    assert report.uncited == []


def test_gap_in_caption_sequence_flagged():
    # The Table 1, 2, 4 bug: a table was cut and 3 was never reclaimed.
    text = "Table 1. One.\nTable 2. Two.\nTable 4. Four.\n"
    report = check_floats(text, "table")
    assert report.status == "suspect"
    assert report.gaps == [3]


def test_duplicate_caption_number_flagged():
    text = "Figure 1. One.\nFigure 2. Two.\nFigure 2. Also two.\n"
    report = check_floats(text, "figure")
    assert report.status == "suspect"
    assert 2 in report.duplicates


def test_out_of_order_captions_flagged():
    text = "Figure 1. One.\nFigure 3. Three.\nFigure 2. Two.\n"
    report = check_floats(text, "figure")
    assert report.status == "suspect"
    assert report.out_of_order is True


def test_dangling_reference_flagged():
    # Body points at Figure 9; only three figures are captioned.
    text = (
        "See Figure 9 for detail.\n"
        "Figure 1. One.\nFigure 2. Two.\nFigure 3. Three.\n"
    )
    report = check_floats(text, "figure")
    assert report.status == "suspect"
    assert 9 in report.missing_captions


def test_uncited_caption_is_a_warning_not_a_failure():
    # Figures 1 and 2 captioned, only Figure 1 referenced.
    text = "We rely on Figure 1.\nFigure 1. One.\nFigure 2. Two.\n"
    report = check_floats(text, "figure")
    assert report.status == "ok"  # uncited does not fail the gate
    assert report.uncited == [2]
    assert report.warnings()


def test_table_and_figure_kinds_are_independent():
    text = "Table 1. T.\nFigure 1. F.\nFigure 2. F2.\n"
    assert find_captions(text, "table") == [1]
    assert find_captions(text, "figure") == [1, 2]


def test_markdown_bold_and_italic_captions_are_recognized():
    # Pandoc sources write captions bold (**Figure 1.**) or italic (*Fig. 1.*); both must
    # register as captions, not be missed and reported as "referenced but never captioned".
    text = (
        "As shown in Figure 1 and Figure 2.\n"
        "**Figure 1.** First caption.\n"
        "*Fig. 2. Second caption.*\n"
    )
    assert find_captions(text, "figure") == [1, 2]
    report = check_floats(text, "figure")
    assert report.missing_captions == []
    assert report.status == "ok"


def test_possessive_mentions_belong_to_another_paper():
    # "their table 2" / "Fischer's table 3" cite ANOTHER paper's floats; this document
    # never captions them, so they must not be reported as missing captions. A bare
    # "Table 2" in the same text is ours and must still be caught (the planted bad case).
    text = (
        "Table 1. Ours.\n"
        "We use the fit of Fischer et al. (2015, their table 2) and their table 3.\n"
        "The coefficients come from Fischer's table 2 directly.\n"
    )
    report = check_floats(text, "table")
    assert report.missing_captions == []
    assert report.status == "ok"

    planted = text + "The bare Table 2 shows our own results.\n"
    report = check_floats(planted, "table")
    assert report.missing_captions == [2]
    assert report.status == "suspect"
