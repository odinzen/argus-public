"""Fetch a work record from the OpenAlex API (standard library only).

OpenAlex is a broad superset of Crossref that also ingests PubMed, arXiv, and the
repositories, so it resolves references Crossref misses -- the fallback that turns a
Crossref 404 from "broken" into "verified elsewhere". Mapped to the shared CrossrefRecord
shape so the same author/title/volume/page diff runs against it unchanged.
"""

from __future__ import annotations

import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from .verify import CrossrefRecord, first_page_of

_API = "https://api.openalex.org/works/doi:"


def _parse(data: dict) -> CrossrefRecord | None:
    """Map an OpenAlex work object to a CrossrefRecord, or None if it is not a work."""
    if not data or data.get("id") is None:
        return None
    authors = [a.get("author", {}).get("display_name", "") for a in data.get("authorships", [])]
    biblio = data.get("biblio") or {}
    return CrossrefRecord(
        title=data.get("display_name") or "",
        authors=[a for a in authors if a],
        year=data.get("publication_year"),
        volume=biblio.get("volume") or None,
        first_page=first_page_of(biblio.get("first_page")) or None,
    )


def fetch(doi: str, mailto: str | None = None) -> CrossrefRecord | None:
    """Return the OpenAlex record for a DOI, or None if it does not resolve."""
    url = _API + quote(doi)
    if mailto:
        url += f"?mailto={quote(mailto)}"
    agent = f"argus (+{mailto})" if mailto else "argus"
    try:
        with urlopen(Request(url, headers={"User-Agent": agent}), timeout=30) as resp:
            data = json.load(resp)
    except Exception:
        return None
    return _parse(data)
