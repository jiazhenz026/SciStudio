"""Weakened-CI automatic block (ADR-043 §6.4).

A PR that weakens CI in any of the 14 patterns enumerated in §6.4 is a
blocker. Full stop. The only valid escape is the three-part loosening
ritual from §3.4.2: ``Loosening-Approved: @<Tier2>`` + companion
addendum + clean contradiction audit.

This module performs the diff-time detection between two git refs and
returns a list of
:class:`scieasy.qa.schemas.governance.WeakeningFinding` records.

Entry-point (ADR-043 §4.7 audit fix F14)::

    verify_no_weakening(base_ref: str = "main", head_ref: str = "HEAD")
        -> list[WeakeningFinding]

14 detected patterns (§6.4 table)
---------------------------------

1.  ``deleted-test-file`` — ``git diff --diff-filter=D tests/**/*.py``.
2.  ``removed-test-function`` — AST diff: function present at base,
    absent at head, in a test file.
3.  ``lowered-coverage-threshold`` — ``pyproject.toml``
    ``--cov-fail-under`` numeric decrease.
4.  ``lowered-mutation-threshold`` — §4.5 numeric mutation-score
    threshold decrease (mutmut / mutation-score config). v1 detects
    only explicit numeric keys in ``pyproject.toml``; full mutmut
    integration ships in Phase 1F (TODO).
5.  ``unjustified-skip-or-xfail`` — new ``@pytest.mark.skip`` /
    ``@pytest.mark.xfail`` markers without a ``reason=`` argument that
    cites a ``#NNN`` issue reference.
6.  ``disabled-lint-rule`` — ``[tool.ruff.lint]`` ``select`` shrinks
    OR ``ignore`` grows.
7.  ``disabled-typecheck-flag`` — any mypy / pyright strict-* flag
    flipped from ``true`` to ``false``.
8.  ``disabled-precommit-hook`` — ``.pre-commit-config.yaml`` hook
    removal.
9.  ``removed-ci-job`` — ``.github/workflows/*.yml`` job deletion.
10. ``increased-pytest-timeout`` — ``timeout = N`` value increase in
    ``pyproject.toml``.
11. ``expanded-exemption-paths`` — ``governs.exclusions`` /
    ADR-042 §27 exemptions list growth.
12. ``expanded-noqa-usage`` — inline ``# noqa`` count growth where the
    new line does not cite a ``#NNN`` issue link.
13. ``reduced-skill-list`` — ``docs/skills/required.yaml`` entry
    removal (ADR-042 §17 mirror).
14. ``reduced-honeypot-count`` — ``.governance-paths.yaml``
    ``honeypot_canaries:`` entry-count decrease.

Approval ritual
---------------

If at least one weakening is detected but the commit messages between
``base`` and ``head`` carry a ``Loosening-Approved: @<handle>`` trailer,
each finding's ``has_loosening_approval`` is set to ``True`` and
``blocking`` is set to ``False`` for **detection** purposes. The full
§3.4.2 ritual (Tier-2 verification of the approver + companion-
addendum PR + clean contradiction audit) is a CI-side check performed
by :mod:`scieasy.qa.governance.mod_pr_check` — this module only
records whether the trailer is present.

Authority limits
----------------

This is a static, regex-and-AST-driven detector. False negatives
(weakenings that slip through) are acceptable for v1 — the §3.5
recursive workflow runs the full contradiction audit on the same
diff as a safety net. The high-value cases are the explicit numeric
thresholds, the hook/job/skill-list shrinks, and the AST-detectable
skip/xfail additions.

Independence from §3.4
----------------------

This check is **independent** of and **stricter than** the §3.4
monotonic check: §3.4 covers all 14 governance axes (some of which
overlap with CI weakening), while §6.4 specifically focuses on CI
weakening because GitHub's 2026 agent-PR analysis identified it as
the highest-frequency-and-impact failure mode.

References
----------
ADR-043 §6.4 (lines 1602-1676) — authoritative spec + 14-row table.
ADR-043 §6.4.1 (lines 1640-1675) — :class:`WeakeningKind` /
:class:`WeakeningFinding` schemas (shipped in §3.4.3 / Phase 1A-c).
ADR-043 §4.7 line 1206 — entry-point signature.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scieasy.qa.schemas.governance import WeakeningFinding, WeakeningKind

# --------------------------------------------------------------------------- #
# Approval trailer                                                            #
# --------------------------------------------------------------------------- #

_LOOSENING_APPROVED_RE = re.compile(
    r"^Loosening-Approved:\s*(@[A-Za-z0-9][A-Za-z0-9_-]*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# --------------------------------------------------------------------------- #
# Git helpers                                                                 #
# --------------------------------------------------------------------------- #


def _git(repo_root: Path, *args: str) -> str:
    """Run ``git *args`` in ``repo_root`` and return stdout (or empty)."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, UnicodeDecodeError):
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout or ""


