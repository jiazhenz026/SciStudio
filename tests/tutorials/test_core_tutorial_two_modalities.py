"""Core tutorial 4 — the multimodal, joint-analysis, git-branch level.

``test_core_tutorials.py`` already applies the format-level conformance every
shipped tutorial gets. This file checks what only tutorial 4 promises (#2082):

* the beat order and each beat's judged condition survive edits;
* the level owes nothing to any other level: its two picture types, the reader
  that turns a slide file into one, and their previewer are landed by its own
  bootstrap and register into its project at the project tier;
* the shipped data is what ``SOURCE.md`` says it is — the two ER tumors land at
  bootstrap, the two triple-negative ones wait for the branch, and each
  sample's slide, mask and count table describe the same spots;
* the pre-built workflow reads only files the bootstrap lands;
* the previewer says when it shows a sampled overview rather than every pixel;
* the story so far walks through the real runtime, beat by beat.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml
from PIL import Image

from scistudio.tutorials.actions import iter_file_actions
from scistudio.tutorials.manifest import TutorialManifest, TutorialSourceKind, load_manifest

from .conftest import say_text

REPO_ROOT = Path(__file__).resolve().parents[2]
TUTORIAL_DIR = REPO_ROOT / "src" / "scistudio" / "tutorials" / "core" / "two-modalities-one-answer"
ASSETS = TUTORIAL_DIR / "assets"
DATA = ASSETS / "data"

#: Which samples ship in which directory. The ER pair opens the level; the
#: triple-negative pair arrives when the subtype changes and the analysis
#: branches.
SAMPLES = {"er": ("CID4535", "CID4290"), "tnbc": ("CID44971", "CID4465")}
ALL_SAMPLES = tuple((subtype, sample) for subtype, samples in SAMPLES.items() for sample in samples)

GENE_PANEL_SIZE = 2000


@pytest.fixture(scope="module")
def manifest() -> TutorialManifest:
    return load_manifest(TUTORIAL_DIR, source_kind=TutorialSourceKind.CORE)


@pytest.fixture(scope="module")
def code(request: pytest.FixtureRequest) -> dict[str, ModuleType]:
    """The shipped code assets, imported the way the drop-in scans import them.

    The two type modules must land in ``sys.modules`` under their bare stems
    first, because the loader opens with ``from he_image import HEImage``: the
    exact import it performs in a project, where the types directory joins
    ``sys.path``.
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

    modules = {
        "he_image": load("he_image", "he_image.py"),
        "he_mask": load("he_mask", "he_mask.py"),
    }
    modules["loader"] = load("_scistudio_t4_loader", "load_slide_image.py")
    modules["preview"] = load("_scistudio_t4_preview", "image_preview.py")

    request.addfinalizer(lambda: [sys.modules.pop(name, None) for name in bound])
    return modules


def _file(subtype: str, sample: str, kind: str) -> Path:
    suffix = {"he": "_he.jpg", "mask": "_mask.png", "counts": "_counts.csv"}[kind]
    return DATA / subtype / f"{sample}{suffix}"


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
        ("two-instruments-one-question", None),
        ("read-them-in", {"run_succeeded"}),
        ("look-at-them", {"ui_event"}),
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


def test_what_the_level_does_not_teach_ships_at_bootstrap(manifest: TutorialManifest) -> None:
    """The ER data and the four picture files land before the first step.

    None of them is a lesson. Landing them here rather than pulling them from
    My Library is what lets the level be played first.
    """
    assert manifest.bootstrap is not None
    actions = list(iter_file_actions(manifest.bootstrap.do))
    assert {action.destination for action in actions} == {
        "data/raw",
        "types/he_image.py",
        "types/he_mask.py",
        "blocks/load_slide_image.py",
        "previewers/image_preview.py",
    }
    # Only the two ER tumors: the opening says "two" and means it.
    assert {action.source for action in actions if action.destination == "data/raw"} == {"assets/data/er"}


def test_the_workflow_arrives_prebuilt(manifest: TutorialManifest) -> None:
    """This is not a wiring lesson: the step that asks for Run writes the workflow itself."""
    step = next(step for step in manifest.steps if step.id == "read-them-in")
    assert [action.destination for action in iter_file_actions(step.do)] == ["workflows/main.yaml"]


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
        f"{sample}{suffix}" for sample in SAMPLES[subtype] for suffix in ("_he.jpg", "_mask.png", "_counts.csv")
    }
    assert {path.name for path in (DATA / subtype).iterdir()} == expected


