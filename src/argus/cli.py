"""argus command line.

  argus check refs.json         verify each reference against the registries
  argus order manuscript.docx   check numbering: citations, plus figure/table captions
  argus typography draft.md     find unclosed superscripts and flat subscripts (source)
  argus typography draft.docx   confirm a rebuilt docx carries the styled runs
  argus renumber draft.md       report citation order; --apply to rewrite in place
  argus format manuscript.docx  flag body paragraphs that drift from the body formatting
  argus statements paper.docx   check COI, AI-use, data-availability and other statements
  argus editorial paper.docx    Editorial checklist: banned phrasing, em-dashes, spelling
  argus units paper.docx        temperature and composition unit consistency
  argus consistency paper.docx  check distinctive abstract values appear in the body
  argus repro public-repo/      check a repro repo's README manifest against its files

``argus order`` checks three numbering systems in one pass: in-text citations against the
reference list, and figure and table captions against the body that references them. Citations
are read whether they are bracketed [n] or ACS-style superscripts (math superscripts such as
gamma^3 or mol^-1 are left alone). Citation numbering is counted from the Introduction, so an
abstract carries no numbers.
``argus refs.json`` (no subcommand) still runs ``check``, the original behaviour.
"""

from __future__ import annotations

import argparse
import sys

from . import (
    anchors,
    audit,
    consistency,
    crosscheck,
    docx,
    editorial,
    fields,
    floats,
    formatting,
    ordering,
    policy,
    renumbering,
    repro,
    statements,
    typography,
    units,
    xref,
)
from .references import load_references
from .resolver import default_resolvers, resolve_doi
from .verify import verify

_SUBCOMMANDS = {
    "check",
    "order",
    "audit",
    "typography",
    "renumber",
    "format",
    "statements",
    "editorial",
    "units",
    "consistency",
    "repro",
}


def _read_text(path: str) -> str:
    return docx.text(path) if path.lower().endswith(".docx") else _read_plain(path)


