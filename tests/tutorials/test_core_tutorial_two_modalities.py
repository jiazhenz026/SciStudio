"""Core tutorial 4 — the multimodal, joint-analysis, git-branch level.

``test_core_tutorials.py`` already applies the format-level conformance every
shipped tutorial gets. This file checks what only tutorial 4 promises (#2082):

* the beat order and each beat's judged condition survive edits;
* the level owes nothing to any other level: its picture types, the reader that
  turns a slide file into one, their preview panel and the three analysis blocks
  are landed by its own bootstrap and register into its project;
* the shipped data is what ``SOURCE.md`` says it is — the two ER tumors land at
  bootstrap, the two triple-negative ones arrive on the branch, and each
  sample's slide, mask and count table describe the same spots;
* the three workflows read only files the level lands, and the TNBC recipe
  differs from the ER one in its Loads and one setting, nothing else;
* the science is recomputed, not asserted: every gene the steps and the notes
  name is significant, in the same direction, in both tumors of its batch;
* the preview panel draws every pixel of a slide, read in tiles, never a sampled overview;
* the whole story walks through the real runtime, git terms included.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml
from PIL import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.tutorials.actions import iter_file_actions
from scistudio.tutorials.manifest import TutorialManifest, TutorialSourceKind, load_manifest

from .conftest import say_text

REPO_ROOT = Path(__file__).resolve().parents[2]
TUTORIAL_DIR = REPO_ROOT / "src" / "scistudio" / "tutorials" / "core" / "two-modalities-one-answer"
ASSETS = TUTORIAL_DIR / "assets"
DATA = ASSETS / "data"
WORKFLOWS = ASSETS / "workflows"

#: Which samples ship in which directory. The ER pair opens the level; the
#: triple-negative pair arrives when the subtype changes and the analysis
#: branches.
SAMPLES = {"er": ("CID4535", "CID4290"), "tnbc": ("CID44971", "CID4465")}
ALL_SAMPLES = tuple((subtype, sample) for subtype, samples in SAMPLES.items() for sample in samples)

GENE_PANEL_SIZE = 2000

#: The genes the level's text names, by batch and direction. Each must be
#: significant in both tumors of its batch, moving the same way.
QUOTED = {
    "er": {
        "higher": ("KRT8", "KRT18", "EPCAM", "CDH1", "GATA3", "FOXA1"),
        "lower": ("CCDC80", "SFRP4", "DCN"),
    },
    "tnbc": {
        "higher": ("MMP9", "CXCL10", "CXCL9", "KRT16"),
        "lower": ("COL14A1", "TNXB", "AQP1"),
    },
}

#: Every block the level lands, and the file it lands from.
LEVEL_BLOCKS = {
    "load_slide_image": "load_slide_image.py",
    "annotate_regions": "annotate_regions.py",
    "normalize_expression": "normalize_expression.py",
    "compare_regions": "compare_regions.py",
}


@pytest.fixture(scope="module")
def manifest() -> TutorialManifest:
    return load_manifest(TUTORIAL_DIR, source_kind=TutorialSourceKind.CORE)


@pytest.fixture(scope="module")
def code(request: pytest.FixtureRequest) -> dict[str, ModuleType]:
    """The shipped code assets, imported the way the drop-in scans import them.

    The two type modules must land in ``sys.modules`` under their bare stems
    first, because the loader and Annotate Regions open with ``from he_image
    import HEImage`` / ``from he_mask import HEMask``: the exact import they
    perform in a project, where the types directory joins ``sys.path``.
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

    modules = {"he_image": load("he_image", "he_image.py"), "he_mask": load("he_mask", "he_mask.py")}
    modules["loader"] = load("_scistudio_t4_loader", "load_slide_image.py")
    modules["annotate"] = load("_scistudio_t4_annotate", "annotate_regions.py")
    modules["normalize"] = load("_scistudio_t4_normalize", "normalize_expression.py")
    modules["compare"] = load("_scistudio_t4_compare", "compare_regions.py")

    request.addfinalizer(lambda: [sys.modules.pop(name, None) for name in bound])
    return modules


def _file(subtype: str, sample: str, kind: str) -> Path:
    suffix = {"he": "_he.png", "mask": "_mask.png", "counts": "_counts.csv"}[kind]
    return DATA / subtype / f"{sample}{suffix}"


def _workflow(name: str) -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return document


def _node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in document["workflow"]["nodes"] if node["id"] == node_id)


def _step(manifest: TutorialManifest, step_id: str) -> Any:
    return next(step for step in manifest.steps if step.id == step_id)


# ---------------------------------------------------------------------------
# The beat map
# ---------------------------------------------------------------------------


