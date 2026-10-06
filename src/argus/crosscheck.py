"""Join Zotero-keyed citations to the registry metadata check and the numbering check.

Given the field-code citations from a docx, this assigns each cited item its canonical
number (order of first appearance), verifies each item's stored metadata against the
registries, and confirms the printed number matches the canonical one. The result is
per reference: right paper, right place, right number, all keyed to the Zotero item.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fields import FieldCitation
from .references import reference_from_csl
from .resolver import Resolver, default_resolvers, resolve_doi
from .verify import verify


@dataclass
class ReferenceAudit:
    canonical_number: int  # number assigned by order of first appearance
    key: str  # Zotero item key
    title: str
    doi: str | None
    metadata_status: str  # "ok" | "suspect" | "broken" | "no-doi"
    metadata_issues: list[str]
    source: str  # registry that verified (e.g. "crossref", "openalex")
    printed_numbers: list[int]  # numbers actually printed for this item in the body
    number_ok: bool  # printed number(s) all equal the canonical number


@dataclass
class ManuscriptAudit:
    references: list[ReferenceAudit]
    numbering_issues: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        bad = any(
            r.metadata_status in ("suspect", "broken") or not r.number_ok for r in self.references
        )
        return "suspect" if bad or self.numbering_issues else "ok"


def _first_appearance(citations: list[FieldCitation]) -> tuple[list[str], dict[str, dict]]:
    order: list[str] = []
    data: dict[str, dict] = {}
    for citation in citations:
        for item in citation.items:
            if item.key and item.key not in data:
                data[item.key] = item.item_data
                order.append(item.key)
    return order, data


def _printed_by_key(citations: list[FieldCitation]) -> dict[str, set[int]]:
    """Numbers printed for each item. When a citation lists as many numbers as items, map
    them positionally; otherwise attribute all of the citation's numbers to each item (an
    honest over-approximation that still catches a number that should not be there)."""
    seen: dict[str, set[int]] = {}
    for citation in citations:
        keys = [it.key for it in citation.items if it.key]
        nums = citation.numbers
        if len(keys) == len(nums):
            pairs = zip(keys, nums, strict=True)
        else:
            pairs = ((k, n) for k in keys for n in nums)
        for key, num in pairs:
            seen.setdefault(key, set()).add(num)
    return seen


def audit(
    citations: list[FieldCitation],
    resolvers: list[Resolver] | None = None,
    mailto: str | None = None,
) -> ManuscriptAudit:
    resolvers = resolvers or default_resolvers()
    order, data = _first_appearance(citations)
    canonical = {key: i + 1 for i, key in enumerate(order)}
    printed = _printed_by_key(citations)

    refs = []
    for key in order:
        ref = reference_from_csl(data[key])
        status, issues, source = "no-doi", [], ""
        if ref.doi:
            resolution = resolve_doi(ref.doi, resolvers, mailto)
            if not resolution.resolved:
                status, issues = "broken", [f"DOI did not resolve at any registry: {ref.doi}"]
            else:
                finding = verify(ref, resolution.record)
                status, issues, source = finding.status, finding.issues, resolution.source
        nums = sorted(printed.get(key, set()))
        refs.append(
            ReferenceAudit(
                canonical_number=canonical[key],
                key=key,
                title=ref.title,
                doi=ref.doi,
                metadata_status=status,
                metadata_issues=issues,
                source=source,
                printed_numbers=nums,
                number_ok=(not nums or nums == [canonical[key]]),
            )
        )

    issues = []
    all_printed = sorted({n for nums in printed.values() for n in nums})
    expected = list(range(1, len(order) + 1))
    if all_printed and all_printed != expected:
        missing = [n for n in expected if n not in all_printed]
        extra = [n for n in all_printed if n not in expected]
        if missing:
            issues.append("numbers expected but never printed: " + ", ".join(map(str, missing)))
        if extra:
            issues.append(
                "numbers printed beyond the cited-item count: " + ", ".join(map(str, extra))
            )
    for r in refs:
        if not r.number_ok:
            issues.append(
                f"{r.key} (canonical {r.canonical_number}) printed as "
                f"{r.printed_numbers}, expected {r.canonical_number}"
            )
    return ManuscriptAudit(refs, issues)
