from argus.formatting import (
    check_formatting,
    extract_paragraphs,
)

BODY_TEXT = (
    "This is a full paragraph of running body prose that comfortably clears the length "
    "threshold the check uses to tell a real body paragraph apart from a heading or a "
    "caption or a short byline line, so it joins the body formatting vote as one sample."
)


def _para(text, *, sz="22", after="120", line="300", jc="both"):
    """A <w:p> block with the given direct formatting (sz in half-points)."""
    spacing = f'<w:spacing w:after="{after}" w:line="{line}" w:lineRule="auto"/>' if line else (
        f'<w:spacing w:after="{after}"/>' if after else ""
    )
    jc_xml = f'<w:jc w:val="{jc}"/>' if jc else ""
    sz_xml = f'<w:sz w:val="{sz}"/>' if sz else ""
    return (
        f"<w:p><w:pPr>{spacing}{jc_xml}</w:pPr>"
        f"<w:r><w:rPr>{sz_xml}</w:rPr><w:t>{text}</w:t></w:r></w:p>"
    )


def _doc(*paras):
    return "<w:document><w:body>" + "".join(paras) + "</w:body></w:document>"


def test_uniform_body_passes():
    xml = _doc(_para(BODY_TEXT + " one"), _para(BODY_TEXT + " two"), _para(BODY_TEXT + " three"))
    report = check_formatting(xml)
    assert report.status == "ok"
    assert report.prose_count == 3
    assert not report.groups


def test_single_spaced_insert_is_flagged():
    # Two 1.5-spaced body paragraphs plus one that lost its line spacing (the real bug).
    xml = _doc(
        _para(BODY_TEXT + " one"),
        _para(BODY_TEXT + " two"),
        _para(BODY_TEXT + " pasted", line=None),  # single spacing, no line rule
    )
    report = check_formatting(xml)
    assert report.status == "suspect"
    assert len(report.groups) == 1 and report.groups[0].count == 1
    assert report.groups[0].drift  # missing the body's line spacing
    assert "single spacing" in " ".join(report.groups[0].differences)


def test_wrong_size_and_alignment_flagged():
    xml = _doc(
        _para(BODY_TEXT + " one"),
        _para(BODY_TEXT + " two"),
        _para(BODY_TEXT + " odd", sz="20", jc="left"),  # 10pt, left, vs 11pt justify
    )
    report = check_formatting(xml)
    assert report.status == "suspect"
    diffs = " ".join(report.groups[0].differences)
    assert "10pt" in diffs and "left" in diffs


def test_reference_list_is_excluded():
    # Bibliography entries have their own (smaller, single-spaced) format and must not be
    # compared against the body; the check stops at the References heading.
    ref = _para("(1) Author, A. A Title. Journal Year, Vol, pages. A long enough entry line.",
                sz="20", line=None, jc="left")
    xml = _doc(
        _para(BODY_TEXT + " one"),
        _para(BODY_TEXT + " two"),
        _para(BODY_TEXT + " three"),
        "<w:p><w:r><w:t>References</w:t></w:r></w:p>",
        ref, ref, ref,
    )
    report = check_formatting(xml)
    assert report.prose_count == 3  # references excluded
    assert report.status == "ok"


def test_deliberate_secondary_style_is_a_note_not_a_failure():
    # Back matter explicitly set to 10pt (size present, spacing kept) is a deliberate
    # style, reported as a note and NOT failing the check.
    xml = _doc(
        _para(BODY_TEXT + " a"), _para(BODY_TEXT + " b"), _para(BODY_TEXT + " c"),
        _para(BODY_TEXT + " d"), _para(BODY_TEXT + " e"),
        _para(BODY_TEXT + " back1", sz="20"),
        _para(BODY_TEXT + " back2", sz="20"),
    )
    report = check_formatting(xml)
    assert report.status == "ok"  # explicit different size is not drift
    assert report.style_groups and not report.drift_groups
    assert report.style_groups[0].count == 2


def test_lost_formatting_beats_deliberate_style():
    # A paragraph that dropped its spacing entirely (drift) fails even when a deliberate
    # secondary style (a coherent 10pt back-matter block) is also present.
    xml = _doc(
        _para(BODY_TEXT + " a"), _para(BODY_TEXT + " b"), _para(BODY_TEXT + " c"),
        _para(BODY_TEXT + " back1", sz="20"),         # deliberate 10pt block -> note
        _para(BODY_TEXT + " back2", sz="20"),
        _para(BODY_TEXT + " lost", after=None, line=None, jc=None),  # drift -> suspect
    )
    report = check_formatting(xml)
    assert report.status == "suspect"
    assert len(report.drift_groups) == 1 and report.drift_groups[0].drift
    assert len(report.style_groups) == 1 and report.style_groups[0].count == 2


def test_lone_different_paragraph_fails_even_if_explicitly_set():
    # One paragraph set to a different size on its own (not a coherent block) is suspect.
    xml = _doc(
        _para(BODY_TEXT + " a"), _para(BODY_TEXT + " b"), _para(BODY_TEXT + " c"),
        _para(BODY_TEXT + " lone", sz="20"),
    )
    report = check_formatting(xml)
    assert report.status == "suspect"
    assert len(report.drift_groups) == 1 and not report.style_groups


def test_headings_and_captions_are_not_in_the_body_vote():
    # A short heading and a caption must not be compared against the body signature.
    heading = (
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>2. Methods</w:t></w:r></w:p>"
    )
    caption = _para(
        "Figure 1. A caption that happens to be long enough to pass the length gate here."
    )
    xml = _doc(_para(BODY_TEXT + " one"), _para(BODY_TEXT + " two"), heading, caption)
    report = check_formatting(xml)
    assert report.prose_count == 2  # only the two body paragraphs
    assert report.status == "ok"


def test_extract_reads_alignment_and_size():
    xml = _doc(_para(BODY_TEXT))
    p = extract_paragraphs(xml)[0]
    assert p.signature.align == "justify"
    assert p.signature.size_halfpt == "22"


def test_too_few_paragraphs_is_inconclusive():
    xml = _doc(_para(BODY_TEXT))
    report = check_formatting(xml)
    assert report.majority is None
    assert report.groups == []
