"""Tier grading beyond the driver field — ADR-053 spec §4.4 "Tier assets" row.

Asserts FR-020a: a user-level or project-level manifest is rejected when it
declares an executable asset, a ``replay`` action, or a destination under a
directory the product imports or executes — and that core and package manifests
are not.

Why this exists at all, in the spec's own words: rejecting ``driver`` alone
does not make a tier incapable of carrying executable code, because a
project-level tutorial could drop a ``.py`` into ``blocks/`` through an
ordinary write action and have it imported on the next registry refresh.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scistudio.tutorials.actions import EXECUTED_PROJECT_DIRS
from scistudio.tutorials.manifest import (
    EXECUTABLE_ASSET_DIRS,
    ManifestValidationError,
    TutorialSourceKind,
    load_manifest,
)

from .conftest import MINIMAL_MANIFEST, write_tutorial

GRADED_OUT = [TutorialSourceKind.USER, TutorialSourceKind.PROJECT]
GRADED_IN = [TutorialSourceKind.CORE, TutorialSourceKind.PACKAGE]


def test_the_two_restricted_sets_are_the_ones_fr_020a_names() -> None:
    assert set(EXECUTABLE_ASSET_DIRS) == {"code", "panels", "replay"}
    assert set(EXECUTED_PROJECT_DIRS) >= {"blocks", "types", "previewers", "plots"}


# ---------------------------------------------------------------------------
# An executable asset carried in the directory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", GRADED_OUT)
@pytest.mark.parametrize("asset_dir", sorted(EXECUTABLE_ASSET_DIRS))
def test_an_executable_asset_is_rejected_for_the_ungraded_tiers(
    kind: TutorialSourceKind, asset_dir: str, tmp_path: Path
) -> None:
    directory = write_tutorial(
        tmp_path / f"{kind.value}-{asset_dir}",
        copy.deepcopy(MINIMAL_MANIFEST),
        files={f"assets/{asset_dir}/thing.py": "print('hi')\n"},
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=kind)
    message = str(excinfo.value)
    assert kind.value in message
    assert f"assets/{asset_dir}" in message


@pytest.mark.parametrize("kind", GRADED_IN)
@pytest.mark.parametrize("asset_dir", sorted(EXECUTABLE_ASSET_DIRS))
def test_an_executable_asset_is_accepted_for_core_and_packages(
    kind: TutorialSourceKind, asset_dir: str, tmp_path: Path
) -> None:
    directory = write_tutorial(
        tmp_path / f"{kind.value}-{asset_dir}",
        copy.deepcopy(MINIMAL_MANIFEST),
        files={f"assets/{asset_dir}/thing.py": "print('hi')\n"},
    )
    assert load_manifest(directory, source_kind=kind).id == "example"


@pytest.mark.parametrize("kind", GRADED_OUT)
def test_a_data_asset_is_fine_for_every_tier(kind: TutorialSourceKind, tmp_path: Path) -> None:
    directory = write_tutorial(
        tmp_path / f"{kind.value}-data",
        copy.deepcopy(MINIMAL_MANIFEST),
        files={"assets/data/cells.csv": "well,mean\n", "assets/pages/intro.md": "# Hello\n"},
    )
    assert load_manifest(directory, source_kind=kind).id == "example"


def test_an_empty_executable_asset_directory_is_not_a_rejection(tmp_path: Path) -> None:
    directory = write_tutorial(tmp_path / "empty-code", copy.deepcopy(MINIMAL_MANIFEST))
    (directory / "assets" / "code").mkdir(parents=True)
    assert load_manifest(directory, source_kind=TutorialSourceKind.PROJECT).id == "example"


# ---------------------------------------------------------------------------
# A replay action
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", GRADED_OUT)
def test_a_replay_action_is_rejected_for_the_ungraded_tiers(kind: TutorialSourceKind, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [
        {
            "replay": {
                "surface": "ai_chat_terminal",
                "segments": [{"id": "one", "source": "assets/replay/one.txt"}],
            }
        }
    ]
    directory = write_tutorial(tmp_path / f"{kind.value}-replay", data, files={"assets/replay/one.txt": "hi\n"})
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=kind)
    message = str(excinfo.value)
    assert kind.value in message
    assert "replay" in message


@pytest.mark.parametrize("kind", GRADED_IN)
def test_a_replay_action_is_accepted_for_core_and_packages(kind: TutorialSourceKind, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [
        {
            "replay": {
                "surface": "ai_chat_terminal",
                "segments": [{"id": "one", "source": "assets/replay/one.txt"}],
            }
        }
    ]
    directory = write_tutorial(tmp_path / f"{kind.value}-replay", data, files={"assets/replay/one.txt": "hi\n"})
    assert load_manifest(directory, source_kind=kind).steps[0].do


# ---------------------------------------------------------------------------
# A destination under an executed directory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", GRADED_OUT)
@pytest.mark.parametrize("executed", sorted(EXECUTED_PROJECT_DIRS))
def test_a_destination_under_an_executed_directory_is_rejected(
    kind: TutorialSourceKind, executed: str, tmp_path: Path
) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"write": {"source": "assets/data/x.py", "destination": f"{executed}/x.py"}}]
    directory = write_tutorial(tmp_path / f"{kind.value}-{executed}", data, files={"assets/data/x.py": "x = 1\n"})
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=kind)
    message = str(excinfo.value)
    assert kind.value in message
    assert executed in message
    assert "destination" in message


@pytest.mark.parametrize("kind", GRADED_OUT)
def test_a_bootstrap_destination_is_graded_the_same_way(kind: TutorialSourceKind, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["bootstrap"] = {"do": [{"write": {"source": "assets/data/x.py", "destination": "blocks/x.py"}}]}
    directory = write_tutorial(tmp_path / f"{kind.value}-boot", data, files={"assets/data/x.py": "x = 1\n"})
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=kind)
    assert "blocks" in str(excinfo.value)


@pytest.mark.parametrize("kind", GRADED_OUT)
def test_a_destination_outside_the_executed_set_is_allowed(kind: TutorialSourceKind, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"write": {"source": "assets/data/x.csv", "destination": "data/raw/x.csv"}}]
    directory = write_tutorial(tmp_path / f"{kind.value}-ok", data, files={"assets/data/x.csv": "a\n"})
    assert load_manifest(directory, source_kind=kind).steps[0].do


@pytest.mark.parametrize("kind", GRADED_IN)
def test_core_and_packages_may_write_into_an_executed_directory(kind: TutorialSourceKind, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"write": {"source": "assets/code/x.py", "destination": "blocks/x.py"}}]
    directory = write_tutorial(tmp_path / f"{kind.value}-blocks", data, files={"assets/code/x.py": "x = 1\n"})
    assert load_manifest(directory, source_kind=kind).steps[0].do


# ---------------------------------------------------------------------------
# The copy-to-project-root route into an executed directory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", GRADED_OUT)
def test_a_copy_whose_tree_lands_in_an_executed_directory_is_rejected(kind: TutorialSourceKind, tmp_path: Path) -> None:
    """Naming ``blocks/`` and copying a tree that contains it are the same exposure."""
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"copy": {"source": "assets/data/bundle", "destination": "."}}]
    directory = write_tutorial(
        tmp_path / f"{kind.value}-copytree",
        data,
        files={"assets/data/bundle/blocks/sneaky.py": "import os\n"},
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=kind)
    message = str(excinfo.value)
    assert "blocks" in message
    assert "sneaky.py" in message


@pytest.mark.parametrize("kind", GRADED_OUT)
def test_a_copy_of_ordinary_data_is_still_allowed(kind: TutorialSourceKind, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"copy": {"source": "assets/data/bundle", "destination": "data/raw"}}]
    directory = write_tutorial(
        tmp_path / f"{kind.value}-copyok",
        data,
        files={"assets/data/bundle/cells.csv": "well,mean\n"},
    )
    assert load_manifest(directory, source_kind=kind).steps[0].do


def test_the_grading_is_a_property_of_the_tier_not_of_the_manifest() -> None:
    assert TutorialSourceKind.CORE.allows_executable_content is True
    assert TutorialSourceKind.PACKAGE.allows_executable_content is True
    assert TutorialSourceKind.USER.allows_executable_content is False
    assert TutorialSourceKind.PROJECT.allows_executable_content is False
