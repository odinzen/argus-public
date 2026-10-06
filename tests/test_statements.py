from argus import statements

# A minimal back-matter block that satisfies the default required set.
CLEAN = """\
## Conflict of interest
The authors declare a commercial interest: M.E.B. is a founder of Odinzen LLC.

## Data availability
The thermodynamic database is available from the corresponding author on reasonable
request. Sol-computed data are openly available at the project repository.
"""


def test_clean_passes():
    report = statements.check_statements(CLEAN)
    assert report.status == "ok"
    assert all(f.ok for f in report.findings)


def test_missing_data_availability_flagged():
    text = "## Conflict of interest\nA founder of Odinzen LLC declares this.\n"
    report = statements.check_statements(text)
    das = next(f for f in report.findings if f.key == "data_availability")
    assert not das.present
    assert report.status == "suspect"


def test_coi_without_commercial_interest_flagged():
    text = CLEAN.replace("M.E.B. is a founder of Odinzen LLC.", "The authors declare none.")
    report = statements.check_statements(text)
    coi = next(f for f in report.findings if f.key == "conflict_of_interest")
    assert coi.present and not coi.ok  # present but does not name Odinzen


def test_ai_use_autonomous_flagged_for_nature():
    text = CLEAN + "\n## Use of AI\nAn autonomous large language model agent did the work.\n"
    report = statements.check_statements(text, journal="Nature")
    ai = next(f for f in report.findings if f.key == "ai_use")
    assert ai.present and not ai.ok
    assert any("autonomous" in i for i in ai.issues)


def test_ai_use_agentic_passes_for_nature():
    text = (
        CLEAN
        + "\n## Author contributions\nM.E.B. designed the study.\n"
        + "\n## Use of AI\nAn agentic, human-gated loop using generative AI tools assisted; "
        "all references were verified by a human.\n"
    )
    report = statements.check_statements(text, journal="Nature")
    ai = next(f for f in report.findings if f.key == "ai_use")
    assert ai.ok


def test_sol_use_requires_jennewein_citation():
    text = CLEAN + "\n## Acknowledgements\nComputations used ASU Sol.\n"
    report = statements.check_statements(text)
    assert report.extra_issues  # Sol named, Jennewein DOI absent
    assert "10.1145/3569951.3597573" in report.extra_issues[0]


def test_sol_with_citation_ok():
    text = CLEAN + "\n## Acknowledgements\nComputations used ASU Sol (10.1145/3569951.3597573).\n"
    report = statements.check_statements(text)
    assert report.extra_issues == []


def test_byline_tempe_warning():
    text = "Odinzen LLC, Tempe, Arizona\n" + CLEAN
    assert any("Houston" in w for w in statements.byline_warnings(text))


def test_heading_only_block_folds_in_the_body():
    # A bare section heading matches the cue but the declaration lives in the
    # next paragraph; the rule must judge heading + body, not the heading alone.
    text = (
        "## Competing interests\n\n"
        "The author founded Odinzen LLC and declares this as a competing interest.\n\n"
        "## Data availability\n\n"
        "The data are available in the repository.\n"
    )
    report = statements.check_statements(text)
    ci = next(f for f in report.findings if f.key == "conflict_of_interest")
    assert ci.present and not ci.issues


def test_tempe_warning_needs_the_word_not_temperature():
    # "temperature" contains "tempe"; a thermodynamics paper must not trip the
    # byline warning unless the city itself appears.
    text = "Odinzen LLC, Houston. The melting temperature is 1673 K.\n" + CLEAN
    assert not any("Houston" in w for w in statements.byline_warnings(text))
