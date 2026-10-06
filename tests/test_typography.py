import zipfile

from argus.typography import (
    check_docx,
    check_markdown,
    find_bare_formulas,
    find_flat_charges,
    find_flat_subscripts,
    find_unclosed_superscripts,
)


def _make_docx(path, body_xml):
    """Minimal .docx (a zip with one document.xml) for exercising check_docx."""
    doc = (
        '<?xml version="1.0"?><w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body_xml}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", doc)
    return str(path)


def _run(text):
    return (
        '<w:p><w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr>'
        f"<w:t>{text}</w:t></w:r></w:p>"
    )


def _tokens(issues):
    return [(x.line, x.token, x.suggestion) for x in issues]


# --- unclosed superscripts (the shipped bug) ---


def test_unclosed_scientific_notation_and_units():
    text = "C_p = 533 - 9.537 x 10^6 / T^2 and sigma is 0.87 mS cm^-1 here.\n"
    toks = {x.token for x in find_unclosed_superscripts(text)}
    assert "^6" in toks
    assert "^2" in toks
    assert "^-1" in toks


def test_closed_pairs_are_not_flagged():
    # The real fixes: once carets are closed the check must go quiet, including the
    # trailing caret of a pair, which a naive lone-caret scan wrongly flags.
    text = "10^6^ / T^2^, mS cm^-1^, Ta^5+^, Nb^5+^, Li^+^, q^2^.\n"
    assert find_unclosed_superscripts(text) == []


def test_charge_superscripts_only_flag_when_unclosed():
    assert find_unclosed_superscripts("doping with Ta^5+ ions\n")  # unclosed
    assert find_unclosed_superscripts("doping with Ta^5+^ ions\n") == []  # closed


def test_doi_substring_is_not_a_superscript():
    # A caret cannot appear in a DOI, but the protected-span logic must survive one.
    text = "See https://doi.org/10.1039/D4DD00115J for details.\n"
    assert find_unclosed_superscripts(text) == []


def test_line_numbers_are_reported():
    text = "clean line\nbroken 10^6 here\n"
    issues = find_unclosed_superscripts(text)
    assert issues[0].line == 2


# --- flat subscripts (descriptors that should carry one) ---


def test_flat_descriptors_are_flagged_with_fixes():
    text = "dHf = -7152 kJ/mol, Cp at 800 K, D0 calibrated, S298 = 424.\n"
    got = {t: s for _, t, s in _tokens(find_flat_subscripts(text))}
    assert got["dHf"] == "dH~f~"
    assert got["Cp"] == "C~p~"
    assert got["D0"] == "D~0~"
    assert got["S298"] == "S~298~"


def test_already_subscripted_descriptor_is_quiet():
    assert find_flat_subscripts("dH~f~ and C~p~ and D~0~ and S~298~\n") == []


def test_descriptor_guard_avoids_words_and_years():
    # Cp inside a word, and a four-digit year, must not fire.
    assert find_flat_subscripts("the Cpython runtime in 2298 AD\n") == []


def test_d0_inside_doi_is_protected():
    text = "https://doi.org/10.1039/D4DD00115J cites the prefactor D0 elsewhere.\n"
    got = [t for _, t, _ in _tokens(find_flat_subscripts(text))]
    assert got == ["D0"]  # the real D0, not the DOI's DD00 substring


# --- bare ionic charges (no caret at all) ---


def test_flat_charges_flagged_with_caret_fix():
    text = "high Li+ conductivity, with Ca2+ and O2- present.\n"
    got = {t: s for _, t, s in _tokens(find_flat_charges(text))}
    assert got["Li+"] == "Li^+^"
    assert got["Ca2+"] == "Ca^2+^"
    assert got["O2-"] == "O^2-^"


def test_flat_charge_ignores_closed_and_non_elements():
    # Already superscripted, and a non-element "A+" grade / arithmetic, must stay quiet.
    assert find_flat_charges("Li^+^ and Ta^5+^ are fine\n") == []
    assert find_flat_charges("earned an A+ and computed N-1 and x = 3+2\n") == []


# --- bare molecular formulas (heuristic warning) ---


def test_bare_formula_flagged_but_partial_pressure_preserved():
    text = "Atmospheric CO2 rises while log p~CO2~ stays fixed.\n"
    toks = [(t, s) for _, t, s in _tokens(find_bare_formulas(text))]
    assert ("CO2", "CO~2~") in toks
    assert all(t != "p" for t, _ in toks)  # the p~CO2~ unit is untouched


def test_bare_formula_ignores_non_formula_tokens():
    assert find_bare_formulas("Fig3 and COVID and H2020 grant\n") == []


def test_bare_formula_ignores_espei_parameter_codes():
    # VV0001/VV0002 are ESPEI parameter names: two "V" groups then a leading-zero,
    # four-digit run. A stoichiometric subscript is never written that way.
    text = "treating the tetragonal phase (VV0001 and VV0002) as free parameters\n"
    assert find_bare_formulas(text) == []


# --- report status: errors fail, warnings do not ---


def test_report_status_suspect_on_unclosed_caret():
    assert check_markdown("value 10^6 shipped\n").status == "suspect"


def test_report_status_ok_when_only_warnings():
    # A flat Cp is a warning; it should not flip status to suspect on its own.
    report = check_markdown("the Cp value is high\n")
    assert report.status == "ok"
    assert report.warnings


def test_clean_source_passes():
    text = "10^6^ / T^2^ with dH~f~ = -7152 and C~p~ closed.\n"
    report = check_markdown(text)
    assert report.status == "ok"
    assert report.issues == []


# --- rendered docx verification ---


def test_docx_counts_runs_and_passes_when_clean(tmp_path):
    body = (
        '<w:p><w:r><w:t>C</w:t></w:r>'
        '<w:r><w:rPr><w:vertAlign w:val="subscript"/></w:rPr><w:t>p</w:t></w:r></w:p>'
        + _run("6")
    )
    r = check_docx(_make_docx(tmp_path / "clean.docx", body))
    assert r.superscript_runs == 1
    assert r.subscript_runs == 1
    assert r.status == "ok"


def test_docx_flags_leftover_caret(tmp_path):
    # A build that kept an unclosed superscript leaves a literal caret in the text.
    body = "<w:p><w:r><w:t>value is 10^6 J/mol</w:t></w:r></w:p>"
    r = check_docx(_make_docx(tmp_path / "bad.docx", body))
    assert r.status == "suspect"
    assert r.leftover_carets


def test_docx_ignores_caret_free_doi(tmp_path):
    body = "<w:p><w:r><w:t>see doi.org/10.1039/D4DD00115J</w:t></w:r></w:p>"
    r = check_docx(_make_docx(tmp_path / "doi.docx", body))
    assert r.status == "ok"
