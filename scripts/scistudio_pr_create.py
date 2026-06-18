#!/usr/bin/env python3
"""Wrapper around ``gh pr create`` that pre-flights the ADR-042 gate (Addendum 6).

Thin caller of the single shared evaluator (ADR-042 Addendum 6 §6): it extracts
the PR body and base from the ``gh pr create`` argv, then runs
``gate_record check --mode pre-pr --pr-body-file <body>`` once. The evaluator
owns scope, issue-closure, label/bypass, docs/test, check execution, and guard
orchestration. PR-state-impossible findings (core-change / merge / bypass label
provenance) are classified internally by the evaluator's pre-PR mode — there is
no caller-side finding filter and no separate receipt step.

Usage::

    python scripts/scistudio_pr_create.py --title "..." --body "$(cat body.md)"
    python scripts/scistudio_pr_create.py --title "..." --body-file body.md
    python scripts/scistudio_pr_create.py --dry-run --title "..." --body "..."
    SCISTUDIO_SKIP_PREFLIGHT=1 python scripts/scistudio_pr_create.py ...

Exit codes:
    0 — pre-flight clean AND ``gh pr create`` succeeded (or ``--dry-run``)
    1 — pre-flight failed OR ``--body``/``--body-file`` missing
    2 — wrapper environment error (no gate ledger, no git, etc.)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


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


def extract_base(argv: list[str]) -> str | None:
    """Read PR base ref from ``--base`` in *argv* (matches ``gh pr create``).

    Returns ``None`` when ``--base`` is absent (caller defaults to
    ``origin/main``). Supports both space-separated (``--base foo``) and
    equals-separated (``--base=foo``) forms.
    """
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--base" and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--base="):
            return token.split("=", 1)[1]
        i += 1
    return None


def resolve_base_ref(base: str | None) -> str:
    """Map a ``gh pr create`` ``--base`` value to a git diff base ref.

    ``gh pr create --base`` takes a plain branch name (``main``,
    ``umbrella/foo``); ``git diff`` and the evaluator want a remote ref like
    ``origin/main``. This function bridges the two:

    - ``None`` -> ``origin/main`` (preserves the wrapper's historical default
      when the caller did not pass ``--base``).
    - already-qualified ref (``origin/<x>``, ``refs/<x>``) -> use verbatim so
      callers can override completely without accidental double-prefixing.
    - plain branch name -> ``f"origin/{name}"``.

    Content-agnostic: makes no assumption about whether the base is ``main``, a
    stacked-PR umbrella branch, a release branch, or anything else (#1382).
    """
    if base is None:
        return "origin/main"
    if base.startswith(("origin/", "refs/")):
        return base
    return f"origin/{base}"


def run_pre_pr_check(repo_root: Path, body_file: Path, *, base: str = "origin/main") -> int:
    """Invoke ``gate_record check --mode pre-pr`` and return its exit code.

    The evaluator streams its own findings/repair hints; the wrapper forwards
    them so the agent sees exactly what CI's ``--mode ci`` run would surface.
    """
    cmd = [
        sys.executable,
        "-m",
        "scistudio.qa.governance.gate_record",
        "check",
        "--mode",
        "pre-pr",
        "--base",
        base,
        "--head",
        "HEAD",
        "--pr-body-file",
        str(body_file),
    ]
    env = os.environ.copy()
    src_dir = repo_root / "src"
    if src_dir.is_dir():
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(cmd, env=env, cwd=str(repo_root), check=False)
    return proc.returncode


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
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"ERROR: not in a git repository or git unavailable: {exc}", file=sys.stderr)
            return 2

        # Shared deterministic discovery (Addendum 6 §5.1): the evaluator's own
        # `check` resolves the active ledger for the branch; we only verify one
        # exists so the wrapper can emit a clear environment error early.
        src_dir = repo_root / "src"
        if src_dir.is_dir() and str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        try:
            from scistudio.qa.governance.gate_record import io

            discovery = io.discover_ledger(repo_root)
        except Exception as exc:  # surface any import/discovery failure as env error.
            print(f"ERROR: gate ledger discovery failed: {exc}", file=sys.stderr)
            return 2
        if not discovery.found:
            if discovery.ambiguous:
                print(
                    "ERROR: multiple gate ledgers match this branch; pass the PR through "
                    "`gate_record check --mode pre-pr --record <path>` to disambiguate.",
                    file=sys.stderr,
                )
            else:
                print(
                    "ERROR: no gate ledger found for this branch; run `gate_record init` before creating the PR.",
                    file=sys.stderr,
                )
            return 2

        body = extract_body(argv)
        if not body:
            print(
                "ERROR: --body or --body-file is required (the evaluator needs the "
                "real PR body for issue-closure reconciliation)",
                file=sys.stderr,
            )
            return 1

        base = resolve_base_ref(extract_base(argv))

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
            handle.write(body)
            body_file = Path(handle.name)
        try:
            exit_code = run_pre_pr_check(repo_root, body_file, base=base)
        finally:
            body_file.unlink(missing_ok=True)

        if exit_code != 0:
            print(
                "\n-> pre-flight failed. Fix the unsatisfied obligations above before "
                "creating the PR (CI `--mode ci` will reject the same findings).",
                file=sys.stderr,
            )
            return 1

        print(
            f"OK: pre-flight clean ({discovery.path.name if discovery.path else 'ledger'}). Creating PR...",
            file=sys.stderr,
        )
    else:
        print(
            "WARNING: pre-flight SKIPPED via SCISTUDIO_SKIP_PREFLIGHT=1; CI is the only gate.",
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
