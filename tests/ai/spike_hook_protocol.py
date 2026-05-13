"""T-ECA-105 spike driver — Claude Code PreToolUse hook protocol verification.

Manual spike, NOT collected by pytest (the module-level skip marker
ensures this even if a future maintainer renames the file). Run
directly:

    python tests/ai/spike_hook_protocol.py [scenario]

where scenario is one of: native | blocking | deny | all (default: all).

Scenarios:

* native   — trigger a CC ``Read`` tool call with a quick-approve hook.
              Verifies that the PreToolUse hook fires for native tools
              and that approve (exit 0) lets the tool call proceed.
* blocking — same as native but the hook sleeps 35 seconds before
              exiting 0. Verifies that CC tolerates a >30s synchronous
              block (per OQ6 the production timeout will be 5 minutes).
* deny     — quick-deny hook (exit 2). Verifies CC aborts the tool
              call cleanly.
* mcp      — best-effort attempt at triggering an MCP tool call.
              Phase-2 MCP server doesn't exist yet, so this scenario
              registers no MCP server and instead documents the gap.

Outputs:

* Per-scenario stdout/stderr captured into ``$REPO/.workflow/aborted/spike-out/{scenario}.{stdout,stderr,exit,duration,hook-log}.txt``.
* Console summary printed at the end.

The spike write-up in ``docs/specs/eca-spike-hook-protocol.md`` cites
the observations from a real run of this driver.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Belt and braces: even though pytest only collects ``test_*.py`` modules,
# add an explicit marker so that an accidental rename does not silently
# attach this 35-second-blocking spike to the CI test matrix.
try:
    import pytest

    pytestmark = pytest.mark.skip(reason="manual spike, not for CI (T-ECA-105)")
except ImportError:  # pragma: no cover
    pass


REPO = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO / "docs" / "specs" / "eca-spike-hook-protocol" / "example_hook.py"
OUT_DIR = REPO / ".workflow" / "aborted" / "spike-out"


def _write_settings(workdir: Path, hook_log: Path) -> Path:
    """Emit a CC settings JSON registering the PreToolUse hook."""
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            # CC executes hook commands via the shell. On
                            # Windows + Git Bash, raw ``C:\...\python.exe`` paths
                            # get mangled (backslashes stripped). Use ``python``
                            # from PATH and quote the script path.
                            "command": f'python "{HOOK_SCRIPT}"',
                        }
                    ],
                }
            ]
        }
    }
    path = workdir / "spike-settings.json"
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    # Also record the hook-log location into env for the bash invocation;
    # CC inherits the parent's env, so this is what the hook script reads.
    os.environ["SPIKE_HOOK_LOG"] = str(hook_log)
    return path


def _run_cc(prompt: str, settings_path: Path, *, env_overrides: dict[str, str], timeout: float) -> dict:
    """Spawn ``claude --print`` with the given prompt and settings."""
    cmd = [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-hook-events",
        "--settings",
        str(settings_path),
        prompt,
    ]
    env = os.environ.copy()
    env.update(env_overrides)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input="",
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        elapsed = time.monotonic() - t0
        return {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
            "elapsed": elapsed,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - t0
        return {
            "stdout": (exc.stdout or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or ""),
            "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or ""),
            "returncode": None,
            "elapsed": elapsed,
            "timed_out": True,
        }


def _persist(name: str, result: dict, hook_log: Path) -> None:
    """Write a scenario's outputs to disk under OUT_DIR/{name}.* for later inspection."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{name}.stdout.txt").write_text(result["stdout"] or "", encoding="utf-8")
    (OUT_DIR / f"{name}.stderr.txt").write_text(result["stderr"] or "", encoding="utf-8")
    (OUT_DIR / f"{name}.meta.json").write_text(
        json.dumps(
            {
                "returncode": result["returncode"],
                "elapsed": result["elapsed"],
                "timed_out": result["timed_out"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if hook_log.exists():
        shutil.copy(hook_log, OUT_DIR / f"{name}.hook-log.jsonl")


def _summarise(name: str, result: dict, hook_log: Path) -> str:
    fires = 0
    if hook_log.exists():
        fires = sum(1 for _ in hook_log.read_text(encoding="utf-8").splitlines() if _.strip())
    return (
        f"[{name}] exit={result['returncode']} timed_out={result['timed_out']} "
        f"elapsed={result['elapsed']:.2f}s hook-fires={fires}"
    )


def scenario_native(workdir: Path) -> str:
    hook_log = workdir / "hook-native.log"
    if hook_log.exists():
        hook_log.unlink()
    settings = _write_settings(workdir, hook_log)
    sample = workdir / "sample.txt"
    sample.write_text("hello spike\n", encoding="utf-8")
    result = _run_cc(
        f"Use the Read tool to read {sample} and quote one line back to me.",
        settings,
        env_overrides={"SPIKE_HOOK_DECISION": "approve", "SPIKE_HOOK_SLEEP": "0"},
        timeout=120.0,
    )
    _persist("native", result, hook_log)
    return _summarise("native", result, hook_log)


def scenario_blocking(workdir: Path) -> str:
    hook_log = workdir / "hook-blocking.log"
    if hook_log.exists():
        hook_log.unlink()
    settings = _write_settings(workdir, hook_log)
    sample = workdir / "sample-blocking.txt"
    sample.write_text("hello blocking\n", encoding="utf-8")
    result = _run_cc(
        f"Use the Read tool to read {sample} and quote one line back to me.",
        settings,
        env_overrides={"SPIKE_HOOK_DECISION": "approve", "SPIKE_HOOK_SLEEP": "35"},
        timeout=180.0,
    )
    _persist("blocking", result, hook_log)
    return _summarise("blocking", result, hook_log)


def scenario_deny(workdir: Path) -> str:
    hook_log = workdir / "hook-deny.log"
    if hook_log.exists():
        hook_log.unlink()
    settings = _write_settings(workdir, hook_log)
    sample = workdir / "sample-deny.txt"
    sample.write_text("hello deny\n", encoding="utf-8")
    result = _run_cc(
        f"Use the Read tool to read {sample} and quote one line back to me.",
        settings,
        env_overrides={"SPIKE_HOOK_DECISION": "deny", "SPIKE_HOOK_SLEEP": "0"},
        timeout=120.0,
    )
    _persist("deny", result, hook_log)
    return _summarise("deny", result, hook_log)


def scenario_mcp(workdir: Path) -> str:
    """Best-effort MCP scenario.

    Phase-2 of the cascade defines the real SciEasy MCP server; it is
    not implemented yet. This scenario documents the gap by emitting a
    placeholder log so the write-up cites the limitation rather than
    silently asserting MCP coverage.
    """
    out = OUT_DIR / "mcp.meta.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    note = {
        "scenario": "mcp",
        "status": "skipped",
        "reason": "No SciEasy MCP server exists yet (Phase 2). The CC docs explicitly state PreToolUse hooks fire for ALL tool calls including MCP tools (https://docs.anthropic.com/claude-code/hooks). No reason to believe MCP coverage diverges from native coverage; if it did, the spike would re-run during Phase-2 integration.",
    }
    out.write_text(json.dumps(note, indent=2), encoding="utf-8")
    return "[mcp] SKIPPED (Phase-2 server not yet implemented; relying on CC docs)"


def main(argv: list[str]) -> int:
    scenario = argv[1] if len(argv) > 1 else "all"
    workdir = OUT_DIR
    workdir.mkdir(parents=True, exist_ok=True)
    summaries: list[str] = []
    if scenario in ("native", "all"):
        summaries.append(scenario_native(workdir))
    if scenario in ("blocking", "all"):
        summaries.append(scenario_blocking(workdir))
    if scenario in ("deny", "all"):
        summaries.append(scenario_deny(workdir))
    if scenario in ("mcp", "all"):
        summaries.append(scenario_mcp(workdir))
    print("\n=== T-ECA-105 spike summary ===")
    for line in summaries:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
