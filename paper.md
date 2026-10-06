---
title: 'Argus: a command-line tool for verifying bibliographies against Crossref and detecting distorted citations'
tags:
  - Python
  - research integrity
  - citation verification
  - Crossref
  - large language models
  - reproducibility
authors:
  - name: Michael E. Bustamante
    orcid: 0009-0009-9001-8151
    affiliation: 1
affiliations:
  - name: Odinzen LLC, Houston, TX, United States
    index: 1
date: 22 June 2026
bibliography: paper.bib
---

# Summary

Argus is a command-line tool that checks the references in a manuscript against the
authoritative Crossref record for each work and reports any whose metadata does not
match. Its primary check is a bidirectional comparison of the complete author list,
including initials, which detects a failure that resolution-based checks miss: a real
article cited with one or more authors that belong to a different paper. Argus also
compares the title, year, volume, and first page. It reads CSL-JSON or BibTeX, the
formats reference managers export, depends only on the Python standard library and the
public Crossref API, and contains no language model in its verification path. A
non-zero exit status when any reference fails makes it suitable as a pre-submission or
continuous-integration check.

# Statement of need

Reference lists assembled with the help of large language models contain citations
that look correct but are not. The rate has been measured across medicine
[@bhattacharyya_2023], geography [@day_2023], and scientific writing generally
[@athaluri_2023], and the errors fall into two categories that are easily conflated:
references that are wholly fabricated, and references to real papers that carry errors
in their metadata [@walters_wilder_2023]. Both appear in broader surveys of model
hallucination [@ji_2023]. The second category is the more dangerous, because it
survives the usual checks. A citation can keep the correct title, journal, year, and
first author while carrying a co-author from a different paper, or a single wrong
initial; its DOI still resolves to a real article. A check that asks only whether the
DOI resolves, or that matches the first author and year, accepts it.

Existing tooling does not close this gap. Reference managers retrieve metadata by
identifier, and citation-consistency checkers compare in-text citations against the
reference list, but neither diffs the full author list of an existing citation against
the canonical record. That comparison is the check Argus provides.

The need generalizes beyond bibliographies. Autonomous, AI-driven research pipelines
increasingly produce results that are acted on as fact, and a system's confidence is
not evidence of correctness. For example, an autonomous laboratory reported the rapid
synthesis of dozens of inorganic compounds, with phase identification performed by an
automated analysis pipeline [@szymanski_2023]; the automated structural assignments
were subsequently questioned by domain experts and a peer-reviewed Author Correction
was issued [@alab_correction_2026]. The system is an impressive piece of engineering,
and the episode is not a criticism of its authors; it illustrates a general principle.
Where a generator's output is consequential, correctness is established by a
verification step anchored to an external source of truth, not by the generator
itself. Argus implements such a step for one well-defined problem, the integrity of a
reference list, with the resolved Crossref record as the sole authority.

# Verification method

Argus reads a CSL-JSON or BibTeX file. For each reference that carries a DOI, it
retrieves the Crossref record over HTTPS and compares the fields in Table 1.

Table 1: Fields compared against the Crossref record.

| Field        | Comparison                                                              | Distortion detected                          |
|--------------|------------------------------------------------------------------------|----------------------------------------------|
| Author list  | set membership in both directions; surname similarity >= 0.85; initials compared when a surname matches | co-author conflation, wrong initial, dropped author |
| Title        | string similarity >= 0.90                                               | paraphrased or truncated title               |
| Year         | absolute difference <= 1                                                | wrong year                                   |
| Volume       | normalized equality                                                     | wrong volume                                 |
| First page   | first page of the range, equality                                       | wrong first page                             |
| DOI          | must resolve at Crossref                                                | fabricated or unresolvable DOI               |

