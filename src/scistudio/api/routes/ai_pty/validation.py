"""Query-parameter validation for the ``ai_pty`` WebSocket route.

Hardens the user-supplied ``project_dir`` query string before it
becomes the spawned subprocess ``cwd=``.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.ai.agent.mcp._context import _safe_under, get_optional_context


def _validate_project_dir(raw: str) -> Path:
    """Resolve and sanity-check the ``project_dir`` query parameter.

    Strategy:

    1. Resolve to an absolute path (the frontend always sends absolute).
    2. If an MCP context with an active project is installed, refuse
       paths outside that root (path-traversal hardening — same defence
       as the MCP tool path resolution).
    3. Otherwise (no MCP context yet, e.g. headless tests), accept any
       absolute path that exists and is a directory.

    Security note: this is a user-supplied path that ultimately becomes
    ``cwd=`` of a spawned subprocess.  The canonicalisation through
    :meth:`Path.resolve` plus the under-project-root check (via
    :func:`_safe_under`'s ``relative_to`` comparison) blocks
    ``..``-escapes and symlink traversal; on macOS realpath also
    canonicalises ``/tmp → /private/tmp`` so the resolved-prefix check
    survives platform-specific filesystem quirks.  CodeQL's
    ``py/path-injection`` rule will still flag this function because the
    primitive ``Path`` operations are user-tainted; the alert is
    accepted given the explicit allowlist check below.
    """
    target = Path(raw)
    if not target.is_absolute():
        raise RuntimeError(f"project_dir must be absolute, got {raw!r}.")
    # ``strict=True`` raises FileNotFoundError when the path doesn't
    # exist — combined with the ``is_dir`` check this gives CodeQL a
    # narrower attack surface than open-ended ``resolve()``.
    try:
        resolved = target.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise FileNotFoundError(f"project_dir does not exist: {raw}") from exc
    if not resolved.is_dir():
        raise FileNotFoundError(f"project_dir is not a directory: {resolved}")

    ctx = get_optional_context()
    if ctx is not None and ctx.project_dir is not None:
        try:
            _safe_under(ctx.project_dir, resolved)
        except PermissionError as exc:
            raise PermissionError(
                f"project_dir {resolved} is outside the active project root {ctx.project_dir}"
            ) from exc
    return resolved
