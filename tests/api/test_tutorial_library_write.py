"""Saving to My Library from inside a tutorial writes to the scoped library.

``docs/specs/adr-053-learning-center.md`` FR-070 and FR-071. The scoped library
exists because one designed scenario has the user save a custom type to My
Library so the next scenario can reuse it, and that must not deposit a teaching
type into every real project the user opens afterwards.

The read side resolved through
:func:`scistudio.core.dropins.library_root_for_project` from the start; the
write path predated it and bound ``user_blocks_dir`` / ``user_types_dir``
directly. The save therefore went to ``~/.scistudio`` while the scan looked in
the tutorial library — which polluted the user's real library with teaching
files that survived clearing tutorial data, and left ``library_contains``
unable to become true, because the two halves were looking at different
directories.

Every test here drives the HTTP endpoint. The bug was invisible to a test that
called the resolver directly, which is exactly how it survived.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.core import dropins
from scistudio.tutorials import projects as tutorial_projects
from scistudio.tutorials.projects import TutorialKey

TEACHING_BLOCK = '''\
from typing import Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig


class TeachingProbe(Block):
    """Block saved to My Library during a tutorial."""

    type_name: ClassVar[str] = "test.teaching_probe"
    name: ClassVar[str] = "teaching_probe"
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {}
'''

TEACHING_TYPE = '''\
from scistudio.core.types.base import DataObject


class TeachingProbeType(DataObject):
    """Type saved to My Library during a tutorial."""
'''

WELCOME = TutorialKey.core("welcome-to-scistudio")


def _put(client: TestClient, *, target: str, filename: str, content: str) -> httpx.Response:
    return client.put(
        "/api/user-library/file",
        params={"target": target, "filename": filename},
        json={"content": content},
    )


def _get(client: TestClient, *, target: str, filename: str) -> httpx.Response:
    return client.get("/api/user-library/file", params={"target": target, "filename": filename})


@pytest.fixture
def tutorial_project(client: TestClient, runtime: ApiRuntime) -> Path:
    """Create and open a tutorial project, as starting a tutorial does."""
    plan = tutorial_projects.plan_tutorial_project(WELCOME, "Welcome To SciStudio")
    tutorial_projects.ensure_tutorial_parent()
    tutorial_projects.ensure_scoped_library()
    project = runtime.create_project(
        plan.name,
        plan.description,
        str(plan.parent),
        dir_name=plan.dir_name,
        tutorial_source_kind=WELCOME.source_kind,
        tutorial_source_id=WELCOME.source_id,
        tutorial_id=WELCOME.tutorial_id,
    )
    return Path(project.path)


@pytest.fixture
def real_project(client: TestClient, project_parent: Path) -> Path:
    """Create and open a project of the user's own."""
    response = client.post(
        "/api/projects/",
        json={"name": "My Analysis", "description": "real work", "path": str(project_parent)},
    )
    assert response.status_code == 200
    return Path(response.json()["path"])


# ---------------------------------------------------------------------------
# FR-070 / FR-071 — the save follows the open project
# ---------------------------------------------------------------------------


def test_a_save_from_a_tutorial_lands_in_the_scoped_library(client: TestClient, tutorial_project: Path) -> None:
    """FR-070, and the pollution FR-071 exists to prevent."""
    response = _put(client, target="blocks", filename="teaching_probe.py", content=TEACHING_BLOCK)

    assert response.status_code == 200, response.text
    scoped = dropins.tutorial_library_dir() / "blocks" / "teaching_probe.py"
    assert scoped.is_file()
    assert Path(response.json()["path"]) == scoped
    # The user's real library is untouched. This is the assertion the finding
    # was about: a teaching block here would be scanned into every project the
    # reader opened afterwards, and would survive clearing tutorial data.
    assert not (dropins.user_blocks_dir() / "teaching_probe.py").exists()


def test_a_type_save_from_a_tutorial_lands_in_the_scoped_library(client: TestClient, tutorial_project: Path) -> None:
    """Both tiers swap, not just blocks — the scenario saves a custom *type*."""
    response = _put(client, target="types", filename="teaching_probe_type.py", content=TEACHING_TYPE)

    assert response.status_code == 200, response.text
    assert (dropins.tutorial_library_dir() / "types" / "teaching_probe_type.py").is_file()
    assert not (dropins.user_types_dir() / "teaching_probe_type.py").exists()


def test_a_save_from_a_real_project_still_lands_in_the_real_library(client: TestClient, real_project: Path) -> None:
    """FR-071 is one-sided: nothing about the ordinary path changes."""
    response = _put(client, target="blocks", filename="teaching_probe.py", content=TEACHING_BLOCK)

    assert response.status_code == 200, response.text
    assert (dropins.user_blocks_dir() / "teaching_probe.py").is_file()
    assert not (dropins.tutorial_library_dir() / "blocks" / "teaching_probe.py").exists()


def test_a_save_with_no_project_open_lands_in_the_real_library(client: TestClient) -> None:
    """No open project is the real-library case, not an error."""
    response = _put(client, target="blocks", filename="teaching_probe.py", content=TEACHING_BLOCK)

    assert response.status_code == 200, response.text
    assert (dropins.user_blocks_dir() / "teaching_probe.py").is_file()


