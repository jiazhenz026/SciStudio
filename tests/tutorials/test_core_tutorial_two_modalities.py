"""Core tutorial 3 — the multimodal, joint-analysis, git-branch level.

``test_core_tutorials.py`` already applies the format-level conformance every
shipped tutorial gets. This file checks what only tutorial 3 promises (#2082,
scenarios doc 关卡 3):

* the beat order and each beat's judged condition survive edits;
* the shipped data is deterministic — the section stack and both workbooks are
  regenerated from the recipe recorded below and required to match, so the
  numbers the steps quote cannot drift away from the files;
* the reuse is real: the ``Image`` type, the ``segment_cells`` block, and the
  ``Image`` previewer register into *this* tutorial's project out of a
  tutorial-scoped library seeded the way tutorial 2's last three steps leave
  it, previewer tier included (#2125);
* the pairing hazard is genuine — the stack's page order and the workbook's
  sheet order really do disagree, and every index pair is wrong;
* the science is recomputed, not asserted: nine regions on every section, and
  the four normalisation/batch combinations produce exactly the cluster splits
  the step texts quote — including the two that go wrong, in opposite ways;
* the k-means is deterministic and order-independent;
* the whole tutorial walks through the real runtime, beat by beat, git terms
  and library reuse included.
"""

from __future__ import annotations

import functools
import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.tutorials.actions import iter_file_actions
from scistudio.tutorials.manifest import TutorialManifest, TutorialSourceKind, load_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
TUTORIAL_DIR = REPO_ROOT / "src" / "scistudio" / "tutorials" / "core" / "two-modalities-one-answer"
TUTORIAL_2_CODE = REPO_ROOT / "src" / "scistudio" / "tutorials" / "core" / "what-is-a-type" / "assets" / "code"
ASSETS = TUTORIAL_DIR / "assets"

# ---------------------------------------------------------------------------
# The recipe behind assets/data/, in full.
#
# The three files are committed as binaries, so their provenance has to be
# executable: this recipe regenerates them and the tests below require
# equality. Nine tissue domains per section on independent layouts, three
# carrying each of three expression programmes; a shallow first sequencing run
# and a deeper second one whose two housekeeping genes soak up a wildly
# variable share of every position's library.
# ---------------------------------------------------------------------------
SEED = 20260822
SHAPE = (96, 96)
SIGMA = 5.0
PEAK = 130.0
BACKGROUND = 22.0
RAMP = 18.0
NOISE = 2.0

DOMAINS_PER_SECTION = 9
MIN_SEPARATION = 22.0
MARGIN = 12

# The scanner recorded the slides in the order they were loaded; the
# sequencing core sorted its sheets by section label. Every index pair is
# wrong, which is the whole reason the Pair Editor is in this level.
ACQUISITION_ORDER = ("S05", "S09", "S01")
SHEET_ORDER = ("S01", "S05", "S09")

POSITION_STEP = 4
POSITION_START = 2

GENES = ("hk_A", "hk_B", *[f"mk_{index:02d}" for index in range(1, 11)])
PROGRAM_MARKERS = {
    0: ("mk_01", "mk_02", "mk_03"),
    1: ("mk_04", "mk_05", "mk_06"),
    2: ("mk_07", "mk_08", "mk_09"),
}
PROGRAMS = {
    "S01": (0, 1, 2, 0, 1, 2, 0, 1, 2),
    "S05": (1, 0, 2, 2, 1, 0, 0, 2, 1),
    "S09": (2, 2, 0, 1, 0, 1, 2, 0, 1),
}

RUN1_DEPTH = 0.25
RUN2_DEPTH = 9.0
RUN2_CARRY = 1.8
BASE_HK = (12.0, 9.0)
BASE_MARKER = 5.0
BASE_OTHER = 1.0
BASE_GRADIENT = 2.0

# The numbers the step texts and this file both stand on, recomputed below.
REGIONS_PER_SECTION = 9
TOTAL_REGIONS = 27
# (run, method) -> the cluster sizes the reader sees, largest-signal cluster first.
EXPECTED_CLUSTER_SIZES = {
    (1, "total_count"): [9, 9, 9],
    (1, "median_ratio"): [7, 18, 2],
    (2, "total_count"): [14, 8, 5],
    (2, "median_ratio"): [9, 9, 9],
}


def _section_seed(section: str, salt: int = 0) -> int:
    return SEED + salt + sum(ord(char) * (index + 1) for index, char in enumerate(section))


@functools.cache
def _domain_centres(section: str) -> tuple[tuple[int, int], ...]:
    rng = np.random.default_rng(_section_seed(section))
    low, high = MARGIN, SHAPE[0] - MARGIN
    centres: list[tuple[int, int]] = []
    attempts = 0
    while len(centres) < DOMAINS_PER_SECTION:
        attempts += 1
        if attempts > 400:  # a corner the sampler cannot finish from; start over
            centres, attempts = [], 0
        cy = int(rng.integers(low, high))
        cx = int(rng.integers(low, high))
        if all((cy - y) ** 2 + (cx - x) ** 2 >= MIN_SEPARATION**2 for y, x in centres):
            centres.append((cy, cx))
    return tuple(centres)


