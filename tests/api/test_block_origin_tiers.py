"""Origin tiers — the user library and the project are told apart (ADR-053 §3).

``docs/specs/adr-053-personal-tool-library.md`` §2.2 and FR-001 to FR-005,
issue #1995. ``map_block_origin`` used to collapse both drop-in tiers into one
``custom`` label, so ``~/.scistudio/blocks/`` and ``{project}/blocks/`` reached
the palette indistinguishable and the user library was invisible.

Four things are pinned here, and the third and fourth are the reason the fix is
a resolver rather than a string comparison:

* A block from each directory reports its own tier, and a block whose path
  resolves to neither falls back to ``custom`` (FR-001, FR-002).
* The shared resolver serves the *type* surface through the same function with
  a different :class:`OriginSurface`, so B2's types listing cannot drift from
  the palette (FR-003, FR-005).
* Containment is decided on resolved real paths. A symlink inside a tier root
  that points outside it is not in that tier, and on Windows a path on a
  different drive is not relative to anything on this one — the case a
  ``str.startswith`` check answers wrongly and silently.
* ``BlockSummary.source`` keeps its pre-ADR-053 value. FR-002 requires existing
  consumers of ``custom`` to keep working, so the tier split rides on the
  additive ``origin`` field (FR-004) rather than on redefining a shipped one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api._block_source import (
    BLOCK_SURFACE,
    TYPE_SURFACE,
    map_block_origin,
    map_source_label,
    resolve_origin,
)
from scistudio.api.runtime import ApiRuntime
from scistudio.core.dropins import user_blocks_dir, user_types_dir

PROBE_BLOCK = '''\
from typing import Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig


class {class_name}(Block):
    """Drop-in block used to pin the ADR-053 origin split."""

    type_name: ClassVar[str] = "test.{type_suffix}"
    name: ClassVar[str] = "{type_suffix}"
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {{}}
'''


class _Spec:
    """The three registry-spec fields the resolver reads, and nothing else."""

    def __init__(self, *, file_path: str | None = None, module_path: str = "", source: str = "") -> None:
        self.file_path = file_path
        self.module_path = module_path
        self.source = source


def _write_block(directory: Path, stem: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{stem}.py"
    target.write_text(
        PROBE_BLOCK.format(class_name=stem.title().replace("_", ""), type_suffix=stem),
        encoding="utf-8",
    )
    return target


def _origins(client: TestClient) -> dict[str, str]:
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    return {block["type_name"]: block["origin"] for block in response.json()["blocks"]}


def _sources(client: TestClient) -> dict[str, str]:
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    return {block["type_name"]: block["source"] for block in response.json()["blocks"]}


# ---------------------------------------------------------------------------
# FR-001 / FR-002 — the split and its fallback, at the resolver
# ---------------------------------------------------------------------------


def test_user_library_block_resolves_to_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A block under ``~/.scistudio/blocks`` is ``user`` (FR-001)."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    path = _write_block(user_blocks_dir(), "library_block")
    spec = _Spec(file_path=str(path), source="tier1")
    assert map_block_origin(spec, project_dir=tmp_path / "proj") == "user"


def test_project_block_resolves_to_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A block under ``{project}/blocks`` is ``project`` (FR-001)."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    project = tmp_path / "proj"
    path = _write_block(project / "blocks", "project_block")
    spec = _Spec(file_path=str(path), source="tier1")
    assert map_block_origin(spec, project_dir=project) == "project"


def test_project_block_without_an_open_project_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no project open the project tier does not exist, so ``custom``."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    path = _write_block(tmp_path / "proj" / "blocks", "orphan_block")
    assert map_block_origin(_Spec(file_path=str(path), source="tier1")) == "custom"


def test_path_outside_both_roots_falls_back_to_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A drop-in reached from neither root degrades rather than breaking (FR-002)."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    stray = _write_block(tmp_path / "elsewhere", "stray_block")
    spec = _Spec(file_path=str(stray), source="tier1")
    assert map_block_origin(spec, project_dir=tmp_path / "proj") == "custom"


def test_absent_file_path_on_a_dropin_falls_back_to_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A tier-1 spec with no usable path is ``custom``, never ``package`` (FR-002)."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    spec = _Spec(module_path="_scistudio_dropin_probe_1234", source="tier1")
    assert map_block_origin(spec, project_dir=tmp_path / "proj") == "custom"


def test_builtin_and_package_labels_are_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``builtin`` and ``package`` keep their pre-ADR-053 meaning."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    assert map_block_origin(_Spec(module_path="scistudio.blocks.io.loaders", source="entry_point")) == "builtin"
    assert map_block_origin(_Spec(module_path="scistudio.blocks", source="builtin")) == "builtin"
    assert map_block_origin(_Spec(module_path="scistudio_blocks_imaging.blocks", source="entry_point")) == "package"


def test_symlink_escaping_the_user_root_is_not_in_that_tier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Containment is decided after symlinks are resolved, not before (FR-002)."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    outside = _write_block(tmp_path / "outside", "escaped_block")
    link = user_blocks_dir()
    link.mkdir(parents=True, exist_ok=True)
    link = link / "escaped_block.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted in this environment")
    assert map_block_origin(_Spec(file_path=str(link), source="tier1")) == "custom"


@pytest.mark.skipif(sys.platform != "win32", reason="drive letters are a Windows path semantic")
def test_a_different_windows_drive_is_not_relative_to_the_user_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path on another drive cannot be under either root (FR-002)."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    home_drive = Path(user_blocks_dir()).drive.rstrip(":").upper() or "C"
    other_drive = "Z" if home_drive != "Z" else "Y"
    spec = _Spec(file_path=rf"{other_drive}:\scistudio\blocks\elsewhere.py", source="tier1")
    assert map_block_origin(spec, project_dir=tmp_path / "proj") == "custom"


# ---------------------------------------------------------------------------
# FR-003 / FR-005 — one resolver, two surfaces
# ---------------------------------------------------------------------------


def test_one_resolver_serves_the_type_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same function resolves a type spec through ``TYPE_SURFACE`` (FR-003).

    The type vocabulary differs from the block vocabulary in exactly one label —
    ``core`` where blocks say ``builtin`` — and in the tier child directory.
    Everything else, including the ``custom`` fallback, is the shared behaviour,
    which is what makes a second path comparison unnecessary (FR-005).
    """
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    project = tmp_path / "proj"
    user_type = user_types_dir()
    user_type.mkdir(parents=True, exist_ok=True)
    (user_type / "library_type.py").write_text("", encoding="utf-8")
    project_type = project / "types"
    project_type.mkdir(parents=True, exist_ok=True)
    (project_type / "project_type.py").write_text("", encoding="utf-8")

    def type_origin(**kwargs: object) -> str:
        return resolve_origin(TYPE_SURFACE, project_dir=project, **kwargs)  # type: ignore[arg-type]

    assert type_origin(file_path=str(user_type / "library_type.py")) == "user"
    assert type_origin(file_path=str(project_type / "project_type.py")) == "project"
    assert type_origin(file_path=str(tmp_path / "elsewhere" / "x.py")) == "custom"
    assert type_origin(module_path="scistudio.core.types.array") == "core"
    assert type_origin(module_path="scistudio_blocks_imaging.types") == "package"
    assert type_origin(module_path="_scistudio_type_dropin_x_1_2", is_dropin=True) == "custom"


