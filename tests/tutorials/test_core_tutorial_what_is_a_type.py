"""Core tutorial 2 — the type-system level — held to its own claims.

``test_core_tutorials.py`` already applies the format-level conformance every
shipped tutorial gets. This file checks what only tutorial 2 promises
(#2081, #2135, scenarios doc 关卡 2):

* the beat order and each beat's judged condition survive edits;
* the three plot twists are real: the capability error the reader hits is the
  product's own dispatch message, quoted verbatim in the step text; the
  number-table beat rests on Image genuinely subclassing Array; and the
  segmentation's imperfection is recomputed from the shipped micrographs every
  run — twelve objects for eleven cells at the fixed threshold, because an
  18-pixel speck of debris on the first slide crosses it too, and 195 plus 248
  objects with the adaptive method, which is the "worse" the copy claims;
* the shipped TIFFs are deterministic: the test regenerates both from the
  recorded recipe and requires pixel equality, so the data cannot drift from
  the numbers;
* the interactive block is a *real* interactive block — mixin, execution
  mode, panel manifest with a served module URL and a path-confined
  ``asset_root`` beside the block — and its panel is the shipped, hand-written
  ES module implementing the ADR-051 PanelModule contract;
* the panel registers for ``Image`` and paints the pixels as an
  indexed-color PNG, and it derives its tier from where it sits, so the same
  file works in the project and, after "Move to My Library", in the library's
  user-tier slot;
* the whole tutorial walks through the real runtime, beat by beat.

The level was rewritten to the owner's design in #2135: it now ships two
micrographs rather than one so the loader step can teach batch processing, it
wires both workflows for the reader instead of asking them to drag and connect
(tutorial 1 already taught that), and it ends at the areas table rather than at
a Save block. Everything in this file describes that level; nothing in it
should be read as a request to change it.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

import numpy as np
import pytest
import yaml

from scistudio.blocks.base import BlockConfig
from scistudio.core.types import Collection
from scistudio.tutorials.actions import iter_file_actions
from scistudio.tutorials.manifest import TutorialManifest, TutorialSourceKind, load_manifest

from .conftest import say_text

TUTORIAL_DIR = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials" / "core" / "what-is-a-type"
ASSETS = TUTORIAL_DIR / "assets"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# The recipe behind the two shipped micrographs, in full
# ---------------------------------------------------------------------------
#
# The two TIFFs are committed as binaries, so their provenance has to be
# executable: this recipe rebuilds both from the archived sources and the test
# below requires pixel equality. Editing the data without editing the recipe
# fails there, which is what keeps every count the tutorial text stands on
# honest.
#
# The sources are two generated fluorescence micrographs, archived at the
# tutorial's ``sources/`` — *outside* ``assets/``, because everything under
# ``assets/data`` is copied into the reader's project by the bootstrap and the
# sources are provenance, not something a reader should find in data/raw. They
# are 768px greyscale PNGs. They were made with
# an image model from a prompt asking for cultured mammalian cells seen straight
# down the objective: irregular outlines, a brighter membrane rim, mottled
# cytoplasm carrying bright punctate organelles, an off-centre nucleus, uneven
# illumination falling towards one corner, out-of-focus haze, and sensor noise.
# Six cells on the first, five on the second, and the second explicitly free of
# debris. A generated image is not reproducible from its prompt, so the *source*
# is archived rather than the prompt: from those two PNGs everything below is
# deterministic, and NumPy is the only thing it needs.
#
# What the recipe does to them, and why each step is there:
#
# * **Downsample to 200x200 by box averaging.** The level's grid, and the
#   averaging also puts the model's high-frequency artefacts below the pixel.
# * **Flat-field.** The illumination falls off hard enough towards one corner
#   that a global threshold joins three cells to the background before it
#   finds the fourth. Most of that gradient is estimated (a wide minimum
#   filter, blurred) and subtracted; a quarter of it is deliberately left, so
#   the adaptive method still has something to be adaptive about. This is the
#   first step of any real micrograph pipeline, not a fix for these two files.
# * **Gain.** Scales the flattened image so the block's default threshold of 70
#   is the right cut-off, rather than moving the default to suit the data.
# * **One speck of debris, on the first slide only.** Placed at the point
#   furthest from any cell, at 89 pixels — over the block's minimum area, and
#   fourteen times smaller than the smallest cell. The threshold picks it up as
#   a seventh object, and removing it by hand is the entire reason the
#   interactive block exists. It is drawn rather than found because "a speck
#   that clears the threshold and is unmistakably not a cell" is a property the
#   level's plot depends on, not one an image model can be asked for.
_SHAPE = (200, 200)
_SOURCES = {"cells_01.tif": "cells_01_source.png", "cells_02.tif": "cells_02_source.png"}

#: Background estimate: the minimum over this window, then a mean over this radius.
_FLAT_WINDOW = 25
_FLAT_BLUR = 12
#: How much of the estimated gradient to remove. Below 1.0 on purpose — see above.
_FLAT_STRENGTH = 0.75
#: Scales the flattened image to the block's default threshold.
_GAIN = 1.4
#: (y, x, radius, amplitude) of the drawn speck, on the first slide only.
_SPECK_ONE = (128, 170, 5.6, 120.0)

#: Which micrograph each shipped file is, in the order the tutorial loads them.
_SLIDES = {"cells_01.tif": 1, "cells_02.tif": 2}

# The numbers the tutorial's copy and this file both stand on, recomputed from
# the shipped assets by the tests below rather than trusted from a note. Slide
# one holds six cells and the speck; slide two holds five cells and nothing
# else, which is why the speck is a *find*, not a fixture of every image. The
# speck is label 6 because labels are handed out in scan order.
_THRESHOLD_AREAS = {
    "cells_01.tif": {1: 1780, 2: 1612, 3: 2023, 4: 1644, 5: 1423, 6: 89, 7: 2020},
    "cells_02.tif": {1: 1376, 2: 1181, 3: 1342, 4: 1607, 5: 1448},
}
_ADAPTIVE_COUNTS = {"cells_01.tif": 13, "cells_02.tif": 6}
_SPECK_LABEL = 6
_CELL_COUNTS = {"cells_01.tif": 6, "cells_02.tif": 5}


def _minimum_filter(field: np.ndarray, size: int) -> np.ndarray:
    """The minimum over a square window, separably, so the recipe needs only NumPy.

    A minimum estimates the background where a mean cannot: a mean over a
    window that contains a cell is pulled up by the cell, and subtracting that
    would carve a hole where the cell is.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    pad = size // 2
    padded = np.pad(field, pad, mode="edge")
    rows = sliding_window_view(padded, size, axis=0).min(axis=-1)
    return np.asarray(sliding_window_view(rows, size, axis=1).min(axis=-1))


def _box_mean(field: np.ndarray, radius: int) -> np.ndarray:
    """The mean over a square window, via a summed-area table.

    The same function the block's adaptive method uses (``_local_mean`` in
    ``segment_cells.py``), repeated here rather than imported: this recipe is
    the data's provenance and must not shift when a block is edited.
    """
    padded = np.pad(field, radius + 1, mode="edge")
    table = padded.cumsum(axis=0).cumsum(axis=1)
    size = 2 * radius + 1
    height, width = field.shape
    y0, x0 = np.mgrid[0:height, 0:width]
    y1, x1 = y0 + size, x0 + size
    total = table[y1, x1] - table[y0, x1] - table[y1, x0] + table[y0, x0]
    return np.asarray(total / float(size * size))


def _expected_micrograph(filename: str) -> np.ndarray:
    """Rebuild one shipped TIFF from its archived source, as a uint8 array."""
    from PIL import Image as PILImage

    source = PILImage.open(TUTORIAL_DIR / "sources" / _SOURCES[filename])
    height, width = _SHAPE
    pixels = np.asarray(source.resize((width, height), PILImage.BOX)).astype(float)

    background = _box_mean(_minimum_filter(pixels, _FLAT_WINDOW), _FLAT_BLUR)
    flat = np.clip((pixels - _FLAT_STRENGTH * (background - background.mean())) * _GAIN, 0, 255)

    if _SLIDES[filename] == 1:
        cy, cx, radius, amplitude = _SPECK_ONE
        yy, xx = np.mgrid[0:height, 0:width]
        speck = np.clip((radius - np.hypot(yy - cy, xx - cx)) / 1.5, 0, 1) ** 0.6
        flat = np.clip(flat + speck * amplitude, 0, 255)

    return np.rint(flat).astype(np.uint8)


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


