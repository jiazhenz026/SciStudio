"""Manifest format and validation — ADR-053 spec §4.4 "Manifest" row.

Asserts: required fields; ``steps`` xor ``driver``; asset and destination
containment; an unknown vocabulary term rejected at validation (FR-049);
``driver`` rejected for the user and project tiers (FR-020). Plus the two
version cases FR-007a separates, and the single-declaration locks that keep the
published schema from growing a second copy of the vocabulary or of the replay
surface set.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scistudio.tutorials import actions as actions_module
from scistudio.tutorials import conditions as conditions_module
from scistudio.tutorials.manifest import (
    SCHEMA_PATH,
    ManifestValidationError,
    TutorialSourceKind,
    UnsupportedManifestVersionError,
    load_manifest,
    load_schema,
    parse_manifest,
)

from .conftest import MINIMAL_MANIFEST, write_tutorial

FIXTURES = Path(__file__).parent / "fixtures"


def parse(data: dict[str, Any], *, tmp_path: Path, kind: TutorialSourceKind = TutorialSourceKind.CORE) -> Any:
    return parse_manifest(data, directory=tmp_path, source_kind=kind, path=tmp_path / "tutorial.yaml")


# ---------------------------------------------------------------------------
# Required fields (FR-007, FR-007a)
# ---------------------------------------------------------------------------


def test_minimal_manifest_parses(tmp_path: Path) -> None:
    manifest = parse(copy.deepcopy(MINIMAL_MANIFEST), tmp_path=tmp_path)
    assert manifest.id == "example"
    assert manifest.title == "Example"
    assert manifest.summary == "A tutorial used by the tests."
    assert manifest.manifest_version == 1
    assert manifest.source_kind is TutorialSourceKind.CORE


@pytest.mark.parametrize("missing", ["manifest_version", "id", "title", "summary"])
def test_missing_required_field_is_rejected_naming_file_and_field(missing: str, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    del data[missing]
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    message = str(excinfo.value)
    assert "tutorial.yaml" in message
    assert missing in message


def test_unknown_top_level_field_is_rejected(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["kind"] = "workflow"
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert "kind" in str(excinfo.value)


def test_unsupported_version_is_not_a_malformed_manifest(tmp_path: Path) -> None:
    """FR-007a: 'written for a newer core' and 'malformed' owe different messages."""
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["manifest_version"] = 99
    with pytest.raises(UnsupportedManifestVersionError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert excinfo.value.declared_version == 99
    assert "99" in str(excinfo.value)
    assert not isinstance(excinfo.value, ManifestValidationError)


def test_a_manifest_that_is_not_a_mapping_is_malformed(tmp_path: Path) -> None:
    with pytest.raises(ManifestValidationError):
        parse_manifest(["not", "a", "mapping"], directory=tmp_path, source_kind=TutorialSourceKind.CORE, path=tmp_path)


# ---------------------------------------------------------------------------
# steps xor driver (FR-010)
# ---------------------------------------------------------------------------


def test_declaring_both_steps_and_driver_names_the_conflict(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["driver"] = "pkg.module:Driver"
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert "both" in str(excinfo.value)
    assert "steps" in str(excinfo.value)
    assert "driver" in str(excinfo.value)


def test_declaring_neither_steps_nor_driver_names_the_conflict(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    del data["steps"]
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert "neither" in str(excinfo.value)


def test_driver_only_manifest_is_driver_driven(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    del data["steps"]
    data["driver"] = "pkg.module:Driver"
    manifest = parse(data, tmp_path=tmp_path, kind=TutorialSourceKind.PACKAGE)
    assert manifest.is_driver_driven
    assert manifest.steps == ()


# ---------------------------------------------------------------------------
# bootstrap presence decides the project (FR-009)
# ---------------------------------------------------------------------------


def test_bootstrap_presence_is_what_grants_a_project(tmp_path: Path) -> None:
    without = parse(copy.deepcopy(MINIMAL_MANIFEST), tmp_path=tmp_path)
    assert without.creates_project is False

    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["bootstrap"] = {"project_name": "Example"}
    with_bootstrap = parse(data, tmp_path=tmp_path)
    assert with_bootstrap.creates_project is True


# ---------------------------------------------------------------------------
# Steps (FR-011, FR-012)
# ---------------------------------------------------------------------------


def test_step_without_done_when_awaits_an_explicit_continue(tmp_path: Path) -> None:
    manifest = parse(copy.deepcopy(MINIMAL_MANIFEST), tmp_path=tmp_path)
    assert manifest.steps[0].awaiting_continue is True


def test_step_with_done_when_does_not_await_continue(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["done_when"] = {"node_exists": {"block_type": "LoadCSV"}}
    manifest = parse(data, tmp_path=tmp_path)
    assert manifest.steps[0].awaiting_continue is False
    assert manifest.steps[0].done_when is not None


def test_duplicate_step_ids_are_rejected(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"] = [{"id": "one"}, {"id": "one"}]
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert "duplicate step id" in str(excinfo.value)


def test_step_fields_round_trip(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"] = [{"id": "one", "say": "Hello", "highlight": "palette", "route_to": "canvas"}]
    step = parse(data, tmp_path=tmp_path).steps[0]
    assert (step.say, step.highlight, step.route_to) == ("Hello", "palette", "canvas")


# ---------------------------------------------------------------------------
# Containment (FR-014, FR-015)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("escaping", ["../outside.py", "/etc/passwd", "a/../../outside.py"])
def test_asset_source_escaping_the_tutorial_directory_is_rejected(escaping: str, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"write": {"source": escaping, "destination": "notes.md"}}]
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert "source" in str(excinfo.value)


@pytest.mark.parametrize("escaping", ["../outside.py", "/etc/passwd", "a/../../outside.py"])
def test_write_destination_escaping_the_project_is_rejected(escaping: str, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"write": {"source": "assets/data/x.csv", "destination": escaping}}]
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert "destination" in str(excinfo.value)


def test_a_backslash_path_is_rejected_rather_than_meaning_two_things(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"write": {"source": "assets\\data\\x.csv", "destination": "x.csv"}}]
    with pytest.raises(ManifestValidationError):
        parse(data, tmp_path=tmp_path)


def test_cover_escaping_the_tutorial_directory_is_rejected(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["cover"] = "../secret.png"
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert "cover" in str(excinfo.value)


def test_containment_is_rejected_while_listing_not_while_writing(tmp_path: Path) -> None:
    """FR-014's stated reason: a bad tutorial fails while being listed."""
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"write": {"source": "../evil.py", "destination": "blocks/evil.py"}}]
    directory = write_tutorial(tmp_path / "bad", data)
    with pytest.raises(ManifestValidationError):
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    # Nothing was executed: the tutorial has no project and none was created.
    assert not (tmp_path / "project").exists()


