"""Manifest format and validation — ADR-053 spec §4.4 "Manifest" row.

Asserts: required fields; ``steps`` xor ``driver``; asset and destination
containment; an unknown vocabulary term rejected at validation (FR-049);
``driver`` rejected for the user and project tiers (FR-020). Plus the two
version cases FR-007a separates, the closed ``route_to`` and ``highlight`` sets,
and the single-declaration locks that keep the published schema from growing a
second copy of any of the five core-owned sets.
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
from scistudio.tutorials import manifest as manifest_module
from scistudio.tutorials.manifest import (
    HIGHLIGHT_SPECS,
    HIGHLIGHT_TARGETS,
    PREFILL_SPECS,
    PREFILL_TARGETS,
    ROUTE_TARGETS,
    SCHEMA_PATH,
    Highlight,
    HighlightSpec,
    ManifestValidationError,
    Prefill,
    PrefillSpec,
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
    data["steps"] = [{"id": "one", "say": "Hello", "highlight": "block_palette", "route_to": "canvas"}]
    step = parse(data, tmp_path=tmp_path).steps[0]
    assert (step.say, step.route_to) == ("Hello", "canvas")
    assert step.highlight == Highlight(target="block_palette")


# ---------------------------------------------------------------------------
# The two closed step vocabularies: route_to and highlight (FR-011)
# ---------------------------------------------------------------------------


def test_the_route_target_set_is_the_declared_one() -> None:
    assert set(ROUTE_TARGETS) == {
        "ai_chat",
        "terminal",
        "config",
        "logs",
        "plots",
        "history",
        "git",
        "canvas",
        "block_palette",
        "data_types",
    }


def test_route_targets_use_the_user_visible_tab_names() -> None:
    """The internal keys are ``ai`` and ``lineage``; manifests say what the user reads."""
    assert "history" in ROUTE_TARGETS
    assert "lineage" not in ROUTE_TARGETS
    assert "ai_chat" in ROUTE_TARGETS
    assert "ai" not in ROUTE_TARGETS


def test_the_highlight_target_set_is_the_declared_one() -> None:
    assert set(HIGHLIGHT_TARGETS) == {
        "block_palette",
        "canvas",
        "run_button",
        "new_menu_button",
        "plots_new_button",
        "history_restore_button",
        "bring_in_my_work_button",
        "data_preview",
        "config_panel",
        "palette_block",
        "node",
        "plot_card",
    }


def test_only_the_entity_targets_require_an_argument() -> None:
    """Which targets need to say *which one*, and what they call it.

    The split is the point of the vocabulary: a target naming a surface or a
    control that exists exactly once is already an address, and one naming an
    element among many of its kind is not. A target that grew a required
    argument without the frontend learning to read it would silently stop
    resolving, so the two sides are pinned here and in the frontend's parity
    test.
    """
    required = {spec.name: spec.required for spec in HIGHLIGHT_SPECS}
    assert {name: args for name, args in required.items() if args} == {
        "palette_block": ("block_type",),
        "node": ("block_type",),
        "plot_card": ("plot_id",),
    }


@pytest.mark.parametrize("target", sorted(ROUTE_TARGETS))
def test_every_route_target_is_accepted(target: str, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["route_to"] = target
    assert parse(data, tmp_path=tmp_path).steps[0].route_to == target


@pytest.mark.parametrize("spec", HIGHLIGHT_SPECS, ids=lambda spec: spec.name)
def test_every_highlight_target_is_accepted(spec: HighlightSpec, tmp_path: Path) -> None:
    args = {name: f"fixture_{name}" for name in spec.required}
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["highlight"] = spec.name if not args else {spec.name: args}

    assert parse(data, tmp_path=tmp_path).steps[0].highlight == Highlight(target=spec.name, args=args)


@pytest.mark.parametrize("spec", [spec for spec in HIGHLIGHT_SPECS if not spec.required], ids=lambda spec: spec.name)
def test_an_argument_free_target_may_also_be_written_as_a_mapping(spec: HighlightSpec, tmp_path: Path) -> None:
    """Both spellings mean the same thing, so neither is a trap.

    ``highlight: canvas`` is what an author will write, but the mapping form is
    the general one, and a target that accepted only the shorthand would make
    the format's one nested syntax conditional on which target you picked.
    """
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["highlight"] = {spec.name: {}}

    assert parse(data, tmp_path=tmp_path).steps[0].highlight == Highlight(target=spec.name)


@pytest.mark.parametrize("spec", [spec for spec in HIGHLIGHT_SPECS if spec.required], ids=lambda spec: spec.name)
def test_an_entity_target_without_its_argument_is_rejected(spec: HighlightSpec, tmp_path: Path) -> None:
    """The failure this vocabulary exists to prevent, caught at authoring time.

    ``highlight: palette_block`` with no ``block_type`` is an author asking to
    point at "a block in the palette" — there are thirty. Accepting it would
    light up the panel and leave the reader exactly as lost as the strip that
    this replaced, with nothing anywhere saying the guidance was incomplete.
    """
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["highlight"] = spec.name

    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)

    message = str(excinfo.value)
    assert spec.name in message
    for name in spec.required:
        assert name in message


def test_an_argument_the_target_does_not_take_is_rejected(tmp_path: Path) -> None:
    """An argument nothing reads is an author believing they said more than they did.

    Written with the required argument present, so this is the "and also" case
    rather than the missing-argument one: ``block_type`` addresses the element
    and ``block_name`` addresses nothing, and accepting it silently would let a
    manifest carry guidance the frontend never sees.
    """
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["highlight"] = {"palette_block": {"block_type": "load_data", "block_name": "Load"}}

    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)

    assert "block_name" in str(excinfo.value)


def test_a_highlight_naming_two_targets_is_rejected(tmp_path: Path) -> None:
    """One step points at one thing; a spotlight cannot be in two places."""
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["highlight"] = {"canvas": {}, "run_button": {}}

    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)

    assert "exactly one target" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The third closed step vocabulary: prefill (FR-011b)
# ---------------------------------------------------------------------------


def test_the_prefill_target_set_is_the_declared_one() -> None:
    """The vocabulary is closed for the same reason highlight's is.

    A prefill only does anything once the frontend seeds the dialog it names,
    so a target with no consumer is a manifest line that silently does nothing.
    """
    assert set(PREFILL_TARGETS) == {"new_custom_block", "new_data_type", "new_plot", "block_config"}


@pytest.mark.parametrize("spec", PREFILL_SPECS, ids=lambda spec: spec.name)
def test_every_prefill_target_is_accepted(spec: PrefillSpec, tmp_path: Path) -> None:
    args = {name: f"fixture_{name}" for name in spec.required}
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["prefill"] = [{spec.name: args}]

    assert parse(data, tmp_path=tmp_path).steps[0].prefill == (Prefill(target=spec.name, args=args),)


def test_a_step_declares_no_prefill_by_default(tmp_path: Path) -> None:
    """The field is optional, and its absence is an empty tuple rather than None."""
    assert parse(copy.deepcopy(MINIMAL_MANIFEST), tmp_path=tmp_path).steps[0].prefill == ()


@pytest.mark.parametrize("spec", [spec for spec in PREFILL_SPECS if spec.required], ids=lambda spec: spec.name)
def test_a_prefill_missing_a_value_it_seeds_is_rejected(spec: PrefillSpec, tmp_path: Path) -> None:
    """A target with nothing to seed would open the dialog on its own default.

    Which is the state this field exists to fix, so accepting it silently would
    leave the author believing they had fixed it.
    """
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["prefill"] = [{spec.name: {}}]

    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)

    message = str(excinfo.value)
    assert spec.name in message
    for name in spec.required:
        assert name in message


def test_a_prefill_value_the_target_does_not_take_is_rejected(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["prefill"] = [{"new_custom_block": {"filename": "my_block", "destination": "library"}}]

    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)

    assert "destination" in str(excinfo.value)


@pytest.mark.parametrize("bad", ["new_block", "new-custom-block", "New custom block", "config_panel"])
def test_a_prefill_target_outside_the_set_is_rejected(bad: str, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["prefill"] = [{bad: {"filename": "x"}}]

    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)

    message = str(excinfo.value)
    assert bad in message
    for target in PREFILL_TARGETS:
        assert target in message


def test_one_step_prefilling_the_same_dialog_twice_is_rejected(tmp_path: Path) -> None:
    """A dialog opens holding one set of values, so two answers is an author error."""
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["prefill"] = [
        {"new_custom_block": {"filename": "first"}},
        {"new_custom_block": {"filename": "second"}},
    ]

    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)

    assert "twice" in str(excinfo.value)


def test_a_prefill_naming_two_targets_in_one_entry_is_rejected(tmp_path: Path) -> None:
    """The single-key mapping shape ``do`` uses, enforced the way ``do`` enforces it.

    Refused by the published schema before the parser sees it, which is why the
    assertion is on the field path rather than on a message this module owns.
    """
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["prefill"] = [{"new_custom_block": {"filename": "x"}, "canvas": {}}]

    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)

    assert "steps[0].prefill[0]" in str(excinfo.value)


@pytest.mark.parametrize("bad", ["new_custom_block", {"new_custom_block": {"filename": "x"}}])
def test_a_prefill_that_is_not_a_list_is_rejected(bad: Any, tmp_path: Path) -> None:
    """A step may seed several dialogs, so the field is a list even for one."""
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["prefill"] = bad

    with pytest.raises(ManifestValidationError):
        parse(data, tmp_path=tmp_path)


@pytest.mark.parametrize("bad", ["lineage", "ai", "preview", "Canvas", "settings_tab"])
def test_a_route_to_outside_the_set_is_rejected_naming_the_field_and_the_values(bad: str, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["route_to"] = bad
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    message = str(excinfo.value)
    assert "route_to" in message
    assert bad in message
    for target in ROUTE_TARGETS:
        assert target in message


@pytest.mark.parametrize("bad", ["palette", "block-palette", "run", "the big green button"])
def test_a_highlight_outside_the_set_is_rejected_naming_the_field_and_the_values(bad: str, tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["highlight"] = bad
    with pytest.raises(ManifestValidationError) as excinfo:
        parse(data, tmp_path=tmp_path)
    message = str(excinfo.value)
    assert "highlight" in message
    assert bad in message
    for target in HIGHLIGHT_TARGETS:
        assert target in message


def test_omitting_route_to_and_highlight_stays_legal(tmp_path: Path) -> None:
    step = parse(copy.deepcopy(MINIMAL_MANIFEST), tmp_path=tmp_path).steps[0]
    assert step.route_to is None
    assert step.highlight is None


def test_a_bad_route_target_fails_the_author_while_the_tutorial_is_listed(tmp_path: Path) -> None:
    """The same argument FR-049 makes for terms: a typo must not reach the user."""
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["route_to"] = "lineage"
    directory = write_tutorial(tmp_path / "typo", data)
    with pytest.raises(ManifestValidationError):
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)


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
    try:
        (directory / "assets" / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        # Capability probe, not a platform skip: on Windows, creating a
        # symlink needs Developer Mode or elevation; with either granted,
        # this test runs instead of skipping (#2075).
        pytest.skip("symlink creation is not permitted in this environment")
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


def test_being_handed_the_manifest_instead_of_its_directory_says_so(tmp_path: Path) -> None:
    """Joining the filename on again would report ``.../tutorial.yaml/tutorial.yaml``."""
    directory = write_tutorial(tmp_path / "bare")
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory / "tutorial.yaml", source_kind=TutorialSourceKind.CORE)
    message = str(excinfo.value)
    assert "is a file" in message
    assert "tutorial.yaml/tutorial.yaml" not in message
    assert str(directory) in message


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


def test_the_schema_does_not_restate_any_of_the_closed_sets() -> None:
    """Each closed set names one owning declaration; a second copy could drift."""
    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    owned: dict[str, frozenset[str]] = {
        "vocabulary term": conditions_module.VOCABULARY,
        "replay surface": actions_module.REPLAY_SURFACES,
        "route target": manifest_module.ROUTE_TARGETS,
        "highlight target": manifest_module.HIGHLIGHT_TARGETS,
        "prefill target": manifest_module.PREFILL_TARGETS,
        "ui event name": conditions_module.UI_EVENT_NAMES,
    }
    for label, members in owned.items():
        for member in members:
            assert f'"{member}"' not in raw, f"the schema restates the {label} {member!r}"


def test_the_reserved_asset_directories_are_the_six_the_spec_names() -> None:
    from scistudio.tutorials.manifest import RESERVED_ASSET_DIRS

    assert RESERVED_ASSET_DIRS == ("data", "code", "panels", "replay", "workflows", "pages")


def test_yaml_round_trip_of_the_fixture_matches_the_parsed_model() -> None:
    raw = yaml.safe_load((FIXTURES / "minimal-core" / "tutorial.yaml").read_text(encoding="utf-8"))
    manifest = parse_manifest(
        raw,
        directory=FIXTURES / "minimal-core",
        source_kind=TutorialSourceKind.CORE,
        path=FIXTURES / "minimal-core" / "tutorial.yaml",
    )
    assert [step.id for step in manifest.steps] == [step["id"] for step in raw["steps"]]


# ---------------------------------------------------------------------------
# Reading tutorials, derived rather than declared
# ---------------------------------------------------------------------------


def test_a_tutorial_whose_steps_only_wait_on_the_reader_is_a_reading_tutorial(tmp_path: Path) -> None:
    """The Learning Center's Reading tab is filled from this property.

    A step with no ``done_when`` waits on an explicit continue, and
    ``page_reached`` waits on the reader turning a page. Neither judges any
    product fact, so a tutorial built only from them asks the user to read and
    nothing else.
    """
    manifest = parse(
        {
            **MINIMAL_MANIFEST,
            "steps": [
                {"id": "open", "say": "Here is what SciStudio gives you."},
                {"id": "blocks", "say": "Blocks.", "done_when": {"page_reached": {"page": "blocks"}}},
            ],
        },
        tmp_path=tmp_path,
    )

    assert manifest.is_reading_only is True


def test_one_step_judging_a_product_fact_makes_the_whole_tutorial_hands_on(tmp_path: Path) -> None:
    """However much prose it carries. The judged step is work the user must do."""
    manifest = parse(
        {
            **MINIMAL_MANIFEST,
            "steps": [
                {"id": "read", "say": "Blocks are the unit of work."},
                {"id": "do-it", "say": "Now run it.", "done_when": {"run_succeeded": {}}},
            ],
        },
        tmp_path=tmp_path,
    )

    assert manifest.is_reading_only is False


def test_a_driver_driven_tutorial_is_not_classified_as_reading(tmp_path: Path) -> None:
    """Its steps are the driver's to produce and are not on disk to inspect."""
    manifest = parse(
        {
            "manifest_version": 1,
            "id": "example",
            "title": "Example",
            "summary": "A tutorial used by the tests.",
            "driver": "scistudio_blocks_imaging.tutorials:Driver",
        },
        tmp_path=tmp_path,
        kind=TutorialSourceKind.PACKAGE,
    )

    assert manifest.is_reading_only is False


