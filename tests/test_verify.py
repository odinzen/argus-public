from argus.verify import CrossrefRecord, Reference, author_list_diff, verify


def test_catches_coauthor_conflation():
    # Right first author, title, and year; wrong co-authors. The classic distortion
    # a DOI-resolves or first-author check waves through.
    ref = Reference(
        "navrotsky2010",
        "Nanophase transition metal oxides",
        ["A. Navrotsky", "L. Mazeina", "J. Majzlan"],
        2010,
        "10.0/x",
    )
    record = CrossrefRecord(
        "Nanophase transition metal oxides",
        ["Navrotsky", "Ma", "Doe", "Birkner"],
        2010,
    )
    finding = verify(ref, record)
    assert finding.status == "suspect"
    assert any("mazeina" in i.lower() for i in finding.issues)


def test_correct_reference_passes():
    ref = Reference(
        "ok",
        "Nanophase transition metal oxides",
        ["A. Navrotsky", "C. Ma", "J. Doe", "B. Birkner"],
        2010,
        "10.0/x",
    )
    record = CrossrefRecord(
        "Nanophase transition metal oxides",
        ["Navrotsky", "Ma", "Doe", "Birkner"],
        2010,
    )
    assert verify(ref, record).status == "ok"


def test_flags_dropped_coauthor():
    issues = author_list_diff(["S. Shumway"], ["Shumway", "Wilson"])
    assert any("missing" in i for i in issues)


def test_initials_do_not_false_positive():
    assert author_list_diff(["F. K. Shumway"], ["Shumway"]) == []


def test_title_mismatch_flagged():
    ref = Reference("t", "A totally different title", ["Doe"], 2020, "10.0/z")
    record = CrossrefRecord("The real published title", ["Doe"], 2020)
    assert verify(ref, record).status == "suspect"


def test_catches_wrong_initials_on_right_surname():
    # The Shumway incident: right surname, wrong initials. Surname-only matching
    # waved this through; the initial diff catches it.
    issues = author_list_diff(["F. K. Shumway"], ["S. G. Shumway"])
    assert any("initials differ" in i for i in issues)


def test_matching_initials_pass():
    assert author_list_diff(["S. Shumway"], ["S. G. Shumway"]) == []


def test_flags_wrong_volume():
    ref = Reference("v", "A title", ["Doe"], 2020, "10.0/v", volume="12")
    record = CrossrefRecord("A title", ["Doe"], 2020, volume="21")
    finding = verify(ref, record)
    assert finding.status == "suspect"
    assert any("volume differs" in i for i in finding.issues)


def test_flags_wrong_first_page():
    ref = Reference("p", "A title", ["Doe"], 2020, "10.0/p", first_page="1024")
    record = CrossrefRecord("A title", ["Doe"], 2020, first_page="204")
    finding = verify(ref, record)
    assert finding.status == "suspect"
    assert any("first page differs" in i for i in finding.issues)


def test_volume_and_page_range_pass():
    ref = Reference("ok", "A title", ["Doe"], 2020, "10.0/ok", volume="13", first_page="1024")
    record = CrossrefRecord("A title", ["Doe"], 2020, volume="13", first_page="1024-1027")
    assert verify(ref, record).status == "ok"


def test_flags_dropped_tail_author_in_full_list():
    # A citation that lists almost the whole roster but quietly drops the last name.
    cited = ["Aa", "Bb", "Cc"]
    record = ["Aa", "Bb", "Cc", "Dd"]
    issues = author_list_diff(cited, record)
    assert any("missing" in i and "dd" in i.lower() for i in issues)


def test_et_al_citation_not_flagged_for_drops():
    # A short "et al." citation legitimately omits most authors; not our failure mode.
    record = ["Szymanski", "Rendy", "Fei", "Kumar", "He", "Ceder"]
    assert author_list_diff(["Szymanski"], record) == []


# --- Rendering-artifact false positives found on the LLZO manuscripts (2026-07-01).
# Crossref ships formula titles as MathML and dashes/math as Unicode; a title typed
# as plain text is the same reference, not drift.

def test_mathml_subscript_title_not_flagged():
    ref = Reference(
        "murugan",
        "Fast Lithium Ion Conduction in Garnet-Type Li7La3Zr2O12",
        ["Murugan"], 2007, "10.0/m",
    )
    record = CrossrefRecord(
        "Fast Lithium Ion Conduction in Garnet‐Type "
        "Li<sub>7</sub>La<sub>3</sub>Zr<sub>2</sub>O<sub>12</sub>",
        ["Murugan"], 2007,
    )
    assert verify(ref, record).status == "ok"


def test_unicode_dash_and_math_symbols_in_title_not_flagged():
    ref = Reference(
        "miara",
        "Effect of Doping (0 <= x <= 0.375) on the Garnet Conductor",
        ["Miara"], 2013, "10.0/d",
    )
    record = CrossrefRecord(
        "Effect of Doping (0 ≤ x ≤ 0.375) on the Garnet Conductor",
        ["Miara"], 2013,
    )
    assert verify(ref, record).status == "ok"


# --- Explicit "et al." truncation: an omitted tail is fine, a wrong name is not.

def test_explicit_et_al_not_flagged_as_dropped_tail():
    # Vancouver "list six, then et al." against a seven-author record: the omitted
    # seventh must not read as a dropped-author error (this false-flagged before).
    cited = ["Leeman", "Liu", "Stiles", "Lee", "Bhatt", "Schoop", "et al."]
    record = ["Leeman", "Liu", "Stiles", "Lee", "Bhatt", "Schoop", "Palgrave"]
    assert author_list_diff(cited, record) == []


def test_et_al_does_not_excuse_a_wrong_author():
    # Planted known-bad: truncation must never wave through a borrowed/wrong name.
    issues = author_list_diff(
        ["Navrotsky", "Mazeina", "et al."],
        ["Navrotsky", "Ma", "Doe", "Birkner"],
    )
    assert any("mazeina" in i.lower() for i in issues)
