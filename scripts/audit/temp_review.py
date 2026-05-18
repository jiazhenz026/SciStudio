"""Phase -0.5 temporary simplified review system (ADR-042/043/044 cascade).

This module implements the temporary review gate defined in
``docs/planning/phase-0-5-temp-review-design.md``. It runs a small,
well-defined subset of the eventual Phase 1 QA regime so that
implementation PRs ship under *some* automated review while the full
regime is being built.

Lifecycle: lives from the merge of P-0.5.B until the end of Phase 1, at
which point a single decommission PR deletes this file along with
``tests/audit/test_temp_review.py`` and surgically reverts the local
``temp-review`` hook in ``.pre-commit-config.yaml`` and the
``Phase -0.5 temporary review`` step in ``.github/workflows/ci.yml``.

The checks fall into two families:

* **Piggyback checks** — invoke existing tooling (``ruff``, ``mypy``,
  ``pytest``, ``lint-imports``). These have their own rule IDs and
  output formats.
* **Net-new rules** — ``QA001``..``QA005`` implemented directly in this
  module against the Python AST (``QA001``/``QA002``) or against
  ``git log`` (``QA003``/``QA005``) or a regex over file contents
  (``QA004``).

Output format (one finding per line, machine parseable):

    <path>:<line>: <severity>: <rule-id>: <message>

Exit codes:

* ``0`` — all checks passed
* ``1`` — one or more findings
* ``2`` — config / environment error

See ``docs/planning/phase-0-5-temp-review-design.md`` §2 for the
authoritative rule definitions and §4 for the CLI contract.
"""

from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

#: Trailers that satisfy the QA003 attribution requirement. ADR-042 §13.2
#: tightens this to ``Assisted-by: <Runtime>:<ModelID>`` in TC-1B.5; the
#: temp regime accepts the looser form deliberately (see §2.7 of the design
#: doc and §7.1 of the risks register).
_QA003_TRAILER_RE = re.compile(r"^(Assisted-by|Co-Authored-By):\s+.+$", re.IGNORECASE | re.MULTILINE)

#: Branch pattern on which QA003 fires. The temp system intentionally
#: scopes attribution to cascade tracking branches only — see the design
#: doc §7.2 open question (1) and the recommended scoping.
_QA003_BRANCH_RE = re.compile(r"^track/adr-042/.*$")

#: Patterns that QA005 forbids in commit message bodies. Each is a
#: word-boundaried form of ``git add -A`` / ``git add .`` / ``git add *``.
_QA005_PATTERNS = (
    re.compile(r"\bgit\s+add\s+-A\b"),
    re.compile(r"\bgit\s+add\s+\.(\s|$)"),
    re.compile(r"\bgit\s+add\s+\*"),
)

#: YAML frontmatter block: two ``---`` fences enclosing arbitrary
#: content. Schema validation is deferred to TC-1B.2 (uses 1A.1 schemas).
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

#: AST-checked qa-namespace root.
_QA_NAMESPACE = Path("src") / "scieasy" / "qa"

#: Glob roots for ADR/spec frontmatter scanning.
_FRONTMATTER_ROOTS: tuple[Path, ...] = (Path("docs") / "adr", Path("docs") / "spec")


# --------------------------------------------------------------------------- #
# Data shapes                                                                 #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Finding:
    """A single review finding rendered into the script's output format."""

    path: str
    line: int
    severity: str
    rule_id: str
    message: str

    def render(self) -> str:
        """Return the canonical one-line representation of this finding."""
        return f"{self.path}:{self.line}: {self.severity}: {self.rule_id}: {self.message}"


@dataclass
class Context:
    """Run-time configuration resolved from argv + cwd."""

    repo_root: Path
    changed_files_only: bool
    ci_mode: bool
    base_ref: str
    explicit_paths: tuple[Path, ...]


# --------------------------------------------------------------------------- #
# Git helpers                                                                 #
# --------------------------------------------------------------------------- #