def _file_at_ref(repo_root: Path, ref: str, path: str) -> str:
    """Return contents of ``path`` at ``ref`` or ``""`` if absent."""
    return _git(repo_root, "show", f"{ref}:{path}")


def _changed_files(repo_root: Path, base: str, head: str, *filters: str) -> list[str]:
    """Return files changed between ``base...head`` (three-dot merge-base diff).

    Uses ``git diff --name-only base...head`` (three dots) so only commits
    reachable from *head* but not from *base* are included.  Two-dot diff
    would include commits on *base* that are not in *head*'s ancestry, which
    falsely flags out-of-date feature branches as touching governance paths
    (#1180).

    ``filters`` is forwarded to ``git diff --diff-filter=...`` if any
    single-letter filter codes are present, else used as raw extra args.
    """
    args: list[str] = ["diff", "--name-only", f"{base}...{head}"]
    for f in filters:
        args.append(f)
    out = _git(repo_root, *args)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _deleted_files(repo_root: Path, base: str, head: str) -> list[str]:
    """Return files deleted between ``base...head`` (three-dot merge-base diff).

    Uses three-dot syntax for the same reason as :func:`_changed_files` (#1180).
    """
    out = _git(
        repo_root,
        "diff",
        "--name-only",
        "--diff-filter=D",
        f"{base}...{head}",
    )
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _commit_message_between(repo_root: Path, base: str, head: str) -> str:
    """Return concatenated commit messages between ``base`` and ``head``."""
    return _git(repo_root, "log", f"{base}..{head}", "--format=%B")


# --------------------------------------------------------------------------- #
# Detector context                                                            #
# --------------------------------------------------------------------------- #


@dataclass
class _Ctx:
    repo_root: Path
    base: str
    head: str
    changed: list[str]
    deleted: list[str]


# --------------------------------------------------------------------------- #
# Pattern 1 — deleted-test-file                                               #
# --------------------------------------------------------------------------- #


def _is_test_path(p: str) -> bool:
    """Return True when ``p`` looks like a pytest discovery target."""
    parts = p.replace("\\", "/").split("/")
    if not p.endswith(".py"):
        return False
    if "tests" not in parts:
        return False
    name = parts[-1]
    return name.startswith("test_") or name.endswith("_test.py")


