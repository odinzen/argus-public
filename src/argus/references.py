"""Load references from CSL-JSON or BibTeX, the formats reference managers export.

CSL-JSON is Zotero's "Export Items -> CSL JSON"; BibTeX (.bib) is what LaTeX users
keep. `load_references` picks the parser by extension, falling back to a content sniff.
Both produce the same `Reference` objects, so the verifier does not care which was used.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .verify import Reference, first_page_of


def load_references(path: str | Path) -> list[Reference]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".bib":
        return load_bibtex(p)
    if suffix == ".json":
        return load_csl_json(p)
    text = p.read_text(encoding="utf-8").lstrip()
    return load_bibtex(p) if text.startswith("@") else load_csl_json(p)


_ET_AL_LITERAL = {"others", "et al", "et al.", "et alii", "and others"}


def _csl_year(item: dict) -> int | None:
    """Year from a CSL date-parts, robust to malformed shapes ('n.d.', {}, non-lists)."""
    iss = item.get("issued")
    parts = iss.get("date-parts") if isinstance(iss, dict) else None
    well_formed = isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]
    val = parts[0][0] if well_formed else None
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def reference_from_csl(item: dict) -> Reference:
    """Build a Reference from one CSL-JSON item (a list entry or a Zotero itemData block)."""
    raw = item.get("author", [])
    if not isinstance(raw, list):  # a malformed export can hand us a bare string
        raw = []

    def _sentinel(a) -> bool:  # CSL renders "et al." as a literal "others" author
        if not isinstance(a, dict):
            return False
        return (a.get("family") or a.get("literal") or "").strip().lower() in _ET_AL_LITERAL

    authors = [
        " ".join(filter(None, [a.get("given"), a.get("family") or a.get("literal")]))
        for a in raw
        if isinstance(a, dict) and not _sentinel(a)
    ]
    volume = item.get("volume")
    return Reference(
        key=item.get("id") or item.get("DOI") or item.get("title", "?"),
        title=item.get("title", ""),
        authors=[a for a in authors if a],
        year=_csl_year(item),
        doi=item.get("DOI"),
        volume=str(volume) if volume else None,
        first_page=first_page_of(item.get("page")) or None,
        truncated=any(_sentinel(a) for a in raw),
    )


def load_csl_json(path: str | Path) -> list[Reference]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):  # a single item exported without the surrounding array
        data = [data]
    if not isinstance(data, list):
        raise ValueError("CSL-JSON must be an array of items or a single item object")
    # Skip non-object entries (a stray string or null) rather than crash the whole run.
    return [reference_from_csl(item) for item in data if isinstance(item, dict)]


def load_bibtex(path: str | Path) -> list[Reference]:
    text = Path(path).read_text(encoding="utf-8")
    refs = []
    for etype, key, fields in _iter_entries(text):
        if etype.lower() in ("comment", "string", "preamble"):
            continue
        author_field = fields.get("author", "")
        refs.append(
            Reference(
                key=key or fields.get("doi") or fields.get("title", "?"),
                title=_clean(fields.get("title", "")),
                authors=_parse_authors(author_field),
                year=_first_year(fields.get("year") or fields.get("date") or ""),
                doi=_clean(fields.get("doi")) or None,
                volume=_clean(fields.get("volume")) or None,
                first_page=first_page_of(_clean(fields.get("pages", ""))) or None,
                truncated=bool(re.search(r"\band\s+others\b", author_field, re.I)),
            )
        )
    return refs


_LATEX_LETTERS = {
    r"\o": "o", r"\O": "O", r"\l": "l", r"\L": "L", r"\i": "i", r"\j": "j",
    r"\aa": "a", r"\AA": "A", r"\ss": "ss", r"\ae": "ae", r"\AE": "AE",
    r"\oe": "oe", r"\OE": "OE",
}


def _delatex(s: str) -> str:
    """Reduce common LaTeX accents to their base letter so names normalize cleanly."""
    s = re.sub(r"\\[\"'`^~=.]\{?([A-Za-z])\}?", r"\1", s)  # \"u, \'{e}, \^o, ...
    s = re.sub(r"\\[a-zA-Z]+\{([A-Za-z])\}", r"\1", s)      # \c{c}, \v{s}, \u{g}, ...
    for command, letter in _LATEX_LETTERS.items():
        s = s.replace(command, letter)
    return s


def _clean(value: str | None) -> str:
    s = _delatex(value or "")
    return re.sub(r"\s+", " ", s.replace("{", "").replace("}", "")).strip()


def _first_year(value: str) -> int | None:
    m = re.search(r"\d{4}", value or "")
    return int(m.group(0)) if m else None


def _parse_authors(raw: str) -> list[str]:
    """BibTeX author field -> "Given Family" strings, the form the verifier expects."""
    out = []
    for part in re.split(r"\s+and\s+", _clean(raw)):
        part = part.strip()
        if not part or part.lower() == "others":  # "and others" is BibTeX for et al.
            continue
        if "," in part:
            last, first = part.split(",", 1)
            out.append(f"{first.strip()} {last.strip()}".strip())
        else:
            out.append(part)
    return out


def _iter_entries(text: str):
    """Yield (entry_type, citation_key, {field: value}) for each @entry in a .bib file."""
    for m in re.finditer(r"@(\w+)\s*\{", text):
        body = _balanced(text, m.end() - 1)
        if body is None:
            continue
        comma = body.find(",")
        if comma == -1:
            yield m.group(1), body.strip(), {}
            continue
        yield m.group(1), body[:comma].strip(), _parse_fields(body[comma + 1 :])


def _balanced(text: str, open_pos: int) -> str | None:
    """Substring inside the braces opened at open_pos, respecting nesting."""
    depth = 0
    for j in range(open_pos, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[open_pos + 1 : j]
    return None


def _parse_fields(s: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    i, n = 0, len(s)
    while i < n:
        while i < n and s[i] in " \t\r\n,":
            i += 1
        m = re.match(r"[A-Za-z][\w-]*", s[i:])
        if not m:
            break
        name = m.group(0).lower()
        i += m.end()
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i >= n or s[i] != "=":
            break
        i += 1
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i < n and s[i] == "{":
            val = _balanced(s, i) or ""
            i += len(val) + 2
        elif i < n and s[i] == '"':
            j = s.find('"', i + 1)
            j = n if j == -1 else j
            val = s[i + 1 : j]
            i = j + 1
        else:
            j = i
            while j < n and s[j] != ",":
                j += 1
            val = s[i:j].strip()
            i = j
        fields[name] = val
    return fields
