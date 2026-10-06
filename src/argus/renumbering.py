"""Renumber a manuscript's citations into first-appearance order, counting from the
Introduction.

An abstract is front matter. Normally it carries no numbered citations at all, and even
when it does, those markers must not drive the numbering -- Vancouver numbers a reference
by where it is first cited in the main text. So the count starts at the Introduction, and
a reference first named in the abstract takes the number of its first main-text mention.

This computes that numbering from `main_text_start` onward, then applies it: every in-text
`[n]` (the abstract included, so its markers point at the right renumbered entries) is
remapped, and the reference list is reordered and relabelled 1..N to match. The reference
*text* is never touched, only its number and position, so it is safe on a hand-numbered
markdown source where there is no reference manager to regenerate the list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .anchors import _BRACKET, _expand, find_numeric_anchors
from .audit import main_text_start, references_section
from .ordering import first_appearance

# A reference-list entry line: leading [n], then the reference text. One entry per line,
# which is how a --wrap=none pandoc markdown bibliography is written.
_ENTRY = re.compile(r"^(\s*)\[(\d{1,3})\]\s+(.*\S)\s*$")


def _collapse(nums: list[int]) -> str:
    """Sorted, de-duplicated numbers as a citation run, runs of 3+ folded to `lo-hi`."""
    nums = sorted(set(nums))
    out: list[str] = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        if j - i >= 2:
            out.append(f"{nums[i]}-{nums[j]}")
        else:
            out.extend(str(n) for n in nums[i : j + 1])
        i = j + 1
    return ",".join(out)


@dataclass
class RenumberResult:
    text: str  # the renumbered manuscript
    remap: dict[int, int]  # old printed number -> new (first-appearance) number
    warnings: list[str] = field(default_factory=list)
    changed: bool = False


def renumber_markdown(text: str) -> RenumberResult:
    """Renumber citations to first main-text appearance and reorder the reference list."""
    start = main_text_start(text)
    section = references_section(text)
    has_refs = bool(section) and section in text and section != text
    ref_start = text.find(section) if has_refs else len(text)

    body = text[start:ref_start]
    order = first_appearance(find_numeric_anchors(body))
    remap = {old: i + 1 for i, old in enumerate(order)}

    warnings: list[str] = []
    # A number cited before the Introduction but never in the main text has no place in
    # the count. Flag it rather than silently leaving it unmapped.
    front = {n for a in find_numeric_anchors(text[:start]) for n in a.numbers}
    for n in sorted(front - set(order)):
        warnings.append(f"[{n}] is cited only before the Introduction; it gets no number")

    def _remap_run(m: re.Match[str]) -> str:
        return "[" + _collapse([remap.get(n, n) for n in _expand(m.group(1))]) + "]"

    head = _BRACKET.sub(_remap_run, text[:ref_start])
    tail, tail_warnings = _renumber_reflist(text[ref_start:], remap)
    warnings += tail_warnings

    new_text = head + tail
    return RenumberResult(new_text, remap, warnings, changed=new_text != text)


def _renumber_reflist(tail: str, remap: dict[int, int]) -> tuple[str, list[str]]:
    """Reorder the reference entries by new number and relabel them, in place."""
    lines = tail.split("\n")
    slots = [i for i, ln in enumerate(lines) if _ENTRY.match(ln)]
    entries = [_ENTRY.match(lines[i]) for i in slots]

    warnings: list[str] = []
    listed = [int(m.group(2)) for m in entries]
    unmapped = [n for n in listed if n not in remap]
    if unmapped:
        warnings.append(
            "listed but never cited in the main text: " + ", ".join(map(str, unmapped))
        )

    # Order the entries by their new number; an uncited entry keeps its old number so it
    # sorts after the cited set rather than colliding at the front.
    ordered = sorted(entries, key=lambda m: remap.get(int(m.group(2)), int(m.group(2))))
    for slot, m in zip(slots, ordered, strict=True):
        old = int(m.group(2))
        lines[slot] = f"{m.group(1)}[{remap.get(old, old)}] {m.group(3)}"
    return "\n".join(lines), warnings