def _section_image(section: str) -> np.ndarray:
    rng = np.random.default_rng(_section_seed(section, salt=7919))
    height, width = SHAPE
    yy, xx = np.mgrid[0:height, 0:width]
    pixels = BACKGROUND + RAMP * (yy / (height - 1)) + rng.normal(0.0, NOISE, SHAPE)
    for cy, cx in _domain_centres(section):
        pixels += PEAK * np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2.0 * SIGMA**2)))
    return np.clip(pixels, 0, 255).astype(np.uint8)


def _positions() -> np.ndarray:
    axis = np.arange(POSITION_START, SHAPE[0], POSITION_STEP)
    yy, xx = np.meshgrid(axis, axis, indexing="ij")
    return np.stack([yy.ravel(), xx.ravel()], axis=1)


def _programme_at(section: str, y: int, x: int) -> int | None:
    for index, (cy, cx) in enumerate(_domain_centres(section)):
        if (y - cy) ** 2 + (x - cx) ** 2 <= (1.6 * SIGMA) ** 2:
            return PROGRAMS[section][index]
    return None


def _counts_for(section: str, run: int) -> pd.DataFrame:
    rng = np.random.default_rng(_section_seed(section, salt=101 * run))
    coords = _positions()
    rows = []
    for y, x in coords:
        programme = _programme_at(section, int(y), int(x))
        base = np.full(len(GENES), BASE_OTHER)
        base[0], base[1] = BASE_HK
        if programme is not None:
            for marker in PROGRAM_MARKERS[programme]:
                base[GENES.index(marker)] = BASE_MARKER
            base[GENES.index("mk_10")] = BASE_GRADIENT
        if run == 1:
            lam = base * float(rng.lognormal(0.0, 0.35)) * RUN1_DEPTH
        else:
            carry = float(rng.lognormal(0.0, RUN2_CARRY))
            lam = base * float(rng.lognormal(0.0, 0.25)) * RUN2_DEPTH
            lam[0] *= carry * 14.0
            lam[1] *= carry * 11.0
        rows.append(rng.poisson(lam))
    frame = pd.DataFrame(np.stack(rows), columns=list(GENES))
    frame.insert(0, "x", coords[:, 1])
    frame.insert(0, "y", coords[:, 0])
    frame.insert(0, "section", section)
    frame.insert(0, "position_id", [f"{section}_P{index:03d}" for index in range(len(coords))])
    return frame


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def manifest() -> TutorialManifest:
    return load_manifest(TUTORIAL_DIR, source_kind=TutorialSourceKind.CORE)


