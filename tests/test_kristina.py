import zipfile

from argus import cli, kristina


def _kinds(report):
    return {x.kind for x in report.issues}


def test_em_dash_is_an_error():
    r = kristina.check_kristina("The result — a good one — held.\n")
    assert r.status == "suspect"
    assert "em-dash" in _kinds(r)


def test_pandoc_double_hyphen_dash_flagged():
    r = kristina.check_kristina("The value was high -- higher than expected.\n")
    assert "em-dash" in _kinds(r)


def test_citation_range_en_dash_not_flagged():
    # Elsevier numeric styles collapse consecutive citations with an en dash.
    r = kristina.check_kristina("Competing phases [13–15], at a cost [2, 5–7].\n")
    assert "em-dash" not in _kinds(r)


def test_prose_dash_beside_citation_range_still_flagged():
    r = kristina.check_kristina("Phases [13–15] – the stable ones – held.\n")
    assert sum(x.kind == "em-dash" for x in r.issues) == 2


def test_em_dash_inside_brackets_still_flagged():
    r = kristina.check_kristina("Competing phases [13—15] held.\n")
    assert "em-dash" in _kinds(r)


def test_superscript_citation_range_in_docx_not_flagged(tmp_path, capsys):
    run = '<w:r><w:t xml:space="preserve">{}</w:t></w:r>'
    sup = '<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>13–15</w:t></w:r>'
    body = "<w:p>" + run.format("Competing phases") + sup + run.format(", at a cost.") + "</w:p>"
    doc = (
        '<?xml version="1.0"?><w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    path = tmp_path / "paper.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", doc)
    assert cli.main(["kristina", str(path)]) == 0
    assert "em-dash" not in capsys.readouterr().out


def test_et_al_expansion_is_an_error():
    r = kristina.check_kristina("Following Murugan and co-workers, we adopt the value.\n")
    assert r.status == "suspect"
    assert "et-al-expanded" in _kinds(r)


def test_in_preparation_citation_is_an_error():
    r = kristina.check_kristina("A companion study (in preparation) extends this.\n")
    assert "in-preparation" in _kinds(r)


def test_banned_phrase_is_a_warning():
    r = kristina.check_kristina("The fit is very consistent with the data.\n")
    assert r.status == "ok"  # warnings do not gate
    assert "banned-phrase" in _kinds(r)
    hit = next(x for x in r.issues if x.kind == "banned-phrase")
    assert hit.suggestion == "in good agreement with"


def test_british_spelling_flagged_by_default():
    r = kristina.check_kristina("We ran the optimisation and digitising steps.\n")
    kinds = _kinds(r)
    assert any(k.startswith("spelling") for k in kinds)
    hit = next(x for x in r.issues if x.kind.startswith("spelling"))
    assert hit.suggestion.startswith("optimization")


def test_american_spelling_flagged_for_british_journal():
    r = kristina.check_kristina("We ran the optimization step.\n", journal_variant="British")
    hit = next((x for x in r.issues if x.kind.startswith("spelling")), None)
    assert hit is not None
    assert hit.suggestion.startswith("optimisation")


def test_sentence_initial_but():
    r = kristina.check_kristina("The value is low. But it agrees with theory.\n")
    assert "sentence-initial" in _kinds(r)


def test_unit_mixing_in_one_line():
    r = kristina.check_kristina("The eutectic is 232 degC, i.e. 505 K, in this system.\n")
    assert "unit-mix" in _kinds(r)


def test_long_sentence_flagged():
    long = "word " * 45 + "end.\n"
    r = kristina.check_kristina(long)
    assert "long-sentence" in _kinds(r)


def test_references_section_excluded():
    text = (
        "The present work reports the value.\n\n"
        "## References\n"
        "1. Author, A. Optimisation of things. Journal, 2020.\n"
    )
    r = kristina.check_kristina(text)
    # The British spelling sits in the reference list, which is Zotero-managed and excluded.
    assert not any(k.startswith("spelling") for k in _kinds(r))


def test_clean_prose_passes():
    text = "The present work calculates the enthalpy. It is in good agreement with theory.\n"
    r = kristina.check_kristina(text)
    assert r.status == "ok"
    assert r.issues == []
