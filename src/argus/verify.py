"""Verify a reference against its Crossref record.

The check that matters is the FULL author list, not just the first author. A
distorted citation usually keeps the right first author, title, and year and swaps
the co-authors: a real paper wearing another's byline. A DOI-resolves or
first-author check passes that; a full-list diff catches it.

Beyond the author set we also compare initials (a wrong initial on a correct
surname), the title, the year, the volume, and the first page, the same fields a
careful manual check would diff against the resolved record.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class Reference:
    key: str
    title: str
    authors: list[str]
    year: int | None = None
    doi: str | None = None
    volume: str | None = None
    first_page: str | None = None
    truncated: bool = False  # citation ends in "et al." -> omitted tail is not a drop


@dataclass
class CrossrefRecord:
    title: str
    authors: list[str]  # "Given Family" where given is known, else family alone
    year: int | None = None
    volume: str | None = None
    first_page: str | None = None


@dataclass
class Finding:
    key: str
    status: str  # "ok" or "suspect"
    issues: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    # Strip the HTML/MathML Crossref ships in titles (<sub>7</sub>, <i>) BEFORE
    # normalizing. Without this the tags fold to "sub"/"i" word tokens and a
    # formula title (Li7La3Zr2O12) reads as different from the same title typed
    # as plain text -- the false-positive that flags every subscripted formula.
    tagless = _TAG.sub(" ", s or "")
    # Fold accents (Müller -> muller) so the citation and the record normalize alike.
    folded = unicodedata.normalize("NFKD", tagless)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", folded.lower())).strip()


def _surname(author: str) -> str:
    toks = _norm(author).split()
    return toks[-1] if toks else ""


def _initial(author: str) -> str:
    """Leading given-name initial, or "" if only a surname is present."""
    toks = _norm(author).split()
    return toks[0][0] if len(toks) >= 2 and toks[0] else ""


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


_TAG = re.compile(r"<[^>]+>")


def _plain(s: str) -> str:
    """Strip the HTML/MathML tags Crossref ships in titles (<sub>, <i>, ...) for display."""
    return re.sub(r"\s+", " ", _TAG.sub("", s or "")).strip()


def _norm_volume(v: str | None) -> str:
    return re.sub(r"\s+", "", str(v).strip().lower()) if v else ""


def first_page_of(page: str | None) -> str:
    """First page of a range like '1024-1027' (handles -, en/em dash)."""
    if not page:
        return ""
    return re.split(r"[-‒–—]", str(page))[0].strip()


_ET_AL = {"et al", "et alii", "and others", "others"}


def _is_et_al(author: str) -> bool:
    """True for an 'et al.' / CSL 'others' truncation sentinel, not a real name."""
    return _norm(author) in _ET_AL


def author_list_diff(stored: list[str], crossref: list[str], truncated: bool = False) -> list[str]:
    """Mismatches between two author lists, by surname and initial.

    Surnames match on equality or >=0.85 similarity, so romanization and minor
    spelling differences do not false-positive. When a surname matches, the leading
    initials are compared too, so a wrong initial on a correct surname is caught;
    a missing initial on either side is not held against the citation.

    ``truncated`` (or an "et al." / CSL "others" sentinel found inside the list)
    marks an intentional truncation, so the dropped-author check is skipped. The
    conflation and wrong-initial checks still run -- truncation excuses an omitted
    tail, never a wrong or borrowed author.
    """
    truncated = truncated or any(_is_et_al(a) for a in (stored or []))
    cited = [a for a in (stored or []) if _surname(a) and not _is_et_al(a)]
    record = [a for a in (crossref or []) if _surname(a)]
    if not cited or not record:
        return []

    rec_surnames = [_surname(a) for a in record]

    def matches(name: str, other: str) -> bool:
        return name == other or _similar(name, other) >= 0.85

    issues = []
    wrong = [a for a in cited if not any(matches(_surname(a), r) for r in rec_surnames)]
    if wrong:
        issues.append("cited authors not on the record: " + ", ".join(_surname(a) for a in wrong))

    # Only look for dropped authors when the citation appears to list the full set.
    # A short "et al." citation legitimately omits authors, so flagging those would be
    # noise; a citation that lists nearly everyone but one is the suspicious case.
    cited_surnames = [_surname(a) for a in cited]
    looks_complete = (
        len(cited_surnames) >= len(rec_surnames) - 2
        or len(cited_surnames) >= 0.7 * len(rec_surnames)
    )
    if looks_complete and not truncated:
        dropped = [r for r in rec_surnames if not any(matches(r, c) for c in cited_surnames)]
        if dropped:
            issues.append("record authors missing from the citation: " + ", ".join(dropped))

    for a in cited:
        ci = _initial(a)
        if not ci:
            continue
        rec_inits = [
            _initial(r) for r in record if matches(_surname(a), _surname(r)) and _initial(r)
        ]
        if rec_inits and ci not in rec_inits:
            issues.append(
                f"author initials differ for {_surname(a)}: cited {ci.upper()}, "
                f"record {'/'.join(i.upper() for i in dict.fromkeys(rec_inits))}"
            )

    return issues


def verify(ref: Reference, record: CrossrefRecord, title_threshold: float = 0.9) -> Finding:
    issues = []
    if _similar(_norm(ref.title), _norm(record.title)) < title_threshold:
        issues.append(f'title differs from the record: "{_plain(record.title)}"')
    if ref.year and record.year and abs(ref.year - record.year) > 1:
        issues.append(f"year differs: cited {ref.year}, record {record.year}")
    if ref.volume and record.volume and _norm_volume(ref.volume) != _norm_volume(record.volume):
        issues.append(f"volume differs: cited {ref.volume}, record {record.volume}")
    if (
        ref.first_page
        and record.first_page
        and first_page_of(ref.first_page) != first_page_of(record.first_page)
    ):
        issues.append(f"first page differs: cited {ref.first_page}, record {record.first_page}")
    issues += author_list_diff(ref.authors, record.authors, truncated=ref.truncated)
    return Finding(ref.key, "ok" if not issues else "suspect", issues)
