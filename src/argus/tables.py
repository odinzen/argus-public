"""Load references from a CSV or TSV table (Zotero, Scopus, Web of Science, PubMed, or by hand).

A table carries no schema, so the risk is a misread that still looks clean: a dropped
author, a shifted column, half a file swallowed by a stray quote. Anything that cannot be
read unambiguously is refused or left to fail the comparison, never guessed into a pass.
"""

from __future__ import annotations

import codecs
import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from .references import _clean, _first_year
from .verify import Reference, first_page_of

# Header names after lowercasing and dropping punctuation, in order of preference. Matching
# is exact: "Publication Title" is the journal and "Short Title" is not the title.
_COLUMNS = {
    "doi": ("doi", "di", "doiurl", "doilink", "doiorurl", "digitalobjectidentifier"),
    "title": ("title", "articletitle", "documenttitle", "papertitle", "ti"),
    "authors": ("authorfullnames", "af", "authors", "author", "au", "authornames", "authorlist"),
    "first author": ("firstauthor", "leadauthor"),
    "year": ("publicationyear", "pubyear", "year", "py", "date", "publicationdate", "issued"),
    "volume": ("volume", "vol", "vl"),
    "first page": (
        "firstpage", "startpage", "beginningpage", "pagestart", "bp",
        "pages", "page", "pagerange", "pp",
    ),
    "key": ("citationkey", "citekey", "bibtexkey", "refid", "paperid", "id", "key"),
}
_BLANK = {"", "-", "--", "n/a", "na", "nan", "none", "null"}


@dataclass
class ReferenceTable:
    refs: list[Reference]
    notes: list[str]  # what the file could not supply, so was not checked