def _shipped_image(assets: dict[str, ModuleType], filename: str = "cells_01.tif") -> Any:
    return assets["loader"].LoadTiffImage().load_file(ASSETS / "data" / filename, {})


def _threshold_labels(assets: dict[str, ModuleType], filename: str = "cells_01.tif") -> Any:
    block = assets["segment"].SegmentCellsBlock()
    return block.process_item(_shipped_image(assets, filename), BlockConfig(params={}))


def _label_plane(image: Any) -> np.ndarray:
    """The label channel of a Segment Cells output.

    The block emits two channels on one grid — the micrograph it read on
    ``c=0``, the labels on ``c=1`` — so the panel can draw one over the
    other. Anything counting objects wants the second. Counting the array whole
    would count grey levels as label ids.
    """
    data = np.asarray(image.to_memory())
    return data[-1] if data.ndim == 3 else data


def _label_areas(labels: np.ndarray) -> dict[int, int]:
    """Every label in the map with its pixel count, background excluded."""
    return {int(label): int((labels == label).sum()) for label in np.unique(labels) if label != 0}


# ---------------------------------------------------------------------------
# The beat map
# ---------------------------------------------------------------------------


def _judged_terms(step: Any) -> tuple[str, ...] | None:
    """The step's judged terms, in declaration order, or ``None`` when it judges nothing.

    A list rather than a set, deliberately. ``Condition.terms()`` returns a
    frozenset because the session layer only needs to know which events can
    change the answer — but two ``config_matches`` under an ``all`` collapse to
    one entry there, and this file has a step whose whole point is that it
    carries exactly two of them. Walking the tree keeps the count visible.
    """
    if step.done_when is None:
        return None

    def walk(condition: Any) -> list[str]:
        if condition.is_combinator:
            return [term for operand in condition.operands for term in walk(operand)]
        return [condition.term]

    return tuple(walk(step.done_when))


def test_the_beat_map_is_the_designed_one(manifest: TutorialManifest) -> None:
    """Beat -> step -> condition, as dispatched. A reorder or a swapped judge fails here.

    The level is cut into dialogue beats rather than paragraphs, which is why
    this list is longer than the list of things the reader actually does. A step
    that declares ``auto_advance`` leaves the instant its condition is met, so a
    payoff written after the instruction would never be read; every payoff
    therefore opens the *following* step, and those reading steps judge nothing
    (``None`` below). The pairing is load-bearing in both directions, and this
    is the test that catches it going wrong: folding a payoff back into the step
    that instructs would hide the payoff, and giving a reading step a condition
    would take away the one pace only the reader can set.

    Two entries carry more than one term and neither is incidental.
    ``browse-to-the-image`` judges two ``config_matches`` under an ``all``,
    one per file: a multi-file ``path`` holds a list, each entry is judged on
    its own, and one term would let a reader who picked a single file walk on
    from a step whose whole subject is loading both. ``try-another-method``
    pairs the config change with the run, because seeing the adaptive result is
    the lesson and setting the dropdown is not.
    """
    expected = [
        ("a-task-arrives", None),
        ("create-the-image-type", ("file_exists",)),
        ("make-it-image", ("type_registered",)),
        ("add-load", ("node_exists",)),
        ("select-the-load-block", ("ui_event",)),
        ("browse-to-the-image", ("config_matches", "config_matches")),
        ("say-it-is-an-image", ("config_equals",)),
        ("run-into-the-wall", ("run_failed",)),
        ("read-the-capability-error", None),
        ("teach-it-to-load", ("file_exists",)),
        ("set-the-capability", ("config_matches",)),
        ("run-it-again", ("run_succeeded",)),
        ("look-at-the-numbers", ("ui_event",)),
        ("why-numbers", ("previewer_registered",)),
        ("look-again", ("ui_event",)),
        ("open-the-rendered-image", ("ui_event",)),
        ("segment-the-cells", ("file_exists",)),
        ("wired-for-you", ("run_succeeded",)),
        ("look-at-the-labels", ("ui_event",)),
        ("open-the-first-slide", ("ui_event",)),
        ("try-another-method", ("ui_event",)),
        ("switch-to-adaptive", ("config_equals",)),
        ("run-the-adaptive-method", ("run_succeeded",)),
        ("open-the-adaptive-result", ("ui_event",)),
        ("back-to-threshold", ("config_equals",)),
        ("blocks-can-be-interactive", ("file_exists",)),
        ("run-with-review", ("interaction_completed",)),
        ("look-at-the-areas", ("ui_event",)),
        ("open-the-first-table", ("ui_event",)),
        ("a-dataframe-of-areas", None),
        ("save-the-type", ("library_contains",)),
        ("save-the-block", ("library_contains",)),
        ("save-the-previewer", None),
        ("a-histogram-for-your-labmate", ("plot_exists",)),
        ("run-the-histogram", ("ui_event",)),
        ("export-the-histogram", ("ui_event",)),
        ("what-a-type-is", None),
    ]
    actual = [(step.id, _judged_terms(step)) for step in manifest.steps]
    assert actual == expected


def test_the_two_file_step_names_both_micrographs(manifest: TutorialManifest) -> None:
    """``browse-to-the-image`` requires *both* files, and names the ones that ship.

    The beat map above proves the step carries two terms; this proves the two
    terms are the two files the bootstrap actually lands. A step that asked for
    ``cells.tif`` — the single micrograph this level used to ship — would still
    have two terms and would still read as a batch-processing lesson, while
    being unsatisfiable in the project the reader is sitting in.
    """
    step = manifest.step_by_id("browse-to-the-image")
    assert step is not None and step.done_when is not None
    condition = step.done_when
    assert condition.term == "all"
    patterns = [str(operand.args["pattern"]) for operand in condition.operands]
    assert patterns == ["data/raw/cells_01.tif", "data/raw/cells_02.tif"]
    for filename in _SLIDES:
        assert (ASSETS / "data" / filename).is_file(), f"the step asks for {filename}, which must ship"
    said = say_text(step)
    for filename in _SLIDES:
        assert filename in said, "the copy names the files the condition judges"


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


def test_the_we_write_it_beats_write_what_their_step_teaches(manifest: TutorialManifest) -> None:
    """Every asset this level writes into the project, and when it lands.

    Two kinds, and the difference is the reader's hand. A **trigger** is a
    button in the dialogue: the four teaching files arrive because the reader
    pressed "write it for me", which is the beat where the level hands over
    code it does not want them to type. An **entry action** lands the moment
    the step opens, before its first line is readable, and is reserved for
    material that has to already be there for the step's own text to make sense
    — the Image type the reader is asked to *look at*, and the two workflows
    the level wires on the reader's behalf.

    Wiring is the change #2135 made to this list. Tutorial 1 already taught
    dragging and connecting, so this level writes the graph instead of asking
    for it, twice: once with the segmentation joined on, and once more with the
    interactive block after it. Both write over ``workflows/main.yaml``, which
    is why a stale expectation here would go unnoticed — the second write would
    simply replace the first and no step would fail.
    """
    triggered = {
        step.id: {action.destination for action in iter_file_actions(step.trigger.do)}
        for step in manifest.steps
        if step.trigger is not None
    }
    assert triggered == {
        "teach-it-to-load": {"blocks/load_tiff_image.py"},
        "why-numbers": {"previewers/image_preview.py"},
        "segment-the-cells": {"blocks/segment_cells.py"},
        # The panel lands under the project's ``panels/`` root, named for the id
        # its declaration carries: that is where four-tier discovery looks, and
        # a directory beside the block would never be found (ADR-054 spec 1).
        "blocks-can-be-interactive": {"blocks/review_labels.py", "panels/tutorial.review_labels"},
        "a-histogram-for-your-labmate": {"plots/cell_size_histogram"},
    }

    on_entry = {
        step.id: {(action.source, action.destination) for action in iter_file_actions(step.do)}
        for step in manifest.steps
        if step.do
    }
    assert on_entry == {
        "make-it-image": {("assets/code/image.py", "types/image.py")},
        "wired-for-you": {("assets/workflows/load-and-segment.yaml", "workflows/main.yaml")},
        "run-with-review": {("assets/workflows/with-review.yaml", "workflows/main.yaml")},
    }


