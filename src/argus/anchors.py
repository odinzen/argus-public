"""Extract in-text citation markers and their positions.

Numbering correctness needs to know where each citation occurs, which the reference-list
path discards. We read numeric markers ([12], [3, 5], [4-6]) with their position in the
body, and -- for Word manuscripts authored through Zotero -- count the field codes that
carry a managed citation. A body with numeric markers but no field codes behind them is
fully unmanaged, the exact state that lets in-text numbers and the list drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A bracketed run of citation numbers: [12], [3, 5], [4-6], [3, 5-7]. Ranges and lists
# are expanded to the individual numbers they stand for.
_BRACKET = re.compile(r"\[(\d{1,3}(?:\s*[–—,-]\s*\d{1,3})*)\]")
_RANGE = re.compile(r"(\d{1,3})\s*[–—-]\s*(\d{1,3})")
_ZOTERO_FIELD = re.compile(r"ZOTERO_ITEM\s+CSL_CITATION", re.IGNORECASE)


@dataclass
class Anchor:
    position: int
    numbers: list[int]


def _expand(run: str) -> list[int]:
    numbers: list[int] = []
    for token in run.split(","):
        token = token.strip()
        if not token:
            continue
        m = _RANGE.fullmatch(token)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo <= hi and hi - lo < 100:
                numbers.extend(range(lo, hi + 1))
        elif token.isdigit():
            numbers.append(int(token))
    return numbers


def find_numeric_anchors(text: str) -> list[Anchor]:
    """Bracketed citation markers in reading order, each with its character position."""
    anchors = []
    for m in _BRACKET.finditer(text or ""):
        numbers = _expand(m.group(1))
        if numbers:
            anchors.append(Anchor(m.start(), numbers))
    return anchors


def field_citation_count(document_xml: str) -> int:
    """Number of Zotero CSL field codes in a Word document.xml (the managed-citation count)."""
    return len(_ZOTERO_FIELD.findall(document_xml or ""))
