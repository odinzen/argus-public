# Conventions

Python 3.10+, src layout, package `argus`. Standard library only at runtime
(Crossref over urllib); pytest and ruff for dev.

- Run `pytest` and `ruff check src tests` before committing; keep both green.
- The authority is always the resolved Crossref record. Argus compares and flags;
  it never edits a citation or fills a field from a model. No LLM in the verify path.
- New behavior gets a test, including a planted bad citation that proves the check
  fires.
