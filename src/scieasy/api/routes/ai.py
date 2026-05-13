"""AI block generation, workflow suggestion, param optimisation endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from scieasy.api.schemas import (
    AIGenerateBlockRequest,
    AIGenerateBlockResponse,
    AIOptimizeParamsRequest,
    AIOptimizeParamsResponse,
    AISuggestWorkflowRequest,
    AISuggestWorkflowResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/generate-block", response_model=AIGenerateBlockResponse)
async def generate_block(body: AIGenerateBlockRequest) -> dict[str, Any]:
    """Generate a block from a natural-language description.

    Calls the AI block generator pipeline: category inference, prompt
    construction, LLM call, code extraction, validation, and retry.

    Returns
    -------
    dict
        Generated code, block name, validation status, report, and category.

    Raises
    ------
    HTTPException 503
        When the AI optional dependencies are not installed.
    HTTPException 500
        On any other generation error.
    """
    try:
        from scieasy.ai.generation.block_generator import generate_block as ai_generate_block

        result = ai_generate_block(body.description, body.block_category)
        return {
            "code": result.code,
            "block_name": result.block_name,
            "validation_passed": result.validation_report.get("passed", False),
            "validation_report": result.validation_report,
            "category": result.category,
        }
    except ImportError as exc:
        logger.warning("AI features unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="AI features require: pip install scieasy[ai]",
        ) from exc
    except Exception as exc:
        logger.error("Block generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/suggest-workflow", response_model=AISuggestWorkflowResponse)
async def suggest_workflow(body: AISuggestWorkflowRequest) -> dict[str, Any]:
    """Return a clear Phase 9 placeholder for workflow suggestion.

    The wired implementation lives in PR #245 and will replace this stub
    once that PR merges.
    """
    raise HTTPException(status_code=501, detail="AI workflow suggestion will arrive in Phase 9.")


@router.post("/optimize-params", response_model=AIOptimizeParamsResponse)
async def optimize_params_endpoint(body: AIOptimizeParamsRequest) -> dict[str, Any]:
    """Suggest improved parameter values for a block using AI.

    Analyses intermediate results and the block's config schema to
    propose parameter changes that may improve workflow outcomes.
    """
    try:
        from scieasy.ai.optimization.param_optimizer import optimize_params

        result = optimize_params(
            block_id=body.block_id,
            intermediate_results=body.intermediate_results,
            search_space=body.search_space,
        )
        return result
    except ImportError:
        raise HTTPException(status_code=503, detail="AI dependencies not installed") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