@pytest.mark.parametrize("subtype", sorted(SAMPLES))
def test_the_spot_counts_source_md_quotes_are_the_shipped_ones(subtype: str) -> None:
    """The attribution file quotes a spot count per sample; the tables must agree."""
    quoted = {
        match.group(1): int(match.group(2).replace(",", ""))
        for match in re.finditer(r"^\| (CID\d+) \| \w+ \| ([\d,]+) \|$", (DATA / subtype / "SOURCE.md").read_text(), re.M)
    }
    assert set(quoted) == set(SAMPLES[subtype])
    for sample, spots in quoted.items():
        table = pd.read_csv(_file(subtype, sample, "counts"), usecols=["barcode"])
        assert len(table) == spots, f"{sample}: SOURCE.md quotes {spots} spots, the table has {len(table)}"


def test_every_table_carries_the_same_gene_panel() -> None:
    """One shared panel, so a comparison across tumors compares the same genes."""
    headers = {sample: list(pd.read_csv(_file(subtype, sample, "counts"), nrows=0).columns) for subtype, sample in ALL_SAMPLES}
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


def test_the_prebuilt_workflow_reads_only_what_the_bootstrap_lands() -> None:
    """Every Load path names a file the bootstrap copied into ``data/raw``."""
    from scistudio.workflow.schema import WorkflowFileModel

    document = yaml.safe_load((ASSETS / "workflows" / "main.yaml").read_text(encoding="utf-8"))
    WorkflowFileModel.model_validate(document)
    landed = {f"data/raw/{path.name}" for path in (DATA / "er").iterdir()}
    loads = [node for node in document["workflow"]["nodes"] if node["block_type"] == "load_data"]
    assert {node["config"]["params"]["core_type"] for node in loads} == {"HEImage", "HEMask", "DataFrame"}
    for node in loads:
        paths = node["config"]["params"]["path"]
        assert set(paths) <= landed, f"{node['id']} reads a file the bootstrap does not land"


# ---------------------------------------------------------------------------
# The reader and the previewer
# ---------------------------------------------------------------------------


def test_the_loader_claims_jpeg_and_png_for_both_picture_types(code: dict[str, ModuleType]) -> None:
    capabilities = code["loader"].LoadSlideImage.format_capabilities
    assert {(capability.data_type.__name__, capability.format_id) for capability in capabilities} == {
        ("HEImage", "jpeg"),
        ("HEImage", "png"),
        ("HEMask", "jpeg"),
        ("HEMask", "png"),
    }


