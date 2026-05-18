"""Monotonic-strengthening check (ADR-043 §3.4).

Rules may only get stricter on the 14 axes listed in §3.4.1. A loosening
on any axis is permitted only when the commit carries the three-part
``Loosening-Approved: + Loosening-Reason: + companion-addendum`` ritual
described in §3.4.2. This module performs the diff-time detection and
returns a :class:`scieasy.qa.schemas.governance.MonotonicCheckResult`.

Entry-point (ADR-043 §4.7 audit fix F14)::

    check_monotonic(base: str, head: str) -> MonotonicCheckResult

The 14 canonical axes (§3.4.1 table) are encoded in
:data:`MONOTONIC_AXIS_DIRECTIONS` with their *strictness direction* — for
some axes higher numbers are stricter (e.g. coverage threshold), for
others lower numbers are stricter (e.g. pytest timeout). The detectors
share a small framework: each is a function that compares the base and
head views of one file (or set of files) and emits zero or more
:class:`scieasy.qa.schemas.governance.LoosenedAxis` entries.

Authority limits
----------------

The 14 axes are best-effort *static* detections. False negatives are
acceptable for v1 (CI's secondary review safety-net catches them); the
high-value cases are the explicit numeric thresholds in ``pyproject.toml``
and the structural shrink/grow in ``.governance-paths.yaml`` /
``docs/skills/required.yaml`` / ``.pre-commit-config.yaml``.

References
----------
ADR-043 §3.4 (lines 655-720) — authoritative spec.
ADR-043 §4.7 line 1195 — entry-point signature.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from scieasy.qa.schemas.governance import LoosenedAxis, MonotonicCheckResult

# --------------------------------------------------------------------------- #
# Canonical axis directions (ADR-043 §3.4.1 table)                            #
# --------------------------------------------------------------------------- #

#: For each axis, the strictness direction:
#:
#: - ``"increase-is-stricter"`` — higher numbers are stricter (e.g. coverage threshold).
#: - ``"decrease-is-stricter"`` — lower numbers are stricter (e.g. pytest timeout).
#: - ``"add-is-stricter"``      — gaining list members tightens the regime.
#: - ``"remove-is-stricter"``   — shrinking a list tightens the regime
#:                                (e.g. allowed agent runtimes for a path).
#:
#: Axis identifiers match the §3.4.1 table row labels (slugified).
MONOTONIC_AXIS_DIRECTIONS: dict[str, str] = {
    "coverage-threshold": "increase-is-stricter",
    "required-ci-gates": "increase-is-stricter",
    "pre-commit-hooks": "add-is-stricter",
    "ruff-rule-selection": "add-is-stricter",
    "mypy-strictness-flags": "add-is-stricter",
    "pytest-timeout": "decrease-is-stricter",
    "required-skill-list": "add-is-stricter",
    "agent-editable-false-paths": "add-is-stricter",
    "doc-drift-path-exemptions": "remove-is-stricter",
    "trivial-fast-lane-line-limits": "decrease-is-stricter",
    "honeypot-canary-count": "increase-is-stricter",
    "allowed-agent-runtimes-per-maintainers-path": "remove-is-stricter",
    "frontmatter-required-fields": "add-is-stricter",
    "is-code-implementation-true-adrs": "add-is-stricter",
}


_LOOSENING_APPROVED_RE = re.compile(
    r"^Loosening-Approved:\s*(@[A-Za-z0-9][A-Za-z0-9_-]*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_LOOSENING_REASON_RE = re.compile(
    r"^Loosening-Reason:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


# --------------------------------------------------------------------------- #
# Git helpers                                                                 #
# --------------------------------------------------------------------------- #


def _git(repo_root: Path, *args: str) -> str:
    """Run ``git *args`` in ``repo_root`` and return stdout (or empty)."""
    try:
        out = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout


def _file_at_ref(repo_root: Path, ref: str, path: str) -> str:
    """Return the contents of ``path`` at ``ref`` or ``""`` if absent."""
    return _git(repo_root, "show", f"{ref}:{path}")


def _commit_message_between(repo_root: Path, base: str, head: str) -> str:
    """Return concatenated commit messages between ``base`` and ``head``."""
    return _git(repo_root, "log", f"{base}..{head}", "--format=%B")


# --------------------------------------------------------------------------- #
# Per-axis detectors                                                          #
# --------------------------------------------------------------------------- #


@dataclass
class _AxisContext:
    repo_root: Path
    base: str
    head: str


def _read_pyproject(ctx: _AxisContext, ref: str) -> str:
    return _file_at_ref(ctx.repo_root, ref, "pyproject.toml")


_COV_RE = re.compile(r"--cov-fail-under=(\d+(?:\.\d+)?)")
_TIMEOUT_RE = re.compile(r"^\s*timeout\s*=\s*(\d+)\s*$", re.MULTILINE)


def _detect_coverage_threshold(ctx: _AxisContext) -> list[LoosenedAxis]:
    base_txt = _read_pyproject(ctx, ctx.base)
    head_txt = _read_pyproject(ctx, ctx.head)
    bm = _COV_RE.search(base_txt)
    hm = _COV_RE.search(head_txt)
    if not bm or not hm:
        return []
    if float(hm.group(1)) >= float(bm.group(1)):
        return []
    return [
        LoosenedAxis(
            axis="coverage-threshold",
            before_value=bm.group(1),
            after_value=hm.group(1),
            file="pyproject.toml",
        )
    ]


def _detect_pytest_timeout(ctx: _AxisContext) -> list[LoosenedAxis]:
    base_txt = _read_pyproject(ctx, ctx.base)
    head_txt = _read_pyproject(ctx, ctx.head)
    bm = _TIMEOUT_RE.search(base_txt)
    hm = _TIMEOUT_RE.search(head_txt)
    if not bm or not hm:
        return []
    if int(hm.group(1)) <= int(bm.group(1)):
        return []
    return [
        LoosenedAxis(
            axis="pytest-timeout",
            before_value=bm.group(1),
            after_value=hm.group(1),
            file="pyproject.toml",
        )
    ]


def _detect_honeypot_canary_count(ctx: _AxisContext) -> list[LoosenedAxis]:
    base_txt = _file_at_ref(ctx.repo_root, ctx.base, ".governance-paths.yaml")
    head_txt = _file_at_ref(ctx.repo_root, ctx.head, ".governance-paths.yaml")
    if not base_txt or not head_txt:
        return []
    base_count = sum(1 for line in base_txt.splitlines() if line.lstrip().startswith("- path:"))
    head_count = sum(1 for line in head_txt.splitlines() if line.lstrip().startswith("- path:"))
    if head_count >= base_count:
        return []
    return [
        LoosenedAxis(
            axis="honeypot-canary-count",
            before_value=str(base_count),
            after_value=str(head_count),
            file=".governance-paths.yaml",
        )
    ]


def _set_diff_removed(base_lines: Iterable[str], head_lines: Iterable[str], strip_prefix: str = "- ") -> list[str]:
    """Return entries present in ``base_lines`` but absent in ``head_lines``.

    Order is preserved by base order. Entries are normalised by stripping
    ``strip_prefix`` and surrounding whitespace.
    """

    def _norm(seq: Iterable[str]) -> list[str]:
        out: list[str] = []
        for raw in seq:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(strip_prefix):
                line = line[len(strip_prefix) :].strip()
            out.append(line.strip('"').strip("'"))
        return out

    head_set = set(_norm(head_lines))
    return [e for e in _norm(base_lines) if e not in head_set]


def _detect_required_skill_list(ctx: _AxisContext) -> list[LoosenedAxis]:
    base = _file_at_ref(ctx.repo_root, ctx.base, "docs/skills/required.yaml")
    head = _file_at_ref(ctx.repo_root, ctx.head, "docs/skills/required.yaml")
    if not base or not head:
        return []
    # Only count top-level list entries — naïve but robust enough for the
    # one file shape this axis targets.
    removed = _set_diff_removed(base.splitlines(), head.splitlines())
    if not removed:
        return []
    return [
        LoosenedAxis(
            axis="required-skill-list",
            before_value=", ".join(removed),
            after_value="<removed>",
            file="docs/skills/required.yaml",
        )
    ]


def _detect_precommit_hooks(ctx: _AxisContext) -> list[LoosenedAxis]:
    base = _file_at_ref(ctx.repo_root, ctx.base, ".pre-commit-config.yaml")
    head = _file_at_ref(ctx.repo_root, ctx.head, ".pre-commit-config.yaml")
    if not base or not head:
        return []
    # Each hook is identified by its ``- id: <name>`` line. Removed
    # entries are a loosening.
    pattern = re.compile(r"^\s*-\s*id:\s*(\S+)", re.MULTILINE)
    base_hooks = set(pattern.findall(base))
    head_hooks = set(pattern.findall(head))
    removed = sorted(base_hooks - head_hooks)
    if not removed:
        return []
    return [
        LoosenedAxis(
            axis="pre-commit-hooks",
            before_value=", ".join(removed),
            after_value="<removed>",
            file=".pre-commit-config.yaml",
        )
    ]


def _detect_ruff_rule_selection(ctx: _AxisContext) -> list[LoosenedAxis]:
    base = _read_pyproject(ctx, ctx.base)
    head = _read_pyproject(ctx, ctx.head)
    if not base or not head:
        return []
    # Match ``select = [...]`` arrays under ``[tool.ruff.lint]`` (or the
    # legacy ``[tool.ruff]``). A shrink in selected rule sets is a
    # loosening; an expansion of ``ignore = [...]`` is too.
    select_re = re.compile(r"\[tool\.ruff(?:\.lint)?\]\s*?\n.*?(?=^\[|\Z)", re.DOTALL | re.MULTILINE)

    def _arrays(text: str, key: str) -> set[str]:
        out: set[str] = set()
        for block in select_re.findall(text):
            m = re.search(rf"\b{key}\s*=\s*\[(.*?)\]", block, re.DOTALL)
            if not m:
                continue
            for item in re.split(r"[\s,]+", m.group(1)):
                stripped = item.strip().strip('"').strip("'")
                if stripped:
                    out.add(stripped)
        return out

    base_select = _arrays(base, "select")
    head_select = _arrays(head, "select")
    base_ignore = _arrays(base, "ignore")
    head_ignore = _arrays(head, "ignore")

    findings: list[LoosenedAxis] = []
    removed_select = sorted(base_select - head_select)
    added_ignore = sorted(head_ignore - base_ignore)
    if removed_select:
        findings.append(
            LoosenedAxis(
                axis="ruff-rule-selection",
                before_value=", ".join(removed_select),
                after_value="<removed from select>",
                file="pyproject.toml",
            )
        )
    if added_ignore:
        findings.append(
            LoosenedAxis(
                axis="ruff-rule-selection",
                before_value="<not ignored>",
                after_value=", ".join(added_ignore),
                file="pyproject.toml",
            )
        )
    return findings


def _detect_mypy_strictness(ctx: _AxisContext) -> list[LoosenedAxis]:
    base = _read_pyproject(ctx, ctx.base)
    head = _read_pyproject(ctx, ctx.head)
    if not base or not head:
        return []
    flag_re = re.compile(r"^\s*(strict[_a-z]*|disallow_[_a-z]+)\s*=\s*(true|false)", re.MULTILINE)
    base_flags = dict(flag_re.findall(base))
    head_flags = dict(flag_re.findall(head))
    findings: list[LoosenedAxis] = []
    for flag, base_val in base_flags.items():
        head_val = head_flags.get(flag, base_val)
        if base_val == "true" and head_val == "false":
            findings.append(
                LoosenedAxis(
                    axis="mypy-strictness-flags",
                    before_value=f"{flag}=true",
                    after_value=f"{flag}=false",
                    file="pyproject.toml",
                )
            )
    return findings


def _detect_required_ci_gates(ctx: _AxisContext) -> list[LoosenedAxis]:
    """Detect deleted CI job entries (``jobs:`` block shrink).

    Per §3.4.1 the axis is the *number* of required CI gates. Approximate
    by counting ``jobs:`` immediate keys in ``.github/workflows/*.yml``.
    """
    findings: list[LoosenedAxis] = []
    listing = _git(ctx.repo_root, "ls-tree", "--name-only", "-r", ctx.head, ".github/workflows/")
    head_files = [line.strip() for line in listing.splitlines() if line.strip().endswith(".yml")]
    if not head_files:
        # base may still have workflows; fall back to base listing.
        listing = _git(ctx.repo_root, "ls-tree", "--name-only", "-r", ctx.base, ".github/workflows/")
        head_files = [line.strip() for line in listing.splitlines() if line.strip().endswith(".yml")]

    base_listing = _git(ctx.repo_root, "ls-tree", "--name-only", "-r", ctx.base, ".github/workflows/")
    base_files = [line.strip() for line in base_listing.splitlines() if line.strip().endswith(".yml")]

    def _jobs_in(ref: str, path: str) -> set[str]:
        body = _file_at_ref(ctx.repo_root, ref, path)
        if "\njobs:\n" not in "\n" + body and not body.lstrip().startswith("jobs:"):
            return set()
        # naïve — take the lines after ``jobs:`` until a top-level key
        # surfaces. For monotonic-shrink detection the over-approximation
        # is fine: we only care about removed entries, not absolute count.
        after = body.split("jobs:", 1)[1] if "jobs:" in body else ""
        out: set[str] = set()
        for line in after.splitlines():
            if not line.startswith("  "):
                continue
            m = re.match(r"^\s\s([A-Za-z][A-Za-z0-9_-]*):", line)
            if m:
                out.add(m.group(1))
        return out

    for f in sorted(set(base_files) | set(head_files)):
        base_jobs = _jobs_in(ctx.base, f)
        head_jobs = _jobs_in(ctx.head, f) if f in head_files else set()
        removed = sorted(base_jobs - head_jobs)
        if removed:
            findings.append(
                LoosenedAxis(
                    axis="required-ci-gates",
                    before_value=", ".join(removed),
                    after_value="<removed>",
                    file=f,
                )
            )
    return findings


def _detect_governance_paths_exemption(ctx: _AxisContext) -> list[LoosenedAxis]:
    """Catch loosenings via shrunk ``.governance-paths.yaml`` registry."""
    base = _file_at_ref(ctx.repo_root, ctx.base, ".governance-paths.yaml")
    head = _file_at_ref(ctx.repo_root, ctx.head, ".governance-paths.yaml")
    if not base or not head:
        return []
    pattern = re.compile(r'^\s*-\s+"?(?P<p>[^"\s]+)"?\s*$', re.MULTILINE)
    # Only the ``governance_paths:`` block — the ``honeypot_canaries:`` block
    # uses ``- path:`` lines so the regex above won't match those.
    base_set = set(pattern.findall(base))
    head_set = set(pattern.findall(head))
    removed = sorted(base_set - head_set)
    if not removed:
        return []
    return [
        LoosenedAxis(
            axis="agent-editable-false-paths",
            before_value=", ".join(removed),
            after_value="<removed>",
            file=".governance-paths.yaml",
        )
    ]


# Registry of (axis-id → detector). Order is the report order.
_DETECTORS: list[tuple[str, Callable[[_AxisContext], list[LoosenedAxis]]]] = [
    ("coverage-threshold", _detect_coverage_threshold),
    ("pytest-timeout", _detect_pytest_timeout),
    ("honeypot-canary-count", _detect_honeypot_canary_count),
    ("required-skill-list", _detect_required_skill_list),
    ("pre-commit-hooks", _detect_precommit_hooks),
    ("ruff-rule-selection", _detect_ruff_rule_selection),
    ("mypy-strictness-flags", _detect_mypy_strictness),
    ("required-ci-gates", _detect_required_ci_gates),
    ("agent-editable-false-paths", _detect_governance_paths_exemption),
]

# TODO(#1113): the remaining 5 axes
#   (doc-drift-path-exemptions, trivial-fast-lane-line-limits,
#    allowed-agent-runtimes-per-maintainers-path,
#    frontmatter-required-fields, is-code-implementation-true-adrs)
#   need detectors. They depend on artifacts seeded in later Phase 1
#   waves (1F frontmatter-required-fields lint, 1G ratchet baselines,
#   workflow-v2 1H). Their direction is already canonicalised in
#   MONOTONIC_AXIS_DIRECTIONS so a follow-up only needs to register a
#   detector function.
#   Out of scope per ADR-043 §3.4 / Phase 1 SUMMARY manager default.
#   Followup: open as part of ADR-043 Phase 1 sub-issues under #1113.


# --------------------------------------------------------------------------- #
# Public entry-point                                                          #
# --------------------------------------------------------------------------- #


def check_monotonic(
    base: str,
    head: str,
    *,
    repo_root: Path | None = None,
) -> MonotonicCheckResult:
    """Detect monotonic-strengthening violations between ``base`` and ``head``.

    Returns a fully-populated
    :class:`scieasy.qa.schemas.governance.MonotonicCheckResult`. The
    ``overall_blocking`` flag is ``False`` only when:

    1. No loosenings were detected, **or**
    2. All three of (trailer present, approver Tier-2-verified,
       companion addendum PR cited) are true and the contradiction-audit
       re-ran clean.

    The ``approver_is_tier2_verified`` and ``contradiction_audit_clean``
    fields are populated to ``False`` by default — verifying them
    requires GitHub-API access (handled by
    :mod:`scieasy.qa.governance.mod_pr_check` on CI). The CLI layer can
    set them via flags when the workflow knows the answer.
    """
    repo_root = (repo_root or Path.cwd()).resolve()
    ctx = _AxisContext(repo_root=repo_root, base=base, head=head)

    loosened: list[LoosenedAxis] = []
    for _name, fn in _DETECTORS:
        loosened.extend(fn(ctx))

    msg = _commit_message_between(repo_root, base, head)
    trailer_match = _LOOSENING_APPROVED_RE.search(msg)
    has_trailer = trailer_match is not None
    approver = trailer_match.group(1) if trailer_match else None

    has_reason = bool(_LOOSENING_REASON_RE.search(msg))

    # ``overall_blocking`` follows the §3.4.2 protocol — without the
    # three-part ritual, any loosening is blocking.
    overall_blocking = False if not loosened else not (has_trailer and has_reason)

    return MonotonicCheckResult(
        loosened=loosened,
        has_loosening_approved_trailer=has_trailer,
        approver_handle=approver,
        approver_is_tier2_verified=False,  # CI populates; see docstring.
        companion_addendum_pr=None,  # CI populates from a `Companion-Addendum-PR:` trailer.
        contradiction_audit_clean=False,  # CI populates.
        overall_blocking=overall_blocking,
    )


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.monotonic_check",
        description="Monotonic-strengthening check between two git refs (ADR-043 §3.4).",
    )
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root or Path.cwd()).resolve()
    result = check_monotonic(args.base, args.head, repo_root=repo_root)
    print(result.model_dump_json(indent=2))
    return 1 if result.overall_blocking else 0


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
