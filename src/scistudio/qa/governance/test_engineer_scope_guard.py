"""Block production-code edits for ADR-042 test engineer work."""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

TEST_ENGINEER_PERSONA = "test_engineer"

ALLOWED_PATTERNS = (
    "tests/**",
    "frontend/**/*.test.*",
    "frontend/**/*.spec.*",
    "frontend/**/__tests__/**",
    "frontend/**/__fixtures__/**",
    "frontend/**/__mocks__/**",
    "frontend/e2e/**",
    "frontend/tests/**",
    "frontend/test/**",
    "frontend/playwright.config.*",
    "frontend/vitest.config.*",
    "frontend/vitest.setup.*",
    "docs/ai-developer/e2e/**",
    "docs/audit/**",
)

QA_TOOLING_PATTERN = "src/scistudio/qa/**"

PRODUCTION_PATTERNS = (
    "src/scistudio/**",
    "frontend/src/**",
    "frontend/app/**",
    "frontend/components/**",
    "frontend/lib/**",
    "src/scistudio/api/**",
    "src/scistudio/blocks/**",
    "src/scistudio/core/**",
    "src/scistudio/engine/**",
    "src/scistudio/lineage/**",
    "src/scistudio/mcp/**",
    "src/scistudio/plugins/**",
)

PRODUCT_BUILD_PATTERNS = (
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "uv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/pnpm-lock.yaml",
    "frontend/yarn.lock",
    "frontend/tsconfig*.json",
    "frontend/vite.config.*",
    "frontend/next.config.*",
)

GOVERNANCE_PATTERNS = (
    ".github/**",
    ".workflow/**",
    ".sentrux/**",
    ".agents/**",
    ".codex/**",
    ".claude/**",
    "docs/ai-developer/rules.md",
    "docs/ai-developer/specific_rules/**",
    "docs/ai-developer/personas/**",
    "docs/ai-developer/templates/**",
)


def _source_sha(repo_root: Path | None) -> str:
    if repo_root is None:
        return "unknown"
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _normalize_path(path: str | Path, repo_root: Path | None = None) -> str:
    candidate = Path(path)
    if repo_root is not None and candidate.is_absolute():
        with contextlib.suppress(ValueError):
            candidate = candidate.relative_to(repo_root)
    normalized = candidate.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def _matches(path: str, pattern: str) -> bool:
    posix_path = PurePosixPath(path)
    if posix_path.match(pattern) or fnmatch.fnmatchcase(path, pattern):
        return True
    if "/**/" in pattern:
        shallow_pattern = pattern.replace("/**/", "/")
        return posix_path.match(shallow_pattern) or fnmatch.fnmatchcase(path, shallow_pattern)
    return False


def _matches_any(path: str, patterns: Sequence[str]) -> str | None:
    return next((pattern for pattern in patterns if _matches(path, pattern)), None)


def _scope_allows(path: str, scope_includes: Sequence[str]) -> str | None:
    normalized_includes = tuple(_normalize_path(include) for include in scope_includes)
    return _matches_any(path, normalized_includes)


def classify_path(path: str, *, scope_includes: Sequence[str] = ()) -> tuple[str, str | None]:
    """Classify a normalized changed path for test-engineer write access."""

    allowed_pattern = _matches_any(path, ALLOWED_PATTERNS)
    if allowed_pattern is not None:
        return "allowed_test_artifact", allowed_pattern

    scope_pattern = _scope_allows(path, scope_includes)
    if scope_pattern is not None and _matches(path, QA_TOOLING_PATTERN):
        return "allowed_explicit_qa_tooling", scope_pattern

    production_pattern = _matches_any(path, PRODUCTION_PATTERNS)
    if production_pattern is not None:
        return "blocked_production_surface", production_pattern

    build_pattern = _matches_any(path, PRODUCT_BUILD_PATTERNS)
    if build_pattern is not None:
        return "blocked_product_build_surface", build_pattern

    governance_pattern = _matches_any(path, GOVERNANCE_PATTERNS)
    if governance_pattern is not None:
        return "blocked_governance_surface", governance_pattern

    if scope_pattern is not None:
        return "blocked_amended_non_qa_surface", scope_pattern

    return "blocked_unknown_surface", None


def _blocked_finding(
    *,
    persona: str,
    path: str,
    classification: str,
    matched_pattern: str | None,
    scope_includes: Sequence[str],
) -> Finding:
    attempted_amendment = _scope_allows(path, scope_includes)
    return Finding(
        rule_id="test_engineer_scope_guard.blocked-path",
        severity=Severity.ERROR,
        file=path,
        message="test_engineer changes must stay in test, validation, e2e, or explicitly scoped QA tooling paths",
        evidence={
            "persona": persona,
            "path": path,
            "classification": classification,
            "matched_pattern": matched_pattern,
            "amendment_state": "attempted" if attempted_amendment else "none",
            "amendment_pattern": attempted_amendment,
            "recommended_handoff": "assign implementer or remove the blocked path",
        },
    )


def check(
    *,
    repo_root: Path | None = None,
    persona: str,
    changed_files: Sequence[str | Path],
    scope_includes: Sequence[str | Path] = (),
) -> AuditReport:
    """Validate changed files for the test_engineer no-production-code boundary."""

    normalized_files = [_normalize_path(path, repo_root) for path in changed_files]
    normalized_includes = [_normalize_path(path, repo_root) for path in scope_includes]
    classifications: dict[str, str] = {}
    findings: list[Finding] = []

    if persona != TEST_ENGINEER_PERSONA:
        return AuditReport(
            tool="test_engineer_scope_guard",
            status=AuditStatus.PASS,
            source_sha=_source_sha(repo_root),
            findings=[],
            summary={
                "persona": persona,
                "applies": False,
                "changed_files": normalized_files,
            },
        )

    for path in normalized_files:
        classification, matched_pattern = classify_path(path, scope_includes=normalized_includes)
        classifications[path] = classification
        if classification.startswith("blocked_"):
            findings.append(
                _blocked_finding(
                    persona=persona,
                    path=path,
                    classification=classification,
                    matched_pattern=matched_pattern,
                    scope_includes=normalized_includes,
                )
            )

    return AuditReport(
        tool="test_engineer_scope_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={
            "persona": persona,
            "applies": True,
            "changed_files": normalized_files,
            "classifications": classifications,
            "allowed_patterns": ALLOWED_PATTERNS,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--persona", required=True)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--scope-include", action="append", default=[])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = check(
        repo_root=args.repo_root,
        persona=args.persona,
        changed_files=args.changed_file,
        scope_includes=args.scope_include,
    )
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print("test_engineer_scope_guard: pass" if not report.findings else "test_engineer_scope_guard: fail")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
