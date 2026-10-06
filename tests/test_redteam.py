"""Red team for Argus's input parsers: feed malformed references and confirm he fails closed
(a clean result or a clean typed error), never an uncaught traceback. Every case that once
crashed stays here as a regression. Standalone runner (no pytest needed) or pytest.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import argus.references as R  # noqa: E402


def _write(name, content):
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def test_happy_path_still_parses():
    ref = R.reference_from_csl(
        {"id": "a", "title": "T", "author": [{"given": "J", "family": "Doe"}],
         "issued": {"date-parts": [[2020]]}, "DOI": "10.1/x", "volume": "3", "page": "12-20"}
    )
    assert ref.title == "T" and ref.year == 2020 and ref.authors == ["J Doe"]


def test_author_field_not_a_list():
    R.reference_from_csl({"title": "T", "author": "Doe, J."})  # must not crash


def test_nonnumeric_year_is_none():
    assert R.reference_from_csl({"title": "T", "issued": {"date-parts": [["n.d."]]}}).year is None


def test_empty_issued_is_none():
    assert R.reference_from_csl({"title": "T", "issued": {}}).year is None


def test_csl_single_object_not_array():
    p = _write("refs.json", json.dumps({"title": "Solo", "author": [{"family": "X"}]}))
    assert len(R.load_csl_json(p)) == 1


def test_csl_list_with_junk_items():
    p = _write("refs.json", json.dumps(["a bare string", None, 42, {"title": "Real"}]))
    titles = [r.title for r in R.load_csl_json(p)]
    assert "Real" in titles


def test_invalid_json_raises_clean_error():
    p = _write("bad.json", "{ this is not json")
    try:
        R.load_references(p)
        raise AssertionError("expected a parse error")
    except ValueError:
        pass  # JSONDecodeError is a ValueError; a clean typed failure, not a random crash


def test_bibtex_unbalanced_braces_no_crash():
    p = _write("x.bib", "@article{key, title={Unclosed brace ")
    R.load_bibtex(p)  # must not crash


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[pass] {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {e.__class__.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