def test_the_wired_workflows_keep_the_choices_the_reader_made(manifest: TutorialManifest) -> None:
    """Overwriting ``main.yaml`` must not take back a decision the level asked for.

    Three steps make the reader configure the Load block — both files, the
    Image type, the TIFF capability — and then ``wired-for-you`` writes a whole
    workflow over the file those choices live in. If the shipped asset spelled
    any of them differently, the reader would watch their own work silently
    revert, and the step after it would judge a value they never chose. So the
    asset's Load node is held against the conditions of the steps that came
    before it, term by term.
    """
    shipped = yaml.safe_load((ASSETS / "workflows" / "load-and-segment.yaml").read_text(encoding="utf-8"))
    load_node = next(node for node in shipped["workflow"]["nodes"] if node["block_type"] == "load_data")
    params = load_node["config"]["params"]

    browse = manifest.step_by_id("browse-to-the-image")
    assert browse is not None and browse.done_when is not None
    assert params["path"] == [str(operand.args["pattern"]) for operand in browse.done_when.operands]

    typed = manifest.step_by_id("say-it-is-an-image")
    assert typed is not None and typed.done_when is not None
    assert str(typed.done_when.args["key"]) == "core_type"
    assert params["core_type"] == typed.done_when.args["value"]

    # The capability is deliberately NOT written into the asset. A drop-in
    # block's id carries the source file's mtime, so any literal here would
    # name a capability that does not exist on the reader's machine and the
    # wired run would fail to dispatch. Leaving it out lets the same resolution
    # that answered the reader's own selection answer this one.
    assert "capability_id" not in params, (
        "an mtime-stamped id cannot be shipped; dispatch resolves (Image, .tif) instead"
    )

    # The review workflow inherits the same node, so the same holds after the
    # second rewrite — the interactive block joins the graph, nothing else moves.
    with_review = yaml.safe_load((ASSETS / "workflows" / "with-review.yaml").read_text(encoding="utf-8"))
    reviewed_load = next(node for node in with_review["workflow"]["nodes"] if node["block_type"] == "load_data")
    assert reviewed_load == load_node


def test_the_promotion_bridge_judges_the_type_and_the_block(manifest: TutorialManifest) -> None:
    """The ending judges two of the three promotions, and says why the third is not judged.

    Tutorial 3 stands on all three — its fresh project finds Image, Segment
    Cells, and the Image panel already in the library — but only two of the
    three moves are things ``library_contains`` can see. The Panels tab's
    card offers Auto / This project / All projects, which records *scope*
    rather than moving the file, so the panel step asks for something the
    term cannot judge and is deliberately left unjudged with a TODO explaining
    the gap.

    This test exists so that stays a decision rather than an accident. Dropping
    the panel step's condition without the TODO, or quietly re-judging it
    on a term the step does not ask for, both fail here.
    """
    judged: list[tuple[str, str]] = []
    for step in manifest.steps:
        if step.done_when is None or "library_contains" not in step.done_when.terms():
            continue
        condition = step.done_when
        assert not condition.is_combinator
        judged.append((str(condition.args["kind"]), str(condition.args["name"])))
    assert judged == [("type", "Image"), ("block", "segment_cells")]

    panel_step = manifest.step_by_id("save-the-previewer")
    assert panel_step is not None
    assert panel_step.done_when is None, "the panel promotion is unjudged on purpose; see the TODO"
    assert "All projects" in say_text(panel_step), "the step still asks for the Previewers tab's own control"

    source = (TUTORIAL_DIR / "tutorial.yaml").read_text(encoding="utf-8")
    assert "TODO(#2135)" in source, "an unjudged step must carry the tracked reason it is unjudged"
    assert "it does not move the file into the library" in source, "the TODO must say why the term cannot judge it"


def test_the_library_step_states_the_real_library_consequence(manifest: TutorialManifest) -> None:
    """FR-072: the save-to-library lesson names what the action does beyond this project.

    The requirement exists because an action whose real consequence the reader
    never observes teaches nothing: they would learn a menu item, not what it
    does to their machine. The copy carries it as the contrast between the two
    scopes — the type lives in *this* project until it is moved, after which it
    is available in *every* project the reader opens — so both halves are
    asserted, not just the reassuring one.
    """
    step = manifest.step_by_id("save-the-type")
    assert step is not None and step.say
    said = say_text(step)
    assert "only this project" in said, "the before state: a project-tier type is invisible everywhere else"
    assert "personal library" in said and "every project you open" in said, "the after state, in the reader's terms"


# ---------------------------------------------------------------------------
# The three plot twists are real
# ---------------------------------------------------------------------------


def test_the_capability_error_is_quoted_verbatim(manifest: TutorialManifest) -> None:
    """The step that reads the error quotes the product's own dispatch message, not a paraphrase.

    Hitting the wall and reading the wall are two beats now: ``run-into-the-wall``
    only presses Run, and the quote lives on the reading step that opens next,
    because a line written under an ``auto_advance`` instruction is never seen.
    So the quote is held against the dispatch source on the step where the
    reader actually reads it, which is what catches the product's message being
    reworded while the tutorial goes on claiming to show it verbatim.
    """
    from scistudio.blocks.io import _unified_dispatch

    step = manifest.step_by_id("read-the-capability-error")
    assert step is not None and step.say
    quoted = "no load capability is registered for type"
    assert quoted in say_text(step)
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


def test_the_image_type_is_the_array_subclass_the_step_describes(
    manifest: TutorialManifest, assets: dict[str, ModuleType]
) -> None:
    """``make-it-image`` describes the file it just wrote; the file must match the description.

    The step used to ask the reader to uncomment two color lines by hand, and
    this test used to hold the asset to having them there to uncomment. #2135
    took the edit away — the level spends its attention on the type system, not
    on CSS — and the rewritten step dropped the color sentence with it. What
    the reader is now told about code they only read is one claim: an Image is
    a subclass of Array.

    That claim is checked against the mechanism that produces it. Subclassing
    is what makes an Image acceptable anywhere an Array is, which is the whole
    reason the core Array panel can render one at all.
    """
    from scistudio.core.types import Array

    source = (ASSETS / "code" / "image.py").read_text(encoding="utf-8")
    assert "class Image(Array):" in source, "the reader is told they are looking at a subclass of Array"

    image_cls = assets["image"].Image
    assert image_cls.__mro__[1] is Array, "Array is the immediate base the step names"

    step = manifest.step_by_id("make-it-image")
    assert step is not None and step.say
    said = say_text(step)
    assert "subtype of Array" in said or "subclass of Array" in said


def test_the_shipped_tiffs_match_their_recorded_recipe() -> None:
    """Both committed binaries regenerate bit-for-bit, so the numbers cannot drift.

    This is the hinge the rest of the file hangs on. Every count below — seven
    objects on the first slide, five on the second, thirteen and ten with the
    adaptive method — is a fact about these exact pixels, and the tutorial's
    copy narrates those counts. Rebuilding the data from a different source, a
    different flat-field, or a moved speck would change the counts silently; it
    cannot, because it fails here first.
    """
    import tifffile

    for filename in _SLIDES:
        shipped = np.asarray(tifffile.imread(ASSETS / "data" / filename))
        assert shipped.dtype == np.uint8 and shipped.shape == _SHAPE, filename
        np.testing.assert_array_equal(shipped, _expected_micrograph(filename), err_msg=filename)


def test_the_loader_reads_both_tiffs_as_images(assets: dict[str, ModuleType]) -> None:
    """The hand-written baseline reader agrees byte-for-byte with tifffile, on both slides.

    Core forbids ``import tifffile`` under ``src/scistudio`` (the decoder
    belongs to imaging packages — ``test_version_alignment`` pins it), so the
    shipped loader reads the TIFF contract itself with the standard library.
    tifffile is a dev-extra here, which makes it this test's independent
    referee: both readers must produce the same pixels.

    Both files are read because the level loads both in one batch, and a reader
    that happened to work on the first and not the second would fail the
    tutorial at its Run step rather than here.
    """
    import tifffile

    for filename in _SLIDES:
        image = _shipped_image(assets, filename)
        assert isinstance(image, assets["image"].Image)
        assert image.axes == ["y", "x"]
        pixels = image.to_memory()
        assert pixels.shape == _SHAPE and pixels.dtype == np.uint8
        np.testing.assert_array_equal(pixels, np.asarray(tifffile.imread(ASSETS / "data" / filename)))
    loader_source = (ASSETS / "code" / "load_tiff_image.py").read_text(encoding="utf-8")
    assert "tifffile" not in loader_source, "the shipped loader must not lean on the dev-only decoder"


