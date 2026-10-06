from argus.crosscheck import audit
from argus.fields import CitedItem, FieldCitation
from argus.resolver import FunctionResolver
from argus.verify import CrossrefRecord


def _cite(order, printed, numbers, items):
    return FieldCitation(
        order=order,
        items=[CitedItem(key=k, item_data=d) for k, d in items],
        printed=printed,
        numbers=numbers,
    )


# Resolver: clean records for /good and /other, a conflated byline for /bad.
def _record(doi, mailto=None):
    if doi == "10.0/good":
        return CrossrefRecord("Right title", ["Jane Doe"], 2020)
    if doi == "10.0/other":
        return CrossrefRecord("Other", ["R Roe"], 2021)
    if doi == "10.0/bad":
        return CrossrefRecord("Right title", ["Someone Else"], 2020)
    return None


FAKE = [FunctionResolver("crossref", _record)]


def test_keyed_numbering_and_metadata():
    good = {
        "title": "Right title",
        "author": [{"family": "Doe", "given": "Jane"}],
        "DOI": "10.0/good",
    }
    other = {"title": "Other", "author": [{"family": "Roe", "given": "R"}], "DOI": "10.0/other"}
    citations = [
        _cite(0, "[1]", [1], [("KEYA1111", good)]),
        _cite(1, "[2]", [2], [("KEYB2222", other)]),
        _cite(2, "[1]", [1], [("KEYA1111", good)]),  # re-cite of ref 1
    ]
    result = audit(citations, resolvers=FAKE)
    assert result.status == "ok"
    assert [r.canonical_number for r in result.references] == [1, 2]
    assert result.references[0].key == "KEYA1111"
    assert result.references[0].metadata_status == "ok"
    assert all(r.number_ok for r in result.references)


def test_flags_conflated_metadata():
    bad = {
        "title": "Right title",
        "author": [{"family": "Doe", "given": "Jane"}],
        "DOI": "10.0/bad",
    }
    result = audit([_cite(0, "[1]", [1], [("K", bad)])], resolvers=FAKE)
    assert result.references[0].metadata_status == "suspect"
    assert result.status == "suspect"


def test_flags_broken_doi():
    item = {"title": "X", "author": [{"family": "Q"}], "DOI": "10.0/missing"}
    result = audit([_cite(0, "[1]", [1], [("K", item)])], resolvers=FAKE)
    assert result.references[0].metadata_status == "broken"


def test_flags_wrong_printed_number():
    # Second-appearing item printed as [1] when it should be [2]: numbering drift.
    a = {"title": "A", "DOI": "10.0/good"}
    b = {"title": "B", "DOI": "10.0/good"}
    citations = [
        _cite(0, "[1]", [1], [("KA", a)]),
        _cite(1, "[1]", [1], [("KB", b)]),  # KB is the 2nd ref but printed [1]
    ]
    result = audit(citations, resolvers=FAKE)
    kb = next(r for r in result.references if r.key == "KB")
    assert kb.canonical_number == 2
    assert not kb.number_ok
    assert result.status == "suspect"


def test_no_doi_item_is_not_a_failure():
    item = {"title": "A book", "author": [{"family": "Author"}]}  # no DOI
    result = audit([_cite(0, "[1]", [1], [("K", item)])], resolvers=FAKE)
    assert result.references[0].metadata_status == "no-doi"
    assert result.status == "ok"
