"""The person's chosen previewer per type — storage and routing (#2049).

Two properties carry the design and each has its own section below.

The **short circuit** must be purely additive: with no choice recorded, every
routing answer is the one ADR-048 FR-003 already gave. `test_the_ladder_is_untouched_when_nothing_is_chosen`
is the guard on that, and it is the test to look at first if the tier tests
elsewhere start failing.

The **fallbacks** carry the other half: a choice is a preference, not a
constraint. Four things can stop one applying and none may raise, because a
recorded preference must never be able to stop a preview from rendering.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.previewers.choices import (
    clear_choice,
    load_choices,
    project_choices_path,
    read_choice_layer,
    user_choices_path,
    write_choice,
)
from scistudio.previewers.models import OwnerKind, PreviewerSpec, PreviewTarget, TargetKind
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter


def _spec(
    previewer_id: str,
    owner: OwnerKind,
    *,
    target_type: str = "Probe",
    supports_collection: bool = False,
    priority: int = 50,
) -> PreviewerSpec:
    return PreviewerSpec(
        previewer_id=previewer_id,
        owner_kind=owner,
        owner_name=owner.value,
        target_type=target_type,
        supports_collection=supports_collection,
        priority=priority,
    )


ITEM = PreviewTarget(
    kind=TargetKind.DATA_REF,
    ref="ref",
    recorded_type="Probe",
    type_chain=("DataObject", "Series", "Probe"),
)
COLLECTION = PreviewTarget(
    kind=TargetKind.COLLECTION_REF,
    ref="ref",
    recorded_type="Probe",
    type_chain=("DataObject", "Series", "Probe"),
    collection_item_type="Probe",
)


@pytest.fixture()
def registry() -> PreviewerRegistry:
    """A registry with one previewer per tier, all claiming ``Probe``."""
    reg = PreviewerRegistry()
    reg.register(_spec("probe.project", OwnerKind.PROJECT))
    reg.register(_spec("probe.user", OwnerKind.USER))
    reg.register(_spec("probe.package", OwnerKind.PACKAGE))
    return reg


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "home"
    (fake / ".scistudio").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    return fake


# ---------------------------------------------------------------------------
# Storage: two layers, project over user
# ---------------------------------------------------------------------------


def test_a_choice_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "previewer-choices.json"
    write_choice(path, "Probe", "probe.package")
    assert read_choice_layer(path) == {"Probe": "probe.package"}


def test_writing_one_type_leaves_the_others_alone(tmp_path: Path) -> None:
    """The write reads first, so a second type is not lost to a blind overwrite."""
    path = tmp_path / "previewer-choices.json"
    write_choice(path, "Probe", "probe.package")
    write_choice(path, "Image", "image.viewer")
    assert read_choice_layer(path) == {"Probe": "probe.package", "Image": "image.viewer"}


def test_clearing_removes_only_that_type(tmp_path: Path) -> None:
    path = tmp_path / "previewer-choices.json"
    write_choice(path, "Probe", "probe.package")
    write_choice(path, "Image", "image.viewer")
    clear_choice(path, "Probe")
    assert read_choice_layer(path) == {"Image": "image.viewer"}


def test_clearing_a_type_that_was_never_chosen_is_not_an_error(tmp_path: Path) -> None:
    path = tmp_path / "previewer-choices.json"
    clear_choice(path, "NeverChosen")
    assert read_choice_layer(path) == {}


def test_the_project_layer_overrides_the_user_layer(home: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_choice(user_choices_path(project), "Probe", "probe.user")
    write_choice(project_choices_path(project), "Probe", "probe.project")

    assert load_choices(project)["Probe"] == "probe.project"


def test_the_user_layer_shows_through_for_types_the_project_did_not_override(home: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_choice(user_choices_path(project), "Probe", "probe.user")
    write_choice(user_choices_path(project), "Image", "image.user")
    write_choice(project_choices_path(project), "Probe", "probe.project")

    assert load_choices(project) == {"Probe": "probe.project", "Image": "image.user"}


def test_the_user_layer_loads_with_no_project_open(home: Path) -> None:
    """A person's global preference is not a property of whichever project is open."""
    write_choice(user_choices_path(None), "Probe", "probe.user")
    assert load_choices(None) == {"Probe": "probe.user"}


