from argus import xref

NUMBERED = """\
## 1 Introduction
We set the scene and point to Section 3.2 for the model.

## 2 Methods
See Section 4 for the results.

## 3 Model
### 3.2 Cubic model
Details here.

## 4 Results
Everything resolves.
"""


def test_resolving_sections_pass():
    r = xref.check_crossrefs(NUMBERED, NUMBERED)
    assert r.headings_numbered
    assert r.status == "ok"
    assert r.dangling_sections == []


def test_dangling_section_flagged():
    text = NUMBERED + "\nAs discussed in Section 9.9, this is wrong.\n"
    r = xref.check_crossrefs(text, text)
    assert "9.9" in r.dangling_sections
    assert r.status == "suspect"


def test_sections_and_list_form():
    text = "## 3 A\n## 4 B\nSee Sections 3 and 4 for detail.\n"
    r = xref.check_crossrefs(text, text)
    assert set(r.section_refs) == {"3", "4"}
    assert r.status == "ok"


def test_unnumbered_headings_not_resolved():
    text = "## Introduction\nSee Section 4 for the model.\n## Methods\nText.\n"
    r = xref.check_crossrefs(text, text)
    assert r.headings_numbered is False
    assert r.dangling_sections == []  # cannot resolve, so nothing is failed
    assert r.status == "ok"


def test_si_floats_inventoried_not_failed():
    text = "## 1 Intro\nAs in Table S3 and Fig. S1, the trend holds.\n"
    r = xref.check_crossrefs(text, text)
    assert r.si_floats == ["Fig S1", "Table S3"]
    assert r.status == "ok"  # SI floats are a note, not a failure


def test_no_references_is_clean():
    text = "## 1 Intro\nA plain paragraph with nothing to resolve.\n"
    r = xref.check_crossrefs(text, text)
    assert r.section_refs == [] and r.si_floats == []
    assert r.status == "ok"


def test_possessive_section_refs_belong_to_another_paper():
    # "their section 4.2.3" points into a cited paper, not this document's headings; it
    # must not dangle. A bare "Section 9.9" must still dangle (the planted bad case).
    text = "## 1 Intro\nUnstable per Fischer et al. (2015, their section 4.2.3).\n"
    r = xref.check_crossrefs(text, text)
    assert r.dangling_sections == []
    assert r.status == "ok"

    planted = text + "See Section 9.9 for details.\n"
    r = xref.check_crossrefs(planted, planted)
    assert "9.9" in r.dangling_sections
    assert r.status == "suspect"
