import pytest

from argus import cli
from argus.references import load_references
from argus.resolver import Resolution
from argus.tables import is_table, parse_authors, parse_table
from argus.verify import CrossrefRecord, verify

HEADER = "DOI,Title,Authors,Year,Volume,Pages\n"
RECORD = CrossrefRecord("A title", ["Jane Roe", "John Smith"], 2020, "12", "100")


def one(text):
    refs = parse_table(text).refs
    assert len(refs) == 1
    return refs[0]


# --- the exports people actually have -----------------------------------------------


def test_zotero_columns():
    ref = one(
        '"Key","Item Type","Publication Year","Author","Title","Publication Title","DOI","Date",'
        '"Pages","Volume","Short Title"\n'
        '"AB12CD34","journalArticle","2020","Roe, Jane; Smith, John","A title","J. Things",'
        '"10.0/x","2020-05-01","100-110","12","Short"\n'
    )
    assert ref.key == "row 2: A title"
    assert ref.title == "A title"  # not the journal, not the short title
    assert ref.authors == ["Jane Roe", "John Smith"]
    assert (ref.year, ref.doi, ref.volume, ref.first_page) == (2020, "10.0/x", "12", "100")
    assert verify(ref, RECORD).status == "ok"


def test_scopus_columns_prefer_full_names():
    ref = one(
        '"Authors","Author full names","Author(s) ID","Title","Year","Source title","Volume",'
        '"Art. No.","Page start","Page end","DOI"\n'
        '"Roe J.; Smith J.B.","Roe, Jane (57193000001); Smith, John B. (7004000000)","1; 2",'
        '"A title","2020","J. Things","12","","100","110","10.0/x"\n'
    )
    assert ref.authors == ["Jane Roe", "John B. Smith"]
    assert verify(ref, RECORD).status == "ok"


@pytest.mark.parametrize("name", ["savedrecs.txt", "savedrecs.tsv"])
def test_web_of_science_tab_delimited(tmp_path, name):
    p = tmp_path / name
    p.write_text(
        "PT\tAU\tAF\tTI\tSO\tVL\tBP\tEP\tDI\tPY\n"
        "J\tRoe, J; Smith, J\tRoe, Jane; Smith, John\tA title\tJ THINGS\t12\t100\t110\t"
        "10.0/x\t2020\n",
        encoding="utf-16",
    )
    ref = load_references(p)[0]
    assert ref.authors == ["Jane Roe", "John Smith"]
    assert verify(ref, RECORD).status == "ok"


def test_pubmed_columns():
    ref = one(
        "PMID,Title,Authors,Citation,First Author,Journal/Book,Publication Year,DOI\n"
        '1,A title.,"Roe J, Smith JB.",J Things. 2020,Roe J,J Things,2020,10.0/x\n'
    )
    assert ref.authors == ["J Roe", "JB. Smith"]  # PubMed ends the list with a period
    assert not ref.truncated
    assert verify(ref, RECORD).status == "ok"


def test_first_author_only_is_checked_and_declared():
    table = parse_table("doi,first_author,title\n10.0/x,Roe,A title\n10.0/y,Wrong,A title\n")
    good, bad = table.refs
    assert good.truncated
    assert verify(good, RECORD).status == "ok"
    assert verify(bad, RECORD).status == "suspect"
    assert any("2 of 2 give a shortened author list" in n for n in table.notes)
    assert any("year, volume, first page" in n for n in table.notes)


# --- author cells --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cell", "names"),
    [
        ("Day, Terence", ["Terence Day"]),
        ("Roe, Jane; Smith, John B.", ["Jane Roe", "John B. Smith"]),
        ("Jane Roe; John Smith", ["Jane Roe", "John Smith"]),
        ("Roe J.; Smith J.-B.", ["J. Roe", "J.-B. Smith"]),
        ("Jane Roe | John Smith", ["Jane Roe", "John Smith"]),
        ("Jane Roe\nJohn Smith", ["Jane Roe", "John Smith"]),
        ("Jane Roe, John Smith", ["Jane Roe", "John Smith"]),
        ("Jane Roe, John Smith and Al Poe", ["Jane Roe", "John Smith", "Al Poe"]),
        ("Roe, Jane and Smith, John", ["Jane Roe", "John Smith"]),
        ("Roe, J., Smith, J. B., & Poe, A.", ["J. Roe", "J. B. Smith", "A. Poe"]),
        ("Roe, J. and Smith, J.", ["J. Roe", "J. Smith"]),
        ("Roe, J.; Smith, J. & Poe, A.", ["J. Roe", "J. Smith", "A. Poe"]),
        ("Roe J, Smith JB", ["J Roe", "JB Smith"]),
        ("van der Berg J.", ["J. van der Berg"]),
        ("van der Berg, Jan Peter", ["Jan Peter van der Berg"]),
        ("García López, Juan Carlos; Roe, Jane", ["Juan Carlos García López", "Jane Roe"]),
        ("Smith, John, Jr.; Roe, Jane", ["John Smith", "Jane Roe"]),
        ("Mao, Selleby, Sundman", ["Mao", "Selleby", "Sundman"]),
        ("Mao, Selleby and Sundman", ["Mao", "Selleby", "Sundman"]),
        ("JOHN LI", ["JOHN LI"]),
        ("Wei WANG", ["Wei WANG"]),
        ("Kesapragada V.S.R.K.M.", ["V.S.R.K.M. Kesapragada"]),
        ("Petrov Yu.N.; Ivanov Ya. A.", ["Yu.N. Petrov", "Ya. A. Ivanov"]),
        ("John Smith Jr.", ["John Smith Jr."]),
        (r"M{\"u}ller, Hans", ["Hans Muller"]),
        ("", []),
    ],
)
def test_author_cell(cell, names):
    assert parse_authors(cell) == (names, False)