def test_the_beat_map_is_the_designed_one(manifest: TutorialManifest) -> None:
    """Beat -> step -> condition, as dispatched. A reorder or a swapped judge fails here.

    A step that declares ``auto_advance`` leaves the instant its condition is
    met, so a payoff written under the instruction would never be read: every
    payoff opens the *following* step, and a reading step judges nothing
    (``None`` below).
    """
    expected = [
        ("todays-data", None),
        ("two-instruments-one-question", None),
        ("read-them-in", {"run_succeeded"}),
        ("look-at-them", {"ui_event"}),
        ("open-a-mask", {"ui_event"}),
        ("write-the-analysis", {"node_exists"}),
        ("pair-them", {"interaction_completed"}),
        ("read-the-answer", {"ui_event"}),
        ("draw-the-plots", {"plot_exists"}),
        ("run-the-volcano", {"plot_rendered"}),
        ("run-the-shared-genes", {"plot_rendered"}),
        ("the-conclusion", None),
        ("name-the-note", {"file_exists"}),
        ("write-it-down", None),
        ("two-new-tumors", None),
        ("commit-first", {"ui_event"}),
        ("see-the-er-setting", {"ui_event"}),
        ("the-er-setting", None),
        ("make-a-branch", {"git_branch_exists", "git_current_branch"}),
        ("point-it-at-tnbc", {"config_equals"}),
        ("see-what-changed", {"ui_event"}),
        ("what-changed", None),
        ("run-tnbc", {"run_succeeded"}),
        ("look-at-a-tnbc-mask", {"ui_event"}),
        ("open-a-tnbc-mask", {"ui_event"}),
        ("why-the-stroma", None),
        ("rerun-the-plots", {"ui_event"}),
        ("tnbc-conclusion", None),
        ("name-the-tnbc-note", {"file_exists"}),
        ("write-the-tnbc-note", None),
        ("commit-tnbc", {"ui_event"}),
        ("switch-back", {"git_current_branch"}),
        ("see-the-er-setting-again", {"ui_event"}),
        ("er-is-back", None),
        ("the-end", None),
    ]
    actual = [(step.id, step.done_when.terms() if step.done_when else None) for step in manifest.steps]
    assert actual == expected


def test_every_run_judge_is_scoped_to_its_own_step(manifest: TutorialManifest) -> None:
    """The reader must run *here*, not be credited with a run from an earlier beat."""

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


def test_the_second_pairing_is_judged_on_the_run(manifest: TutorialManifest) -> None:
    """An interaction marker, once set for ``pair``, is never cleared.

    The ER pairing sets it, so a TNBC step judged on ``interaction_completed``
    would pass on arrival. The TNBC run is judged on the run instead, which
    cannot finish until the Pair Editor was confirmed.
    """
    assert _step(manifest, "run-tnbc").done_when.terms() == {"run_succeeded"}


def test_both_commits_are_the_readers_own(manifest: TutorialManifest) -> None:
    """Each commit step waits for a commit, rings the button, and seeds the message."""
    for step_id in ("commit-first", "commit-tnbc"):
        step = _step(manifest, step_id)
        assert step.done_when.args == {"name": "git_committed"}
        assert "git_commit_button" in {h.target for h in step.highlights if h is not None}
        assert [p.target for p in step.prefill] == ["git_commit"]


# ---------------------------------------------------------------------------
# What the level lands, and when
# ---------------------------------------------------------------------------


def test_what_the_level_does_not_teach_ships_at_bootstrap(manifest: TutorialManifest) -> None:
    """The ER data and the eight code files land before the first step.

    None of them is a lesson. Landing them here rather than pulling them from
    My Library is what lets the level be played first.
    """
    assert manifest.bootstrap is not None
    actions = list(iter_file_actions(manifest.bootstrap.do))
    assert {action.destination for action in actions} == {
        "data/raw",
        "types/he_image.py",
        "types/he_mask.py",
        "panels/image_preview",
        *(f"blocks/{source}" for source in LEVEL_BLOCKS.values()),
    }
    # Only the two ER tumors: the opening says "the first two" and means it.
    assert {action.source for action in actions if action.destination == "data/raw"} == {"assets/data/er"}


def test_each_press_writes_what_its_step_says(manifest: TutorialManifest) -> None:
    """Three buttons, and the files behind each."""
    triggered = {
        step.id: {(action.source, action.destination) for action in iter_file_actions(step.trigger.do)}
        for step in manifest.steps
        if step.trigger
    }
    assert triggered == {
        "write-the-analysis": {("assets/workflows/analysis.yaml", "workflows/main.yaml")},
        "draw-the-plots": {
            ("assets/code/volcano_plot.yaml", "plots/cancer_vs_rest/plot.yaml"),
            ("assets/code/volcano_render.py", "plots/cancer_vs_rest/render.py"),
            ("assets/code/shared_genes_plot.yaml", "plots/shared_genes/plot.yaml"),
            ("assets/code/shared_genes_render.py", "plots/shared_genes/render.py"),
        },
        "point-it-at-tnbc": {
            ("assets/data/tnbc", "data/raw"),
            ("assets/workflows/analysis_tnbc.yaml", "workflows/main.yaml"),
        },
    }


