"""The eleven built-in panel documents on disk (ADR-054 spec 1, T-009, #2229).

SC-003 measures the migration by each built-in panel *having a panel directory*
and no built-in panel rendering through a compiled-in component. These tests
measure the first half directly and mechanically, on the files themselves.

They deliberately do not import :mod:`scistudio.panels.registry`, the router,
the discovery walk, or the declaration model. Those are in flight in a sibling
task; a test that imported them would fail for reasons that have nothing to do
with whether the eleven documents are correct, and would stop being a check on
the documents at all. Everything here reads the tree.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILTIN_ROOT = REPO_ROOT / "src" / "scistudio" / "panels" / "builtin"

#: The API version every built-in document declares. One constant, and the
#: backend owns it (D-010); this is the value the documents were written to.
EXPECTED_API_VERSION = "1"

#: The nine displaying panels: id -> (target types, provider attribute).
DISPLAYING_PANELS: dict[str, tuple[tuple[str, ...], str]] = {
    "core.dataframe.basic": (("DataFrame",), "dataframe_panel"),
    "core.array.basic": (("Array",), "array_panel"),
    "core.series.basic": (("Series",), "series_panel"),
    "core.text.basic": (("Text",), "text_panel"),
    "core.artifact.basic": (("Artifact",), "artifact_panel"),
    "core.composite.basic": (("CompositeData",), "composite_panel"),
    "core.collection.basic": (("Collection",), "collection_panel"),
    "core.plot.basic": (("PlotArtifact",), "plot_panel"),
    "core.base.fallback": (("DataObject",), "base_fallback_panel"),
}

#: The two producing panels, declared on their block classes rather than by type.
PRODUCING_PANELS: tuple[str, ...] = (
    "core.interactive.data_router",
    "core.interactive.pair_editor",
)

ALL_PANEL_IDS: tuple[str, ...] = tuple(DISPLAYING_PANELS) + PRODUCING_PANELS

#: The D-017 message contract, panel to host. `read` carries a patch of the
#: panel's own query state, `resource` a bounded follow-up read of one named
#: resource, and `host_action` the chrome the frame cannot perform for itself.
#: Five meanings behind one type is what D-017 refused, so this list is the
#: shape of the wire and a document that sends anything else is a defect.
PANEL_TO_HOST_TYPES = frozenset({"ready", "read", "resource", "host_action", "emit", "error", "state"})

#: The mirror list, host to panel.
HOST_TO_PANEL_TYPES = frozenset(
    {
        "init",
        "update",
        "read_result",
        "resource_result",
        "host_action_result",
        "error",
        "state_request",
        "teardown",
    }
)

#: The three actions `host_action` names (D-017).
HOST_ACTIONS = frozenset({"export", "download", "editor_handoff"})

#: The D-007 declaration shape. Required fields first, then the optional ones
#: with the type each must have when present.
REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "panel_id": str,
    "display_name": str,
    "target_types": list,
    "capability": str,
    "entry": str,
    "api_version": str,
}
OPTIONAL_FIELDS: dict[str, type | tuple[type, ...]] = {
    "features": list,
    "priority": int,
    "supports_collection": bool,
    "provider": str,
}


def declaration(panel_id: str) -> dict[str, object]:
    """Parse one panel's ``panel.json``."""
    return json.loads((BUILTIN_ROOT / panel_id / "panel.json").read_text(encoding="utf-8"))


def entry_document(panel_id: str) -> str:
    """Read one panel's entry document, as named by its own declaration."""
    entry = str(declaration(panel_id)["entry"])
    return (BUILTIN_ROOT / panel_id / entry).read_text(encoding="utf-8")


#: Comment forms stripped before a self-containment scan. A panel document that
#: *documents* the rule it obeys — "no <link rel=stylesheet>", or a TODO citing
#: an issue URL — must not fail the check on the rule it is describing. What is
#: measured is what the document loads, and a comment loads nothing.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"^[ \t]*//.*$", re.MULTILINE)


