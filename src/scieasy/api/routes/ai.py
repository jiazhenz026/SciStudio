"""AI block generation, workflow suggestion, param optimisation endpoints."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

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


@router.get("/status")
async def provider_status() -> dict[str, Any]:
    """Return per-provider availability for the embedded coding agent.

    ADR-034 Phase 1.2: the frontend's Setup screen needs to know which
    CLI agents are installed and logged in so it can disable buttons
    and surface install instructions.  The locked response shape::

        {
          "providers": [
            {"name": "claude-code", "available": true,  "version": "2.1.141", "logged_in": true},
            {"name": "codex",       "available": false, "version": null,      "logged_in": false}
          ]
        }

    All probes are best-effort and bounded by a 2 s subprocess timeout
    — the endpoint must never block the API or 500.
    """
    return {
        "providers": [
            _probe_claude(),
            _probe_codex(),
        ]
    }


def _probe_claude() -> dict[str, Any]:
    """Probe ``claude`` binary + credentials."""
    available, version = _binary_status("claude")
    logged_in = _claude_logged_in()
    return {
        "name": "claude-code",
        "available": available,
        "version": version,
        "logged_in": logged_in,
    }


def _probe_codex() -> dict[str, Any]:
    """Probe ``codex`` binary + credentials.

    Codex stores its auth in ``~/.codex/auth.json`` after
    ``codex login``; presence of that file is treated as "looks logged
    in" for the frontend gate.  Codex may evolve its auth storage
    format; if so this probe gets bumped.
    """
    available, version = _binary_status("codex")
    auth_file = Path.home() / ".codex" / "auth.json"
    return {
        "name": "codex",
        "available": available,
        "version": version,
        "logged_in": auth_file.is_file(),
    }


def _binary_status(name: str) -> tuple[bool, str | None]:
    """Return ``(available, version_string_or_None)`` for ``name``.

    Available iff ``shutil.which`` finds the binary AND ``<name> --version``
    completes within 2 s with non-empty stdout.  Version is the trimmed
    stdout.
    """
    binary = shutil.which(name)
    if not binary:
        return False, None
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False, None
    version = (result.stdout or result.stderr or "").strip()
    if not version:
        return False, None
    return True, version


def _claude_logged_in() -> bool:
    """Heuristic: does claude appear to have stored credentials?

    Order of probes:

    1. ``~/.claude/.credentials.json`` exists — covers Linux / Windows
       and the macOS file-fallback path.
    2. On macOS, ``security find-generic-password`` against either of
       the two known service names (``Claude Code-credentials`` is the
       current name; ``claude-code`` was used briefly).  Bounded by a
       2 s timeout so a slow Keychain doesn't hang the endpoint.
    """
    if (Path.home() / ".claude" / ".credentials.json").is_file():
        return True
    if sys.platform != "darwin":
        return False
    for service in ("Claude Code-credentials", "claude-code"):
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode == 0:
            return True
    return False


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
        return cast(dict[str, Any], result)
    except ImportError:
        raise HTTPException(status_code=503, detail="AI dependencies not installed") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
