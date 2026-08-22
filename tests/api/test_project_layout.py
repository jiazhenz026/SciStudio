"""The project scaffold is one definition, shared by both entry points (#2095).

Two commands create a project workspace -- ``ApiRuntime.create_project`` behind
the GUI's "New project", and ``scistudio init`` on the CLI -- and they each used
to carry a hand-written directory list. The lists had drifted: the CLI omitted
``data/processed`` while a comment above it claimed symmetry with the API, and
neither created the previewer or tutorial drop-in directories even though both
tiers are discovered from a project.

These tests pin the shared definition and, more importantly, pin the *agreement*
between the two entry points, since agreement is the property that silently
decayed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.project_layout import DATA_SUBDIRS, DROPIN_SUBDIRS, PROJECT_SUBDIRS
from scistudio.core.dropins import (
    BLOCKS_DIR_NAME,
    PREVIEWERS_DIR_NAME,
    TUTORIALS_DIR_NAME,
    TYPES_DIR_NAME,
)


def test_dropin_dirs_are_named_by_the_module_that_scans_them() -> None:
    """The scaffold must not respell the drop-in directory names.

    If it did, a project could offer a folder the registry does not scan -- the
    exact failure this module exists to prevent. Adding a fifth drop-in kind
    should mean adding a name to ``core.dropins`` and an entry here, not hunting
    for scaffolds.
    """
    assert DROPIN_SUBDIRS == (
        BLOCKS_DIR_NAME,
        TYPES_DIR_NAME,
        PREVIEWERS_DIR_NAME,
        TUTORIALS_DIR_NAME,
    )


def test_every_dropin_tier_has_a_scaffolded_directory() -> None:
    """Previewers and tutorials were the two missing before #2095."""
    for name in (BLOCKS_DIR_NAME, TYPES_DIR_NAME, PREVIEWERS_DIR_NAME, TUTORIALS_DIR_NAME):
        assert name in PROJECT_SUBDIRS


def test_data_subdirs_include_the_user_facing_pair_and_the_runtime_stores() -> None:
    # data/processed is the one the CLI was missing. It is deliberately empty
    # after a run -- see ARCHITECTURE.md §11.1 -- but it must exist.
    assert "data/raw" in DATA_SUBDIRS
    assert "data/processed" in DATA_SUBDIRS
    for runtime_store in ("data/zarr", "data/parquet", "data/artifacts", "data/exchange"):
        assert runtime_store in DATA_SUBDIRS


def test_project_subdirs_have_no_duplicates() -> None:
    assert len(PROJECT_SUBDIRS) == len(set(PROJECT_SUBDIRS))


def test_api_create_project_creates_every_scaffold_directory(client: TestClient, project_parent: Path) -> None:
    response = client.post(
        "/api/projects/",
        json={"name": "Layout Probe", "description": "", "path": str(project_parent)},
    )
    assert response.status_code == 200
    project_path = Path(response.json()["path"])

    missing = [d for d in PROJECT_SUBDIRS if not (project_path / d).is_dir()]
    assert not missing, f"API scaffold did not create: {missing}"


def test_cli_init_creates_the_same_directories_as_the_api(tmp_path: Path) -> None:
    """The two entry points must agree.

    Run through a subprocess rather than calling the Typer command in-process:
    ``scistudio init`` also initialises a git repository and writes agent
    assets, and the point here is the real command a user runs. Same shape as
    ``tests/cli/test_dunder_main.py``.
    """
    # The child runs in tmp_path, so a relative PYTHONPATH from the parent
    # (``PYTHONPATH=./src``, how this repo is usually run without installing)
    # would resolve against the wrong directory. Prepend the absolute repo
    # ``src`` instead; harmless where the package is already installed.
    repo_src = Path(__file__).resolve().parents[2] / "src"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(repo_src), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])])

    result = subprocess.run(
        [sys.executable, "-m", "scistudio", "init", "cli_layout_probe"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert result.returncode == 0, f"scistudio init failed: {result.stderr[-2000:]}"

    project_path = tmp_path / "cli_layout_probe"
    missing = [d for d in PROJECT_SUBDIRS if not (project_path / d).is_dir()]
    assert not missing, f"CLI scaffold did not create: {missing}"