@pytest.fixture(scope="module")
def assets(request: pytest.FixtureRequest) -> dict[str, ModuleType]:
    """The shipped code assets, imported the way the drop-in scans import them.

    ``image.py`` — tutorial 2's type, which this level consumes from the
    library — must land in ``sys.modules`` under its bare stem first, because
    every block here opens with ``from image import Image``: the exact import
    they perform in a project, where the types directory joins ``sys.path``.
    """
    bound: list[str] = []

    def load(name: str, path: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        bound.append(name)
        spec.loader.exec_module(module)
        return module

    modules = {"image": load("image", TUTORIAL_2_CODE / "image.py")}
    modules["segment"] = load("_scistudio_t3_segment", TUTORIAL_2_CODE / "segment_cells.py")
    modules["stack"] = load("_scistudio_t3_stack", ASSETS / "code" / "load_section_stack.py")
    modules["normalize"] = load("_scistudio_t3_normalize", ASSETS / "code" / "normalize_expression.py")
    modules["joint"] = load("_scistudio_t3_joint", ASSETS / "code" / "joint_region_profiles.py")

    request.addfinalizer(lambda: [sys.modules.pop(name, None) for name in bound])
    return modules


@pytest.fixture(scope="module")
def label_maps(assets: dict[str, ModuleType]) -> dict[str, np.ndarray]:
    """The segmentation of every shipped page, by tutorial 2's own block."""
    image_cls = assets["image"].Image
    block = assets["segment"].SegmentCellsBlock()
    pages = assets["stack"].read_section_stack(ASSETS / "data" / "sections.tif")
    maps: dict[str, np.ndarray] = {}
    for label, pixels in pages:
        labels = block.process_item(image_cls(axes=["y", "x"], data=pixels), BlockConfig(params={}))
        maps[label] = np.asarray(labels.to_memory())
    return maps


@pytest.fixture(scope="module")
def analyses(
    assets: dict[str, ModuleType],
    label_maps: dict[str, np.ndarray],
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[tuple[int, str], pd.DataFrame]:
    """The joint analysis for every (run, method), correctly paired.

    Computed once: four normalisations of three sections, each through the
    joint block. Every numeric claim in this file reads out of here.
    """
    store = tmp_path_factory.mktemp("t3-analyses")
    results: dict[tuple[int, str], pd.DataFrame] = {}
    for run in (1, 2):
        for method in ("total_count", "median_ratio"):
            results[(run, method)] = _analyse(
                assets, label_maps, store, run=run, method=method, expression_order=ACQUISITION_ORDER
            )
    return results


def _persist(obj: Any, store: Path, name: str) -> Any:
    """Give a freshly built DataObject somewhere to live.

    In a real run the engine flushes each block's output to project storage.
    These tests call the blocks directly, so they do the flush themselves.
    """
    obj.save(store / name)
    return obj


def _analyse(
    assets: dict[str, ModuleType],
    label_maps: dict[str, np.ndarray],
    store: Path,
    *,
    run: int,
    method: str,
    expression_order: tuple[str, ...],
) -> pd.DataFrame:
    """Normalise one run and push it through the joint block against the maps."""
    import pyarrow as pa

    from scistudio.core.types import DataFrame
    from scistudio.core.types.collection import Collection

    image_cls = assets["image"].Image
    normalizer = assets["normalize"].NormalizeExpressionBlock()
    tag = f"{run}-{method}-{'-'.join(expression_order)}"

    normalised: dict[str, Any] = {}
    for section in SHEET_ORDER:
        raw = _persist(
            DataFrame(data=pa.Table.from_pandas(_workbook_sheet(run, section), preserve_index=False)),
            store,
            f"raw-{tag}-{section}",
        )
        normalised[section] = _persist(
            normalizer.process_item(raw, BlockConfig(params={"method": method})),
            store,
            f"norm-{tag}-{section}",
        )

    outputs = (
        assets["joint"]
        .JointRegionProfilesBlock()
        .run(
            {
                "labels": Collection([image_cls(axes=["y", "x"], data=label_maps[s]) for s in ACQUISITION_ORDER]),
                "expression": Collection([normalised[section] for section in expression_order]),
            },
            BlockConfig(params={}),
        )
    )
    table = _persist(next(iter(outputs["regions"])), store, f"regions-{tag}")
    return table.to_memory().to_pandas()


@functools.cache
def _workbook(run: int) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = pd.read_excel(ASSETS / "data" / f"run{run}_counts.xlsx", sheet_name=None)
    return sheets


def _workbook_sheet(run: int, section: str) -> pd.DataFrame:
    return _workbook(run)[section]


def _cluster_sizes(table: pd.DataFrame) -> list[int]:
    return [int((table["cluster"] == cluster).sum()) for cluster in sorted(table["cluster"].dropna().unique())]


def _say(manifest: TutorialManifest, step_id: str) -> str:
    say = next(step.say for step in manifest.steps if step.id == step_id)
    assert say is not None, f"step {step_id!r} has no text to check"
    return say


# ---------------------------------------------------------------------------
# The beat map
# ---------------------------------------------------------------------------


def test_the_beat_map_is_the_designed_one(manifest: TutorialManifest) -> None:
    """Beat -> step -> condition, as dispatched. A reorder or a swapped judge fails here."""
    expected = [
        ("two-instruments-one-block-of-tissue", None),
        ("your-library-came-with-you", {"type_registered"}),
        ("load-the-slides", {"node_exists", "config_matches", "config_equals"}),
        ("see-the-sections", {"run_succeeded", "ui_event"}),
        ("load-the-counts", {"config_matches", "config_equals"}),
        ("pair-the-two-streams", {"node_exists", "edge_exists"}),
        ("they-do-not-line-up", {"interaction_completed"}),
        ("segment-the-regions", {"node_exists", "edge_exists"}),
        ("read-the-source", {"ui_event"}),
        ("normalise-the-counts", {"node_exists", "edge_exists"}),
        ("the-joint-block", {"node_exists", "edge_exists"}),
        ("run-the-joint-analysis", {"run_succeeded", "ui_event"}),
        ("bind-a-plot", {"plot_exists"}),
        ("draw-it", {"plot_rendered"}),
        ("a-second-run-arrives", {"git_branch_exists", "git_current_branch"}),
        ("point-it-at-the-second-run", {"config_matches", "run_succeeded"}),
        ("a-normalisation-for-this-batch", {"config_equals", "run_succeeded"}),
        ("switch-back", {"git_current_branch"}),
        ("git-stores-the-recipe", {"run_succeeded"}),
        ("two-variants-alive", None),
    ]
    actual = [(step.id, step.done_when.terms() if step.done_when else None) for step in manifest.steps]
    assert actual == expected


def test_every_run_judge_is_scoped_to_its_own_step(manifest: TutorialManifest) -> None:
    """The reader must run *here*, not be credited with a run from four beats ago.

    Six steps in this level say "press Run", several of them in a row with the
    same workflow. Without ``since_step_entry`` the second one is satisfied by
    the first one's record before the reader has done anything.
    """

    def walk(condition: Any, step_id: str) -> None:
        if condition.is_combinator:
            for operand in condition.operands:
                walk(operand, step_id)
            return
        if condition.term in ("run_succeeded", "run_failed"):
            assert condition.args.get("since_step_entry") is True, (
                f"step {step_id!r} judges {condition.term} without since_step_entry"
            )

    for step in manifest.steps:
        if step.done_when is not None:
            walk(step.done_when, step.id)


def test_the_two_blocks_this_level_writes_are_triggers(manifest: TutorialManifest) -> None:
    """ "Press the button and we will write it" has to be a button, not an entry action.

    The plot's ``render.py`` is deliberately excluded: tutorials 1 and 6 write
    it on entry because the reader has already created the plot and the step
    is about pressing Run on the card, not about producing a file.
    """
    triggered = {
        action.destination for step in manifest.steps if step.trigger for action in iter_file_actions(step.trigger.do)
    }
    assert triggered == {"blocks/normalize_expression.py", "blocks/joint_region_profiles.py"}


def test_the_instrument_reader_ships_at_bootstrap(manifest: TutorialManifest) -> None:
    """The stack loader is not a lesson, so it is not a step.

    Tutorial 2 taught IO blocks and deliberately kept its TIFF loader out of
    My Library. This level's data therefore has to arrive with its own reader,
    and it arrives the way a facility's reader does: with the dataset.
    """
    assert manifest.bootstrap is not None
    destinations = {action.destination for action in iter_file_actions(manifest.bootstrap.do)}
    assert "blocks/load_section_stack.py" in destinations


def test_the_level_never_places_a_block_the_design_excludes(manifest: TutorialManifest) -> None:
    """DataRouter, MergeCollection and MergeBlock are out of scope by design.

    DataRouter competes with the git-branch lesson for the same idea, and the
    two merge blocks are same-type concatenation, which is not what joining two
    modalities is.
    """
    text = "\n".join(step.say or "" for step in manifest.steps).lower()
    for excluded in ("datarouter", "data router", "mergecollection", "merge collection", "merge block"):
        assert excluded not in text, f"the level mentions {excluded!r}, which its design excludes"


# ---------------------------------------------------------------------------
# The shipped data is its recipe
# ---------------------------------------------------------------------------


def test_the_shipped_stack_matches_its_recorded_recipe(assets: dict[str, ModuleType]) -> None:
    """Three pages, in acquisition order, pixel-identical to the recipe above."""
    pages = assets["stack"].read_section_stack(ASSETS / "data" / "sections.tif")
    assert [label for label, _ in pages] == list(ACQUISITION_ORDER)
    for label, pixels in pages:
        assert pixels.shape == SHAPE
        np.testing.assert_array_equal(pixels, _section_image(label))


def test_the_shipped_workbooks_match_their_recorded_recipe() -> None:
    """Both runs, every sheet, in the sequencing core's own label order."""
    for run in (1, 2):
        book = _workbook(run)
        assert list(book) == list(SHEET_ORDER)
        for section, frame in book.items():
            pd.testing.assert_frame_equal(
                frame.reset_index(drop=True),
                _counts_for(section, run).reset_index(drop=True),
                check_dtype=False,
            )


def test_the_two_exports_disagree_about_order_on_every_position() -> None:
    """The hazard the Pair Editor beat rests on is real, not narrated.

    If the two orders happened to share a position, one of the three pairs
    would be right by accident and the step text would be overstating.
    """
    assert ACQUISITION_ORDER != SHEET_ORDER
    assert sorted(ACQUISITION_ORDER) == sorted(SHEET_ORDER)
    assert all(left != right for left, right in zip(ACQUISITION_ORDER, SHEET_ORDER, strict=True))


def test_the_counts_are_hundreds_of_positions_by_tens_of_genes() -> None:
    """The scale the design asked for, held against drift in the recipe."""
    frame = _workbook_sheet(1, "S01")
    assert 100 <= len(frame) <= 999
    assert 10 <= len(GENES) <= 99
    assert set(GENES) <= set(frame.columns)
    assert {"position_id", "section", "y", "x"} <= set(frame.columns)


# ---------------------------------------------------------------------------
# The stack loader
# ---------------------------------------------------------------------------


def test_the_loader_names_every_page_from_the_file(assets: dict[str, ModuleType]) -> None:
    """The names the Pair Editor's two lists show come from the file, not the test.

    Without ``user["display_name"]`` the panel would offer three identical
    filenames and the reader could not tell which row is which section — the
    beat would be unplayable.
    """
    collection = (
        assets["stack"].LoadSectionStack().load(BlockConfig(params={"path": str(ASSETS / "data" / "sections.tif")}))
    )
    assert len(collection) == len(ACQUISITION_ORDER)

    from scistudio.blocks.base.interactive import interactive_item_label

    assert [interactive_item_label(item, i) for i, item in enumerate(collection)] == list(ACQUISITION_ORDER)


def test_the_loader_declares_a_load_capability_for_image(assets: dict[str, ModuleType]) -> None:
    """One declared capability: an Image, from a .tif, at a priority that breaks ties."""
    (capability,) = assets["stack"].LoadSectionStack.get_format_capabilities()
    assert capability.direction == "load"
    assert capability.data_type is assets["image"].Image
    assert ".tif" in capability.extensions
    assert capability.priority > 0, "a tie with another Image/.tif reader must resolve, not raise"


def test_the_loader_refuses_what_it_does_not_read(tmp_path: Path, assets: dict[str, ModuleType]) -> None:
    """A narrow reader says what it cannot do, by name, rather than guessing."""
    not_a_tiff = tmp_path / "notes.tif"
    not_a_tiff.write_bytes(b"this is not a tiff at all, not even close")
    with pytest.raises(ValueError, match="not a TIFF file"):
        assets["stack"].read_section_stack(not_a_tiff)

    compressed = tmp_path / "compressed.tif"
    compressed.write_bytes(_one_page_tiff(compression=5))
    with pytest.raises(ValueError, match="compressed"):
        assets["stack"].read_section_stack(compressed)


def _one_page_tiff(*, compression: int) -> bytes:
    """A minimal single-page TIFF, so the refusal path can be driven honestly."""
    pixels = np.zeros((4, 4), dtype=np.uint8)
    header = struct.pack("<2sHI", b"II", 42, 8)
    entries = [
        (256, 4, 1, 4),
        (257, 4, 1, 4),
        (258, 3, 1, 8),
        (259, 3, 1, compression),
        (273, 4, 1, 8 + 2 + 12 * 7 + 4),
        (277, 3, 1, 1),
        (279, 4, 1, pixels.nbytes),
    ]
    chunk = struct.pack("<H", len(entries))
    for tag, field_type, count, value in entries:
        if field_type == 3:
            chunk += struct.pack("<HHIHH", tag, field_type, count, value, 0)
        else:
            chunk += struct.pack("<HHII", tag, field_type, count, value)
    chunk += struct.pack("<I", 0)
    return header + chunk + bytes(pixels.tobytes())


# ---------------------------------------------------------------------------
# The reused segmentation, on new tissue
# ---------------------------------------------------------------------------


def test_tutorial_twos_block_finds_nine_regions_on_every_section(label_maps: dict[str, np.ndarray]) -> None:
    """The reuse claim, recomputed: the cell block finds tissue domains too.

    Nine per section is the number two step texts quote. It is not configured
    anywhere — it falls out of the shipped pixels through tutorial 2's own
    default threshold — so a drift in either file breaks this.
    """
    assert set(label_maps) == set(ACQUISITION_ORDER)
    for section, labels in label_maps.items():
        assert int(labels.max()) == REGIONS_PER_SECTION, f"{section} segmented into {labels.max()} regions"
        sizes = np.bincount(labels.ravel())[1:]
        assert sizes.min() > 100, f"{section} produced a speck-sized region: {sorted(sizes.tolist())}"


# ---------------------------------------------------------------------------
# The joint block
# ---------------------------------------------------------------------------


def test_the_joint_analysis_produces_one_row_per_region(analyses: dict[tuple[int, str], pd.DataFrame]) -> None:
    table = analyses[(1, "total_count")]
    assert len(table) == TOTAL_REGIONS
    assert list(table.columns[:6]) == ["section", "region", "cluster", "n_positions", "centroid_y", "centroid_x"]
    assert set(table["section"]) == set(ACQUISITION_ORDER)
    assert table["n_positions"].min() >= 4


def test_the_pairing_is_positional_and_the_block_says_so(assets: dict[str, ModuleType]) -> None:
    """Unequal collections are an error naming the counts, not a silent truncation."""
    import pyarrow as pa

    from scistudio.core.types import DataFrame
    from scistudio.core.types.collection import Collection

    image_cls = assets["image"].Image
    labels = Collection([image_cls(axes=["y", "x"], data=np.ones((4, 4), dtype=int)) for _ in range(3)])
    one_table = Collection([DataFrame(data=pa.Table.from_pandas(_workbook_sheet(1, "S01"), preserve_index=False))])
    with pytest.raises(ValueError, match="pairing is positional"):
        assets["joint"].JointRegionProfilesBlock().run(
            {"labels": labels, "expression": one_table}, BlockConfig(params={})
        )


def test_the_kmeans_is_deterministic_and_order_independent(assets: dict[str, ModuleType]) -> None:
    """A result a reader has to trust cannot depend on a seed or on row order.

    The block's initialisation is greedy rather than randomised precisely so
    this holds; a switch to textbook k-means++ would fail here.
    """
    kmeans = assets["joint"].kmeans
    rng = np.random.default_rng(11)
    points = np.concatenate([rng.normal(centre, 0.25, size=(12, 3)) for centre in ([0, 0, 0], [5, 5, 0], [0, 5, 5])])
    first = kmeans(points, 3)
    assert np.array_equal(first, kmeans(points, 3)), "the same input gave two answers"

    order = rng.permutation(len(points))
    shuffled = kmeans(points[order], 3)
    partition = {frozenset(np.flatnonzero(first == label).tolist()) for label in set(first.tolist())}
    reshuffled = {frozenset(order[np.flatnonzero(shuffled == label)].tolist()) for label in set(shuffled.tolist())}
    assert partition == reshuffled, "row order changed the partition"


def test_kmeans_degenerates_gracefully_when_there_is_nothing_to_split(assets: dict[str, ModuleType]) -> None:
    """Fewer points than clusters is a workflow that still runs."""
    kmeans = assets["joint"].kmeans
    assert kmeans(np.zeros((2, 3)), 3).tolist() == [0, 1]


# ---------------------------------------------------------------------------
# The science the step texts quote
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("run", "method"), sorted(EXPECTED_CLUSTER_SIZES))
def test_each_batch_and_method_gives_the_split_the_text_quotes(
    run: int, method: str, analyses: dict[tuple[int, str], pd.DataFrame]
) -> None:
    """The four-way result, recomputed from the shipped files every run.

    Two of these are the level's turning points and both are real statistics,
    not staged: total-count normalisation loses batch 2 to two runaway
    housekeeping genes, and median-of-ratios loses batch 1 because a shallow,
    zero-heavy run leaves its reference profile almost nothing to rest on.
    """
    assert _cluster_sizes(analyses[(run, method)]) == EXPECTED_CLUSTER_SIZES[(run, method)]


@pytest.mark.parametrize(("run", "method"), [(1, "total_count"), (2, "median_ratio")])
def test_the_right_method_gives_three_of_each_cluster_on_every_section(
    run: int, method: str, analyses: dict[tuple[int, str], pd.DataFrame]
) -> None:
    """What the figure is supposed to show, checked as a fact rather than a hope.

    Three sections of one tissue block carry three domains of each programme,
    so a clustering that found tissue rather than depth puts three of every
    colour on every panel. This is the reader's own check, so it has to be true.
    """
    table = analyses[(run, method)]
    counts = pd.crosstab(table["section"], table["cluster"])
    assert counts.to_numpy().tolist() == [[3, 3, 3]] * len(ACQUISITION_ORDER), counts.to_string()


def test_the_step_texts_quote_the_recomputed_numbers(
    manifest: TutorialManifest, analyses: dict[tuple[int, str], pd.DataFrame]
) -> None:
    """Every number a step states is derived here, so the prose cannot drift.

    Tutorial 2's lesson: a step that quotes a count is making a promise about
    the shipped data, and the only way that promise survives an edit is if the
    test recomputes it.
    """
    words = {2: "two", 3: "three", 5: "five", 7: "seven", 8: "eight", 9: "nine", 14: "fourteen", 18: "eighteen"}

    def spelled(values: list[int]) -> list[str]:
        return [words[value] for value in values]

    run_the_joint = _say(manifest, "run-the-joint-analysis").lower()
    assert "twenty-seven" in run_the_joint
    assert len(analyses[(1, "total_count")]) == TOTAL_REGIONS
    assert "nine, nine and nine" in run_the_joint
    assert _cluster_sizes(analyses[(1, "total_count")]) == [9, 9, 9]

    batch_two = _say(manifest, "point-it-at-the-second-run").lower()
    sizes = _cluster_sizes(analyses[(2, "total_count")])
    assert ", ".join(spelled(sizes[:-1])) + " and " + spelled(sizes)[-1] in batch_two

    fixed = _say(manifest, "a-normalisation-for-this-batch").lower()
    assert "nine, nine and nine" in fixed
    assert _cluster_sizes(analyses[(2, "median_ratio")]) == [9, 9, 9]
    wrong_for_batch_one = _cluster_sizes(analyses[(1, "median_ratio")])
    assert ", ".join(spelled(wrong_for_batch_one[:-1])) + " and " + spelled(wrong_for_batch_one)[-1] in fixed

    segmentation = _say(manifest, "segment-the-regions").lower()
    assert "nine regions per section, twenty-seven in all" in segmentation


def test_a_mispairing_is_silent_downstream_which_is_why_the_panel_exists(
    assets: dict[str, ModuleType],
    label_maps: dict[str, np.ndarray],
    tmp_path: Path,
) -> None:
    """The claim the Pair Editor beat rests on, verified in both directions.

    A mispaired run does not fail, does not warn, and does not even lose
    coverage — the positions are the same grid either way. It just answers a
    different question. That is the argument for fixing the order in the panel,
    where the item names are still visible, rather than hoping to notice
    downstream.
    """
    mispaired = _analyse(assets, label_maps, tmp_path, run=1, method="total_count", expression_order=SHEET_ORDER)
    assert len(mispaired) == TOTAL_REGIONS, "a wrong pairing still produces a full, plausible table"
    assert _cluster_sizes(mispaired) != [9, 9, 9], "the answer really is different"


def test_the_plot_script_draws_the_real_region_table(analyses: dict[tuple[int, str], pd.DataFrame]) -> None:
    """The shipped figure is drawn from the shipped analysis, not from a hope.

    The plot script is written into the reader's project and run by the plot
    card, which calls ``render(collection)`` and shows whatever comes back.
    Driving it here on the actual table catches the faults that otherwise
    surface as a red plot card several minutes into the level: a column that
    was renamed, a cluster column that is nullable, a section count the layout
    cannot take.
    """
    import matplotlib

    matplotlib.use("Agg")

    namespace: dict[str, Any] = {}
    exec((ASSETS / "code" / "region_map_render.py").read_text(encoding="utf-8"), namespace)

    class _Items:
        def __init__(self, frame: pd.DataFrame) -> None:
            self._frame = frame

        def open_one(self) -> pd.DataFrame:
            return self._frame

    class _Collection:
        def __init__(self, frame: pd.DataFrame) -> None:
            self.items = _Items(frame)

    figure = namespace["render"](_Collection(analyses[(1, "total_count")]))
    assert figure.axes, "render returned a figure with no panels"
    assert len(figure.axes) == len(ACQUISITION_ORDER), "one panel per section"
    assert "9 / 9 / 9" in figure._suptitle.get_text()


# ---------------------------------------------------------------------------
# The library reuse, end to end (#2125)
# ---------------------------------------------------------------------------


def test_a_completed_tutorial_two_library_serves_this_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The bridge tutorial 2's last three steps build, walked from the other side.

    A tutorial-scoped library seeded exactly as those steps leave it — the
    ``Image`` type, the ``segment_cells`` block, and the ``Image`` previewer —
    must register into a *fresh* tutorial project, because this whole level
    opens on a project that never built any of them.

    The previewer is the one at risk (#2125): promotion copies a previewer's
    source verbatim, so a file that hard-coded ``OwnerKind.PROJECT`` would be
    refused from the library tier. Tutorial 2's previewer derives its tier from
    where it sits, and this is the check that the derivation actually lands it
    in the user-tier slot a tutorial project's library rides (FR-070, #2086).
    """
    import shutil

    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core import dropins
    from scistudio.core.types.registry import TypeRegistry
    from scistudio.previewers.models import OwnerKind
    from scistudio.previewers.project import load_project_previewers, load_user_previewers
    from scistudio.previewers.registry import PreviewerRegistry

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    # The drop-in guard refuses a type stem that already names an imported
    # module, so the ``assets`` fixture's bare ``image`` binding would make the
    # library copy look like a shadowing collision. Take it out for this test
    # and let the scan import the library's own file, which is what a project
    # does.
    monkeypatch.delitem(sys.modules, "image", raising=False)

    library = dropins.tutorial_library_dir()
    for child, source in (
        ("types", "image.py"),
        ("blocks", "segment_cells.py"),
        ("previewers", "image_preview.py"),
    ):
        (library / child).mkdir(parents=True, exist_ok=True)
        shutil.copy(TUTORIAL_2_CODE / source, library / child / source)

    project = dropins.tutorial_parent_dir() / "two-modalities-one-answer"
    for child in ("types", "blocks", "previewers"):
        (project / child).mkdir(parents=True, exist_ok=True)
    (project / "project.yaml").write_text("name: Two Modalities\n", encoding="utf-8")

    types = TypeRegistry()
    dropins.register_type_scan_dirs(types, project)
    types.scan_all()
    assert "Image" in set(types.all_types()), "the type the level's first judged step waits on did not register"

    blocks = BlockRegistry()
    dropins.register_block_scan_dirs(blocks, project)
    blocks.scan()
    assert blocks.get_spec("segment_cells") is not None, "the reused segmentation block did not register"

    previewers = PreviewerRegistry()
    previewers.load_core()
    load_project_previewers(previewers, project)
    load_user_previewers(previewers, project)
    claimed = [spec for spec in previewers.all_specs() if spec.target_type == "Image"]
    assert claimed, "the Image previewer did not survive promotion into the library (#2125)"
    assert {spec.owner_kind for spec in claimed} == {OwnerKind.USER}, (
        "a scoped-library previewer must register in the user-tier slot, not the project one"
    )


# ---------------------------------------------------------------------------
# The whole session, walked through the real runtime
# ---------------------------------------------------------------------------


def test_the_whole_tutorial_walks_through_the_real_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every beat of the real manifest, driven end to end (#2082).

    The runtime, session store, and progress store are the real ones; the
    product-state port is stood in exactly as the API layer stands it in. The
    walk asserts what the level exists for: the library type is already there
    on the first judged step, the fork is built out of the reader's own drags,
    the pairing is the reader's own interaction, the plot is judged by the
    backend ``plot_rendered`` term rather than a reported event, and both git
    beats — make the branch, then return to main — are judged against real
    branch state.
    """
    import ast
    import shutil
    from dataclasses import dataclass
    from datetime import UTC, datetime, timedelta

    import yaml

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
        for path in map(Path, written):
            if path.suffix != ".py" or path.parent.name != "blocks":
                continue
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
        product.block_types = frozenset(blocks)

    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        project_dir=lambda: product.project_dir,
        provisioner=_Provisioner(),
        environment=DiscoveryEnvironment(
            scistudio_version="0.3.1",
            git_available=True,
            # This walk is about tutorial 3's own twenty beats, so the state
            # the reader arrives in is stated rather than re-earned: they have
            # finished tutorial 2, which is what puts the Image type, the
            # Segment Cells block, and the Image previewer in the library this
            # level reads from, and what clears the prerequisite (#2088).
            completed_tutorials=frozenset({TutorialKey.core("what-is-a-type")}),
        ),
        progress=ProgressStore(fake_home / ".scistudio"),
        sessions=SessionStore(fake_home / ".scistudio"),
        open_replay=lambda surface: pytest.fail(f"tutorial 3 declares no replay, yet one opened on {surface!r}"),
        record_ui_event=lambda name, target: _record(name, target),
        forget_ui_events=lambda: _forget(),
        files_written=_settle,
    )

    def _record(name: str, target: str | None) -> None:
        product.events = product.events | {name}
        if target is not None:
            product.targeted_events = product.targeted_events | {(name, target)}

    def _forget() -> None:
        product.events = frozenset()
        product.targeted_events = frozenset()

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[tuple[str, str]] = []

    def _write_workflow() -> None:
        assert product.project_dir is not None
        path = Path(product.project_dir) / "workflows" / "main.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {
                    "workflow": {
                        "id": "main",
                        "version": "1.0.0",
                        "description": "Two modalities — built step by step by the walk.",
                        "nodes": [
                            {"id": node_id, "block_type": body["block_type"], "config": {"params": body["params"]}}
                            for node_id, body in nodes.items()
                        ],
                        "edges": [{"source": source, "target": target} for source, target in edges],
                    }
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _run() -> None:
        # A millisecond past "now", not five seconds: six steps in this walk
        # say "press Run", and a record stamped into the future would satisfy
        # every subsequent step's ``since_step_entry`` before the reader ran
        # anything — which is exactly the fault that scoping exists to stop.
        started = (datetime.now(UTC) + timedelta(milliseconds=1)).isoformat()
        product.runs = (
            RunSummary(run_id=f"r{len(product.runs) + 1}", workflow_id="main", succeeded=True, started_at=started),
            *product.runs,
        )

    def _live(view: Any) -> Any:
        assert view is not None and view.step is not None
        return view.step

    def _advance(expect: str) -> Any:
        moved = runtime.continue_active()
        assert moved.step is not None and moved.step.id == expect, (
            f"expected {expect!r}, on {moved.step.id if moved.step else None!r}"
        )
        return moved

    view = runtime.start(TutorialKey.core("two-modalities-one-answer"))
    assert view.step is not None and view.step.id == "two-instruments-one-block-of-tissue"
    project = Path(view.project_path or "")
    product.project_dir = project
    for name in ("sections.tif", "run1_counts.xlsx", "run2_counts.xlsx"):
        assert (project / "data" / "raw" / name).is_file(), f"the bootstrap did not land {name}"
    assert (project / "blocks" / "load_section_stack.py").is_file(), "the instrument's reader ships with the data"
    assert "load_section_stack" in product.block_types, "the bootstrap settle registered the reader"

    # The library is the premise of the level, not something it builds: the
    # first judged step is already satisfied when the reader arrives on it.
    product.data_types = frozenset({"Image"})
    product.block_types = product.block_types | {"segment_cells"}
    product.previewer_types = frozenset({"Image"})
    _advance("your-library-came-with-you")
    assert _live(runtime.active_session()).satisfied is True

    _advance("load-the-slides")
    assert _live(runtime.active_session()).satisfied is False
    nodes["load-images"] = {"block_type": "load_data", "params": {}}
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is False, "an unconfigured Load is not the step"
    nodes["load-images"]["params"] = {"path": "data/raw/sections.tif", "core_type": "Image"}
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("see-the-sections")
    _run()
    assert _live(runtime.evaluate_active()).satisfied is False, "the run alone is not the look"
    assert _live(runtime.report_ui_event("node_selected", "load_data")).satisfied is True

    _advance("load-the-counts")
    assert _live(runtime.active_session()).satisfied is False
    nodes["load-counts"] = {
        "block_type": "load_data",
        "params": {"path": "data/raw/run1_counts.xlsx", "core_type": "DataFrame"},
    }
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("pair-the-two-streams")
    assert _live(runtime.active_session()).satisfied is False
    nodes["pair-1"] = {"block_type": "paireditor_block", "params": {}}
    edges += [("load-images:data", "pair-1:port_1"), ("load-counts:data", "pair-1:port_2")]
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("they-do-not-line-up")
    assert _live(runtime.active_session()).satisfied is False
    product.interactions = frozenset({"pair-1"})
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("segment-the-regions")
    assert _live(runtime.active_session()).satisfied is False
    nodes["segment-1"] = {"block_type": "segment_cells", "params": {}}
    edges.append(("pair-1:out_1", "segment-1:image"))
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("read-the-source")
    assert _live(runtime.active_session()).satisfied is False
    assert _live(runtime.report_ui_event("block_source_viewed", "segment_cells")).satisfied is True

    _advance("normalise-the-counts")
    view = runtime.trigger_active()
    assert (project / "blocks" / "normalize_expression.py").is_file()
    assert "normalize_expression" in product.block_types, (
        "the settle registered the block before the press reported done"
    )
    assert _live(view).satisfied is False, "the block exists; the reader still wires it"
    nodes["norm-1"] = {"block_type": "normalize_expression", "params": {}}
    edges.append(("pair-1:out_2", "norm-1:counts"))
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("the-joint-block")
    view = runtime.trigger_active()
    assert (project / "blocks" / "joint_region_profiles.py").is_file()
    assert _live(view).satisfied is False
    nodes["joint-1"] = {"block_type": "joint_region_profiles", "params": {}}
    edges.append(("segment-1:labels", "joint-1:labels"))
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is False, "one branch in is not a joint analysis"
    edges.append(("norm-1:normalized", "joint-1:expression"))
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("run-the-joint-analysis")
    _run()
    assert _live(runtime.evaluate_active()).satisfied is False
    assert _live(runtime.report_ui_event("node_selected", "joint_region_profiles")).satisfied is True

    _advance("bind-a-plot")
    assert _live(runtime.active_session()).satisfied is False
    product.plots = (("region_map", "joint-1", "regions"),)
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("draw-it")
    assert (project / "plots" / "region_map" / "render.py").is_file(), "the entry action filled in the plot script"
    assert _live(runtime.active_session()).satisfied is False, "writing the script is not rendering it"
    product.rendered = (("main", "joint-1", "regions", "region_map"),)
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("a-second-run-arrives")
    assert _live(runtime.active_session()).satisfied is False
    product.branches = frozenset({"main", "batch-2"})
    assert _live(runtime.evaluate_active()).satisfied is False, "a branch that exists is not a branch you are on"
    product.current_branch = "batch-2"
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("point-it-at-the-second-run")
    assert _live(runtime.active_session()).satisfied is False
    nodes["load-counts"]["params"]["path"] = "data/raw/run2_counts.xlsx"
    _write_workflow()
    assert _live(runtime.evaluate_active()).satisfied is False, "the reader still has to run it"
    _run()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("a-normalisation-for-this-batch")
    assert _live(runtime.active_session()).satisfied is False
    nodes["norm-1"]["params"] = {"method": "median_ratio"}
    _write_workflow()
    _run()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("switch-back")
    assert _live(runtime.active_session()).satisfied is False
    # Checking out main restores the recipe — and only the recipe.
    nodes["load-counts"]["params"]["path"] = "data/raw/run1_counts.xlsx"
    nodes["norm-1"]["params"] = {}
    _write_workflow()
    product.current_branch = "main"
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("git-stores-the-recipe")
    assert _live(runtime.active_session()).satisfied is False, "the stale figure is the point; the rerun is the lesson"
    _run()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("two-variants-alive")
    assert runtime.continue_active().status is SessionStatus.COMPLETE

    # Tutorial 3 is a level, not the milestone: completing it must not offer
    # the work import (FR-079 names tutorial 4).
    assert runtime.progress_store.work_import_offer_pending() is False