def test_the_notes_are_filled_where_new_note_puts_them(manifest: TutorialManifest) -> None:
    """The reader names each note; the next step writes into that same path."""
    for named, filled in (("name-the-note", "write-it-down"), ("name-the-tnbc-note", "write-the-tnbc-note")):
        path = _step(manifest, named).done_when.args["path"]
        assert [action.destination for action in iter_file_actions(_step(manifest, filled).do)] == [path]


def test_the_level_declares_no_tutorial_prerequisite(manifest: TutorialManifest) -> None:
    """The premise is landed, not required (#2088)."""
    assert manifest.requires.tutorials == ()


def test_no_step_claims_the_reader_built_the_landed_artifacts(manifest: TutorialManifest) -> None:
    """A reader starting here never built anything in an earlier level."""
    text = "\n".join(say_text(step) for step in manifest.steps).lower()
    for claimed in ("last level", "my library", "your library", "you built", "you saved"):
        assert claimed not in text, f"a step claims {claimed!r}, which a reader starting here never did"


def test_the_level_never_places_a_block_the_design_excludes(manifest: TutorialManifest) -> None:
    """DataRouter competes with the git-branch lesson; the merge blocks are not a join of modalities."""
    text = "\n".join(say_text(step) for step in manifest.steps).lower()
    for excluded in ("datarouter", "data router", "mergecollection", "merge collection", "merge block"):
        assert excluded not in text, f"the level mentions {excluded!r}, which its design excludes"


# ---------------------------------------------------------------------------
# The shipped data is what SOURCE.md says it is
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subtype", sorted(SAMPLES))
def test_each_sample_ships_a_slide_a_mask_and_a_table(subtype: str) -> None:
    expected = {"SOURCE.md"} | {
        f"{sample}{suffix}" for sample in SAMPLES[subtype] for suffix in ("_he.png", "_mask.png", "_counts.csv")
    }
    assert {path.name for path in (DATA / subtype).iterdir()} == expected


@pytest.mark.parametrize("subtype", sorted(SAMPLES))
def test_the_spot_counts_source_md_quotes_are_the_shipped_ones(subtype: str) -> None:
    """The attribution file quotes a spot count per sample; the tables must agree."""
    quoted = {
        match.group(1): int(match.group(2).replace(",", ""))
        for match in re.finditer(
            r"^\| (CID\d+) \| \w+ \| ([\d,]+) \|$", (DATA / subtype / "SOURCE.md").read_text(), re.M
        )
    }
    assert set(quoted) == set(SAMPLES[subtype])
    for sample, spots in quoted.items():
        table = pd.read_csv(_file(subtype, sample, "counts"), usecols=["barcode"])
        assert len(table) == spots, f"{sample}: SOURCE.md quotes {spots} spots, the table has {len(table)}"


def test_every_table_carries_the_same_gene_panel() -> None:
    """One shared panel, so a comparison across tumors compares the same genes."""
    headers = {
        sample: list(pd.read_csv(_file(subtype, sample, "counts"), nrows=0).columns) for subtype, sample in ALL_SAMPLES
    }
    for sample, columns in headers.items():
        assert columns[:3] == ["barcode", "x", "y"], f"{sample} does not open with barcode, x, y"
        assert len(columns) - 3 == GENE_PANEL_SIZE, f"{sample} carries {len(columns) - 3} genes"
    panels = {tuple(columns[3:]) for columns in headers.values()}
    assert len(panels) == 1, "the four tables carry different gene panels"


@pytest.mark.parametrize(("subtype", "sample"), ALL_SAMPLES)
def test_every_spot_falls_on_its_slide(subtype: str, sample: str) -> None:
    """``x`` and ``y`` are pixels on the shipped image, so every spot must land inside it."""
    width, height = Image.open(_file(subtype, sample, "he")).size
    spots = pd.read_csv(_file(subtype, sample, "counts"), usecols=["x", "y"])
    assert spots["x"].between(0, width - 1).all()
    assert spots["y"].between(0, height - 1).all()


@pytest.mark.parametrize(("subtype", "sample"), ALL_SAMPLES)
def test_a_mask_is_its_slide_with_a_key_beneath(subtype: str, sample: str) -> None:
    """Same width as the slide, taller by the key; the slide's rows keep their coordinates."""
    slide = Image.open(_file(subtype, sample, "he")).size
    mask = Image.open(_file(subtype, sample, "mask")).size
    assert mask[0] == slide[0]
    assert mask[1] > slide[1]


# ---------------------------------------------------------------------------
# The three workflows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "subtype"), [("main.yaml", "er"), ("analysis.yaml", "er"), ("analysis_tnbc.yaml", "tnbc")]
)
def test_each_workflow_reads_only_what_the_level_lands(name: str, subtype: str) -> None:
    """Every Load path names a file the level copied into ``data/raw`` by then."""
    from scistudio.workflow.schema import WorkflowFileModel

    document = _workflow(name)
    WorkflowFileModel.model_validate(document)
    landed = {f"data/raw/{path.name}" for path in (DATA / subtype).iterdir()}
    loads = [node for node in document["workflow"]["nodes"] if node["block_type"] == "load_data"]
    assert loads, f"{name} reads nothing"
    for node in loads:
        assert set(node["config"]["params"]["path"]) <= landed, f"{name}: {node['id']} reads a file not landed"


