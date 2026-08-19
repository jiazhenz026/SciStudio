"""Progress, its grouping, and the single unlock it drives.

``docs/specs/adr-053-learning-center.md`` FR-074 to FR-081. Progress is a
backend file keyed by ``(source, tutorial id)``, reported per source with no
aggregate, and it drives exactly one thing: the work-import offer, once, from
the core group alone. Nothing is gated on it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.core import dropins
from scistudio.tutorials.progress import (
    CONFIG_FILENAME,
    PROGRESS_FILENAME,
    WORK_IMPORT_MILESTONE_ENV_VAR,
    CatalogueTotals,
    ProgressStore,
    work_import_milestone,
)
from scistudio.tutorials.projects import TutorialKey


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.delenv(WORK_IMPORT_MILESTONE_ENV_VAR, raising=False)
    return fake_home


@pytest.fixture
def store(home: Path) -> ProgressStore:
    return ProgressStore()


def _core(*ids: str) -> CatalogueTotals:
    return CatalogueTotals(source_kind="core", source_id="", tutorial_ids=frozenset(ids))


def _package(name: str, *ids: str) -> CatalogueTotals:
    return CatalogueTotals(source_kind="package", source_id=name, tutorial_ids=frozenset(ids))


# ---------------------------------------------------------------------------
# FR-074 / FR-075 — where it lives and how it is keyed
# ---------------------------------------------------------------------------


def test_progress_is_stored_on_the_backend_under_the_user_library(store: ProgressStore, home: Path) -> None:
    """FR-074: a backend file, not browser storage."""
    assert store.root == dropins.user_library_dir()
    assert store.path == home / ".scistudio" / PROGRESS_FILENAME

    store.mark_completed(TutorialKey.core("welcome"))

    assert store.path.is_file()
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["completed"] == [{"source_kind": "core", "source_id": "", "tutorial_id": "welcome"}]


def test_progress_survives_a_new_store_instance(store: ProgressStore) -> None:
    """The backend must be able to read it back — that is FR-074's whole point."""
    store.mark_completed(TutorialKey.core("welcome"))

    assert ProgressStore().is_completed(TutorialKey.core("welcome")) is True


def test_a_record_is_keyed_by_source_and_tutorial_id(store: ProgressStore) -> None:
    """FR-075 with FR-019: two packages may ship the same tutorial id."""
    first = TutorialKey("package", "scistudio-blocks-imaging", "intro")
    second = TutorialKey("package", "scistudio-blocks-lcms", "intro")

    store.mark_completed(first)

    assert store.is_completed(first) is True
    assert store.is_completed(second) is False
    assert store.is_completed(TutorialKey.core("intro")) is False


def test_completing_the_same_tutorial_twice_records_once(store: ProgressStore) -> None:
    """The second call reports that it changed nothing.

    Which is what "once" (FR-079) is decided on: a tutorial re-run after a
    restart must not look like a first completion.
    """
    key = TutorialKey.core("welcome")

    assert store.mark_completed(key) is True
    assert store.mark_completed(key) is False
    assert len(store.completed_keys()) == 1


def test_an_unreadable_progress_file_reads_as_empty(store: ProgressStore) -> None:
    """A corrupt file costs a repeated tutorial, not an unopenable catalogue."""
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")

    assert store.completed_keys() == frozenset()
    assert store.mark_completed(TutorialKey.core("welcome")) is True


# ---------------------------------------------------------------------------
# FR-076 / FR-077 — grouped counts, and the total that is allowed to grow
# ---------------------------------------------------------------------------


def test_progress_is_reported_grouped_by_source(store: ProgressStore) -> None:
    """FR-076: each group carries its own counts, in the caller's order."""
    store.mark_completed(TutorialKey.core("welcome"))
    store.mark_completed(TutorialKey.core("custom-blocks"))
    store.mark_completed(TutorialKey("package", "scistudio-blocks-imaging", "intro"))

    groups = store.groups(
        [
            _core("welcome", "custom-blocks", "ai"),
            _package("scistudio-blocks-imaging", "intro", "advanced"),
        ]
    )

    assert [(group.source_kind, group.source_id, group.completed, group.total) for group in groups] == [
        ("core", "", 2, 3),
        ("package", "scistudio-blocks-imaging", 1, 2),
    ]


def test_no_aggregate_across_groups_is_reported(store: ProgressStore) -> None:
    """FR-076: the report is groups and nothing else.

    A percentage over a catalogue packages can grow does not denote a fixed
    point in the user's experience, so no such number is produced anywhere for a
    caller to render by accident.
    """
    result = store.groups([_core("welcome"), _package("pkg", "intro")])

    assert isinstance(result, tuple)
    assert not hasattr(result, "completed")
    assert not any(hasattr(group, "percent") for group in result)


def test_a_growing_total_is_not_compensated_for(store: ProgressStore) -> None:
    """FR-077: a complete group goes back to incomplete after an upgrade.

    The intended reading, because there is new material.
    """
    store.mark_completed(TutorialKey("package", "pkg", "intro"))

    (before,) = store.groups([_package("pkg", "intro")])
    assert (before.completed, before.total) == (1, 1)

    (after,) = store.groups([_package("pkg", "intro", "advanced")])
    assert (after.completed, after.total) == (1, 2)


def test_a_withdrawn_tutorial_stops_counting_rather_than_overflowing(store: ProgressStore) -> None:
    """Completion is the intersection with what the source still ships.

    A count-only record would leave ``completed`` above ``total`` after a source
    withdrew a tutorial, which no surface can render honestly.
    """
    store.mark_completed(TutorialKey("package", "pkg", "intro"))
    store.mark_completed(TutorialKey("package", "pkg", "retired"))

    (group,) = store.groups([_package("pkg", "intro")])

    assert (group.completed, group.total) == (1, 1)