def executable_document(panel_id: str) -> str:
    """The entry document with its comments removed."""
    document = entry_document(panel_id)
    document = HTML_COMMENT.sub("", document)
    document = BLOCK_COMMENT.sub("", document)
    return LINE_COMMENT.sub("", document)


# ---------------------------------------------------------------------------
# The directories exist (SC-003, first half)
# ---------------------------------------------------------------------------


def test_eleven_panel_directories_and_no_others() -> None:
    """Exactly the eleven built-in panels have a directory, and nothing else."""
    found = sorted(entry.name for entry in BUILTIN_ROOT.iterdir() if entry.is_dir())
    assert found == sorted(ALL_PANEL_IDS)


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_panel_directory_holds_declaration_and_entry(panel_id: str) -> None:
    """FR-002: a panel is a directory with a declaration and one entry document."""
    directory = BUILTIN_ROOT / panel_id
    assert (directory / "panel.json").is_file()
    entry = str(declaration(panel_id)["entry"])
    assert entry == "index.html", "the built-ins all use the default entry name"
    assert (directory / entry).is_file()


# ---------------------------------------------------------------------------
# The declaration validates against the D-007 shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_declaration_carries_every_required_field(panel_id: str) -> None:
    """FR-003: id, display name, target types, capability and entry are required."""
    data = declaration(panel_id)
    for field, expected_type in REQUIRED_FIELDS.items():
        assert field in data, f"{panel_id}: missing required field {field!r}"
        assert isinstance(data[field], expected_type), f"{panel_id}: {field!r} has the wrong type"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_declaration_has_no_field_outside_the_shape(panel_id: str) -> None:
    """A declaration carries the D-007 fields and nothing invented locally."""
    known = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    unknown = set(declaration(panel_id)) - known
    assert unknown == set(), f"{panel_id}: unknown declaration field(s) {sorted(unknown)}"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_optional_fields_have_the_declared_types(panel_id: str) -> None:
    data = declaration(panel_id)
    for field, expected_type in OPTIONAL_FIELDS.items():
        if field in data:
            assert isinstance(data[field], expected_type), f"{panel_id}: {field!r} has the wrong type"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_declared_id_matches_its_directory(panel_id: str) -> None:
    """The directory is named for the panel it holds, so a copy keeps its id."""
    assert declaration(panel_id)["panel_id"] == panel_id


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_every_panel_declares_the_one_api_version(panel_id: str) -> None:
    """FR-004: one API version, shared by the host and the panels it loads."""
    assert declaration(panel_id)["api_version"] == EXPECTED_API_VERSION


@pytest.mark.parametrize(("panel_id", "spec"), sorted(DISPLAYING_PANELS.items()))
def test_displaying_panels_keep_their_target_types_and_provider(
    panel_id: str, spec: tuple[tuple[str, ...], str]
) -> None:
    """FR-033: the nine keep the ids, target types and providers they had."""
    target_types, provider_attribute = spec
    data = declaration(panel_id)
    assert tuple(data["target_types"]) == target_types
    assert data["provider"] == f"scistudio.panels.fallbacks:{provider_attribute}"


def test_collection_panel_supports_collections() -> None:
    """The collection fallback is the core tier-7 catch-all for a Collection."""
    assert declaration("core.collection.basic")["supports_collection"] is True


def test_base_fallback_sorts_below_every_other_panel() -> None:
    """The tier-8 universal fallback keeps the priority its PanelSpec carried."""
    assert declaration("core.base.fallback")["priority"] == -100


def test_only_the_base_fallback_has_a_negative_priority() -> None:
    for panel_id in ALL_PANEL_IDS:
        priority = declaration(panel_id).get("priority", 0)
        if panel_id == "core.base.fallback":
            continue
        assert priority == 0, f"{panel_id}: unexpected priority {priority}"


