from argus.references import load_bibtex, load_references

BIB = """
@article{day2023,
  author = {Day, Terence},
  title = {A {Preliminary} Investigation of Fake Citations},
  journal = {The Professional Geographer},
  year = {2023},
  volume = {75},
  pages = {1024--1027},
  doi = {10.1080/00330124.2023.2190373}
}

@article{ji2023,
  author = {Ji, Ziwei and Lee, Nayeon and Fung, Pascale},
  title = "Survey of Hallucination",
  year = 2023,
  volume = {55},
  pages = {1--38},
  doi = {10.1145/3571730}
}
"""

CSL = """
[{"id": "x", "title": "T", "author": [{"given": "A", "family": "Doe"}],
  "issued": {"date-parts": [[2020]]}, "DOI": "10.0/x"}]
"""


def test_bibtex_fields(tmp_path):
    p = tmp_path / "refs.bib"
    p.write_text(BIB, encoding="utf-8")
    refs = {r.key: r for r in load_bibtex(p)}
    assert len(refs) == 2

    day = refs["day2023"]
    assert day.title == "A Preliminary Investigation of Fake Citations"
    assert day.authors == ["Terence Day"]
    assert day.year == 2023
    assert day.volume == "75"
    assert day.first_page == "1024"
    assert day.doi == "10.1080/00330124.2023.2190373"

    ji = refs["ji2023"]
    assert ji.authors == ["Ziwei Ji", "Nayeon Lee", "Pascale Fung"]
    assert ji.year == 2023  # bare (unbraced) value
    assert ji.first_page == "1"


def test_bibtex_plain_name_order(tmp_path):
    p = tmp_path / "r.bib"
    p.write_text("@article{k, author = {Jane Roe}, title = {T}, year = {2021}}", encoding="utf-8")
    assert load_bibtex(p)[0].authors == ["Jane Roe"]


def test_dispatch_by_extension(tmp_path):
    bib = tmp_path / "a.bib"
    bib.write_text(BIB, encoding="utf-8")
    csl = tmp_path / "b.json"
    csl.write_text(CSL, encoding="utf-8")
    assert len(load_references(bib)) == 2
    assert load_references(csl)[0].doi == "10.0/x"


def test_dispatch_by_content_sniff(tmp_path):
    p = tmp_path / "refs.txt"  # no recognized extension
    p.write_text(BIB, encoding="utf-8")
    assert len(load_references(p)) == 2


def test_and_others_is_not_an_author(tmp_path):
    p = tmp_path / "r.bib"
    p.write_text(
        "@article{k, author = {Smith, John and Doe, Jane and others}, title={T}, year={2023}}",
        encoding="utf-8",
    )
    ref = load_bibtex(p)[0]
    assert ref.authors == ["John Smith", "Jane Doe"]
    assert ref.truncated  # "and others" is et al.: the omitted tail is not a dropped author


def test_csl_others_literal_sets_truncated():
    from argus.references import reference_from_csl

    ref = reference_from_csl({
        "id": "x", "title": "T", "DOI": "10.0/x",
        "author": [{"given": "A", "family": "Doe"}, {"literal": "others"}],
    })
    assert ref.authors == ["A Doe"]
    assert ref.truncated


def test_latex_accented_name_matches_record(tmp_path):
    from argus.verify import author_list_diff

    p = tmp_path / "r.bib"
    p.write_text(r'@article{k, author = {M{\"u}ller, Hans}, title={T}, year={2023}}', "utf-8")
    cited = load_bibtex(p)[0].authors
    assert author_list_diff(cited, ["Müller"]) == []
