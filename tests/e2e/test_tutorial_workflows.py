"""Headless end-to-end scenarios built from the core tutorials (#2298).

Each test builds a fresh project the way the Learning Center does — by copying
the tutorial's shipped assets into it — then runs a real workflow on a real
server and checks what a user would see: the run record, the GUI events on
``/ws``, the files the workflow wrote, and the preview of an output.

The tutorials are used because they are the product's own reference workflows:
they exercise project blocks, a project-defined type, a project previewer, a
failing run, and an interactive block that pauses for a person.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import pytest

from tests.e2e.harness import Backend, EventStream, Project, build_tutorial_project, requires_e2e

pytestmark = [requires_e2e, pytest.mark.timeout(300)]

WELCOME_WORKFLOW: dict[str, Any] = {
    "id": "main",
    "version": "1.0.0",
    "description": "Load the viability plate, normalize it to its controls, and save it.",
    "nodes": [
        {
            "id": "load",
            "block_type": "load_data",
            "config": {
                "params": {
                    "core_type": "DataFrame",
                    "path": "data/raw/cell_viability_fluorescence.csv",
                    "capability_id": "core.dataframe.csv.load",
                }
            },
            "layout": {"x": 80, "y": 200},
        },
        {
            "id": "norm",
            "block_type": "normalize_fluorescence",
            "config": {"params": {}},
            "layout": {"x": 380, "y": 200},
        },
        {
            "id": "save",
            "block_type": "save_data",
            "config": {"params": {"core_type": "DataFrame", "path": "data/processed", "filename": "result.csv"}},
            "layout": {"x": 680, "y": 200},
        },
    ],
    "edges": [
        {"source": "load:data", "target": "norm:table"},
        {"source": "norm:normalized", "target": "save:data"},
    ],
}

AI_TUTORIAL_BLOCKS = [
    ("assets/data", "data/raw"),
    ("assets/code/qc_outlier_filter.py", "blocks/qc_outlier_filter.py"),
    ("assets/code/fit_ic50.py", "blocks/fit_ic50.py"),
]

TYPE_TUTORIAL_BLOCKS = [
    ("assets/data", "data/raw"),
    # The type first: the blocks and the previewer import it.
    ("assets/code/image.py", "types/image.py"),
    ("assets/code/load_tiff_image.py", "blocks/load_tiff_image.py"),
    ("assets/code/image_preview.py", "previewers/image_preview.py"),
    ("assets/code/segment_cells.py", "blocks/segment_cells.py"),
]

REVIEW_BLOCK = [
    ("assets/code/review_labels.py", "blocks/review_labels.py"),
    ("assets/panels/review_labels", "blocks/review_labels_panel"),
    ("assets/workflows/with-review.yaml", "workflows/main.yaml"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def terminations(record: dict[str, Any]) -> dict[str, str]:
    return {be["block_id"]: be["termination"] for be in record["block_executions"]}


def column_names(page: dict[str, Any]) -> list[str]:
    """The column names a table read reports, whichever shape it names them in."""
    return [column["name"] if isinstance(column, dict) else str(column) for column in page["columns"]]


def review_project(backend: Backend, projects_dir: Path, name: str) -> Project:
    return build_tutorial_project(
        backend,
        projects_dir,
        name=name,
        tutorial="what-is-a-type",
        copies=[*TYPE_TUTORIAL_BLOCKS, *REVIEW_BLOCK],
    )


def test_welcome_workflow_normalizes_the_plate_and_saves_it(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    project = build_tutorial_project(
        backend,
        projects_dir,
        name="welcome",
        tutorial="welcome-to-scistudio",
        copies=[
            ("assets/data", "data/raw"),
            ("assets/code/normalize_fluorescence.py", "blocks/normalize_fluorescence.py"),
        ],
    )
    backend.put_workflow(WELCOME_WORKFLOW)
    stored = backend.call("GET", "/api/workflows/main")
    assert [node["id"] for node in stored["nodes"]] == ["load", "norm", "save"]

    record = backend.wait_for_run(backend.execute("main"))

    assert record["run"]["status"] == "completed", record["run"]
    assert terminations(record) == {"load": "completed", "norm": "completed", "save": "completed"}
    events.wait_for_event("block_done", "load")
    normalized_done = events.wait_for_event("block_done", "norm")
    events.wait_for_event("block_done", "save")
    events.wait_for_event("workflow_completed")

    rows = read_csv(project.path / "data" / "processed" / "result.csv")
    assert len(rows) == 12
    by_condition: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_condition[row["condition"]].append(float(row["normalized_activity"]))
    assert mean(by_condition["neg_control"]) == pytest.approx(0.0, abs=1e-9)
    assert mean(by_condition["pos_control"]) == pytest.approx(1.0, abs=1e-9)
    assert 0.0 < mean(by_condition["treated_1uM"]) < mean(by_condition["treated_5uM"]) < 1.0

    # The block's output is previewable the way the GUI opens it: the session
    # names the panel to mount, and the rows arrive through that panel's own
    # read rather than in the envelope (ADR-054 Phase B).
    ref = normalized_done["data"]["outputs"]["normalized"]["data_ref"]
    envelope = backend.open_preview(ref)
    assert envelope["kind"] == "panel", envelope
    assert envelope["panel"]["id"] == "core.dataframe.basic", envelope

    context = backend.open_panel(ref)
    page = backend.panel_read(context, ref, "table.page", {"page": 1, "page_size": 50})
    assert "normalized_activity" in column_names(page)
    assert page["total"] == 12


def test_ai_tutorial_fits_the_ic50_from_the_doses_the_ai_block_read(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    project = build_tutorial_project(
        backend,
        projects_dir,
        name="what-ai-can-do",
        tutorial="what-ai-can-do",
        copies=[
            *AI_TUTORIAL_BLOCKS,
            ("assets/code/tutorial_ai_agent.py", "blocks/tutorial_ai_agent.py"),
            ("assets/workflows/main-with-ai.yaml", "workflows/main.yaml"),
        ],
    )

    record = backend.wait_for_run(backend.execute("main"))

    assert record["run"]["status"] == "completed", record["run"]
    assert set(terminations(record).values()) == {"completed"}
    rows = read_csv(project.path / "data" / "processed" / "ic50_curve.csv")
    ic50 = {float(row["ic50_um"]) for row in rows}
    assert len(ic50) == 1
    assert ic50.pop() == pytest.approx(29.3, abs=0.5)


def test_ai_tutorial_without_the_ai_block_fails_at_the_fit_and_says_why(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    # The tutorial's first run is meant to fail: the plate names groups, not
    # doses, and nothing has read the doses out of the filename yet.
    build_tutorial_project(
        backend,
        projects_dir,
        name="what-ai-can-do-no-ai",
        tutorial="what-ai-can-do",
        copies=[*AI_TUTORIAL_BLOCKS, ("assets/workflows/main.yaml", "workflows/main.yaml")],
    )

    record = backend.wait_for_run(backend.execute("main"))

    assert record["run"]["status"] == "failed", record["run"]
    outcome = terminations(record)
    assert outcome["load-plate"] == "completed"
    assert outcome["qc-filter"] == "completed"
    assert outcome["fit-curve"] != "completed"
    error = events.wait_for_event("block_error", "fit-curve")
    assert "metadata" in str(error["data"])


def test_type_tutorial_segments_both_micrographs_and_previews_the_labels(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    build_tutorial_project(
        backend,
        projects_dir,
        name="what-is-a-type",
        tutorial="what-is-a-type",
        copies=[*TYPE_TUTORIAL_BLOCKS, ("assets/workflows/load-and-segment.yaml", "workflows/main.yaml")],
    )

    record = backend.wait_for_run(backend.execute("main"))

    assert record["run"]["status"] == "completed", record["run"]
    assert terminations(record) == {"load-cells": "completed", "segment": "completed"}
    # Two micrographs in, two label maps out: a multi-item output reaches the
    # GUI as a collection of registered refs, one per item.
    segmented = events.wait_for_event("block_done", "segment")
    labels = segmented["data"]["outputs"]["labels"]
    assert labels["kind"] == "collection", labels
    assert labels["count"] == 2
    assert labels["item_type"] == "Image"
    for item in labels["items"]:
        assert item["type_name"] == "Image", item
        envelope = backend.open_preview(item["data_ref"])
        assert envelope["payload"], envelope


def test_interactive_review_keeps_every_label_but_the_one_the_user_removed(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    project = review_project(backend, projects_dir, "review-labels")
    panel = backend.http.get("/api/blocks/panels/tutorial.review_labels/panel.mjs")
    assert panel.status_code == 200, panel.text[:500]

    run_id = backend.execute("main")
    prompt = events.wait_for_event("interactive_prompt", "review")

    assert prompt["data"]["panel_manifest"]["panel_id"] == "tutorial.review_labels"
    slides = prompt["data"]["panel_payload"]["slides"]
    assert len(slides) == 2
    first = [row["id"] for row in slides[0]["labels"]]
    second = [row["id"] for row in slides[1]["labels"]]
    assert first and second
    removed = first[0]
    events.send(
        {
            "type": "interactive_complete",
            "block_id": "review",
            "workflow_id": "main",
            "data": {"removed": [[removed], []]},
        }
    )
    record = backend.wait_for_run(run_id)

    assert record["run"]["status"] == "completed", record["run"]
    saved = sorted((project.path / "data" / "processed").glob("cell_areas*.csv"))
    assert len(saved) == 2, saved
    kept_first = [int(row["label"]) for row in read_csv(saved[0])]
    kept_second = [int(row["label"]) for row in read_csv(saved[1])]
    assert kept_first == [label for label in first if label != removed]
    assert kept_second == second
    assert set(read_csv(saved[0])[0]) >= {"label", "area_px", "centroid_y", "centroid_x"}


def test_cancelling_a_run_paused_on_review_cancels_it(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    project = review_project(backend, projects_dir, "review-cancel")

    run_id = backend.execute("main")
    events.wait_for_event("interactive_prompt", "review")
    events.send({"type": "cancel_workflow", "workflow_id": "main"})
    record = backend.wait_for_run(run_id)

    assert record["run"]["status"] == "cancelled", record["run"]
    assert terminations(record).get("save-areas") != "completed"
    assert not list((project.path / "data" / "processed").glob("cell_areas*.csv"))
