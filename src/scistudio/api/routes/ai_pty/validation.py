"""Query-parameter validation for the ``ai_pty`` WebSocket route.

Hardens the user-supplied ``project_dir`` query string before it
becomes the spawned subprocess ``cwd=``.
"""

from __future__ import annotations

from collections.abc import Iterable
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


def validate_agent_launch(
    provider: str,
    permission_mode: str,
    *,
    with_prompt: bool = False,
    accepted: Iterable[str] | None = None,
) -> None:
    """Refuse an agent launch the spawn could not honour, before anything runs.

    The one provider and permission-mode check every agent session goes
    through: the AI Chat WebSocket launch, the pre-spawned tabs, and the routes
    that write a brief first (Bring In My Work, MiniApp create and convert). The
    checks are static — the registry key, the permission mode, whether the CLI
    has an Auto mode, and, when ``with_prompt`` is set, whether the CLI can be
    handed an opening instruction on its command line. Nothing is probed.

    ``accepted`` is the set of provider keys this caller admits; it defaults to
    the registry's agent keys.

    Raises:
        ValueError: With a user-facing sentence naming what is wrong.
    """
    # Development references: #2379, #2454, ADR-034, FR-010.
    from scistudio.ai.agent import providers_registry

    keys = tuple(accepted) if accepted is not None else tuple(providers_registry.agent_keys())
    if provider not in keys:
        raise ValueError(f"Invalid provider {provider!r} (unknown provider); expected one of {sorted(keys)}.")
    if permission_mode not in providers_registry.PERMISSION_MODES:
        raise ValueError(
            f"Invalid permission_mode {permission_mode!r}; expected one of {providers_registry.PERMISSION_MODES}."
        )
    descriptor = providers_registry.get(provider)
    if permission_mode == "auto" and not descriptor.supports_auto_mode:
        raise ValueError(f"{descriptor.label} has no Auto permission mode; choose Manual or Yolo/Bypass.")
    if with_prompt:
        unsupported = providers_registry.session_unsupported_reason(descriptor)
        if unsupported is not None:
            raise ValueError(unsupported)