# ---------------------------------------------------------------------------
# Storage: a preference file outlives the build that wrote it (#2073's lesson)
# ---------------------------------------------------------------------------


def test_a_missing_file_is_an_empty_layer(tmp_path: Path) -> None:
    assert read_choice_layer(tmp_path / "absent.json") == {}


def test_malformed_json_is_ignored_rather_than_raised(tmp_path: Path) -> None:
    path = tmp_path / "previewer-choices.json"
    path.write_text("{not json", encoding="utf-8")
    assert read_choice_layer(path) == {}


def test_a_payload_that_is_not_an_object_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "previewer-choices.json"
    path.write_text('["not", "an", "object"]', encoding="utf-8")
    assert read_choice_layer(path) == {}


def test_an_unknown_key_from_a_newer_build_does_not_lose_the_choices(tmp_path: Path) -> None:
    path = tmp_path / "previewer-choices.json"
    path.write_text(
        json.dumps({"version": 99, "choices": {"Probe": "probe.package"}, "somethingNew": {"a": 1}}),
        encoding="utf-8",
    )
    assert read_choice_layer(path) == {"Probe": "probe.package"}


def test_one_malformed_entry_does_not_cost_the_others(tmp_path: Path) -> None:
    path = tmp_path / "previewer-choices.json"
    path.write_text(
        json.dumps({"choices": {"Probe": "probe.package", "Bad": ["list"], "": "empty-key", "Blank": ""}}),
        encoding="utf-8",
    )
    assert read_choice_layer(path) == {"Probe": "probe.package"}


# ---------------------------------------------------------------------------
# Routing: the short circuit
# ---------------------------------------------------------------------------


def test_the_ladder_is_untouched_when_nothing_is_chosen(registry: PreviewerRegistry) -> None:
    """The guard on "purely additive". If this fails, #2049 changed FR-003."""
    assert PreviewRouter(registry).resolve(ITEM).previewer_id == "probe.project"


@pytest.mark.parametrize("chosen", ["probe.user", "probe.package"])
def test_a_choice_wins_over_the_whole_ladder(registry: PreviewerRegistry, chosen: str) -> None:
    """Including over the project tier, which the ladder would otherwise pick."""
    registry.set_previewer_choices({"Probe": chosen})
    assert PreviewRouter(registry).resolve(ITEM).previewer_id == chosen


def test_choosing_what_the_ladder_would_have_picked_changes_nothing(registry: PreviewerRegistry) -> None:
    registry.set_previewer_choices({"Probe": "probe.project"})
    assert PreviewRouter(registry).resolve(ITEM).previewer_id == "probe.project"


def test_a_choice_on_one_type_does_not_govern_another(registry: PreviewerRegistry) -> None:
    registry.set_previewer_choices({"Image": "probe.package"})
    assert PreviewRouter(registry).resolve(ITEM).previewer_id == "probe.project"


def test_a_choice_does_not_reach_types_that_merely_descend_from_the_chosen_one(
    registry: PreviewerRegistry,
) -> None:
    """Keyed on the exact type name, so a ``Series`` choice leaves ``Probe`` alone.

    The narrower rule is the predictable one: a choice quietly governing
    subtypes the person never looked at is harder to explain than one that
    simply does not apply yet.
    """
    registry.register(_spec("series.core", OwnerKind.CORE, target_type="Series"))
    registry.set_previewer_choices({"Series": "series.core"})
    assert PreviewRouter(registry).resolve(ITEM).previewer_id == "probe.project"


# ---------------------------------------------------------------------------
# Routing: a preference is not a constraint — four fallbacks, none of them raise
# ---------------------------------------------------------------------------


