"""Check a manuscript's front/back-matter statements.

A paper's conflict-of-interest, AI-use, data-availability, funding, and acknowledgement
blocks are where a required disclosure goes missing, gets the wrong wording, or, worst,
says something it must not. Nothing in the reference or numbering checks looks at them.

For each statement a target journal requires, this verifies three things: it is present,
it says what it must (an AI-use disclosure names an *agentic* loop, a conflict declaration
names the Odinzen commercial interest), and it says nothing it must not.

The Sol acknowledgement is handled specially: it is required only when the manuscript says
it used Sol, and then it must also carry the Jennewein 2023 citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import policy


@dataclass
class StatementFinding:
    key: str
    label: str
    present: bool
    line: int  # first line of the block, or 0 if missing
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.present and not self.issues


@dataclass
class StatementsReport:
    findings: list[StatementFinding] = field(default_factory=list)
    extra_issues: list[str] = field(default_factory=list)  # Sol ack, non-fatal notes

    @property
    def status(self) -> str:
        bad = any(not f.ok for f in self.findings) or bool(self.extra_issues)
        return "suspect" if bad else "ok"


@dataclass
class _Block:
    text: str
    line: int


def _blocks(text: str) -> list[_Block]:
    """Paragraph blocks with the 1-based line where each starts."""
    out: list[_Block] = []
    line = 1
    for chunk in re.split(r"(\n\s*\n)", text):
        if chunk.strip("\n").strip() and not re.fullmatch(r"\n\s*\n", chunk):
            out.append(_Block(text=chunk, line=line))
        line += chunk.count("\n")
    return out


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def _find_block(blocks: list[_Block], cues: tuple[str, ...]) -> _Block | None:
    for b in blocks:
        if any(_contains(b.text, cue) for cue in cues):
            return b
    return None


def _check_rule(blocks: list[_Block], rule: policy.StatementRule) -> StatementFinding:
    block = _find_block(blocks, rule.cues)
    if block is None:
        hint = f" ({rule.hint})" if rule.hint else ""
        return StatementFinding(
            key=rule.key,
            label=rule.label,
            present=False,
            line=0,
            issues=[f"missing{hint}"],
        )

    # A section HEADING matches the cue but carries no content, so judging it alone
    # false-flags every properly-declared statement. When the matched block is that
    # short, fold in the block that follows it (the statement body) before judging.
    if len(block.text.strip()) < 60:
        idx = blocks.index(block)
        if idx + 1 < len(blocks):
            block = _Block(
                text=block.text + "\n" + blocks[idx + 1].text, line=block.line
            )

    issues: list[str] = []
    for group in rule.must_contain:
        if not any(_contains(block.text, opt) for opt in group):
            want = " / ".join(group)
            issues.append(f"does not mention {want!r}" + (f" ({rule.hint})" if rule.hint else ""))
    for bad in rule.forbidden:
        if _contains(block.text, bad):
            issues.append(f"contains forbidden text {bad!r} ({rule.hint or 'not allowed here'})")
    return StatementFinding(
        key=rule.key, label=rule.label, present=True, line=block.line, issues=issues
    )


def _check_sol(text: str) -> list[str]:
    """Sol was used -> the Jennewein 2023 citation must be present."""
    if not any(_contains(text, cue) for cue in policy.SOL_CUES):
        return []
    if policy.SOL_ACK_DOI in text:
        return []
    return [
        f"manuscript acknowledges Sol but does not cite the required HPC paper "
        f"(Jennewein 2023, {policy.SOL_ACK_DOI})"
    ]


def check_statements(text: str, journal: str | None = None) -> StatementsReport:
    blocks = _blocks(text)
    report = StatementsReport()
    for key in policy.required_statements(journal):
        rule = policy.STATEMENTS[key]
        report.findings.append(_check_rule(blocks, rule))
    report.extra_issues.extend(_check_sol(text))
    return report


# --- byline drift (warnings, not part of the pass/fail gate) ---


def byline_warnings(text: str) -> list[str]:
    """Heuristic checks against the canonical byline; drift is a copyeditor flag."""
    b = policy.BYLINE
    warnings: list[str] = []
    low = text.lower()
    if "odinzen" in low and b.company.lower() not in low:
        warnings.append(f"company rendered other than {b.company!r} (check the lowercase z)")
    if "odinzen" in low and re.search(r'\btempe\b', low):
        warnings.append("'Tempe' appears near Odinzen; the company city is Houston, TX")
    # Corresponding author cited without the middle initial.
    if re.search(r"\bBustamante\b", text) and b.corresponding not in text:
        warnings.append(f"corresponding author not written as {b.corresponding!r} (middle initial)")
    return warnings