def test_the_reading_terms_are_a_subset_of_the_vocabulary() -> None:
    """A reading term that is not a term at all could never be written down."""
    assert conditions_module.READING_TERMS <= conditions_module.VOCABULARY
    assert frozenset({"page_reached"}) == conditions_module.READING_TERMS


# ---------------------------------------------------------------------------
# The reading step's pages field (FR-011, FR-014)
# ---------------------------------------------------------------------------


def _reading_manifest(pages: list[str]) -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "id": "reads",
        "title": "Reads",
        "summary": "A reading tutorial.",
        "steps": [
            {
                "id": "read-on",
                "say": "Read these.",
                "pages": pages,
                "done_when": {"page_reached": {"page": pages[0].split(".")[0]}},
            }
        ],
    }


def test_a_step_may_declare_pages_that_exist_under_assets_pages(tmp_path: Path) -> None:
    directory = write_tutorial(
        tmp_path / "reads",
        _reading_manifest(["intro", "closing.md"]),
        files={"assets/pages/intro.md": "# Intro\n", "assets/pages/closing.md": "# Closing\n"},
    )
    manifest = load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert manifest.steps[0].pages == ("intro", "closing.md")


def test_a_missing_page_fails_the_author_at_load(tmp_path: Path) -> None:
    directory = write_tutorial(
        tmp_path / "reads",
        _reading_manifest(["intro", "absent"]),
        files={"assets/pages/intro.md": "# Intro\n"},
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert "steps[0].pages" in str(excinfo.value)
    assert "absent" in str(excinfo.value)


def test_a_page_name_cannot_escape_the_pages_directory(tmp_path: Path) -> None:
    directory = write_tutorial(
        tmp_path / "reads",
        _reading_manifest(["../../tutorial"]),
        files={"assets/pages/intro.md": "# Intro\n"},
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert "steps[0].pages" in str(excinfo.value)


def test_a_duplicate_page_in_one_step_is_rejected(tmp_path: Path) -> None:
    directory = write_tutorial(
        tmp_path / "reads",
        _reading_manifest(["intro", "intro"]),
        files={"assets/pages/intro.md": "# Intro\n"},
    )
    with pytest.raises(ManifestValidationError, match="listed twice"):
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)


def test_a_paged_tutorial_judged_by_page_reached_reads_as_reading_only(tmp_path: Path) -> None:
    """The dispatch's is_reading_only check: all/any over page_reached is still reading.

    ``is_reading_only`` reads ``done_when.terms() <= READING_TERMS``, and
    ``terms()`` unions through combinators — so wrapping ``page_reached`` in
    ``all``/``any`` must not push a reading tutorial into the hands-on lists.
    """
    payload = {
        "manifest_version": 1,
        "id": "reads",
        "title": "Reads",
        "summary": "A reading tutorial.",
        "steps": [
            {
                "id": "read-on",
                "say": "Read these.",
                "pages": ["intro", "closing"],
                "done_when": {
                    "all": [
                        {"page_reached": {"page": "intro"}},
                        {"any": [{"page_reached": {"page": "closing"}}]},
                    ]
                },
            },
            {"id": "done", "say": "Done."},
        ],
    }
    directory = write_tutorial(
        tmp_path / "reads",
        payload,
        files={"assets/pages/intro.md": "# Intro\n", "assets/pages/closing.md": "# Closing\n"},
    )
    manifest = load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert manifest.is_reading_only is True


# ---------------------------------------------------------------------------
# The step trigger (FR-011, #2061)
# ---------------------------------------------------------------------------


def _triggered_manifest(trigger: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "id": "triggered",
        "title": "Triggered",
        "summary": "A step with a trigger.",
        "steps": [{"id": "press-play", "say": "Press Play.", "trigger": trigger}],
    }


def test_a_step_may_declare_a_trigger(tmp_path: Path) -> None:
    directory = write_tutorial(
        tmp_path / "triggered",
        _triggered_manifest(
            {"label": "Play", "do": [{"write": {"source": "assets/data/a.txt", "destination": "data/a.txt"}}]}
        ),
        files={"assets/data/a.txt": "hello"},
    )
    manifest = load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    trigger = manifest.steps[0].trigger
    assert trigger is not None
    assert trigger.label == "Play"
    assert len(trigger.do) == 1


def test_a_trigger_requires_a_label(tmp_path: Path) -> None:
    directory = write_tutorial(
        tmp_path / "triggered",
        _triggered_manifest({"do": [{"write": {"source": "assets/data/a.txt", "destination": "data/a.txt"}}]}),
        files={"assets/data/a.txt": "hello"},
    )
    with pytest.raises(ManifestValidationError, match="label"):
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)


