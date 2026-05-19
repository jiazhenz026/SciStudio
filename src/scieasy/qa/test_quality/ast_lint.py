"""AST-based anti-pattern checks for test files."""

from __future__ import annotations

import argparse
import ast
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from .._shared import AuditFinding, AuditReport, as_finding, git_sha, now_utc, schema_dependency_note

TestQualityRule = Literal[
    "empty-assertion",
    "mocked-away-behavior",
    "snapshot-only",
    "broad-exception",
    "untracked-skip",
]


def _normalize_source_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _is_meaningful_assert(assert_node: ast.Assert) -> bool:
    """Return True when assertion appears to check behavior."""

    test = assert_node.test
    if isinstance(test, ast.Constant):
        if isinstance(test.value, bool):
            return False
        return bool(test.value)
    if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id in {"assert_", "id"}:
        return True
    expr = ast.unparse(test).strip().lower()
    # Weak patterns that are usually placeholders.
    if expr in {"true", "false", "none", "0", "1"}:
        return False
    return expr != "isinstance(True, bool)"


def _is_snapshot_assert(node: ast.Assert) -> bool:
    expr = ast.unparse(node.test)
    return "snapshot" in expr.lower() or "match_snapshot" in expr.lower()


def _find_test_functions(tree: ast.AST) -> list[ast.FunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]


def _collect_pytest_skip(node: ast.FunctionDef) -> tuple[bool, str | None]:
    reason = None

    for dec in node.decorator_list:
        if isinstance(dec, ast.Attribute):
            if (
                isinstance(dec.value, ast.Attribute)
                and isinstance(dec.value.value, ast.Name)
                and dec.value.value.id == "pytest"
                and dec.value.attr == "mark"
                and dec.attr in {"skip", "skipif"}
            ):
                return True, reason
            if isinstance(dec.value, ast.Name) and dec.value.id == "pytest" and dec.attr == "skip":
                return True, reason
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "pytest"
            and func.attr in {"mark", "skipif", "skip"}
        ):
            name = func.attr
            if name in {"skip", "skipif"}:
                for kw in dec.keywords:
                    if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                        reason = str(kw.value.value)
                return True, reason
            if name == "mark" and dec.args and isinstance(dec.args[0], ast.Attribute) and dec.args[0].attr == "skip":
                return True, reason
        if isinstance(func, ast.Attribute) and func.attr == "skip" and isinstance(func.value, ast.Name) and func.value.id == "pytest":
                for kw in dec.keywords:
                    if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                        reason = str(kw.value.value)
                return True, reason

    for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                callee = inner.func
                if (
                    isinstance(callee, ast.Attribute)
                    and isinstance(callee.value, ast.Name)
                    and callee.value.id == "pytest"
                    and callee.attr == "skip"
                ):
                    for kw in inner.keywords:
                        if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                            reason = str(kw.value.value)
                    return True, reason
    return False, reason


def _tracked_skip_rationale(reason: str | None) -> bool:
    if not reason:
        return False
    return bool(re.search(r"\b(issue|jira|ticket|gh-|#|tracked)\b", reason, flags=re.IGNORECASE))


def _is_broad_exception(handler: ast.ExceptHandler) -> bool:
    # except:
    # except Exception:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}:
        # If body only pass, return statements and docs are likely empty swallowing.
        if not handler.body:
            return True
        non_noisy = [node for node in handler.body if not isinstance(node, (ast.Pass, ast.Expr, ast.ImportFrom, ast.Import))]
        return len(non_noisy) == 0
    return False


def _mock_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.withitem):
            expression = node.context_expr
            if isinstance(expression, ast.Call):
                func = expression.func
                if (
                    isinstance(func, ast.Name)
                    and func.id in {"patch", "mock"}
                    and isinstance(node.optional_vars, ast.Name)
                ):
                    names.add(node.optional_vars.id)
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in {"patch", "mock"}
                    and isinstance(node.optional_vars, ast.Name)
                ):
                    names.add(node.optional_vars.id)
        if isinstance(node, ast.FunctionDef):
            for arg in node.args.args:
                if arg.annotation and isinstance(ast.unparse(arg.annotation), str):
                    names.add(arg.arg)
    return names


def _is_mocked_away_function(node: ast.FunctionDef) -> bool:
    mocks = _mock_names(node)
    if not mocks:
        return False
    asserts = [item for item in ast.walk(node) if isinstance(item, ast.Assert)]
    if not asserts:
        return False
    for item in asserts:
        text = ast.unparse(item.test).lower()
        if not _is_meaningful_assert(item):
            continue
        # If an assertion uses identifiers not tied to mock objects, it's not mocked-away.
        identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))
        identifiers.discard("self")
        if not identifiers:
            continue
        if not identifiers.issubset(mocks):
            return False
    return True


def _check_for_snapshot_only(node: ast.FunctionDef) -> bool:
    asserts = [item for item in ast.walk(node) if isinstance(item, ast.Assert)]
    if not asserts:
        return False
    return all(_is_snapshot_assert(item) for item in asserts if _is_meaningful_assert(item))


