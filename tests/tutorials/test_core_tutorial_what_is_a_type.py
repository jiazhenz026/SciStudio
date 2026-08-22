"""Core tutorial 2 — the type-system level — held to its own claims.

``test_core_tutorials.py`` already applies the format-level conformance every
shipped tutorial gets. This file checks what only tutorial 2 promises
(#2081, scenarios doc 关卡 2):

* the beat order and each beat's judged condition survive edits;
* the three plot twists are real: the capability error the reader hits is the
  product's own dispatch message, quoted verbatim in the step text; the
  number-table beat rests on Image genuinely subclassing Array; and the
  segmentation's imperfection is recomputed from the shipped TIFF every run —
  7 labels at the fixed threshold (six cells and a nine-pixel speck), 73 with
  the adaptive method, exactly the numbers the step texts quote;
* the shipped TIFF is deterministic: the test regenerates it from the recorded
  recipe and requires pixel equality, so the data cannot drift from the
  numbers;
* the interactive block is a *real* interactive block — mixin, execution
  mode, panel manifest with a served module URL and a path-confined
  ``asset_root`` beside the block — and its panel is the shipped, hand-written
  ES module implementing the ADR-051 PanelModule contract;
* the previewer registers for ``Image`` and renders a genuine PNG, and it
  derives its tier from where it sits, so the same file works in the project
  and, after "Move to My Library", in the library's user-tier slot;
* the whole tutorial walks through the real runtime, beat by beat.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
import yaml

from scistudio.blocks.base import BlockConfig
from scistudio.core.types import Collection
from scistudio.tutorials.actions import iter_file_actions
from scistudio.tutorials.manifest import TutorialManifest, TutorialSourceKind, load_manifest

TUTORIAL_DIR = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials" / "core" / "what-is-a-type"
ASSETS = TUTORIAL_DIR / "assets"

# The recipe behind assets/data/cells.tif, in full. The image is committed as
# a binary, so provenance has to be executable: this recipe regenerates it and
# a test below requires pixel equality. Six gaussian cells, one nine-pixel
# debris speck, an illumination ramp, and seeded sensor noise.
_RNG_SEED = 20260821
_SHAPE = (120, 120)
_CELLS = (
    (24, 26, 5.5, 170.0),
    (28, 78, 6.5, 180.0),
    (60, 22, 5.0, 160.0),
    (66, 62, 7.0, 185.0),
    (94, 40, 5.0, 170.0),
    (90, 96, 6.0, 175.0),
)
_SPECK = (16, 103, 1.1, 140.0)

# The numbers the tutorial text and this file both stand on, recomputed from
# the shipped assets by the tests below.
_THRESHOLD_LABEL_AREAS = {1: 9, 2: 220, 3: 323, 4: 204, 5: 459, 6: 356, 7: 248}
_SPECK_LABEL = 1
_ADAPTIVE_LABEL_COUNT = 73


def _expected_micrograph() -> np.ndarray:
    rng = np.random.default_rng(_RNG_SEED)
    height, width = _SHAPE
    yy, xx = np.mgrid[0:height, 0:width]
    image = 10.0 + 34.0 * (yy / (height - 1)) + rng.normal(loc=0.0, scale=3.5, size=_SHAPE)
    for cy, cx, sigma, peak in (*_CELLS, _SPECK):
        image += peak * np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2.0 * sigma**2)))
    return np.clip(image, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def manifest() -> TutorialManifest:
    return load_manifest(TUTORIAL_DIR, source_kind=TutorialSourceKind.CORE)


@pytest.fixture(scope="module")
def assets(request: pytest.FixtureRequest) -> dict[str, ModuleType]:
    """The shipped code assets, imported the way the drop-in scans import them.

    ``image.py`` must land in ``sys.modules`` under its bare stem first,
    because the three blocks open with ``from image import Image`` — the exact
    import they perform in a project, where the types directory joins
    ``sys.path``. The fixture removes every name it bound.
    """
    bound: list[str] = []

    def load(name: str, filename: str) -> ModuleType:
        spec = importlib.util.spec_from_file_location(name, ASSETS / "code" / filename)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        bound.append(name)
        spec.loader.exec_module(module)
        return module

    modules = {"image": load("image", "image.py")}
    modules["loader"] = load("_scistudio_dropin_test_t2_loader", "load_tiff_image.py")
    modules["segment"] = load("_scistudio_dropin_test_t2_segment", "segment_cells.py")
    modules["review"] = load("_scistudio_dropin_test_t2_review", "review_labels.py")
    modules["preview"] = load("_scistudio_dropin_test_t2_preview", "image_preview.py")

    def cleanup() -> None:
        for name in bound:
            sys.modules.pop(name, None)

    request.addfinalizer(cleanup)
    return modules


def _shipped_image(assets: dict[str, ModuleType]) -> Any:
    return assets["loader"].LoadTiffImage().load_file(ASSETS / "data" / "cells.tif", {})


def _threshold_labels(assets: dict[str, ModuleType]) -> Any:
    block = assets["segment"].SegmentCellsBlock()
    return block.process_item(_shipped_image(assets), BlockConfig(params={}))


# ---------------------------------------------------------------------------
# The beat map
# ---------------------------------------------------------------------------


def test_the_beat_map_is_the_designed_one(manifest: TutorialManifest) -> None:
    """Beat -> step -> condition, as dispatched. A reorder or a swapped judge fails here."""
    expected = [
        ("a-task-arrives", None),
        ("create-the-image-type", {"file_exists"}),
        ("make-it-image", {"type_registered"}),
        ("add-load", {"node_exists"}),
        ("point-load-at-the-image", {"config_matches", "config_equals"}),
        ("run-into-the-wall", {"run_failed"}),
        ("meet-ioblock", {"run_succeeded"}),
        ("numbers-not-pictures", {"ui_event"}),
        ("a-previewer-for-image", {"previewer_registered", "ui_event"}),
        ("segment-the-cells", {"node_exists", "edge_exists"}),
        ("run-the-segmentation", {"run_succeeded", "ui_event"}),
        ("try-another-method", {"config_equals", "run_succeeded"}),
        ("and-back-again", {"config_equals", "run_succeeded"}),
        ("add-the-review-block", {"node_exists", "edge_exists"}),
        ("delete-the-speck", {"interaction_completed"}),
        ("add-save", {"node_exists", "edge_exists"}),
        ("choose-where-it-lands", {"config_matches"}),
        ("export-the-areas", {"run_succeeded", "file_exists"}),
        ("save-the-type", {"library_contains"}),
        ("save-the-block", {"library_contains"}),
        ("save-the-previewer", {"library_contains"}),
        ("what-a-type-is", None),
    ]
    actual = [(step.id, set(step.done_when.terms()) if step.done_when is not None else None) for step in manifest.steps]
    assert actual == expected


def test_every_run_judge_is_scoped_to_its_own_step(manifest: TutorialManifest) -> None:
    """The run terms carry ``since_step_entry`` (#2066), so an old run cannot satisfy them."""
    for step in manifest.steps:
        if step.done_when is None:
            continue

        def _walk(condition: Any) -> list[dict[str, Any]]:
            if condition.is_combinator:
                return [args for operand in condition.operands for args in _walk(operand)]
            return [dict(condition.args)] if condition.term in ("run_failed", "run_succeeded") else []

        for args in _walk(step.done_when):
            assert args.get("since_step_entry") is True, (
                f"step {step.id!r} judges a run term without since_step_entry; "
                "a run from three steps ago would satisfy it"
            )


def test_every_we_write_it_beat_is_a_trigger(manifest: TutorialManifest) -> None:
    """The four teaching writes are reader-triggered, and write what the step teaches."""
    expected = {
        "meet-ioblock": {"blocks/load_tiff_image.py"},
        "a-previewer-for-image": {"previewers/image_preview.py"},
        "segment-the-cells": {"blocks/segment_cells.py"},
        "add-the-review-block": {"blocks/review_labels.py", "blocks/review_labels_panel"},
    }
    triggered = {
        step.id: {action.destination for action in iter_file_actions(step.trigger.do)}
        for step in manifest.steps
        if step.trigger is not None
    }
    assert triggered == expected


def test_the_promotion_bridge_covers_type_block_and_previewer(manifest: TutorialManifest) -> None:
    """The ending judges all three library kinds — the bridge tutorial 3 stands on."""
    judged: list[tuple[str, str]] = []
    for step in manifest.steps:
        if step.done_when is None or "library_contains" not in step.done_when.terms():
            continue
        condition = step.done_when
        assert not condition.is_combinator
        judged.append((str(condition.args["kind"]), str(condition.args["name"])))
    assert judged == [("type", "Image"), ("block", "segment_cells"), ("previewer", "Image")]


def test_the_library_step_states_the_real_library_consequence(manifest: TutorialManifest) -> None:
    """FR-072: the save-to-library lesson names what the action does in a real project."""
    step = manifest.step_by_id("save-the-type")
    assert step is not None and step.say is not None
    assert "your own project" in step.say and "real library" in step.say


# ---------------------------------------------------------------------------
# The three plot twists are real
# ---------------------------------------------------------------------------


def test_the_capability_error_is_quoted_verbatim(manifest: TutorialManifest) -> None:
    """The wall step quotes the product's own dispatch error, not a paraphrase."""
    from scistudio.blocks.io import _unified_dispatch

    step = manifest.step_by_id("run-into-the-wall")
    assert step is not None and step.say is not None
    quoted = "no load capability is registered for type"
    assert quoted in step.say
    dispatch_source = Path(_unified_dispatch.__file__).read_text(encoding="utf-8")
    assert quoted in dispatch_source, "the dispatch error message moved; the step text no longer quotes the product"


def test_image_genuinely_subclasses_array(assets: dict[str, ModuleType]) -> None:
    """The number-table fallback beat rests on the type chain being real."""
    from scistudio.core.types import Array

    image_cls = assets["image"].Image
    assert issubclass(image_cls, Array)
    assert image_cls.required_axes == frozenset({"y", "x"})
    with pytest.raises(ValueError, match="y"):
        image_cls(axes=["a", "b"])


def test_the_type_asset_ships_the_colour_edit(manifest: TutorialManifest) -> None:
    """The one hand edit the reader makes must exist to be uncommented."""
    source = (ASSETS / "code" / "image.py").read_text(encoding="utf-8")
    assert "#   ui_color:" in source and "#   ui_ring_color:" in source
    step = manifest.step_by_id("make-it-image")
    assert step is not None and step.say is not None
    assert "Uncomment" in step.say


def test_the_shipped_tiff_matches_its_recorded_recipe() -> None:
    """The committed binary regenerates bit-for-bit, so the numbers cannot drift."""
    import tifffile

    shipped = np.asarray(tifffile.imread(ASSETS / "data" / "cells.tif"))
    expected = _expected_micrograph()
    assert shipped.dtype == np.uint8 and shipped.shape == _SHAPE
    np.testing.assert_array_equal(shipped, expected)


def test_the_loader_reads_the_tiff_as_an_image(assets: dict[str, ModuleType]) -> None:
    image = _shipped_image(assets)
    assert isinstance(image, assets["image"].Image)
    assert image.axes == ["y", "x"]
    pixels = image.to_memory()
    assert pixels.shape == _SHAPE and pixels.dtype == np.uint8


def test_the_loader_declares_exactly_the_missing_capability(assets: dict[str, ModuleType]) -> None:
    """The declaration is the lesson: (Image, tiff, .tif/.tiff), load direction."""
    capabilities = assets["loader"].LoadTiffImage.get_format_capabilities()
    assert len(capabilities) == 1
    capability = capabilities[0]
    assert capability.direction == "load"
    assert capability.data_type is assets["image"].Image
    assert capability.format_id == "tiff"
    assert set(capability.extensions) == {".tif", ".tiff"}


def test_the_loader_refuses_a_stack(tmp_path: Path, assets: dict[str, ModuleType]) -> None:
    import tifffile

    stack = tmp_path / "stack.tif"
    tifffile.imwrite(stack, np.zeros((3, 8, 8), dtype=np.uint8), photometric="minisblack")
    with pytest.raises(ValueError, match="2-D"):
        assets["loader"].LoadTiffImage().load_file(stack, {})


def test_the_threshold_run_finds_seven_objects_six_cells(assets: dict[str, ModuleType]) -> None:
    """7 labels; the speck is label 1, nine pixels, top-right — as the text says."""
    labels = np.asarray(_threshold_labels(assets).to_memory())
    found = {int(lbl): int((labels == lbl).sum()) for lbl in np.unique(labels) if lbl != 0}
    assert found == _THRESHOLD_LABEL_AREAS
    speck_ys, speck_xs = np.nonzero(labels == _SPECK_LABEL)
    assert (round(float(speck_ys.mean())), round(float(speck_xs.mean()))) == (_SPECK[0], _SPECK[1])


def test_the_adaptive_run_is_honestly_worse(assets: dict[str, ModuleType]) -> None:
    """73 objects — the number the step text quotes, recomputed."""
    block = assets["segment"].SegmentCellsBlock()
    labels = np.asarray(
        block.process_item(_shipped_image(assets), BlockConfig(params={"method": "adaptive"})).to_memory()
    )
    assert int(labels.max()) == _ADAPTIVE_LABEL_COUNT


def test_the_step_texts_quote_the_recomputed_numbers(manifest: TutorialManifest) -> None:
    """Editing the data or the text alone fails here; they must move together."""
    segmentation = manifest.step_by_id("run-the-segmentation")
    assert segmentation is not None and segmentation.say is not None
    assert "Seven objects" in segmentation.say and "six" in segmentation.say
    assert "nine-pixel" in segmentation.say

    adaptive = manifest.step_by_id("try-another-method")
    assert adaptive is not None and adaptive.say is not None
    assert "Seventy-three" in adaptive.say

    export = manifest.step_by_id("export-the-areas")
    assert export is not None and export.say is not None
    assert "Six rows" in export.say


# ---------------------------------------------------------------------------
# The interactive block and its hand-written panel
# ---------------------------------------------------------------------------


def test_the_review_block_is_a_real_interactive_block(assets: dict[str, ModuleType]) -> None:
    """Mixin + execution mode + panel manifest: the registry's own validation gate."""
    from scistudio.blocks.base import ExecutionMode, InteractiveMixin
    from scistudio.blocks.registry._spec import _spec_from_class

    cls = assets["review"].ReviewLabelsBlock
    assert issubclass(cls, InteractiveMixin)
    assert cls.execution_mode is ExecutionMode.INTERACTIVE

    spec = _spec_from_class(cls, source="custom")
    assert spec.type_name == "review_labels"
    assert spec.execution_mode == "interactive"
    assert spec.panel_manifest is not None
    assert spec.panel_manifest["panel_id"] == "tutorial.review_labels"
    assert spec.panel_asset_root is not None and spec.panel_asset_root.endswith("review_labels_panel")


def test_the_panel_manifest_names_the_served_module(assets: dict[str, ModuleType]) -> None:
    """module_url points at the panel-asset route for this panel id, .mjs file included."""
    panel = assets["review"].ReviewLabelsBlock.interactive_panel
    assert panel.module_url == f"/api/blocks/panels/{panel.panel_id}/panel.mjs"
    # The asset the URL names is the one the tutorial copies beside the block.
    assert (ASSETS / "panels" / "review_labels" / "panel.mjs").is_file()


def test_the_panel_module_implements_the_panel_contract() -> None:
    """A dependency-free ES module: default export, apiVersion "1", mount()."""
    source = (ASSETS / "panels" / "review_labels" / "panel.mjs").read_text(encoding="utf-8")
    assert "export default" in source
    assert 'const API_VERSION = "1"' in source
    assert "mount(container, host)" in source
    assert "host.confirm(" in source and "host.cancel(" in source
    assert "unmount()" in source
    for banned in ("import ", "require(", "fetch("):
        assert banned not in source, f"the panel must stay dependency-free and offline; found {banned!r}"


def test_the_prompt_payload_is_window_sized_and_complete(assets: dict[str, ModuleType]) -> None:
    labels = _threshold_labels(assets)
    review = assets["review"].ReviewLabelsBlock()
    prompt = review.prepare_prompt(
        {"labels": Collection(items=[labels], item_type=assets["image"].Image)}, BlockConfig(params={})
    )
    payload = prompt.panel_payload
    assert (payload["height"], payload["width"], payload["stride"]) == (120, 120, 1)
    assert [row["id"] for row in payload["labels"]] == list(_THRESHOLD_LABEL_AREAS)
    assert {row["id"]: row["area"] for row in payload["labels"]} == _THRESHOLD_LABEL_AREAS
    grid = payload["grid"]
    assert len(grid) == 120 and len(grid[0]) == 120
    assert {value for row in grid for value in row} == {0, *_THRESHOLD_LABEL_AREAS}


def test_the_decision_removes_the_speck_and_prices_the_cells(assets: dict[str, ModuleType]) -> None:
    """removed=[1] -> six labels survive, and the areas table prices exactly them."""
    labels = _threshold_labels(assets)
    review = assets["review"].ReviewLabelsBlock()
    out = review.run(
        {"labels": Collection(items=[labels], item_type=assets["image"].Image)},
        BlockConfig(params={"interactive_response": {"removed": [_SPECK_LABEL]}}),
    )
    cleaned = np.asarray(next(iter(out["labels"])).to_memory())
    assert int((cleaned == _SPECK_LABEL).sum()) == 0

    table = next(iter(out["areas"])).get_in_memory_data().to_pandas()
    assert list(table["label"]) == [lbl for lbl in _THRESHOLD_LABEL_AREAS if lbl != _SPECK_LABEL]
    assert {int(row["label"]): int(row["area_px"]) for _, row in table.iterrows()} == {
        lbl: area for lbl, area in _THRESHOLD_LABEL_AREAS.items() if lbl != _SPECK_LABEL
    }


def test_an_unreviewed_run_keeps_every_label(assets: dict[str, ModuleType]) -> None:
    """No decision means no removal — the block never deletes on its own."""
    labels = _threshold_labels(assets)
    review = assets["review"].ReviewLabelsBlock()
    out = review.run({"labels": Collection(items=[labels], item_type=assets["image"].Image)}, BlockConfig(params={}))
    table = next(iter(out["areas"])).get_in_memory_data().to_pandas()
    assert list(table["label"]) == list(_THRESHOLD_LABEL_AREAS)


# ---------------------------------------------------------------------------
# The previewer
# ---------------------------------------------------------------------------


class _StubPlane:
    def __init__(self, matrix: list[list[float]]) -> None:
        self.matrix = matrix
        self.shape = [len(matrix), len(matrix[0])]
        self.dtype = "uint8"


class _StubRequest:
    def __init__(self, matrix: list[list[float]] | None) -> None:
        self.spec = type("Spec", (), {"previewer_id": "project.image.view"})()
        self.target = None
        self.storage = object() if matrix is not None else None
        self.query: dict[str, Any] = {}
        plane = _StubPlane(matrix) if matrix is not None else None
        self.data_access = type("Access", (), {"array_plane": lambda _self, _ref, **_kw: plane})()


def test_the_previewer_claims_image_and_renders_a_real_png(assets: dict[str, ModuleType]) -> None:
    import base64

    from scistudio.previewers.models import EnvelopeKind

    specs = assets["preview"].get_previewers()
    assert len(specs) == 1 and specs[0].target_type == "Image"
    assert specs[0].backend_provider is assets["preview"].render_image

    image = _shipped_image(assets)
    envelope = assets["preview"].render_image(_StubRequest(image.to_memory().tolist()))
    assert envelope.kind is EnvelopeKind.PLOT
    encoded = envelope.payload["src"]
    assert encoded.startswith("data:image/png;base64,")
    png = base64.b64decode(encoded.split(",", 1)[1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_previewer_reports_failure_as_an_envelope(assets: dict[str, ModuleType]) -> None:
    from scistudio.previewers.models import EnvelopeKind

    envelope = assets["preview"].render_image(_StubRequest(None))
    assert envelope.kind is EnvelopeKind.ERROR
    assert envelope.error is not None


def test_the_previewer_derives_its_tier_from_where_it_sits(tmp_path: Path) -> None:
    """The same bytes answer PROJECT beside a project.yaml and USER in a library.

    "Move to My Library" relocates the file verbatim, and the drop-in scans
    refuse a spec whose declared tier disagrees with the directory being
    scanned — so a previewer that hard-coded either tier would break on one
    side of the move. Deriving the tier from the location is what makes the
    promotion the tutorial teaches actually work.
    """
    from scistudio.previewers.models import OwnerKind

    source = (ASSETS / "code" / "image_preview.py").read_text(encoding="utf-8")

    def spec_at(root: Path, marker: bool) -> Any:
        (root / "previewers").mkdir(parents=True)
        if marker:
            (root / "project.yaml").write_text("name: p\n", encoding="utf-8")
        target = root / "previewers" / "image_preview.py"
        target.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"_t2_tier_{marker}", target)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.get_previewers()[0]

    assert spec_at(tmp_path / "project", marker=True).owner_kind is OwnerKind.PROJECT
    assert spec_at(tmp_path / "library", marker=False).owner_kind is OwnerKind.USER


# ---------------------------------------------------------------------------
# The whole session, walked through the real runtime
# ---------------------------------------------------------------------------


def test_the_whole_tutorial_walks_through_the_real_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every beat of the real manifest, driven end to end (#2081).

    The runtime, session store, and progress store are the real ones; the
    product-state port is stood in exactly as the API layer stands it in. The
    walk asserts what the level exists for: the wall is met before the loader
    exists, the number table is met before the previewer exists, the judged
    conditions demand the reader's own clicks and runs, and the three
    promotions land before the tutorial completes — without firing the
    work-import milestone, which belongs to tutorial 4.
    """
    import re
    import shutil
    from dataclasses import dataclass
    from datetime import UTC, datetime, timedelta

    from scistudio.tutorials import discovery
    from scistudio.tutorials.conditions import ExternalEventNames, RunSummary
    from scistudio.tutorials.discovery import DiscoveryEnvironment
    from scistudio.tutorials.progress import ProgressStore
    from scistudio.tutorials.projects import TutorialKey, TutorialProjectPlan
    from scistudio.tutorials.session import SessionStatus, SessionStore, TutorialRuntime
    from scistudio.workflow.schema import WorkflowFileModel

    from .conftest import StubProductState

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: TUTORIAL_DIR.parent)

    @dataclass
    class _ProjectBackedState(StubProductState):
        """Reads the workflow off the project file, the way the product does."""

        def workflow(self) -> Any:
            self.reads.append("workflow")
            if self.project_dir is None:
                return None
            path = Path(self.project_dir) / "workflows" / "main.yaml"
            if not path.is_file():
                return None
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return WorkflowFileModel.model_validate(data).workflow.to_definition()

    class _Provisioner:
        def create(self, plan: TutorialProjectPlan) -> Path:
            plan.path.mkdir(parents=True, exist_ok=True)
            (plan.path / "project.yaml").write_text(f"name: {plan.name}\n", encoding="utf-8")
            return plan.path

        def delete(self, key: TutorialKey, path: Path) -> None:
            if path.is_dir():
                shutil.rmtree(path)

    product = _ProjectBackedState()

    def _settle(written: Any) -> None:
        """The API layer's registry re-scan, reduced to what the conditions read."""
        blocks = set(product.block_types)
        types = set(product.data_types)
        previewers = set(product.previewer_types)
        for path in written:
            path = Path(path)
            if path.suffix != ".py":
                continue
            if path.parent.name == "blocks":
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
                    for node in cls.body:
                        if (
                            isinstance(node, ast.AnnAssign)
                            and isinstance(node.target, ast.Name)
                            and node.target.id == "type_name"
                            and isinstance(node.value, ast.Constant)
                        ):
                            blocks.add(str(node.value.value))
            elif path.parent.name == "types":
                tree = ast.parse(path.read_text(encoding="utf-8"))
                types.update(node.name for node in tree.body if isinstance(node, ast.ClassDef))
            elif path.parent.name == "previewers":
                match = re.search(r'target_type="([^"]+)"', path.read_text(encoding="utf-8"))
                if match:
                    previewers.add(match.group(1))
        product.block_types = frozenset(blocks)
        product.data_types = frozenset(types)
        product.previewer_types = frozenset(previewers)

    def _record_event(name: str, target: str | None) -> None:
        product.events = product.events | {name}
        if target is not None:
            product.targeted_events = product.targeted_events | {(name, target)}

    def _forget_events() -> None:
        product.events = frozenset()
        product.targeted_events = frozenset()

    def _no_replay(surface: str) -> Any:
        raise AssertionError(f"tutorial 2 declares no replay, yet one opened on {surface!r}")

    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        project_dir=lambda: product.project_dir,
        provisioner=_Provisioner(),
        environment=DiscoveryEnvironment(scistudio_version="0.3.1", git_available=True),
        progress=ProgressStore(fake_home / ".scistudio"),
        sessions=SessionStore(fake_home / ".scistudio"),
        open_replay=_no_replay,
        record_ui_event=_record_event,
        forget_ui_events=_forget_events,
        files_written=_settle,
    )

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[tuple[str, str]] = []

    def _write_workflow() -> None:
        data = {
            "workflow": {
                "id": "main",
                "version": "1.0.0",
                "description": "What is a type — built step by step by the walk.",
                "nodes": [
                    {"id": node_id, "block_type": body["block_type"], "config": {"params": body["params"]}}
                    for node_id, body in nodes.items()
                ],
                "edges": [{"source": source, "target": target} for source, target in edges],
            }
        }
        assert product.project_dir is not None
        path = Path(product.project_dir) / "workflows" / "main.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def _run(succeeded: bool) -> None:
        started = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
        record = RunSummary(
            run_id=f"r{len(product.runs) + 1}",
            workflow_id="main",
            succeeded=succeeded,
            started_at=started,
        )
        product.runs = (record, *product.runs)

    def _live_step(view: Any) -> Any:
        assert view is not None and view.step is not None
        return view.step

    def _advance(expect: str) -> Any:
        moved = runtime.continue_active()
        assert moved.step is not None and moved.step.id == expect, (
            f"expected {expect!r}, on {moved.step.id if moved.step else None!r}"
        )
        return moved

    view = runtime.start(TutorialKey.core("what-is-a-type"))
    assert view.step is not None and view.step.id == "a-task-arrives"
    project = Path(view.project_path or "")
    product.project_dir = project
    assert (project / "data" / "raw" / "cells.tif").is_file(), "the bootstrap landed the micrograph"

    _advance("create-the-image-type")
    assert _live_step(runtime.active_session()).satisfied is False
    # The New data type dialog writes the product template and opens it.
    types_dir = project / "types"
    types_dir.mkdir(parents=True, exist_ok=True)
    (types_dir / "image.py").write_text("class MyDataType:\n    pass\n", encoding="utf-8")
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("make-it-image")
    # The entry write replaced the template and the settle registered Image.
    assert _live_step(runtime.active_session()).satisfied is True
    written = (types_dir / "image.py").read_text(encoding="utf-8")
    assert "class Image(Array):" in written
    assert "#   ui_color:" in written, "the colour lines ship commented, for the reader to uncomment"

    _advance("add-load")
    nodes["load-1"] = {"block_type": "load_data", "params": {}}
    _write_workflow()
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("point-load-at-the-image")
    assert _live_step(runtime.active_session()).satisfied is False
    nodes["load-1"]["params"] = {"path": "data/raw/cells.tif", "core_type": "Image"}
    _write_workflow()
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("run-into-the-wall")
    assert _live_step(runtime.active_session()).satisfied is False, "no run has started since entry"
    _run(succeeded=False)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("meet-ioblock")
    view = runtime.trigger_active()
    assert (project / "blocks" / "load_tiff_image.py").is_file()
    assert "load_tiff_image" in product.block_types, "the settle registered the loader before the press reported done"
    assert _live_step(view).satisfied is False, "the loader alone is not the lesson; the reader must run"
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("numbers-not-pictures")
    assert _live_step(runtime.active_session()).satisfied is False
    view = runtime.report_ui_event("node_selected", "load_data")
    assert _live_step(view).satisfied is True

    _advance("a-previewer-for-image")
    view = runtime.trigger_active()
    assert (project / "previewers" / "image_preview.py").is_file()
    assert "Image" in product.previewer_types, "the previewers/ settle registered the previewer live (#2086)"
    assert _live_step(view).satisfied is False, "the write is not the look; the reader must click the node again"
    view = runtime.report_ui_event("node_selected", "load_data")
    assert _live_step(view).satisfied is True

    _advance("segment-the-cells")
    view = runtime.trigger_active()
    assert (project / "blocks" / "segment_cells.py").is_file()
    assert _live_step(view).satisfied is False, "the block exists; the reader still wires it"
    nodes["segment-1"] = {"block_type": "segment_cells", "params": {}}
    edges.append(("load-1:data", "segment-1:image"))
    _write_workflow()
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("run-the-segmentation")
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is False, "the run alone is not the look"
    view = runtime.report_ui_event("node_selected", "segment_cells")
    assert _live_step(view).satisfied is True

    _advance("try-another-method")
    assert _live_step(runtime.active_session()).satisfied is False
    nodes["segment-1"]["params"] = {"method": "adaptive"}
    _write_workflow()
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("and-back-again")
    nodes["segment-1"]["params"] = {"method": "threshold"}
    _write_workflow()
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("add-the-review-block")
    view = runtime.trigger_active()
    assert (project / "blocks" / "review_labels.py").is_file()
    assert (project / "blocks" / "review_labels_panel" / "panel.mjs").is_file(), "the panel travelled beside the block"
    assert _live_step(view).satisfied is False
    nodes["review-1"] = {"block_type": "review_labels", "params": {}}
    edges.append(("segment-1:labels", "review-1:labels"))
    _write_workflow()
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("delete-the-speck")
    assert _live_step(runtime.active_session()).satisfied is False
    product.interactions = frozenset({"review-1"})
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("add-save")
    nodes["save-1"] = {"block_type": "save_data", "params": {}}
    edges.append(("review-1:areas", "save-1:data"))
    _write_workflow()
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("choose-where-it-lands")
    assert _live_step(runtime.active_session()).satisfied is False
    nodes["save-1"]["params"] = {"path": "data/processed", "filename": "cell_areas.csv"}
    _write_workflow()
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("export-the-areas")
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is False, "the run succeeded but the table has not landed"
    processed = project / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "cell_areas.csv").write_text("label,area_px\n", encoding="utf-8")
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("save-the-type")
    assert _live_step(runtime.active_session()).satisfied is False
    product.library = product.library | {("type", "Image")}
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("save-the-block")
    product.library = product.library | {("block", "segment_cells")}
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("save-the-previewer")
    product.library = product.library | {("previewer", "Image")}
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("what-a-type-is")
    finished = runtime.continue_active()
    assert finished.status is SessionStatus.COMPLETE

    # Tutorial 2 is a level, not the milestone: completing it must not offer
    # the work import (FR-079 names tutorial 4).
    assert runtime.progress_store.work_import_offer_pending() is False