@pytest.mark.parametrize(
    "cell",
    ["Roe, J. et al.", "Roe J et al", "Roe, J.; et al.", "Roe J, et al.", "Roe, J. and others"],
)
def test_et_al_sets_truncated(cell):
    names, truncated = parse_authors(cell)
    assert [n.split()[-1] for n in names] == ["Roe"]
    assert truncated


def test_name_ending_like_et_al_is_kept():
    assert parse_authors("Roe, Jane; Petal, Al") == (["Jane Roe", "Al Petal"], False)
    assert parse_authors("Jane Roe; Amy Others") == (["Jane Roe", "Amy Others"], False)


def test_two_surnames_in_a_comma_separated_file():
    refs = parse_table(
        'DOI,Title,Authors\n10.0/x,A,"Mao, Selleby, Sundman"\n10.0/y,B,"Mao, Selleby"\n'
    ).refs
    assert refs[1].authors == ["Mao", "Selleby"]


# --- planted bad citations must fire -------------------------------------------------


@pytest.mark.parametrize(
    "authors",
    [
        "Jane Roe, Max Extra and John Smith",
        "Jane Roe, Max Extra, John Smith",
        "Roe, Jane; Extra, Max; Smith, John",
        "Roe, Jane; Extra, Max & Smith, John",
        "Roe J, Extra M, Smith J",
        "Roe, J., Extra, M., & Smith, J.",
        "Roe, Jane and Extra, Max and Smith, John",
        "Jane Roe, Max Extra; John Smith",
        "Roe J., Extra M. et al.",
        "Roe, Jane; Smith, John; Extra, Max; et al.",
    ],
)
def test_borrowed_author_is_caught_in_every_list_style(authors):
    ref = one(HEADER + f'10.0/x,A title,"{authors}",2020,12,100-110\n')
    finding = verify(ref, RECORD)
    assert finding.status == "suspect"
    assert any("extra" in i for i in finding.issues)


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ('10.0/x,A title,"Roe, Jane",2020,12,100', "missing from the citation: smith"),
        ('10.0/x,A title,"Roe, K.; Smith, John",2020,12,100', "initials differ for roe"),
        ('10.0/x,Other words entirely,"Roe, Jane; Smith, John",2020,12,100', "title differs"),
        ('10.0/x,A title,"Roe, Jane; Smith, John",2015,12,100', "year differs"),
        ('10.0/x,A title,"Roe, Jane; Smith, John",2020,21,100', "volume differs"),
        ('10.0/x,A title,"Roe, Jane; Smith, John",2020,12,101', "first page differs"),
        ("10.0/x,A title,,2020,12,100", "no authors listed"),
        ('10.0/x,,"Roe, Jane; Smith, John",2020,12,100', "title differs"),
    ],
)
def test_planted_error_is_flagged(row, expected):
    finding = verify(one(HEADER + row + "\n"), RECORD)
    assert finding.status == "suspect"
    assert any(expected in i for i in finding.issues)


# --- files that must be refused, not half read ---------------------------------------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("\n\n", "empty"),
        (HEADER, "no references"),
        ("DOI,Title,Year\n10.0/x,A title,2020\n", "no column for authors"),
        ("Title,Authors\nA title,Roe\n", "no column for doi"),
        ("10.0/x,A title,Roe\n", "no column for"),
        (HEADER + "10.0/x,A title, with a comma,Roe,2020,12,100\n", "row 2 has more fields"),
        (HEADER + '10.0/x,"A title,Roe,2020,12,100\n10.0/y,B,Poe,2021,1,1\n', "quoting"),
        (HEADER + '10.0/x,"A" title,Roe,2020,12,100\n', "quoting"),
    ],
)
def test_unreadable_table_is_refused(text, message):
    with pytest.raises(ValueError, match=message):
        parse_table(text)


# --- spreadsheet habits --------------------------------------------------------------


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_delimiters(delimiter):
    row = ["10.0/x", "A title", '"Roe, Jane; Smith, John"', "2020", "12", "100-110"]
    text = delimiter.join(HEADER.strip().split(",")) + "\n" + delimiter.join(row) + "\n"
    assert verify(one(text), RECORD).status == "ok"


