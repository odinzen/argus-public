"""Odinzen manuscript policy: what every outgoing manuscript must and must not carry.

One source of truth for the `statements` and `kristina` checks. It is plain
Python data, not YAML, because argus ships with no third-party dependencies and adding a
loader for one config file is not worth it. Edit the data here; the checks read it.

Two things live here:

- BYLINE, the exact author strings a copyeditor flags when they drift.
- STATEMENTS + JOURNALS, which front/back-matter statements each target journal requires
  and, for each, what it must say and must never say.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Byline:
    company: str = "Odinzen LLC"  # lowercase z
    city: str = "Houston, TX"  # not Tempe
    corresponding: str = "Michael E. Bustamante"  # middle initial
    corresponding_email: str = "michaelbusta@odinzen.io"


BYLINE = Byline()


@dataclass(frozen=True)
class StatementRule:
    """One required statement: how to find it, what it must and must not say."""

    key: str
    label: str
    # Any of these phrases, case-insensitive, marks the statement as present.
    cues: tuple[str, ...]
    # The statement text must contain at least one phrase from each inner group (an AND of
    # ORs): must_contain = [("odinzen llc", "odinzen")] means "mentions Odinzen somehow".
    must_contain: tuple[tuple[str, ...], ...] = ()
    # None of these phrases may appear in the statement text.
    forbidden: tuple[str, ...] = ()
    # A short note shown when the statement is missing, so the fix is obvious.
    hint: str = ""


STATEMENTS: dict[str, StatementRule] = {
    "conflict_of_interest": StatementRule(
        key="conflict_of_interest",
        label="Conflict-of-interest declaration",
        cues=("conflict of interest", "competing interest", "declaration of interest"),
        must_contain=(("odinzen",),),  # declare the commercial interest, not a bare "none"
        hint="declare the Odinzen LLC commercial interest, not 'the authors declare none'",
    ),
    "ai_use": StatementRule(
        key="ai_use",
        label="AI-use disclosure",
        cues=(
            "generative ai",
            "artificial intelligence",
            "large language model",
            "ai-assisted",
            "ai tool",
            "use of ai",
            "during the preparation of this work",
            "agentic",  # our house disclosures name the loop as agentic
        ),
        must_contain=(("agentic",),),
        forbidden=("autonomous",),  # the loop is human-gated; never call it autonomous
        hint="disclose the agentic (human-gated) loop; do not write 'autonomous'",
    ),
    "data_availability": StatementRule(
        key="data_availability",
        label="Data-availability statement",
        cues=("data availability", "availability of data", "data are available"),
        hint="TDB = 'available from the corresponding author on reasonable request'; "
        "Sol-computed data = open with a repo link",
    ),
    "acknowledgement": StatementRule(
        key="acknowledgement",
        label="Acknowledgement",
        cues=("acknowledg",),  # UK/US: acknowledgement / acknowledgment
        hint="if the work used Sol, include the Sol acknowledgement and cite Jennewein 2023 "
        "(10.1145/3569951.3597573); name the funding grant number",
    ),
    "author_contributions": StatementRule(
        key="author_contributions",
        label="Author-contributions statement",
        cues=("author contribution", "credit author", "contributor roles"),
        hint="list contributions; every name must also appear in the byline",
    ),
    "funding": StatementRule(
        key="funding",
        label="Funding statement",
        cues=("funding", "financial support", "this work was supported"),
        hint="name the funder and grant number; include the funder's required disclaimer",
    ),
}

# The Sol acknowledgement is a presence rule with a paired citation, handled specially by
# the statements check (it only fires when the manuscript says it used Sol).
SOL_CUES: tuple[str, ...] = ("sol supercomputer", "asu sol", "research computing at asu")
SOL_ACK_DOI = "10.1145/3569951.3597573"  # Jennewein 2023


@dataclass(frozen=True)
class Journal:
    name: str
    requires: tuple[str, ...]
    temperature_unit: str = ""  # "degC" or "K"; "" = not pinned
    spelling: str = ""  # "American" or "British"; "" = not pinned


# Which statements each target journal mandates. Keys index STATEMENTS. A manuscript
# checked with --journal JECS is held to JECS's list; with no --journal, the union of the
# always-expected ones (conflict_of_interest, data_availability) is used.
JOURNALS: dict[str, Journal] = {
    "JECS": Journal(
        name="Journal of The Electrochemical Society",
        requires=("conflict_of_interest", "data_availability", "ai_use", "funding"),
        temperature_unit="degC",
        spelling="American",
    ),
    "ECM": Journal(
        name="Energy Conversion and Management",
        requires=(
            "conflict_of_interest",
            "data_availability",
            "ai_use",
            "author_contributions",
            "funding",
        ),
        spelling="British",
    ),
    "JPED": Journal(
        name="Journal of Phase Equilibria and Diffusion",
        requires=("conflict_of_interest", "data_availability", "funding"),
        temperature_unit="K",
        spelling="American",
    ),
    "Nature": Journal(
        name="Nature",
        requires=(
            "conflict_of_interest",
            "data_availability",
            "author_contributions",
            "ai_use",
        ),
        spelling="British",
    ),
}

DEFAULT_REQUIRED: tuple[str, ...] = ("conflict_of_interest", "data_availability")


def required_statements(journal: str | None) -> tuple[str, ...]:
    if journal and journal in JOURNALS:
        return JOURNALS[journal].requires
    return DEFAULT_REQUIRED


@dataclass
class PolicyHit:
    """A forbidden term or a policy departure found in a file."""

    path: str
    line: int
    term: str
    snippet: str
    severity: str  # error | warning
    reason: str = ""
    extra: dict = field(default_factory=dict)