@pytest.mark.parametrize("name", ["main.yaml", "analysis.yaml", "analysis_tnbc.yaml"])
def test_the_mask_load_is_the_one_a_ring_lands_on(name: str) -> None:
    """A ``node`` ring lands on the first Load drawn, and the steps ask for the masks."""
    loads = [node for node in _workflow(name)["workflow"]["nodes"] if node["block_type"] == "load_data"]
    assert loads[0]["config"]["params"]["core_type"] == "HEMask"


def test_the_er_tables_arrive_in_the_other_order() -> None:
    """The hazard the first pairing rests on is real: every position is mispaired."""
    params = {
        node["id"]: node.get("config", {}).get("params", {}) for node in _workflow("analysis.yaml")["workflow"]["nodes"]
    }
    masks = [Path(path).name.split("_")[0] for path in params["load-masks"]["path"]]
    tables = [Path(path).name.split("_")[0] for path in params["load-counts"]["path"]]
    assert sorted(masks) == sorted(tables)
    assert all(mask != table for mask, table in zip(masks, tables, strict=True))


def test_the_tnbc_recipe_differs_only_in_its_loads_and_one_setting() -> None:
    """A branch holds a variant, so the variant is kept as small as the data asks."""
    er, tnbc = _workflow("analysis.yaml")["workflow"], _workflow("analysis_tnbc.yaml")["workflow"]
    assert er["edges"] == tnbc["edges"]
    assert [node["id"] for node in er["nodes"]] == [node["id"] for node in tnbc["nodes"]]
    for er_node, tnbc_node in zip(er["nodes"], tnbc["nodes"], strict=True):
        if er_node["block_type"] == "load_data":
            continue
        er_params = dict(er_node.get("config", {}).get("params", {}))
        tnbc_params = dict(tnbc_node.get("config", {}).get("params", {}))
        if er_node["id"] == "compare":
            assert er_params.get("against", "Rest of the tissue") == "Rest of the tissue"
            assert tnbc_params.pop("against") == "Stroma"
            er_params.pop("against", None)
        assert er_params == tnbc_params, f"{er_node['id']} differs between the recipes"


# ---------------------------------------------------------------------------
# The reader, the previewer and the blocks
# ---------------------------------------------------------------------------


def test_the_loader_claims_png_for_both_picture_types(code: dict[str, ModuleType]) -> None:
    capabilities = code["loader"].LoadSlideImage.format_capabilities
    assert {(capability.data_type.__name__, capability.format_id) for capability in capabilities} == {
        ("HEImage", "png"),
        ("HEMask", "png"),
    }


@pytest.mark.parametrize(
    ("kind", "capability_id", "type_name"),
    [
        ("he", "tutorial.he_image.png.load", "HEImage"),
        ("mask", "tutorial.he_mask.png.load", "HEMask"),
    ],
)
def test_the_loader_builds_the_type_its_capability_names(
    code: dict[str, ModuleType], kind: str, capability_id: str, type_name: str
) -> None:
    path = _file("er", "CID4535", kind)
    width, height = Image.open(path).size
    loaded = code["loader"].LoadSlideImage().load_file(path, {"capability_id": capability_id})
    assert type(loaded).__name__ == type_name
    assert np.asarray(loaded.to_memory()).shape == (height, width, 3)


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "LA"])
def test_the_hand_written_reader_decodes_what_pillow_writes(
    code: dict[str, ModuleType], tmp_path: Path, mode: str
) -> None:
    """Every row filter, and the four 8-bit color types, read back pixel for pixel.

    The shipped pictures use no filter. A PNG from anywhere else usually uses
    all five, which is the case this pins: Pillow chooses them per row.
    """
    rng = np.random.default_rng(2082)
    ramp = np.add.outer(np.arange(48), np.arange(64)).astype(np.uint8)
    channels = {"RGB": 3, "RGBA": 4, "L": 1, "LA": 2}[mode]
    pixels = np.stack([ramp + rng.integers(0, 4, ramp.shape, dtype=np.uint8) for _ in range(channels)], axis=-1)
    picture = Image.fromarray(pixels[..., 0] if channels == 1 else pixels, mode)
    path = tmp_path / f"{mode}.png"
    picture.save(path, optimize=True)
    expected = np.asarray(picture.convert("RGB"))
    np.testing.assert_array_equal(code["loader"].read_png(path), expected)


