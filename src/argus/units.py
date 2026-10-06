"""Temperature and composition unit consistency across a manuscript.

Kristina's rule is one primary temperature unit and one composition unit per paper, and
the target journal decides which. This does not know a journal's house unit unless one is
given, so like `argus format` it works two ways: with a `--journal` it holds the paper to
that journal's pinned unit and fails on the other one; without one it only reports a mix,
because K in a rate column and degC in the prose can legitimately coexist and the tool
cannot tell a table cell from a sentence.

Composition is always advisory: at% and mol% are the same quantity, so using both is a
flag, and wt% alongside either is a conversion the reader must be told is intentional, not
a mechanical error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import audit, policy

# degC in either spelling (`°C` or Kristina's `degC`/`deg C`); both are the same unit.
_DEGC = re.compile(r"°\s*C|(?<![A-Za-z])deg\.?\s*C\b", re.IGNORECASE)
# An absolute temperature in kelvin: a number then K, not `Kg`, `K2O`, or a bare variable.
_KELVIN = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*K(?![A-Za-z])")

_COMPOSITION: list[tuple[str, re.Pattern[str]]] = [
    ("at%", re.compile(r"\bat\.?\s*%|\batomic\s*(?:percent|%)", re.IGNORECASE)),
    ("wt%", re.compile(r"\bwt\.?\s*%|\b(?:weight|mass)\s*(?:percent|%)", re.IGNORECASE)),
    ("mol%", re.compile(r"\bmol\.?\s*%|\b(?:mole|molar)\s*(?:percent|%)", re.IGNORECASE)),
]


@dataclass
class UnitFinding:
    kind: str  # temperature | composition
    message: str
    severity: str  # error | warning


@dataclass
class UnitsReport:
    findings: list[UnitFinding] = field(default_factory=list)
    degc: int = 0
    kelvin: int = 0
    composition: dict[str, int] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "suspect" if any(f.severity == "error" for f in self.findings) else "ok"


def _body(text: str) -> str:
    section = audit.references_section(text)
    if section and section in text and section != text:
        return text[: text.find(section)]
    return text


def _temperature(body: str, pinned: str) -> tuple[int, int, list[UnitFinding]]:
    degc = len(_DEGC.findall(body))
    kelvin = len(_KELVIN.findall(body))
    findings: list[UnitFinding] = []
    if pinned == "degC" and kelvin:
        findings.append(
            UnitFinding(
                "temperature",
                f"{kelvin} kelvin value(s) in a degC paper (K belongs only in rate/sensitivity "
                "columns)",
                "error",
            )
        )
    elif pinned == "K" and degc:
        findings.append(
            UnitFinding("temperature", f"{degc} degC value(s) in a kelvin paper", "error")
        )
    elif not pinned and degc and kelvin:
        findings.append(
            UnitFinding(
                "temperature",
                f"both units present ({degc} degC, {kelvin} K); pick one primary per the "
                "target journal",
                "warning",
            )
        )
    return degc, kelvin, findings


def _composition(body: str) -> tuple[dict[str, int], list[UnitFinding]]:
    counts = {name: len(pat.findall(body)) for name, pat in _COMPOSITION}
    present = [name for name, n in counts.items() if n]
    findings: list[UnitFinding] = []
    if "at%" in present and "mol%" in present:
        findings.append(
            UnitFinding(
                "composition",
                "at% and mol% both used; they are the same quantity, use one",
                "warning",
            )
        )
    if "wt%" in present and ("at%" in present or "mol%" in present):
        findings.append(
            UnitFinding(
                "composition",
                "wt% used alongside at%/mol%; confirm the conversion is intended",
                "warning",
            )
        )
    return counts, findings


def check_units(text: str, journal: str | None = None) -> UnitsReport:
    pinned = ""
    if journal and journal in policy.JOURNALS:
        pinned = policy.JOURNALS[journal].temperature_unit
    body = _body(text)
    degc, kelvin, temp_findings = _temperature(body, pinned)
    counts, comp_findings = _composition(body)
    return UnitsReport(
        findings=temp_findings + comp_findings,
        degc=degc,
        kelvin=kelvin,
        composition={k: v for k, v in counts.items() if v},
    )
