"""Best-effort audit of a free-text reference list (from a PDF or Word manuscript).

Unlike the structured path (CSL-JSON/BibTeX), a manuscript gives only text, so this
module isolates the reference section, splits it into entries, and leaves the Crossref
*bibliographic* lookup to the caller. `verdict` then judges how well an entry matches
the record Crossref returned. This is assistive, not exact: it surfaces references with
no confident match (a possible hallucination) and probable author mismatches, for a
person to check. It does not assume intent.
"""

from __future__ import annotations

import re

from .verify import _norm, _surname

# Allow an optional markdown heading marker (## References) or bold (**References**), so
# the split works on pandoc markdown sources as well as flat .docx text.
# Heading padding must stay unambiguous: never \s* (it matches newlines), and never
# stacked optional whitespace runs (three adjacent [ \t]* groups still backtrack
# combinatorially on the 4k-space runs real .docx extractions carry, which hung the
# CLI for good). Each optional marker group therefore REQUIRES its marker, so a
# whitespace run has exactly one way to match and failure stays linear.
_HEADING = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:\*{1,2}[ \t]*)?"
    r"(?:(?:supplementary|supporting)[ \t]+)?"  # a supplement's own list
    r"(references|bibliography|works cited|literature cited)[ \t]*\*{0,2}[ \t]*:?[ \t]*$"
)
_STOP = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:\*{1,2}[ \t]*)?"
    r"(appendix|supplement\w*|supporting information|acknowledg\w*)\b"
)
_LEAD_NUM = re.compile(r"^[\[(]?\d{1,3}[\]).]\s+")
_NUM_LINE = re.compile(r"(?m)^\s*[\[(]?\d{1,3}[\]).]\s+")

# The Introduction heading, allowing a section number and markdown/bold markers:
# "Introduction", "1. Introduction", "## 1 Introduction", "**1. Introduction**".
_INTRO = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:\*{1,2}[ \t]*)?(?:\d+\.?[ \t]*)?introduction\b"
)


def main_text_start(text: str) -> int:
    """Character offset where the numbered main text begins (the Introduction heading).

    Citation numbering starts at the first main-text mention, so everything before the
    Introduction -- title, authors, abstract, keywords -- is front matter that carries no
    number. Returns 0 when no Introduction heading is found, leaving the whole text in
    scope (the manuscript may be a fragment, or use a different opening section).
    """
    m = _INTRO.search(text or "")
    return m.start() if m else 0


def references_section(text: str) -> str:
    """Text of the reference list: from the last References-style heading to the end
    (or to the next appendix/acknowledgements heading). Falls back to the whole text."""
    heads = list(_HEADING.finditer(text))
    if not heads:
        return text
    rest = text[heads[-1].end():]
    stop = _STOP.search(rest)
    return rest[: stop.start()] if stop else rest


def split_entries(section: str) -> list[str]:
    """Split a reference section into individual entries, numbered list or one-per-line."""
    marks = list(_NUM_LINE.finditer(section))
    if len(marks) >= 3:
        bounds = [m.start() for m in marks] + [len(section)]
        parts = [section[bounds[i]: bounds[i + 1]] for i in range(len(bounds) - 1)]
    else:
        parts = re.split(r"\n\s*\n", section)
        if len(parts) < 3:
            parts = section.split("\n")
    entries = []
    for part in parts:
        entry = _LEAD_NUM.sub("", re.sub(r"\s+", " ", part).strip())
        if len(entry) >= 25:
            entries.append(entry)
    return entries


# Low-signal words (>3 chars, so not already filtered) that coincide across unrelated
# titles; ignoring them keeps the match resting on distinctive words.
_STOPWORDS = frozenset(
    """about above after again against among based between beyond both does during from
    have here into more near over says than that their them then these this those through
    toward towards under used using what when where which while with within without exist
    also your been were""".split()
)


def _title_overlap(entry: str, record_title: str) -> float:
    words = set(_norm(entry).split())
    title_words = {
        w for w in _norm(record_title).split() if len(w) > 3 and w not in _STOPWORDS
    }
    if not title_words:
        return 0.0
    return sum(1 for w in title_words if w in words) / len(title_words)


def verdict(entry: str, record_title: str, record_authors: list[str]) -> str:
    """How well a reference entry matches the Crossref record returned for it.

    "match"    title clearly present and the first author appears in the entry;
    "check"    title matches but the record's first author is not found in the entry
               (possible conflation or a noisy extraction) -- look closer;
    "no-match" no confident Crossref match -- a possible hallucination or noisy extraction.
    """
    if _title_overlap(entry, record_title) < 0.6:
        return "no-match"
    if record_authors:
        first = _surname(record_authors[0])
        if first and first not in _norm(entry).split():
            return "check"
    return "match"
