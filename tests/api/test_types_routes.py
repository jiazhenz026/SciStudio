"""The types API — listing and template (ADR-053 §7, FR-026 to FR-028).

``docs/specs/adr-053-personal-tool-library.md`` §2.7 and §2.9, issues #2023 and
#2024. Type data used to reach the frontend only as ``type_hierarchy`` riding
on the block *schema* response: no origin tier, no file path, no extensions,
and a ``ui_ring_color`` field nothing populated. It could support neither tier
grouping nor a promotion action, and it could not be refreshed without
refreshing the palette.

What is pinned here:

* The listing carries every field the Data types tab needs, per type, from one
  request (FR-026).
* It is independent of the block listing (FR-027), and ``type_hierarchy`` is
  left exactly as it was — including its dead ``ui_ring_color``, which FR-066
  deliberately does not revive rather than creating a second supply point for
  one fact.
* Load and save extensions are reported separately (FR-055) and a type with no
  capability reports empty lists rather than omitting the field (FR-056),
  because absence of IO support is information the popover states outright.
* Origin resolution goes through the shared resolver, so a type's tier and a
  block's tier cannot drift (FR-003, FR-005).
* The template endpoint mirrors the block template's response shape (FR-028)
  and shows the colour attributes as commented-out lines, which is how a type
  author finds out that declaring a colour is possible at all.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes.types import _type_origin
from scistudio.api.runtime import ApiRuntime
from scistudio.core.dropins import user_types_dir

PROBE_TYPE = '''\
from typing import ClassVar

from scistudio.core.types import DataObject


class {class_name}(DataObject):
    """{description}"""

    ui_color: ClassVar[str | None] = {ui_color}
'''


class _Spec:
    """The four spec fields the origin adapter reads, and nothing else."""

    def __init__(self, *, file_path: str = "", module_path: str = "", is_dropin: bool = False) -> None:
        self.file_path = file_path
        self.module_path = module_path
        self.is_dropin = is_dropin


def _write_type(directory: Path, stem: str, *, ui_color: str | None = None, description: str = "A probe type.") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{stem}.py"
    target.write_text(
        PROBE_TYPE.format(
            class_name=stem.title().replace("_", ""),
            description=description,
            ui_color=repr(ui_color) if ui_color is not None else "None",
        ),
        encoding="utf-8",
    )
    return target


def _types(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/types/")
    assert response.status_code == 200, response.text
    return {entry["name"]: entry for entry in response.json()["types"]}


# ---------------------------------------------------------------------------
# FR-026 — one request, every field the tab needs
# ---------------------------------------------------------------------------


def test_listing_reports_name_base_description_origin_and_file(client: TestClient) -> None:
    """A core type arrives with its identity, its tier, and its file."""
    entry = _types(client)["Array"]
    assert entry["base_type"] == "DataObject"
    assert entry["description"]
    assert entry["origin"] == "core"
    assert entry["file_path"].endswith("array.py")


def test_listing_reports_declared_colours_as_null_when_undeclared(client: TestClient) -> None:
    """Core types declare nothing, so both colour fields are null, not absent.

    Null is the signal that the frontend should apply the rest of the FR-051
    precedence. Omitting the field instead would make "declared nothing" and
    "this build is missing the feature" the same value on the wire.
    """
    entry = _types(client)["DataFrame"]
    assert entry["ui_color"] is None
    assert entry["ui_ring_color"] is None


def test_listing_is_sorted_by_name(client: TestClient) -> None:
    """Ordering is stable, so the tab is not reshuffled by an unrelated change."""
    names = [entry["name"] for entry in client.get("/api/types/").json()["types"]]
    assert names == sorted(names)


def test_listing_answers_with_and_without_the_trailing_slash(client: TestClient) -> None:
    """Both spellings reach the handler, so a caller cannot pick the wrong one."""
    assert client.get("/api/types/").status_code == 200
    assert client.get("/api/types").status_code == 200


# ---------------------------------------------------------------------------
# FR-054 / FR-055 / FR-056 — extensions, per direction, always present
# ---------------------------------------------------------------------------


def test_extensions_are_derived_from_the_format_capabilities(client: TestClient) -> None:
    """A type with IO support advertises the extensions it handles (FR-054)."""
    entry = _types(client)["DataFrame"]
    assert ".csv" in entry["load_extensions"]
    assert ".csv" in entry["save_extensions"]
    assert entry["load_extensions"] == sorted(entry["load_extensions"])


def test_load_and_save_are_reported_separately(client: TestClient) -> None:
    """The two directions are not collapsed, so a real asymmetry stays visible.

    ``Series`` is writable as JSON but is not registered as readable from it.
    Merging the directions would report it as round-trippable, which it is not.
    """
    entry = _types(client)["Series"]
    assert ".json" in entry["save_extensions"]
    assert ".json" not in entry["load_extensions"]


def test_a_type_with_no_capability_reports_empty_lists(client: TestClient) -> None:
    """``DataObject`` has no format capability and says so explicitly (FR-056)."""
    entry = _types(client)["DataObject"]
    assert entry["load_extensions"] == []
    assert entry["save_extensions"] == []


# ---------------------------------------------------------------------------
# FR-005 — the tier split, through the shared resolver
# ---------------------------------------------------------------------------


def test_user_and_project_types_report_their_own_tiers(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A type from each drop-in directory arrives with its own origin."""
    _write_type(opened_project / "types", "tier_project_probe")
    _write_type(user_types_dir(), "tier_user_probe")
    runtime.refresh_all_registries()

    entries = _types(client)
    assert entries["TierProjectProbe"]["origin"] == "project"
    assert entries["TierUserProbe"]["origin"] == "user"
    assert entries["Array"]["origin"] == "core"


