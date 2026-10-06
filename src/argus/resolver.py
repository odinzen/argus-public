"""Resolve a work record from one of several registries, not Crossref alone.

Crossref is the default and the most complete for journal articles, but it genuinely
misses real references: society journals it does not index, older physics, books, data
and software DOIs. A reference that is real but absent from Crossref should verify against
the registry that does hold it, not read as broken. Every resolver returns the shared
CrossrefRecord shape, so the verifier downstream stays registry-agnostic; the resolution
records which registry answered, so "verified via OpenAlex" is a pass, not a suspect.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .verify import CrossrefRecord


class Resolver(Protocol):
    name: str

    def by_doi(self, doi: str, mailto: str | None = None) -> CrossrefRecord | None: ...


@dataclass
class FunctionResolver:
    """Wrap a plain ``fetch(doi, mailto)`` function as a named Resolver."""

    name: str
    func: Callable[[str, str | None], CrossrefRecord | None]

    def by_doi(self, doi: str, mailto: str | None = None) -> CrossrefRecord | None:
        return self.func(doi, mailto)


@dataclass
class Resolution:
    record: CrossrefRecord | None
    source: str  # registry that answered, e.g. "crossref"; "" if none resolved

    @property
    def resolved(self) -> bool:
        return self.record is not None


def default_resolvers() -> list[Resolver]:
    """Crossref first (richest for journals), then OpenAlex as the broad fallback."""
    from .crossref import fetch as crossref_fetch
    from .openalex import fetch as openalex_fetch

    return [
        FunctionResolver("crossref", crossref_fetch),
        FunctionResolver("openalex", openalex_fetch),
    ]


def resolve_doi(
    doi: str, resolvers: list[Resolver] | None = None, mailto: str | None = None
) -> Resolution:
    """Try each resolver in order; return the first record found and its source."""
    for resolver in resolvers or default_resolvers():
        record = resolver.by_doi(doi, mailto)
        if record is not None:
            return Resolution(record, resolver.name)
    return Resolution(None, "")