def test_the_write_root_is_the_directory_the_registry_scans(
    client: TestClient, tutorial_project: Path, real_project: Path
) -> None:
    """The invariant that makes the two halves agree by construction.

    The user tier the registries scan is the last entry of the drop-in scan
    dirs. The write has to land in exactly that directory, in both contexts, or
    a save is once again invisible to the scan that follows it.
    """
    for project, source, filename in (
        (real_project, TEACHING_BLOCK, "from_real.py"),
        (tutorial_project, TEACHING_BLOCK, "from_tutorial.py"),
    ):
        assert client.get(f"/api/projects/{project}").status_code == 200
        response = _put(client, target="blocks", filename=filename, content=source)
        assert response.status_code == 200, response.text
        assert Path(response.json()["path"]).parent == dropins.block_scan_dirs(project)[-1]


# ---------------------------------------------------------------------------
# The probe has to look where the write goes
# ---------------------------------------------------------------------------


def test_the_existence_probe_is_scoped_to_the_same_library(
    client: TestClient, runtime: ApiRuntime, tutorial_project: Path, real_project: Path
) -> None:
    """A collision check against the wrong library reports the wrong file.

    ``GET /api/user-library/file`` is the probe the new-file and promotion flows
    run before writing, so it takes the runtime for the same reason the write
    does.
    """
    assert client.get(f"/api/projects/{tutorial_project}").status_code == 200
    assert _put(client, target="blocks", filename="teaching_probe.py", content=TEACHING_BLOCK).status_code == 200
    assert _get(client, target="blocks", filename="teaching_probe.py").status_code == 200

    assert client.get(f"/api/projects/{real_project}").status_code == 200
    assert _get(client, target="blocks", filename="teaching_probe.py").status_code == 404


def test_clearing_removes_the_teaching_save_and_keeps_the_real_one(
    client: TestClient, runtime: ApiRuntime, tutorial_project: Path, real_project: Path
) -> None:
    """FR-073, now that a save can actually reach the scoped library.

    Before the fix this test could not be written: the teaching file was in
    ``~/.scistudio``, which clearing does not touch and must not.
    """
    assert client.get(f"/api/projects/{real_project}").status_code == 200
    assert _put(client, target="blocks", filename="my_own.py", content=TEACHING_BLOCK).status_code == 200

    assert client.get(f"/api/projects/{tutorial_project}").status_code == 200
    assert _put(client, target="blocks", filename="teaching_probe.py", content=TEACHING_BLOCK).status_code == 200

    tutorial_projects.clear_tutorial_data()

    assert not (dropins.tutorial_library_dir() / "blocks" / "teaching_probe.py").exists()
    assert (dropins.user_blocks_dir() / "my_own.py").is_file()


# ---------------------------------------------------------------------------
# FR-047 — ``library_contains`` can now become true
# ---------------------------------------------------------------------------


def test_library_contains_sees_a_block_saved_during_a_tutorial(
    client: TestClient, runtime: ApiRuntime, tutorial_project: Path
) -> None:
    """The end-to-end check that proves both halves agree.

    The save goes through the HTTP endpoint and the judgement goes through the
    real product state the tutorial routes build, so nothing here stubs the gap
    the finding was about. While the write bound the user library directly this
    condition could never become true: the file the scan looked for was in
    another directory entirely.
    """
    from scistudio.api.routes.tutorials import _ApiProductState, _RecordedSignals
    from scistudio.tutorials.conditions import evaluate, parse_condition

    assert _put(client, target="blocks", filename="teaching_probe.py", content=TEACHING_BLOCK).status_code == 200

    state = _ApiProductState(
        runtime=runtime,
        recorded=_RecordedSignals(),
        project_dir=runtime.project_dir,
        tutorial_library_dir=dropins.tutorial_library_dir(),
    )

    assert ("block", "test.teaching_probe") in state.library_entries()
    assert evaluate(parse_condition({"library_contains": {"kind": "block", "name": "test.teaching_probe"}}), state)
    # And a name nobody saved stays false, so the term is judging rather than
    # answering true for everything.
    assert not evaluate(parse_condition({"library_contains": {"kind": "block", "name": "test.absent"}}), state)


def test_library_contains_sees_a_type_saved_during_a_tutorial(
    client: TestClient, runtime: ApiRuntime, tutorial_project: Path
) -> None:
    """The other kind the scoped library holds (FR-070)."""
    from scistudio.api.routes.tutorials import _ApiProductState, _RecordedSignals
    from scistudio.tutorials.conditions import evaluate, parse_condition

    assert _put(client, target="types", filename="teaching_probe_type.py", content=TEACHING_TYPE).status_code == 200

    state = _ApiProductState(
        runtime=runtime,
        recorded=_RecordedSignals(),
        project_dir=runtime.project_dir,
        tutorial_library_dir=dropins.tutorial_library_dir(),
    )

    assert evaluate(parse_condition({"library_contains": {"kind": "type", "name": "TeachingProbeType"}}), state)


def test_library_contains_stays_false_for_a_save_from_a_real_project(
    client: TestClient, runtime: ApiRuntime, real_project: Path
) -> None:
    """FR-071 from the judging side.

    A block the user saved to their own library is not in the tutorial library,
    so a tutorial step waiting on it must not be satisfied by work done outside
    the tutorial.
    """
    from scistudio.api.routes.tutorials import _ApiProductState, _RecordedSignals
    from scistudio.tutorials.conditions import evaluate, parse_condition

    assert _put(client, target="blocks", filename="teaching_probe.py", content=TEACHING_BLOCK).status_code == 200

    state = _ApiProductState(
        runtime=runtime,
        recorded=_RecordedSignals(),
        project_dir=runtime.project_dir,
        tutorial_library_dir=dropins.tutorial_library_dir(),
    )

    assert not evaluate(parse_condition({"library_contains": {"kind": "block", "name": "test.teaching_probe"}}), state)