Authors are matched by surname, with a similarity threshold that tolerates
romanization and minor spelling variants; when a surname matches, the leading initials
are compared, so a wrong initial on a correct surname is caught. The author comparison
is bidirectional: every cited author must appear on the record, and, when the citation
lists the full set, no record author may be absent. Short "et al." citations are not
penalized for omitting authors. The authority is always the resolved Crossref record:
Argus reports discrepancies and never edits a citation or supplies a field from a
model.

Each reference is classified into one of four states (Table 2), and the process exits
with a non-zero status if any reference is not `ok`.

Table 2: Per-reference result states.

| Status    | Meaning                                                  |
|-----------|---------------------------------------------------------|
| `ok`      | every checked field matches the record                  |
| `suspect` | one or more fields disagree; the reasons are listed      |
| `no-doi`  | the entry has no DOI and cannot be verified              |
| `broken`  | the DOI did not resolve at Crossref                     |

# Installation and usage

Install from the repository:

```
pip install .
```

Export a library to CSL-JSON (in Zotero: select the items, right-click, Export Items,
CSL JSON) or use an existing BibTeX `.bib` file, then run:

```
argus refs.json --mailto you@example.org
```

The contact email is optional and places requests in Crossref's polite pool. Because
the command exits non-zero when any reference needs review, it can gate a manuscript
repository in continuous integration, for example as a step in a GitHub Actions
workflow:

```yaml
- run: pip install .
- run: argus references.json --mailto ${{ secrets.CONTACT_EMAIL }}
```

A worked example ships with the tool. Running `argus examples/demo_refs.json` checks
five real references, all of which pass, alongside three planted distortions (a
swapped co-author, a wrong initial, and a wrong volume), each reported with the field
at fault.

# Evaluation

The repository includes a benchmark, `examples/benchmark_refs.json`, of thirteen cases
built from real, Crossref-indexed papers: eleven introduced errors and two negative
controls. The results are summarized in Table 3.

Table 3: Benchmark results.

| Case                              | Argus result                |
|-----------------------------------|-----------------------------|
| Co-author conflation              | flagged (author mismatch)   |
| Dropped author (tail of list)     | flagged (author missing)    |
| Wrong first-author initial        | flagged (initials)          |
| Wrong co-author initial           | flagged (initials)          |
| Wrong volume                      | flagged (volume)            |
| Wrong first page                  | flagged (first page)        |
| Truncated title                   | flagged (title)             |
| Wrong year                        | flagged (year)              |
| Fabricated DOI                    | flagged (`broken`)          |
| Missing DOI                       | flagged (`no-doi`)          |
| Author-order swap                 | not flagged (by design)     |
| Correct reference (control)       | passed                      |
| Tolerated surname spelling variant| passed                      |

Of the eleven introduced errors, Argus flags ten. The single undetected case, a
reordering of an otherwise-correct author list, is excluded by design because the
author comparison is set-based. Neither negative control produced a false positive.

# Limitations

Argus is deliberately narrow, and several cases lie outside its scope. It compares
authors as a set, so a reordering of the correct authors is not detected. It uses the
cited DOI as the lookup key, so a citation that points to the wrong article but whose
remaining fields were made to match that article is internally consistent and passes.
Works without a DOI cannot be verified and are reported as `no-doi`, which includes
many books, datasets, and some humanities sources. Where a Crossref record is itself
incomplete or in error, Argus inherits that limitation, since it treats the record as
ground truth. Finally, Argus checks bibliographic metadata only; it does not assess
whether a cited work supports the claim it is attached to. It is therefore a targeted
verifier of citation metadata, more thorough on distorted author lists than
resolution-based checks, but not a complete citation checker.

# Testing

Argus includes a unit-test suite covering each comparison in Table 1, with a planted
failing case for every distortion it claims to detect, so the verifier is tested
against known errors rather than only against correct input. The benchmark of Table 3
is reproducible from the repository with a single command.

# Acknowledgements

Generative AI tools assisted with the implementation. The design of the verification
checks, and responsibility for their correctness, rest with the author.

# References