@pytest.mark.parametrize(("subtype", "sample"), ALL_SAMPLES)
def test_the_shipped_pictures_read_back_as_pillow_reads_them(
    code: dict[str, ModuleType], subtype: str, sample: str
) -> None:
    for kind in ("he", "mask"):
        path = _file(subtype, sample, kind)
        np.testing.assert_array_equal(code["loader"].read_png(path), np.asarray(Image.open(path).convert("RGB")))


def test_the_preview_panel_draws_every_pixel_in_color() -> None:
    """A preview shows only real values (#1886): tiles, never a sampled plane, and three channels as RGB."""
    source = (ASSETS / "panels" / "image_preview" / "index.html").read_text(encoding="utf-8")
    assert '<script src="../../sdk/1/scistudio-panel.js"></script>' in source
    assert 'api.read("array.tile"' in source
    assert "array.plane" not in source
    assert "axis.size >= RGB" in source, "three channels on c are drawn as colour"
    for banned in ("import ", "require(", "fetch(", "http://", "https://"):
        assert banned not in source, f"the panel must stay dependency-free and offline; found {banned!r}"


def test_every_level_block_has_an_icon_of_its_own(code: dict[str, ModuleType]) -> None:
    """Four blocks of one category would otherwise draw four identical nodes."""
    classes = (
        code["loader"].LoadSlideImage,
        code["annotate"].AnnotateRegionsBlock,
        code["normalize"].NormalizeExpressionBlock,
        code["compare"].CompareRegionsBlock,
    )
    icons = [cls.ui_icon for cls in classes]
    assert all(icons) and len(set(icons)) == len(icons)


# ---------------------------------------------------------------------------
# The science, recomputed
# ---------------------------------------------------------------------------


def _analyse(code: dict[str, ModuleType], store: Path, subtype: str, order: tuple[str, ...], **params: Any) -> list:
    """Masks and tables in, one gene table per tumor out, flushed between blocks.

    In a run the engine flushes each block's output to project storage before
    the next block reads it. These tests call the blocks directly, so they flush.
    """
    from scistudio.blocks.io.loaders.load_data import LoadData
    from scistudio.core.types.collection import Collection

    counter = [0]

    def flush(items: Any) -> Any:
        kept = []
        for item in items:
            counter[0] += 1
            item.save(store / f"{subtype}-{counter[0]}")
            kept.append(item)
        return Collection(kept)

    samples = SAMPLES[subtype]
    masks = flush(
        code["loader"]
        .LoadSlideImage()
        .load_file(_file(subtype, s, "mask"), {"capability_id": "tutorial.he_mask.png.load"})
        for s in samples
    )
    tables = LoadData().run(
        {}, BlockConfig(params={"path": [str(_file(subtype, s, "counts")) for s in order], "core_type": "DataFrame"})
    )["data"]
    annotated = flush(
        code["annotate"]
        .AnnotateRegionsBlock()
        .run({"mask": masks, "counts": tables}, BlockConfig(params={}))["annotated"]
    )
    if params.get("stop_after_annotate"):
        return [item.to_memory().to_pandas() for item in annotated]
    normalized = flush(
        code["normalize"].NormalizeExpressionBlock().run({"counts": annotated}, BlockConfig(params={}))["normalized"]
    )
    genes = flush(code["compare"].CompareRegionsBlock().run({"spots": normalized}, BlockConfig(params=params))["genes"])
    return [item.to_memory().to_pandas().set_index("gene") for item in genes]


@pytest.fixture(scope="module")
def results(code: dict[str, ModuleType], tmp_path_factory: pytest.TempPathFactory) -> dict[str, list]:
    """Each batch through its own recipe, correctly paired. Computed once."""
    store = tmp_path_factory.mktemp("t4-analyses")
    return {
        "er": _analyse(code, store, "er", SAMPLES["er"]),
        "tnbc": _analyse(code, store, "tnbc", SAMPLES["tnbc"], against="Stroma"),
    }


@pytest.mark.parametrize("subtype", sorted(QUOTED))
def test_every_quoted_gene_holds_in_both_tumors(results: dict[str, list], subtype: str) -> None:
    """The text says "both tumors agree"; so must the recomputed tables."""
    tables = results[subtype]
    assert len(tables) == 2
    for direction, genes in QUOTED[subtype].items():
        for gene in genes:
            for table in tables:
                assert gene in table.index, f"{gene} was not tested in {table['tumor'].iloc[0]}"
                fold, q = table.at[gene, "log2_fold_change"], table.at[gene, "q_value"]
                assert q < 0.05, f"{gene} is not significant in {table['tumor'].iloc[0]} (q={q:.3g})"
                assert (fold > 0) == (direction == "higher"), f"{gene} moves the wrong way in {table['tumor'].iloc[0]}"


def test_the_recipes_compare_what_they_say(results: dict[str, list]) -> None:
    assert {table["against"].iloc[0] for table in results["er"]} == {"Rest of the tissue"}
    assert {table["against"].iloc[0] for table in results["tnbc"]} == {"Stroma"}