@pytest.mark.parametrize(
    ("kind", "capability_id", "type_name"),
    [
        ("he", "tutorial.he_image.jpeg.load", "HEImage"),
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


def _preview_request(*, truncated: bool) -> SimpleNamespace:
    """A request whose reader hands back one small RGB plane per channel."""
    plane = SimpleNamespace(
        matrix=[[10, 20], [30, 40]],
        shape=[1000, 1000, 3],
        axes=["y", "x", "c"],
        dtype="uint8",
        truncated=truncated,
    )
    return SimpleNamespace(
        storage=object(),
        spec=SimpleNamespace(previewer_id="project.heimage.view"),
        target=None,
        data_access=SimpleNamespace(array_plane=lambda storage, slice_index=0: plane),
    )


@pytest.mark.parametrize("truncated", [True, False])
def test_the_previewer_says_when_it_shows_an_overview(code: dict[str, ModuleType], truncated: bool) -> None:
    """A sampled picture must never be presented as the data itself (#1886)."""
    envelope = code["preview"].render_image(_preview_request(truncated=truncated))
    assert envelope.metadata.sampled is truncated
    assert envelope.metadata.complete is (not truncated)
    assert ("sampled overview" in envelope.payload["alt"]) is truncated


# ---------------------------------------------------------------------------
# What the bootstrap lands, registered end to end
# ---------------------------------------------------------------------------


def test_the_landed_artifacts_register_into_the_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The four files the bootstrap writes have to become real product state.

    The Load block's core_type list has to offer ``HEImage`` and ``HEMask``,
    dispatch has to find the slide reader, and the preview panel has to draw a
    slide as a picture rather than as a table of numbers. The previewer derives
    its tier from where it sits (#2125), so landed in the project's own
    ``previewers/`` it must register at the project tier.
    """
    import shutil

    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core import dropins
    from scistudio.core.types.registry import TypeRegistry
    from scistudio.previewers.models import OwnerKind
    from scistudio.previewers.project import load_project_previewers
    from scistudio.previewers.registry import PreviewerRegistry

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
    for child in ("types", "blocks", "previewers"):
        (project / child).mkdir(parents=True, exist_ok=True)
    (project / "project.yaml").write_text("name: Two Modalities\n", encoding="utf-8")
    for child, source in (
        ("types", "he_image.py"),
        ("types", "he_mask.py"),
        ("blocks", "load_slide_image.py"),
        ("previewers", "image_preview.py"),
    ):
        shutil.copy(ASSETS / "code" / source, project / child / source)

    types = TypeRegistry()
    dropins.register_type_scan_dirs(types, project)
    types.scan_all()
    assert {"HEImage", "HEMask"} <= set(types.all_types()), "the picture types the Loads ask for did not register"

    blocks = BlockRegistry()
    dropins.register_block_scan_dirs(blocks, project)
    blocks.scan()
    assert blocks.get_spec("load_slide_image") is not None, "the slide reader did not register"

    previewers = PreviewerRegistry()
    previewers.load_core()
    load_project_previewers(previewers, project)
    for type_name in ("HEImage", "HEMask"):
        claimed = [spec for spec in previewers.all_specs() if spec.target_type == type_name]
        assert claimed, f"no previewer claims {type_name}, so it previews as a number table"
        assert {spec.owner_kind for spec in claimed} == {OwnerKind.PROJECT}


# ---------------------------------------------------------------------------
# The story so far, walked through the real runtime
# ---------------------------------------------------------------------------


def test_the_story_so_far_walks_through_the_real_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every beat of the real manifest, driven end to end (#2082).

    The runtime, session store and progress store are the real ones; the
    product-state port is stood in exactly as the API layer stands it in. A
    reader who has finished nothing else arrives on a project that already
    holds the ER data and every picture file, receives the workflow built, and
    is judged on their own Run and their own click.
    """
    import ast
    import shutil
    from datetime import UTC, datetime, timedelta

    from scistudio.tutorials import discovery
    from scistudio.tutorials.conditions import ExternalEventNames, RunSummary
    from scistudio.tutorials.discovery import DiscoveryEnvironment
    from scistudio.tutorials.progress import ProgressStore
    from scistudio.tutorials.projects import TutorialKey, TutorialProjectPlan
    from scistudio.tutorials.session import SessionStatus, SessionStore, TutorialRuntime

    from .conftest import StubProductState

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: TUTORIAL_DIR.parent)

    class _Provisioner:
        def create(self, plan: TutorialProjectPlan) -> Path:
            plan.path.mkdir(parents=True, exist_ok=True)
            (plan.path / "project.yaml").write_text(f"name: {plan.name}\n", encoding="utf-8")
            return plan.path

        def delete(self, key: TutorialKey, path: Path) -> None:
            if path.is_dir():
                shutil.rmtree(path)

    product = StubProductState()

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

    view = runtime.start(TutorialKey.core("two-modalities-one-answer"))
    assert view.step is not None and view.step.id == "two-instruments-one-question"
    project = Path(view.project_path or "")
    product.project_dir = project

    raw = project / "data" / "raw"
    for sample in SAMPLES["er"]:
        for suffix in ("_he.jpg", "_mask.png", "_counts.csv"):
            assert (raw / f"{sample}{suffix}").is_file(), f"the bootstrap did not land {sample}{suffix}"
    for sample in SAMPLES["tnbc"]:
        assert not any(raw.glob(f"{sample}_*")), f"{sample} arrived before the branch that introduces it"
    for landed in ("types/he_image.py", "types/he_mask.py", "blocks/load_slide_image.py", "previewers/image_preview.py"):
        assert (project / landed).is_file(), f"the bootstrap did not land {landed}"
    assert "load_slide_image" in product.block_types, "the bootstrap settle registered the slide reader"
    assert not (project / "workflows" / "main.yaml").exists(), "the workflow arrives with the step that runs it"

    _advance("read-them-in")
    written = project / "workflows" / "main.yaml"
    assert written.read_bytes() == (ASSETS / "workflows" / "main.yaml").read_bytes()
    assert _live(runtime.active_session()).satisfied is False, "the written workflow is not the run"
    _run()
    assert _live(runtime.evaluate_active()).satisfied is True

    _advance("look-at-them")
    assert _live(runtime.active_session()).satisfied is False, "the run alone is not the look"
    assert _live(runtime.report_ui_event("node_selected", "load_data")).satisfied is True

    assert runtime.continue_active().status is SessionStatus.COMPLETE
    # This is a level, not the milestone: completing it must not offer the work
    # import (FR-079 names the AI level).
    assert runtime.progress_store.work_import_offer_pending() is False
