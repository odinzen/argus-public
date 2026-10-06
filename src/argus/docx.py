"""Read text and field codes from a .docx (a zip of XML), standard library only.

Mirrors what the browser build does with JSZip, so the CLI can audit a Word manuscript
without leaving the standard library. Paragraph boundaries become newlines so a marker's
character position stays meaningful for the ordering check.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

_PARA_END = re.compile(r"</w:p>")
_TAG = re.compile(r"<[^>]+>")
_INSTR = re.compile(r"<w:instrText[^>]*>(.*?)</w:instrText>", re.DOTALL)

_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}

# ACS-style citations are superscript, not bracketed. To reuse the [n] ordering pipeline we
# render a superscript *citation* as "[n]" while reading. The hard part is that math also
# rides in superscript (gamma^3, cos^3, dG_v^2, mol^-1), so a bare superscript integer is not
# enough to go on. A citation is a positive-integer run that does NOT sit on a math base: not
# after a subscript (x_i^2), not after a Greek letter or a digit (gamma^3, 10^6), not after a
# function name (cos^3), and never a signed exponent (mol^-1, m^-2 fail the leading-digit
# requirement). Whatever slips past these still shows up in the numbering diff for a human.
_RUN = re.compile(r"<w:r\b.*?</w:r>", re.DOTALL)
_WT = re.compile(r"<w:t[^>]*>(.*?)</w:t>", re.DOTALL)
_SUPERSCRIPT = re.compile(r'<w:vertAlign\s+w:val="superscript"\s*/>')
_SUBSCRIPT = re.compile(r'<w:vertAlign\s+w:val="subscript"\s*/>')
_CITE_NUMS = re.compile(r"\d{1,3}(?:\s*[,–—-]\s*\d{1,3})*")
_MATH_FN = re.compile(r"(?<![a-z])(?:cos|sin|tan|sec|csc|cot|exp|log|ln)$", re.IGNORECASE)

# Unicode superscript digits (typed by hand instead of a real superscript run) and the
# superscript minus that marks a negative exponent.
_SUP_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_SUP_TRANS = str.maketrans(_SUP_DIGITS, "0123456789")
_SUP_RUN = re.compile(f"[{_SUP_DIGITS}]+")
_SUP_MINUS = "⁻"


def _unescape(s: str) -> str:
    for entity, char in _ENTITIES.items():
        s = s.replace(entity, char)
    return s


def _greek(ch: str) -> bool:
    return "Ͱ" <= ch <= "Ͽ"


def _cite_context(prev_char: str, prev_subscript: bool, tail: str) -> bool:
    """True when what precedes a superscript reads like text, not a math base."""
    if prev_subscript:
        return False
    if prev_char and (prev_char.isdigit() or _greek(prev_char)):
        return False
    return not _MATH_FN.search(tail)


def _bracket_superscript_runs(xml: str) -> str:
    """Rewrite each superscript citation run's text to a "[n]" marker, in place.

    The math-base context is per paragraph: a digit that ends the previous paragraph or table
    cell (a technique cell reading "MHTC-96") is not the base of a superscript that opens the
    next one, so the context resets at every paragraph end.
    """
    return "".join(_bracket_paragraph(part) for part in re.split(r"(?<=</w:p>)", xml))


def _bracket_paragraph(xml: str) -> str:
    state = {"tail": "", "prev_subscript": False}

    def rewrite(match: re.Match) -> str:
        run = match.group(0)
        visible = _unescape("".join(_WT.findall(run)))
        is_sup = bool(_SUPERSCRIPT.search(run))
        out = run
        if (
            is_sup
            and _CITE_NUMS.fullmatch(visible.strip())
            and _cite_context(state["tail"][-1:], state["prev_subscript"], state["tail"])
        ):
            visible = f"[{visible.strip()}]"
            done = [False]

            def one(m: re.Match) -> str:
                if done[0]:
                    return "<w:t></w:t>"
                done[0] = True
                return f'<w:t xml:space="preserve">{visible}</w:t>'

            out = _WT.sub(one, run)
        state["tail"] = (state["tail"] + visible)[-16:]
        state["prev_subscript"] = bool(_SUBSCRIPT.search(run))
        return out

    return _RUN.sub(rewrite, xml)


def _bracket_unicode_superscripts(flat: str) -> str:
    """Typed unicode superscript digits (spacing,¹) become "[n]" markers too."""

    def rewrite(m: re.Match) -> str:
        prev = flat[m.start() - 1] if m.start() else ""
        if prev == _SUP_MINUS or prev.isdigit() or _greek(prev):
            return m.group(0)  # a negative or math exponent, leave it
        return f"[{m.group(0).translate(_SUP_TRANS)}]"

    return _SUP_RUN.sub(rewrite, flat)


def document_xml(path: str | Path) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read("word/document.xml").decode("utf-8", "replace")


def text(path: str | Path) -> str:
    """Visible text with paragraphs separated by newlines (field codes stripped)."""
    xml = document_xml(path)
    xml = _INSTR.sub("", xml)  # drop field instructions; they are not visible text
    xml = _PARA_END.sub("\n", xml)
    return _unescape(_TAG.sub("", xml))


def text_for_ordering(path: str | Path) -> str:
    """Like ``text`` but superscript citations (ACS style) are rendered as "[n]" markers.

    Lets the bracketed-citation ordering check work on a superscript-cited manuscript without
    the rest of the pipeline knowing the difference.
    """
    xml = document_xml(path)
    xml = _INSTR.sub("", xml)
    xml = _bracket_superscript_runs(xml)
    xml = _PARA_END.sub("\n", xml)
    return _bracket_unicode_superscripts(_unescape(_TAG.sub("", xml)))


def field_codes(path: str | Path) -> list[str]:
    """Raw text of every <w:instrText> run (Zotero citation field codes live here)."""
    return _INSTR.findall(document_xml(path))