@pytest.mark.parametrize(
    ("subtype", "note"),
    [("er", "conclusion.md"), ("tnbc", "conclusion_tnbc.md")],
)
def test_the_notes_and_the_steps_name_only_genes_that_hold(manifest: TutorialManifest, subtype: str, note: str) -> None:
    """Nothing the reader is told to write down is outside the recomputed list."""
    named = set(QUOTED[subtype]["higher"]) | set(QUOTED[subtype]["lower"])
    text = (ASSETS / "notes" / note).read_text(encoding="utf-8")
    step = say_text(_step(manifest, "the-conclusion" if subtype == "er" else "tnbc-conclusion"))
    for source in (text, step):
        # Capitalized names only, minus the two subtypes, the receptor and the
        # tumor ids (CID...), which are not genes.
        words = re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", source)
        mentioned = {word for word in words if word not in {"TNBC", "HER2"} and not re.fullmatch(r"CID\d+", word)}
        # Genes named only to say they do *not* agree are allowed in the TNBC note.
        mentioned -= {"GATA3", "KRT18"} if subtype == "tnbc" else set()
        assert mentioned <= named, f"{sorted(mentioned - named)} are named but not recomputed"


def test_a_mispairing_is_silent_and_changes_the_answer(code: dict[str, ModuleType], tmp_path: Path) -> None:
    """Why the Pair Editor is in the level: nothing downstream notices.

    Each tumor's spots, read off the other tumor's mask, still all get a region
    — mostly the gray Normal of bare slide under them — and no block fails.
    """
    paired = _analyse(code, tmp_path, "er", SAMPLES["er"], stop_after_annotate=True)
    swapped = _analyse(code, tmp_path, "er", SAMPLES["er"][::-1], stop_after_annotate=True)
    for right, wrong in zip(paired, swapped, strict=True):
        assert right["region"].notna().all() and wrong["region"].notna().all()
    assert (paired[1]["region"] == "Invasive cancer").mean() > 0.9
    assert (swapped[0]["region"] == "Normal").mean() > 0.8


# ---------------------------------------------------------------------------
# What the bootstrap lands, registered end to end
# ---------------------------------------------------------------------------


