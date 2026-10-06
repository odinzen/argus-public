"""Check that in-text citation numbers and the reference list agree, and stay in order.

A citation number is not data -- it is a projection of (document reading order) x (cited
works). When the in-text marker and the list are maintained by hand they drift: a body
that cites [22] over a list that stops at [18] (truncation), a list entry nobody cites
(orphan), a gap or a duplicate, or a list whose order no longer matches first appearance.
This recomputes the canonical numbering from first appearance and reports every
disagreement. ``renumber`` returns the old -> new map to apply through the reference
manager, never by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .anchors import Anchor

_LEAD_NUM = re.compile(r"(?m)^\s*[\[(]?(\d{1,3})[\]).]\s+")


def numbered_entries(section: str) -> list[int]:
    """The leading numbers of a numbered reference list, in listed order."""
    return [int(m.group(1)) for m in _LEAD_NUM.finditer(section or "")]


def first_appearance(anchors: list[Anchor]) -> list[int]:
    """Distinct citation numbers in order of first appearance in the body."""
    seen: dict[int, None] = {}
    for anchor in sorted(anchors, key=lambda a: a.position):
        for n in anchor.numbers:
            seen.setdefault(n, None)
    return list(seen)


@dataclass
class OrderingReport:
    cited: list[int]  # distinct in-text numbers, first-appearance order
    listed: list[int]  # reference-list numbers, in listed order
    missing_entries: list[int]  # cited in the body but absent from the list (truncation)
    orphans: list[int]  # in the list but never cited
    gaps: list[int]  # numbers within 1..max absent from the list
    duplicates: list[int]  # numbers listed more than once
    out_of_order: bool  # list order does not match first-appearance (citation) order
    remap: dict[int, int] = field(default_factory=dict)  # old printed number -> canonical

    @property
    def status(self) -> str:
        clean = not (
            self.missing_entries
            or self.orphans
            or self.gaps
            or self.duplicates
            or self.out_of_order
        )
        return "ok" if clean else "suspect"

    def issues(self) -> list[str]:
        out = []
        if self.missing_entries:
            out.append(
                "cited in the body but missing from the reference list: "
                + ", ".join(map(str, self.missing_entries))
            )
        if self.orphans:
            out.append("in the list but never cited: " + ", ".join(map(str, self.orphans)))
        if self.gaps:
            out.append("gaps in the numbering: " + ", ".join(map(str, self.gaps)))
        if self.duplicates:
            out.append("numbers listed more than once: " + ", ".join(map(str, self.duplicates)))
        if self.out_of_order:
            out.append("reference list is not in first-appearance (citation) order")
        return out


def check(anchors: list[Anchor], listed: list[int], ordered_list: bool = True) -> OrderingReport:
    """Diff in-text citation order against a numbered reference list.

    Set ``ordered_list`` False when the list numbers were inferred from entry count (a
    Word auto-numbered list carries no literal numbers, so its order cannot be diffed and
    only truncation, orphans, and coverage are assessable).
    """
    cited = first_appearance(anchors)
    cited_set, listed_set = set(cited), set(listed)

    missing_entries = [n for n in cited if n not in listed_set]
    orphans = [n for n in listed if n not in cited_set]

    seen: set[int] = set()
    duplicates = sorted({n for n in listed if n in seen or seen.add(n)})
    gaps = [n for n in range(1, max(listed, default=0) + 1) if n not in listed_set]

    # The list should run in first-appearance order. Compare only the numbers the two
    # sides share, so a truncation or an orphan does not also masquerade as mis-ordering.
    shared_cite_order = [n for n in cited if n in listed_set]
    shared_list_order = [n for n in listed if n in cited_set]
    out_of_order = ordered_list and (shared_cite_order != shared_list_order)

    remap = {old: i + 1 for i, old in enumerate(cited)}
    return OrderingReport(
        cited, listed, missing_entries, orphans, gaps, duplicates, out_of_order, remap
    )


def renumber(anchors: list[Anchor]) -> dict[int, int]:
    """Old printed number -> canonical number, assigned by order of first appearance."""
    return {old: i + 1 for i, old in enumerate(first_appearance(anchors))}
