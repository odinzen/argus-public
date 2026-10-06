"""Abstract-to-body number consistency.

A revision changes a value in the body and leaves the abstract stating the old one, or the
reverse. It reads as correct in either place alone, so nothing but a side-by-side catches
it. LLZO's transition temperature moved 600 -> 1400 -> 849 K across revisions; an abstract
left at an earlier number is exactly this failure.

The check pulls the distinctive quantities out of the abstract (a value carrying a unit or
an uncertainty, and either a decimal or a magnitude worth tracking, so trivial small
integers do not fire) and confirms each appears in the body within a small tolerance. A
value present as `912.6 K` in the body matches an abstract `912`; a `912.6` against an
abstract `849` does not, and is reported for review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import audit

# A value with an uncertainty (912.6 ± 20.5) or with a unit (505 K, 88.3 J/mol). Units are
# a curated set that actually occurs in these papers; a distinctive number outside it is
# better missed than guessed at.
_WITH_UNCERTAINTY = re.compile(r"(\d+(?:\.\d+)?)\s*(?:±|\+/-|\+-)\s*\d+(?:\.\d+)?")
_WITH_UNIT = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(?:K|°C|degC|%|at\.?%|wt\.?%|mol\.?%|eV|kJ/mol|J/mol"
    r"|J/\(mol[ ·]?K\)|GPa|MPa|nm|µm|mS/cm|S/cm)\b"
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Mismatch:
    value: float
    text: str  # as written in the abstract
    severity: str = "warning"


@dataclass
class ConsistencyReport:
    abstract_quantities: list[str] = field(default_factory=list)
    mismatches: list[Mismatch] = field(default_factory=list)
    checked: bool = True  # False when there is no identifiable abstract/body split

    @property
    def status(self) -> str:
        return "suspect" if self.mismatches else "ok"


def _distinctive(value: float, had_uncertainty: bool) -> bool:
    # Track a value if it carries an uncertainty, has a fractional part, or is large enough
    # to be a specific figure rather than a count. This keeps "5 at%" and "2 phases" out.
    return had_uncertainty or (value != int(value)) or abs(value) >= 100


def _abstract_quantities(abstract: str) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    seen: set[float] = set()
    for m in _WITH_UNCERTAINTY.finditer(abstract):
        v = float(m.group(1))
        if _distinctive(v, True) and v not in seen:
            seen.add(v)
            out.append((v, m.group().strip()))
    # Mask the uncertainty spans so the error term of "88.3 ± 1.2 J/mol" is not re-read as a
    # separate "1.2 J/mol" quantity by the unit pass.
    masked = _WITH_UNCERTAINTY.sub(lambda m: " " * len(m.group()), abstract)
    for m in _WITH_UNIT.finditer(masked):
        v = float(m.group(1))
        if _distinctive(v, False) and v not in seen:
            seen.add(v)
            out.append((v, m.group().strip()))
    return out


def _body_numbers(body: str) -> list[float]:
    return [float(x) for x in _NUMBER.findall(body)]


def _found(value: float, body_numbers: list[float]) -> bool:
    tol = max(0.015 * abs(value), 0.05)
    return any(abs(value - b) <= tol for b in body_numbers)


def check_consistency(text: str) -> ConsistencyReport:
    start = audit.main_text_start(text)
    if start <= 0:
        # No Introduction heading: cannot separate abstract from body.
        return ConsistencyReport(checked=False)
    abstract = text[:start]

    section = audit.references_section(text)
    has_refs = bool(section) and section in text and section != text
    end = text.find(section) if has_refs else len(text)
    body = text[start:end]

    quantities = _abstract_quantities(abstract)
    body_numbers = _body_numbers(body)
    report = ConsistencyReport(abstract_quantities=[t for _, t in quantities])
    for value, written in quantities:
        if not _found(value, body_numbers):
            report.mismatches.append(Mismatch(value=value, text=written))
    return report
