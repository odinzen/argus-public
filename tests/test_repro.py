from argus import repro

README = """\
# Repro

## Scripts
| File | What it computes |
|------|------------------|
| `exact_entropy.py` | Core calculator. |
| `figures/make_figures.py` | Regenerates the figures. |

Parameter ledger is `params.json`.
"""


def _repo(tmp_path, files, readme=README):
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    for rel in files:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# code\n", encoding="utf-8")
    return str(tmp_path)


def test_all_referenced_present_and_documented(tmp_path):
    repo = _repo(tmp_path, ["exact_entropy.py", "figures/make_figures.py", "params.json"])
    r = repro.check_repro(repo)
    assert r.status == "ok"
    assert r.dangling == [] and r.uncatalogued == []


def test_dangling_readme_reference_flagged(tmp_path):
    # README names figures/make_figures.py but the file is missing.
    repo = _repo(tmp_path, ["exact_entropy.py", "params.json"])
    r = repro.check_repro(repo)
    assert "figures/make_figures.py" in r.dangling
    assert r.status == "suspect"


def test_uncatalogued_script_warned(tmp_path):
    repo = _repo(
        tmp_path,
        ["exact_entropy.py", "figures/make_figures.py", "params.json", "secret_scratch.py"],
    )
    r = repro.check_repro(repo)
    assert r.status == "ok"  # a warning, not a failure
    assert "secret_scratch.py" in r.uncatalogued


def test_infrastructure_files_ignored(tmp_path):
    repo = _repo(
        tmp_path,
        ["exact_entropy.py", "figures/make_figures.py", "params.json", "__init__.py"],
    )
    (tmp_path / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    r = repro.check_repro(repo)
    assert r.uncatalogued == []  # __init__.py and requirements.txt are infrastructure


def test_basename_mention_counts_as_documented(tmp_path):
    # A script mentioned by bare name in prose (not backticked path) still counts.
    readme = README + "\nWe also ship survey.py for the spinel survey.\n"
    repo = _repo(tmp_path, ["exact_entropy.py", "figures/make_figures.py", "params.json",
                            "survey.py"], readme=readme)
    r = repro.check_repro(repo)
    assert "survey.py" not in r.uncatalogued


def test_bare_prose_mention_missing_is_a_warning_not_failure(tmp_path):
    # A bare basename dropped in prose (a Sol batch) that is not shipped: warn, do not fail.
    readme = README + "\nThe k-point batch (`kconv_on_sol.py`) was run on Sol.\n"
    repo = _repo(tmp_path, ["exact_entropy.py", "figures/make_figures.py", "params.json"],
                 readme=readme)
    r = repro.check_repro(repo)
    assert r.status == "ok"
    assert "kconv_on_sol.py" in r.mentioned_missing
    assert "kconv_on_sol.py" not in r.dangling


def test_bare_run_command_resolves_in_subdir(tmp_path):
    # README does "cd code; python stability_screen.py"; the file lives in code/.
    readme = README + "\n```\ncd code\npython stability_screen.py\n```\n"
    repo = _repo(
        tmp_path,
        ["exact_entropy.py", "figures/make_figures.py", "params.json", "code/stability_screen.py"],
        readme=readme,
    )
    r = repro.check_repro(repo)
    assert "stability_screen.py" not in r.dangling
    assert "stability_screen.py" not in r.mentioned_missing
    assert r.status == "ok"


def test_run_command_missing_is_a_failure(tmp_path):
    # A name inside a fenced run block is a hard claim it exists.
    readme = README + "\n```\npython survey.py\n```\n"
    repo = _repo(tmp_path, ["exact_entropy.py", "figures/make_figures.py", "params.json"],
                 readme=readme)
    r = repro.check_repro(repo)
    assert "survey.py" in r.dangling
    assert r.status == "suspect"


def test_results_output_json_not_required_to_be_documented(tmp_path):
    repo = _repo(
        tmp_path,
        ["exact_entropy.py", "figures/make_figures.py", "params.json", "run_results.json"],
    )
    r = repro.check_repro(repo)
    assert "run_results.json" not in r.uncatalogued


def test_referenced_paths_extraction():
    paths = repro.referenced_paths(README)
    assert "exact_entropy.py" in paths
    assert "figures/make_figures.py" in paths
    assert "params.json" in paths
