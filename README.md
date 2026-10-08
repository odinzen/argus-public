# Argus

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23198753.svg)](https://doi.org/10.5281/zenodo.23198753)

Argus checks a bibliography against Crossref and flags any citation whose metadata
does not match the record it points to. It is built for the failure most checks miss:
a citation that keeps the right first author, title, and year but carries the wrong
co-authors, a real paper wearing another's byline. A resolving DOI or a first-author
check passes that; a full author-list diff catches it.

Named for Argus Panoptes, the hundred-eyed guardian who never fully slept.

## Quickstart

```
pip install .
argus refs.json --mailto you@example.org
```

`refs.json` is a CSL-JSON file (Zotero: select items, right-click, Export Items, CSL
JSON); Argus also reads BibTeX (`refs.bib`). The `--mailto` is optional and places
requests in Crossref's polite pool.

Try it on the bundled example:

```
argus examples/demo_refs.json
```

It checks five real papers (all pass) plus three planted distortions, each reported
with the field at fault.

To install without cloning the repository:

```
pip install "git+https://github.com/odinzen/argus-public.git"
```

## Using Argus with an AI assistant (ChatGPT, Gemini, Claude)

Argus runs Python and must reach Crossref over the internet, so how you use it with an AI
assistant depends on whether the assistant can run commands with internet access.

**Assistants that run commands on your computer or in a connected workspace** (Claude Code,
OpenAI Codex, Gemini CLI, Cursor, and similar) can install and run Argus themselves. Paste:

> Install Argus with `pip install "git+https://github.com/odinzen/argus-public.git"`, read its
> AGENTS.md, then run `argus check refs.json` on my reference file and `argus order` on my
> manuscript. Report every reference that is not `ok`, with the field Argus flags and the
> registry value. Do not correct any reference from memory.

`AGENTS.md` in this repository tells the assistant how to run Argus and read its output.

**Chat websites** (chatgpt.com, gemini.google.com, claude.ai) usually run code in a sandbox
without internet access, so they cannot reach Crossref and cannot run the check. Run Argus
yourself, paste its report into the chat, and ask the assistant to help fix each flagged entry
using the registry values Argus prints. If your chat tool can reach the internet, the
instructions above apply.

Whichever you use, the registry record is the authority. An assistant that fills in a missing
author list or page range from memory reintroduces exactly the error Argus is built to catch.

## What it checks

| Field       | Comparison                                                                 |
|-------------|----------------------------------------------------------------------------|
| Author list | every cited author on the record and (for full lists) none dropped; surname similarity; initials compared when a surname matches |
| Title       | similarity, tolerant of formatting and subscripts                          |
| Year        | within one year                                                            |
| Volume      | equality, when the citation gives it                                       |
| First page  | equality, when the citation gives it                                       |
| DOI         | must resolve at Crossref                                                   |

The authority is always Crossref. Argus only compares and flags; it never edits a
citation or fills a field from a model.

## Output

Each reference is reported as one of:

| Status    | Meaning                                              |
|-----------|------------------------------------------------------|
| `ok`      | every checked field matches the record               |
| `suspect` | one or more fields disagree (the reasons are listed) |
| `no-doi`  | no DOI, cannot be verified                           |
| `broken`  | the DOI did not resolve                              |

The exit code is non-zero if any reference needs review.

## Numbering

`argus check` verifies that each reference is real and correct. `argus order` verifies a
different thing: that the manuscript's *numbering* is internally consistent. It reads a
`.docx` or plain text and checks three numbering systems in one pass.

```
argus order manuscript.docx
```

- **Citations** — in-text `[n]` markers against the reference list: a number cited but
  not listed (truncation), a list entry never cited (orphan), gaps, duplicates, and a
  list that is not in first-appearance order.
- **Figures** and **tables** — caption sequence against the body that refers to them: a
  skipped number (`Table 1, 2, 4` after a table is cut), a number on two captions, a
  `Figure 9` in the prose with only five figures captioned (dangling reference), and a
  caption out of ascending order. A float that is captioned but never referenced is
  reported as a warning, not a failure.
- **Section references** — `Section 4.3` resolved against the document's numbered headings;
  a reference to a section that does not exist is flagged. When the headings carry no
  numbers (`## Methods`, not `## 3 Methods`) the references cannot be resolved and the check
  says so instead of guessing. Supplementary floats (`Table S3`, `Fig. S2`) live in a
  separate file, so they are listed as an inventory to confirm against the SI, not failed.

A reference manager renumbers citations on edit; nothing renumbers figures, tables, or
section pointers, so these checks catch the errors that survive longest. The exit code is
non-zero if any numbering or resolution problem (not a warning or note) is found.

Citation numbering is counted **from the Introduction**. An abstract is front matter and
does not start the count, so a draft whose abstract happens to cite 1, 2, 3 in sequence is
still out of order if the running text opens on a later reference. `argus order` reports
"reference list is not in first-appearance order" when it does.

## Renumbering

`argus renumber` recomputes citation numbers by first appearance (from the Introduction)
and can apply the fix to a markdown source.

```
argus renumber draft.md          # report the old -> new map
argus renumber draft.md --apply  # rewrite in-text [n] and reorder the reference list
```

It rewrites every in-text marker (the abstract included, so its citations point at the
right entries) and reorders and relabels the reference list 1..N. Reference *text* is never
touched, only its number and position, so it is safe on a hand-numbered markdown source
where there is no reference manager to regenerate the list. A citation that appears only
before the Introduction is flagged rather than numbered.

## Typography

`argus typography` catches the super/subscript errors a pandoc markdown -> docx build
drops. The recurring one is an *unclosed* caret: `10^6`, `T^2`, `cm^-1` with the closing
`^` missing renders as a literal caret, not a superscript, so a near-final draft ships
with `10^6` sitting in the text.

```
argus typography draft.md      # scan the markdown source
argus typography draft.docx    # confirm a rebuilt docx carries the styled runs
```

On a `.md` source it reports:

- **Unclosed superscripts** (error) — `10^6`, `cm^-1`, `q^2` with no closing caret.
  Scanned everywhere, including references, since a stray caret is always a build bug.
- **Flat descriptors** (warning) — a quantity that should carry a subscript left flat:
  `dHf` -> `dH~f~`, `Cp` -> `C~p~`, `D0` -> `D~0~`, `S298` -> `S~298~`.
- **Bare formulas** (warning) — a molecular formula in prose with unsubscripted digits,
  `CO2` -> `CO~2~`, validated against real element symbols so `SGTE91` and DOI substrings
  do not fire. The `~` guards leave an already-subscripted unit like `p~CO2~` alone.
- **Degree glyph** (warning) — a temperature written with the wrong degree character,
  `25 oC` or `25 ºC` (a letter o or the masculine ordinal) instead of `25 °C`. A correct
  `°` never fires, and `degC` is left alone.

Warnings are scoped to the body; formulas inside the reference list are Zotero-managed
and only counted, not listed. On a `.docx` it counts the superscript/subscript runs and
fails if any literal caret survived the build, and reports how many equation objects
(`<m:oMath>`) it holds: an equation referenced in the prose with zero math objects was
pasted as an image or left as plain text, and is noted. The exit code is non-zero only on
an error (an unclosed caret), never on a warning or note alone.

## Formatting

`argus format` catches the paragraph that lost its formatting. Editing or inserting a
paragraph in Word (or through python-docx) silently drops its size, line spacing,
paragraph spacing and alignment, so a pasted paragraph renders single-spaced and ragged
in the middle of justified 1.5-spaced body text while reading identically in the source.
Nothing re-applies paragraph formatting the way a reference manager renumbers citations,
so this is the check that catches the drift a full manual read eventually does.

```
argus format manuscript.docx
```

The check is value-free: it does not know a journal's house size, so it takes the body's
own dominant signature (size, spacing-after, line rule, alignment) as the standard and
reports the paragraphs that depart from it. The reference list is excluded (its entries
have their own format), and headings, captions and short front-matter lines are left out
of the body vote.

- **Drift** (fails) — a paragraph *missing* the formatting the body has, or a lone
  paragraph set off on its own. The lost-formatting bug.
- **Deliberate style** (note, does not fail) — a coherent block of two or more paragraphs
  explicitly set to a different, self-consistent format, such as smaller back matter. It
  is reported for confirmation, not flagged as an error.

## Statements

`argus statements` checks the front and back matter that the reference and numbering checks
never look at: conflict-of-interest, AI-use, data-availability, funding, acknowledgement.
For each statement the target journal requires it verifies three things: it is present, it
says what it must, and it says nothing it must not.

```
argus statements manuscript.docx --journal JECS
```

- **Present** — a required statement that is simply absent is flagged, with the fix named.
- **Says what it must** — a conflict declaration names the commercial interest rather than
  "the authors declare none"; an AI-use disclosure names an *agentic* (human-gated) loop
  and never calls it "autonomous".
- **Says nothing it must not** — phrases a statement must never carry are flagged.

The Sol acknowledgement is handled specially: it is required only when the manuscript says
it used Sol, and then the paired HPC citation must be present. Byline drift (the company
rendering, the corresponding author's middle initial, the city) is reported as a warning.
Without `--journal`, the always-expected set (conflict of interest and data availability)
is used.

## Editorial checklist

`argus editorial` is the machine-checkable slice of the standing editorial checklist. Most
of that checklist is judgment and stays a human pass; the rest are literal string rules
that drift back into every draft.

```
argus editorial manuscript.docx --journal JECS
```

- **Firm rules** (fail) — an em/en dash used as a separator, "and co-workers" for "et al.",
  an "in preparation" companion citation.
- **Preferences** (warn) — the banned phrasings and their replacements, "compute" for
  "calculate", non-target spelling (American by default, set by the journal), a
  sentence-initial "But"/"And", a sentence over ~40 words, degC and K mixed in one line.

The reference list is excluded, its wording is Zotero-managed.

## Units

`argus units` checks that the paper keeps one primary temperature unit and one composition
unit, the way the checklist requires. It does not know a journal's house unit unless one is
given, so it works two ways.

```
argus units manuscript.docx --journal JECS
```

- **With `--journal`** the paper is held to that journal's pinned temperature unit (JECS is
  degC, JPED is K) and a value in the other unit is an error, except the reference list,
  which is excluded.
- **Without one** it only reports a mix, because kelvin in a rate column and degC in the
  prose can coexist and the tool cannot tell a table cell from a sentence.
- **Composition** is always advisory: at% and mol% are the same quantity, so using both is
  flagged, and wt% alongside either is a conversion the reader must be told is intentional.

## Repro repo

`argus repro` checks that a public reproducibility repo's README still matches its files.
These repos ship the scripts that regenerate a paper's numbers and figures; the figures
themselves are regenerated, not committed, so there is nothing to diff against an image.
What drifts is the README: a script is renamed and the README still names the old one, or a
new script lands and never makes the list.

```
argus repro path/to/public-repo
```

It reads the README as the manifest, taking file names from backticked paths and from the
run commands in fenced blocks.

- **Dangling** (fails) — a name in a run command (`python survey.py`) or a path with a
  directory (`figures/make_figures.py`) that is not in the repo: the reproduce contract is
  broken.
- **Mentioned but missing** (warning) — a bare file name dropped in prose that is not
  shipped, which is often a Sol-only batch or a renamed script, so it is flagged, not failed.
- **Uncatalogued** (warning) — a script or data file present but never mentioned in the
  README. Generated `*_results.json` outputs are not counted.

Nothing is executed: the check never runs a script and never needs to touch Sol.

## Consistency

`argus consistency` catches an abstract left stating a value the body has since revised (or
the reverse). It reads correct in either place alone, so only a side-by-side finds it.

```
argus consistency manuscript.docx
```

It pulls the distinctive quantities out of the abstract -- a value carrying a unit or an
uncertainty, and either a decimal or a magnitude worth tracking, so trivial small integers
like "3 phases" do not fire -- and confirms each appears in the body within a small
tolerance. A body `912.6 K` matches an abstract `912`; a body `912.6` against an abstract
`849` does not, and is reported for review. The reference list is excluded (its years and
volumes are numbers too). The abstract/body split is the Introduction heading, so a
fragment without one is skipped rather than guessed at.

## Continuous integration

Because the exit code gates on review, Argus drops into a pre-submission check or a CI
job. For example, in GitHub Actions:

```yaml
- run: pip install .
- run: argus references.json --mailto ${{ secrets.CONTACT_EMAIL }}
```

To gate Argus's own tests and lint on every push, add `.github/workflows/ci.yml`
(create it from the GitHub Actions tab, since pushing a workflow file needs a token with
the `workflow` scope):

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .[dev]
      - run: ruff check src tests
      - run: pytest -q
```

## As a pre-commit hook

A manuscript or reproducibility repo can run the checks on every commit by referencing this
repo in its `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/odinzen/argus-public
    rev: <commit-sha>
    hooks:
      - id: argus-repro                # only in a reproducibility repo
      - id: argus-editorial
        files: ^manuscript\.md$        # point each manuscript hook at your draft
      - id: argus-units
        files: ^manuscript\.md$
```

The repo-level hook (`argus-repro`) scans the tree; the manuscript hooks take
one file, so set `files:` to the draft. All hooks are defined in `.pre-commit-hooks.yaml`.

## Web UI (local only)

A no-install browser version runs the same Python core via
[Pyodide](https://pyodide.org), so there is one implementation, not two. Your
bibliography stays in the browser; only DOIs are sent to Crossref. It is for local use
only and is not publicly hosted. To run it locally:

```
python scripts/sync_web.py
python -m http.server -d web 8000   # then open http://localhost:8000
```

## Development

```
pip install -e .[dev]
pytest
ruff check src tests
```

`examples/benchmark_refs.json` is a thirteen-case benchmark (conflation, dropped
authors, wrong initials, wrong volume/page, truncated title, wrong year, fabricated
and missing DOIs, plus an author-order swap and a tolerated spelling variant) that
documents what Argus catches and what it does not.

## License

Copyright (c) 2026 Odinzen LLC. Argus is free software, released under the GNU Affero
General Public License, version 3 or (at your option) any later version (from 0.2.0;
0.1.0 was GPL-3.0-or-later). Anyone who runs a modified Argus for others over a network
must offer those users its source. See [LICENSE](LICENSE)
and [NOTICE](NOTICE). If you use Argus in published work, please cite it: doi 10.5281/zenodo.23198753 (all
versions; version 0.1.0 is 10.5281/zenodo.23198754). See CITATION.cff.