def test_a_choice_naming_an_unregistered_previewer_falls_back(registry: PreviewerRegistry) -> None:
    """The realistic case: the package that provided it was uninstalled."""
    registry.set_previewer_choices({"Probe": "gone.after.uninstall"})
    assert PreviewRouter(registry).resolve(ITEM).previewer_id == "probe.project"


def test_a_choice_for_an_unrelated_type_falls_back(registry: PreviewerRegistry) -> None:
    """Bounded to the target's type chain, so a choice reorders the ladder's
    candidates but can never widen them to a previewer that claims something
    else entirely."""
    registry.register(_spec("image.viewer", OwnerKind.PACKAGE, target_type="Image"))
    registry.set_previewer_choices({"Probe": "image.viewer"})
    assert PreviewRouter(registry).resolve(ITEM).previewer_id == "probe.project"


def test_choosing_an_ancestors_previewer_is_honoured(registry: PreviewerRegistry) -> None:
    """Picking core's plain ``Series`` view for a ``Probe`` is a real preference,
    not a mistake, so the chain bound admits it."""
    registry.register(_spec("series.core", OwnerKind.CORE, target_type="Series"))
    registry.set_previewer_choices({"Probe": "series.core"})
    assert PreviewRouter(registry).resolve(ITEM).previewer_id == "series.core"


def test_a_single_item_choice_is_not_used_for_a_collection() -> None:
    """FR-003/US4 applies to a choice too: a single-item viewer handed a whole
    collection is a broken view, not an honoured preference.

    The registry here deliberately has a *different* collection-capable
    previewer, so falling back is visible rather than coincidentally identical.
    """
    reg = PreviewerRegistry()
    reg.register(_spec("probe.single", OwnerKind.PACKAGE, supports_collection=False, priority=90))
    reg.register(_spec("probe.batch", OwnerKind.PROJECT, supports_collection=True, priority=10))
    reg.set_previewer_choices({"Probe": "probe.single"})

    assert PreviewRouter(reg).resolve(COLLECTION).previewer_id == "probe.batch"
    # ...and the same choice still applies to a single item.
    assert PreviewRouter(reg).resolve(ITEM).previewer_id == "probe.single"


def test_a_collection_capable_choice_is_honoured_for_a_collection() -> None:
    reg = PreviewerRegistry()
    reg.register(_spec("probe.batch.chosen", OwnerKind.PACKAGE, supports_collection=True, priority=1))
    reg.register(_spec("probe.batch.other", OwnerKind.PROJECT, supports_collection=True, priority=99))
    reg.set_previewer_choices({"Probe": "probe.batch.chosen"})

    assert PreviewRouter(reg).resolve(COLLECTION).previewer_id == "probe.batch.chosen"


# ---------------------------------------------------------------------------
# Routing: FR-005 is untouched
# ---------------------------------------------------------------------------


def test_the_project_default_still_only_breaks_a_same_tier_tie() -> None:
    """#2049 is additive: FR-005 keeps the narrow role it was specified with.

    Two package previewers tie on priority; the project default picks one. That
    is the only thing it has ever done, and adding the choice layer above it
    must not have widened it into a general default.
    """
    reg = PreviewerRegistry()
    reg.register(_spec("probe.a", OwnerKind.PACKAGE, priority=50))
    reg.register(_spec("probe.b", OwnerKind.PACKAGE, priority=50))
    reg.set_project_default("Probe", "probe.b")

    assert PreviewRouter(reg).resolve(ITEM).previewer_id == "probe.b"


def test_a_choice_and_a_project_default_do_not_meet(registry: PreviewerRegistry) -> None:
    """When a choice applies, the ladder does not run, so FR-005 never arbitrates."""
    registry.set_project_default("Probe", "probe.project")
    registry.set_previewer_choices({"Probe": "probe.package"})

    assert PreviewRouter(registry).resolve(ITEM).previewer_id == "probe.package"
