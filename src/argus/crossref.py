"""Fetch a work record from the Crossref REST API (standard library only)."""

from __future__ import annotations

import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from .verify import CrossrefRecord, first_page_of

_API = "https://api.crossref.org/works/"


def fetch(doi: str, mailto: str | None = None) -> CrossrefRecord | None:
    """Return the Crossref record for a DOI, or None if it does not resolve."""
    url = _API + quote(doi)
    if mailto:
        url += f"?mailto={quote(mailto)}"
    agent = f"argus (+{mailto})" if mailto else "argus"
    try:
        with urlopen(Request(url, headers={"User-Agent": agent}), timeout=30) as resp:
            message = json.load(resp).get("message", {})
    except Exception:
        return None

    authors = [
        " ".join(filter(None, [a.get("given"), a.get("family") or a.get("literal")]))
        for a in message.get("author", [])
    ]
    parts = ((message.get("issued") or {}).get("date-parts") or [[None]])[0] or [None]
    return CrossrefRecord(
        title=(message.get("title") or [""])[0],
        authors=[a for a in authors if a],
        year=parts[0],
        volume=message.get("volume"),
        first_page=first_page_of(message.get("page")) or None,
    )