def test_a_source_with_no_completions_reports_zero(store: ProgressStore) -> None:
    """A group the user has not touched is still a group."""
    (group,) = store.groups([_package("pkg", "intro", "advanced")])

    assert (group.completed, group.total) == (0, 2)


# ---------------------------------------------------------------------------
# FR-078 — package uninstall
# ---------------------------------------------------------------------------


def test_package_uninstall_removes_that_package_group(store: ProgressStore) -> None:
    """FR-078, and only that package's group."""
    store.mark_completed(TutorialKey("package", "scistudio-blocks-imaging", "intro"))
    store.mark_completed(TutorialKey("package", "scistudio-blocks-lcms", "intro"))
    store.mark_completed(TutorialKey.core("welcome"))

    removed = store.remove_package_group("scistudio-blocks-imaging")

    assert removed == 1
    assert store.is_completed(TutorialKey("package", "scistudio-blocks-imaging", "intro")) is False
    assert store.is_completed(TutorialKey("package", "scistudio-blocks-lcms", "intro")) is True
    assert store.is_completed(TutorialKey.core("welcome")) is True


def test_reinstalling_starts_from_zero(store: ProgressStore) -> None:
    """FR-078: the record is deleted, not hidden.

    A retained record would make a reinstalled package look already-finished to
    a user who has never seen its tutorials.
    """
    key = TutorialKey("package", "pkg", "intro")
    store.mark_completed(key)
    store.remove_package_group("pkg")

    (group,) = store.groups([_package("pkg", "intro")])

    assert (group.completed, group.total) == (0, 1)


def test_uninstalling_a_package_with_no_progress_changes_nothing(store: ProgressStore) -> None:
    store.mark_completed(TutorialKey.core("welcome"))

    assert store.remove_package_group("never-seen") == 0
    assert store.is_completed(TutorialKey.core("welcome")) is True


# ---------------------------------------------------------------------------
# FR-079 / FR-080 / FR-081 — the one unlock
# ---------------------------------------------------------------------------


def test_the_milestone_is_configuration_not_a_constant(store: ProgressStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-079 with spec assumption A-005.

    The scenarios spec decides which tutorial this is and may change it later,
    so the value comes from configuration: an environment variable first, then
    the Learning Center settings file.
    """
    assert work_import_milestone() is None

    (store.root).mkdir(parents=True, exist_ok=True)
    (store.root / CONFIG_FILENAME).write_text(json.dumps({"work_import_milestone": "ai-agent"}), encoding="utf-8")
    assert work_import_milestone() == "ai-agent"

    monkeypatch.setenv(WORK_IMPORT_MILESTONE_ENV_VAR, "something-else")
    assert work_import_milestone() == "something-else"


def test_completing_the_milestone_makes_the_offer_pending(
    store: ProgressStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-079: completing the named core tutorial presents the offer."""
    monkeypatch.setenv(WORK_IMPORT_MILESTONE_ENV_VAR, "ai-agent")

    assert store.work_import_offer_pending() is False

    store.mark_completed(TutorialKey.core("welcome"))
    assert store.work_import_offer_pending() is False

    store.mark_completed(TutorialKey.core("ai-agent"))
    assert store.work_import_offer_pending() is True


def test_the_offer_is_presented_once(store: ProgressStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-079's "once", and User Story 5's skip path."""
    monkeypatch.setenv(WORK_IMPORT_MILESTONE_ENV_VAR, "ai-agent")
    store.mark_completed(TutorialKey.core("ai-agent"))

    store.dismiss_work_import_offer()

    assert store.work_import_offer_pending() is False
    assert ProgressStore().work_import_offer_pending() is False
    # Dismissal does not erase progress.
    assert store.is_completed(TutorialKey.core("ai-agent")) is True


def test_only_the_core_group_can_drive_the_unlock(store: ProgressStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-080: package progress drives nothing.

    The milestone is a core tutorial id, so a package tutorial with the same id
    cannot reach the unlock however much of that package the user completes.
    """
    monkeypatch.setenv(WORK_IMPORT_MILESTONE_ENV_VAR, "ai-agent")

    store.mark_completed(TutorialKey("package", "pkg", "ai-agent"))
    store.mark_completed(TutorialKey("user", "user", "ai-agent"))
    store.mark_completed(TutorialKey("project", "project", "ai-agent"))

    assert store.work_import_offer_pending() is False

    store.mark_completed(TutorialKey.core("ai-agent"))
    assert store.work_import_offer_pending() is True


def test_an_unconfigured_milestone_never_volunteers_the_offer(store: ProgressStore) -> None:
    """FR-081: an unconfigured milestone withholds a prompt, not a capability."""
    store.mark_completed(TutorialKey.core("ai-agent"))

    assert work_import_milestone() is None
    assert store.work_import_offer_pending() is False


def test_clearing_removes_progress_and_the_unlock_state(store: ProgressStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-088's progress half."""
    monkeypatch.setenv(WORK_IMPORT_MILESTONE_ENV_VAR, "ai-agent")
    store.mark_completed(TutorialKey.core("ai-agent"))
    store.dismiss_work_import_offer()

    store.clear()

    assert store.completed_keys() == frozenset()
    assert not store.path.exists()
    # Progress is gone, so the offer is owed again once the tutorial is redone.
    assert store.work_import_offer_pending() is False
    store.mark_completed(TutorialKey.core("ai-agent"))
    assert store.work_import_offer_pending() is True