def _read_plain(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8", errors="replace")


def check(args: argparse.Namespace) -> int:
    resolvers = default_resolvers()
    refs = load_references(args.refs)
    problems = 0
    for ref in refs:
        if not ref.doi:
            problems += 1
            print(f"[no-doi]  {ref.key}")
            continue
        resolution = resolve_doi(ref.doi, resolvers, args.mailto)
        if not resolution.resolved:
            problems += 1
            print(f"[broken]  {ref.key}: DOI did not resolve at any registry ({ref.doi})")
            continue
        finding = verify(ref, resolution.record)
        via = "" if resolution.source == "crossref" else f" (via {resolution.source})"
        if finding.status == "ok":
            print(f"[ok]      {ref.key}{via}")
        else:
            problems += 1
            print(f"[suspect] {ref.key}{via}")
            for issue in finding.issues:
                print(f"            - {issue}")
    print(f"\n{len(refs)} checked, {problems} need review.")
    return 1 if problems else 0


def _order_citations(body: str, section: str, manuscript: str) -> int:
    """Citation [n] numbering vs the reference list. Returns 1 on a problem, else 0."""
    found = anchors.find_numeric_anchors(body)
    listed = ordering.numbered_entries(section)

    # A Word auto-numbered list carries no literal numbers in the text; infer 1..N from
    # the entry count so truncation and orphans are still caught (order is not assessable).
    inferred = False
    if not listed:
        n = len(audit.split_entries(section))
        if n >= 3:
            listed = list(range(1, n + 1))
            inferred = True

    if not found:
        print(
            "citations: no in-text markers found (bracketed or superscript); "
            "nothing to order-check."
        )
        return 0
    if not listed:
        print("citations: no reference list found; cannot compare numbering.")
        return 1

    report = ordering.check(found, listed, ordered_list=not inferred)
    if inferred:
        print(f"  (reference numbers inferred from {len(listed)} entries; auto-numbered list)\n")
    print(f"in-text citations: {len(report.cited)} distinct, first appears {report.cited[:8]}...")
    print(f"reference list:    {len(listed)} entries\n")
    if report.status == "ok":
        print("[ok] in-text numbering and the reference list agree and are in order.")
    else:
        print("[suspect] numbering problems:")
        for issue in report.issues():
            print(f"  - {issue}")

    if manuscript.lower().endswith(".docx"):
        managed = anchors.field_citation_count(docx.document_xml(manuscript))
        if managed == 0:
            print(
                "\n  note: no Zotero field codes -- every citation is unmanaged typed text, "
                "so numbering cannot be regenerated and will drift on edit."
            )
    return 1 if report.status != "ok" else 0


def _order_floats(body: str) -> int:
    """Figure and table caption numbering vs the body's references. 1 on a problem."""
    problems = 0
    for kind in ("table", "figure"):
        report = floats.check_floats(body, kind)
        if not report.captions and not report.referenced:
            continue  # the manuscript has none of this float
        label = kind + "s"
        n = len(set(report.captions))
        line = f"\n{label}: {n} captioned {sorted(set(report.captions))}"
        if report.referenced:
            line += f", {len(report.referenced)} referenced"
        print(line)
        if report.status == "ok":
            print(f"[ok] {label} are numbered 1..{n} and references resolve.")
        else:
            problems += 1
            print(f"[suspect] {label} numbering problems:")
            for issue in report.issues():
                print(f"  - {issue}")
        for warning in report.warnings():
            print(f"  warning: {warning}")
    return 1 if problems else 0


def _order_crossrefs(full_text: str, body: str) -> int:
    """Section-reference resolvability and an SI-float inventory. 1 on a dangling section."""
    report = xref.check_crossrefs(full_text, body)
    if not report.section_refs and not report.si_floats:
        return 0
    print(f"\nsection references: {len(report.section_refs)} in text")
    if not report.headings_numbered and report.section_refs:
        print("  note: headings are unnumbered, so section references are not resolved.")
    elif report.status == "ok":
        print("[ok] every section reference resolves to a numbered heading.")
    else:
        print(f"[suspect] {len(report.dangling_sections)} section reference(s) resolve to nothing:")
        for n in report.dangling_sections:
            print(f"  - Section {n} referenced but no such numbered heading")
    if report.si_floats:
        print(f"  note: supplementary floats referenced (confirm the SI has them): "
              f"{', '.join(report.si_floats)}")
    return 1 if report.dangling_sections else 0


def _read_for_ordering(path: str) -> str:
    """Ordering text: on a .docx, superscript (ACS-style) citations become [n] markers."""
    return docx.text_for_ordering(path) if path.lower().endswith(".docx") else _read_plain(path)


def order(args: argparse.Namespace) -> int:
    text = _read_for_ordering(args.manuscript)
    section = audit.references_section(text)
    has_refs = bool(section) and section in text and section != text
    end = text.find(section) if has_refs else len(text)
    start = audit.main_text_start(text)
    body = text[start:end]

    if start > 0:
        print("(citation numbering counted from the Introduction; front matter excluded)\n")
    cite_rc = _order_citations(body, section, args.manuscript)
    float_rc = _order_floats(body)
    xref_rc = _order_crossrefs(text[:end], body)
    return 1 if (cite_rc or float_rc or xref_rc) else 0


def renumber_cmd(args: argparse.Namespace) -> int:
    from pathlib import Path

    if args.manuscript.lower().endswith(".docx"):
        print("renumber needs the markdown/text source (it rewrites citation numbers).")
        return 1
    text = _read_plain(args.manuscript)
    result = renumbering.renumber_markdown(text)
    if not result.remap:
        print("no in-text citations found; nothing to renumber.")
        return 0

    changed = [(o, n) for o, n in sorted(result.remap.items()) if o != n]
    print(f"{len(result.remap)} references, numbered by first appearance from the Introduction.")
    if not changed:
        print("[ok] already in citation order; nothing to renumber.")
    else:
        print(f"[suspect] {len(changed)} reference(s) out of citation order (old -> new):")
        for old, new in changed:
            print(f"  [{old}] -> [{new}]")
    for w in result.warnings:
        print(f"  warning: {w}")

    if args.apply and result.changed:
        Path(args.manuscript).write_text(result.text, encoding="utf-8")
        print(f"\napplied -> {args.manuscript}")
    elif changed:
        print("\nrerun with --apply to rewrite the file.")
    return 1 if changed else 0


def audit_cmd(args: argparse.Namespace) -> int:
    xml = docx.document_xml(args.manuscript)
    citations = fields.extract_citations(xml)
    if not citations:
        print("No Zotero citation field codes found. This .docx was not authored with the Zotero")
        print("plugin, or its citations are typed text. Use `argus order` (numbering) and")
        print("`argus check` (metadata on exported references) instead.")
        return 1

    result = crosscheck.audit(citations, mailto=args.mailto)
    print(f"{len(result.references)} keyed references from {len(citations)} in-text citations\n")
    for r in result.references:
        ok = r.metadata_status in ("ok", "no-doi") and r.number_ok
        via = "" if r.source in ("", "crossref") else f" via {r.source}"
        print(
            f"[{r.canonical_number:>3}] {'ok  ' if ok else 'FLAG'} {r.key}  "
            f"\"{r.title[:52]}\"  ({r.metadata_status}{via})"
        )
        for issue in r.metadata_issues:
            print(f"        - {issue}")
        if not r.number_ok:
            print(f"        - printed as {r.printed_numbers}, expected {r.canonical_number}")
    if result.numbering_issues:
        print("\nnumbering:")
        for issue in result.numbering_issues:
            print(f"  - {issue}")
    print(f"\nstatus: {result.status}")
    return 0 if result.status == "ok" else 1


def _typography_docx(path: str) -> int:
    r = typography.check_docx(path)
    print(f"styled runs: {r.superscript_runs} superscript, {r.subscript_runs} subscript")
    print(
        f"equations: {r.math_objects} math object(s), "
        f"{r.equation_references} in-text reference(s)"
    )
    if r.equations_may_be_images:
        print(
            "  note: equations are referenced but no equation objects were found -- they may "
            "be pasted images or plain text, not real OMML equations."
        )
    if r.status == "ok":
        print("[ok] no literal caret left in the rendered text.")
        return 0
    print(f"[suspect] {len(r.leftover_carets)} literal caret(s) survived the build:")
    for snip in r.leftover_carets[:20]:
        print(f"  - ...{snip}...")
    return 1


def _typography_source(path: str) -> int:
    text = _read_plain(path)
    # An unclosed caret is a build bug anywhere, including a reference. The flat-
    # descriptor / bare-formula warnings, though, would nag about every compound in a
    # bibliography title, which is Zotero-managed (rule 6) and left flat by CSL -- so
    # scope those to the body, the same body/references split `argus order` uses.
    section = audit.references_section(text)
    has_refs = bool(section) and section in text and section != text
    body = text[: text.find(section)] if has_refs else text

    errors = typography.find_unclosed_superscripts(text)
    warnings = (
        typography.find_flat_subscripts(body)
        + typography.find_flat_charges(body)
        + typography.find_bare_formulas(body)
        + typography.find_degree_glyph(body)
    )
    warnings.sort(key=lambda x: x.line)

    if not errors and not warnings:
        print("[ok] no unclosed superscripts or flat descriptors found.")
        if has_refs:
            _note_reference_formulas(section)
        return 0
    if errors:
        print(f"[suspect] {len(errors)} unclosed superscript(s) (pandoc renders as literal '^'):")
        for x in errors:
            print(f"  line {x.line}: {x.token!r} -> {x.suggestion!r}   ...{x.snippet}...")
    if warnings:
        print(f"\n{len(warnings)} descriptor/formula warning(s) in the body (confirm first):")
        for x in warnings:
            print(f"  line {x.line}: {x.token!r} -> {x.suggestion!r}   ...{x.snippet}...")
    if has_refs:
        _note_reference_formulas(section)
    return 1 if errors else 0


def _note_reference_formulas(section: str) -> None:
    n = len(typography.find_bare_formulas(section))
    if n:
        print(
            f"\n  note: {n} flat formula(s) in the reference list not shown -- fix these in "
            "Zotero (CSL nocase/<sub>), not by hand-editing the bibliography."
        )


def typography_cmd(args: argparse.Namespace) -> int:
    if args.manuscript.lower().endswith(".docx"):
        return _typography_docx(args.manuscript)
    return _typography_source(args.manuscript)


def format_cmd(args: argparse.Namespace) -> int:
    if not args.manuscript.lower().endswith(".docx"):
        print("format needs a .docx (it reads paragraph size, spacing, and alignment).")
        return 1
    report = formatting.check_formatting(docx.document_xml(args.manuscript))
    if report.majority is None:
        print(f"formatting: only {report.prose_count} body paragraph(s); nothing to compare.")
        return 0
    print(f"body prose: {report.prose_count} paragraphs (reference list excluded)")
    print(f"dominant format: {report.majority.describe()}\n")
    if report.status == "ok" and not report.notes():
        print("[ok] every body paragraph matches the dominant format.")
        return 0
    if report.drift_groups:
        print(f"[suspect] {len(report.drift_groups)} paragraph format(s) lost the body formatting:")
        for issue in report.issues():
            print(f"  - {issue}")
    for note in report.notes():
        print(f"  note (set differently, confirm intended): {note}")
    return 1 if report.status != "ok" else 0


def statements_cmd(args: argparse.Namespace) -> int:
    text = _read_text(args.manuscript)
    report = statements.check_statements(text, journal=args.journal)
    which = args.journal or "default set (conflict-of-interest, data availability)"
    print(f"required statements: {which}\n")
    for f in report.findings:
        mark = "ok  " if f.ok else "FLAG"
        where = f" (line {f.line})" if f.present else ""
        print(f"[{mark}] {f.label}{where}")
        for issue in f.issues:
            print(f"        - {issue}")
    for issue in report.extra_issues:
        print(f"[FLAG] {issue}")
    for w in statements.byline_warnings(text):
        print(f"  warning (byline): {w}")
    print(f"\nstatus: {report.status}")
    return 0 if report.status == "ok" else 1


def editorial_cmd(args: argparse.Namespace) -> int:
    variant = ""
    if args.journal and args.journal in policy.JOURNALS:
        variant = policy.JOURNALS[args.journal].spelling
    # Superscript citations come through as "[n]" so a collapsed range reads like a bracketed one.
    text = _read_for_ordering(args.manuscript)
    report = editorial.check_editorial(text, journal_variant=variant or None)
    if not report.issues:
        print(f"[ok] no editorial-checklist issues found (spelling target: {report.variant}).")
        return 0
    if report.errors:
        print(f"[suspect] {len(report.errors)} firm-rule violation(s):")
        for x in report.errors:
            print(f"  line {x.line}: [{x.kind}] {x.token!r} -> {x.suggestion}   ...{x.snippet}...")
    if report.warnings:
        print(f"\n{len(report.warnings)} preference warning(s) (confirm before applying):")
        for x in report.warnings:
            print(f"  line {x.line}: [{x.kind}] {x.token!r} -> {x.suggestion}   ...{x.snippet}...")
    return 1 if report.errors else 0


def units_cmd(args: argparse.Namespace) -> int:
    text = _read_text(args.manuscript)
    report = units.check_units(text, journal=args.journal)
    comp = ", ".join(f"{k} x{v}" for k, v in report.composition.items()) or "none"
    print(f"temperature: {report.degc} degC, {report.kelvin} K   composition: {comp}\n")
    if not report.findings:
        print("[ok] temperature and composition units are consistent.")
        return 0
    errors = [f for f in report.findings if f.severity == "error"]
    if errors:
        print(f"[suspect] {len(errors)} unit inconsistency(ies):")
        for f in errors:
            print(f"  - [{f.kind}] {f.message}")
    for f in report.findings:
        if f.severity == "warning":
            print(f"  warning: [{f.kind}] {f.message}")
    return 1 if errors else 0


def consistency_cmd(args: argparse.Namespace) -> int:
    text = _read_text(args.manuscript)
    report = consistency.check_consistency(text)
    if not report.checked:
        print("no Introduction heading found; cannot separate abstract from body.")
        return 0
    print(f"abstract quantities tracked: {len(report.abstract_quantities)}")
    if report.abstract_quantities:
        print("  " + ", ".join(report.abstract_quantities))
    if not report.mismatches:
        print("\n[ok] every distinctive abstract value appears in the body.")
        return 0
    print(f"\n[suspect] {len(report.mismatches)} abstract value(s) not found in the body (review):")
    for m in report.mismatches:
        print(f"  - {m.text!r} (a revision may have desynced the abstract from the body)")
    return 1


def repro_cmd(args: argparse.Namespace) -> int:
    report = repro.check_repro(args.repo)
    print(f"README references {len(report.referenced)} file(s).")
    if report.status == "ok" and not report.uncatalogued and not report.mentioned_missing:
        print("[ok] every referenced file exists and every artifact is documented.")
        return 0
    if report.dangling:
        print(f"[suspect] {len(report.dangling)} README reference(s) point to a missing file:")
        for rel in report.dangling:
            print(f"  - {rel} (run-command or path in the README, not in the repo)")
    for rel in report.mentioned_missing:
        print(f"  warning: {rel} mentioned in the README but not in the repo (renamed? Sol-only?)")
    for rel in report.uncatalogued:
        print(f"  warning: {rel} is in the repo but not documented in the README")
    return 1 if report.dangling else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in _SUBCOMMANDS and not argv[0].startswith("-"):
        argv = ["check", *argv]  # back-compat: `argus refs.json` means `argus check refs.json`

    parser = argparse.ArgumentParser(prog="argus", description="Verify citations and numbering.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="verify references against the registries")
    p_check.add_argument("refs", help="references file: CSL-JSON (.json) or BibTeX (.bib)")
    p_check.add_argument("--mailto", help="contact email for the registries' polite pools")
    p_check.set_defaults(func=check)

    p_order = sub.add_parser(
        "order", help="check citation, figure, and table numbering in a manuscript"
    )
    p_order.add_argument("manuscript", help="manuscript: .docx or plain text")
    p_order.set_defaults(func=order)

    p_audit = sub.add_parser(
        "audit", help="Zotero-keyed per-citation audit (metadata + number) of a .docx"
    )
    p_audit.add_argument("manuscript", help="Zotero-authored .docx (citations as field codes)")
    p_audit.add_argument("--mailto", help="contact email for the registries' polite pools")
    p_audit.set_defaults(func=audit_cmd)

    p_typo = sub.add_parser(
        "typography",
        help="find unclosed superscripts / flat subscripts in a .md source, or verify a .docx",
    )
    p_typo.add_argument("manuscript", help="pandoc markdown source (.md/.txt) or a built .docx")
    p_typo.set_defaults(func=typography_cmd)

    p_renum = sub.add_parser(
        "renumber",
        help="renumber citations to first-appearance order (from the Introduction)",
    )
    p_renum.add_argument("manuscript", help="markdown/text source with a numbered reference list")
    p_renum.add_argument(
        "--apply", action="store_true", help="rewrite the file in place (default: report only)"
    )
    p_renum.set_defaults(func=renumber_cmd)

    p_fmt = sub.add_parser(
        "format",
        help="flag body paragraphs whose size/spacing/alignment drifts from the majority",
    )
    p_fmt.add_argument("manuscript", help="a .docx manuscript")
    p_fmt.set_defaults(func=format_cmd)

    p_stmt = sub.add_parser(
        "statements", help="check front/back-matter statements (COI, AI use, data availability)"
    )
    p_stmt.add_argument("manuscript", help="manuscript: .docx or plain text")
    p_stmt.add_argument(
        "--journal", help="target journal key (JECS, ECM, JPED, Nature); sets which are required"
    )
    p_stmt.set_defaults(func=statements_cmd)

    p_edit = sub.add_parser(
        "editorial", help="Editorial checklist: banned phrasing, em-dashes, spelling"
    )
    p_edit.add_argument("manuscript", help="manuscript: .docx or plain text")
    p_edit.add_argument("--journal", help="target journal key; sets the spelling variant")
    p_edit.set_defaults(func=editorial_cmd)

    p_units = sub.add_parser(
        "units", help="temperature and composition unit consistency"
    )
    p_units.add_argument("manuscript", help="manuscript: .docx or plain text")
    p_units.add_argument("--journal", help="target journal key; sets the pinned temperature unit")
    p_units.set_defaults(func=units_cmd)

    p_cons = sub.add_parser(
        "consistency", help="check distinctive abstract values appear in the body"
    )
    p_cons.add_argument("manuscript", help="manuscript: .docx or plain text")
    p_cons.set_defaults(func=consistency_cmd)

    p_repro = sub.add_parser(
        "repro", help="check a public repro repo's README manifest against its files"
    )
    p_repro.add_argument("repo", help="path to a reproducibility repo (directory)")
    p_repro.set_defaults(func=repro_cmd)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
