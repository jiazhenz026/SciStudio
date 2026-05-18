"""Weakened-CI Automatic Block hard gate (ADR-043 §6.4).

GitHub's 2026-05-07 explicit doctrine — "Any change that weakens CI is a
blocker. Full stop." — translates into the 14 detection patterns
catalogued in §6.4 (table on ADR-043 lines 1610-1626). This module
implements all 14 patterns and emits
:class:`scieasy.qa.schemas.governance.WeakeningFinding` entries.

Entry-point (ADR-043 §4.7 audit fix F14)::

    check_weakened_ci(base: str, head: str) -> list[WeakeningFinding]

Authority relationship with monotonic_check (§3.4)
--------------------------------------------------

§6.4 lines 1635-1638 are explicit: this check is **independent of and
stricter than** ``monotonic_check``. Some axes (coverage threshold,
pytest timeout, pre-commit hooks, mypy strictness, ruff rule sets) appear
in both; the deliberate double-coverage is by design — this is the
GitHub-doctrine front line and runs unconditionally on every PR, whereas
``monotonic_check`` is the longer-tail axis sweep. Both refer to the same
§3.4.2 loosening ritual (``Loosening-Approved`` + ``Loosening-Reason`` +
companion addendum) for approval.

References
----------
ADR-043 §6.4 (lines 1602-1675) — authoritative spec including all 14
detection patterns + the §6.4.1 :class:`WeakeningKind` enum + the
:class:`WeakeningFinding` schema.
ADR-043 §4.7 line 1205 — entry-point signature.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scieasy.qa.schemas.governance import WeakeningFinding, WeakeningKind

# Re-use the monotonic_check helpers so we share one ``git`` shell-out
# implementation (and identical authority limits) between the two tools.
from .monotonic_check import _commit_message_between, _file_at_ref, _git

# --------------------------------------------------------------------------- #
# Loosening-ritual trailer extraction                                         #
# --------------------------------------------------------------------------- #

_LOOSENING_APPROVED_RE = re.compile(
    r"^Loosening-Approved:\s*(@[A-Za-z0-9][A-Za-z0-9_-]*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_LOOSENING_REASON_RE = re.compile(
    r"^Loosening-Reason:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def _has_loosening_ritual(repo_root: Path, base: str, head: str) -> bool:
    """Return True iff every part of the §3.4.2 ritual is present.

    The full ritual is trailer + reason + companion addendum + clean
    contradiction audit. The last two are CI facts that this check
    cannot verify locally, so the local detector tracks only trailer +
    reason and surfaces the result through ``WeakeningFinding.blocking``.
    """
    msg = _commit_message_between(repo_root, base, head)
    return bool(_LOOSENING_APPROVED_RE.search(msg)) and bool(_LOOSENING_REASON_RE.search(msg))


# --------------------------------------------------------------------------- #
# Detector framework                                                          #
# --------------------------------------------------------------------------- #


@dataclass
class _DetectorContext:
    repo_root: Path
    base: str
    head: str
    has_loosening_approval: bool


_COV_RE = re.compile(r"--cov-fail-under=(\d+(?:\.\d+)?)")
_TIMEOUT_RE = re.compile(r"^\s*timeout\s*=\s*(\d+)\s*$", re.MULTILINE)
_MUTATION_RE = re.compile(r"^\s*mutation_threshold\s*=\s*(\d+(?:\.\d+)?)", re.MULTILINE)


def _finding(
    *,
    kind: WeakeningKind,
    file: str,
    before: str,
    after: str,
    ctx: _DetectorContext,
    line: int | None = None,
) -> WeakeningFinding:
    return WeakeningFinding(
        kind=kind,
        file=file,
        line=line,
        before_value=before,
        after_value=after,
        has_loosening_approval=ctx.has_loosening_approval,
        blocking=not ctx.has_loosening_approval,
    )


# --------------------------------------------------------------------------- #
# Modified-file enumeration                                                   #
# --------------------------------------------------------------------------- #


def _diff_status(ctx: _DetectorContext) -> list[tuple[str, str]]:
    """Return ``[(status_char, path), …]`` from ``git diff --name-status``."""
    out = _git(ctx.repo_root, "diff", "--name-status", f"{ctx.base}..{ctx.head}")
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0][0], parts[-1]))
    return rows


# --------------------------------------------------------------------------- #
# Detector 1: deleted test file                                               #
# --------------------------------------------------------------------------- #


def _detect_deleted_test_files(ctx: _DetectorContext) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for status, path in _diff_status(ctx):
        if status == "D" and path.startswith("tests/") and path.endswith(".py"):
            findings.append(
                _finding(
                    kind=WeakeningKind.DELETED_TEST_FILE,
                    file=path,
                    before="<present>",
                    after="<deleted>",
                    ctx=ctx,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Detector 2: removed test function (AST diff)                                #
# --------------------------------------------------------------------------- #


def _top_level_test_functions(source: str) -> set[str]:
    """Return the set of top-level ``test_*`` function names in ``source``.

    TODO(#1113): class-scoped ``def test_*`` methods are not yet tracked.
    Out of scope per ADR-043 §6.4 v1; class-method AST diff adds a layer
    that needs to canonicalise method ownership (rename-vs-move).
    Followup: open as part of ADR-043 Phase 1 sub-issues under #1113.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    }


def _detect_removed_test_functions(ctx: _DetectorContext) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for status, path in _diff_status(ctx):
        if status != "M":
            continue
        if not (path.startswith("tests/") and path.endswith(".py")):
            continue
        base_src = _file_at_ref(ctx.repo_root, ctx.base, path)
        head_src = _file_at_ref(ctx.repo_root, ctx.head, path)
        removed = _top_level_test_functions(base_src) - _top_level_test_functions(head_src)
        for name in sorted(removed):
            findings.append(
                _finding(
                    kind=WeakeningKind.REMOVED_TEST_FUNCTION,
                    file=path,
                    before=name,
                    after="<removed>",
                    ctx=ctx,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Detector 3: lowered coverage threshold                                      #
# --------------------------------------------------------------------------- #


def _detect_lowered_coverage(ctx: _DetectorContext) -> list[WeakeningFinding]:
    base = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    bm = _COV_RE.search(base)
    hm = _COV_RE.search(head)
    if not bm or not hm:
        return []
    if float(hm.group(1)) >= float(bm.group(1)):
        return []
    return [
        _finding(
            kind=WeakeningKind.LOWERED_COVERAGE_THRESHOLD,
            file="pyproject.toml",
            before=bm.group(1),
            after=hm.group(1),
            ctx=ctx,
        )
    ]


# --------------------------------------------------------------------------- #
# Detector 4: lowered mutation threshold                                      #
# --------------------------------------------------------------------------- #


def _detect_lowered_mutation(ctx: _DetectorContext) -> list[WeakeningFinding]:
    base = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    bm = _MUTATION_RE.search(base)
    hm = _MUTATION_RE.search(head)
    if not bm or not hm:
        return []
    if float(hm.group(1)) >= float(bm.group(1)):
        return []
    return [
        _finding(
            kind=WeakeningKind.LOWERED_MUTATION_THRESHOLD,
            file="pyproject.toml",
            before=bm.group(1),
            after=hm.group(1),
            ctx=ctx,
        )
    ]


# --------------------------------------------------------------------------- #
# Detector 5: unjustified pytest.skip / pytest.xfail                          #
# --------------------------------------------------------------------------- #

# A "justified" skip/xfail has a ``reason=`` argument that mentions a
# ``#NNN`` issue ref. The base-vs-head delta is the NEW decorators added
# in head; existing ones are not re-policed.
_ISSUE_REF_RE = re.compile(r"#\d+")


def _decorators_in(source: str) -> set[tuple[str, str | None]]:
    """Return ``{(decorator_name, reason_value), …}``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    out: set[tuple[str, str | None]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            qual = _qualified_decorator_name(dec)
            if qual not in {"pytest.mark.skip", "pytest.mark.xfail", "pytest.skip", "pytest.xfail"}:
                continue
            reason: str | None = None
            call = dec if isinstance(dec, ast.Call) else None
            if call is not None:
                for kw in call.keywords:
                    if kw.arg == "reason" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        reason = kw.value.value
            out.add((qual, reason))
    return out


def _qualified_decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.expr = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _detect_unjustified_skip_xfail(ctx: _DetectorContext) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for status, path in _diff_status(ctx):
        if status not in {"M", "A"}:
            continue
        if not path.endswith(".py"):
            continue
        base_src = _file_at_ref(ctx.repo_root, ctx.base, path) if status == "M" else ""
        head_src = _file_at_ref(ctx.repo_root, ctx.head, path)
        new_decs = _decorators_in(head_src) - _decorators_in(base_src)
        for qual, reason in sorted(new_decs):
            if reason and _ISSUE_REF_RE.search(reason):
                continue
            findings.append(
                _finding(
                    kind=WeakeningKind.UNJUSTIFIED_SKIP_OR_XFAIL,
                    file=path,
                    before="<absent>",
                    after=qual + (f"(reason={reason!r})" if reason else ""),
                    ctx=ctx,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Detector 6: disabled lint rule (ruff select shrink / ignore grow)           #
# --------------------------------------------------------------------------- #


def _ruff_arrays(text: str, key: str) -> set[str]:
    select_re = re.compile(r"\[tool\.ruff(?:\.lint)?\]\s*?\n.*?(?=^\[|\Z)", re.DOTALL | re.MULTILINE)
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


def _detect_disabled_lint_rule(ctx: _DetectorContext) -> list[WeakeningFinding]:
    base = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    findings: list[WeakeningFinding] = []
    removed_select = sorted(_ruff_arrays(base, "select") - _ruff_arrays(head, "select"))
    added_ignore = sorted(_ruff_arrays(head, "ignore") - _ruff_arrays(base, "ignore"))
    for rule in removed_select:
        findings.append(
            _finding(
                kind=WeakeningKind.DISABLED_LINT_RULE,
                file="pyproject.toml",
                before=f"select+={rule}",
                after=f"select-={rule}",
                ctx=ctx,
            )
        )
    for rule in added_ignore:
        findings.append(
            _finding(
                kind=WeakeningKind.DISABLED_LINT_RULE,
                file="pyproject.toml",
                before=f"ignore-={rule}",
                after=f"ignore+={rule}",
                ctx=ctx,
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Detector 7: disabled type-check flag                                        #
# --------------------------------------------------------------------------- #


def _detect_disabled_typecheck_flag(ctx: _DetectorContext) -> list[WeakeningFinding]:
    base = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    flag_re = re.compile(r"^\s*(strict[_a-z]*|disallow_[_a-z]+)\s*=\s*(true|false)", re.MULTILINE)
    base_flags = dict(flag_re.findall(base))
    head_flags = dict(flag_re.findall(head))
    findings: list[WeakeningFinding] = []
    for flag, base_val in base_flags.items():
        head_val = head_flags.get(flag, base_val)
        if base_val == "true" and head_val == "false":
            findings.append(
                _finding(
                    kind=WeakeningKind.DISABLED_TYPECHECK_FLAG,
                    file="pyproject.toml",
                    before=f"{flag}=true",
                    after=f"{flag}=false",
                    ctx=ctx,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Detector 8: disabled pre-commit hook                                        #
# --------------------------------------------------------------------------- #


def _detect_disabled_precommit_hook(ctx: _DetectorContext) -> list[WeakeningFinding]:
    base = _file_at_ref(ctx.repo_root, ctx.base, ".pre-commit-config.yaml")
    head = _file_at_ref(ctx.repo_root, ctx.head, ".pre-commit-config.yaml")
    if not base or not head:
        return []
    pattern = re.compile(r"^\s*-\s*id:\s*(\S+)", re.MULTILINE)
    removed = sorted(set(pattern.findall(base)) - set(pattern.findall(head)))
    return [
        _finding(
            kind=WeakeningKind.DISABLED_PRECOMMIT_HOOK,
            file=".pre-commit-config.yaml",
            before=name,
            after="<removed>",
            ctx=ctx,
        )
        for name in removed
    ]


# --------------------------------------------------------------------------- #
# Detector 9: removed CI job                                                  #
# --------------------------------------------------------------------------- #


def _jobs_in(text: str) -> set[str]:
    if "jobs:" not in text:
        return set()
    after = text.split("jobs:", 1)[1]
    out: set[str] = set()
    for line in after.splitlines():
        m = re.match(r"^\s\s([A-Za-z][A-Za-z0-9_-]*):", line)
        if m:
            out.add(m.group(1))
    return out


def _detect_removed_ci_job(ctx: _DetectorContext) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    base_listing = _git(ctx.repo_root, "ls-tree", "--name-only", "-r", ctx.base, ".github/workflows/")
    head_listing = _git(ctx.repo_root, "ls-tree", "--name-only", "-r", ctx.head, ".github/workflows/")
    base_files = {ln.strip() for ln in base_listing.splitlines() if ln.strip().endswith(".yml")}
    head_files = {ln.strip() for ln in head_listing.splitlines() if ln.strip().endswith(".yml")}
    for path in sorted(base_files | head_files):
        base_jobs = _jobs_in(_file_at_ref(ctx.repo_root, ctx.base, path)) if path in base_files else set()
        head_jobs = _jobs_in(_file_at_ref(ctx.repo_root, ctx.head, path)) if path in head_files else set()
        for job in sorted(base_jobs - head_jobs):
            findings.append(
                _finding(
                    kind=WeakeningKind.REMOVED_CI_JOB,
                    file=path,
                    before=job,
                    after="<removed>",
                    ctx=ctx,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Detector 10: increased pytest timeout                                       #
# --------------------------------------------------------------------------- #


def _detect_increased_pytest_timeout(ctx: _DetectorContext) -> list[WeakeningFinding]:
    base = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    bm = _TIMEOUT_RE.search(base)
    hm = _TIMEOUT_RE.search(head)
    if not bm or not hm:
        return []
    if int(hm.group(1)) <= int(bm.group(1)):
        return []
    return [
        _finding(
            kind=WeakeningKind.INCREASED_PYTEST_TIMEOUT,
            file="pyproject.toml",
            before=bm.group(1),
            after=hm.group(1),
            ctx=ctx,
        )
    ]


# --------------------------------------------------------------------------- #
# Detector 11: expanded exemption paths (governs.exclusions in ADR/spec)      #
# --------------------------------------------------------------------------- #


def _detect_expanded_exemption_paths(ctx: _DetectorContext) -> list[WeakeningFinding]:
    """Detect growth in any ``governs.exclusions`` list inside ADR/spec frontmatter.

    The §6.4 table refers to ADR-042 §27 exemptions; the canonical knob
    on a per-ADR / per-spec basis is the ``governs.exclusions`` array in
    its frontmatter. Naïve string-diff on the YAML frontmatter is enough
    for the v1 detector — pydantic parsing belongs to the
    ``frontmatter_lint`` tool (Phase 1F).
    """
    findings: list[WeakeningFinding] = []
    exclusions_re = re.compile(r"exclusions:\s*\n((?:\s+-\s+.+\n)+)")
    for status, path in _diff_status(ctx):
        if status not in {"M"}:
            continue
        if not (path.startswith("docs/adr/") or path.startswith("docs/specs/")) or not path.endswith(".md"):
            continue
        base = _file_at_ref(ctx.repo_root, ctx.base, path)
        head = _file_at_ref(ctx.repo_root, ctx.head, path)
        base_set = _exclusion_entries(base, exclusions_re)
        head_set = _exclusion_entries(head, exclusions_re)
        added = sorted(head_set - base_set)
        for entry in added:
            findings.append(
                _finding(
                    kind=WeakeningKind.EXPANDED_EXEMPTION_PATHS,
                    file=path,
                    before="<not exempt>",
                    after=entry,
                    ctx=ctx,
                )
            )
    return findings


def _exclusion_entries(text: str, exclusions_re: re.Pattern[str]) -> set[str]:
    out: set[str] = set()
    for block in exclusions_re.findall(text):
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("-"):
                out.add(line[1:].strip().strip('"').strip("'"))
    return out


# --------------------------------------------------------------------------- #
# Detector 12: expanded noqa usage                                            #
# --------------------------------------------------------------------------- #

_NOQA_LINE_RE = re.compile(r"#\s*noqa(?::[A-Z0-9, ]*)?")
_NOQA_WITH_ISSUE_RE = re.compile(r"#\s*noqa[^\n]*#\d+")


def _detect_expanded_noqa(ctx: _DetectorContext) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for status, path in _diff_status(ctx):
        if status not in {"M", "A"}:
            continue
        if not path.endswith(".py"):
            continue
        base = _file_at_ref(ctx.repo_root, ctx.base, path) if status == "M" else ""
        head = _file_at_ref(ctx.repo_root, ctx.head, path)
        base_count = len(_NOQA_LINE_RE.findall(base))
        head_lines = head.splitlines()
        head_count = 0
        unjustified = 0
        for line in head_lines:
            if _NOQA_LINE_RE.search(line):
                head_count += 1
                if not _NOQA_WITH_ISSUE_RE.search(line):
                    unjustified += 1
        if head_count > base_count and unjustified > 0:
            findings.append(
                _finding(
                    kind=WeakeningKind.EXPANDED_NOQA_USAGE,
                    file=path,
                    before=f"{base_count} noqa",
                    after=f"{head_count} noqa ({unjustified} without issue ref)",
                    ctx=ctx,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Detector 13: reduced required-skill list                                    #
# --------------------------------------------------------------------------- #


def _detect_reduced_skill_list(ctx: _DetectorContext) -> list[WeakeningFinding]:
    base = _file_at_ref(ctx.repo_root, ctx.base, "docs/skills/required.yaml")
    head = _file_at_ref(ctx.repo_root, ctx.head, "docs/skills/required.yaml")
    if not base or not head:
        return []
    pattern = re.compile(r"^\s*-\s+(.+)\s*$", re.MULTILINE)

    def _entries(text: str) -> set[str]:
        return {m.group(1).strip().strip('"').strip("'") for m in pattern.finditer(text)}

    removed = sorted(_entries(base) - _entries(head))
    return [
        _finding(
            kind=WeakeningKind.REDUCED_SKILL_LIST,
            file="docs/skills/required.yaml",
            before=name,
            after="<removed>",
            ctx=ctx,
        )
        for name in removed
    ]


# --------------------------------------------------------------------------- #
# Detector 14: reduced honeypot canary count                                  #
# --------------------------------------------------------------------------- #


def _detect_reduced_honeypot_count(ctx: _DetectorContext) -> list[WeakeningFinding]:
    base = _file_at_ref(ctx.repo_root, ctx.base, ".governance-paths.yaml")
    head = _file_at_ref(ctx.repo_root, ctx.head, ".governance-paths.yaml")
    if not base or not head:
        return []
    base_count = sum(1 for ln in base.splitlines() if ln.lstrip().startswith("- path:"))
    head_count = sum(1 for ln in head.splitlines() if ln.lstrip().startswith("- path:"))
    if head_count >= base_count:
        return []
    return [
        _finding(
            kind=WeakeningKind.REDUCED_HONEYPOT_COUNT,
            file=".governance-paths.yaml",
            before=str(base_count),
            after=str(head_count),
            ctx=ctx,
        )
    ]


# --------------------------------------------------------------------------- #
# Registry                                                                    #
# --------------------------------------------------------------------------- #

_DETECTORS: list[Callable[[_DetectorContext], list[WeakeningFinding]]] = [
    _detect_deleted_test_files,
    _detect_removed_test_functions,
    _detect_lowered_coverage,
    _detect_lowered_mutation,
    _detect_unjustified_skip_xfail,
    _detect_disabled_lint_rule,
    _detect_disabled_typecheck_flag,
    _detect_disabled_precommit_hook,
    _detect_removed_ci_job,
    _detect_increased_pytest_timeout,
    _detect_expanded_exemption_paths,
    _detect_expanded_noqa,
    _detect_reduced_skill_list,
    _detect_reduced_honeypot_count,
]


# --------------------------------------------------------------------------- #
# Public entry-point                                                          #
# --------------------------------------------------------------------------- #


def check_weakened_ci(
    base: str,
    head: str,
    *,
    repo_root: Path | None = None,
) -> list[WeakeningFinding]:
    """Detect CI-weakening across the 14 §6.4 patterns.

    Each finding's :attr:`WeakeningFinding.blocking` flag is ``True``
    unless the commit message between ``base`` and ``head`` carries the
    §3.4.2 ritual (``Loosening-Approved:`` + ``Loosening-Reason:``).
    The CI workflow is the authoritative gate; it OR's
    ``has_loosening_approval`` with the contradiction-audit + companion-
    addendum status to compute the merge gate.
    """
    repo_root = (repo_root or Path.cwd()).resolve()
    ctx = _DetectorContext(
        repo_root=repo_root,
        base=base,
        head=head,
        has_loosening_approval=_has_loosening_ritual(repo_root, base, head),
    )
    findings: list[WeakeningFinding] = []
    for det in _DETECTORS:
        findings.extend(det(ctx))
    return findings


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.weakened_ci_check",
        description="CI-weakening detector (ADR-043 §6.4).",
    )
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root or Path.cwd()).resolve()
    findings = check_weakened_ci(args.base, args.head, repo_root=repo_root)
    blocking = [f for f in findings if f.blocking]
    for f in findings:
        print(f.model_dump_json(), file=sys.stderr if f.blocking else sys.stdout)
    return 1 if blocking else 0


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