def test_the_loader_declares_exactly_the_missing_capability(assets: dict[str, ModuleType]) -> None:
    """The declaration is the lesson: (Image, tiff, .tif/.tiff), load direction."""
    capabilities = assets["loader"].LoadTiffImage.get_format_capabilities()
    assert len(capabilities) == 1
    capability = capabilities[0]
    assert capability.direction == "load"
    assert capability.data_type is assets["image"].Image
    assert capability.format_id == "tiff"
    assert set(capability.extensions) == {".tif", ".tiff"}


def test_the_capability_the_step_asks_for_is_the_one_the_loader_mints(
    manifest: TutorialManifest, assets: dict[str, ModuleType]
) -> None:
    """``set-the-capability`` judges an id nobody types by hand; it must be the real one.

    SimpleLoader mints a capability id out of four facts — the module the block
    lives in, its class name, the direction, and the format id. Three of those
    are stable; the module is not. A drop-in block is imported under a synthetic
    name the scanner invents from the file's stem *and its modification time*
    (``_scistudio_dropin_load_tiff_image_1787593641``), so the id differs on
    every machine and changes again every time the file is rewritten. A literal
    in the manifest could therefore never match, and the step would refuse to
    advance while the reader stared at the right entry selected in the format
    dropdown.

    So the step matches a glob over the stable tail, and this test holds that
    glob against an id the loader really mints — the class, the direction, and
    the format, in that order. A rename anywhere in the loader fails here rather
    than in front of a reader.
    """
    step = manifest.step_by_id("set-the-capability")
    assert step is not None and step.done_when is not None
    assert step.done_when.term == "config_matches", "an mtime-stamped id cannot be compared for equality"
    pattern = str(step.done_when.args["pattern"])

    minted = assets["loader"].LoadTiffImage.get_format_capabilities()[0].id
    assert PurePosixPath(minted).match(pattern), (
        f"the step's pattern {pattern!r} does not match the id the loader mints, {minted!r}"
    )
    assert pattern.startswith("*."), "only the module segment is unknowable; the rest must be pinned"
    assert pattern[2:] == ".".join(minted.split(".")[1:]), "the pinned tail is the class, the direction and the format"


def test_the_loader_refuses_what_it_does_not_read(tmp_path: Path, assets: dict[str, ModuleType]) -> None:
    """Outside the narrow contract, the reader refuses by name instead of guessing."""
    import tifffile

    loader = assets["loader"].LoadTiffImage()

    stack = tmp_path / "stack.tif"
    tifffile.imwrite(stack, np.zeros((3, 8, 8), dtype=np.uint8), photometric="minisblack")
    with pytest.raises(ValueError, match="single 2-D plane"):
        loader.load_file(stack, {})

    compressed = tmp_path / "compressed.tif"
    tifffile.imwrite(compressed, np.zeros((8, 8), dtype=np.uint8), compression="zlib")
    with pytest.raises(ValueError, match="uncompressed"):
        loader.load_file(compressed, {})

    not_tiff = tmp_path / "notes.tif"
    not_tiff.write_bytes(b"just some text pretending")
    with pytest.raises(ValueError, match="byte-order mark"):
        loader.load_file(not_tiff, {})


def test_the_threshold_run_finds_twelve_objects_eleven_cells(assets: dict[str, ModuleType]) -> None:
    """Eleven cells across the two slides, twelve objects — and the twelfth is the speck.

    This is the level's third plot twist, and it is not staged: the threshold
    is a real global cut-off and the extra object is a real 18-pixel speck of
    debris that happens to be brighter than it. The exact areas are pinned
    rather than only the counts, because "seven objects" would still hold if two
    cells merged into one blob and a noise grain took the freed slot — a
    different image entirely, telling a different story.

    The speck is asserted where the recipe put it and at a size no cell could
    be mistaken for, which is what makes the next step's "that little dot" and
    the interactive block that removes it honest.
    """
    for filename, expected in _THRESHOLD_AREAS.items():
        labels = _label_plane(_threshold_labels(assets, filename))
        assert _label_areas(labels) == expected, filename

    speck = _THRESHOLD_AREAS["cells_01.tif"][_SPECK_LABEL]
    cells = [area for label, area in _THRESHOLD_AREAS["cells_01.tif"].items() if label != _SPECK_LABEL]
    assert len(cells) == _CELL_COUNTS["cells_01.tif"]
    assert speck * 10 < min(cells), "the speck must be unmistakably smaller than any cell"

    labels = _label_plane(_threshold_labels(assets, "cells_01.tif"))
    speck_ys, speck_xs = np.nonzero(labels == _SPECK_LABEL)
    assert (round(float(speck_ys.mean())), round(float(speck_xs.mean()))) == (_SPECK_ONE[0], _SPECK_ONE[1])

    # The second slide is clean, which is what makes the first slide's speck a
    # finding rather than a fixture the reader would learn to expect.
    assert len(_THRESHOLD_AREAS["cells_02.tif"]) == _CELL_COUNTS["cells_02.tif"]


def test_the_adaptive_run_is_honestly_worse(assets: dict[str, ModuleType]) -> None:
    """Thirteen and ten objects: the reader is told it turned out worse, and it did.

    ``try-another-method`` sends the reader to a genuinely available method and
    ``back-to-threshold`` opens with "that turned out worse than before". The
    copy is only honest while the adaptive method really is worse, so this is
    recomputed rather than asserted as a bare number.

    "Worse" is not the object count on its own, and it is not "no cell survives"
    either — filling holes helps the adaptive run as much as the threshold one,
    so both return recognisable cells. What the local cut-off adds is *debris*:
    it follows the texture between cells as readily as their edges, and hands
    back fragments alongside them. So the two assertions are that it finds more
    objects than the threshold did, and that some of what it found is far too
    small to be a cell. Together those are the sentence the copy says: it found
    more, and the extra is not cells.
    """
    block = assets["segment"].SegmentCellsBlock()
    for filename, expected in _ADAPTIVE_COUNTS.items():
        labels = _label_plane(
            block.process_item(_shipped_image(assets, filename), BlockConfig(params={"method": "adaptive"}))
        )
        found = _label_areas(labels)
        assert len(found) == expected, filename
        assert len(found) > len(_THRESHOLD_AREAS[filename]), f"{filename}: adaptive must find more pieces"

        cells = [area for label, area in _THRESHOLD_AREAS[filename].items() if area > 500]
        fragments = [area for area in found.values() if area < min(cells) / 2]
        assert fragments, (
            f"{filename}: adaptive must return something no one would call a cell — "
            f"its smallest object is {min(found.values())}px against a smallest cell of {min(cells)}px"
        )


def test_the_step_texts_stand_on_what_the_pixels_do(manifest: TutorialManifest) -> None:
    """Editing the data or the copy alone fails here; they must move together.

    The rewrite took the spoken counts out of this level — the reader is shown
    the label map and the areas table rather than told a tally — so what is
    pinned now is each claim the copy still makes, against the measurement that
    makes it true. Every one of them is a claim that could quietly stop being
    true if the micrographs were regenerated:

    * "it picked out something that is not a cell" — singular, and only true
      because the threshold run finds exactly one non-cell object;
    * "that little dot" — true only while that object is a speck rather than a
      merged pair of cells or a smear along an edge;
    * "that turned out worse than before" — true only while adaptive finds
      more objects than threshold, not fewer or the same;
    * "the size of every cell has been computed" — true only while the areas
      the block reports are the areas of the labels that survive review.
    """
    twist = manifest.step_by_id("try-another-method")
    assert twist is not None and twist.say
    assert "not a cell" in say_text(twist)
    extras = len(_THRESHOLD_AREAS["cells_01.tif"]) - _CELL_COUNTS["cells_01.tif"]
    assert extras == 1, "the copy says the run picked out one thing that is not a cell"

    dot = manifest.step_by_id("blocks-can-be-interactive")
    assert dot is not None and dot.say
    assert "little dot" in say_text(dot)
    assert _THRESHOLD_AREAS["cells_01.tif"][_SPECK_LABEL] < 150, "a dot, not a blob"

    worse = manifest.step_by_id("back-to-threshold")
    assert worse is not None and worse.say
    assert "worse than before" in say_text(worse)
    for filename, adaptive in _ADAPTIVE_COUNTS.items():
        assert adaptive > len(_THRESHOLD_AREAS[filename]), filename

    table = manifest.step_by_id("a-dataframe-of-areas")
    assert table is not None and table.say
    said = say_text(table)
    assert "DataFrame" in said and "size of every cell" in said


