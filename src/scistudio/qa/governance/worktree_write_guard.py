"""Pre-tool guard for AI writes in SciStudio worktrees."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scistudio.qa.governance.gate_record.io import _load_record
from scistudio.qa.governance.gate_record.paths import _normalize_path

MAIN_BRANCHES = {"main", "master"}
PATH_KEYS = ("file_path", "path", "notebook_path")
BROAD_OVERRIDE_LABELS = {"human-authored", "admin-approved:ai-override"}


def _git(repo_root: Path, args: Sequence[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL).strip()


def _repo_root(start: Path) -> Path:
    return Path(_git(start, ["rev-parse", "--show-toplevel"])).resolve()


def _branch(repo_root: Path) -> str:
    return _git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])


def _effective_include(record: Any) -> list[str]:
    includes = list(record.scope.include)
    for amendment in record.amendments:
        includes.extend(amendment.include)
    return includes


def _effective_exclude(record: Any) -> list[str]:
    excludes = list(record.scope.exclude)
    for amendment in record.amendments:
        excludes.extend(amendment.exclude)
    return excludes


def _matches(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _labels(payload: Mapping[str, Any]) -> set[str]:
    raw = payload.get("bypass_labels") or payload.get("labels") or []
    if isinstance(raw, str):
        return {item.strip() for item in raw.replace(",", " ").split() if item.strip()}
    if isinstance(raw, Sequence):
        return {str(item).strip() for item in raw if str(item).strip()}
    return set()


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


def _discover_record(repo_root: Path, branch: str) -> Path | None:
    records = []
    records_dir = repo_root / ".workflow" / "records"
    if not records_dir.is_dir():
        return None
    for path in sorted(records_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, Mapping) and data.get("branch") == branch:
            records.append(path)
    if len(records) == 1:
        return records[0]
    managers = [path for path in records if json.loads(path.read_text(encoding="utf-8")).get("task_kind") == "manager"]
    return managers[0] if len(managers) == 1 else None


def check_paths(
    *,
    repo_root: Path,
    target_paths: Sequence[str],
    gate_record: Path | None = None,
    branch: str | None = None,
    bypass_labels: Sequence[str] = (),
) -> list[str]:
    """Return blocking errors for attempted AI writes."""

    root = repo_root.resolve()
    current_branch = branch or _branch(root)
    if set(bypass_labels) & BROAD_OVERRIDE_LABELS:
        return []
    errors: list[str] = []
    if current_branch in MAIN_BRANCHES or current_branch == "HEAD":
        errors.append(f"AI writes must use a dedicated non-main branch/worktree; current branch is {current_branch!r}")
    if not target_paths:
        return errors

    record_path = gate_record or _discover_record(root, current_branch)
    if record_path is None:
        errors.append("AI writes require exactly one committed gate record matching the current branch")
        return errors
    record = _load_record(record_path)
    if record.branch != current_branch:
        errors.append(f"gate record branch {record.branch!r} does not match current branch {current_branch!r}")

    includes = _effective_include(record)
    excludes = _effective_exclude(record)
    for raw_path in target_paths:
        candidate = Path(raw_path)
        absolute = candidate if candidate.is_absolute() else root / candidate
        try:
            resolved = absolute.resolve()
        except OSError:
            resolved = absolute.absolute()
        try:
            rel = _normalize_path(str(resolved.relative_to(root)))
        except ValueError:
            errors.append(f"write target is outside the assigned worktree: {raw_path}")
            continue
        if includes and not _matches(rel, includes):
            errors.append(f"write target is outside gate scope include patterns: {rel}")
        if _matches(rel, excludes):
            errors.append(f"write target is inside gate scope exclude patterns: {rel}")
    return errors


def check_hook_payload(payload: Mapping[str, Any], *, cwd: Path | None = None) -> list[str]:
    """Validate a Claude/Codex hook stdin payload."""

    start = Path(str(payload.get("cwd") or cwd or Path.cwd()))
    root = _repo_root(start)
    target_paths = _extract_paths(payload)
    return check_paths(repo_root=root, target_paths=target_paths, bypass_labels=sorted(_labels(payload)))


def _render_hook_block(errors: Sequence[str]) -> None:
    if not errors:
        return
    print("ADR-042 worktree write guard blocked this AI write:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--gate-record", type=Path)
    parser.add_argument("--branch")
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
        root = args.repo_root.resolve() if args.repo_root is not None else _repo_root(Path.cwd())
        errors = check_paths(
            repo_root=root,
            target_paths=args.target,
            gate_record=args.gate_record,
            branch=args.branch,
        )
    _render_hook_block(errors)
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