def test_semicolon_file_with_sep_line():
    ref = one('sep=;\nDOI;Title;Authors\n10.0/x;A title;"Roe, Jane; Smith, John"\n')
    assert ref.key == "row 2: A title"
    assert ref.authors == ["Jane Roe", "John Smith"]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1252", "utf-16"])
def test_encodings(tmp_path, encoding):
    p = tmp_path / "refs.CSV"
    p.write_bytes('DOI,Title,Authors\n10.0/x,Über,"Müller, Hans"\n'.encode(encoding))
    ref = load_references(p)[0]
    assert (ref.title, ref.authors) == ("Über", ["Hans Müller"])


@pytest.mark.parametrize(
    ("cell", "doi"),
    [
        ("10.1021/acs.x", "10.1021/acs.x"),
        ("https://doi.org/10.1021/acs.x", "10.1021/acs.x"),
        ("http://dx.doi.org/10.1021/acs.x", "10.1021/acs.x"),
        ("doi.org/10.1021/acs.x", "10.1021/acs.x"),
        ("doi: 10.1021/acs.x.", "10.1021/acs.x"),
        ("DOI:10.1021/acs.x", "10.1021/acs.x"),
        ("https://doi.org/10.1002/%28SICI%291097", "10.1002/(SICI)1097"),
        ("https://pubs.example.org/doi/abs/10.1111/j.1551?x=1", "10.1111/j.1551"),
        ("https://example.org/paper/7", None),
        ("N/A", None),
        ("", None),
        ("not a doi", "not a doi"),  # stays, so it is reported broken rather than absent
    ],
)
def test_doi_cell(cell, doi):
    assert one(f"DOI,Title,Authors\n{cell},A title,Roe\n").doi == doi


def test_float_columns_and_page_prefix():
    ref = one(HEADER + '10.0/x,A title,"Roe, Jane; Smith, John",2020.0,12.0,pp. 100-110\n')
    assert verify(ref, RECORD).status == "ok"
    assert one(HEADER + "10.0/x,A title,Roe,2020,12,100.0\n").first_page == "100"
    assert one(HEADER + "10.0/x,A title,Roe,2020,12,P123\n").first_page == "P123"


def test_row_number_matches_the_spreadsheet():
    text = HEADER + '10.0/x,"A\nwrapped title",Roe,,,\n,,,,,\n10.0/y,B,Poe,,,,,\n'
    assert [r.key for r in parse_table(text).refs] == ["row 2: A wrapped title", "row 4: B"]


def test_citation_key_column_is_used():
    assert one("Citation Key,DOI,Title,Authors\nroe2020,10.0/x,T,Roe\n").key == "row 2: roe2020"


def test_long_cell_is_read():
    notes = "x" * 300_000
    assert one(f"DOI,Title,Authors,Notes\n10.0/x,T,Roe,{notes}\n").title == "T"


# --- command line --------------------------------------------------------------------


def test_cli_reports_rows_and_exit_codes(tmp_path, monkeypatch, capsys):
    records = {"10.0/x": RECORD, "10.0/bad": RECORD}
    monkeypatch.setattr(
        cli, "resolve_doi", lambda doi, *_: Resolution(records.get(doi), "crossref")
    )
    p = tmp_path / "refs.csv"
    good = '10.0/x,A title,"Roe, Jane; Smith, John",2020,12,100\n'
    p.write_text(HEADER + good, encoding="utf-8")
    assert cli.main([str(p)]) == 0
    assert "[ok]      row 2: A title" in capsys.readouterr().out

    p.write_text(
        HEADER + good + '10.0/bad,A title,"Roe, Jane; Extra, Max",2020,12,100\n'
        ",No doi,Roe,,,\n10.0/gone,Gone,Roe,,,\n",
        encoding="utf-8",
    )
    assert cli.main(["check", str(p)]) == 1
    out = capsys.readouterr().out
    assert "[suspect] row 3: A title" in out
    assert "[no-doi]  row 4: No doi" in out
    assert "[broken]  row 5: Gone" in out
    assert "4 checked, 3 need review." in out


@pytest.mark.parametrize("text", ["", "plain words", "[1] Roe, J. A title, doi: 10.0/x"])
def test_text_without_a_header_row_is_not_a_table(tmp_path, text):
    p = tmp_path / "refs.txt"
    p.write_text(text, encoding="utf-8")
    assert not is_table(p)
    assert cli.main(["check", str(p)]) == 2


def test_cli_refuses_an_unreadable_table(tmp_path, capsys):
    p = tmp_path / "data.csv"
    p.write_text("T,Cp\n298,25.1\n", encoding="utf-8")
    assert cli.main(["check", str(p)]) == 2
    assert "no column for doi, title, authors" in capsys.readouterr().err