def _detect_deleted_test_file(ctx: _Ctx) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for f in ctx.deleted:
        if _is_test_path(f):
            findings.append(
                WeakeningFinding(
                    kind=WeakeningKind.DELETED_TEST_FILE,
                    file=f,
                    line=None,
                    before_value="<present>",
                    after_value="<deleted>",
                    has_loosening_approval=False,
                    blocking=True,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Pattern 2 — removed-test-function (AST diff)                                #
# --------------------------------------------------------------------------- #


def _module_test_functions(src: str) -> set[str]:
    """Return set of top-level ``def test_*`` / ``async def test_*`` names."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_"):
            out.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for inner in node.body:
                if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef) and inner.name.startswith("test_"):
                    out.add(f"{node.name}::{inner.name}")
    return out


def _detect_removed_test_function(ctx: _Ctx) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for f in ctx.changed:
        if f in ctx.deleted:
            continue  # already reported as deleted-test-file
        if not _is_test_path(f):
            continue
        base_src = _file_at_ref(ctx.repo_root, ctx.base, f)
        head_src = _file_at_ref(ctx.repo_root, ctx.head, f)
        if not base_src:
            continue
        base_fns = _module_test_functions(base_src)
        head_fns = _module_test_functions(head_src)
        removed = sorted(base_fns - head_fns)
        for name in removed:
            findings.append(
                WeakeningFinding(
                    kind=WeakeningKind.REMOVED_TEST_FUNCTION,
                    file=f,
                    line=None,
                    before_value=name,
                    after_value="<removed>",
                    has_loosening_approval=False,
                    blocking=True,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Pattern 3 — lowered-coverage-threshold                                      #
# --------------------------------------------------------------------------- #

_COV_RE = re.compile(r"--cov-fail-under=(\d+(?:\.\d+)?)")


def _detect_lowered_coverage(ctx: _Ctx) -> list[WeakeningFinding]:
    base_txt = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head_txt = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    bm = _COV_RE.search(base_txt)
    hm = _COV_RE.search(head_txt)
    if not bm or not hm:
        return []
    if float(hm.group(1)) >= float(bm.group(1)):
        return []
    return [
        WeakeningFinding(
            kind=WeakeningKind.LOWERED_COVERAGE_THRESHOLD,
            file="pyproject.toml",
            line=None,
            before_value=bm.group(1),
            after_value=hm.group(1),
            has_loosening_approval=False,
            blocking=True,
        )
    ]


# --------------------------------------------------------------------------- #
# Pattern 4 — lowered-mutation-threshold                                      #
# --------------------------------------------------------------------------- #

# Match explicit numeric mutation-score thresholds. Common keys:
#   minimum-score = NN
#   mutation_score_threshold = NN
#   mutation-score-threshold = NN
_MUT_RE = re.compile(
    r"^\s*(?:minimum-score|mutation[_-]score[_-]threshold)\s*=\s*(\d+(?:\.\d+)?)",
    re.MULTILINE,
)


def _detect_lowered_mutation_threshold(ctx: _Ctx) -> list[WeakeningFinding]:
    # TODO(#1113): full mutmut integration ships in Phase 1F. v1 detects
    # only the explicit numeric threshold key in pyproject.toml.
    #   Out of scope per ADR-043 §6.4 row 4 / Phase 1F deliverable.
    #   Followup: open as part of ADR-043 Phase 1F sub-issues under #1113.
    base_txt = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head_txt = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    bm = _MUT_RE.search(base_txt)
    hm = _MUT_RE.search(head_txt)
    if not bm or not hm:
        return []
    if float(hm.group(1)) >= float(bm.group(1)):
        return []
    return [
        WeakeningFinding(
            kind=WeakeningKind.LOWERED_MUTATION_THRESHOLD,
            file="pyproject.toml",
            line=None,
            before_value=bm.group(1),
            after_value=hm.group(1),
            has_loosening_approval=False,
            blocking=True,
        )
    ]


# --------------------------------------------------------------------------- #
# Pattern 5 — unjustified-skip-or-xfail                                       #
# --------------------------------------------------------------------------- #


def _skip_xfail_decorators(src: str) -> set[tuple[str, str]]:
    """Return ``{(qualname, reason)}`` for every skip/xfail decorator.

    ``qualname`` identifies the function (``test_x`` or ``TestY::test_x``).
    ``reason`` is the literal value of a ``reason=`` keyword arg, or
    ``""`` when absent.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()

    out: set[tuple[str, str]] = set()

    def _walk(node: ast.AST, container_prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                qn = f"{container_prefix}{child.name}" if container_prefix else child.name
                for dec in child.decorator_list:
                    reason = _extract_skip_xfail(dec)
                    if reason is not None:
                        out.add((qn, reason))
            elif isinstance(child, ast.ClassDef):
                _walk(child, container_prefix=f"{child.name}::")

    _walk(tree)
    return out


def _extract_skip_xfail(dec: ast.expr) -> str | None:
    """Return reason= for skip/xfail decorators, ``""`` if no reason, else None."""
    # Forms accepted:
    #   @pytest.mark.skip
    #   @pytest.mark.skip(reason="...")
    #   @pytest.mark.skipif(..., reason="...")
    #   @pytest.mark.xfail
    #   @pytest.mark.xfail(reason="...")
    name: str | None = None
    keywords: list[ast.keyword] = []

    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Attribute):
        # walk ``pytest.mark.skip`` style
        attr_chain: list[str] = []
        cur: ast.AST = target
        while isinstance(cur, ast.Attribute):
            attr_chain.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            attr_chain.append(cur.id)
        attr_chain.reverse()
        # Want ``mark.skip``, ``mark.skipif``, ``mark.xfail`` suffixes
        if len(attr_chain) >= 2 and attr_chain[-2] == "mark":
            tail = attr_chain[-1]
            if tail in {"skip", "skipif", "xfail"}:
                name = tail
    if name is None:
        return None
    if isinstance(dec, ast.Call):
        keywords = list(dec.keywords)
    reason = ""
    for kw in keywords:
        if kw.arg == "reason" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            reason = kw.value.value
            break
    return reason


_ISSUE_REF_RE = re.compile(r"#\d+")


def _detect_unjustified_skip_xfail(ctx: _Ctx) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for f in ctx.changed:
        if f in ctx.deleted:
            continue
        if not _is_test_path(f):
            continue
        base_src = _file_at_ref(ctx.repo_root, ctx.base, f)
        head_src = _file_at_ref(ctx.repo_root, ctx.head, f)
        if not head_src:
            continue
        base_set = _skip_xfail_decorators(base_src)
        head_set = _skip_xfail_decorators(head_src)
        new_markers = head_set - base_set
        for qn, reason in sorted(new_markers):
            if reason and _ISSUE_REF_RE.search(reason):
                continue  # justified
            findings.append(
                WeakeningFinding(
                    kind=WeakeningKind.UNJUSTIFIED_SKIP_OR_XFAIL,
                    file=f,
                    line=None,
                    before_value="<no-marker>",
                    after_value=f"{qn} reason={reason!r}",
                    has_loosening_approval=False,
                    blocking=True,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Pattern 6 — disabled-lint-rule (ruff)                                       #
# --------------------------------------------------------------------------- #


def _ruff_lint_block(src: str) -> tuple[set[str], set[str]]:
    """Return (``select`` set, ``ignore`` set) for ``[tool.ruff.lint]``.

    Simple line-based parser (avoids adding tomli/tomllib dependency in
    a context that only needs set membership). The parser is intentional
    in only catching the common single-line list forms; multi-line
    arrays are flattened by accumulating until the closing bracket.
    """
    select: set[str] = set()
    ignore: set[str] = set()
    in_lint = False
    current: str | None = None  # 'select' or 'ignore'
    buf = ""
    for raw in src.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("["):
            in_lint = stripped == "[tool.ruff.lint]"
            current = None
            buf = ""
            continue
        if not in_lint:
            continue
        if current is None:
            for key, target in (("select", select), ("ignore", ignore)):
                m = re.match(rf"{key}\s*=\s*(.*)$", stripped)
                if m:
                    current = key
                    buf = m.group(1)
                    if buf.count("[") == buf.count("]") and "]" in buf:
                        _consume(buf, target)
                        current = None
                        buf = ""
                    break
        else:
            buf += " " + stripped
            target = select if current == "select" else ignore
            if buf.count("[") == buf.count("]") and "]" in buf:
                _consume(buf, target)
                current = None
                buf = ""
    return select, ignore


def _consume(buf: str, target: set[str]) -> None:
    """Parse ``[...]`` style array into ``target`` set."""
    # Drop the brackets and split on commas; ignore comments.
    inner = buf[buf.find("[") + 1 : buf.rfind("]")]
    # Strip inline comments
    inner = re.sub(r"#.*$", "", inner, flags=re.MULTILINE)
    for piece in inner.split(","):
        item = piece.strip().strip("'\"")
        if item:
            target.add(item)


def _detect_disabled_lint_rule(ctx: _Ctx) -> list[WeakeningFinding]:
    base_txt = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head_txt = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    if not base_txt or not head_txt:
        return []
    base_select, base_ignore = _ruff_lint_block(base_txt)
    head_select, head_ignore = _ruff_lint_block(head_txt)
    findings: list[WeakeningFinding] = []
    select_removed = sorted(base_select - head_select)
    ignore_added = sorted(head_ignore - base_ignore)
    if select_removed:
        findings.append(
            WeakeningFinding(
                kind=WeakeningKind.DISABLED_LINT_RULE,
                file="pyproject.toml",
                line=None,
                before_value="select+=" + ",".join(select_removed),
                after_value="<removed>",
                has_loosening_approval=False,
                blocking=True,
            )
        )
    if ignore_added:
        findings.append(
            WeakeningFinding(
                kind=WeakeningKind.DISABLED_LINT_RULE,
                file="pyproject.toml",
                line=None,
                before_value="ignore",
                after_value="ignore+=" + ",".join(ignore_added),
                has_loosening_approval=False,
                blocking=True,
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Pattern 7 — disabled-typecheck-flag                                         #
# --------------------------------------------------------------------------- #

# Match e.g.  strict_optional = true   |   strict = true   |   reportGeneralTypeIssues = "error"
# Also accepts JSON syntax (``"key": "value"`` for pyrightconfig.json).
_TYPECHECK_FLAG_RE = re.compile(
    r"^\s*\"?(strict[_a-zA-Z]*|disallow_[a-zA-Z_]+|warn_[a-zA-Z_]+|report[A-Z][A-Za-z_]+)\"?"
    r"\s*[=:]\s*(true|false|\"error\"|\"warning\"|\"none\")",
    re.MULTILINE,
)


def _typecheck_flags(src: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _TYPECHECK_FLAG_RE.finditer(src):
        out[m.group(1)] = m.group(2)
    return out


def _detect_disabled_typecheck_flag(ctx: _Ctx) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for f in ("pyproject.toml", "mypy.ini", "pyrightconfig.json"):
        base_txt = _file_at_ref(ctx.repo_root, ctx.base, f)
        head_txt = _file_at_ref(ctx.repo_root, ctx.head, f)
        if not base_txt or not head_txt:
            continue
        bf = _typecheck_flags(base_txt)
        hf = _typecheck_flags(head_txt)
        for key, bval in bf.items():
            hval = hf.get(key)
            if hval is None:
                continue
            if bval == "true" and hval == "false":
                findings.append(
                    WeakeningFinding(
                        kind=WeakeningKind.DISABLED_TYPECHECK_FLAG,
                        file=f,
                        line=None,
                        before_value=f"{key}=true",
                        after_value=f"{key}=false",
                        has_loosening_approval=False,
                        blocking=True,
                    )
                )
            elif bval == '"error"' and hval in {'"warning"', '"none"'}:
                findings.append(
                    WeakeningFinding(
                        kind=WeakeningKind.DISABLED_TYPECHECK_FLAG,
                        file=f,
                        line=None,
                        before_value=f"{key}={bval}",
                        after_value=f"{key}={hval}",
                        has_loosening_approval=False,
                        blocking=True,
                    )
                )
    return findings


# --------------------------------------------------------------------------- #
# Pattern 8 — disabled-precommit-hook                                         #
# --------------------------------------------------------------------------- #

_HOOK_ID_RE = re.compile(r"^\s*-\s*id:\s*(\S+)\s*$", re.MULTILINE)


def _precommit_hooks(src: str) -> set[str]:
    return set(_HOOK_ID_RE.findall(src))


def _detect_disabled_precommit_hook(ctx: _Ctx) -> list[WeakeningFinding]:
    base_txt = _file_at_ref(ctx.repo_root, ctx.base, ".pre-commit-config.yaml")
    head_txt = _file_at_ref(ctx.repo_root, ctx.head, ".pre-commit-config.yaml")
    if not base_txt or not head_txt:
        return []
    removed = sorted(_precommit_hooks(base_txt) - _precommit_hooks(head_txt))
    return [
        WeakeningFinding(
            kind=WeakeningKind.DISABLED_PRECOMMIT_HOOK,
            file=".pre-commit-config.yaml",
            line=None,
            before_value=hook,
            after_value="<removed>",
            has_loosening_approval=False,
            blocking=True,
        )
        for hook in removed
    ]


# --------------------------------------------------------------------------- #
# Pattern 9 — removed-ci-job                                                  #
# --------------------------------------------------------------------------- #


def _workflow_jobs(src: str) -> set[str]:
    """Return job names listed under ``jobs:`` in a GitHub workflow YAML."""
    if "jobs:" not in src:
        return set()
    after = src.split("jobs:", 1)[1]
    out: set[str] = set()
    for line in after.splitlines():
        if not line.startswith("  "):
            continue
        m = re.match(r"^  ([A-Za-z][A-Za-z0-9_-]*):", line)
        if m:
            out.add(m.group(1))
    return out


def _detect_removed_ci_job(ctx: _Ctx) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    workflow_files: set[str] = set()
    for f in ctx.changed:
        nf = f.replace("\\", "/")
        if nf.startswith(".github/workflows/") and (nf.endswith(".yml") or nf.endswith(".yaml")):
            workflow_files.add(nf)
    for f in ctx.deleted:
        nf = f.replace("\\", "/")
        if nf.startswith(".github/workflows/") and (nf.endswith(".yml") or nf.endswith(".yaml")):
            workflow_files.add(nf)
    for f in sorted(workflow_files):
        base_src = _file_at_ref(ctx.repo_root, ctx.base, f)
        head_src = _file_at_ref(ctx.repo_root, ctx.head, f)
        base_jobs = _workflow_jobs(base_src)
        head_jobs = _workflow_jobs(head_src) if head_src else set()
        removed = sorted(base_jobs - head_jobs)
        for job in removed:
            findings.append(
                WeakeningFinding(
                    kind=WeakeningKind.REMOVED_CI_JOB,
                    file=f,
                    line=None,
                    before_value=job,
                    after_value="<removed>",
                    has_loosening_approval=False,
                    blocking=True,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Pattern 10 — increased-pytest-timeout                                       #
# --------------------------------------------------------------------------- #

_TIMEOUT_RE = re.compile(r"^\s*timeout\s*=\s*(\d+)\s*$", re.MULTILINE)


def _detect_increased_pytest_timeout(ctx: _Ctx) -> list[WeakeningFinding]:
    base_txt = _file_at_ref(ctx.repo_root, ctx.base, "pyproject.toml")
    head_txt = _file_at_ref(ctx.repo_root, ctx.head, "pyproject.toml")
    bm = _TIMEOUT_RE.search(base_txt)
    hm = _TIMEOUT_RE.search(head_txt)
    if not bm or not hm:
        return []
    if int(hm.group(1)) <= int(bm.group(1)):
        return []
    return [
        WeakeningFinding(
            kind=WeakeningKind.INCREASED_PYTEST_TIMEOUT,
            file="pyproject.toml",
            line=None,
            before_value=bm.group(1),
            after_value=hm.group(1),
            has_loosening_approval=False,
            blocking=True,
        )
    ]


# --------------------------------------------------------------------------- #
# Pattern 11 — expanded-exemption-paths                                       #
# --------------------------------------------------------------------------- #

# We pattern-match against any line of the shape  - "<glob>"  inside an
# ``exclusions:`` or ``governs.exclusions:`` block. Implementation kept
# simple — detect growth in the count of ``- ...`` lines under any
# ``exclusions:`` block in .governance-paths.yaml or
# docs/governance/exemptions.yaml.

_EXCLUSION_LIST_RE = re.compile(r"^\s*-\s+\"?([^\"\s][^\"\n]*?)\"?\s*$", re.MULTILINE)


def _exclusion_entries(src: str) -> set[str]:
    """Return entries listed under any top-level ``exclusions:`` block."""
    if "exclusions:" not in src:
        return set()
    out: set[str] = set()
    in_block = False
    base_indent = 0
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("exclusions:"):
            in_block = True
            base_indent = len(line) - len(stripped)
            continue
        if not in_block:
            continue
        if not line.strip():
            continue
        # block ends when we hit a line at or below the parent indent
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent and not stripped.startswith("- "):
            in_block = False
            continue
        m = _EXCLUSION_LIST_RE.match(line)
        if m:
            out.add(m.group(1).strip())
    return out


def _detect_expanded_exemption_paths(ctx: _Ctx) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    for f in (".governance-paths.yaml", "docs/governance/exemptions.yaml"):
        base_txt = _file_at_ref(ctx.repo_root, ctx.base, f)
        head_txt = _file_at_ref(ctx.repo_root, ctx.head, f)
        if not base_txt and not head_txt:
            continue
        base_set = _exclusion_entries(base_txt)
        head_set = _exclusion_entries(head_txt)
        added = sorted(head_set - base_set)
        for entry in added:
            findings.append(
                WeakeningFinding(
                    kind=WeakeningKind.EXPANDED_EXEMPTION_PATHS,
                    file=f,
                    line=None,
                    before_value="<absent>",
                    after_value=entry,
                    has_loosening_approval=False,
                    blocking=True,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Pattern 12 — expanded-noqa-usage                                            #
# --------------------------------------------------------------------------- #

_NOQA_RE = re.compile(r"#\s*noqa(?::\s*[A-Z0-9, ]+)?(.*)$", re.IGNORECASE)


def _noqa_is_in_string_literal(line: str, noqa_pos: int) -> bool:
    """Heuristic: is the noqa at ``noqa_pos`` a NON-real lint exemption?

    Returns ``True`` when the noqa is being **discussed** rather than
    **applied** — i.e. inside a string literal, a backtick-quoted
    markdown / docstring code span, a triple-quoted block, or a
    documentation comment with prior prose content.

    The heuristic is conservative: it favours false negatives (missing
    a real weakening) over false positives (blocking a doc PR that
    mentions ``# noqa`` in prose). The §3.5 recursive workflow runs
    the full contradiction audit as a safety net.
    """
    prefix = line[:noqa_pos]
    triple_d = '"' * 3
    triple_s = "'" * 3
    # Only treat triple-quote presence as "in string" when the triple-
    # quote count is ODD (unterminated). A line like ``doc = """x"""
    # # noqa: E501`` has TWO triple-double-quotes before the noqa — the
    # string is closed and the noqa is a real directive. This addresses
    # Codex P1 review on PR #1175: a single occurrence ANYWHERE in the
    # prefix used to short-circuit as "in string", causing false
    # negatives on real exemptions immediately after a closed triple-
    # quoted string.
    if prefix.count(triple_d) % 2 == 1 or prefix.count(triple_s) % 2 == 1:
        return True
    # Strip escaped quotes and triple-quote runs (so they don't bias
    # the single-quote parity check below).
    prefix_no_esc = prefix.replace(r"\"", "").replace(r"\'", "").replace(triple_d, "").replace(triple_s, "")
    if prefix_no_esc.count('"') % 2 == 1 or prefix_no_esc.count("'") % 2 == 1:
        return True
    # Markdown / docstring code-span: ``noqa`` enclosed in backticks.
    if "`" in prefix and "`" in line[noqa_pos:]:
        # Backtick on both sides → code-span context, not a real directive.
        return True
    # Documentation comment / prose: the noqa lives inside a leading
    # ``# ...`` line comment that already has prior text — the noqa is
    # being talked about, not applied as a directive. A real noqa lives
    # at the end of code, not inside a block-style comment.
    stripped = prefix.lstrip()
    return bool(stripped.startswith("#"))


def _detect_expanded_noqa_usage(ctx: _Ctx) -> list[WeakeningFinding]:
    findings: list[WeakeningFinding] = []
    diff = _git(ctx.repo_root, "diff", f"{ctx.base}...{ctx.head}", "--unified=0")
    current_file: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/") :].strip()
            continue
        if not current_file:
            continue
        # Scope to Python source — the noqa directive is a Python-lint
        # exemption, so .md / .rst / .yaml etc. cannot legitimately
        # suppress lint.
        if not current_file.endswith(".py"):
            continue
        # Only inspect added lines (start with '+' but not '+++')
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        m = _NOQA_RE.search(added)
        if not m:
            continue
        # Skip false positives where the noqa directive appears inside
        # a string literal (regex patterns, test fixture text, docstrings).
        if _noqa_is_in_string_literal(added, m.start()):
            continue
        trailing = m.group(1) or ""
        if _ISSUE_REF_RE.search(trailing):
            continue  # justified — cites a #NNN
        findings.append(
            WeakeningFinding(
                kind=WeakeningKind.EXPANDED_NOQA_USAGE,
                file=current_file,
                line=None,
                before_value="<no-noqa>",
                after_value=added.strip()[:120],
                has_loosening_approval=False,
                blocking=True,
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Pattern 13 — reduced-skill-list                                             #
# --------------------------------------------------------------------------- #

_SKILL_LIST_RE = re.compile(r"^\s*-\s+\"?([^\"\s][^\"\n]*?)\"?\s*$", re.MULTILINE)


def _required_skills(src: str) -> set[str]:
    """Pull all ``- entry`` lines from docs/skills/required.yaml.

    Conservative: we extract every dash-prefixed entry rather than
    parsing the YAML structure, mirroring the parsing strategy already
    in :mod:`scieasy.qa.governance.monotonic_check`.
    """
    return {m.group(1).strip() for m in _SKILL_LIST_RE.finditer(src)}


def _detect_reduced_skill_list(ctx: _Ctx) -> list[WeakeningFinding]:
    base_txt = _file_at_ref(ctx.repo_root, ctx.base, "docs/skills/required.yaml")
    head_txt = _file_at_ref(ctx.repo_root, ctx.head, "docs/skills/required.yaml")
    if not base_txt or not head_txt:
        return []
    removed = sorted(_required_skills(base_txt) - _required_skills(head_txt))
    return [
        WeakeningFinding(
            kind=WeakeningKind.REDUCED_SKILL_LIST,
            file="docs/skills/required.yaml",
            line=None,
            before_value=skill,
            after_value="<removed>",
            has_loosening_approval=False,
            blocking=True,
        )
        for skill in removed
    ]


# --------------------------------------------------------------------------- #
# Pattern 14 — reduced-honeypot-count                                         #
# --------------------------------------------------------------------------- #


def _honeypot_canary_count(src: str) -> int:
    return sum(1 for line in src.splitlines() if line.lstrip().startswith("- path:"))


def _detect_reduced_honeypot_count(ctx: _Ctx) -> list[WeakeningFinding]:
    base_txt = _file_at_ref(ctx.repo_root, ctx.base, ".governance-paths.yaml")
    head_txt = _file_at_ref(ctx.repo_root, ctx.head, ".governance-paths.yaml")
    if not base_txt or not head_txt:
        return []
    bc = _honeypot_canary_count(base_txt)
    hc = _honeypot_canary_count(head_txt)
    if hc >= bc:
        return []
    return [
        WeakeningFinding(
            kind=WeakeningKind.REDUCED_HONEYPOT_COUNT,
            file=".governance-paths.yaml",
            line=None,
            before_value=str(bc),
            after_value=str(hc),
            has_loosening_approval=False,
            blocking=True,
        )
    ]


# --------------------------------------------------------------------------- #
# Detector registry                                                           #
# --------------------------------------------------------------------------- #

_DETECTORS: list[tuple[WeakeningKind, Callable[[_Ctx], list[WeakeningFinding]]]] = [
    (WeakeningKind.DELETED_TEST_FILE, _detect_deleted_test_file),
    (WeakeningKind.REMOVED_TEST_FUNCTION, _detect_removed_test_function),
    (WeakeningKind.LOWERED_COVERAGE_THRESHOLD, _detect_lowered_coverage),
    (WeakeningKind.LOWERED_MUTATION_THRESHOLD, _detect_lowered_mutation_threshold),
    (WeakeningKind.UNJUSTIFIED_SKIP_OR_XFAIL, _detect_unjustified_skip_xfail),
    (WeakeningKind.DISABLED_LINT_RULE, _detect_disabled_lint_rule),
    (WeakeningKind.DISABLED_TYPECHECK_FLAG, _detect_disabled_typecheck_flag),
    (WeakeningKind.DISABLED_PRECOMMIT_HOOK, _detect_disabled_precommit_hook),
    (WeakeningKind.REMOVED_CI_JOB, _detect_removed_ci_job),
    (WeakeningKind.INCREASED_PYTEST_TIMEOUT, _detect_increased_pytest_timeout),
    (WeakeningKind.EXPANDED_EXEMPTION_PATHS, _detect_expanded_exemption_paths),
    (WeakeningKind.EXPANDED_NOQA_USAGE, _detect_expanded_noqa_usage),
    (WeakeningKind.REDUCED_SKILL_LIST, _detect_reduced_skill_list),
    (WeakeningKind.REDUCED_HONEYPOT_COUNT, _detect_reduced_honeypot_count),
]


# --------------------------------------------------------------------------- #
# Public entry-point                                                          #
# --------------------------------------------------------------------------- #


def verify_no_weakening(
    base_ref: str = "main",
    head_ref: str = "HEAD",
    *,
    repo_root: Path | None = None,
) -> list[WeakeningFinding]:
    """Detect CI weakening between two refs (ADR-043 §6.4).

    Returns one
    :class:`scieasy.qa.schemas.governance.WeakeningFinding` per detected
    pattern. The ``has_loosening_approval`` flag is set to ``True`` when
    the commit messages between ``base_ref`` and ``head_ref`` carry a
    ``Loosening-Approved: @<handle>`` trailer; in that case ``blocking``
    is set to ``False``. The Tier-2 verification of the approver and
    the companion-addendum-PR check are CI-side concerns handled by
    :mod:`scieasy.qa.governance.mod_pr_check`.

    Parameters
    ----------
    base_ref:
        Git ref representing the pre-change state (default ``"main"``).
    head_ref:
        Git ref representing the post-change state (default ``"HEAD"``).
    repo_root:
        Repository root (default: current working directory).
    """
    root = (repo_root or Path.cwd()).resolve()
    changed = _changed_files(root, base_ref, head_ref)
    deleted = _deleted_files(root, base_ref, head_ref)
    ctx = _Ctx(repo_root=root, base=base_ref, head=head_ref, changed=changed, deleted=deleted)

    msg = _commit_message_between(root, base_ref, head_ref)
    has_approval = _LOOSENING_APPROVED_RE.search(msg) is not None

    findings: list[WeakeningFinding] = []
    for _kind, fn in _DETECTORS:
        for f in fn(ctx):
            if has_approval:
                # Mark as approved + non-blocking. The full §3.4.2 ritual
                # (Tier-2 verify, companion addendum, contradiction audit)
                # is checked by mod_pr_check on CI; we only record the
                # trailer presence here.
                findings.append(f.model_copy(update={"has_loosening_approval": True, "blocking": False}))
            else:
                findings.append(f)
    return findings


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.weakened_ci_check",
        description="Weakened-CI automatic block (ADR-043 §6.4).",
    )
    parser.add_argument("--base", default="main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    root = Path(args.repo_root or Path.cwd()).resolve()
    findings = verify_no_weakening(args.base, args.head, repo_root=root)

    if not findings:
        return 0

    import json

    payload = {
        "schema_version": "weakened-ci-v1",
        "base": args.base,
        "head": args.head,
        "findings": [f.model_dump() for f in findings],
        "blocking": any(f.blocking for f in findings),
    }
    print(json.dumps(payload, indent=2))
    return 1 if payload["blocking"] else 0


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
