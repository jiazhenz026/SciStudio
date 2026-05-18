"""LOCAL pre-commit governance-modification guard (ADR-043 §3.3 Tool 1).

This is the LOCAL half of the §3.3 authority split. It runs in
pre-commit and per-runtime hooks (Claude Code ``PreToolUse``, Codex hook,
…) and is deliberately **best-effort**: it cannot query GitHub for
review state, so it only validates the *shape* of the
``Governance-Modification-Approved-By:`` trailer plus a handful of
fast-fail checks (auto-generated file hand-edit, symlink resolution).

The CI-side authoritative verifier lives at
:mod:`scieasy.qa.governance.mod_pr_check` (§3.3 Tool 2). Authority
separation per ADR-043 §3.3 audit P0.3 fix.

Entry-point (ADR-043 §4.7 audit fix F14)::

    check_governance_modification(staged_files: list[Path]) -> CheckResult

The function is pure (no network, no subprocess except ``git log -1`` for
trailer extraction), which is what makes it safe to wire into hot pre-
commit and per-runtime hook paths.

Author kind detection
---------------------

§3.3 step 3 says the hook must detect the commit author kind (per
ADR-042 §16.2 + §25.2). The current implementation treats the *commit
author email* + ``Assisted-by:`` trailer presence as the discriminator:

- Email matches an entry in ``docs/identity/humans.yml`` with
  ``tier: maintainer`` → ``human-tier-2``.
- Email matches an entry with ``tier: contributor`` → ``human-tier-1``.
- Commit carries an ``Assisted-by:`` trailer → ``agent``.
- Otherwise → ``unknown``.

This matches the §3.3 step 3 decision matrix:

- Tier-2 human → ``OK`` (CI / CODEOWNERS still enforces at PR time).
- Tier-1 / Agent → require the trailer SHAPE.
- Unknown → reject.

References
----------
ADR-043 §3.3 (Tool 1) — authoritative spec.
ADR-043 §4.7 line 1185 — entry-point signature.
ADR-042 §16.2 — committer-vs-author identity protocol.
ADR-042 §25.2 — tier classification source of truth.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

#: Header line for the ``Governance-Modification-Approved-By:`` trailer.
#: Matched case-insensitively per RFC 5322; the trailer value must be a
#: GitHandle (``@<alpha>...``) per :mod:`scieasy.qa.schemas._common`.
_TRAILER_RE = re.compile(
    r"^Governance-Modification-Approved-By:\s*(@[A-Za-z0-9][A-Za-z0-9_-]*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: Auto-generated governance files. Hand-edits are rejected outright; only
#: the generator scripts may commit them (§3.3 step 5). The current entry
#: is the auto-generated half of ``.github/CODEOWNERS`` — recognised by
#: the ``BEGIN auto-generated`` / ``END auto-generated`` block markers
#: laid down by ``scripts/audit/generate_codeowners.py`` (Phase 1C).
_AUTO_GENERATED_PATHS: frozenset[str] = frozenset(
    {
        # TODO(#1113): expand once §3.2 grows its generator surface.
        # Out of scope per ADR-043 §3.3 step 5 / SUMMARY manager default.
        # Followup: open as part of ADR-043 Phase 1 sub-issues under #1113.
    }
)


AuthorKind = Literal["human-tier-2", "human-tier-1", "agent", "unknown"]


@dataclass
class CheckResult:
    """Outcome of a single LOCAL governance-modification check.

    Mirrors the loose shape used by ``scripts/audit/temp_review.py``:
    a boolean ``ok``, a list of human-readable findings, and an optional
    block of remediation instructions for the committer.
    """

    ok: bool
    findings: list[str] = field(default_factory=list)
    remediation: str | None = None
    author_kind: AuthorKind = "unknown"
    governance_files: list[Path] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Author-kind detection                                                       #
# --------------------------------------------------------------------------- #


def _read_commit_message(repo_root: Path) -> str:
    """Read the in-progress commit message.

    Pre-commit invokes the hook *before* ``COMMIT_EDITMSG`` is finalised;
    we read the staged file directly. When invoked outside a commit
    (e.g. CLI smoke tests), returns the most recent commit body via
    ``git log -1 --format=%B``.
    """
    edit_msg = repo_root / ".git" / "COMMIT_EDITMSG"
    if edit_msg.exists():
        return edit_msg.read_text(encoding="utf-8", errors="replace")
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return out.stdout if out.returncode == 0 else ""


def _read_commit_author_email(repo_root: Path) -> str:
    """Return the configured commit author email.

    Order: ``GIT_AUTHOR_EMAIL`` env var (set by pre-commit when the
    commit is mid-flight) → ``git config user.email`` → empty.
    """
    import os

    env = os.environ.get("GIT_AUTHOR_EMAIL")
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "config", "user.email"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return (out.stdout or "").strip()


def _load_humans(repo_root: Path) -> dict[str, str]:
    """Return ``{email_lower: tier}`` from ``docs/identity/humans.yml``.

    Missing / unreadable file → empty dict (we degrade to ``unknown``
    author kind in that case, which is the conservative outcome).
    """
    path = repo_root / "docs" / "identity" / "humans.yml"
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    mapping: dict[str, str] = {}
    for entry in raw.get("humans", []) or []:
        email = (entry.get("email") or "").strip().lower()
        tier = (entry.get("tier") or "").strip()
        if email and tier:
            mapping[email] = tier
    return mapping


def detect_author_kind(repo_root: Path) -> AuthorKind:
    """Classify the commit author per ADR-042 §16.2 + §25.2.

    See module docstring for the decision matrix.
    """
    email = _read_commit_author_email(repo_root).lower()
    tier = _load_humans(repo_root).get(email, "")
    if tier == "maintainer":
        return "human-tier-2"
    if tier == "contributor":
        return "human-tier-1"
    msg = _read_commit_message(repo_root)
    if re.search(r"^Assisted-by:\s+", msg, re.IGNORECASE | re.MULTILINE):
        return "agent"
    return "unknown"


# --------------------------------------------------------------------------- #
# Governance-path matching                                                    #
# --------------------------------------------------------------------------- #


def _load_governance_globs(repo_root: Path) -> list[str]:
    """Read the ``.governance-paths.yaml`` registry.

    Validated lightly here (we only need ``governance_paths``); full
    pydantic validation lives at
    :class:`scieasy.qa.schemas.governance.GovernancePaths` and runs
    elsewhere (e.g. weekly cron / CI). Missing file → empty list (the
    caller treats that as "no governance paths" — which is the same
    fail-open behaviour a fresh checkout has before Phase 1C lands).
    """
    path = repo_root / ".governance-paths.yaml"
    if not path.is_file():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    return list(raw.get("governance_paths") or [])


def _glob_match(repo_relative: str, globs: list[str]) -> bool:
    """Return True iff ``repo_relative`` matches any ``globs`` entry.

    Implemented via :class:`pathlib.PurePosixPath.match` with a manual
    ``**`` recursion — :mod:`fnmatch` does not handle ``**`` segments.
    """
    from pathlib import PurePosixPath

    p = PurePosixPath(repo_relative)
    for pattern in globs:
        # Normalise trailing slash if present.
        norm = pattern.rstrip("/")
        if not norm:
            continue
        if "**" in norm:
            # Convert ``a/**`` to a prefix match plus ``**`` over the tail.
            if norm.endswith("/**"):
                prefix = norm[:-3]
                if not prefix or repo_relative == prefix or repo_relative.startswith(prefix + "/"):
                    return True
            elif norm.startswith("**/"):
                tail = norm[3:]
                if p.match(tail) or any(part for part in p.parts if PurePosixPath(part).match(tail)):
                    return True
                # also match within nested paths
                if any(PurePosixPath("/".join(p.parts[i:])).match(tail) for i in range(len(p.parts))):
                    return True
            else:
                # ``a/**/b`` form — split and check.
                head, _, tail = norm.partition("/**/")
                if tail and (repo_relative.startswith(head + "/") or repo_relative == head) and p.match("*/" + tail):
                    return True
        else:
            if p.match(norm) or repo_relative == norm:
                return True
    return False


def find_governance_files(staged_files: list[Path], repo_root: Path) -> list[Path]:
    """Filter ``staged_files`` down to those under a governance path."""
    globs = _load_governance_globs(repo_root)
    if not globs:
        return []
    governance: list[Path] = []
    for sf in staged_files:
        try:
            rel = sf.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            # Outside repo — treat as not governance (the CI-side check
            # owns this edge case).
            continue
        if _glob_match(rel, globs):
            governance.append(sf)
    return governance


def _resolve_real_path(p: Path) -> Path:
    """Resolve symlinks defensively; never raise on missing files."""
    try:
        return p.resolve(strict=False)
    except OSError:
        return p


# --------------------------------------------------------------------------- #
# Public entry-point                                                          #
# --------------------------------------------------------------------------- #


def check_governance_modification(
    staged_files: list[Path],
    *,
    repo_root: Path | None = None,
) -> CheckResult:
    """Local-side governance-edit guardrail.

    Authority limits:
      - LOCAL hook; cannot query GitHub for PR review state.
      - Role: fail fast on obviously-missing trailers + helpful remediation.
      - The CI-side tool
        :func:`scieasy.qa.governance.mod_pr_check.verify_governance_pr`
        does the authoritative approval verification at PR time.

    Logic (ADR-043 §3.3 Tool 1):
      1. Resolve which staged files match ``.governance-paths.yaml``.
      2. If none → OK.
      3. Detect commit author kind:
           - Human Tier-2 → OK.
           - Human Tier-1 / Agent → require trailer SHAPE
             (``Governance-Modification-Approved-By: @<Tier2>``).
             Print remediation pointing at
             ``docs/contributing/workflows/governance-modification.md``.
           - Unknown → REJECT.
      4. Cross-check no symlink trickery (resolve real path; reject if
         the resolution differs from the staged path).
      5. If file is auto-generated, reject any hand-edit.
    """
    repo_root = (repo_root or Path.cwd()).resolve()
    result = CheckResult(ok=True)

    governance = find_governance_files(staged_files, repo_root)
    result.governance_files = governance
    if not governance:
        return result

    # Step 5 first — auto-generated hand-edit is fatal regardless of
    # author kind. ``_AUTO_GENERATED_PATHS`` is currently empty (see
    # constant docstring TODO).
    for gf in governance:
        try:
            rel = gf.resolve().relative_to(repo_root).as_posix()
        except ValueError:
            rel = gf.as_posix()
        if rel in _AUTO_GENERATED_PATHS:
            result.ok = False
            result.findings.append(
                f"governance/auto-generated-handedit: {rel} is auto-generated; "
                "regenerate via the documented generator instead of editing by hand"
            )

    # Step 4 — symlink trickery check.
    for gf in governance:
        real = _resolve_real_path(gf)
        if real != gf.absolute():
            try:
                real_rel = real.relative_to(repo_root).as_posix()
                staged_rel = gf.resolve().relative_to(repo_root).as_posix()
            except ValueError:
                continue
            if real_rel != staged_rel:
                result.ok = False
                result.findings.append(
                    f"governance/symlink-trickery: {staged_rel} resolves to {real_rel}; "
                    "governance paths must not be edited via symlinks"
                )

    # Step 3 — author kind.
    result.author_kind = detect_author_kind(repo_root)

    if result.author_kind == "human-tier-2":
        return result  # CI / CODEOWNERS still enforces at PR time.

    if result.author_kind == "unknown":
        result.ok = False
        result.findings.append(
            "governance/unknown-author: commit author email is not registered in "
            "docs/identity/humans.yml; cannot determine tier for governance modification"
        )
        result.remediation = _remediation_text("unknown")
        return result

    # Tier-1 / Agent — require trailer SHAPE (CI verifies the cited
    # approver actually reviewed).
    msg = _read_commit_message(repo_root)
    match = _TRAILER_RE.search(msg)
    if not match:
        result.ok = False
        result.findings.append(
            "governance/missing-approval-trailer: commit modifies "
            f"{len(governance)} governance file(s) without a "
            "'Governance-Modification-Approved-By: @<Tier2-handle>' trailer"
        )
        result.remediation = _remediation_text(result.author_kind)
    return result


def _remediation_text(author_kind: AuthorKind) -> str:
    """Render the committer-facing remediation message."""
    return (
        "Governance-path modifications require a Tier-2 approver trailer:\n"
        "\n"
        "    Governance-Modification-Approved-By: @<tier2-handle>\n"
        "\n"
        f"Detected author kind: {author_kind}.\n"
        "See docs/contributing/workflows/governance-modification.md for the\n"
        "full protocol (ADR-043 §3.3). The CI-side check (mod_pr_check)\n"
        "will additionally verify the cited approver actually reviewed the PR."
    )


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _staged_files(repo_root: Path) -> list[Path]:
    """Return staged files via ``git diff --cached --name-only``."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if out.returncode != 0:
        return []
    return [repo_root / line for line in out.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point. ``argv`` defaults to ``sys.argv[1:]``."""
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.mod_guard",
        description="LOCAL pre-commit governance-modification guard (ADR-043 §3.3 Tool 1).",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Staged files to check (default: read from `git diff --cached`).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root (default: current working directory).",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root or Path.cwd()).resolve()
    if args.files:
        staged = [Path(f) if Path(f).is_absolute() else (repo_root / f) for f in args.files]
    else:
        staged = _staged_files(repo_root)

    result = check_governance_modification(staged, repo_root=repo_root)
    if result.ok:
        return 0

    for finding in result.findings:
        print(finding, file=sys.stderr)
    if result.remediation:
        print(file=sys.stderr)
        print(result.remediation, file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
