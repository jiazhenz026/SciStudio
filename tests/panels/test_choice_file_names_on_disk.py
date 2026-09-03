"""The choices file names, pinned to the literal strings on a person's disk.

The migration renamed the per-type choice file from ``previewer-choices.json``
to ``panel-choices.json`` and added a read of the old name so a preference made
before the rename survives it.

That read is correct today — a file literally named ``previewer-choices.json``
is found and carried across. But nothing was defending the *name*. The three
tests that cover the migration
(``test_panel_resolution.py::test_an_existing_previewer_choices_file_is_read_as_displaying_choices``
and its two neighbours) build their fixture file from ``LEGACY_CHOICES_FILENAME``
and then read through the same constant, so they verify the mechanism against
itself: changing the constant to a name no person's disk has moves the fixture
with it and all three still pass. The same is true of ``CHOICES_FILENAME``,
which the pre-rename suite pinned as a literal in
``test_previewer_choice.py`` and the migrated suite reaches only through the
constant.

Verified by mutation: setting ``LEGACY_CHOICES_FILENAME`` to
``previewer-choices-DISABLED.json`` and running ``tests/panels``,
``tests/api/test_panel_choice_routes.py`` and
``tests/api/test_panel_source_routes.py`` produced zero failures.

A file name is not an identifier. It is a thing that exists on disks this build
did not write, so it is spelled out here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.core.panels import PanelCapability
from scistudio.panels.choices import (
    CHOICES_FILENAME,
    LEGACY_CHOICES_FILENAME,
    load_choice_layers,
    load_choices,
    project_choices_path,
    read_choice_layers,
    user_choices_path,
    write_choice,
)


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "home"
    (fake / ".scistudio").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    return fake


# ---------------------------------------------------------------------------
# The two names
# ---------------------------------------------------------------------------


def test_the_legacy_choices_file_is_the_name_that_is_on_disk() -> None:
    """``previewer-choices.json`` is what pre-rename builds wrote and left behind."""
    assert LEGACY_CHOICES_FILENAME == "previewer-choices.json"


def test_the_current_choices_file_name_is_pinned() -> None:
    """Renaming it again silently orphans every preference written since."""
    assert CHOICES_FILENAME == "panel-choices.json"


def test_a_file_named_on_disk_by_a_pre_rename_build_is_read(tmp_path: Path) -> None:
    """The migration read, exercised through the literal name rather than the constant.

    This is the same property
    ``test_an_existing_previewer_choices_file_is_read_as_displaying_choices``
    names; it differs only in writing the fixture as ``previewer-choices.json``
    rather than as ``LEGACY_CHOICES_FILENAME``, which is what makes it able to
    fail.
    """
    (tmp_path / "previewer-choices.json").write_text(
        json.dumps({"version": 1, "choices": {"DataFrame": "pkg.table"}}),
        encoding="utf-8",
    )

    layers = read_choice_layers(tmp_path / "panel-choices.json")

    assert layers[PanelCapability.DISPLAYING.value] == {"DataFrame": "pkg.table"}


def test_the_written_file_is_the_panel_named_one(tmp_path: Path) -> None:
    """A write lands on the new name, spelled out, and leaves the old one alone."""
    (tmp_path / "previewer-choices.json").write_text(
        json.dumps({"version": 1, "choices": {"DataFrame": "pkg.table"}}),
        encoding="utf-8",
    )

    write_choice(tmp_path / CHOICES_FILENAME, "Series", "pkg.line")

    assert (tmp_path / "panel-choices.json").is_file()
    assert (tmp_path / "previewer-choices.json").is_file()


# ---------------------------------------------------------------------------
# Two merge paths, one rule
# ---------------------------------------------------------------------------


def test_the_runtime_merge_keeps_the_project_layer_over_the_user_layer(home: Path, tmp_path: Path) -> None:
    """``load_choice_layers`` is the merge the registry is actually fed.

    The precedence rule is implemented twice — once in ``load_choices`` and once
    in ``load_choice_layers`` — and ``build_preview_service`` uses the second.
    The panel-suite tests that name this property
    (``test_the_project_layer_overrides_the_user_layer`` and
    ``test_the_user_layer_shows_through_for_types_the_project_did_not_override``)
    both go through ``load_choices``, so breaking the rule in
    ``load_choice_layers`` leaves them green; only one API test notices.
    Verified by mutation.
    """
    project = tmp_path / "project"
    project.mkdir()
    write_choice(user_choices_path(project), "Probe", "probe.user")
    write_choice(user_choices_path(project), "Image", "image.user")
    write_choice(project_choices_path(project), "Probe", "probe.project")

    layers = load_choice_layers(project)

    assert layers[PanelCapability.DISPLAYING.value] == {
        "Probe": "probe.project",
        "Image": "image.user",
    }


def test_the_two_merge_paths_agree(home: Path, tmp_path: Path) -> None:
    """One rule stated twice must stay one rule.

    Nothing compares them, so a fix applied to whichever function the reporter
    happened to find would leave the other behind.
    """
    project = tmp_path / "project"
    project.mkdir()
    write_choice(user_choices_path(project), "Probe", "probe.user")
    write_choice(user_choices_path(project), "Image", "image.user")
    write_choice(project_choices_path(project), "Probe", "probe.project")

    assert load_choices(project) == load_choice_layers(project)[PanelCapability.DISPLAYING.value]