# ---------------------------------------------------------------------------
# The interactive block and its hand-written panel
# ---------------------------------------------------------------------------


def test_the_review_block_is_a_real_interactive_block(assets: dict[str, ModuleType]) -> None:
    """Mixin + execution mode + panel manifest: the registry's own validation gate."""
    from scistudio.blocks.base import ExecutionMode, InteractiveMixin
    from scistudio.blocks.registry._capability import _validate_interactive_capability
    from scistudio.blocks.registry._spec import _spec_from_class
    from scistudio.core.panels import PanelCapability

    cls = assets["review"].ReviewLabelsBlock
    assert issubclass(cls, InteractiveMixin)
    assert cls.execution_mode is ExecutionMode.INTERACTIVE

    spec = _spec_from_class(cls, source="custom")
    assert spec.type_name == "review_labels"
    assert spec.execution_mode == "interactive"
    assert spec.panel_manifest is not None
    assert spec.panel_manifest["panel_id"] == "tutorial.review_labels"
    # ADR-054 spec 1 FR-050: a panel a block opens declares the producing
    # capability, and the registry refuses the block otherwise. Run the gate
    # itself rather than restating what it checks.
    assert cls.interactive_panel.capability is PanelCapability.PRODUCING
    _validate_interactive_capability(cls)
    # FR-017 / section 4.2: the block names the panel by id and confines no
    # asset root of its own. The retired module form carried a filesystem
    # directory here for the ``/api/blocks/panels/...`` route to serve out of;
    # the panel directory is discovered from the project's ``panels/`` root now,
    # so a block that grew one back would be reaching around discovery.
    assert spec.panel_asset_root is None


def test_the_panel_manifest_names_the_panel_by_id_alone(assets: dict[str, ModuleType]) -> None:
    """The manifest is an id, a capability and a version — no hand-written URL.

    ADR-054 spec 1 section 4.2 names this block as one the change fixes: it
    hard-coded ``/api/blocks/panels/tutorial.review_labels/panel.mjs``. A URL a
    block spells for itself is a URL that goes stale the moment the route it
    names moves, which is exactly what happened. The document is now addressed
    through the merged asset route, built from the panel id by
    ``panel_descriptor``, so the manifest must carry no URL at all — and the
    directory it addresses must exist, in the on-disk form, in this tutorial's
    assets.
    """
    from scistudio.panels.descriptor import panel_descriptor

    panel = assets["review"].ReviewLabelsBlock.interactive_panel
    assert panel.panel_id == "tutorial.review_labels"
    assert panel.module_url == ""
    assert panel.css == ()
    assert panel.entry == "index.html"
    assert panel.api_version == "1"

    # The descriptor the paused block hands the host: the merged route, this
    # panel's id, this manifest's entry.
    descriptor = panel_descriptor(panel).to_dict()
    assert descriptor["document_url"] == "/api/panels/assets/tutorial.review_labels/index.html"
    assert descriptor["asset_base_url"] == "/api/panels/assets/tutorial.review_labels/"
    assert descriptor["capability"] == "producing"

    # The directory the id resolves to is the one the tutorial copies into the
    # project, and it is a panel directory: a declaration plus one document.
    panel_dir = ASSETS / "panels" / "review_labels"
    assert (panel_dir / "panel.json").is_file()
    assert (panel_dir / "index.html").is_file()
    assert not (panel_dir / "panel.mjs").exists(), "the retired ADR-051 module form is gone"


def test_the_panel_declaration_is_the_on_disk_form() -> None:
    """``panel.json`` reads as a valid producing declaration for this panel id.

    Read through :func:`read_panel_declaration` rather than ``json.loads``: the
    point is not that the file parses but that the discovery walk which will
    find it in the reader's project accepts it, with every field FR-003 requires.
    """
    from scistudio.core.panels import PanelCapability, read_panel_declaration

    manifest = read_panel_declaration(ASSETS / "panels" / "review_labels")
    assert manifest.panel_id == "tutorial.review_labels"
    assert manifest.display_name == "Review Labels"
    assert manifest.capability is PanelCapability.PRODUCING
    assert manifest.entry == "index.html"
    assert manifest.api_version == "1"
    # Addressed by the block that opens it, never by a data type (FR-017).
    assert manifest.target_types == ()


def test_the_panel_document_implements_the_panel_contract() -> None:
    """A strictly self-contained producing document: the envelope, and one emission.

    The replacement for the assertions that pinned the ES-module form
    (``export default`` / ``mount(container, host)`` / ``host.confirm(`` /
    ``host.cancel(``). Every one of those named a thing the contract retired, so
    each is replaced by the thing that now does its job: the D-011 envelope and
    the token check instead of ``mount``'s two arguments, the ``emit`` of a
    ``scistudio.output`` call instead of ``host.confirm``, and the host's own
    Confirm/Cancel chrome (D-018) instead of ``host.cancel``. FR-034's
    self-containment is checked here too, which the module form never had to be.
    """
    panel_dir = ASSETS / "panels" / "review_labels"
    source = (panel_dir / "index.html").read_text(encoding="utf-8")
    # Comments stripped before the self-containment scan, exactly as
    # ``tests/panels/test_builtin_panels.py`` does it: a document that
    # *documents* the rule it obeys must not fail on the rule it describes.
    # What is measured is what the document loads, and a comment loads nothing.
    executable = re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)
    executable = re.sub(r"/\*.*?\*/", "", executable, flags=re.DOTALL)
    executable = re.sub(r"^[ \t]*//.*$", "", executable, flags=re.MULTILINE)

    # FR-034 / A-004: markup, styles and script in one file.
    assert "<style>" in source and "<script>" in source and "<body>" in source
    assert re.search(r"<script\b[^>]*\bsrc\b", executable) is None
    assert re.search(r"<link\b[^>]*stylesheet", executable, flags=re.IGNORECASE) is None
    assert re.search(r"@import\b", executable, flags=re.IGNORECASE) is None
    assert re.search(r"\bimport\s*\(", executable) is None
    assert re.search(r"^\s*import\s+[\w{*]", executable, flags=re.MULTILINE) is None
    assert re.findall(r"\bhttps?://(?!www\.w3\.org/)", executable) == [], "no CDN, nothing off this origin"
    for banned in ("require(", "fetch(", "XMLHttpRequest", "WebSocket"):
        assert banned not in executable, f"the panel must stay dependency-free and offline; found {banned!r}"

    # D-011: the envelope, the one API version, and the per-mount token check.
    assert "var PANEL_MESSAGE_MARKER = 1;" in executable
    assert 'var PANEL_API_VERSION = "1";' in executable
    assert "if (data.scistudio_panel !== PANEL_MESSAGE_MARKER) return;" in executable
    assert "if (data.token !== token) return;" in executable
    # D-017: it answers `init` with `ready` and honours `teardown`.
    assert 'post("ready", { api_version: PANEL_API_VERSION });' in executable
    assert 'case "teardown":' in executable

    # FR-012 / FR-050: the one outbound path is `emit`, and what it emits is the
    # decision `ReviewLabelsBlock.run` reads back out of `interactive_response`.
    assert 'post("emit", { code: code });' in executable
    assert '"removed = "' in executable
    assert '"scistudio.output(removed=removed)"' in executable
    # D-018: Confirm and Cancel are host chrome, so the panel re-emits its whole
    # decision rather than emitting what moved. It must say so, and it must not
    # have grown a Confirm of its own.
    assert "Confirm and Cancel are host chrome" in source
    assert "host.confirm(" not in executable and "host.cancel(" not in executable