def test_a_dropin_type_reports_the_file_it_came_from(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """``file_path`` points at the user's own file, which is what promotion copies."""
    written = _write_type(opened_project / "types", "path_probe")
    runtime.refresh_all_registries()

    assert Path(_types(client)["PathProbe"]["file_path"]) == written


def test_the_origin_adapter_delegates_the_whole_vocabulary() -> None:
    """Every FR-005 label comes out of the shared resolver, including the fallback.

    ``custom`` is the case worth pinning: a drop-in registers under a synthetic
    module name that is not an import path, so a resolver told only the module
    path would call it ``package``. The adapter passes ``is_dropin`` precisely
    so that cannot happen.
    """
    assert _type_origin(_Spec(module_path="scistudio.core.types.array"), None) == "core"
    assert _type_origin(_Spec(module_path="scistudio_blocks_imaging.types"), None) == "package"
    assert _type_origin(_Spec(module_path="_scistudio_type_dropin_x_1_2", is_dropin=True), None) == "custom"


def test_a_dropin_outside_both_tiers_falls_back_to_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A path under neither root degrades to ``custom`` rather than breaking (FR-002)."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    stray = _write_type(tmp_path / "elsewhere", "stray_probe")
    spec = _Spec(file_path=str(stray), module_path="_scistudio_type_dropin_stray_1_2", is_dropin=True)
    assert _type_origin(spec, tmp_path / "proj") == "custom"


def test_a_core_types_file_path_never_reads_as_a_tier(client: TestClient) -> None:
    """A core type has a real file, and it must not be mistaken for a drop-in.

    Every tier records ``file_path`` (FR-026), so the adapter has to decide the
    tier from ``is_dropin`` rather than from "does this spec have a path".
    """
    entry = _types(client)["Text"]
    assert entry["file_path"]
    assert entry["origin"] == "core"


# ---------------------------------------------------------------------------
# FR-049 / FR-050 — a declared colour reaches the endpoint
# ---------------------------------------------------------------------------


def test_a_declared_colour_reaches_the_listing(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A colour declared in a user's type file arrives at the single source."""
    _write_type(opened_project / "types", "painted_probe", ui_color="#0A7D55")
    runtime.refresh_all_registries()

    assert _types(client)["PaintedProbe"]["ui_color"] == "#0a7d55"


def test_a_broken_colour_does_not_break_the_listing(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A malformed value falls through to null and the type still lists (FR-052)."""
    _write_type(opened_project / "types", "broken_probe", ui_color="octarine")
    runtime.refresh_all_registries()

    entry = _types(client)["BrokenProbe"]
    assert entry["ui_color"] is None
    assert entry["origin"] == "project"


# ---------------------------------------------------------------------------
# FR-027 / FR-066 — independent of the block response, which is left alone
# ---------------------------------------------------------------------------


def test_the_listing_is_served_by_its_own_router() -> None:
    """The types routes hang off ``/api/types``, not off the block router.

    FR-027 is a claim about coupling, so it is asserted on the routing table:
    a types path nested under ``/api/blocks`` would contradict the requirement
    in the URL even if the handlers never touched each other.
    """
    from scistudio.api.routes.types import router

    paths = [str(getattr(route, "path", "")) for route in router.routes]
    assert all(path.startswith("/api/types") for path in paths)
    assert "/api/types/template" in paths


def test_the_data_types_tab_needs_no_block_request(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A newly written type is listed without the palette being fetched first."""
    _write_type(opened_project / "types", "independent_probe")
    runtime.refresh_all_registries()

    assert "IndependentProbe" in _types(client)


def test_type_hierarchy_still_carries_its_dead_colour_field(client: TestClient) -> None:
    """``TypeHierarchyEntry.ui_ring_color`` stays unpopulated (FR-066).

    The cheap alternative to a types endpoint was to start populating this
    field. It was rejected: it would make type colour arrive from two places
    that have to be kept in step by hand. ``type_hierarchy`` keeps serving
    hierarchy, so this assertion is what stops the rejected design from being
    reintroduced by someone who finds the field and assumes it was an oversight.
    """
    response = client.get("/api/blocks/load_data/schema")
    assert response.status_code == 200, response.text
    hierarchy = response.json()["type_hierarchy"]
    assert hierarchy, "the block schema must still carry type_hierarchy"
    assert all(entry["ui_ring_color"] is None for entry in hierarchy)


# ---------------------------------------------------------------------------
# FR-028 — the type template
# ---------------------------------------------------------------------------


def _template(client: TestClient, kind: str = "basic") -> dict[str, Any]:
    response = client.get(f"/api/types/template?kind={kind}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_template_returns_the_block_template_response_shape(client: TestClient) -> None:
    """Same three fields as ``GET /api/blocks/template`` so the flows can share."""
    body = _template(client)
    assert set(body) == {"kind", "content", "suggested_filename"}
    assert body["kind"] == "basic"
    assert body["suggested_filename"].endswith(".py")


def test_template_content_is_a_valid_data_type_module(client: TestClient) -> None:
    """The template parses and subclasses a real core type."""
    content = _template(client)["content"]
    ast.parse(content)
    assert "from scistudio.core.types import" in content
    assert "class MyDataType(" in content


def test_template_shows_the_colour_attributes_commented_out(client: TestClient) -> None:
    """The colour hooks are visible but inert (FR-028).

    Commented rather than set: a template that shipped a colour would give
    every new type the same one. Commented lines are how the author discovers
    the capability exists without being opted into it.
    """
    content = _template(client)["content"]
    assert "#   ui_color: ClassVar[str | None]" in content
    assert "#   ui_ring_color: ClassVar[str | None]" in content
    # Inert: uncommenting is the author's choice, so nothing may be assigned at
    # class level in the template itself.
    tree = ast.parse(content)
    assigned = {
        node.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert "ui_color" not in assigned
    assert "ui_ring_color" not in assigned


def test_template_default_kind_is_basic(client: TestClient) -> None:
    """Omitting ``kind`` defaults to ``basic``, matching the block endpoint."""
    response = client.get("/api/types/template")
    assert response.status_code == 200
    assert response.json()["kind"] == "basic"


def test_template_unknown_kind_400(client: TestClient) -> None:
    """An unknown kind is a client error, and the message names it."""
    response = client.get("/api/types/template?kind=frobnicator")
    assert response.status_code == 400
    assert "frobnicator" in response.json()["detail"]