def _check_empty_assertions(node: ast.FunctionDef) -> bool:
    asserts = [item for item in ast.walk(node) if isinstance(item, ast.Assert)]
    if not asserts:
        return True
    return not any(_is_meaningful_assert(item) for item in asserts)


def _check_broad_exceptions(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad_exception(node):
            line = getattr(node, "lineno", 1)
            out.append((line, "bare or broad exception"))
    return out


def check_test_file(
    path: Path,
    *,
    source: str | None = None,
) -> AuditReport:
    file_path = Path(path)
    file_text = source if source is not None else file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(file_text, filename=str(file_path))
    except SyntaxError as exc:
        return AuditReport(
            tool="test_quality.ast_lint",
            status="failed",
            generated_at=now_utc(),
            source_sha=git_sha(file_path.parent),
            findings=[
                as_finding(
                    tool="test_quality.ast_lint",
                    severity="error",
                    finding_class="invalid-syntax",
                    message=str(exc.msg),
                    path=_normalize_source_path(file_path),
                    line=exc.lineno,
                    subject=str(file_path),
                )
            ],
            summary={"files": [_normalize_source_path(file_path)], "findings": 1, "schema_dependency": schema_dependency_note()},
        )

    findings: list[AuditFinding] = []
    for line, message in _check_broad_exceptions(tree):
        findings.append(
            as_finding(
                tool="test_quality.ast_lint",
                severity="error",
                finding_class="broad-exception",
                message=message,
                path=_normalize_source_path(file_path),
                line=line,
                subject="except",
            )
        )

    for function in _find_test_functions(tree):
        if _check_empty_assertions(function):
            findings.append(
                as_finding(
                    tool="test_quality.ast_lint",
                    severity="error",
                    finding_class="empty-assertion",
                    message=f"{function.name} has no meaningful assertions.",
                    path=_normalize_source_path(file_path),
                    line=function.lineno,
                    subject=function.name,
                )
            )
        if _check_for_snapshot_only(function):
            findings.append(
                as_finding(
                    tool="test_quality.ast_lint",
                    severity="warning",
                    finding_class="snapshot-only",
                    message=f"{function.name} appears to only assert snapshots.",
                    path=_normalize_source_path(file_path),
                    line=function.lineno,
                    subject=function.name,
                )
            )
        if _is_mocked_away_function(function):
            findings.append(
                as_finding(
                    tool="test_quality.ast_lint",
                    severity="error",
                    finding_class="mocked-away-behavior",
                    message=f"{function.name} may only assert mocked interactions.",
                    path=_normalize_source_path(file_path),
                    line=function.lineno,
                    subject=function.name,
                )
            )
        is_skip, reason = _collect_pytest_skip(function)
        if is_skip and not _tracked_skip_rationale(reason):
            findings.append(
                as_finding(
                    tool="test_quality.ast_lint",
                    severity="error",
                    finding_class="untracked-skip",
                    message=f"{function.name} is skipped without tracked rationale.",
                    path=_normalize_source_path(file_path),
                    line=function.lineno,
                    subject=function.name,
                )
            )

    status: Literal["passed", "failed", "skipped", "error"] = "passed"
    if any(item.severity == "error" for item in findings):
        status = "failed"

    return AuditReport(
        tool="test_quality.ast_lint",
        status=status,
        generated_at=now_utc(),
        source_sha=git_sha(file_path.parent),
        findings=findings,
        summary={
            "files": [_normalize_source_path(file_path)],
            "findings": len(findings),
            "schema_dependency": schema_dependency_note(),
        },
    )


def check_test_paths(paths: Sequence[Path], *, repo_root: Path) -> AuditReport:
    all_paths: list[Path] = []
    for item in paths:
        candidate = (repo_root / item).resolve()
        if candidate.is_dir():
            all_paths.extend(
                p
                for p in candidate.rglob("*.py")
                if "test" in p.name.lower() and p.suffix == ".py"
            )
        elif candidate.exists():
            all_paths.append(candidate)

    findings: list[AuditFinding] = []
    for path in all_paths:
        findings.extend(check_test_file(path).findings)

    status: Literal["passed", "failed", "skipped", "error"] = "passed"
    if any(item.severity == "error" for item in findings):
        status = "failed"

    return AuditReport(
        tool="test_quality.ast_lint",
        status=status,
        generated_at=now_utc(),
        source_sha=git_sha(repo_root),
        findings=findings,
        summary={"files": [str(path) for path in all_paths], "findings": len(findings), "schema_dependency": schema_dependency_note()},
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ADR-042 AST test linting.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args()


def _run_cli() -> int:
    args = _parse_args()
    report = check_test_paths([Path(path) for path in args.paths], repo_root=Path(".").resolve())
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        print(f"status={report.status} findings={len(report.findings)}")
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(_run_cli())