def test_the_prompt_payload_is_window_sized_and_complete(assets: dict[str, ModuleType]) -> None:
    """The panel gets a payload it can draw, and nothing the reader must click has been thinned away.

    The block sends a strided view when the label map is larger than the
    panel's window, which at 200x200 means every other pixel — a 100x100 grid.
    Striding is what keeps the JSON small enough for the browser, and it is
    also the one thing here that could quietly break the level: the object the
    reader is asked to delete is an 18-pixel speck, and a stride that dropped
    it would leave them staring at a picture with nothing wrong in it while the
    step waited for a click that could never happen.

    So both halves are asserted, on both slides. The areas table is the
    full-resolution truth, one row per label with its real pixel count, and the
    strided grid still contains every label id including the speck's. A future
    map large enough for a stride of three or four would fail here rather than
    in front of a reader.

    The batch is asserted too, and it is not a nicety: the level loads two
    micrographs, so a block that reviewed one would stop the run dead the first
    time a reader followed the step as written.
    """
    maps = [_threshold_labels(assets, name) for name in ("cells_01.tif", "cells_02.tif")]
    review = assets["review"].ReviewLabelsBlock()
    prompt = review.prepare_prompt(
        {"labels": Collection(items=maps, item_type=assets["image"].Image)}, BlockConfig(params={})
    )
    slides = prompt.panel_payload["slides"]
    assert len(slides) == 2, "the batch the reader loaded is the batch the window carries"

    for slide, name in zip(slides, ("cells_01.tif", "cells_02.tif"), strict=True):
        expected = _THRESHOLD_AREAS[name]
        stride = int(slide["stride"])
        assert stride == 2, "200 pixels through a 160-pixel window is every other row and column"
        assert (slide["height"], slide["width"]) == (_SHAPE[0] // stride, _SHAPE[1] // stride)
        assert [row["id"] for row in slide["labels"]] == list(expected)
        assert {row["id"]: row["area"] for row in slide["labels"]} == expected, (
            "the areas the panel lists are counted at full resolution, not off the strided grid"
        )
        grid = slide["grid"]
        assert len(grid) == slide["height"] and len(grid[0]) == slide["width"]
        assert {value for row in grid for value in row} == {0, *expected}, (
            "every label survived the stride, the speck the reader has to click included"
        )


def test_the_decision_removes_the_speck_and_prices_the_cells(assets: dict[str, ModuleType]) -> None:
    """removed=[1] -> six labels survive, and the areas table prices exactly them.

    The corrected label map is not an output. The reader deleted those labels
    themselves, on screen; handing the map back would restate what they just
    did. The table is where the removal has to show, which is what the
    assertions below read.
    """
    labels = _threshold_labels(assets)
    review = assets["review"].ReviewLabelsBlock()
    out = review.run(
        {"labels": Collection(items=[labels], item_type=assets["image"].Image)},
        BlockConfig(params={"interactive_response": {"removed": [_SPECK_LABEL]}}),
    )
    assert set(out) == {"areas"}

    expected = _THRESHOLD_AREAS["cells_01.tif"]
    table = next(iter(out["areas"])).get_in_memory_data().to_pandas()
    assert list(table["label"]) == [label for label in expected if label != _SPECK_LABEL]
    assert {int(row["label"]): int(row["area_px"]) for _, row in table.iterrows()} == {
        label: area for label, area in expected.items() if label != _SPECK_LABEL
    }


def test_an_unreviewed_run_keeps_every_label(assets: dict[str, ModuleType]) -> None:
    """No decision means no removal — the block never deletes on its own."""
    labels = _threshold_labels(assets)
    review = assets["review"].ReviewLabelsBlock()
    out = review.run({"labels": Collection(items=[labels], item_type=assets["image"].Image)}, BlockConfig(params={}))
    table = next(iter(out["areas"])).get_in_memory_data().to_pandas()
    assert list(table["label"]) == list(_THRESHOLD_AREAS["cells_01.tif"])


# ---------------------------------------------------------------------------
# The panel
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


def _png_chunks(png: bytes) -> list[tuple[bytes, bytes]]:
    """Every chunk of a PNG as ``(tag, body)``, in file order.

    Written out rather than pulled from a library because the panel encodes
    its PNG by hand, and a test that decoded with Pillow would be checking that
    Pillow is forgiving rather than that the bytes are right.
    """
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    chunks: list[tuple[bytes, bytes]] = []
    offset = 8
    while offset < len(png):
        length = int.from_bytes(png[offset : offset + 4], "big")
        tag = png[offset + 4 : offset + 8]
        chunks.append((tag, png[offset + 8 : offset + 8 + length]))
        offset += 12 + length
    return chunks


def _png_indices(width: int, height: int, idat: bytes) -> np.ndarray:
    """The palette index of every pixel, filter bytes stripped."""
    import zlib

    raw = zlib.decompress(idat)
    rows = []
    for y in range(height):
        start = y * (width + 1)
        assert raw[start] == 0, "the encoder writes filter type 0 on every row"
        rows.append(list(raw[start + 1 : start + 1 + width]))
    return np.array(rows, dtype=np.uint8)


def test_the_panel_claims_image_and_paints_the_pixels_in_color(assets: dict[str, ModuleType]) -> None:
    """The payoff beat shows a fluorescence image, so the PNG must actually be one.

    "There they are!" is the line that opens the step after this panel
    lands, and it is only earned if the reader is looking at something that
    reads as cells at a glance. A grayscale ramp would satisfy "renders a real
    PNG" and would still leave the reader squinting at a gray smear, so this
    test checks the encoding the panel chose and what that encoding does to
    the two pixels that matter.

    Indexed color (IHDR color type 3) is the choice: one byte per pixel plus a
    768-byte palette, so the color costs almost nothing and lives in a chunk
    that either exists or does not. The palette is then read the way the eye
    reads it — background dark, cell interior bright, and green clearly ahead
    of the other channels somewhere in between, which is what makes it a
    channel LUT rather than a gray ramp with extra steps. A regression to
    grayscale fails on the missing PLTE; a regression to a gray palette fails
    on the green.
    """
    import base64

    from scistudio.panels.models import EnvelopeKind

    specs = assets["preview"].get_previewers()
    assert len(specs) == 1 and specs[0].target_type == "Image"
    assert specs[0].backend_provider is assets["preview"].render_image

    image = _shipped_image(assets)
    envelope = assets["preview"].render_image(_StubRequest(image.to_memory().tolist()))
    assert envelope.kind is EnvelopeKind.PLOT
    encoded = envelope.payload["src"]
    assert encoded.startswith("data:image/png;base64,")
    png = base64.b64decode(encoded.split(",", 1)[1])

    chunks = dict(_png_chunks(png))
    assert [tag for tag, _ in _png_chunks(png)] == [b"IHDR", b"PLTE", b"IDAT", b"IEND"]
    width, height, depth, color_type = (
        int.from_bytes(chunks[b"IHDR"][0:4], "big"),
        int.from_bytes(chunks[b"IHDR"][4:8], "big"),
        chunks[b"IHDR"][8],
        chunks[b"IHDR"][9],
    )
    assert (height, width) == _SHAPE
    assert (depth, color_type) == (8, 3), "8-bit indexed color: one byte per pixel plus a palette"

    palette = chunks[b"PLTE"]
    assert len(palette) == 768
    assert palette == assets["preview"]._lut(), "the palette shipped is the LUT the module builds"

    def color_at(y: int, x: int) -> tuple[int, int, int]:
        index = int(indices[y, x])
        return tuple(palette[3 * index : 3 * index + 3])  # type: ignore[return-value]

    indices = _png_indices(width, height, chunks[b"IDAT"])

    def luminance(rgb: tuple[int, int, int]) -> float:
        return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]

    background = color_at(0, 0)
    assert luminance(background) < 40, f"the corner is empty slide and must stay dark, got {background}"

    # A point inside a cell, read off the shipped pixels rather than named by
    # hand: the brightest pixel of the first slide is in one.
    shipped = _expected_micrograph("cells_01.tif")
    bright_y, bright_x = np.unravel_index(int(np.argmax(shipped)), shipped.shape)
    interior = color_at(int(bright_y), int(bright_x))
    assert luminance(interior) > 180, f"the middle of a cell must be bright, got {interior}"

    green_forward = [
        index
        for index in range(256)
        if palette[3 * index + 1] > palette[3 * index] + 40 and palette[3 * index + 1] > palette[3 * index + 2] + 40
    ]
    assert len(green_forward) > 64, "a fluorescence LUT, not a gray ramp: green leads over most of the range"


