"""``scripts/committer.py`` — hard-tooling wrapper around ``git add`` / ``git commit``.

Per ADR-042 §16, every commit by an agent runtime MUST flow through this
wrapper. It enforces four invariants:

1. Forbid the wildcard staging idioms ``-A``, ``-a``, ``.``, ``*`` (§16.3).
   Agents must enumerate every file they stage. This is the primary
   guardrail against silent contract drift.
2. Auto-append the ``Assisted-by: <runtime>/<model>`` git trailer (§16.2)
   to every commit message based on the ``SCIEASY_AGENT_RUNTIME`` /
   ``SCIEASY_AGENT_MODEL`` environment variables.
3. Run ``pre-commit run --files <list>`` before staging (§16.4) so the
   commit is rejected on lint/type failures BEFORE the index moves. If
   ``pre-commit`` is not installed, emit a single warning and continue
   (see TODO below — full enforcement lands with Phase 1F).
4. Append a JSONL record to ``docs/audit/commit-log.jsonl`` (§16.5) with
   SHA, timestamp, author, runtime, model, files, message-first-line.

Identity resolution (§16.2 + §25.2):

- If ``SCIEASY_HUMAN_OVERRIDE`` is set, the commit is treated as human-
  authored (no auto-trailer).
- Else, if ``SCIEASY_AGENT_RUNTIME`` is set, auto-trailer with that
  runtime+model.
- Else, attempt to match the configured git author email against
  ``docs/identity/humans.yml`` (per §25.2 / 1A-b ``IdentityRegistry``).
  A match permits the commit as a human; no trailer is added.
- Else, the commit is REFUSED (§16.2: "without ``SCIEASY_AGENT_RUNTIME``,
  ``committer.py`` refuses to commit unless ...").

# TODO(#1155): ``pre-commit run --files`` graceful-degradation when the
#   binary is absent. ADR-042 §16.4 specifies hard-rejection on hook
#   failure, but the pre-commit-config audit hook set is not yet wired
#   (it lands in Phase 1F). For sub-PR 3 we emit a single stderr warning
#   and proceed; once Phase 1F ships, this falls back to a hard error.
#   Followup: open as part of ADR-042 Phase 1F.

# TODO(#1155): ``docs/identity/humans.yml`` is not yet a tracked file
#   (Phase 1H sub-PR 2 ships the AGENTS.md hierarchy + identity registry).
#   For sub-PR 3 we look it up if it exists but treat its absence as
#   "no human identity match available". Followup: open as part of
#   ADR-042 Phase 1H sub-PR 2.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_FORBIDDEN_ARGS = ("-A", "--all", "-a", ".", "*")
_RUNTIMES = ("Claude", "Codex", "Cursor", "Aider", "Gemini")


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("could not locate repo root from committer.py")


def _is_forbidden(arg: str) -> bool:
    """Return True if ``arg`` is one of the forbidden wildcard staging tokens.

    Matches the literal tokens listed in ADR-042 §16.3:

    - ``-A`` / ``--all``: stage every change in the worktree.
    - ``-a``: ``git commit -a``-style auto-stage (read in ``commit`` argv).
    - ``.``: relative-current-dir wildcard.
    - ``*``: shell glob; rejected even though the shell usually expands it
      before ``committer.py`` ever sees it (defence-in-depth).
    """
    return arg in _FORBIDDEN_ARGS


def _reject_forbidden(argv: list[str]) -> None:
    for arg in argv:
        if _is_forbidden(arg):
            raise SystemExit(
                f"committer.py refuses forbidden staging arg: {arg!r}.\n"
                "Per ADR-042 §16.3, enumerate every file explicitly.\n"
                "Allowed: 'committer.py add path/a path/b'."
            )


def _git_author_email(cwd: Path) -> str:
    """Return ``git config user.email`` or the empty string."""
    try:
        out = subprocess.run(
            ["git", "config", "--get", "user.email"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip()
    except (FileNotFoundError, OSError):
        return ""


def _identity_match(email: str, root: Path) -> dict[str, Any] | None:
    """Look up ``email`` in ``docs/identity/humans.yml``, if it exists.

    Returns the matching human's dict, or ``None`` if no match (or the
    registry file is absent — see module-level TODO).
    """
    registry_path = root / "docs" / "identity" / "humans.yml"
    if not registry_path.is_file() or not email:
        return None
    try:
        data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    for human in data.get("humans") or []:
        if isinstance(human, dict) and human.get("email") == email:
            return human
    return None


def _resolve_actor(root: Path) -> dict[str, str]:
    """Resolve the actor based on env vars + identity registry.

    Returns a dict with keys ``kind`` (``agent`` / ``human``), ``runtime``,
    ``model``, ``email``, ``github``.

    Raises ``SystemExit`` if no identity signal resolves (the §16.2 refusal
    path).
    """
    email = _git_author_email(root)

    if os.environ.get("SCIEASY_HUMAN_OVERRIDE"):
        return {
            "kind": "human",
            "runtime": "",
            "model": "",
            "email": email,
            "github": os.environ.get("SCIEASY_HUMAN_OVERRIDE", ""),
        }

    runtime = os.environ.get("SCIEASY_AGENT_RUNTIME", "")
    if runtime:
        if runtime not in _RUNTIMES:
            raise SystemExit(
                f"committer.py: SCIEASY_AGENT_RUNTIME={runtime!r} not in {sorted(_RUNTIMES)} (ADR-042 §16.2)."
            )
        return {
            "kind": "agent",
            "runtime": runtime,
            "model": os.environ.get("SCIEASY_AGENT_MODEL", ""),
            "email": email,
            "github": "",
        }

    human = _identity_match(email, root)
    if human is not None:
        return {
            "kind": "human",
            "runtime": "",
            "model": "",
            "email": email,
            "github": str(human.get("github", "")),
        }

    raise SystemExit(
        "committer.py: no actor identity could be resolved.\n"
        "Set SCIEASY_AGENT_RUNTIME=<Claude|Codex|...> (agent),\n"
        "or SCIEASY_HUMAN_OVERRIDE=<github-handle> (human one-off),\n"
        "or register your email in docs/identity/humans.yml (human, recurring).\n"
        "See ADR-042 §16.2 + §25.2."
    )


def _build_trailer(actor: dict[str, str]) -> str | None:
    """Build the ``Assisted-by:`` trailer per ADR-042 §13.2.

    Returns ``None`` for human commits (no auto-trailer).
    """
    if actor["kind"] != "agent":
        return None
    runtime = actor["runtime"]
    model = actor["model"] or "unknown-model"
    return f"Assisted-by: {runtime}/{model}"


_TRAILER_RE = re.compile(r"^[A-Z][A-Za-z0-9-]+: ")


def _append_trailer(message: str, trailer: str) -> str:
    """Insert ``trailer`` into the trailer block of ``message`` per git conventions.

    If the message already has a trailer block (consecutive lines matching
    ``Key: value`` at the tail, preceded by a blank line), append within it.
    Otherwise, append a blank line then the trailer.
    """
    if not trailer:
        return message
    stripped = message.rstrip("\n")
    lines = stripped.split("\n")
    # Find the start of the trailer block by walking up while we see Key: value lines.
    i = len(lines) - 1
    while i >= 0 and lines[i] != "" and _TRAILER_RE.match(lines[i]):
        i -= 1
    # If the message already contains the exact trailer (idempotent), keep as-is.
    if any(line == trailer for line in lines):
        return stripped + "\n"
    if i >= 0 and lines[i] == "":
        # There's already a trailer block; append within it.
        lines.append(trailer)
    else:
        lines.append("")
        lines.append(trailer)
    return "\n".join(lines) + "\n"


def _run_pre_commit(files: list[str], cwd: Path) -> int:
    """Invoke ``pre-commit run --files <files>``. Degrades gracefully if absent."""
    pre_commit = shutil.which("pre-commit")
    if pre_commit is None:
        print(
            "committer.py: WARNING — `pre-commit` binary not found on PATH; "
            "skipping §16.4 invocation. See module-level TODO(#1155).",
            file=sys.stderr,
        )
        return 0
    if not files:
        return 0
    result = subprocess.run(
        [pre_commit, "run", "--files", *files],
        cwd=cwd,
        check=False,
    )
    return result.returncode


def _git(args: list[str], cwd: Path, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
    )


def _append_commit_log(
    root: Path,
    *,
    sha: str,
    actor: dict[str, str],
    files: list[str],
    message: str,
) -> None:
    """Append the §16.5 JSONL record."""
    log_path = root / "docs" / "audit" / "commit-log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "sha": sha,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": actor.get("github") or actor.get("runtime") or actor.get("email") or "unknown",
        "runtime": actor.get("runtime", ""),
        "model": actor.get("model", ""),
        "files": files,
        "message_first_line": message.splitlines()[0] if message else "",
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _cmd_add(files: list[str], cwd: Path) -> int:
    """Stage the listed files. Forbidden tokens reject before any git call."""
    if not files:
        raise SystemExit("committer.py add: at least one file is required.")
    _reject_forbidden(files)
    rc = _run_pre_commit(files, cwd)
    if rc != 0:
        return rc
    result = _git(["add", "--", *files], cwd=cwd)
    return result.returncode


def _cmd_commit(
    message: str,
    *,
    cwd: Path,
    dry_run: bool = False,
    actor: dict[str, str] | None = None,
) -> int:
    """Run ``git commit -m <message>`` with auto-trailer + commit-log append.

    ``message`` is the user-supplied first line + body; we append the
    ``Assisted-by:`` trailer for agent commits.
    """
    root = _find_repo_root()
    actor = actor or _resolve_actor(root)
    trailer = _build_trailer(actor)
    final_message = (
        _append_trailer(message, trailer) if trailer else message + ("\n" if not message.endswith("\n") else "")
    )

    # Compute the staged file list BEFORE the commit so it's recorded faithfully.
    staged = _git(["diff", "--cached", "--name-only"], cwd=cwd, capture=True)
    files = [line for line in staged.stdout.splitlines() if line.strip()]

    if dry_run:
        print("--- committer.py dry-run ---")
        print(f"actor: {actor}")
        print(f"files: {files}")
        print("message:")
        print(final_message)
        return 0

    result = _git(["commit", "-m", final_message], cwd=cwd)
    if result.returncode != 0:
        return result.returncode

    head = _git(["rev-parse", "HEAD"], cwd=cwd, capture=True)
    sha = head.stdout.strip()
    _append_commit_log(root, sha=sha, actor=actor, files=files, message=final_message)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(prog="committer.py", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_p = subparsers.add_parser("add", help="git add (forbidden tokens rejected)")
    add_p.add_argument("files", nargs="+")

    commit_p = subparsers.add_parser("commit", help="git commit with auto-trailer")
    commit_p.add_argument("-m", "--message", required=True)
    commit_p.add_argument("-A", action="store_true", help="(forbidden — rejected)")
    commit_p.add_argument("-a", action="store_true", help="(forbidden — rejected)")
    commit_p.add_argument("--dry-run", action="store_true")

    args, extra = parser.parse_known_args(argv)
    # Reject -A/-a explicitly (argparse turns them into bool attrs above).
    if getattr(args, "A", False) or getattr(args, "a", False):
        raise SystemExit("committer.py refuses -A/-a (ADR-042 §16.3).")
    _reject_forbidden(extra)

    cwd = _find_repo_root()
    if args.command == "add":
        return _cmd_add(list(args.files), cwd=cwd)
    if args.command == "commit":
        return _cmd_commit(args.message, cwd=cwd, dry_run=args.dry_run)
    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable but satisfies mypy


if __name__ == "__main__":
    sys.exit(main())