# ---------------------------------------------------------------------------
# The capability split (FR-006)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("panel_id", sorted(DISPLAYING_PANELS))
def test_the_nine_declare_displaying(panel_id: str) -> None:
    assert declaration(panel_id)["capability"] == "displaying"


@pytest.mark.parametrize("panel_id", PRODUCING_PANELS)
def test_the_two_interactive_panels_declare_producing(panel_id: str) -> None:
    assert declaration(panel_id)["capability"] == "producing"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_capability_is_one_of_exactly_two(panel_id: str) -> None:
    """FR-006: the enumeration has exactly two members."""
    assert declaration(panel_id)["capability"] in {"displaying", "producing"}


@pytest.mark.parametrize("panel_id", sorted(DISPLAYING_PANELS))
def test_a_displaying_panel_never_sends_emit(panel_id: str) -> None:
    """ADR-054 3.6: a displaying panel emits nothing."""
    document = executable_document(panel_id)
    assert '"emit"' not in document
    assert "'emit'" not in document


@pytest.mark.parametrize("panel_id", PRODUCING_PANELS)
def test_a_producing_panel_emits_through_the_one_outbound_path(panel_id: str) -> None:
    """The decision leaves as `emit`, carrying code the panel does not interpret."""
    document = entry_document(panel_id)
    assert 'post("emit"' in document
    assert "scistudio.output(" in document


# ---------------------------------------------------------------------------
# The message contract on the wire (D-017)
#
# The host half of this contract is written from the same text, in
# frontend/src/panels/. These assertions are the panel half. If the two ever
# disagree, that is meant to surface here as a failure rather than as one side
# quietly bending to the other's shape.
# ---------------------------------------------------------------------------

#: A message send. Every outbound type is either spelled as a literal at a
#: `post("...")` / `request("...")` call, or forwarded through the single
#: `post(type, payload)` inside the `request` helper. The lookbehind skips the
#: two function *definitions*, which name a parameter rather than sending
#: anything.
OUTBOUND_CALL = re.compile(r"(?<!function )\b(?:post|request)\(\s*(?:\"([a-z_]+)\"|([A-Za-z_$][\w$]*))")

#: The literal action passed to the `hostAction` wrapper.
HOST_ACTION_CALL = re.compile(r"\bhostAction\(\s*\"([a-z_]+)\"")

#: An inbound message the document handles, as a `case` of its message switch.
INBOUND_CASE = re.compile(r"case\s+\"([a-z_]+)\"\s*:")


def outbound_message_types(panel_id: str) -> set[str]:
    """Every message type a document can send, read off its send sites."""
    document = executable_document(panel_id)
    types: set[str] = set()
    for literal, identifier in OUTBOUND_CALL.findall(document):
        if literal:
            types.add(literal)
            continue
        # The one send whose type is not a literal is `request`'s own forward to
        # `post`. Anything else would be a type this file cannot account for.
        assert identifier == "type", f"{panel_id}: a message is sent with a computed type {identifier!r}"
        assert "function request(type, body)" in document, f"{panel_id}: unexplained computed send"
    return types