def test_the_panel_reports_failure_as_an_envelope(assets: dict[str, ModuleType]) -> None:
    from scistudio.panels.models import EnvelopeKind

    envelope = assets["preview"].render_image(_StubRequest(None))
    assert envelope.kind is EnvelopeKind.ERROR
    assert envelope.error is not None


def test_the_panel_derives_its_tier_from_where_it_sits(tmp_path: Path) -> None:
    """The same bytes answer PROJECT beside a project.yaml and USER in a library.

    "Move to My Library" relocates the file verbatim, and the drop-in scans
    refuse a spec whose declared tier disagrees with the directory being
    scanned — so a panel that hard-coded either tier would break on one
    side of the move. Deriving the tier from the location is what makes the
    promotion the tutorial teaches actually work.
    """
    from scistudio.panels.models import OwnerKind

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
#
# The walk below drives the real runtime, so the two things the runtime talks
# to have to behave the way the product's do: the workflow file the canvas and
# the config panel edit, and the registry re-scan the API layer performs after
# a tutorial writes a file. Both live out here as plain functions rather than
# inside the test, because they are mechanism rather than narrative — and
# because a walk that reads as a list of beats is the point of that test.


def _open_workflow(project: Path) -> dict[str, Any]:
    """The graph as it stands on disk, including whatever the tutorial wrote there."""
    path = project / "workflows" / "main.yaml"
    if not path.is_file():
        return {"workflow": {"id": "main", "version": "1.0.0", "nodes": [], "edges": []}}
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def _save_workflow(project: Path, data: dict[str, Any]) -> None:
    path = project / "workflows" / "main.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _place_node(project: Path, node_id: str, block_type: str) -> None:
    """Drop a node onto whatever graph is currently open, as the canvas would."""
    data = _open_workflow(project)
    data["workflow"]["nodes"].append({"id": node_id, "block_type": block_type, "config": {"params": {}}})
    _save_workflow(project, data)


def _configure_node(project: Path, block_type: str, **params: Any) -> None:
    """Edit one node's parameters in place, as the config panel would."""
    data = _open_workflow(project)
    for node in data["workflow"]["nodes"]:
        if node["block_type"] == block_type:
            node.setdefault("config", {}).setdefault("params", {}).update(params)
            _save_workflow(project, data)
            return
    raise AssertionError(f"no {block_type!r} node to configure; the walk got ahead of the graph")


def _declared_block_types(source: str) -> set[str]:
    """Every ``type_name`` a block module declares, read without importing it."""
    found: set[str] = set()
    for cls in (node for node in ast.parse(source).body if isinstance(node, ast.ClassDef)):
        for node in cls.body:
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "type_name"
                and isinstance(node.value, ast.Constant)
            ):
                found.add(str(node.value.value))
    return found


def _rescan(product: Any, written: Any) -> None:
    """The API layer's registry re-scan, reduced to what the conditions read.

    A tutorial write is only half of what the reader sees happen: the file
    lands, and the product notices. The runtime calls this back with the paths
    it wrote, and the steps that judge ``block_registered``, ``type_registered``
    or ``previewer_registered`` become true here — which is what lets the walk
    prove those steps are satisfied by the write rather than by the press.
    """
    import re

    blocks = set(product.block_types)
    types = set(product.data_types)
    panels = set(product.panel_types)
    for raw in written:
        path = Path(raw)
        if path.suffix != ".py":
            continue
        source = path.read_text(encoding="utf-8")
        if path.parent.name == "blocks":
            blocks |= _declared_block_types(source)
        elif path.parent.name == "types":
            types.update(node.name for node in ast.parse(source).body if isinstance(node, ast.ClassDef))
        elif path.parent.name == "previewers":
            match = re.search(r'target_type="([^"]+)"', source)
            if match:
                panels.add(match.group(1))
    product.block_types = frozenset(blocks)
    product.data_types = frozenset(types)
    product.panel_types = frozenset(panels)


