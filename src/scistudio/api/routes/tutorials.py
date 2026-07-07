"""Guided onboarding tutorial endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import ProjectResponse

router = APIRouter(prefix="/api/tutorials", tags=["tutorials"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]

RUN_FIRST_WORKFLOW_ID = "run-first-scistudio-workflow"
TUTORIAL_PROJECT_NAME = "Run Your First SciStudio Workflow"
DATASET_PATH = "data/raw/cell_viability_fluorescence.csv"
CUSTOM_BLOCK_PATH = "blocks/normalize_fluorescence.py"
CUSTOM_BLOCK_TYPE = "normalize_fluorescence"
CUSTOM_BLOCK_NAME = "Normalize Fluorescence"
PLOT_ID = "normalized_activity_plot"
PLOT_TITLE = "Normalized activity by condition"
NEGATIVE_CONTROL = "neg_control"
POSITIVE_CONTROL = "pos_control"

_DATASET_CSV = """condition,replicate,fluorescence
neg_control,1,3120
neg_control,2,3280
neg_control,3,3010
treated_1uM,1,8240
treated_1uM,2,7910
treated_1uM,3,8460
treated_5uM,1,12650
treated_5uM,2,13120
treated_5uM,3,12380
pos_control,1,18400
pos_control,2,19150
pos_control,3,17980
"""


class RunFirstWorkflowBootstrapRequest(BaseModel):
    """Request body for starting a fresh onboarding tutorial instance."""

    parent_path: str | None = Field(
        default=None,
        description="Optional parent directory for the tutorial project. Defaults to ~/SciStudio Tutorials.",
    )


class RunFirstWorkflowBootstrapResponse(BaseModel):
    """Concrete resource handles for the first-workflow onboarding tutorial."""

    tutorial_id: str
    project: ProjectResponse
    dataset_path: str
    workflow_id: str
    custom_block_path: str
    custom_block_type: str
    custom_block_name: str
    plot_id: str
    plot_title: str
    negative_control: str
    positive_control: str


def _tutorial_parent(parent_path: str | None) -> Path:
    if parent_path:
        return Path(parent_path).expanduser().resolve()
    return Path.home() / "SciStudio Tutorials"


def _unique_project_name(parent: Path) -> str:
    base = TUTORIAL_PROJECT_NAME

    def slug(name: str) -> str:
        return "".join(char.lower() if char.isalnum() else "-" for char in name).strip("-") or "project"

    if not (parent / slug(base)).exists():
        return base
    for index in range(2, 1000):
        candidate = f"{base} {index}"
        if not (parent / slug(candidate)).exists():
            return candidate
    raise RuntimeError("Could not find an available tutorial project name.")


@router.post("/run-first-workflow/bootstrap", response_model=RunFirstWorkflowBootstrapResponse)
async def bootstrap_run_first_workflow(
    body: RunFirstWorkflowBootstrapRequest,
    runtime: RuntimeDep,
) -> RunFirstWorkflowBootstrapResponse:
    """Create a fresh real project for the first-workflow onboarding tutorial."""
    parent = _tutorial_parent(body.parent_path)
    try:
        parent.mkdir(parents=True, exist_ok=True)
        project = runtime.create_project(
            _unique_project_name(parent),
            "SciStudio onboarding tutorial project.",
            str(parent),
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create tutorial project: {exc}") from exc

    project_root = Path(project.path)
    dataset = project_root / DATASET_PATH
    try:
        dataset.parent.mkdir(parents=True, exist_ok=True)
        dataset.write_text(_DATASET_CSV, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write tutorial dataset: {exc}") from exc

    return RunFirstWorkflowBootstrapResponse(
        tutorial_id=RUN_FIRST_WORKFLOW_ID,
        project=ProjectResponse(**runtime.project_response(project)),
        dataset_path=DATASET_PATH,
        workflow_id="main",
        custom_block_path=CUSTOM_BLOCK_PATH,
        custom_block_type=CUSTOM_BLOCK_TYPE,
        custom_block_name=CUSTOM_BLOCK_NAME,
        plot_id=PLOT_ID,
        plot_title=PLOT_TITLE,
        negative_control=NEGATIVE_CONTROL,
        positive_control=POSITIVE_CONTROL,
    )
