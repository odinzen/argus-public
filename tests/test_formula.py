import zipfile

from argus.typography import check_docx, find_degree_glyph


def _make_docx(path, body_xml, extra_ns=""):
    doc = (
        '<?xml version="1.0"?><w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
        f"{extra_ns}><w:body>{body_xml}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", doc)
    return str(path)


def _para(text):
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


# --- degree glyph ---


def test_letter_o_degree_flagged():
    issues = find_degree_glyph("It melts at 232 oC in air.\n")
    assert [x.kind for x in issues] == ["degree-glyph"]
    assert issues[0].suggestion == "°C"


def test_masculine_ordinal_degree_flagged():
    assert find_degree_glyph("Sintered at 900 ºC.\n")  # U+00BA before C


def test_correct_degree_not_flagged():
    assert find_degree_glyph("It melts at 232 °C in air.\n") == []


def test_degc_word_not_flagged():
    assert find_degree_glyph("It melts at 232 degC in air.\n") == []


def test_oclock_not_flagged():
    # "oC" only fires immediately before a word-boundary C; "oClock" is safe.
    assert find_degree_glyph("by 5 oClock the run finished\n") == []


# --- equation objects in a .docx ---


def test_referenced_equations_without_math_objects_flagged(tmp_path):
    body = _para("As shown in Eq. (3), the driving force is defined there.")
    path = _make_docx(tmp_path / "noeq.docx", body)
    r = check_docx(path)
    assert r.equation_references >= 1
    assert r.math_objects == 0
    assert r.equations_may_be_images


def test_equations_present_as_objects_not_flagged(tmp_path):
    body = _para("As shown in Eq. (3), see below.") + "<m:oMath><m:r><m:t>x=1</m:t></m:r></m:oMath>"
    path = _make_docx(tmp_path / "eq.docx", body)
    r = check_docx(path)
    assert r.math_objects == 1
    assert not r.equations_may_be_images


def test_no_equation_references_no_flag(tmp_path):
    body = _para("A plain paragraph with no equations at all.")
    path = _make_docx(tmp_path / "plain.docx", body)
    r = check_docx(path)
    assert not r.equations_may_be_images