def read_call_arguments(panel_id: str) -> list[str]:
    """The argument text of every `read(...)` call in a document."""
    document = executable_document(panel_id)
    arguments: list[str] = []
    for match in re.finditer(r"\bread\(", document):
        depth = 1
        index = match.end()
        while index < len(document) and depth:
            if document[index] == "(":
                depth += 1
            elif document[index] == ")":
                depth -= 1
            index += 1
        arguments.append(document[match.end() : index - 1])
    return arguments


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_sends_no_message_type_outside_the_contract(panel_id: str) -> None:
    """D-017: the panel-to-host types are a closed list."""
    sent = outbound_message_types(panel_id)
    assert sent, f"{panel_id}: no outbound message type found at all"
    unknown = sent - PANEL_TO_HOST_TYPES
    assert unknown == set(), f"{panel_id}: sends message type(s) outside the contract: {sorted(unknown)}"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_read_payload_carries_no_action_key(panel_id: str) -> None:
    """The regression guard for what D-017 refused.

    A `read` is a patch of the panel's own query state. An `action` key inside
    it would be five meanings behind one type again, and the export, the
    download, the editor handoff and the child routing would stop being legible
    on the wire.
    """
    for argument in read_call_arguments(panel_id):
        assert "action" not in argument, f"{panel_id}: a read payload names an action: {argument.strip()!r}"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_handles_no_inbound_type_outside_the_contract(panel_id: str) -> None:
    """The mirror: a document answers only host-to-panel types it could be sent."""
    handled = set(INBOUND_CASE.findall(executable_document(panel_id)))
    unknown = handled - HOST_TO_PANEL_TYPES
    assert unknown == set(), f"{panel_id}: handles inbound type(s) outside the contract: {sorted(unknown)}"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_host_action_names_only_the_three_actions(panel_id: str) -> None:
    """D-017: `host_action` carries export, download or editor_handoff."""
    named = set(HOST_ACTION_CALL.findall(executable_document(panel_id)))
    unknown = named - HOST_ACTIONS
    assert unknown == set(), f"{panel_id}: unknown host action(s) {sorted(unknown)}"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_a_request_is_answered_by_its_own_result_type(panel_id: str) -> None:
    """Each request type a document sends has its answer handled, and no
    document handles an answer to a request it never sends.
    """
    document = executable_document(panel_id)
    sent = outbound_message_types(panel_id)
    handled = set(INBOUND_CASE.findall(document))
    for request_type in ("read", "resource", "host_action"):
        result_type = f"{request_type}_result"
        assert (request_type in sent) == (result_type in handled), (
            f"{panel_id}: sends {request_type}={request_type in sent} but handles "
            f"{result_type}={result_type in handled}"
        )


@pytest.mark.parametrize("panel_id", sorted(DISPLAYING_PANELS))
def test_a_displaying_panel_still_gets_the_bounded_read_channels(panel_id: str) -> None:
    """FR-011 withholds the emission path from a displaying panel, not the
    bounded read FR-010 requires the host to supply. Only `emit` is gated, so a
    displaying panel sending `read`, `resource` or `host_action` is correct.
    """
    sent = outbound_message_types(panel_id)
    assert "emit" not in sent
    assert "ready" in sent


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_no_panel_implements_the_emission_whitelist(panel_id: str) -> None:
    """FR-012 / ADR-054 3.6: the statement check belongs where an emission is
    queued, which is the explore session. A panel that parsed what it emits
    would be interpreting it.
    """
    document = executable_document(panel_id)
    for forbidden in ("new Function(", "eval(", "ast.parse", "parseStatements"):
        assert forbidden not in document, f"{panel_id}: {forbidden} has no place in a panel document"


# ---------------------------------------------------------------------------
# Self-containment (FR-034, A-004)
# ---------------------------------------------------------------------------

