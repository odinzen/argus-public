from argus.openalex import _parse
from argus.resolver import FunctionResolver, resolve_doi
from argus.verify import CrossrefRecord


def test_falls_back_to_second_resolver():
    miss = FunctionResolver("crossref", lambda doi, mailto=None: None)
    hit = FunctionResolver("openalex", lambda doi, mailto=None: CrossrefRecord("T", ["Doe"], 2020))
    resolution = resolve_doi("10.0/x", [miss, hit])
    assert resolution.resolved
    assert resolution.source == "openalex"


def test_unresolved_everywhere():
    miss = FunctionResolver("crossref", lambda doi, mailto=None: None)
    resolution = resolve_doi("10.0/x", [miss])
    assert not resolution.resolved
    assert resolution.source == ""


def test_first_resolver_wins():
    a = FunctionResolver("crossref", lambda doi, mailto=None: CrossrefRecord("A", ["Aa"]))
    b = FunctionResolver("openalex", lambda doi, mailto=None: CrossrefRecord("B", ["Bb"]))
    assert resolve_doi("10.0/x", [a, b]).source == "crossref"


def test_openalex_parse_maps_fields():
    data = {
        "id": "https://openalex.org/W1",
        "display_name": "A real title",
        "publication_year": 2021,
        "authorships": [
            {"author": {"display_name": "Jane Doe"}},
            {"author": {"display_name": "John Roe"}},
        ],
        "biblio": {"volume": "12", "first_page": "100", "last_page": "110"},
    }
    record = _parse(data)
    assert record.title == "A real title"
    assert record.authors == ["Jane Doe", "John Roe"]
    assert record.year == 2021
    assert record.volume == "12"
    assert record.first_page == "100"


def test_openalex_parse_rejects_empty():
    assert _parse({}) is None
    assert _parse({"id": None}) is None