def test_the_landed_artifacts_register_into_the_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The files the bootstrap writes have to become real product state.

    The Load block's core_type list has to offer ``HEImage`` and ``HEMask``,
    dispatch has to find the slide reader, the palette has to carry the three
    analysis blocks, and the preview panel has to draw a slide as a picture.
    Landed in the project's own ``panels/``, the panel folder registers at the
    project tier for both picture types.
    """
    import shutil

    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core import dropins
    from scistudio.core.types.registry import TypeRegistry
    from scistudio.panels.registry import discover_panels
    from scistudio.previewers.models import OwnerKind

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    # The drop-in guard refuses a type stem that already names an imported
    # module, so the ``code`` fixture's bare bindings would make the landed
    # copies look like shadowing collisions. Let the scan import the project's
    # own files, which is what the product does.
    for stem in ("he_image", "he_mask"):
        monkeypatch.delitem(sys.modules, stem, raising=False)

    project = dropins.tutorial_parent_dir() / "two-modalities-one-answer"
    for child in ("types", "blocks"):
        (project / child).mkdir(parents=True, exist_ok=True)
    (project / "project.yaml").write_text("name: Two Modalities\n", encoding="utf-8")
    landed = [("types", "he_image.py"), ("types", "he_mask.py")]
    landed += [("blocks", source) for source in LEVEL_BLOCKS.values()]
    for child, source in landed:
        shutil.copy(ASSETS / "code" / source, project / child / source)
    shutil.copytree(ASSETS / "panels" / "image_preview", project / "panels" / "image_preview")

    types = TypeRegistry()
    dropins.register_type_scan_dirs(types, project)
    types.scan_all()
    assert {"HEImage", "HEMask"} <= set(types.all_types()), "the picture types the Loads ask for did not register"

    blocks = BlockRegistry()
    dropins.register_block_scan_dirs(blocks, project)
    blocks.scan()
    for block_type in LEVEL_BLOCKS:
        assert blocks.get_spec(block_type) is not None, f"{block_type} did not register"

    panels = discover_panels(project, registered_types=set(types.all_types()))
    candidates = [spec for panel in panels.panels.values() for spec in panel.candidates()]
    for type_name in ("HEImage", "HEMask"):
        claimed = [spec for spec in candidates if spec.target_type == type_name]
        assert claimed, f"no previewer claims {type_name}, so it previews as a number table"
        assert {spec.owner_kind for spec in claimed} == {OwnerKind.PROJECT}


# ---------------------------------------------------------------------------
# The whole session, walked through the real runtime
# ---------------------------------------------------------------------------


def _project_backed_state() -> Any:
    """A product-state stand-in that reads the workflow off the project file, as the product does."""
    from dataclasses import dataclass

    from scistudio.workflow.schema import WorkflowFileModel

    from .conftest import StubProductState

    @dataclass
    class _ProjectBackedState(StubProductState):
        def workflow(self) -> Any:
            self.reads.append("workflow")
            if self.project_dir is None:
                return None
            path = Path(self.project_dir) / "workflows" / "main.yaml"
            if not path.is_file():
                return None
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return WorkflowFileModel.model_validate(data).workflow.to_definition()

    return _ProjectBackedState()


class _Provisioner:
    """Creates and deletes tutorial projects on disk, and nothing else."""

    def create(self, plan: Any) -> Path:
        plan.path.mkdir(parents=True, exist_ok=True)
        (plan.path / "project.yaml").write_text(f"name: {plan.name}\n", encoding="utf-8")
        return Path(plan.path)

    def delete(self, key: Any, path: Path) -> None:
        import shutil

        if path.is_dir():
            shutil.rmtree(path)


def _block_types_in(written: Any) -> set[str]:
    """The block type names declared by the ``blocks/*.py`` files just written.

    The API layer's registry re-scan, reduced to what the conditions read.
    """
    import ast

    found: set[str] = set()
    for path in map(Path, written):
        if path.suffix != ".py" or path.parent.name != "blocks":
            continue
        for cls in (
            node for node in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(node, ast.ClassDef)
        ):
            for node in cls.body:
                if (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and node.target.id == "type_name"
                    and isinstance(node.value, ast.Constant)
                ):
                    found.add(str(node.value.value))
    return found


def test_the_whole_tutorial_walks_through_the_real_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every beat of the real manifest, driven end to end (#2082).

    The runtime, session store and progress store are the real ones; the
    product-state port is stood in exactly as the API layer stands it in, and
    reads the workflow off the project file the way the product does. Git
    state, runs, plots and interactions are set the way the product would set
    them after the reader's own action.
    """
    from datetime import UTC, datetime, timedelta

    from scistudio.tutorials import discovery
    from scistudio.tutorials.conditions import ExternalEventNames, RunSummary
    from scistudio.tutorials.discovery import DiscoveryEnvironment
    from scistudio.tutorials.progress import ProgressStore
    from scistudio.tutorials.projects import TutorialKey
    from scistudio.tutorials.session import SessionStatus, SessionStore, TutorialRuntime

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: TUTORIAL_DIR.parent)

    product = _project_backed_state()

    def _settle(written: Any) -> None:
        product.block_types = frozenset(set(product.block_types) | _block_types_in(written))

    def _record(name: str, target: str | None) -> None:
        product.events = product.events | {name}
        if target is not None:
            product.targeted_events = product.targeted_events | {(name, target)}

    def _forget() -> None:
        product.events = frozenset()
        product.targeted_events = frozenset()

    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        project_dir=lambda: product.project_dir,
        provisioner=_Provisioner(),
        environment=DiscoveryEnvironment(
            scistudio_version="0.3.1",
            git_available=True,
            # The level requires nothing: it lands what it needs itself. An
            # empty history is the harder case and the one this walks.
            completed_tutorials=frozenset(),
        ),
        progress=ProgressStore(fake_home / ".scistudio"),
        sessions=SessionStore(fake_home / ".scistudio"),
        open_replay=lambda surface: pytest.fail(f"tutorial 4 declares no replay, yet one opened on {surface!r}"),
        record_ui_event=_record,
        forget_ui_events=_forget,
        files_written=_settle,
    )

    def _run() -> None:
        # A millisecond past "now": a record stamped further ahead would satisfy
        # a later step's ``since_step_entry`` before the reader ran anything.
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

    def _waits_then(action: Any) -> None:
        """The step is not satisfied on arrival, and is after the reader's action."""
        assert _live(runtime.active_session()).satisfied is False
        result = action()
        # A trigger or a reported event answers with the session view; anything
        # else the reader did is judged by evaluating the step afresh.
        view = result if hasattr(result, "step") else runtime.evaluate_active()
        assert _live(view).satisfied is True

    def _event(name: str, target: str | None = None) -> Any:
        return lambda: runtime.report_ui_event(name, target)

    view = runtime.start(TutorialKey.core("two-modalities-one-answer"))
    assert view.step is not None and view.step.id == "todays-data"
    project = Path(view.project_path or "")
    product.project_dir = project
    product.branches = frozenset({"main"})
    product.current_branch = "main"

    raw = project / "data" / "raw"
    for sample in SAMPLES["er"]:
        for suffix in ("_he.png", "_mask.png", "_counts.csv"):
            assert (raw / f"{sample}{suffix}").is_file(), f"the bootstrap did not land {sample}{suffix}"
    for sample in SAMPLES["tnbc"]:
        assert not any(raw.glob(f"{sample}_*")), f"{sample} arrived before the branch that introduces it"
    assert set(LEVEL_BLOCKS) <= set(product.block_types), "the bootstrap settle registered the level's blocks"
    assert not (project / "workflows" / "main.yaml").exists(), "the workflow arrives with the step that runs it"

    # ----------------------------------------------------------- the ER tumors
    _advance("two-instruments-one-question")
    _advance("read-them-in")
    assert (project / "workflows" / "main.yaml").read_bytes() == (WORKFLOWS / "main.yaml").read_bytes()
    _waits_then(_run)

    _advance("look-at-them")
    _waits_then(_event("node_selected", "load_data"))
    _advance("open-a-mask")
    _waits_then(_event("preview_item_opened"))

    _advance("write-the-analysis")
    _waits_then(runtime.trigger_active)
    assert (project / "workflows" / "main.yaml").read_bytes() == (WORKFLOWS / "analysis.yaml").read_bytes()

    _advance("pair-them")

    def _pair() -> None:
        product.interactions = frozenset({"pair"})
        _run()

    _waits_then(_pair)

    _advance("read-the-answer")
    _waits_then(_event("node_selected", "compare_regions"))

    _advance("draw-the-plots")

    def _draw() -> None:
        runtime.trigger_active()
        # The API layer lists plots off plots/*/plot.yaml; the stand-in is told.
        product.plots = (("cancer_vs_rest", "compare", "genes"), ("shared_genes", "compare", "genes"))

    _waits_then(_draw)
    for plot_id in ("cancer_vs_rest", "shared_genes"):
        assert (project / "plots" / plot_id / "render.py").is_file()

    _advance("run-the-volcano")

    def _render(plot_id: str) -> Any:
        def action() -> None:
            product.rendered = (*product.rendered, ("main", "compare", "genes", plot_id))

        return action

    _waits_then(_render("cancer_vs_rest"))
    _advance("run-the-shared-genes")
    _waits_then(_render("shared_genes"))

    _advance("the-conclusion")
    _advance("name-the-note")

    def _new_note(name: str) -> Any:
        return lambda: (project / name).write_text("", encoding="utf-8")

    _waits_then(_new_note("conclusion.md"))
    _advance("write-it-down")
    assert (project / "conclusion.md").read_bytes() == (ASSETS / "notes" / "conclusion.md").read_bytes()

    # ------------------------------------------------------- the TNBC tumors
    _advance("two-new-tumors")
    _advance("commit-first")
    _waits_then(_event("git_committed"))
    _advance("see-the-er-setting")
    _waits_then(_event("node_selected", "compare_regions"))
    _advance("the-er-setting")

    _advance("make-a-branch")

    def _branch() -> None:
        product.branches = product.branches | {"tnbc"}
        assert _live(runtime.evaluate_active()).satisfied is False, "a branch that exists is not one you are on"
        product.current_branch = "tnbc"

    _waits_then(_branch)

    _advance("point-it-at-tnbc")
    _waits_then(runtime.trigger_active)
    for sample in SAMPLES["tnbc"]:
        assert (raw / f"{sample}_mask.png").is_file(), f"the press did not land {sample}"
    assert (raw / "CID4535_mask.png").is_file(), "the ER data stays beside the new tumors"

    _advance("see-what-changed")
    _waits_then(_event("node_selected", "compare_regions"))
    _advance("what-changed")

    _advance("run-tnbc")
    # The ER pairing left the `pair` marker set; the run is what is judged.
    assert "pair" in product.interactions_completed()
    _waits_then(_run)

    _advance("look-at-a-tnbc-mask")
    _waits_then(_event("node_selected", "load_data"))
    _advance("open-a-tnbc-mask")
    _waits_then(_event("preview_item_opened"))
    _advance("why-the-stroma")

    _advance("rerun-the-plots")
    # The ER figures still stand in the preview cache: the fact is already
    # true, and only the reader's own presses may satisfy this step.
    assert _live(runtime.active_session()).satisfied is False, "the standing figures must not satisfy a re-render"
    runtime.report_ui_event("plot_rendered", "cancer_vs_rest")
    assert _live(runtime.evaluate_active()).satisfied is False, "one of two plots is not both"
    assert _live(runtime.report_ui_event("plot_rendered", "shared_genes")).satisfied is True

    _advance("tnbc-conclusion")
    _advance("name-the-tnbc-note")
    _waits_then(_new_note("conclusion-tnbc.md"))
    _advance("write-the-tnbc-note")
    assert (project / "conclusion-tnbc.md").read_bytes() == (ASSETS / "notes" / "conclusion_tnbc.md").read_bytes()

    _advance("commit-tnbc")
    _waits_then(_event("git_committed"))

    _advance("switch-back")

    def _switch_back() -> None:
        product.current_branch = "main"

    _waits_then(_switch_back)
    _advance("see-the-er-setting-again")
    _waits_then(_event("node_selected", "compare_regions"))
    _advance("er-is-back")
    _advance("the-end")
    assert runtime.continue_active().status is SessionStatus.COMPLETE

    # This is a level, not the milestone: completing it must not offer the work
    # import (FR-079 names the AI level).
    assert runtime.progress_store.work_import_offer_pending() is False
