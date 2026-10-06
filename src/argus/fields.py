"""Extract Zotero citation field codes from a Word .docx, keyed to library items.

A Zotero-authored docx stores each in-text citation as a field whose instruction is
`ADDIN ZOTERO_ITEM CSL_CITATION {json}`. That JSON carries, per cited work, the Zotero
item key (inside its `uris`), the full CSL-JSON metadata Zotero inserted (`itemData`), and
the rendered citation string (`properties.formattedCitation`). Reading these ties every
in-text citation to a specific library item, so the metadata check and the numbering check
can be joined per citation instead of run blind. Standard library only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# instrText runs (complex fields) and fldSimple instr attributes (simple fields), in document
# order. A citation's JSON can be split across several instrText runs, so the stream is
# concatenated before scanning.
_PIECE = re.compile(
    r'<w:instrText[^>]*>(.*?)</w:instrText>|<w:fldSimple[^>]*w:instr="([^"]*)"',
    re.DOTALL,
)
_MARKER = "ADDIN ZOTERO_ITEM CSL_CITATION"
_KEY = re.compile(r"/items/([A-Z0-9]+)")
_TAG = re.compile(r"<[^>]+>")
_NUM = re.compile(r"\d{1,3}")
_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}


@dataclass
class CitedItem:
    key: str  # Zotero item key from the uris, "" if absent
    item_data: dict  # CSL-JSON metadata Zotero stored for the work


@dataclass
class FieldCitation:
    order: int  # position of this citation in document reading order
    items: list[CitedItem]
    printed: str  # rendered citation text, e.g. "[1]" or "[3, 5]"
    numbers: list[int]  # numbers parsed from the rendered text


def _unescape(s: str) -> str:
    for entity, char in _ENTITIES.items():
        s = s.replace(entity, char)
    return s


def _instruction_stream(document_xml: str) -> str:
    pieces = []
    for m in _PIECE.finditer(document_xml or ""):
        pieces.append(m.group(1) if m.group(1) is not None else m.group(2))
    return _unescape("".join(p or "" for p in pieces))


def _balanced_json(s: str, start: int) -> str | None:
    """Substring of the JSON object opened at `start`, respecting strings and nesting."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _item_key(citation_item: dict) -> str:
    for uri in citation_item.get("uris", []):
        m = _KEY.search(uri or "")
        if m:
            return m.group(1)
    return ""


def extract_citations(document_xml: str) -> list[FieldCitation]:
    """Every Zotero citation field in document order, keyed to its library items."""
    stream = _instruction_stream(document_xml)
    out: list[FieldCitation] = []
    pos = 0
    while True:
        marker = stream.find(_MARKER, pos)
        if marker == -1:
            break
        brace = stream.find("{", marker)
        if brace == -1:
            break
        block = _balanced_json(stream, brace)
        if block is None:
            break
        pos = brace + len(block)
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = [
            CitedItem(key=_item_key(ci), item_data=ci.get("itemData", {}))
            for ci in data.get("citationItems", [])
        ]
        props = data.get("properties", {})
        printed = _TAG.sub("", props.get("formattedCitation") or props.get("plainCitation") or "")
        out.append(
            FieldCitation(
                order=len(out),
                items=items,
                printed=printed,
                numbers=[int(n) for n in _NUM.findall(printed)],
            )
        )
    return out
