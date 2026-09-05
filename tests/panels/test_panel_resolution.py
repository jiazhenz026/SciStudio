"""Capability-aware resolution and the per-capability user choice (T-016).

ADR-054 spec 1, FR-048, FR-049 and SC-015, with FR-016 and A-006 as the
constraint on everything else: the routing ladder and the per-type user choice
are carried over without redesign. What changes is that a request now states the
capability it needs, and the candidates are filtered by it *before* the ladder
and the choice see them.

Without the filter, a person who chose a displaying panel as their default for
frames would find a session unable to produce from a frame at all — which is the
regression these tests exist to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.core.panels import PanelCapability
from scistudio.panels.choices import (
    CHOICES_FILENAME,
    LEGACY_CHOICES_FILENAME,
    load_choices,
    read_choice_layer,
    read_choice_layers,
    write_choice,
)
from scistudio.panels.models import OwnerKind, PanelSpec, PreviewTarget, TargetKind, UnknownTargetError
from scistudio.panels.registry import PanelRegistry
from scistudio.panels.router import PreviewRouter


def _spec(
    panel_id: str,
    *,
    target_type: str = "DataFrame",
    owner: OwnerKind = OwnerKind.PACKAGE,
    capability: PanelCapability = PanelCapability.DISPLAYING,
    priority: int = 0,
) -> PanelSpec:
    return PanelSpec(
        previewer_id=panel_id,
        owner_kind=owner,
        owner_name="test",
        target_type=target_type,
        capability=capability,
        priority=priority,
    )


def _registry(*specs: PanelSpec) -> PanelRegistry:
    registry = PanelRegistry()
    for spec in specs:
        registry.register(spec)
    return registry


def _frame() -> PreviewTarget:
    return PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="r1",
        recorded_type="DataFrame",
        type_chain=("DataObject", "DataFrame"),
    )


# ---------------------------------------------------------------------------
# FR-048 — the capability filters the candidates before the ladder
# ---------------------------------------------------------------------------


def test_a_spec_declares_displaying_unless_it_says_otherwise() -> None:
    """What is called a previewer today is the degenerate case."""
    assert _spec("p").capability is PanelCapability.DISPLAYING


def test_a_producing_request_skips_a_displaying_only_panel() -> None:
    """SC-015, first half."""
    router = PreviewRouter(
        _registry(
            _spec("pkg.table", priority=10),
            _spec("pkg.editor", capability=PanelCapability.PRODUCING, priority=0),
        )
    )

    resolution = router.resolve_request(_frame(), PanelCapability.PRODUCING)

    assert resolution.spec.previewer_id == "pkg.editor"
    assert resolution.granted_capability is PanelCapability.PRODUCING
    assert resolution.fell_back_to_display is False


def test_a_displaying_request_still_prefers_the_higher_priority_panel() -> None:
    """A-006: the ladder is carried over; the filter only removes candidates."""
    router = PreviewRouter(
        _registry(
            _spec("pkg.table", priority=10),
            _spec("pkg.editor", capability=PanelCapability.PRODUCING, priority=0),
        )
    )

    assert router.resolve_request(_frame(), PanelCapability.DISPLAYING).spec.previewer_id == "pkg.table"


def test_a_producing_panel_satisfies_a_displaying_request() -> None:
    """FR-006: one panel, and it never has to be written twice."""
    router = PreviewRouter(_registry(_spec("pkg.editor", capability=PanelCapability.PRODUCING)))

    resolution = router.resolve_request(_frame(), PanelCapability.DISPLAYING)

    assert resolution.spec.previewer_id == "pkg.editor"
    assert resolution.granted_capability is PanelCapability.DISPLAYING


def test_the_unchanged_resolve_entry_point_is_the_displaying_request() -> None:
    """FR-016/A-006: every existing caller keeps the answer it had."""
    registry = _registry(_spec("pkg.table"))
    router = PreviewRouter(registry)

    assert router.resolve(_frame()) is router.resolve_request(_frame(), PanelCapability.DISPLAYING).spec


# ---------------------------------------------------------------------------
# FR-049 — falling back to the displaying resolution with no outbound path
# ---------------------------------------------------------------------------


def test_a_producing_request_with_no_producing_panel_falls_back_to_display() -> None:
    """SC-015, second half: the data is still shown, and nothing is granted."""
    router = PreviewRouter(_registry(_spec("pkg.table")))

    resolution = router.resolve_request(_frame(), PanelCapability.PRODUCING)

    assert resolution.spec.previewer_id == "pkg.table"
    assert resolution.granted_capability is PanelCapability.DISPLAYING
    assert resolution.fell_back_to_display is True


def test_a_request_that_matches_nothing_at_all_still_raises() -> None:
    """The fallback is to the *displaying* resolution, not to silence."""
    router = PreviewRouter(_registry())

    with pytest.raises(UnknownTargetError):
        router.resolve_request(_frame(), PanelCapability.PRODUCING)


def test_the_core_fallback_serves_a_producing_request_with_no_outbound_path() -> None:
    router = PreviewRouter(_registry(_spec("core.base.fallback", target_type="DataObject", owner=OwnerKind.CORE)))

    resolution = router.resolve_request(_frame(), PanelCapability.PRODUCING)

    assert resolution.spec.previewer_id == "core.base.fallback"
    assert resolution.granted_capability is PanelCapability.DISPLAYING


# ---------------------------------------------------------------------------
# FR-049 — the choice is per type and per capability
# ---------------------------------------------------------------------------


def test_a_choice_is_read_for_the_capability_the_request_asks_for() -> None:
    """The panel a person prefers for looking at a frame and the one they
    prefer for producing from it can differ."""
    registry = _registry(
        _spec("pkg.table", priority=10),
        _spec("core.dataframe.basic", owner=OwnerKind.CORE),
        _spec("pkg.editor", capability=PanelCapability.PRODUCING),
        _spec("pkg.other_editor", capability=PanelCapability.PRODUCING, priority=5),
    )
    registry.set_panel_choices(
        {
            "displaying": {"DataFrame": "core.dataframe.basic"},
            "producing": {"DataFrame": "pkg.editor"},
        }
    )
    router = PreviewRouter(registry)

    assert router.resolve_request(_frame(), PanelCapability.DISPLAYING).spec.previewer_id == "core.dataframe.basic"
    assert router.resolve_request(_frame(), PanelCapability.PRODUCING).spec.previewer_id == "pkg.editor"


def test_a_displaying_choice_does_not_govern_a_producing_request() -> None:
    """The regression the filter exists to prevent: a displaying default must
    not make a session unable to produce from the type at all."""
    registry = _registry(
        _spec("core.dataframe.basic", owner=OwnerKind.CORE),
        _spec("pkg.editor", capability=PanelCapability.PRODUCING),
    )
    registry.set_panel_choices({"displaying": {"DataFrame": "core.dataframe.basic"}})
    router = PreviewRouter(registry)

    assert router.resolve_request(_frame(), PanelCapability.PRODUCING).spec.previewer_id == "pkg.editor"


def test_a_choice_naming_a_panel_that_cannot_serve_the_capability_is_ignored() -> None:
    """A preference is not a constraint: an unusable one falls through to the
    ladder rather than stopping the panel from rendering."""
    registry = _registry(
        _spec("pkg.table"),
        _spec("pkg.editor", capability=PanelCapability.PRODUCING),
    )
    registry.set_panel_choices({"producing": {"DataFrame": "pkg.table"}})
    router = PreviewRouter(registry)

    assert router.resolve_request(_frame(), PanelCapability.PRODUCING).spec.previewer_id == "pkg.editor"


def test_a_flat_choice_mapping_is_read_as_a_displaying_choice() -> None:
    """The shape every caller wrote before this spec existed."""
    registry = _registry(_spec("pkg.table"), _spec("core.dataframe.basic", owner=OwnerKind.CORE))
    registry.set_panel_choices({"DataFrame": "core.dataframe.basic"})
    router = PreviewRouter(registry)

    assert router.resolve(_frame()).previewer_id == "core.dataframe.basic"


# ---------------------------------------------------------------------------
# FR-049 on disk — the per-capability file, and the one already there
# ---------------------------------------------------------------------------


def test_an_existing_previewer_choices_file_is_read_as_displaying_choices(tmp_path: Path) -> None:
    """Nothing is lost. Every choice recorded before this spec was made from the
    preview surface, which is the displaying resolution; no producing request
    existed when the file was written, so displaying is the honest home for it.
    """
    legacy = tmp_path / LEGACY_CHOICES_FILENAME
    legacy.write_text(
        json.dumps({"version": 1, "choices": {"DataFrame": "pkg.table", "Series": "pkg.line"}}),
        encoding="utf-8",
    )

    layers = read_choice_layers(tmp_path / CHOICES_FILENAME)

    assert layers[PanelCapability.DISPLAYING.value] == {"DataFrame": "pkg.table", "Series": "pkg.line"}
    assert layers[PanelCapability.PRODUCING.value] == {}


def test_the_panel_named_file_wins_wholesale_when_both_exist(tmp_path: Path) -> None:
    """One file is in effect, and it is the panel-named one. Merging two
    declarations of the same thing produces a state neither file describes."""
    (tmp_path / LEGACY_CHOICES_FILENAME).write_text(
        json.dumps({"version": 1, "choices": {"DataFrame": "stale.table"}}), encoding="utf-8"
    )
    (tmp_path / CHOICES_FILENAME).write_text(
        json.dumps({"version": 2, "choices": {"displaying": {"Series": "pkg.line"}}}), encoding="utf-8"
    )

    layers = read_choice_layers(tmp_path / CHOICES_FILENAME)

    assert layers[PanelCapability.DISPLAYING.value] == {"Series": "pkg.line"}


def test_the_first_write_carries_the_legacy_entries_across(tmp_path: Path) -> None:
    """The setting a person made before the rename survives the first write to
    the panel-named file; losing it here is the failure this test exists for."""
    (tmp_path / LEGACY_CHOICES_FILENAME).write_text(
        json.dumps({"version": 1, "choices": {"DataFrame": "pkg.table"}}), encoding="utf-8"
    )

    write_choice(tmp_path / CHOICES_FILENAME, "Series", "pkg.line")

    layers = read_choice_layers(tmp_path / CHOICES_FILENAME)
    assert layers[PanelCapability.DISPLAYING.value] == {"DataFrame": "pkg.table", "Series": "pkg.line"}
    assert (tmp_path / LEGACY_CHOICES_FILENAME).is_file(), "the old file is left alone, not deleted"


def test_a_producing_choice_is_written_to_its_own_layer(tmp_path: Path) -> None:
    path = tmp_path / CHOICES_FILENAME
    write_choice(path, "DataFrame", "pkg.table", capability=PanelCapability.DISPLAYING)
    write_choice(path, "DataFrame", "pkg.editor", capability=PanelCapability.PRODUCING)

    assert read_choice_layer(path, PanelCapability.DISPLAYING) == {"DataFrame": "pkg.table"}
    assert read_choice_layer(path, PanelCapability.PRODUCING) == {"DataFrame": "pkg.editor"}


def test_the_written_file_states_its_schema_version(tmp_path: Path) -> None:
    path = tmp_path / CHOICES_FILENAME
    write_choice(path, "DataFrame", "pkg.table")

    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["version"] == 2
    assert set(body["choices"]) == {"displaying", "producing"}


def test_an_unreadable_choices_file_is_an_empty_layer(tmp_path: Path) -> None:
    """Losing a preference must never be able to stop a preview from rendering."""
    (tmp_path / CHOICES_FILENAME).write_text("{not json", encoding="utf-8")

    assert read_choice_layer(tmp_path / CHOICES_FILENAME) == {}


def test_load_choices_keeps_the_project_layer_over_the_user_layer(tmp_path: Path, monkeypatch) -> None:
    from scistudio.core import dropins

    library = tmp_path / "library"
    project = tmp_path / "project"
    (project / ".scistudio").mkdir(parents=True)
    library.mkdir()
    monkeypatch.setattr(dropins, "user_library_dir", lambda: library)
    write_choice(library / CHOICES_FILENAME, "DataFrame", "user.table")
    write_choice(project / ".scistudio" / CHOICES_FILENAME, "DataFrame", "project.table")

    assert load_choices(project)["DataFrame"] == "project.table"
