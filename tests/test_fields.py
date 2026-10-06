from argus.fields import extract_citations

# A minimal Zotero-authored document.xml: two complex-field citations, the first with its
# JSON split across two instrText runs (as Word does for long fields).
TWO_CITES = (
    "<w:document><w:body>"
    "<w:p><w:r><w:instrText> ADDIN ZOTERO_ITEM CSL_CITATION "
    '{"properties":{"formattedCitation":"[1]"},"citationItems":[{"uris":'
    '["http://zotero.org/groups/123/items/ABCD2345"],"itemData":{"title":"First paper",'
    "</w:instrText></w:r>"
    "<w:r><w:instrText>"
    '"author":[{"family":"Doe","given":"J"}],"issued":{"date-parts":[[2020]]},"DOI":"10.0/a"}}]} '
    "</w:instrText></w:r></w:p>"
    "<w:p><w:r><w:instrText> ADDIN ZOTERO_ITEM CSL_CITATION "
    '{"properties":{"formattedCitation":"[2]"},"citationItems":[{"uris":'
    '["http://zotero.org/groups/123/items/WXYZ6789"],"itemData":{"title":"Second paper",'
    '"author":[{"family":"Roe","given":"R"}],"issued":{"date-parts":[[2021]]},"DOI":"10.0/b"}}]} '
    "</w:instrText></w:r></w:p>"
    "</w:body></w:document>"
)


def test_extracts_keys_metadata_and_numbers():
    cites = extract_citations(TWO_CITES)
    assert len(cites) == 2
    assert [c.numbers for c in cites] == [[1], [2]]
    assert cites[0].items[0].key == "ABCD2345"
    assert cites[1].items[0].key == "WXYZ6789"
    # Metadata survives the JSON being split across two instrText runs.
    assert cites[0].items[0].item_data["title"] == "First paper"
    assert cites[0].items[0].item_data["DOI"] == "10.0/a"


def test_multi_item_citation():
    xml = (
        "<w:body><w:instrText> ADDIN ZOTERO_ITEM CSL_CITATION "
        '{"properties":{"formattedCitation":"[3, 5]"},"citationItems":['
        '{"uris":["http://zotero.org/users/9/items/AAAA1111"],"itemData":{"title":"A"}},'
        '{"uris":["http://zotero.org/users/9/items/BBBB2222"],"itemData":{"title":"B"}}]} '
        "</w:instrText></w:body>"
    )
    cites = extract_citations(xml)
    assert len(cites) == 1
    assert [it.key for it in cites[0].items] == ["AAAA1111", "BBBB2222"]
    assert cites[0].numbers == [3, 5]


def test_no_field_codes():
    assert extract_citations("<w:body><w:p><w:t>plain text [1]</w:t></w:p></w:body>") == []