def test_the_whole_tutorial_walks_through_the_real_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every beat of the real manifest, driven end to end (#2081, #2135).

    The runtime, session store, and progress store are the real ones; the
    product-state port is stood in exactly as the API layer stands it in. The
    walk asserts what the level exists for: the wall is met before the loader
    exists, the number table is met before the panel exists, the judged
    conditions demand the reader's own clicks and runs, and the promotions land
    before the tutorial completes — without firing the work-import milestone,
    which belongs to tutorial 4.

    The walk names every step because the manifest is cut into dialogue beats:
    the steps that carry a payoff judge nothing and advance on a plain
    ``_advance``, and each step that does judge something is satisfied here by
    the same product change the reader would make on it. A beat that moved to a
    different step, or a condition that quietly migrated with it, breaks this
    walk long before it could confuse a reader.

    Two steps write ``workflows/main.yaml`` on entry, and the walk deliberately
    does *not* stand in for them. The fake product reads the workflow off the
    project file the way the real one does, so if those writes stopped
    happening — or landed a graph missing the segmentation or the review node —
    the run steps that follow would have nothing to segment and this walk would
    fail. Building the graph by hand here would hide exactly that.
    """
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
        files_written=lambda written: _rescan(product, written),
    )

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
    for filename in _SLIDES:
        assert (project / "data" / "raw" / filename).is_file(), "the bootstrap landed both micrographs"

    _advance("create-the-image-type")
    assert _live_step(runtime.active_session()).satisfied is False
    # The New data type dialog writes the product template and opens it.
    types_dir = project / "types"
    types_dir.mkdir(parents=True, exist_ok=True)
    (types_dir / "image.py").write_text("class MyDataType:\n    pass\n", encoding="utf-8")
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("make-it-image")
    # The entry write replaced the template and the re-scan registered Image.
    assert _live_step(runtime.active_session()).satisfied is True
    written = (types_dir / "image.py").read_text(encoding="utf-8")
    assert "class Image(Array):" in written, "the step tells the reader to look at a subclass of Array"
    assert "MyDataType" not in written, "the dialog's template is gone, not appended to"

    _advance("add-load")
    _place_node(project, "load-1", "load_data")
    assert _live_step(runtime.evaluate_active()).satisfied is True

    # Pointing the Load block at the micrographs is three beats — select the
    # node, browse to the files, then name their type — and each beat judges
    # only its own share of what the reader has just done.
    _advance("select-the-load-block")
    assert _live_step(runtime.active_session()).satisfied is False
    view = runtime.report_ui_event("node_selected", "load_data")
    assert _live_step(view).satisfied is True

    _advance("browse-to-the-image")
    assert _live_step(runtime.active_session()).satisfied is False
    _configure_node(project, "load_data", path=["data/raw/cells_01.tif"])
    assert _live_step(runtime.evaluate_active()).satisfied is False, (
        "one file is half the batch; the step names both and requires both"
    )
    _configure_node(project, "load_data", path=["data/raw/cells_01.tif", "data/raw/cells_02.tif"])
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("say-it-is-an-image")
    assert _live_step(runtime.active_session()).satisfied is False, "the paths are set; the core_type is not"
    _configure_node(project, "load_data", core_type="Image")
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("run-into-the-wall")
    assert _live_step(runtime.active_session()).satisfied is False, "no run has started since entry"
    _run(succeeded=False)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    # The wall's payoff — the dispatch error, quoted verbatim — is a reading step
    # of its own, which is the only way an auto-advancing level can show it at all.
    _advance("read-the-capability-error")

    _advance("teach-it-to-load")
    view = runtime.trigger_active()
    assert (project / "blocks" / "load_tiff_image.py").is_file()
    assert "load_tiff_image" in product.block_types, "the re-scan registered the loader before the press reported done"
    assert _live_step(view).satisfied is True, "this step judges the file its own trigger writes"

    _advance("set-the-capability")
    assert _live_step(runtime.active_session()).satisfied is False, (
        "the loader exists; the Load block has not been pointed at it yet"
    )
    # The shape a drop-in block really mints, mtime segment and all.
    _configure_node(
        project, "load_data", capability_id="_scistudio_dropin_load_tiff_image_1787593641.loadtiffimage.load.tiff"
    )
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("run-it-again")
    assert _live_step(runtime.active_session()).satisfied is False, (
        "the capability alone is not the lesson; the reader must run"
    )
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    # Why the micrograph came out as numbers, and the panel that fixes it,
    # are one step: the explanation carries the button that writes the file.
    # The instruction to open a file is judged; the verdict on what it shows is
    # the step after it.
    _advance("look-at-the-numbers")
    view = runtime.report_ui_event("preview_item_opened", None)
    assert _live_step(view).satisfied is True

    _advance("why-numbers")
    assert _live_step(runtime.active_session()).satisfied is False
    view = runtime.trigger_active()
    assert (project / "previewers" / "image_preview.py").is_file()
    assert "Image" in product.panel_types, "the previewers/ re-scan registered the panel live (#2086)"
    assert _live_step(view).satisfied is True, "registration is all this step asks for"

    _advance("look-again")
    assert _live_step(runtime.active_session()).satisfied is False, (
        "the write is not the look; the reader must click the node again"
    )
    view = runtime.report_ui_event("node_selected", "load_data")
    assert _live_step(view).satisfied is True

    # The verdict "there they are" is about a picture the reader has to have
    # opened, so the click comes first.
    _advance("open-the-rendered-image")
    view = runtime.report_ui_event("preview_item_opened", None)
    assert _live_step(view).satisfied is True

    _advance("segment-the-cells")
    view = runtime.trigger_active()
    assert (project / "blocks" / "segment_cells.py").is_file()
    assert _live_step(view).satisfied is True, "this step judges the file its own trigger writes"

    # The level wires the graph itself here. Nothing below stands in for that:
    # the segmentation node and its edge are on disk because the step's entry
    # action put them there, and the reader's own Load configuration survived.
    _advance("wired-for-you")
    wired = _open_workflow(project)["workflow"]
    assert [node["block_type"] for node in wired["nodes"]] == ["load_data", "segment_cells"]
    assert [(edge["source"], edge["target"]) for edge in wired["edges"]] == [("load-cells:data", "segment:image")]
    assert wired["nodes"][0]["config"]["params"]["core_type"] == "Image"
    assert wired["nodes"][0]["config"]["params"]["path"] == ["data/raw/cells_01.tif", "data/raw/cells_02.tif"]
    # A run-only step: the harness dates each run a few seconds ahead so it
    # counts as "since entry", which is why the arrival state is not asserted
    # here the way it is on steps that judge something the reader must do.
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    # The look comes before the verdict, and the same click is asked for twice:
    # once to see the labels, once to reach the settings. The event recorder is
    # cleared on step entry, so the second ask is not satisfied by the first
    # click — which is what makes the two steps separable at all.
    _advance("look-at-the-labels")
    assert _live_step(runtime.active_session()).satisfied is False, "nothing clicked on arrival"
    view = runtime.report_ui_event("node_selected", "segment_cells")
    assert _live_step(view).satisfied is True

    # Selecting the block lists the batch; opening a card is what draws a slide,
    # and the verdict in the next step is about something the reader has seen.
    _advance("open-the-first-slide")
    view = runtime.report_ui_event("preview_item_opened", None)
    assert _live_step(view).satisfied is True

    _advance("try-another-method")
    assert _live_step(runtime.active_session()).satisfied is False, (
        "the click that satisfied the step before this one does not carry over"
    )
    view = runtime.report_ui_event("node_selected", "segment_cells")
    assert _live_step(view).satisfied is True

    _advance("switch-to-adaptive")
    assert _live_step(runtime.active_session()).satisfied is False, "the method is still threshold on arrival"
    _configure_node(project, "segment_cells", method="adaptive")
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("run-the-adaptive-method")
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("open-the-adaptive-result")
    view = runtime.report_ui_event("preview_item_opened", None)
    assert _live_step(view).satisfied is True

    _advance("back-to-threshold")
    assert _live_step(runtime.active_session()).satisfied is False, "the method is still adaptive on arrival"
    _configure_node(project, "segment_cells", method="threshold")
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("blocks-can-be-interactive")
    view = runtime.trigger_active()
    assert (project / "blocks" / "review_labels.py").is_file()
    # The panel traveled with the block. Asserted through the discovery walk
    # rather than as a file that exists, because "the file is on disk" is
    # precisely what stayed true of the retired ADR-051 module form after the
    # loader that mounted it was deleted. What the block actually needs is the
    # id its manifest names resolving, in the tier the reader's project owns, to
    # a panel directory whose entry document is there to serve.
    from scistudio.core.panels import PanelCapability, PanelTier
    from scistudio.panels.discovery import discover_panels

    discovered = discover_panels(project_roots=[project / "panels"]).get("tutorial.review_labels")
    assert discovered is not None, "the panel the block opens must be discoverable in the project"
    assert discovered.tier is PanelTier.PROJECT
    assert discovered.manifest.capability is PanelCapability.PRODUCING
    assert discovered.entry_path.name == "index.html" and discovered.entry_path.is_file()
    assert _live_step(view).satisfied is True, "this step judges the file its own trigger writes"

    # The second wiring write, and the same rule: the review node is on the
    # canvas because the step put it there, not because the walk did.
    _advance("run-with-review")
    reviewed = _open_workflow(project)["workflow"]
    # Save joins here: the areas are the answer the level was working towards,
    # and an answer that lives only in a preview is not one the reader can take
    # away.
    assert [node["block_type"] for node in reviewed["nodes"]] == [
        "load_data",
        "segment_cells",
        "review_labels",
        "save_data",
    ]
    wired = [(edge["source"], edge["target"]) for edge in reviewed["edges"]]
    assert ("segment:labels", "review:labels") in wired
    assert ("review:areas", "save-areas:data") in wired
    assert _live_step(runtime.active_session()).satisfied is False, "the panel has not been confirmed yet"
    product.interactions = frozenset({"review"})
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("look-at-the-areas")
    assert _live_step(runtime.active_session()).satisfied is False, "confirming the panel is not looking at the result"
    view = runtime.report_ui_event("node_selected", "review_labels")
    assert _live_step(view).satisfied is True

    # The areas table, named on a reading beat the reader paces for themselves.
    _advance("open-the-first-table")
    view = runtime.report_ui_event("preview_item_opened", None)
    assert _live_step(view).satisfied is True

    _advance("a-dataframe-of-areas")

    _advance("save-the-type")
    assert _live_step(runtime.active_session()).satisfied is False
    product.library = product.library | {("type", "Image")}
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("save-the-block")
    product.library = product.library | {("block", "segment_cells")}
    assert _live_step(runtime.evaluate_active()).satisfied is True

    # The panel promotion judges nothing (TODO(#2135) on the step): the
    # control it asks for records a scope rather than moving the file, so the
    # reader continues by hand and the walk does too.
    _advance("save-the-previewer")

    # The histogram: the step's own trigger scaffolds the plot, so the plot the
    # next step rings exists before its text is readable (FR-059).
    _advance("a-histogram-for-your-labmate")
    runtime.trigger_active()
    assert (project / "plots" / "cell_size_histogram" / "plot.yaml").is_file()
    assert (project / "plots" / "cell_size_histogram" / "render.py").is_file()
    # `plot_exists` judges the product's plot bindings rather than the files, so
    # the step waits for the product to have read the new plot directory.
    product.plots = (("cell_size_histogram", "review", "areas"),)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("run-the-histogram")
    view = runtime.report_ui_event("plot_rendered", "cell_size_histogram")
    assert _live_step(view).satisfied is True

    # Exporting is judged on the act, not the file: the reader names the file in
    # a native dialog and image extensions are outside the watcher's allowlist,
    # so no `file_exists` could be written or re-evaluated.
    _advance("export-the-histogram")
    assert _live_step(runtime.active_session()).satisfied is False
    view = runtime.report_ui_event("plot_exported", None)
    assert _live_step(view).satisfied is True

    _advance("what-a-type-is")
    finished = runtime.continue_active()
    assert finished.status is SessionStatus.COMPLETE

    # Tutorial 2 is a level, not the milestone: completing it must not offer
    # the work import (FR-079 names tutorial 4).
    assert runtime.progress_store.work_import_offer_pending() is False
