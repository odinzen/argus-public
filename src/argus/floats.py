"""Check that figure and table numbers are sequential and that references resolve.

Captions and the body that refers to them are maintained by hand far more often than
citations are, so they drift the same way and worse: a caption sequence that skips a
number (Table 1, 2, 4 after a table is cut), two captions sharing a number, a "Figure 9"
in the prose with only five figures, a figure that is captioned but never called out.
A reference manager renumbers citations; nothing renumbers floats, so this is the check
that has to catch them.

We read captions from line-leading "Figure 3." / "Table 1:" markers and references from
"Figure 3" / "Figs. 1-3" / "Tables 1 and 2" mentions elsewhere, then diff the two.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Keyword alternations per float kind, covering singular, plural, and abbreviated forms
# with an optional trailing period: Figure, Figures, Fig, Figs, Fig., Figs.. The full word
# is tried before the abbreviation so the longer form wins; the word boundary in the
# patterns keeps "fig" inside "configuration" from matching.
_KEYWORDS = {
    "figure": r"Figures?|Figs?\.?",
    "table": r"Tables?|Tabs?\.?",
}

_NUM = re.compile(r"\d{1,3}")
_RANGE_GAP = re.compile(r"-|–|—|\bto\b", re.IGNORECASE)


def _caption_re(kind: str) -> re.Pattern[str]:
    # A caption opens its line: "Figure 3. ..." or "Table 1: ...". The trailing . or :
    # separates a real caption from a sentence that merely starts with a reference
    # ("Figure 5 shows ..."). A leading markdown emphasis marker is allowed, since a
    # pandoc source writes captions bold or italic: "**Figure 1.** ...", "*Fig. 1. ...*".
    return re.compile(rf"(?m)^[ \t]*[*_]{{0,2}}[ \t]*\b({_KEYWORDS[kind]})\s*(\d{{1,3}})\s*[.:]")


def _mention_re(kind: str) -> re.Pattern[str]:
    # Any "Figure 3", "Figs. 1-3", "Tables 1 and 2" run, captions included; the caller
    # drops the ones whose position coincides with a caption. A possessive prefix marks a
    # float belonging to ANOTHER paper ("their table 2", "Fischer's table 3"), which this
    # document is not expected to caption, so those mentions are not collected.
    run = r"\d{1,3}(?:\s*(?:and|to|[-–—,&])\s*\d{1,3})*"
    return re.compile(rf"(?<!their )(?<!'s )(?<!’s )\b({_KEYWORDS[kind]})\s*({run})", re.IGNORECASE)


def _expand_run(run: str) -> list[int]:
    """Numbers named by a mention run: '1-3' -> [1,2,3], '1 and 3' -> [1,3]."""
    out: list[int] = []
    matches = list(_NUM.finditer(run))
    for i, m in enumerate(matches):
        n = int(m.group())
        if i > 0:
            gap = run[matches[i - 1].end() : m.start()]
            lo = int(matches[i - 1].group())
            if _RANGE_GAP.search(gap) and lo < n and n - lo < 100:
                out.extend(range(lo + 1, n))  # fill the range; n itself appended below
        out.append(n)
    return out


def find_captions(text: str, kind: str) -> list[int]:
    """Caption numbers in document order (duplicates kept, so they can be reported)."""
    return [int(m.group(2)) for m in _caption_re(kind).finditer(text or "")]


def find_float_references(text: str, kind: str) -> list[int]:
    """Distinct in-text reference numbers in first-appearance order, captions excluded."""
    caption_starts = {m.start(1) for m in _caption_re(kind).finditer(text or "")}
    seen: dict[int, None] = {}
    for m in _mention_re(kind).finditer(text or ""):
        if m.start(1) in caption_starts:
            continue  # this mention is the caption itself
        for n in _expand_run(m.group(2)):
            seen.setdefault(n, None)
    return list(seen)


@dataclass
class FloatNumbering:
    kind: str  # "figure" / "table"
    captions: list[int]  # caption numbers, document order
    referenced: list[int]  # distinct in-text references, first-appearance order
    missing_captions: list[int]  # referenced in the body but no caption (dangling)
    uncited: list[int]  # captioned but never referenced (warning, not a failure)
    gaps: list[int]  # numbers within 1..max absent from the captions
    duplicates: list[int]  # a number carried by more than one caption
    out_of_order: bool  # caption numbers do not ascend 1, 2, 3, ...

    @property
    def status(self) -> str:
        broken = (
            self.missing_captions or self.gaps or self.duplicates or self.out_of_order
        )
        return "ok" if not broken else "suspect"

    def issues(self) -> list[str]:
        noun = self.kind
        Noun = self.kind.title()
        out = []
        if self.gaps:
            out.append(f"{noun} numbering skips: " + ", ".join(map(str, self.gaps)))
        if self.duplicates:
            out.append(
                f"{noun} number on more than one caption: "
                + ", ".join(map(str, self.duplicates))
            )
        if self.out_of_order:
            out.append(
                f"{noun} captions are out of order: "
                + ", ".join(map(str, self.captions))
            )
        if self.missing_captions:
            out.append(
                "referenced in the text but never captioned: "
                + ", ".join(f"{Noun} {n}" for n in self.missing_captions)
            )
        return out

    def warnings(self) -> list[str]:
        if not self.uncited:
            return []
        Noun = self.kind.title()
        return [
            "captioned but never referenced in the text: "
            + ", ".join(f"{Noun} {n}" for n in self.uncited)
        ]


def check_floats(text: str, kind: str) -> FloatNumbering:
    """Diff a float's caption sequence against the body's references to it."""
    captions = find_captions(text, kind)
    referenced = find_float_references(text, kind)
    caption_set = set(captions)
    ref_set = set(referenced)

    unique = list(dict.fromkeys(captions))
    seen: set[int] = set()
    duplicates = sorted({n for n in captions if n in seen or seen.add(n)})
    gaps = [n for n in range(1, max(captions, default=0) + 1) if n not in caption_set]
    out_of_order = unique != sorted(unique)
    missing_captions = [n for n in referenced if n not in caption_set]
    uncited = [n for n in unique if n not in ref_set]

    return FloatNumbering(
        kind=kind,
        captions=captions,
        referenced=referenced,
        missing_captions=missing_captions,
        uncited=uncited,
        gaps=gaps,
        duplicates=duplicates,
        out_of_order=out_of_order,
    )
