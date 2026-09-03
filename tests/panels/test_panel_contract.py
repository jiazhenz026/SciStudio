"""The shared panel contract: one version, two capabilities, one manifest.

ADR-054 spec 1, T-002 and T-003. Covers FR-001 to FR-006, the D-007 on-disk
form, and SC-001's half about the version constant.

The version test is written as a search of the tree rather than as an identity
check between two imports, because SC-001 is a claim about the *tree*: two
modules can agree at runtime while a third definition sits in a file nobody
imported during the test.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scistudio.core.panels import (
    DEFAULT_PANEL_ENTRY,
    PANEL_API_VERSION,
    PANEL_TIER_ORDER,
    REQUIRED_DECLARATION_FIELDS,
    InvalidDeclarationFieldError,
    MissingDeclarationFieldError,
    PanelCapability,
    PanelDeclarationError,
    PanelManifest,
    PanelTier,
    UnreadableDeclarationError,
    manifest_from_declaration,
    read_panel_declaration,
)

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "scistudio"

#: The declaration `W4-builtin` ships for the plot panel, verbatim. The
#: validator must accept it exactly as written — it is the agreed cross-agent
#: contract, so a change here is a change to what a built-in panel may say.
PLOT_PANEL_JSON = """{
  "panel_id": "core.plot.basic",
  "display_name": "Plot",
  "target_types": ["PlotArtifact"],
  "capability": "displaying",
  "entry": "index.html",
  "api_version": "1",
  "features": ["png", "jpeg", "svg", "pdf", "export"],
  "priority": 0,
  "supports_collection": false,
  "provider": "scistudio.panels.fallbacks:plot_panel"
}
"""


# ---------------------------------------------------------------------------
# FR-004 / SC-001 — exactly one API version constant
# ---------------------------------------------------------------------------


def _module_level_assignments(path: Path, name: str) -> int:
    """Count module-level ``name = ...`` assignments in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):  # pragma: no cover - defensive
        return 0
    count = 0
    for node in tree.body:
        targets = (
            node.targets if isinstance(node, ast.Assign) else ([node.target] if isinstance(node, ast.AnnAssign) else [])
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                count += 1
    return count


def test_exactly_one_panel_api_version_definition_in_the_tree() -> None:
    """SC-001/FR-004: one definition, and it is the core one (D-010)."""
    definitions = {
        path.relative_to(SRC_ROOT).as_posix(): count
        for path in SRC_ROOT.rglob("*.py")
        if (count := _module_level_assignments(path, "PANEL_API_VERSION"))
    }
    assert definitions == {"core/panels.py": 1}, (
        f"PANEL_API_VERSION must be defined once, in scistudio.core.panels (D-010); found: {definitions}"
    )


def test_every_module_that_names_the_version_shares_the_one_object() -> None:
    """A re-export, not a second literal that happens to agree today."""
    from scistudio.blocks.base import interactive
    from scistudio.panels import models

    assert models.PANEL_API_VERSION is PANEL_API_VERSION
    assert interactive.PANEL_API_VERSION is PANEL_API_VERSION


# ---------------------------------------------------------------------------
# FR-001 — the manifest lives in core and the block layer imports downward
# ---------------------------------------------------------------------------


def test_the_block_layer_imports_the_manifest_rather_than_defining_one() -> None:
    """FR-001: one manifest type, and the block layer's name for it is that one."""
    import scistudio.blocks.base as blocks_base_root
    from scistudio.blocks.base import interactive as blocks_base_interactive

    assert blocks_base_interactive.PanelManifest is PanelManifest
    assert blocks_base_root.PanelManifest is PanelManifest


def test_the_block_layer_does_not_import_the_panel_subsystem() -> None:
    """The block layer sits below the panel subsystem; the edge runs one way."""
    source = (SRC_ROOT / "blocks" / "base" / "interactive.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    offenders = [name for name in imported if name.startswith("scistudio.panels")]
    assert not offenders, f"blocks/base/interactive.py must not import the panel subsystem: {offenders}"
    assert "scistudio.core.panels" in imported


# ---------------------------------------------------------------------------
# FR-006 — the capability set is closed and asymmetric
# ---------------------------------------------------------------------------


def test_the_capability_set_has_exactly_two_members() -> None:
    assert [member.value for member in PanelCapability] == ["displaying", "producing"]


def test_a_producing_panel_is_also_mountable_for_display() -> None:
    """FR-006, and the reason the FR-048 filter is not an equality test."""
    assert PanelCapability.PRODUCING.satisfies(PanelCapability.DISPLAYING)
    assert PanelCapability.PRODUCING.satisfies(PanelCapability.PRODUCING)


def test_a_displaying_panel_does_not_satisfy_a_producing_request() -> None:
    assert PanelCapability.DISPLAYING.satisfies(PanelCapability.DISPLAYING)
    assert not PanelCapability.DISPLAYING.satisfies(PanelCapability.PRODUCING)


# ---------------------------------------------------------------------------
# FR-019 — the tier order
# ---------------------------------------------------------------------------


def test_the_tier_order_is_project_user_package_core() -> None:
    assert PANEL_TIER_ORDER == (PanelTier.PROJECT, PanelTier.USER, PanelTier.PACKAGE, PanelTier.CORE)
    assert PanelTier.PROJECT.shadow_rank < PanelTier.USER.shadow_rank
    assert PanelTier.USER.shadow_rank < PanelTier.PACKAGE.shadow_rank
    assert PanelTier.PACKAGE.shadow_rank < PanelTier.CORE.shadow_rank


# ---------------------------------------------------------------------------
# D-007 — the on-disk form
# ---------------------------------------------------------------------------


def test_the_agreed_builtin_declaration_is_accepted_verbatim() -> None:
    """The cross-agent contract: `W4-builtin`'s plot ``panel.json`` must load."""
    manifest = manifest_from_declaration(json.loads(PLOT_PANEL_JSON), Path("core.plot.basic"))

    assert manifest.panel_id == "core.plot.basic"
    assert manifest.display_name == "Plot"
    assert manifest.target_types == ("PlotArtifact",)
    assert manifest.capability is PanelCapability.DISPLAYING
    assert manifest.entry == "index.html"
    assert manifest.api_version == PANEL_API_VERSION
    assert manifest.features == ("png", "jpeg", "svg", "pdf", "export")
    assert manifest.priority == 0
    assert manifest.supports_collection is False
    assert manifest.provider == "scistudio.panels.fallbacks:plot_panel"


def test_the_optional_fields_take_the_documented_defaults() -> None:
    declaration = {
        "panel_id": "acme.thing",
        "display_name": "Thing",
        "target_types": ["Thing"],
        "capability": "producing",
        "entry": "main.html",
        "api_version": "1",
    }

    manifest = manifest_from_declaration(declaration, Path("acme.thing"))

    assert manifest.features == ()
    assert manifest.priority == 0
    assert manifest.supports_collection is False
    assert manifest.provider is None
    assert DEFAULT_PANEL_ENTRY == "index.html"


@pytest.mark.parametrize("missing", REQUIRED_DECLARATION_FIELDS)
def test_a_missing_required_field_is_refused_naming_the_directory_and_the_field(missing: str) -> None:
    """FR-003: the diagnostic names the panel directory and the missing field."""
    declaration = {
        "panel_id": "acme.thing",
        "display_name": "Thing",
        "target_types": ["Thing"],
        "capability": "displaying",
        "entry": "index.html",
        "api_version": "1",
    }
    del declaration[missing]
    directory = Path("/tmp/panels/acme.thing")

    with pytest.raises(MissingDeclarationFieldError) as caught:
        manifest_from_declaration(declaration, directory)

    assert caught.value.field == missing
    assert missing in caught.value.message
    assert str(directory) in caught.value.message


def test_an_empty_required_field_is_treated_as_missing() -> None:
    declaration = {
        "panel_id": "acme.thing",
        "display_name": "   ",
        "target_types": ["Thing"],
        "capability": "displaying",
        "entry": "index.html",
        "api_version": "1",
    }

    with pytest.raises(MissingDeclarationFieldError) as caught:
        manifest_from_declaration(declaration, Path("acme.thing"))

    assert caught.value.field == "display_name"


def test_a_capability_outside_the_closed_set_is_refused() -> None:
    declaration = {
        "panel_id": "acme.thing",
        "display_name": "Thing",
        "target_types": ["Thing"],
        "capability": "editing",
        "entry": "index.html",
        "api_version": "1",
    }

    with pytest.raises(InvalidDeclarationFieldError) as caught:
        manifest_from_declaration(declaration, Path("acme.thing"))

    assert caught.value.field == "capability"
    assert "displaying" in caught.value.message and "producing" in caught.value.message


def test_a_field_of_the_wrong_shape_is_refused_rather_than_coerced() -> None:
    declaration = {
        "panel_id": "acme.thing",
        "display_name": "Thing",
        "target_types": "Thing",
        "capability": "displaying",
        "entry": "index.html",
        "api_version": "1",
    }

    with pytest.raises(InvalidDeclarationFieldError) as caught:
        manifest_from_declaration(declaration, Path("acme.thing"))

    assert caught.value.field == "target_types"


def test_an_unknown_field_is_ignored_rather_than_refused() -> None:
    """A declaration from a later build still loads; SciStudio is not the only
    thing that writes these files."""
    declaration = {
        "panel_id": "acme.thing",
        "display_name": "Thing",
        "target_types": ["Thing"],
        "capability": "displaying",
        "entry": "index.html",
        "api_version": "1",
        "something_from_the_future": {"nested": True},
    }

    assert manifest_from_declaration(declaration, Path("acme.thing")).panel_id == "acme.thing"


def test_a_declaration_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "acme.thing"
    directory.mkdir()
    (directory / "panel.json").write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(UnreadableDeclarationError):
        read_panel_declaration(directory)


def test_a_directory_without_a_declaration_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "acme.thing"
    directory.mkdir()

    with pytest.raises(UnreadableDeclarationError) as caught:
        read_panel_declaration(directory)

    assert str(directory) in caught.value.message


def test_unparseable_json_is_refused_with_the_directory_named(tmp_path: Path) -> None:
    directory = tmp_path / "acme.thing"
    directory.mkdir()
    (directory / "panel.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(UnreadableDeclarationError) as caught:
        read_panel_declaration(directory)

    assert str(directory) in caught.value.message


def test_a_declaration_naming_an_absent_entry_document_is_refused(tmp_path: Path) -> None:
    """FR-002: a panel is a directory *and* a self-contained entry document."""
    directory = tmp_path / "acme.thing"
    directory.mkdir()
    (directory / "panel.json").write_text(
        json.dumps(
            {
                "panel_id": "acme.thing",
                "display_name": "Thing",
                "target_types": ["Thing"],
                "capability": "displaying",
                "entry": "index.html",
                "api_version": "1",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(InvalidDeclarationFieldError) as caught:
        read_panel_declaration(directory)

    assert caught.value.field == "entry"


def test_a_valid_directory_round_trips_through_the_declaration_form(tmp_path: Path) -> None:
    from tests.panels.conftest import write_panel

    directory = write_panel(tmp_path, "acme.thing", capability="producing", features=["sort"])

    manifest = read_panel_declaration(directory)
    rewritten = manifest_from_declaration(manifest.to_declaration_dict(), directory)

    assert rewritten == manifest


def test_every_declaration_error_is_a_panel_declaration_error() -> None:
    """One base class to catch, so discovery never has to enumerate them."""
    for error in (MissingDeclarationFieldError, InvalidDeclarationFieldError, UnreadableDeclarationError):
        assert issubclass(error, PanelDeclarationError)