def _run_subprocess(args: Sequence[str], cwd: Path) -> tuple[int, str, str]:
    """Run a subprocess capturing UTF-8 output (cross-platform).

    On Windows ``text=True`` defaults to the legacy ANSI codepage
    (``gbk`` on zh-CN locales), which crashes on non-ASCII output from
    ruff/git. Forcing ``encoding="utf-8"`` + ``errors="replace"`` keeps
    the script portable without sacrificing readable output.
    """
    proc = subprocess.run(
        list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return proc.returncode, stdout, stderr


def _run_git(args: Sequence[str], cwd: Path) -> tuple[int, str, str]:
    """Run a git subcommand from ``cwd`` and return ``(rc, stdout, stderr)``.

    Returns ``(2, "", reason)`` if ``git`` is not installed.
    """
    if shutil.which("git") is None:
        return 2, "", "git not found on PATH"
    return _run_subprocess(["git", *args], cwd)


def _git_current_branch(repo_root: Path) -> str:
    """Return the current branch name, or empty string in detached-HEAD."""
    rc, out, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if rc != 0:
        return ""
    return out.strip()


def _git_changed_files(repo_root: Path, base_ref: str) -> list[Path]:
    """Return PR-diff file list relative to ``base_ref``.

    Uses ``git diff --name-only --diff-filter=ACMR base_ref...HEAD`` to
    enumerate Added / Copied / Modified / Renamed files (excludes
    deletions). Returns empty list if git is unavailable or the base
    ref cannot be resolved.
    """
    rc, out, _ = _run_git(
        ["diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}...HEAD"],
        repo_root,
    )
    if rc != 0:
        return []
    return [Path(line) for line in out.splitlines() if line.strip()]


def _git_staged_files(repo_root: Path) -> list[Path]:
    """Return staged (index) file list — used by the pre-commit fast path."""
    rc, out, _ = _run_git(
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        repo_root,
    )
    if rc != 0:
        return []
    return [Path(line) for line in out.splitlines() if line.strip()]


def _git_commits_in_diff(repo_root: Path, base_ref: str) -> list[str]:
    """Return commit SHAs reachable from HEAD but not from ``base_ref``."""
    rc, out, _ = _run_git(["log", "--format=%H", f"{base_ref}..HEAD"], repo_root)
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _git_commit_message(repo_root: Path, sha: str) -> str:
    """Return the full commit message body for ``sha``."""
    rc, out, _ = _run_git(["log", "-1", "--format=%B", sha], repo_root)
    if rc != 0:
        return ""
    return out


# --------------------------------------------------------------------------- #
# AST checks (QA001 / QA002)                                                  #
# --------------------------------------------------------------------------- #


def _is_init_only_imports(tree: ast.Module) -> bool:
    """Return True iff ``tree`` contains only Import/ImportFrom nodes.

    Used to relax QA001 on ``__init__.py`` re-export shims (per design §2.5).
    """
    return all(isinstance(node, ast.Import | ast.ImportFrom) for node in tree.body)


def _check_qa_module_docstrings(file: Path) -> list[Finding]:
    """Run QA001 (module docstring) on a single Python file."""
    try:
        source = file.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError as exc:
        return [
            Finding(
                path=str(file).replace("\\", "/"),
                line=exc.lineno or 1,
                severity="error",
                rule_id="QA001",
                message=f"syntax error while parsing: {exc.msg}",
            )
        ]
    docstring = ast.get_docstring(tree)
    if docstring:
        return []
    if file.name == "__init__.py" and _is_init_only_imports(tree):
        return []
    return [
        Finding(
            path=str(file).replace("\\", "/"),
            line=1,
            severity="error",
            rule_id="QA001",
            message="missing module docstring",
        )
    ]


def _check_qa_public_class_docstrings(file: Path) -> list[Finding]:
    """Run QA002 (public-class docstring) on a single Python file."""
    try:
        source = file.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError:
        # QA001 already reported the syntax error; skip silently here.
        return []
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name.startswith("_"):
            continue
        if ast.get_docstring(node):
            continue
        findings.append(
            Finding(
                path=str(file).replace("\\", "/"),
                line=node.lineno,
                severity="error",
                rule_id="QA002",
                message=f"missing public class docstring: {node.name}",
            )
        )
    return findings


def _iter_qa_python_files(repo_root: Path, restrict_to: Iterable[Path] | None) -> Iterable[Path]:
    """Yield ``.py`` files under ``src/scieasy/qa/`` (absolute paths).

    If ``restrict_to`` is provided, the yielded set is filtered to its
    intersection (for pre-commit ``--changed-files-only`` and PR-diff
    modes).
    """
    qa_root = repo_root / _QA_NAMESPACE
    if not qa_root.is_dir():
        return
    candidates = sorted(p for p in qa_root.rglob("*.py") if p.is_file())
    if restrict_to is None:
        yield from candidates
        return
    restrict_set = {(repo_root / p).resolve() for p in restrict_to}
    for path in candidates:
        if path.resolve() in restrict_set:
            yield path


def _run_ast_checks(ctx: Context, restrict_to: Iterable[Path] | None) -> list[Finding]:
    """Run QA001 + QA002 against the qa namespace."""
    findings: list[Finding] = []
    for file in _iter_qa_python_files(ctx.repo_root, restrict_to):
        rel = file.relative_to(ctx.repo_root)
        findings.extend(_render_relative(_check_qa_module_docstrings(file), rel))
        findings.extend(_render_relative(_check_qa_public_class_docstrings(file), rel))
    return findings


def _render_relative(findings: list[Finding], rel: Path) -> list[Finding]:
    """Replace each finding's path with its repo-relative posix form."""
    rel_str = str(rel).replace("\\", "/")
    return [
        Finding(path=rel_str, line=f.line, severity=f.severity, rule_id=f.rule_id, message=f.message) for f in findings
    ]


# --------------------------------------------------------------------------- #
# Frontmatter check (QA004)                                                   #
# --------------------------------------------------------------------------- #


def _check_frontmatter(repo_root: Path, candidate_files: Iterable[Path]) -> list[Finding]:
    """Run QA004 against new ADR/spec markdown files in ``candidate_files``."""
    findings: list[Finding] = []
    for path in candidate_files:
        if path.suffix.lower() != ".md":
            continue
        if not any(_path_starts_with(path, root) for root in _FRONTMATTER_ROOTS):
            continue
        abs_path = repo_root / path
        if not abs_path.is_file():
            # File was deleted in the diff; nothing to scan.
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _FRONTMATTER_RE.search(text):
            continue
        findings.append(
            Finding(
                path=str(path).replace("\\", "/"),
                line=1,
                severity="error",
                rule_id="QA004",
                message="missing YAML frontmatter block",
            )
        )
    return findings


def _path_starts_with(candidate: Path, prefix: Path) -> bool:
    """Cross-platform ``candidate.is_relative_to(prefix)`` shim."""
    try:
        candidate.relative_to(prefix)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- #
# Commit checks (QA003 / QA005)                                               #
# --------------------------------------------------------------------------- #


def _check_commit_trailers(repo_root: Path, base_ref: str, branch: str) -> list[Finding]:
    """Run QA003 over commits unique to HEAD vs ``base_ref``.

    Only fires when ``branch`` matches ``track/adr-042/**``.
    """
    if not _QA003_BRANCH_RE.match(branch):
        return []
    findings: list[Finding] = []
    for sha in _git_commits_in_diff(repo_root, base_ref):
        message = _git_commit_message(repo_root, sha)
        if _QA003_TRAILER_RE.search(message):
            continue
        findings.append(
            Finding(
                path=f"commit {sha[:12]}",
                line=1,
                severity="error",
                rule_id="QA003",
                message="missing Assisted-by/Co-Authored-By trailer",
            )
        )
    return findings


def _check_commit_git_add_all(repo_root: Path, base_ref: str) -> list[Finding]:
    """Run QA005 over commits unique to HEAD vs ``base_ref``."""
    findings: list[Finding] = []
    for sha in _git_commits_in_diff(repo_root, base_ref):
        message = _git_commit_message(repo_root, sha)
        if any(pat.search(message) for pat in _QA005_PATTERNS):
            findings.append(
                Finding(
                    path=f"commit {sha[:12]}",
                    line=1,
                    severity="error",
                    rule_id="QA005",
                    message="forbidden git-add-all reference in commit message",
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Piggyback checks (ruff / mypy / pytest / importlinter)                      #
# --------------------------------------------------------------------------- #


def _piggyback_ruff_lint(ctx: Context, paths: Sequence[str]) -> tuple[int, str]:
    """Run ``ruff check`` against ``paths`` (or the repo root if empty)."""
    if shutil.which("ruff") is None:
        return 2, "ruff not installed"
    args = ["ruff", "check", *paths] if paths else ["ruff", "check", "."]
    rc, out, err = _run_subprocess(args, ctx.repo_root)
    return rc, out + err


def _piggyback_ruff_format(ctx: Context, paths: Sequence[str]) -> tuple[int, str]:
    """Run ``ruff format --check`` against ``paths`` (or the repo root)."""
    if shutil.which("ruff") is None:
        return 2, "ruff not installed"
    args = ["ruff", "format", "--check", *paths] if paths else ["ruff", "format", "--check", "."]
    rc, out, err = _run_subprocess(args, ctx.repo_root)
    return rc, out + err


def _piggyback_mypy_strict_on_qa(ctx: Context) -> tuple[int, str]:
    """Run ``mypy --strict`` against ``src/scieasy/qa/`` if it exists."""
    qa_root = ctx.repo_root / _QA_NAMESPACE
    if not qa_root.is_dir():
        return 0, "mypy --strict skipped: src/scieasy/qa/ not present yet"
    # Defensive: skip if the dir is empty (no .py files).
    if not any(qa_root.rglob("*.py")):
        return 0, "mypy --strict skipped: src/scieasy/qa/ is empty"
    if shutil.which("mypy") is None:
        return 2, "mypy not installed"
    rc, out, err = _run_subprocess(["mypy", "--strict", str(qa_root)], ctx.repo_root)
    return rc, out + err


def _piggyback_lint_imports(ctx: Context) -> tuple[int, str]:
    """Run ``lint-imports`` if ``src/scieasy/qa/`` is present."""
    qa_root = ctx.repo_root / _QA_NAMESPACE
    if not qa_root.is_dir():
        return 0, "lint-imports skipped: src/scieasy/qa/ not present yet"
    if shutil.which("lint-imports") is None:
        return 2, "lint-imports (import-linter) not installed"
    rc, out, err = _run_subprocess(["lint-imports"], ctx.repo_root)
    return rc, out + err


# --------------------------------------------------------------------------- #
# CLI orchestration                                                           #
# --------------------------------------------------------------------------- #


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.audit.temp_review",
        description=(
            "Phase -0.5 temporary simplified review. Decommissioned end of "
            "Phase 1; see docs/planning/phase-0-5-temp-review-design.md."
        ),
    )
    parser.add_argument(
        "--changed-files-only",
        action="store_true",
        help="Restrict checks to staged files (pre-commit fast path).",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Enable commit-trailer + PR-diff checks (CI mode).",
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Base ref for --ci PR-diff comparison (default: origin/main).",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Explicit paths to scan (overrides default scan roots).",
    )
    return parser.parse_args(list(argv))


def _resolve_context(args: argparse.Namespace, repo_root: Path) -> Context:
    return Context(
        repo_root=repo_root,
        changed_files_only=bool(args.changed_files_only),
        ci_mode=bool(args.ci),
        base_ref=str(args.base_ref),
        explicit_paths=tuple(args.paths),
    )


def _find_repo_root(start: Path) -> Path:
    """Walk upward from ``start`` to find a directory containing ``.git``."""
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent
    return start


def _candidate_files(ctx: Context) -> list[Path]:
    """Resolve the file list to scan in diff-based modes.

    Returns empty list in "scan everything" mode (the caller will fall
    back to a full repo walk for AST checks). Each path is repo-relative.
    """
    if ctx.explicit_paths:
        out: list[Path] = []
        for p in ctx.explicit_paths:
            if p.is_absolute():
                try:
                    rel = p.relative_to(ctx.repo_root)
                except ValueError:
                    continue
                out.append(rel)
            else:
                out.append(p)
        return out
    if ctx.changed_files_only:
        return _git_staged_files(ctx.repo_root)
    if ctx.ci_mode:
        return _git_changed_files(ctx.repo_root, ctx.base_ref)
    return []


def _emit(findings: Sequence[Finding], stream: object) -> None:
    """Write findings, one per line, to ``stream``."""
    for finding in findings:
        stream.write(finding.render() + "\n")  # type: ignore[attr-defined]


def _collect_findings(ctx: Context) -> tuple[list[Finding], list[str], int]:
    """Run every enabled check and return (findings, messages, env_error).

    ``env_error`` is 0 on success and 2 if any subprocess could not be
    invoked (e.g. ``git`` missing). Messages are diagnostic strings for
    the trailing summary (always emitted on stderr).
    """
    findings: list[Finding] = []
    messages: list[str] = []
    env_error = 0

    candidates = _candidate_files(ctx)
    restrict_to: list[Path] | None = (
        candidates if (ctx.changed_files_only or ctx.ci_mode or ctx.explicit_paths) else None
    )

    # QA001 + QA002.
    findings.extend(_run_ast_checks(ctx, restrict_to))

    # QA004. Per design §2.8 the check fires only on *new* files in the PR
    # diff. In full-scan mode (no diff context) we therefore must not flag
    # historical ADR/spec files that predate the temp regime — they are
    # grandfathered until TC-1B.2 ships full pydantic validation.
    if restrict_to is not None:
        findings.extend(_check_frontmatter(ctx.repo_root, restrict_to))

    if ctx.ci_mode:
        branch = _git_current_branch(ctx.repo_root)
        if branch:
            findings.extend(_check_commit_trailers(ctx.repo_root, ctx.base_ref, branch))
        findings.extend(_check_commit_git_add_all(ctx.repo_root, ctx.base_ref))

    # Piggyback invocations.
    ruff_paths: list[str] = []
    if ctx.changed_files_only and candidates:
        ruff_paths = [str(p) for p in candidates if p.suffix == ".py" and (ctx.repo_root / p).is_file()]
        if not ruff_paths:
            messages.append("ruff: no python files in staged set, skipped")
    if not ctx.changed_files_only or ruff_paths:
        rc_lint, out_lint = _piggyback_ruff_lint(ctx, ruff_paths)
        if rc_lint == 2:
            env_error = 2
            messages.append(f"ruff check: {out_lint.strip()}")
        elif rc_lint != 0:
            findings.append(
                Finding(
                    path="ruff",
                    line=1,
                    severity="error",
                    rule_id="ruff",
                    message=f"ruff check reported findings (exit {rc_lint})",
                )
            )
            messages.append("ruff check output:\n" + out_lint.rstrip())
        rc_fmt, out_fmt = _piggyback_ruff_format(ctx, ruff_paths)
        if rc_fmt == 2:
            env_error = 2
            messages.append(f"ruff format --check: {out_fmt.strip()}")
        elif rc_fmt != 0:
            findings.append(
                Finding(
                    path="ruff",
                    line=1,
                    severity="error",
                    rule_id="ruff-format",
                    message=f"ruff format --check reported findings (exit {rc_fmt})",
                )
            )
            messages.append("ruff format --check output:\n" + out_fmt.rstrip())

    if ctx.ci_mode:
        rc_my, out_my = _piggyback_mypy_strict_on_qa(ctx)
        if rc_my == 2:
            env_error = 2
            messages.append(f"mypy --strict: {out_my.strip()}")
        elif rc_my != 0:
            findings.append(
                Finding(
                    path="mypy",
                    line=1,
                    severity="error",
                    rule_id="mypy-strict",
                    message=f"mypy --strict reported findings (exit {rc_my})",
                )
            )
            messages.append("mypy --strict output:\n" + out_my.rstrip())
        else:
            messages.append(out_my.rstrip() or "mypy --strict: ok")

        rc_il, out_il = _piggyback_lint_imports(ctx)
        if rc_il == 2:
            env_error = 2
            messages.append(f"lint-imports: {out_il.strip()}")
        elif rc_il != 0:
            findings.append(
                Finding(
                    path="import-linter",
                    line=1,
                    severity="error",
                    rule_id="import-linter",
                    message=f"lint-imports reported findings (exit {rc_il})",
                )
            )
            messages.append("lint-imports output:\n" + out_il.rstrip())
        else:
            messages.append(out_il.rstrip() or "lint-imports: ok")

    return findings, messages, env_error


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code (0/1/2)."""
    start = time.perf_counter()
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = _find_repo_root(Path.cwd())
    ctx = _resolve_context(args, repo_root)

    try:
        findings, messages, env_error = _collect_findings(ctx)
    except OSError as exc:  # pragma: no cover - defensive
        sys.stderr.write(f"temp_review: environment error: {exc}\n")
        return 2

    _emit(findings, sys.stdout)

    elapsed = time.perf_counter() - start
    file_count = (
        sum(1 for _ in _iter_qa_python_files(ctx.repo_root, None))
        if not ctx.changed_files_only
        else len(_candidate_files(ctx))
    )
    summary = f"temp_review: {len(findings)} finding(s), {file_count} file(s) checked, {elapsed:.2f}s"
    for msg in messages:
        sys.stderr.write(msg + "\n")
    sys.stderr.write(summary + "\n")

    if env_error == 2:
        return 2
    return 0 if not findings else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
