"""The machine-checkable slice of a standing editorial checklist.

The checklist comes from editorial review of past manuscripts. Most of it is judgment (split
a 40-word sentence, cut an illustrative figure, expand the CALPHAD sections) and stays a
human pass.
The rest are literal string rules that drift back into every draft, and those are here: the
banned phrasings and their replacements, the em-dash and colon habit, "et al." kept intact,
American spelling, no "in preparation" citations, and no degC/K mixed in one sentence.

Firm rules gate (error): an em-dash separator, "and co-workers" for "et al.", and an "in
preparation" citation. Preference swaps and spelling are warnings, confirmed before
applying, since a curated phrase can occur legitimately. The reference list is excluded,
its wording is Zotero-managed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import audit


@dataclass
class KIssue:
    line: int
    kind: str
    token: str
    suggestion: str
    snippet: str
    severity: str  # error | warning


# Banned phrasing -> replacement, straight from the checklist. All warnings: each can, in
# principle, be a legitimate use, so a human confirms. Ordered so a longer phrase is tried
# before the shorter one it contains ("grid resolution" before "grid").
_PHRASES: list[tuple[str, str]] = [
    ("very consistent with", "in good agreement with"),
    ("very similar to", "in good agreement with / consistent with"),
    ("grid resolution", "step size of the search"),
    ("highest leverage target", "most effective target"),
    ("richer experimental dataset", "more extensive experimental dataset"),
    ("nucleation treatment", "nucleation promoter"),
    ("duty cycle minimum", "minimum operating temperature"),
    ("the same workflow predicts", "the present model predicts"),
    ("this work", "the present work / the present assessment"),
    ("deployments", "systems / installations"),
]

# "compute" in a CALPHAD paper should be "calculate". Warned, not gated, because a paper
# that genuinely computes (a runtime, a hardware cost) may want the word.
_COMPUTE = re.compile(r"\bcomput(e|es|ed|ing|ation|ational)\b", re.IGNORECASE)

# Spelling: (American, British) pairs. The target variant decides which side is flagged;
# with no journal given, the default is American, so British forms are flagged.
_SPELLING: list[tuple[str, str]] = [
    ("optimization", "optimisation"),
    ("optimize", "optimise"),
    ("digitizing", "digitising"),
    ("digitize", "digitise"),
    ("analyze", "analyse"),
    ("behavior", "behaviour"),
    ("color", "colour"),
    ("modeling", "modelling"),
    ("labeled", "labelled"),
    ("characterize", "characterise"),
    ("minimize", "minimise"),
    ("maximize", "maximise"),
    ("utilize", "utilise"),
    ("organization", "organisation"),
]

# An em-dash used as a separator: a real em/en dash, or the pandoc "--" between spaces.
_EMDASH = re.compile(r"—|–| -- ")
# A collapsed numeric citation range ("[13–15]", "[2, 5–7]"). Elsevier numeric styles print
# consecutive references this way, so its en dash is not a clause separator.
_CITE_RANGE = re.compile(r"\[\d{1,3}(?:\s*[,–-]\s*\d{1,3})*\]")
# "et al." expanded, which the checklist forbids.
_ETAL_EXPANDED = re.compile(r"\band co-?workers\b|\band colleagues\b", re.IGNORECASE)
# A companion study cited as unpublished.
_IN_PREP = re.compile(r"\bin prep(aration)?\b", re.IGNORECASE)
# Sentence-initial "But"/"And".
_SENT_INITIAL = re.compile(r"(?:^|(?<=[.!?]\s))\s*(But|And)\b")

_DEGC = re.compile(r"\d\s*(?:°\s*C|degC|deg\s*C)\b", re.IGNORECASE)
_KELVIN = re.compile(r"\d\s*K\b")


def _snippet(line: str, start: int, end: int, pad: int = 16) -> str:
    return line[max(0, start - pad) : end + pad].strip()


def _phrase_issues(lines: list[str]) -> list[KIssue]:
    out: list[KIssue] = []
    for i, line in enumerate(lines, 1):
        for phrase, repl in _PHRASES:
            for m in re.finditer(rf"\b{re.escape(phrase)}\b", line, re.IGNORECASE):
                snip = _snippet(line, *m.span())
                out.append(KIssue(i, "banned-phrase", m.group(), repl, snip, "warning"))
        for m in _COMPUTE.finditer(line):
            repl = m.group().replace("omput", "alculat").replace("mput", "alculat")
            snip = _snippet(line, *m.span())
            out.append(KIssue(i, "compute->calculate", m.group(), repl, snip, "warning"))
    return out


def _spelling_issues(lines: list[str], variant: str) -> list[KIssue]:
    out: list[KIssue] = []
    kind = f"spelling-{variant.lower()}"
    for i, line in enumerate(lines, 1):
        for american, british in _SPELLING:
            wrong, right = (british, american) if variant == "American" else (american, british)
            for m in re.finditer(rf"\b{re.escape(wrong)}\w*", line, re.IGNORECASE):
                # Suggest the target form, carrying any suffix (optimisation -> optimization).
                fixed = right + m.group()[len(wrong) :]
                out.append(KIssue(i, kind, m.group(), fixed, _snippet(line, *m.span()), "warning"))
    return out


def _rule_issues(lines: list[str]) -> list[KIssue]:
    out: list[KIssue] = []
    for i, line in enumerate(lines, 1):
        ranges = [c.span() for c in _CITE_RANGE.finditer(line)]
        for m in _EMDASH.finditer(line):
            if m.group() == "–" and any(a < m.start() < b for a, b in ranges):
                continue
            out.append(
                KIssue(
                    i,
                    "em-dash",
                    "em/en dash",  # ASCII label; the raw glyph shows in the snippet
                    "comma, parentheses, or a new sentence",
                    _snippet(line, *m.span()),
                    "error",
                )
            )
        for m in _ETAL_EXPANDED.finditer(line):
            snip = _snippet(line, *m.span())
            out.append(KIssue(i, "et-al-expanded", m.group(), "keep 'et al.'", snip, "error"))
        for m in _IN_PREP.finditer(line):
            out.append(
                KIssue(
                    i,
                    "in-preparation",
                    m.group(),
                    "no 'in preparation' companion citations",
                    _snippet(line, *m.span()),
                    "error",
                )
            )
        for m in _SENT_INITIAL.finditer(line):
            out.append(
                KIssue(
                    i,
                    "sentence-initial",
                    m.group(1),
                    "recast without a leading 'But'/'And'",
                    _snippet(line, m.start(1), m.end(1)),
                    "warning",
                )
            )
        if _DEGC.search(line) and _KELVIN.search(line):
            out.append(
                KIssue(
                    i,
                    "unit-mix",
                    "degC + K",
                    "one temperature unit per sentence (K only in rate columns)",
                    line.strip()[:60],
                    "warning",
                )
            )
    return out


def _long_sentences(text: str, limit: int = 40) -> list[KIssue]:
    """Sentences over ~limit words. Line is approximate (the sentence's first line)."""
    out: list[KIssue] = []
    offset_line = _line_index(text)
    for m in re.finditer(r"[^.!?\n]+[.!?]", text):
        words = len(m.group().split())
        if words > limit:
            out.append(
                KIssue(
                    offset_line(m.start()),
                    "long-sentence",
                    f"{words} words",
                    "split into two sentences",
                    m.group().strip()[:60],
                    "warning",
                )
            )
    return out


def _line_index(text: str):
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)

    def at(pos: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    return at


@dataclass
class EditorialReport:
    issues: list[KIssue] = field(default_factory=list)
    variant: str = "American"

    @property
    def errors(self) -> list[KIssue]:
        return [x for x in self.issues if x.severity == "error"]

    @property
    def warnings(self) -> list[KIssue]:
        return [x for x in self.issues if x.severity == "warning"]

    @property
    def status(self) -> str:
        return "suspect" if self.errors else "ok"


def _body(text: str) -> str:
    """Everything before the reference list; the prose rules are body-only."""
    section = audit.references_section(text)
    if section and section in text and section != text:
        return text[: text.find(section)]
    return text


def check_editorial(text: str, journal_variant: str | None = None) -> EditorialReport:
    variant = journal_variant or "American"
    body = _body(text)
    lines = body.splitlines()
    issues = _phrase_issues(lines)
    issues += _spelling_issues(lines, variant)
    issues += _rule_issues(lines)
    issues += _long_sentences(body)
    issues.sort(key=lambda x: (x.line, x.severity != "error"))
    return EditorialReport(issues=issues, variant=variant)
