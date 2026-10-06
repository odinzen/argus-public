"""README-manifest congruence for a public reproducibility repo.

These repos ship the scripts that regenerate a paper's numbers and figures, and a README
that lists what each one does. The figures themselves are regenerated, not committed, so
there is nothing to diff against an image. What drifts is the README: a script gets renamed
and the README still names the old one, or a new script lands and never makes the table.
Either way the "run these to reproduce" contract is broken, and a reader hits it before we
do.

This reads the README as the manifest and checks it against the files present. A referenced
file that does not exist is a dangling entry (fail); a script or data file in the repo that
the README never mentions is uncatalogued (a warning, since not every file is meant to be
run). Nothing is executed: the check respects the rule that scripts are run only by hand,
and it never needs to touch Sol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .walk import walk_files

# File extensions that carry the reproducibility payload and should be documented.
_ARTIFACT_SUFFIXES = frozenset(".py .csv .tsv .json .dat .tdb .ipynb .r .sh".split())

# Files that are infrastructure, not artifacts, so their absence from the README is fine.
_IGNORE_NAMES = frozenset(
    {
        "readme.md",
        "license",
        "license.txt",
        "license.md",
        "requirements.txt",
        "environment.yml",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "conftest.py",
        "__init__.py",
        ".gitignore",
    }
)

# A backticked token that looks like a path: it carries one of the artifact extensions,
# optionally behind a directory. `figures/make_figures.py`, `ti_o_partition.py`.
_BACKTICK_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`")

# Fenced code blocks: a name told to be run here ("python survey.py") is a hard claim it
# exists, unlike a name dropped into prose (a Sol batch, a script mentioned for context).
_FENCE = re.compile(r"```.*?```", re.DOTALL)


@dataclass
class ReproReport:
    referenced: list[str] = field(default_factory=list)  # paths the README names
    dangling: list[str] = field(default_factory=list)  # strong claim, missing (fail)
    mentioned_missing: list[str] = field(default_factory=list)  # prose mention, missing (warn)
    uncatalogued: list[str] = field(default_factory=list)  # present but undocumented (warn)

    @property
    def status(self) -> str:
        return "suspect" if self.dangling else "ok"


def _readme_path(root: Path) -> Path | None:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = root / name
        if p.exists():
            return p
    return None


_PATH_TOKEN = re.compile(r"([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)")


def referenced_paths(readme_text: str) -> list[str]:
    """Artifact-looking paths named in the README, deduped in first-seen order.

    Two sources: backticked paths anywhere, and bare tokens inside fenced code blocks (a
    "python survey.py" run command names a file the same as a backticked path does).
    """
    out: list[str] = []
    seen: set[str] = set()

    def consider(tok: str) -> None:
        if Path(tok).suffix.lower() in _ARTIFACT_SUFFIXES and tok not in seen:
            seen.add(tok)
            out.append(tok)

    for m in _BACKTICK_PATH.finditer(readme_text):
        consider(m.group(1))
    for fence in _FENCE.finditer(readme_text):
        for m in _PATH_TOKEN.finditer(fence.group()):
            consider(m.group(1))
    return out


def _is_artifact(path: Path) -> bool:
    if path.suffix.lower() not in _ARTIFACT_SUFFIXES or path.name.lower() in _IGNORE_NAMES:
        return False
    # A generated "*_results.json" is an output, not a script or ledger to be documented.
    return not path.stem.endswith("_results")


def _is_strong_claim(rel: str, code_text: str) -> bool:
    """A path with a directory, or a name inside a run-command block, is claimed to exist."""
    return "/" in rel or rel in code_text or Path(rel).name in code_text


def check_repro(root: str) -> ReproReport:
    root_path = Path(root)
    readme = _readme_path(root_path)
    if readme is None:
        # No README: everything is uncatalogued, but report it as one dangling-style note by
        # leaving referenced empty; the caller surfaces the missing README.
        report = ReproReport()
        report.uncatalogued = sorted(
            str(Path(f).relative_to(root_path)).replace("\\", "/")
            for f in walk_files(root)
            if _is_artifact(Path(f))
        )
        return report

    readme_text = readme.read_text(encoding="utf-8", errors="replace")
    referenced = referenced_paths(readme_text)
    code_text = "\n".join(m.group() for m in _FENCE.finditer(readme_text))

    files = [Path(f) for f in walk_files(root)]
    rel_paths = {str(p.relative_to(root_path)).replace("\\", "/") for p in files}
    basenames = {p.name for p in files}

    report = ReproReport(referenced=referenced)
    for tok in referenced:
        # A path with a directory must exist exactly; a bare name resolves if a file of that
        # name exists anywhere (the README's "cd code; python x.py" runs code/x.py).
        resolved = tok in rel_paths if "/" in tok else Path(tok).name in basenames
        if resolved:
            continue
        if _is_strong_claim(tok, code_text):
            report.dangling.append(tok)
        else:
            report.mentioned_missing.append(tok)

    # An artifact file is catalogued if its relative path or its basename appears in the
    # README text (a mention in prose counts, not only a backticked path).
    for p in files:
        if not _is_artifact(p) or p.samefile(readme):
            continue
        rel = str(p.relative_to(root_path)).replace("\\", "/")
        if rel not in readme_text and p.name not in readme_text:
            report.uncatalogued.append(rel)
    report.uncatalogued.sort()
    return report