def test_symlinked_asset_escape_is_rejected_when_the_directory_is_read(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.py").write_text("import os\n", encoding="utf-8")
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [{"write": {"source": "assets/link/evil.py", "destination": "notes.py"}}]
    directory = write_tutorial(tmp_path / "linky", data)
    (directory / "assets").mkdir(exist_ok=True)
    (directory / "assets" / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert "symbolic link" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Vocabulary rejection happens at validation (FR-049)
# ---------------------------------------------------------------------------


def test_unknown_vocabulary_term_is_rejected_at_manifest_validation(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["done_when"] = {"node_exsits": {"block_type": "LoadCSV"}}
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    message = str(excinfo.value)
    assert "node_exsits" in message
    assert "done_when" in message


def test_missing_term_argument_is_rejected_at_manifest_validation(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["done_when"] = {"file_exists": {}}
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    assert "path" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Tier: the driver field (FR-020)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", [TutorialSourceKind.USER, TutorialSourceKind.PROJECT])
def test_driver_is_rejected_for_user_and_project_tiers(kind: TutorialSourceKind, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    del data["steps"]
    data["driver"] = "pkg.module:Driver"
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path, kind=kind)
    message = str(excinfo.value)
    assert "driver" in message
    assert kind.value in message
    assert "core and packages" in message


@pytest.mark.parametrize("kind", [TutorialSourceKind.CORE, TutorialSourceKind.PACKAGE])
def test_driver_is_accepted_for_core_and_package_tiers(kind: TutorialSourceKind, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    del data["steps"]
    data["driver"] = "pkg.module:Driver"
    assert parse(data, tmp_path=tmp_path, kind=kind).driver == "pkg.module:Driver"


# ---------------------------------------------------------------------------
# Loading from disk (FR-005, FR-013)
# ---------------------------------------------------------------------------


def test_the_manifest_is_the_only_required_file(tmp_path: Path) -> None:
    directory = write_tutorial(tmp_path / "bare")
    manifest = load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert manifest.id == "example"
    assert not manifest.assets_dir.exists()


def test_the_committed_fixture_tutorial_loads(tmp_path: Path) -> None:
    manifest = load_manifest(FIXTURES / "minimal-core", source_kind=TutorialSourceKind.CORE)
    assert manifest.id == "minimal-core"
    assert manifest.order == 1
    assert manifest.requires.scistudio == ">=0.3.0"
    assert manifest.creates_project is True
    assert manifest.steps[0].done_when is not None
    assert manifest.steps[1].awaiting_continue is True
    assert manifest.step_by_id("drag-load") is manifest.steps[0]
    assert manifest.step_by_id("nope") is None


def test_invalid_yaml_names_the_file(tmp_path: Path) -> None:
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / "tutorial.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert "tutorial.yaml" in str(excinfo.value)


def test_a_missing_manifest_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(tmp_path / "absent", source_kind=TutorialSourceKind.CORE)
    assert "tutorial.yaml" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The published schema is the contract, and stays the only copy
# ---------------------------------------------------------------------------


def test_the_schema_document_is_valid_json_and_published_at_the_declared_path() -> None:
    assert SCHEMA_PATH.is_file()
    document = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert document["$schema"].startswith("https://json-schema.org/draft/")
    assert set(document["required"]) == {"manifest_version", "id", "title", "summary"}
    assert load_schema() == document


def test_the_schema_does_not_restate_the_vocabulary_or_the_replay_surfaces() -> None:
    """FR-045 and FR-061a each name one owning declaration; a second copy could drift."""
    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    for term in conditions_module.VOCABULARY:
        assert f'"{term}"' not in raw, f"the schema restates the vocabulary term {term!r}"
    for surface in actions_module.REPLAY_SURFACES:
        assert f'"{surface}"' not in raw, f"the schema restates the replay surface {surface!r}"


def test_the_reserved_asset_directories_are_the_five_the_spec_names() -> None:
    from scistudio.tutorials.manifest import RESERVED_ASSET_DIRS

    assert RESERVED_ASSET_DIRS == ("data", "code", "panels", "replay", "pages")


def test_yaml_round_trip_of_the_fixture_matches_the_parsed_model() -> None:
    raw = yaml.safe_load((FIXTURES / "minimal-core" / "tutorial.yaml").read_text(encoding="utf-8"))
    manifest = parse_manifest(
        raw,
        directory=FIXTURES / "minimal-core",
        source_kind=TutorialSourceKind.CORE,
        path=FIXTURES / "minimal-core" / "tutorial.yaml",
    )
    assert [step.id for step in manifest.steps] == [step["id"] for step in raw["steps"]]