#: An external script tag: `<script src=...>` in any spelling.
SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=", re.IGNORECASE)
#: An external stylesheet link.
STYLESHEET_LINK = re.compile(r"<link\b[^>]*\brel\s*=\s*[\"']?stylesheet", re.IGNORECASE)
#: A dynamic module import, and the static forms that only work in a module.
DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(")
STATIC_IMPORT = re.compile(r"^\s*import\s+[\w{*]", re.MULTILINE)
#: A CSS `@import`, which is an external stylesheet by another name.
CSS_IMPORT = re.compile(r"@import\b", re.IGNORECASE)
#: Anything reaching off this origin.
REMOTE_URL = re.compile(r"\bhttps?://(?!www\.w3\.org/)", re.IGNORECASE)


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_loads_no_external_script(panel_id: str) -> None:
    assert SCRIPT_SRC.search(executable_document(panel_id)) is None


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_loads_no_external_stylesheet(panel_id: str) -> None:
    document = executable_document(panel_id)
    assert STYLESHEET_LINK.search(document) is None
    assert CSS_IMPORT.search(document) is None


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_imports_no_shared_runtime(panel_id: str) -> None:
    """A-004: no shared runtime import, so a fork gets the whole panel."""
    document = executable_document(panel_id)
    assert DYNAMIC_IMPORT.search(document) is None
    assert STATIC_IMPORT.search(document) is None


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_names_no_remote_url(panel_id: str) -> None:
    """No CDN, and nothing else off this origin. The one exception is the SVG
    namespace, which is an identifier rather than something fetched.
    """
    found = REMOTE_URL.findall(executable_document(panel_id))
    assert found == [], f"{panel_id}: remote reference(s) {found}"


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_carries_its_own_markup_styles_and_script(panel_id: str) -> None:
    """FR-002/FR-034: one file holding all three, not a shell around a bundle."""
    document = entry_document(panel_id)
    assert "<style>" in document
    assert "<script>" in document
    assert "<body>" in document


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_panel_directory_holds_nothing_but_its_own_two_files(panel_id: str) -> None:
    """A panel a person copies is a directory copy, so there is nothing else in
    it to go stale — no build output, no shared asset, no lockfile.
    """
    found = sorted(entry.name for entry in (BUILTIN_ROOT / panel_id).iterdir())
    assert found == ["index.html", "panel.json"]


# ---------------------------------------------------------------------------
# The message contract each document speaks (D-011, D-016)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_answers_init_with_ready(panel_id: str) -> None:
    """FR-009: the handshake is answered, and with the declared API version."""
    document = entry_document(panel_id)
    assert 'post("ready"' in document
    assert "PANEL_API_VERSION" in document
    assert f'PANEL_API_VERSION = "{EXPECTED_API_VERSION}"' in document


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_speaks_the_envelope_and_checks_the_token(panel_id: str) -> None:
    """D-011 / FR-008: every message carries the marker and the mount's token,
    and a message whose token does not match is ignored.
    """
    document = entry_document(panel_id)
    assert "scistudio_panel: PANEL_MESSAGE_MARKER" in document
    assert "PANEL_MESSAGE_MARKER = 1" in document
    assert "data.scistudio_panel !== PANEL_MESSAGE_MARKER" in document
    assert "data.token !== token" in document


@pytest.mark.parametrize("panel_id", ALL_PANEL_IDS)
def test_document_handles_teardown(panel_id: str) -> None:
    document = entry_document(panel_id)
    assert 'case "teardown"' in document


# ---------------------------------------------------------------------------
# Packaging (the wheel is the only way these reach an installed SciStudio)
# ---------------------------------------------------------------------------


def test_package_data_ships_the_panel_documents() -> None:
    """A panel directory is named for its panel id, so ``packages.find`` cannot
    see it. Without an explicit package-data pattern an installed wheel has no
    built-in panels at all, and the wheel-release-smoke job would be the first
    place it showed up.
    """
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = pyproject["tool"]["setuptools"]["package-data"]["scistudio"]
    assert "panels/builtin/**/*" in patterns


def test_package_data_pattern_matches_every_declaration_and_document() -> None:
    """The pattern is checked against the real files, not just its own spelling."""
    package_root = REPO_ROOT / "src" / "scistudio"
    matched = {path.relative_to(package_root).as_posix() for path in package_root.glob("panels/builtin/**/*")}
    for panel_id in ALL_PANEL_IDS:
        assert f"panels/builtin/{panel_id}/panel.json" in matched
        assert f"panels/builtin/{panel_id}/index.html" in matched


def test_the_python_providers_are_unchanged() -> None:
    """FR-033: the panels were rewritten; their providers were not. Read the
    source rather than importing it, so this stays a check on the file even
    while the surrounding subsystem is being changed.
    """
    source = (REPO_ROOT / "src" / "scistudio" / "panels" / "fallbacks.py").read_text(encoding="utf-8")
    for _target_types, provider_attribute in DISPLAYING_PANELS.values():
        assert f"def {provider_attribute}(" in source
