"""Pre-tool guard for AI writes in SciStudio worktrees (ADR-042 Addendum 6 §6.1).

Minimal single-job guard: catch the case where an AI agent **forgot to create a
worktree** and is editing the **main repo working tree** directly. AI-authored
work must happen in a dedicated worktree; this guard enforces that at write time.

It is NOT an evaluator-owned calculator (the evaluator never calls it) and it has
NO gate-record precondition and NO write-time scope enforcement. Scope
reconciliation lives entirely in ``gate_record check`` (the evaluator).

Algorithm (§6.1, replaces the legacy ``check_paths``):

1. Resolve the target write path to an absolute path. If it is outside any git
   repository: **ALLOW** unconditionally (no jurisdiction over non-repo paths
   such as ``~/.claude/memory/``, temp files, or external logs).
2. Identify which registered git worktree the target belongs to using
   ``git worktree list --porcelain``, selecting the **longest matching worktree
   root** so a path under a nested linked worktree matches that worktree, not
   the main checkout.
3. **BLOCK** when the target belongs to the **main (primary) working tree** —
   the "forgot to make a worktree" case.
4. Otherwise **ALLOW** (any linked non-main worktree, or any non-repo path).

The decision does NOT depend on the agent's cwd; it depends only on whether the
target resolves into the main working tree. When the guard blocks AND a ledger
is discoverable, it records a ``guard_event`` (best effort); it must never
require a ledger to make the block decision.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PATH_KEYS = ("file_path", "path", "notebook_path")

# Broad override labels that suppress the block (CI still verifies provenance).
# Imported lazily from the single label vocabulary to avoid coupling the guard
# to the gate ledger import chain when it runs as a standalone hook.
BROAD_OVERRIDE_LABELS = {"human-authored", "admin-approved:bypass"}


def _git(repo_root: Path, args: Sequence[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL).strip()


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _git_toplevel(start: Path) -> Path | None:
    """Return the git working-tree root reachable from ``start``, or None."""

    try:
        out = _git(start, ["rev-parse", "--show-toplevel"])
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        return None
    return _resolve(Path(out)) if out else None


def _worktree_roots(repo_root: Path) -> tuple[Path | None, list[Path]]:
    """Return ``(main_worktree_root, all_worktree_roots)`` via porcelain output.

    The first ``worktree`` entry from ``git worktree list --porcelain`` is the
    main (primary) working tree; the rest are linked worktrees.
    """

    try:
        out = _git(repo_root, ["worktree", "list", "--porcelain"])
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        return None, []
    roots: list[Path] = []
    for line in out.splitlines():
        if line.startswith("worktree "):
            roots.append(_resolve(Path(line[len("worktree ") :].strip())))
    main_root = roots[0] if roots else None
    return main_root, roots


def _nearest_existing_dir(path: Path) -> Path | None:
    """Return the nearest existing ancestor directory of ``path`` (or None).

    The target file usually does not exist yet (it is about to be written), and
    even its immediate parent may be missing. Walk up until an existing
    directory is found so git can be queried from inside the repo that will own
    the target — never from the agent's cwd.
    """

    for candidate in [path, *path.parents]:
        if candidate.is_dir():
            return candidate
    return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _owning_worktree(target: Path, roots: Sequence[Path]) -> Path | None:
    """Return the longest registered worktree root containing ``target``."""

    matches = [root for root in roots if _is_under(target, root)]
    if not matches:
        return None
    return max(matches, key=lambda root: len(root.parts))


def check_target(target: Path, *, start: Path | None = None) -> list[str]:
    """Return blocking errors for a single attempted AI write to ``target``.

    Empty list means ALLOW. ``start`` is the directory from which git is queried
    (defaults to the target's parent); the decision never depends on the agent's
    cwd, only on whether the target resolves into the main working tree.
    """

    absolute = _resolve(target if target.is_absolute() else Path.cwd() / target)
    # 1. Outside any git repository -> ALLOW unconditionally.
    probe = start or _nearest_existing_dir(absolute) or Path.cwd()
    toplevel = _git_toplevel(probe)
    if toplevel is None:
        return []
    main_root, roots = _worktree_roots(toplevel)
    if main_root is None or not roots:
        return []
    # 2. Identify the owning worktree (longest matching root).
    owner = _owning_worktree(absolute, roots)
    if owner is None:
        # The target git toplevel was found but it is not a registered worktree
        # root (e.g. a submodule or unusual layout): no jurisdiction -> ALLOW.
        return []
    # 3. Block only when the target belongs to the main (primary) working tree.
    if owner == main_root:
        return [
            "AI-authored edits must happen in a dedicated worktree, not the main "
            f"working tree ({main_root}). Create one with `git worktree add "
            "../<name> <branch>` and run your edits there."
        ]
    # 4. Any linked non-main worktree (or non-repo path) -> ALLOW.
    return []


def check_targets(target_paths: Sequence[str], *, start: Path | None = None) -> list[str]:
    """Return blocking errors across multiple target write paths."""

    errors: list[str] = []
    for raw in target_paths:
        if not str(raw).strip():
            continue
        errors.extend(check_target(Path(raw), start=start))
    return errors


# ---------------------------------------------------------------------------
# Hook payload parsing.
# ---------------------------------------------------------------------------


def _tool_input(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = payload.get("tool_input") or payload.get("arguments") or payload
    return raw if isinstance(raw, Mapping) else {}


def _extract_paths(payload: Mapping[str, Any]) -> list[str]:
    tool_input = _tool_input(payload)
    paths: list[str] = []
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, Sequence) and not isinstance(edits, str):
        for edit in edits:
            if isinstance(edit, Mapping):
                value = edit.get("file_path") or edit.get("path")
                if isinstance(value, str) and value.strip():
                    paths.append(value)
    return paths


def _labels(payload: Mapping[str, Any]) -> set[str]:
    raw = payload.get("bypass_labels") or payload.get("labels") or []
    if isinstance(raw, str):
        return {item.strip() for item in raw.replace(",", " ").split() if item.strip()}
    if isinstance(raw, Sequence):
        return {str(item).strip() for item in raw if str(item).strip()}
    return set()


def _record_block_guard_event(start: Path, errors: Sequence[str]) -> None:
    """Best-effort: record a ``guard_event`` on the discoverable ledger.

    Never required to make the block decision; failures are swallowed so the
    guard always returns its decision even when the ledger machinery is absent.
    """

    try:
        from scistudio.qa.governance.gate_record import io
        from scistudio.qa.governance.gate_record.ledger import GuardEvent

        toplevel = _git_toplevel(start)
        if toplevel is None:
            return
        discovery = io.discover_ledger(toplevel)
        if not discovery.found or discovery.path is None:
            return
        ledger = io.load_ledger(discovery.path)
        ledger.guard_events.append(
            GuardEvent(
                guard="worktree_write_guard",
                status="fail",
                findings=[{"rule_id": "worktree.main-checkout-write", "message": error} for error in errors],
            )
        )
        io.write_ledger(discovery.path, ledger, repo_root=toplevel)
    except Exception:  # guard must never raise on bookkeeping.
        return


def check_hook_payload(payload: Mapping[str, Any], *, cwd: Path | None = None) -> list[str]:
    """Validate a Claude/Codex hook stdin payload; return blocking errors."""

    if set(_labels(payload)) & BROAD_OVERRIDE_LABELS:
        return []
    start = Path(str(payload.get("cwd") or cwd or Path.cwd()))
    target_paths = _extract_paths(payload)
    errors = check_targets(target_paths, start=None)
    if errors:
        _record_block_guard_event(start, errors)
    return errors


def _render_hook_block(errors: Sequence[str]) -> None:
    if not errors:
        return
    print("ADR-042 worktree write guard blocked this AI write:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--hook-json", action="store_true")
    args = parser.parse_args(argv)

    if args.hook_json:
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print(f"invalid hook JSON: {exc}", file=sys.stderr)
            return 2
        errors = check_hook_payload(payload)
    else:
        errors = check_targets(args.target)
    _render_hook_block(errors)
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
