"""Superscript (ACS-style) citation rendering for the ordering pipeline.

The tricky part is telling a citation superscript from a math superscript, so the planted
cases cover both: real citations must become [n], math must not.
"""

from argus.anchors import find_numeric_anchors
from argus.docx import _bracket_superscript_runs, _bracket_unicode_superscripts


def _run(text, va=None):
    rpr = f'<w:rPr><w:vertAlign w:val="{va}"/></w:rPr>' if va else ""
    return f"<w:r>{rpr}<w:t>{text}</w:t></w:r>"


def _plain(text):
    return _bracket_superscript_runs(_run(text) + _run("3", "superscript"))


def test_superscript_citation_becomes_bracket():
    # "...spacing" then a superscript 3 -> a citation.
    xml = _run("spacing,") + _run("3", "superscript")
    assert "[3]" in _bracket_superscript_runs(xml)


def test_superscript_list_kept_together():
    xml = _run("Vonnegut") + _run("14,15", "superscript")
    assert "[14,15]" in _bracket_superscript_runs(xml)


def test_greek_base_is_not_a_citation():
    # gamma^3 (an exponent), not citation 3.
    xml = _run("γ") + _run("3", "superscript")
    assert "[3]" not in _bracket_superscript_runs(xml)


def test_subscript_base_is_not_a_citation():
    # dG_v^2: the 2 follows a subscript, so it is an exponent.
    xml = _run("G") + _run("v", "subscript") + _run("2", "superscript")
    assert "[2]" not in _bracket_superscript_runs(xml)


def test_function_base_is_not_a_citation():
    # cos^3, not citation 3.
    xml = _run("cos") + _run("3", "superscript")
    assert "[3]" not in _bracket_superscript_runs(xml)


def test_negative_exponent_is_not_a_citation():
    # mol^-1 has a leading sign, so it never matches a citation number.
    xml = _run("mol") + _run("−1", "superscript")
    out = _bracket_superscript_runs(xml)
    assert "[" not in out


def test_unicode_superscript_citation():
    assert _bracket_unicode_superscripts("the Einstein relation¹²") == "the Einstein relation[12]"


def test_unicode_superscript_negative_exponent_kept():
    # mol⁻¹ : the ¹ follows a superscript minus, so it is an exponent.
    assert _bracket_unicode_superscripts("395 kJ mol⁻¹") == "395 kJ mol⁻¹"


def test_rendered_citations_are_found_by_the_anchor_reader():
    import re

    xml = (
        _run("Telkes")
        + _run("1", "superscript")
        + _run(" and Bramfitt")
        + _run("2", "superscript")
    )
    flat = _bracket_unicode_superscripts(_bracket_superscript_runs(xml))
    flat = re.sub(r"<[^>]+>", "", flat)  # strip tags the way docx.text does
    assert [a.numbers for a in find_numeric_anchors(flat)] == [[1], [2]]


def _para(*runs):
    return "<w:p>" + "".join(runs) + "</w:p>"


def _cell(*runs):
    return "<w:tc>" + _para(*runs) + "</w:tc>"


def test_citation_alone_in_cell_after_cell_ending_in_digit():
    # Regression: a compilation row whose technique cell ends "MHTC-96" and whose reference
    # cell holds only a superscript 12. The digit belongs to the previous cell, so it is not
    # a math base and the 12 is a citation.
    xml = _cell(_run("drop, MHTC-96")) + _cell(_run("12", "superscript"))
    assert "[12]" in _bracket_superscript_runs(xml)


def test_citation_after_paragraph_ending_in_digit():
    xml = _para(_run("measured at 1273")) + _para(_run("See the review"), _run("7", "superscript"))
    assert "[7]" in _bracket_superscript_runs(xml)


def test_exponent_within_a_paragraph_still_rejected():
    # 10^6 inside one paragraph stays an exponent after the per-paragraph reset.
    xml = _para(_run("about 10"), _run("6", "superscript"), _run(" drops"))
    assert "[6]" not in _bracket_superscript_runs(xml)
