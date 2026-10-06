from argus import units


def test_clean_single_temperature_unit():
    r = units.check_units("The eutectic is 232 degC and the liquidus is 400 degC.\n")
    assert r.status == "ok"
    assert r.degc == 2 and r.kelvin == 0


def test_mixed_temperature_without_journal_warns():
    r = units.check_units("The value is 232 degC, i.e. 505 K, here.\n")
    assert r.status == "ok"  # advisory without a journal
    assert any(f.kind == "temperature" and f.severity == "warning" for f in r.findings)


def test_kelvin_in_degc_journal_is_an_error():
    r = units.check_units("The eutectic is 232 degC. A rate at 505 K appears.\n", journal="JECS")
    assert r.status == "suspect"
    assert any(f.severity == "error" for f in r.findings)


def test_degc_in_kelvin_journal_is_an_error():
    # JPED is pinned to K (CALPHAD convention).
    r = units.check_units("Gibbs energies to 1200 K, but one value at 232 degC.\n", journal="JPED")
    assert r.status == "suspect"


def test_degc_glyph_variants_both_count():
    r = units.check_units("It melts at 156 °C, close to 157 degC.\n")
    assert r.degc == 2


def test_at_and_mol_percent_both_used_warns():
    r = units.check_units("We used 5 at% Ta and later 5 mol% Al in the same study.\n")
    assert any("same quantity" in f.message for f in r.findings)


def test_wt_and_at_percent_warns_conversion():
    r = units.check_units("Reported as 2 wt% and also 3 at% in the tables.\n")
    assert any("conversion" in f.message for f in r.findings)


def test_kelvin_not_matched_in_kg_or_formula():
    r = units.check_units("A 5 Kg sample of K2O was used.\n")
    assert r.kelvin == 0


def test_composition_single_unit_clean():
    r = units.check_units("All compositions are in at%: 5 at% Ta, 10 at% Al.\n")
    assert r.status == "ok"
    assert r.composition == {"at%": 3}


def test_references_section_excluded():
    text = "Melts at 900 degC.\n\n## References\n1. Author. Something at 1200 K. Journal, 2020.\n"
    r = units.check_units(text, journal="JECS")
    # The kelvin sits in the reference list; excluded, so no error for a degC journal.
    assert r.status == "ok"
