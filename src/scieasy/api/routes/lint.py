"""ADR-036 §3.3 — server-side Python lint endpoint (skeleton).

Wraps ``ruff check --stdin --output-format json`` so the embedded Monaco
editor can render diagnostics as squiggles via ``setModelMarkers``.

Implementation phase agent (I36a) replaces each ``raise NotImplementedError``
below with the real handler. This module is intentionally thin: there is a
single endpoint and a single dataclass-shaped response.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/lint", tags=["lint"])


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


@router.post("/python", response_model=LintResponse)
async def lint_python(body: LintRequest) -> LintResponse:
    """Lint a Python source string with ruff. (ADR-036 §3.3 — SKELETON)

    Implementation plan (per ADR-036 §3.3):
      1. Spawn ``ruff check --stdin-filename=<filename> --output-format
         json -`` via ``subprocess.run`` (text=True, capture_output=True,
         timeout=10s).
      2. Pipe ``body.content`` to stdin.
      3. Parse stdout as JSON. ruff returns a list of objects with keys
         ``code``, ``message``, ``location: {row, column}``,
         ``end_location: {row, column}``, ``severity`` (only newer ruff;
         pre-0.4 returns severity-less; default to "warning").
      4. Map each entry to ``LintDiagnostic`` (1-based row/column, no
         conversion needed — Monaco is also 1-based).
      5. Return ``LintResponse(diagnostics=[...])``.

    Soft-fail behaviour (per ADR-036 §6 risk row 2):
      - ``FileNotFoundError`` (ruff binary missing) -> return
        ``LintResponse(diagnostics=[], note="ruff unavailable on server")``;
        also log WARN once. The editor renders without squiggles; saves
        still work.
      - ``subprocess.TimeoutExpired`` -> same soft-fail with
        ``note="ruff timed out"``.
      - JSON decode error on ruff stdout -> soft-fail with
        ``note="ruff returned non-JSON"``.

    Edge cases:
      - Empty content -> ruff returns ``[]`` -> empty diagnostics, no error.
      - Content with non-ASCII bytes -> ruff handles UTF-8 via stdin; no
        special handling needed.
      - filename not ending in .py -> still works; ruff infers from the
        ``--stdin-filename`` extension.
      - content > 10 MB — accept. The lint pipeline is independent of the
        file API's size cap; users may paste a large snippet.

    Test plan (must be added by I36a):
      - test_lint_clean_returns_empty: ``content="print('ok')\\n"``.
      - test_lint_unused_import: returns one diagnostic with code starting
        with "F401".
      - test_lint_syntax_error: returns one diagnostic with code "E999".
      - test_lint_ruff_missing: monkeypatch ``subprocess.run`` to raise
        ``FileNotFoundError`` -> response has empty diagnostics + note.
      - test_lint_ruff_timeout: monkeypatch to raise
        ``subprocess.TimeoutExpired`` -> response has empty diagnostics
        + note.
      - test_lint_diagnostic_shape: asserts every field of one returned
        diagnostic matches the contract above.

    References: ADR-036 §3.3 + §6 risk row 2.
    """
    raise NotImplementedError("ADR-036 skeleton — implementation phase I36a fills this in")
