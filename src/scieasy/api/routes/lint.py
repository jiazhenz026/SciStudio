"""ADR-036 §3.3 — server-side Python lint endpoint.

Wraps ``ruff check --stdin --output-format json`` so the embedded Monaco
editor can render diagnostics as squiggles via ``setModelMarkers``.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lint", tags=["lint"])

_RUFF_TIMEOUT_SECONDS: float = 10.0
_RUFF_MISSING_NOTE: str = "ruff unavailable on server"
_RUFF_TIMEOUT_NOTE: str = "ruff timed out"
_RUFF_NON_JSON_NOTE: str = "ruff returned non-JSON"

# Track whether we've already logged the "ruff missing" warning so the
# server log isn't flooded on every keystroke.
_ruff_missing_warned: bool = False


class LintDiagnostic(BaseModel):
    """One ruff diagnostic, normalised to a stable shape for the frontend.

    Field naming mirrors Monaco's ``IMarkerData`` so the React side can
    map straight through without a translation layer.
    """

    line: int
    column: int
    end_line: int
    end_column: int
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str


class LintRequest(BaseModel):
    """Skeleton — request body for /api/lint/python (per ADR-036 §3.3)."""

    content: str
    filename: str = Field(
        default="snippet.py",
        description="Used as ``--stdin-filename`` so ruff resolves per-file config.",
    )


class LintResponse(BaseModel):
    """Skeleton — response body for /api/lint/python (per ADR-036 §3.3)."""

    diagnostics: list[LintDiagnostic] = Field(default_factory=list)
    note: str | None = Field(
        default=None,
        description=(
            "Human-readable note when ruff is unavailable (per ADR-036 §6 "
            "risk row 2). Frontend may show this as a passive hint."
        ),
    )


def _map_diagnostic(entry: dict[str, Any]) -> LintDiagnostic:
    """Map a ruff JSON diagnostic to the stable :class:`LintDiagnostic` shape.

    ruff's JSON shape:
      ``{code, message, location: {row, column},
         end_location: {row, column}, severity?}``

    Pre-0.4 ruff omits ``severity`` — we default to ``"warning"`` so the
    Monaco model markers still render with a sensible icon.
    """
    location = entry.get("location") or {}
    end_location = entry.get("end_location") or location
    severity = entry.get("severity") or "warning"
    code = entry.get("code") or ""
    return LintDiagnostic(
        line=int(location.get("row", 1)),
        column=int(location.get("column", 1)),
        end_line=int(end_location.get("row", location.get("row", 1))),
        end_column=int(end_location.get("column", location.get("column", 1))),
        code=str(code) if code is not None else "",
        severity=str(severity),
        message=str(entry.get("message", "")),
    )


def lint_python_source(content: str, filename: str = "snippet.py") -> LintResponse:
    """Lint a Python source string with ruff. (ADR-036 §3.3)

    Public helper extracted from :func:`lint_python` so other backend
    routes (e.g. the blocks-reload-on-save hook in ADR-036 §3.5) can
    reuse the same diagnostics shape without going back through HTTP.

    Soft-fails (per ADR-036 §6 risk row 2) when ruff is missing, times
    out, or returns non-JSON — callers see an empty ``diagnostics`` list
    and a non-empty ``note`` string.
    """
    global _ruff_missing_warned

    try:
        completed = subprocess.run(
            [
                "ruff",
                "check",
                f"--stdin-filename={filename}",
                "--output-format=json",
                "--quiet",
                "-",
            ],
            input=content,
            capture_output=True,
            text=True,
            timeout=_RUFF_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        if not _ruff_missing_warned:
            logger.warning("lint: ruff binary not found on PATH; lint endpoint will soft-fail")
            _ruff_missing_warned = True
        return LintResponse(diagnostics=[], note=_RUFF_MISSING_NOTE)
    except subprocess.TimeoutExpired:
        logger.warning("lint: ruff timed out after %ss", _RUFF_TIMEOUT_SECONDS)
        return LintResponse(diagnostics=[], note=_RUFF_TIMEOUT_NOTE)

    raw = completed.stdout or "[]"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "lint: ruff returned non-JSON (rc=%s, stderr=%r)",
            completed.returncode,
            (completed.stderr or "")[:200],
        )
        return LintResponse(diagnostics=[], note=_RUFF_NON_JSON_NOTE)

    if not isinstance(parsed, list):
        return LintResponse(diagnostics=[], note=_RUFF_NON_JSON_NOTE)

    diagnostics = [_map_diagnostic(entry) for entry in parsed if isinstance(entry, dict)]
    return LintResponse(diagnostics=diagnostics)


@router.post("/python", response_model=LintResponse)
async def lint_python(body: LintRequest) -> LintResponse:
    """Lint a Python source string with ruff. (ADR-036 §3.3)

    Soft-fails (per ADR-036 §6 risk row 2) when ruff is missing, times out,
    or returns non-JSON — the editor renders without squiggles in those
    cases and saves continue to work.
    """
    return lint_python_source(body.content, body.filename)
