"""Honeypot canary integrity check (ADR-043 §3.6.3).

Lines marked ``# CANARY-DO-NOT-MODIFY: TRIPWIRE-RULE`` in the files
listed under ``.governance-paths.yaml::honeypot_canaries`` have no
functional role — their sole purpose is detection. Any modification
(including whitespace) trips the canary and produces a
:class:`scieasy.qa.schemas.governance.HoneypotViolation`.

Entry-point (ADR-043 §4.7 audit fix F14)::

    check_honeypot(paths_yaml: Path, repo_root: Path) -> list[HoneypotViolation]

Verification mode
-----------------

The check has two modes:

* **marker-presence**: the default in Phase 1E. For each
  ``honeypot_canaries[*]`` entry, verify the ``marker_pattern`` string
  is present somewhere in the file. If absent, emit a violation.
  This is the version that ships before TC-1B.7 orchestrators register
  SHA baselines.
* **sha-pinned**: when a ``HoneypotRule`` baseline file exists with the
  ``expected_sha256`` field populated (TC-1B.7 deliverable), the check
  additionally hashes the file and compares. **Not implemented in v1.**

References
----------
ADR-043 §3.6.3 — authoritative spec.
ADR-043 §4.7 line 1200 — entry-point signature.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

from scieasy.qa.schemas.governance import HoneypotViolation

# TODO(#1113): SHA-pinned verification mode.
#   Out of scope per ADR-043 §3.6.3 / TC-1B.7 ownership note in
#   .governance-paths.yaml (lines 85-93). Phase 1E ships marker-presence
#   only; SHA baselines are seeded by 1B.7 orchestrators.
#   Followup: open as part of ADR-043 Phase 1 sub-issues under #1113.


def _last_committer_email(repo_root: Path) -> str:
    """Return the last commit's author email; ``""`` if unavailable."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ae"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return (out.stdout or "").strip() if out.returncode == 0 else ""


def _last_commit_sha(repo_root: Path) -> str:
    """Return the last commit SHA; ``""`` if unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return (out.stdout or "").strip() if out.returncode == 0 else ""


def check_honeypot(
    paths_yaml: Path,
    *,
    repo_root: Path | None = None,
    action: str = "block-pr",
) -> list[HoneypotViolation]:
    """Verify every registered honeypot canary line still trips.

    Parameters
    ----------
    paths_yaml:
        Path to ``.governance-paths.yaml`` (or a fixture file in tests).
    repo_root:
        Repository root used to resolve canary ``path:`` entries. The
        ``paths_yaml`` parent is the default.
    action:
        ``"auto-revert"`` / ``"block-pr"`` / ``"notify-only"`` — recorded
        on each :class:`HoneypotViolation` (one of the three values from
        the schema's :class:`~typing.Literal`).
    """
    if action not in {"auto-revert", "block-pr", "notify-only"}:
        raise ValueError(f"invalid action: {action!r}")

    paths_yaml = paths_yaml.resolve()
    repo_root = (repo_root or paths_yaml.parent).resolve()

    try:
        raw = yaml.safe_load(paths_yaml.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    entries = raw.get("honeypot_canaries") or []

    violations: list[HoneypotViolation] = []
    last_sha = _last_commit_sha(repo_root)
    last_author = _last_committer_email(repo_root)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel = (entry.get("path") or "").strip()
        marker = (entry.get("marker_pattern") or "").strip()
        if not rel or not marker:
            continue
        target = (repo_root / rel).resolve()
        if not target.is_file():
            violations.append(
                HoneypotViolation(
                    rule_path=rel,
                    violating_commit_sha=last_sha or "",
                    violating_author=last_author or "",
                    action_taken=action,  # type: ignore[arg-type]
                )
            )
            continue
        try:
            body = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            violations.append(
                HoneypotViolation(
                    rule_path=rel,
                    violating_commit_sha=last_sha or "",
                    violating_author=last_author or "",
                    action_taken=action,  # type: ignore[arg-type]
                )
            )
            continue
        if marker not in body:
            violations.append(
                HoneypotViolation(
                    rule_path=rel,
                    violating_commit_sha=last_sha or "",
                    violating_author=last_author or "",
                    action_taken=action,  # type: ignore[arg-type]
                )
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.honeypot",
        description="Honeypot canary integrity check (ADR-043 §3.6.3).",
    )
    parser.add_argument(
        "--paths-yaml",
        default=".governance-paths.yaml",
        help="Path to .governance-paths.yaml (default: ./.governance-paths.yaml).",
    )
    parser.add_argument("--repo-root", default=None)
    parser.add_argument(
        "--check-all",
        action="store_true",
        help="(Compat flag; the check always runs over every honeypot_canaries entry.)",
    )
    parser.add_argument(
        "--action",
        default="block-pr",
        choices=["auto-revert", "block-pr", "notify-only"],
        help="HoneypotViolation.action_taken value (default: block-pr).",
    )
    args = parser.parse_args(argv)
    _ = args.check_all  # accepted for the §3.5 workflow call signature.

    repo_root = Path(args.repo_root or Path.cwd()).resolve()
    paths_yaml = Path(args.paths_yaml)
    if not paths_yaml.is_absolute():
        paths_yaml = repo_root / paths_yaml
    if not paths_yaml.is_file():
        print(f"honeypot/paths-yaml-missing: {paths_yaml}", file=sys.stderr)
        return 2

    violations = check_honeypot(paths_yaml, repo_root=repo_root, action=args.action)
    if not violations:
        return 0
    for v in violations:
        print(v.model_dump_json(), file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
