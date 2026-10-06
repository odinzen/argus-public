"""Flag running-text paragraphs whose formatting drifts from the body's majority.

Editing or inserting paragraphs in a word processor (or through python-docx) silently
drops their size, line spacing, paragraph spacing and alignment, so a paragraph pasted
into the middle of a manuscript renders single-spaced and ragged amid justified 1.5-spaced
body text while reading identically in the source. A reference manager renumbers
citations and nothing renumbers floats; likewise nothing re-applies paragraph formatting,
so this is the check that catches the drift the eye eventually does but the author does
not, one paragraph at a time, on a full read.

The approach is deliberately value-free. We do not know a journal's house size or spacing,
so we take the body's own dominant signature (size, spacing-after, line rule, alignment)
as the standard and report the paragraphs that depart from it. Only substantial running
paragraphs are compared; headings, captions and short front-matter lines are their own
shapes and are left out of the body vote.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

_PARA = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_PPR = re.compile(r"<w:pPr\b.*?</w:pPr>", re.DOTALL)
_SZ = re.compile(r'<w:sz\s+w:val="(\d+)"')
_JC = re.compile(r'<w:jc\s+w:val="([^"]+)"')
_SPACING = re.compile(r"<w:spacing\b([^/>]*)/?>")
_ATTR = re.compile(r'w:(after|before|line|lineRule)="([^"]+)"')
_PSTYLE = re.compile(r'<w:pStyle\s+w:val="([^"]+)"')
_CAPTION = re.compile(r"^\s*[*_]{0,2}\s*(Figures?|Figs?\.?|Tables?|Tabs?\.?)\s*\d", re.I)
_REF_HEADING = re.compile(
    r"^[*_#\s]*(?:(?:supplementary|supporting)\s+)?"
    r"(references|bibliography|references cited|literature cited|works cited)"
    r"[*_\s]*$",
    re.I,
)

_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}

# A paragraph shorter than this is a heading, caption, byline or list item, not a run of
# body prose, so it does not join the body vote. Deliberately generous: real body
# paragraphs run well past this, and a stray short one only means it is not compared.
PROSE_MIN_CHARS = 180

# A distinct format shared by this many paragraphs reads as a deliberate secondary style
# (10pt back matter, a boxed note); held by fewer, it is more likely a stray paragraph.
COHERENT_MIN = 2


def _unescape(s: str) -> str:
    for entity, char in _ENTITIES.items():
        s = s.replace(entity, char)
    return s


@dataclass(frozen=True)
class Signature:
    size_halfpt: str | None  # w:sz value (half-points); None = inherited
    after: str | None  # w:spacing w:after (twips); None = inherited
    line: str | None  # w:spacing w:line + rule collapsed; None = single/inherited
    align: str  # justify / left / center / right (left when unset)

    def describe(self) -> str:
        size = f"{int(self.size_halfpt) / 2:g}pt" if self.size_halfpt else "inherited size"
        line = _line_label(self.line)
        after = f"{self.after} after" if self.after else "no space after"
        return f"{size}, {line}, {after}, {self.align}"

    def diff(self, other: Signature) -> list[str]:
        out = []
        if self.size_halfpt != other.size_halfpt:
            out.append(f"size {_pt(other.size_halfpt)} (body is {_pt(self.size_halfpt)})")
        if self.line != other.line:
            out.append(f"{_line_label(other.line)} (body is {_line_label(self.line)})")
        if self.after != other.after:
            a = other.after or "none"
            out.append(f"space-after {a} (body is {self.after or 'none'})")
        if self.align != other.align:
            out.append(f"{other.align} (body is {self.align})")
        return out


def _pt(halfpt: str | None) -> str:
    return f"{int(halfpt) / 2:g}pt" if halfpt else "inherited"


def _line_label(line: str | None) -> str:
    if not line:
        return "single spacing"
    # "auto:360" -> 1.5 lines (240 == single); "exact:280" -> fixed height
    rule, _, val = line.partition(":")
    if rule == "auto" and val.isdigit():
        return f"{int(val) / 240:g}x line spacing"
    return f"line {line}"


@dataclass
class Paragraph:
    text: str
    signature: Signature
    style: str | None


def _signature(block: str) -> Signature:
    ppr_match = _PPR.search(block)
    ppr = ppr_match.group(0) if ppr_match else ""

    size = _SZ.search(block)
    jc = _JC.search(ppr)
    align = jc.group(1) if jc else "left"
    if align == "both":
        align = "justify"

    after = line = None
    sp = _SPACING.search(ppr)
    if sp:
        attrs = dict(_ATTR.findall(sp.group(1)))
        after = attrs.get("after")
        if "line" in attrs:
            line = f"{attrs.get('lineRule', 'auto')}:{attrs['line']}"

    return Signature(
        size_halfpt=size.group(1) if size else None,
        after=after,
        line=line,
        align=align,
    )


def extract_paragraphs(document_xml: str) -> list[Paragraph]:
    """Body paragraphs in order, cut at the reference list (its entries are not prose)."""
    out = []
    for block in _PARA.findall(document_xml):
        # visible text: strip the pPr (its child vals are not text) then all tags
        body = _PPR.sub("", block)
        text = _unescape(_TAG.sub("", body)).strip()
        if _REF_HEADING.match(text):
            break  # everything from the References heading on is bibliography, not body
        style = _PSTYLE.search(block)
        out.append(Paragraph(text, _signature(block), style.group(1) if style else None))
    return out


@dataclass
class OutlierGroup:
    differences: list[str]  # how this signature departs from the body majority
    samples: list[str]  # paragraph texts sharing this signature
    count: int  # how many paragraphs share it
    drift: bool  # missing formatting the body has (a lost-formatting paragraph)

    def line(self) -> str:
        snip = self.samples[0][:56] + ("..." if len(self.samples[0]) > 56 else "")
        head = f"{self.count} paragraphs" if self.count > 1 else "1 paragraph"
        return f'{head}: {"; ".join(self.differences)}\n      e.g. "{snip}"'


@dataclass
class FormattingReport:
    prose_count: int
    majority: Signature | None
    groups: list[OutlierGroup]

    @property
    def drift_groups(self) -> list[OutlierGroup]:
        # a real problem: either lost formatting, or a lone paragraph set off on its own
        return [g for g in self.groups if g.drift or g.count < COHERENT_MIN]

    @property
    def style_groups(self) -> list[OutlierGroup]:
        # a coherent, explicitly-set secondary format: a deliberate style, reported only
        return [g for g in self.groups if not g.drift and g.count >= COHERENT_MIN]

    @property
    def status(self) -> str:
        return "suspect" if self.drift_groups else "ok"

    def issues(self) -> list[str]:
        return [g.line() for g in self.drift_groups]

    def notes(self) -> list[str]:
        return [g.line() for g in self.style_groups]


def _is_prose(p: Paragraph) -> bool:
    if len(p.text) < PROSE_MIN_CHARS:
        return False
    if _CAPTION.match(p.text):
        return False
    if p.style and re.search(r"heading|title|caption", p.style, re.I):
        return False
    return True


def check_formatting(document_xml: str) -> FormattingReport:
    """Compare body-prose paragraphs against their own dominant formatting signature."""
    prose = [p for p in extract_paragraphs(document_xml) if _is_prose(p)]
    if len(prose) < 3:
        return FormattingReport(prose_count=len(prose), majority=None, groups=[])

    counts = Counter(p.signature for p in prose)
    majority, _ = counts.most_common(1)[0]

    by_sig: dict[Signature, list[str]] = {}
    for p in prose:
        if p.signature != majority:
            by_sig.setdefault(p.signature, []).append(p.text)

    groups = [
        OutlierGroup(
            differences=majority.diff(sig),
            samples=texts,
            count=len(texts),
            drift=_is_drift(majority, sig),
        )
        for sig, texts in by_sig.items()
    ]
    groups.sort(key=lambda g: (not g.drift, -g.count))  # drift first
    return FormattingReport(prose_count=len(prose), majority=majority, groups=groups)


def _is_drift(majority: Signature, sig: Signature) -> bool:
    """A paragraph that is MISSING formatting the body has, not one set differently.

    A lost-formatting paragraph inherits size, drops its spacing, and falls back to the
    default alignment, so its signature is None where the body's is set. A deliberate
    secondary style (10pt back matter) sets those properties to different values, so it
    is not None. Missing beats different: the first is a bug, the second is a choice.
    """
    for mine, theirs in (
        (majority.size_halfpt, sig.size_halfpt),
        (majority.after, sig.after),
        (majority.line, sig.line),
    ):
        if mine is not None and theirs is None:
            return True
    return False
