"""Cross-reference resolvability: a "Section 4.3" or "Table S3" that points at nothing.

A reference manager keeps citation numbers honest; nothing keeps a section or supplementary
pointer honest, so "see Section 4.3" survives a reorganization that removed 4.3. This checks
the two that can be checked cleanly and skips the ones that cannot.

Section references are resolved against the document's numbered headings. When the headings
carry no numbers (a draft using "## Methods", not "## 3 Methods"), section-number references
cannot be resolved and the check says so rather than guessing. Supplementary floats
("Table S3", "Fig. S2") live in a separate file, so they are listed as an inventory to
confirm against the SI, not failed. Equation-number resolution is deliberately left out: a
display equation's label is too hard to find without false positives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "Section 3.2", "Sec. 4", "Sections 3 and 4". Captures each dotted number after the word.
# A possessive prefix ("their section 4.2.3", "Fischer's section 2") names another paper's
# section, which this document's headings cannot resolve, so those are not collected.
_SECTION_REF = re.compile(
    r"(?<!their )(?<!'s )(?<!’s )\b(?:Sections?|Secs?\.?)\s+(\d+(?:\.\d+)*)", re.IGNORECASE
)
_ALSO_NUM = re.compile(r"\band\s+(\d+(?:\.\d+)*)")

# A numbered heading line: optional #/bold, then a dotted number, then a title word. A
# numbered list item ("1. First") also matches, which only makes the check more permissive
# (a section reference resolves), never a false failure.
_HEADING_NUM = re.compile(r"(?im)^[ \t]*#{0,6}[ \t]*\*{0,2}[ \t]*(\d+(?:\.\d+)*)\.?[ \t]+\S")

# Supplementary floats: "Table S3", "Figure S1", "Fig. S2", "Eq. S4".
_SI_FLOAT = re.compile(
    r"\b(Table|Figure|Fig|Eq|Equation)s?\.?\s*(S\d+)", re.IGNORECASE
)


@dataclass
class CrossrefReport:
    heading_numbers: set[str] = field(default_factory=set)
    section_refs: list[str] = field(default_factory=list)
    dangling_sections: list[str] = field(default_factory=list)
    si_floats: list[str] = field(default_factory=list)
    headings_numbered: bool = True

    @property
    def status(self) -> str:
        return "suspect" if self.dangling_sections else "ok"


def _section_refs(body: str) -> list[str]:
    out: list[str] = []
    for m in _SECTION_REF.finditer(body):
        out.append(m.group(1))
        # Pick up "Sections 3 and 4": the trailing "and N" right after the match.
        tail = body[m.end() : m.end() + 12]
        also = _ALSO_NUM.match(tail.lstrip())
        if also:
            out.append(also.group(1))
    return out


def check_crossrefs(full_text: str, body: str) -> CrossrefReport:
    headings = {m.group(1) for m in _HEADING_NUM.finditer(full_text)}
    refs = _section_refs(body)
    si = sorted(
        {f"{m.group(1).title()} {m.group(2).upper()}" for m in _SI_FLOAT.finditer(body)}
    )
    report = CrossrefReport(
        heading_numbers=headings,
        section_refs=refs,
        si_floats=si,
        headings_numbered=bool(headings),
    )
    if headings:
        # A reference resolves if its exact number heads a section, or a parent does
        # (a "Section 4.3" reference is satisfied by a "4.3" heading; "4" alone is not).
        report.dangling_sections = [r for r in refs if r not in headings]
    return report
