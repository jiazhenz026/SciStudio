#!/usr/bin/env python3
"""Wrapper around ``gh pr create`` that pre-flights ``gate_record ci``.

Motivation: local ``gate_record pre-push`` only runs structural
``validate_gate_record`` checks. CI's ``Verify Workflow Compliance`` job
runs the full guard orchestration (``docs_landing``, ``issue_link``,
``sentrux_gate``, ``mod_guard``, ``weakened_ci_check`` AND the three
PR-state guards). Issues in the first set surface only on CI today,
causing avoidable fix-and-push cycles (see PR #1351).

This wrapper closes that gap by running ``gate_record ci`` locally with
the real ``--pr-body`` before invoking ``gh pr create``. It deliberately
filters findings from the three PR-state guards
(``core_change_guard``, ``pr_merge_guard``, ``human_bypass_guard``)
because their evidence (admin labels on the PR) cannot exist until the
PR itself does — those guards remain CI's authoritative domain.

Usage::

    python scripts/scistudio_pr_create.py --title "..." --body "$(cat body.md)"
    python scripts/scistudio_pr_create.py --title "..." --body-file body.md
    python scripts/scistudio_pr_create.py --dry-run --title "..." --body "..."
    SCISTUDIO_SKIP_PREFLIGHT=1 python scripts/scistudio_pr_create.py ...

Exit codes:
    0 — pre-flight clean AND ``gh pr create`` succeeded (or ``--dry-run``)
    1 — pre-flight failed OR ``--body``/``--body-file`` missing
    2 — wrapper environment error (no gate record, no git, etc.)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Guards whose findings are CI-authoritative and impossible to validate
# locally before the PR exists. See module docstring + issue #1360.
_FILTERED_GUARD_PREFIXES: tuple[str, ...] = (
    "core_change_guard.",
    "pr_merge_guard.",
    "human_bypass_guard.",
)


def extract_body(argv: list[str]) -> str:
    """Read PR body text from ``--body`` or ``--body-file`` in *argv*.

    Returns empty string when neither flag is present. Supports both
    space-separated (``--body foo``) and equals-separated (``--body=foo``)
    forms, matching ``gh pr create``.
    """
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--body" and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--body="):
            return token.split("=", 1)[1]
        if token == "--body-file" and i + 1 < len(argv):
            return Path(argv[i + 1]).read_text(encoding="utf-8")
        if token.startswith("--body-file="):
            return Path(token.split("=", 1)[1]).read_text(encoding="utf-8")
        i += 1
    return ""


def find_gate_record(repo_root: Path, branch: str) -> Path:
    """Locate the committed gate record for *branch*.

    Scans ``<repo_root>/.workflow/records/*.json`` and returns the one
    whose ``branch`` field matches. On multi-match (umbrella PR pattern
    from #1340), prefers ``task_kind == "manager"``.

    Raises ``SystemExit`` with exit code 2 when no unique record is found.
    """
    records_dir = repo_root / ".workflow" / "records"
    if not records_dir.is_dir():
        raise SystemExit("no .workflow/records/ directory under " + str(repo_root))
    matches: list[tuple[Path, dict[str, Any]]] = []
    for record_path in sorted(records_dir.glob("*.json")):
        try:
            data = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("branch") == branch:
            matches.append((record_path, data))
    if not matches:
        raise SystemExit(f"no gate record under .workflow/records/ matches branch {branch!r}")
    if len(matches) == 1:
        return matches[0][0]
    manager = [(p, d) for (p, d) in matches if d.get("task_kind") == "manager"]
    if len(manager) == 1:
        return manager[0][0]
    raise SystemExit(
        f"multiple gate records match branch {branch!r}; cannot pick one. "
        f"Manager candidates: {len(manager)}; total: {len(matches)}."
    )


def filter_findings(report: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Drop PR-state-dependent findings from *report*.

    Returns ``(remaining, filtered_count)``. *remaining* keeps findings
    whose ``rule_id`` does NOT start with any of
    :data:`_FILTERED_GUARD_PREFIXES`; *filtered_count* is the dropped
    count so the wrapper can print a transparency note.
    """
    all_findings = report.get("findings") or []
    remaining = [
        f for f in all_findings if isinstance(f, dict) and not f.get("rule_id", "").startswith(_FILTERED_GUARD_PREFIXES)
    ]
    return remaining, len(all_findings) - len(remaining)


def run_gate_record_ci(
    repo_root: Path,
    gate_record: Path,
    pr_body: str,
    *,
    base: str = "origin/main",
    head: str = "HEAD",
) -> dict[str, Any]:
    """Invoke ``gate_record ci`` and return the parsed JSON report.

    Raises ``SystemExit`` (code 2) when the CLI emits unparseable output.
    """
    cmd = [
        sys.executable,
        "-m",
        "scistudio.qa.governance.gate_record",
        "ci",
        "--gate-record",
        str(gate_record),
        "--base",
        base,
        "--head",
        head,
        "--pr-body",
        pr_body,
        "--format",
        "json",
    ]
    env = os.environ.copy()
    src_dir = repo_root / "src"
    if src_dir.is_dir():
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(repo_root), check=False)
    try:
        return dict(json.loads(proc.stdout))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"gate_record ci emitted unparseable JSON (exit={proc.returncode}):\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    dry_run = "--dry-run" in argv
    if dry_run:
        argv.remove("--dry-run")

    skip_preflight = os.environ.get("SCISTUDIO_SKIP_PREFLIGHT") == "1"

    if not skip_preflight:
        try:
            repo_root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
            branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"ERROR: not in a git repository or git unavailable: {exc}", file=sys.stderr)
            return 2

        try:
            record = find_gate_record(repo_root, branch)
        except SystemExit as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        body = extract_body(argv)
        if not body:
            print(
                "ERROR: --body or --body-file is required (gate_record ci needs "
                "the real PR body for issue_link validation)",
                file=sys.stderr,
            )
            return 1

        try:
            report = run_gate_record_ci(repo_root, record, body)
        except SystemExit as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        remaining, filtered = filter_findings(report)
        if remaining:
            print(
                "\n✗ Pre-flight gate_record ci findings — CI will reject this PR:\n",
                file=sys.stderr,
            )
            for f in remaining:
                print(
                    f"  [{f.get('severity', '?'):>5s}] {f.get('rule_id', '?'):55s} {f.get('message', '')}",
                    file=sys.stderr,
                )
            if filtered:
                print(
                    f"\n  (filtered {filtered} PR-state finding(s) — "
                    f"core_change_guard / pr_merge_guard / human_bypass_guard "
                    f"are CI's authoritative domain.)",
                    file=sys.stderr,
                )
            print(
                f"\n→ {len(remaining)} pre-flight failure(s). Fix locally before pushing.",
                file=sys.stderr,
            )
            return 1

        print(
            f"✓ Pre-flight clean ({record.name}). "
            f"{'(' + str(filtered) + ' PR-state finding(s) filtered.) ' if filtered else ''}"
            f"Creating PR...",
            file=sys.stderr,
        )
    else:
        print(
            "⚠ Pre-flight SKIPPED via SCISTUDIO_SKIP_PREFLIGHT=1; CI is the only gate.",
            file=sys.stderr,
        )

    if dry_run:
        print(f"DRY RUN: would exec: gh pr create {' '.join(argv)}", file=sys.stderr)
        return 0

    try:
        return subprocess.call(["gh", "pr", "create", *argv])
    except FileNotFoundError:
        print("ERROR: gh CLI not found on PATH", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