def test_the_two_surfaces_are_the_same_function() -> None:
    """FR-003 is a claim about implementation, so assert on the implementation.

    ``map_block_origin`` holds no rule of its own: it reads a block spec's
    fields and delegates. If a second path comparison is ever added for types,
    this stops being true.
    """
    assert BLOCK_SURFACE.installed_origin == "builtin"
    assert TYPE_SURFACE.installed_origin == "core"
    assert BLOCK_SURFACE.user_dir() == user_blocks_dir()
    assert TYPE_SURFACE.user_dir() == user_types_dir()


# ---------------------------------------------------------------------------
# FR-002 — the legacy label is untouched
# ---------------------------------------------------------------------------


def test_source_label_keeps_the_pre_adr_053_vocabulary() -> None:
    """``BlockSummary.source`` still collapses both tiers into ``custom``."""
    assert map_source_label("tier1") == "custom"
    assert map_source_label("entry_point") == "package"
    assert map_source_label("package_src") == "package"
    assert map_source_label("builtin") == "builtin"
    assert map_source_label("something_new") == "something_new"


# ---------------------------------------------------------------------------
# FR-004 — the block list response carries the resolved origin
# ---------------------------------------------------------------------------


def test_block_list_carries_each_tier(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A block from each directory arrives at the palette with its own origin."""
    _write_block(opened_project / "blocks", "tier_project_probe")
    _write_block(user_blocks_dir(), "tier_user_probe")
    runtime.refresh_all_registries()

    origins = _origins(client)
    assert origins["test.tier_project_probe"] == "project"
    assert origins["test.tier_user_probe"] == "user"
    assert origins["load_data"] == "builtin"

    # FR-002: the legacy field is unchanged, so a consumer reading ``source``
    # still sees one ``custom`` bucket and keeps working.
    sources = _sources(client)
    assert sources["test.tier_project_probe"] == "custom"
    assert sources["test.tier_user_probe"] == "custom"
    assert sources["load_data"] == "builtin"


def test_block_schema_and_source_endpoints_agree_with_the_palette(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """FR-019 needs one answer, so every block-facing response resolves the same.

    The source viewer is promotion entry point E1 (§6.2), and it decides whether
    to offer promotion from the origin it was handed. A viewer that says
    ``custom`` while the palette says ``project`` would offer the action in one
    place and hide it in the other.
    """
    _write_block(opened_project / "blocks", "tier_schema_probe")
    runtime.refresh_all_registries()

    schema = client.get("/api/blocks/test.tier_schema_probe/schema")
    assert schema.status_code == 200
    assert schema.json()["origin"] == "project"

    source = client.get("/api/blocks/test.tier_schema_probe/source")
    assert source.status_code == 200
    assert source.json()["origin"] == "project"


def test_a_promoted_block_reads_as_user_afterwards(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """FR-019: promotion is offered for ``project`` only, so promotion must move it.

    A user-library block is also tier-1 with a resolvable ``file_path``, so the
    origin field is the only thing that distinguishes an already-promoted block
    from a promotable one.
    """
    project_copy = _write_block(opened_project / "blocks", "tier_promote_probe")
    runtime.refresh_all_registries()
    assert _origins(client)["test.tier_promote_probe"] == "project"

    promoted = user_blocks_dir()
    promoted.mkdir(parents=True, exist_ok=True)
    (promoted / "tier_promote_probe.py").write_text(
        project_copy.read_text(encoding="utf-8").replace("tier_promote_probe", "tier_promoted_probe"),
        encoding="utf-8",
    )
    runtime.refresh_all_registries()
    assert _origins(client)["test.tier_promoted_probe"] == "user"