def is_table(path: str | Path) -> bool:
    """By extension, or by header row for a .txt (Web of Science saves savedrecs.txt)."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".csv", ".tsv"):
        return True
    if suffix in (".json", ".bib"):
        return False
    text = _decode(p.read_bytes())
    try:
        _, header = _read_rows(text, _delimiter(text), header_only=True)[0]
    except ValueError:
        return False
    return {"doi", "title"} <= _match_columns(header).keys()


def read_table(path: str | Path) -> ReferenceTable:
    return parse_table(_decode(Path(path).read_bytes()))


def parse_table(text: str) -> ReferenceTable:
    # Excel writes, and hides, a leading "sep=;" line.
    text = re.sub(r"\Asep=.\r?\n", "", text, flags=re.I)
    rows = _read_rows(text, _delimiter(text))
    header_row, header = next((n, row) for n, row in rows if any(row))
    columns = _match_columns(header)
    _require(columns, header)

    records = []
    for number, row in rows:
        if number <= header_row or not any(row):
            continue
        if any(row[len(header):]):
            raise ValueError(
                f"row {number} has more fields than the header; a comma inside a field "
                "needs that field in quotes"
            )
        records.append((number, {
            name: next((v for v in (_cell(row, i) for i in where) if v), "")
            for name, where in columns.items()
        }))
    if not records:
        raise ValueError("the table has a header but no references")

    comma_lists = _separates_authors_with_commas([r.get("authors", "") for _, r in records])
    refs = [_reference(number, record, comma_lists) for number, record in records]
    return ReferenceTable(refs, _notes(columns, refs))


def _decode(raw: bytes) -> str:
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")  # what Excel writes as plain "CSV" on Windows


def _match_columns(header: list[str]) -> dict[str, list[int]]:
    names = [re.sub(r"[^a-z0-9]", "", h.lower()) for h in header]
    found = {
        column: [i for alias in aliases for i, name in enumerate(names) if name == alias]
        for column, aliases in _COLUMNS.items()
    }
    return {column: where for column, where in found.items() if where}


def _delimiter(text: str) -> str:
    """The delimiter that makes the most sense of the header row."""
    def recognized(delimiter: str) -> int:
        try:
            header = next(row for _, row in _read_rows(text, delimiter, header_only=True))
        except ValueError:
            return 0
        return len(_match_columns(header))

    return max(",;\t", key=recognized)


def _read_rows(text: str, delimiter: str, header_only: bool = False) -> list[tuple[int, list[str]]]:
    """(spreadsheet row, fields) pairs. Strict quoting, because a lenient reader lets one
    unclosed quote absorb every reference after it."""
    rows: list[tuple[int, list[str]]] = []
    old_limit = csv.field_size_limit(len(text) + 1)  # exported abstracts and notes run long
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        for number, row in enumerate(reader, 1):
            fields = [field.strip() for field in row]
            if header_only:
                if any(fields):
                    return [(number, fields)]
                continue
            rows.append((number, fields))
    except csv.Error as error:
        raise ValueError(f"malformed quoting near row {len(rows) + 1} ({error})") from None
    finally:
        csv.field_size_limit(old_limit)
    if not any(any(row) for _, row in rows):
        raise ValueError("the file is empty")
    return rows


def _require(columns: dict[str, list[int]], header: list[str]) -> None:
    missing = [name for name in ("doi", "title") if name not in columns]
    if "authors" not in columns and "first author" not in columns:
        missing.append("authors")
    if missing:
        shown = ", ".join(h for h in header if h)[:200]
        raise ValueError(
            f"no column for {', '.join(missing)}. A reference table needs a header row with "
            f"DOI, Title and Authors columns; this one has: {shown}"
        )


def _cell(row: list[str], index: int) -> str:
    value = row[index] if index < len(row) else ""
    return "" if value.lower() in _BLANK else value


def _reference(number: int, record: dict[str, str], comma_lists: bool) -> Reference:
    if record.get("authors"):
        authors, truncated = parse_authors(record["authors"], comma_lists)
    else:
        authors, truncated = parse_authors(record.get("first author", ""))
        truncated = truncated or bool(authors)
    title = _clean(record["title"])
    key = record.get("key", "")
    if re.fullmatch(r"[A-Z0-9]{8}", key):  # Zotero's internal key means nothing to a reader
        key = ""
    return Reference(
        key=f"row {number}: {key or title[:70] or record['doi'] or '(blank)'}",
        title=title,
        authors=authors,
        year=_first_year(record.get("year", "")),
        doi=_doi(record["doi"]),
        volume=_whole(record.get("volume", "")) or None,
        first_page=_page(record.get("first page", "")) or None,
        truncated=truncated,
    )


def _notes(columns: dict[str, list[int]], refs: list[Reference]) -> list[str]:
    notes = []
    absent = [name for name in ("year", "volume", "first page") if name not in columns]
    if absent:
        notes.append(f"no column for {', '.join(absent)}, so not checked")
    shortened = sum(ref.truncated for ref in refs)
    if shortened:
        notes.append(
            f"{shortened} of {len(refs)} give a shortened author list (et al. or first author "
            "only); the authors they leave out were not checked"
        )
    return notes


def _whole(value: str) -> str:
    """Undo the ".0" that pandas adds to an integer column with gaps."""
    return re.sub(r"^(\d+)\.0+$", r"\1", value)


def _page(value: str) -> str:
    return first_page_of(re.sub(r"^pp?(?:\.\s*|\s+)", "", _whole(value), flags=re.I))


def _doi(value: str) -> str | None:
    if re.match(r"https?://", value, re.I):
        found = re.search(r"10\.\d{4,9}/[^\s?#]+", value)
        value = unquote(found.group(0)) if found else ""
    value = re.sub(r"^(?:(?:dx\.)?doi\.org/|doi\s*:?\s*)", "", value, flags=re.I)
    return value.rstrip(".,;") or None


_SEPARATOR = re.compile(r"[;|\r\n]")
_AND = re.compile(r"\s*,?\s+(?:and|&)\s+", re.I)
_ET_AL_TAIL = re.compile(
    r"[\s,;|]*(?:\bet\.?\s+al(?:ii)?\b|(?:\band\s+|[,;|]\s*)others\b)\W*$", re.I
)
_SUFFIX = re.compile(r",\s*(?:Jr|Sr|II|III|IV)\b\.?(?=\s*(?:[,;|\r\n]|$))")
_SCOPUS_ID = re.compile(r"\s*\(\d{5,}\)")
# Dotted runs of any length, with two-letter Cyrillic initials (Yu.N.); undotted runs stop
# at three letters so that a capitalized surname (Wei WANG) is not read as initials.
_DOTTED = re.compile(r"(?:[^\W\d_]{1,2}\.[-\u2010]?)+[^\W\d_]?")
_UNDOTTED = re.compile(r"[^\W\d_](?:[-\u2010]?[^\W\d_]){0,2}\.?")


def parse_authors(cell: str, comma_lists: bool = False) -> tuple[list[str], bool]:
    """Author cell -> ("Given Family" names, whether it ends in et al.).

    Semicolons are definite. With commas alone, "Family, Given" and "Author, Author" can
    look the same. Two full names are read as two people, since a wrong split shows up as a
    name that is not on the record while a wrong join would hide one; "Day, Terence" stays
    one person unless the file separates authors with commas.
    """
    cell = _SUFFIX.sub("", _SCOPUS_ID.sub("", cell))
    shortened = _ET_AL_TAIL.sub("", cell)
    truncated = shortened != cell
    chunks = [c for c in (_tidy(c) for c in _SEPARATOR.split(shortened)) if c]
    if len(chunks) == 1:
        chunks = _split_on_and(chunks[0])
    inverted = len(chunks) > 1 and all(c.count(",") == 1 for c in chunks)
    names: list[str] = []
    for chunk in chunks:
        if _AND.search(chunk):
            names += parse_authors(chunk, comma_lists)[0]
        else:
            names += _comma_names(chunk, inverted, comma_lists)
    return [name for name in (_clean(n) for n in names) if name], truncated


def _tidy(chunk: str) -> str:
    return re.sub(r"^(?:and|&)\s+", "", chunk.strip(" ,\t"), flags=re.I)


def _split_on_and(chunk: str) -> list[str]:
    """'A, B and C, D' is a list of inverted names; 'A, B and C' is a comma list."""
    parts = [p for p in (_tidy(p) for p in _AND.split(chunk)) if p]
    if len(parts) > 1 and any("," in p for p in parts):
        if not all(p.count(",") == 1 for p in parts):
            return [", ".join(parts)]
    return parts


def _is_initials(text: str) -> bool:
    tokens = text.split()
    return bool(tokens) and all(_is_initials_token(t) for t in tokens)


def _is_initials_token(token: str) -> bool:
    if token in ("Jr.", "Sr.", "St."):
        return False
    if _UNDOTTED.fullmatch(token) and token.upper() == token:
        return True
    letters = re.findall(r"[^\W\d_]+", token)
    return bool(_DOTTED.fullmatch(token)) and all(x[0].isupper() for x in letters)


def _family_then_initials(name: str) -> tuple[str, str] | None:
    """Split "Smith JA" or "van der Berg J. W."; None for "Jane Roe" or an all-caps name."""
    tokens = name.split()
    cut = len(tokens)
    while cut > 0 and _is_initials(tokens[cut - 1]):
        cut -= 1
    family, initials = " ".join(tokens[:cut]), " ".join(tokens[cut:])
    return (family, initials) if initials and any(c.islower() for c in family) else None


def _given_first(name: str) -> str:
    split = _family_then_initials(name)
    return f"{split[1]} {split[0]}" if split else name


def _comma_names(chunk: str, inverted: bool, comma_lists: bool) -> list[str]:
    parts = [p for p in (p.strip() for p in chunk.split(",")) if p]
    families, givens = parts[0::2], parts[1::2]
    if len(families) == len(givens) and all(map(_is_initials, givens)):
        if not any(map(_is_initials, families)):
            return [f"{g} {f}" for f, g in zip(families, givens, strict=True)]
    if len(parts) == 2 and _is_inverted_name(parts[0], parts[1], inverted, comma_lists):
        return [f"{parts[1]} {parts[0]}"]
    return [_given_first(p) for p in parts]


def _is_inverted_name(left: str, right: str, inverted: bool, comma_lists: bool) -> bool:
    if _family_then_initials(left):  # "Smith JA, Doe B" is two people
        return False
    if inverted:
        return True
    if comma_lists:
        return False
    both_full_names = len(left.split()) > 1 and len(right.split()) > 1
    return not both_full_names or left[0].islower() or bool(_family_then_initials(right))


def _separates_authors_with_commas(cells: Iterable[str]) -> bool:
    """True when the file lists authors by comma, so a bare "Mao, Selleby" is two people."""
    cells = list(cells)
    if any(_SEPARATOR.search(c) for c in cells):
        return False
    lists = [_ET_AL_TAIL.sub("", c).split(",") for c in cells if not _AND.search(c)]
    return any(len(x) > 2 and not any(_is_initials(p.strip()) for p in x) for x in lists)