def test_a_trigger_requires_at_least_one_action(tmp_path: Path) -> None:
    """A button that does nothing is a mistake, not a step."""
    directory = write_tutorial(tmp_path / "triggered", _triggered_manifest({"label": "Play", "do": []}))
    # The schema's minItems fires first for an empty list; the parser's own
    # message covers the None-shaped spelling. Either way the author is told.
    with pytest.raises(ManifestValidationError, match=r"at least (1 item|one action)"):
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)


def test_a_trigger_destination_is_contained_like_any_other(tmp_path: Path) -> None:
    """FR-015 reaches the trigger's do list: pressing the button reaches the project."""
    directory = write_tutorial(
        tmp_path / "triggered",
        _triggered_manifest(
            {"label": "Play", "do": [{"write": {"source": "assets/data/a.txt", "destination": "../outside.txt"}}]}
        ),
        files={"assets/data/a.txt": "hello"},
    )
    with pytest.raises(ManifestValidationError, match="triggered"):
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)


def test_a_trigger_write_into_an_executed_path_is_tier_graded(tmp_path: Path) -> None:
    """FR-020a reaches the trigger's do list for the ungraded tiers."""
    directory = write_tutorial(
        tmp_path / "triggered",
        _triggered_manifest(
            {"label": "Play", "do": [{"write": {"source": "assets/data/a.py", "destination": "blocks/a.py"}}]}
        ),
        files={"assets/data/a.py": "print()"},
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=TutorialSourceKind.USER)
    assert "trigger.do" in str(excinfo.value)
    assert "blocks" in str(excinfo.value)
    # The same manifest is legal for core, whose tier may write there.
    load_manifest(directory, source_kind=TutorialSourceKind.CORE)
