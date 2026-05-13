"""``scieasy hook-bridge`` — invoked by Claude Code's PreToolUse hook.

T-ECA-110 / ADR-033 §3 D4.3.

The bridge:

1. Reads CC's PreToolUse hook payload (JSON) from stdin.
2. POSTs ``{chat_id, tool_name, tool_input, project_dir}`` to the local
   SciEasy backend's ``/api/ai/permission-check`` endpoint.
3. Inspects the response:
   * ``{"action": "approve"}`` → exit 0 silently. CC proceeds with the
     tool call.
   * ``{"action": "deny", "reason": ...}`` → print reason to stderr,
     exit 2. CC blocks the tool call and surfaces the reason in the
     assistant message (per spike T-ECA-105 scenario d).
4. On any error path (backend unreachable, non-JSON response, malformed
   stdin, ...) — fail **closed**: print a human-readable reason to
   stderr and exit 2. Never exit 1; CC treats non-2 non-0 exits as
   error-with-tool-proceeds (fail-open), which would defeat the
   permission policy.

Inputs from environment:

* ``SCIEASY_CHAT_ID`` — required. Injected into the Claude Code
  subprocess env by :meth:`ClaudeCodeProvider.start_session` and
  inherited by PreToolUse hook children (issue #723). The bridge uses
  it as the ``chat_id`` parameter to ``/permission-check``.
* ``SCIEASY_PROJECT_DIR`` — optional but recommended. Also injected by
  the provider so the backend can read the session metadata file for
  bypass-mode detection.
* ``SCIEASY_API_BASE`` — optional, defaults to ``http://127.0.0.1:8000``.
  For non-default deployments (e.g. SciEasy on a non-loopback host).

Implementation note: stdlib ``urllib`` is used so the bridge has zero
runtime dependencies beyond Python. The bridge is on a tight invocation
budget (each PreToolUse blocks the agent until it returns) and pulling
in ``requests`` would add cold-start cost for no benefit.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Any

import typer

logger = logging.getLogger(__name__)


_DEFAULT_API_BASE = "http://127.0.0.1:8000"
_TIMEOUT_SECONDS = 360.0
"""Bridge-side timeout. Must be larger than
``permission.DECISION_TIMEOUT_SECONDS`` (default 300) so the backend's
own timeout fires first and returns ``deny:timed_out``, rather than the
bridge tearing down the connection mid-wait.
"""


def _print_stderr(msg: str) -> None:
    """Write a human-readable line to stderr.

    CC captures stderr and includes it in the ``tool_result`` envelope
    (the spike's scenario d showed this verbatim). The user sees this
    text in the assistant's explanation.
    """
    sys.stderr.write(msg.rstrip() + "\n")
    sys.stderr.flush()


def _post_check(
    base_url: str,
    chat_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    project_dir: str | None,
) -> dict[str, Any]:
    """POST to ``/api/ai/permission-check`` and return the parsed JSON.

    Raises ``urllib.error.URLError`` (or subclass) on transport failure,
    ``json.JSONDecodeError`` on malformed response.
    """
    url = base_url.rstrip("/") + "/api/ai/permission-check"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    if project_dir:
        payload["project_dir"] = project_dir
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
        raw = resp.read()
    parsed: dict[str, Any] = json.loads(raw.decode("utf-8"))
    return parsed


def run() -> int:
    """Bridge body. Returns the exit code (0 approve, 2 deny / error)."""
    try:
        stdin_text = sys.stdin.read()
    except Exception as exc:
        _print_stderr(f"scieasy hook-bridge: failed to read stdin: {exc}")
        return 2

    try:
        hook_payload: dict[str, Any] = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError as exc:
        _print_stderr(f"scieasy hook-bridge: stdin is not valid JSON: {exc}")
        return 2

    tool_name = hook_payload.get("tool_name")
    tool_input = hook_payload.get("tool_input") or {}
    if not isinstance(tool_name, str) or not tool_name:
        _print_stderr("scieasy hook-bridge: missing tool_name in hook payload")
        return 2
    if not isinstance(tool_input, dict):
        # CC always emits a dict here; guard against future schema drift.
        _print_stderr("scieasy hook-bridge: tool_input must be an object")
        return 2

    chat_id = os.environ.get("SCIEASY_CHAT_ID")
    if not chat_id:
        # If the bridge is invoked outside of a SciEasy-managed CC session
        # there is no chat to ask, so fail closed.
        _print_stderr("scieasy hook-bridge: SCIEASY_CHAT_ID env var not set; cannot route permission request")
        return 2

    project_dir = os.environ.get("SCIEASY_PROJECT_DIR")
    base_url = os.environ.get("SCIEASY_API_BASE", _DEFAULT_API_BASE)

    try:
        result = _post_check(base_url, chat_id, tool_name, tool_input, project_dir)
    except urllib.error.URLError as exc:
        _print_stderr(f"scieasy hook-bridge: backend unreachable at {base_url} ({exc.reason}); denying for safety")
        return 2
    except (json.JSONDecodeError, ValueError) as exc:
        _print_stderr(f"scieasy hook-bridge: invalid response from backend: {exc}")
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        _print_stderr(f"scieasy hook-bridge: unexpected error: {exc!r}")
        return 2

    action = result.get("action")
    if action == "approve":
        return 0
    reason = result.get("reason") or "denied by user"
    _print_stderr(f"scieasy hook-bridge: permission denied ({reason})")
    return 2


def _typer_command() -> None:
    """Typer-friendly entry point that calls :func:`run` and exits.

    Typer wraps return values as 0; we need explicit exit codes, so we
    raise :class:`typer.Exit` with the bridge's return code.
    """
    raise typer.Exit(code=run())


def register(app: typer.Typer) -> None:
    """Register the ``hook-bridge`` subcommand on the given Typer app.

    Called from :mod:`scieasy.cli.main` at module import time so the
    existing ``scieasy`` console script gains the subcommand without a
    new ``[project.scripts]`` entry.
    """
    app.command("hook-bridge", help="Bridge CC PreToolUse hooks to the SciEasy permission backend.")(_typer_command)


if __name__ == "__main__":
    sys.exit(run())
