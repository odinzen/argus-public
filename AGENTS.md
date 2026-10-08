# Instructions for AI assistants using Argus

Argus verifies a bibliography against Crossref (and other DOI registries) and checks a manuscript's
citation numbering. Use it when a person asks you to check, verify, or clean up references.

## Install

```
pip install "git+https://github.com/odinzen/argus-public.git"
```

Python 3.10 or newer, standard library only. Argus must be able to reach https://api.crossref.org;
in a sandbox without internet access it cannot verify anything, so say so instead of guessing.

## Commands

| Task | Command |
|---|---|
| Verify each reference against its registry record | `argus check refs.json --mailto you@example.org` (CSL-JSON or BibTeX) |
| Check in-text numbering against the reference list, plus figure, table and section references | `argus order manuscript.docx` (or a plain-text or Markdown file) |
| Per-citation audit of a Word file written with the Zotero plugin | `argus audit manuscript.docx` |
| Renumber citations into first-appearance order | `argus renumber draft.md` (report only; `--apply` rewrites the file) |

A reference manager exports CSL-JSON: in Zotero, select the items, right-click, Export Items,
CSL JSON. Try `argus check examples/demo_refs.json` to see every status.

## Reading the result

| Status | Meaning | What to do |
|---|---|---|
| `ok` | every checked field matches the record | nothing |
| `suspect` | a field disagrees; the reason is listed | show the person the field and the registry value |
| `no-doi` | no DOI, cannot be verified | ask for a DOI or a source |
| `broken` | the DOI did not resolve at any registry | the DOI is wrong or the work is unregistered |

The exit code is non-zero when anything needs review.

## Rules

- The registry record is the authority. Never correct a reference from memory or by generating
  plausible metadata: a model-written author list is exactly the error Argus exists to catch.
- Report what Argus found and let the person decide on each fix. Do not rewrite their reference
  list or manuscript unless they ask, and then only with values taken from the registry record.
- A resolving DOI is not verification on its own; the authors, title, journal, volume, pages and
  year must match too.
