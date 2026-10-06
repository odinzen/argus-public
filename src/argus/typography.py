"""Catch super/subscript typography that the pandoc markdown -> docx build drops.

A manuscript written in pandoc markdown (`markdown+subscript+superscript`) marks a
superscript as `10^6^` and a subscript as `S~298~`. The recurring failure is an
*unclosed* caret -- `10^6`, `T^2`, `cm^-1` with the trailing `^` missing -- which
pandoc renders as a literal caret, not a superscript. Subscripts fail the opposite
way: a descriptor that should carry one is left flat (`dHf`, `Cp`, `D0`), so it reads
as sloppy next to the formulas that are subscripted correctly.

Both LLZO papers shipped near-final drafts with this. The checks here are the machine
form of the spot-check that found it: scan the markdown source for unclosed carets and
flat descriptors, and confirm a rebuilt docx actually carries the runs.

Unclosed carets are reported as errors (an unambiguous build artifact). Flat
descriptors and bare molecular formulas are heuristics, so they are warnings -- a human
confirms before rewriting, because `Cp`/`S30` also occur as ordinary variables and
sample labels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import docx

# A closed superscript/subscript pair: caret-or-tilde, no whitespace inside, closed.
# Stripping these first means a caret that remains is genuinely unclosed.
_CLOSED_SUP = re.compile(r"\^[^\s^]+\^")
_CLOSED_SUB = re.compile(r"~[^\s~]+~")

# A remaining caret that opens superscript-like content (a digit, sign, or letter run)
# with no closing caret before the next space. This is the shipped bug.
_UNCLOSED_SUP = re.compile(r"\^[-+]?[0-9A-Za-z][0-9A-Za-z)]*")

# A bare ionic charge written with no caret at all: `Li+`, `Ca2+`, `O2-`, `Al3+`. The
# element symbol prefix (validated below) keeps this off "A+" grades and "C++". The sign
# must sit directly on the symbol, so an already-superscripted `Li^+^` does not match.
_FLAT_CHARGE = re.compile(r"(?<![\w~^])([A-Z][a-z]?)(\d?[+-])(?![\w~=])")

# Flat descriptors that should carry a subscript. Curated, not inferred: each is a
# quantity that appears subscripted in the same papers, guarded so it does not fire
# inside a longer word or an already-tilde'd token. The S-with-digits case covers
# standard-state markers (S298, S30) without swallowing four-digit years.
_DESCRIPTORS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<![\w~])dHf(?![\w~])"), "dH~f~"),
    (re.compile(r"(?<![\w~])Cp(?![\w~,])"), "C~p~"),
    (re.compile(r"(?<![\w~])D0(?![\w~])"), "D~0~"),
    (re.compile(r"(?<![\w~])S(29[0-9]|30)(?![\w~])"), r"S~\g<1>~"),
]

# A bare molecular formula in prose: element-symbol runs carrying a digit that should
# be a subscript, not wrapped in tildes. The tilde guards leave `p~CO2~` (a partial
# pressure already subscripted as a unit) untouched. Heuristic, hence a warning.
_BARE_FORMULA = re.compile(
    r"(?<![\w~/.])((?:[A-Z][a-z]?\d*){1,8})(?![\w~])"
)

# Requiring every group to be a real element symbol is what separates Li7La3Zr2O12 from
# an acronym-plus-year like SGTE91 (G, T, E are not elements).
_ELEMENTS = frozenset(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn "
    "Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce "
    "Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn "
    "Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr".split()
)

# Anything sitting inside a URL or DOI is off-limits: `10.1039/D4DD00115J` contains the
# substring `D0`, and that false positive is exactly what tripped an early audit.
_PROTECTED = re.compile(r"https?://\S+|(?<!\w)10\.\d{4,9}/\S+|doi\.org/\S+", re.IGNORECASE)

# A degree written with the wrong glyph before C: the letter o/O, the masculine ordinal
# `º`, or a ring `˚`, where a real degree `°` was meant ("25 oC" for "25 degC").
# The correct `°` is not in the class, so a right degree never fires.
_DEGREE_WRONG = re.compile(r"(?<=\d)\s*[oOº˚]\s*(?=C\b)")

# OMML math and equation references, for the .docx display-equation-object check: an
# equation referenced in the prose but rendered as a pasted image or plain text carries no
# <m:oMath> element, so a paper with "Eq. (3)" and zero math objects is a build smell.
_OMML = re.compile(r"<m:oMath[ >]")
_EQ_REF = re.compile(r"\bEq(?:s|uation|uations)?\.?\s*\(?\s*\d", re.IGNORECASE)


@dataclass
class Issue:
    line: int
    kind: str  # unclosed-superscript | flat-subscript | bare-formula
    token: str
    suggestion: str
    snippet: str
    severity: str  # error | warning


def _protected_spans(line: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _PROTECTED.finditer(line)]


def _in_protected(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


def _snippet(line: str, start: int, end: int, pad: int = 14) -> str:
    return line[max(0, start - pad) : end + pad].strip()


def _looks_like_formula(tok: str) -> bool:
    # Require a digit (the would-be subscript) and at least two element-ish groups, so
    # "Fig3"/"H2020"/"COVID" and bare capitals do not qualify.
    if not any(c.isdigit() for c in tok):
        return False
    groups = re.findall(r"[A-Z][a-z]?\d*", tok)
    if len(groups) < 2 or "".join(groups) != tok:
        return False
    # A stoichiometric subscript is 1-2 digits with no leading zero; ESPEI parameter
    # codes (VV0001, VV0002) and identifiers fail this and must not be flagged.
    for num in re.findall(r"\d+", tok):
        if len(num) > 2 or num.startswith("0"):
            return False
    # Every symbol must be a real element, so SGTE91 / DFT2 / GHSER-style codes are out.
    return all(re.match(r"[A-Z][a-z]?", g).group() in _ELEMENTS for g in groups)


def find_unclosed_superscripts(text: str) -> list[Issue]:
    out: list[Issue] = []
    for i, line in enumerate(text.splitlines(), 1):
        spans = _protected_spans(line)
        stripped = _CLOSED_SUB.sub(lambda m: " " * len(m.group()), line)
        stripped = _CLOSED_SUP.sub(lambda m: " " * len(m.group()), stripped)
        for m in _UNCLOSED_SUP.finditer(stripped):
            if _in_protected(m.start(), spans):
                continue
            tok = line[m.start() : m.end()]
            out.append(
                Issue(
                    line=i,
                    kind="unclosed-superscript",
                    token=tok,
                    suggestion=f"{tok}^",
                    snippet=_snippet(line, m.start(), m.end()),
                    severity="error",
                )
            )
    return out


def find_flat_subscripts(text: str) -> list[Issue]:
    out: list[Issue] = []
    for i, line in enumerate(text.splitlines(), 1):
        spans = _protected_spans(line)
        for pat, repl in _DESCRIPTORS:
            for m in pat.finditer(line):
                if _in_protected(m.start(), spans):
                    continue
                out.append(
                    Issue(
                        line=i,
                        kind="flat-subscript",
                        token=m.group(),
                        suggestion=m.expand(repl),
                        snippet=_snippet(line, m.start(), m.end()),
                        severity="warning",
                    )
                )
    return out


def find_flat_charges(text: str) -> list[Issue]:
    out: list[Issue] = []
    for i, line in enumerate(text.splitlines(), 1):
        spans = _protected_spans(line)
        for m in _FLAT_CHARGE.finditer(line):
            if _in_protected(m.start(), spans) or m.group(1) not in _ELEMENTS:
                continue
            tok = m.group()
            out.append(
                Issue(
                    line=i,
                    kind="flat-charge",
                    token=tok,
                    suggestion=f"{m.group(1)}^{m.group(2)}^",
                    snippet=_snippet(line, m.start(), m.end()),
                    severity="warning",
                )
            )
    return out


def find_bare_formulas(text: str) -> list[Issue]:
    out: list[Issue] = []
    for i, line in enumerate(text.splitlines(), 1):
        spans = _protected_spans(line)
        for m in _BARE_FORMULA.finditer(line):
            tok = m.group(1)
            if _in_protected(m.start(1), spans) or not _looks_like_formula(tok):
                continue
            fixed = re.sub(r"(\d+)", r"~\g<1>~", tok)
            out.append(
                Issue(
                    line=i,
                    kind="bare-formula",
                    token=tok,
                    suggestion=fixed,
                    snippet=_snippet(line, m.start(1), m.end(1)),
                    severity="warning",
                )
            )
    return out


def find_degree_glyph(text: str) -> list[Issue]:
    out: list[Issue] = []
    for i, line in enumerate(text.splitlines(), 1):
        spans = _protected_spans(line)
        for m in _DEGREE_WRONG.finditer(line):
            if _in_protected(m.start(), spans):
                continue
            out.append(
                Issue(
                    line=i,
                    kind="degree-glyph",
                    token=line[m.start() : m.end() + 1].strip(),  # include the following C
                    suggestion="°C",
                    snippet=_snippet(line, m.start(), m.end() + 1),
                    severity="warning",
                )
            )
    return out


@dataclass
class TypographyReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [x for x in self.issues if x.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [x for x in self.issues if x.severity == "warning"]

    @property
    def status(self) -> str:
        return "suspect" if self.errors else "ok"


def check_markdown(text: str) -> TypographyReport:
    """Scan pandoc markdown for unclosed carets (errors) and flat descriptors/formulas."""
    issues = find_unclosed_superscripts(text)
    issues += find_flat_subscripts(text)
    issues += find_flat_charges(text)
    issues += find_bare_formulas(text)
    issues += find_degree_glyph(text)
    issues.sort(key=lambda x: (x.line, x.severity != "error"))
    return TypographyReport(issues=issues)


@dataclass
class RenderedTypography:
    superscript_runs: int
    subscript_runs: int
    leftover_carets: list[str]  # visible-text snippets still holding a literal caret
    math_objects: int = 0  # <m:oMath> equation objects in the build
    equation_references: int = 0  # "Eq. (n)" mentions in the visible text

    @property
    def status(self) -> str:
        # A rendered manuscript should have no literal caret left; any is a build that
        # kept an unclosed superscript as text. Zero styled runs on a formula-bearing
        # paper is its own smell, but the caller decides that, not this dataclass.
        return "suspect" if self.leftover_carets else "ok"

    @property
    def equations_may_be_images(self) -> bool:
        # Referenced equations but no OMML: they were pasted as images or left as plain
        # text, not built as equation objects. A note, not a failure.
        return self.equation_references > 0 and self.math_objects == 0


_VERTALIGN = re.compile(r'<w:vertAlign\s+w:val="(superscript|subscript)"\s*/>')


def check_docx(path: str) -> RenderedTypography:
    """Confirm a rebuilt docx carries the runs and kept no literal caret in its text."""
    xml = docx.document_xml(path)
    kinds = _VERTALIGN.findall(xml)
    body = docx.text(path)
    spans = _protected_spans(body)
    leftover = [
        body[max(0, m.start() - 20) : m.start() + 20].strip()
        for m in re.finditer(r"\^", body)
        if not _in_protected(m.start(), spans)
    ]
    return RenderedTypography(
        superscript_runs=kinds.count("superscript"),
        subscript_runs=kinds.count("subscript"),
        leftover_carets=leftover,
        math_objects=len(_OMML.findall(xml)),
        equation_references=len(_EQ_REF.findall(body)),
    )
