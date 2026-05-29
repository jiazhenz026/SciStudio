"""CI-equivalent check selection and execution for ADR-042 Addendum 6 (§7.5).

The required check set is derived from three inputs (§7.5):

1. the strictness tier (task kind, escalated by observed diff per §7.6);
2. the observed changed-file surfaces from git;
3. the CI workflow graph.

CI workflow YAML is the source of command truth. To keep the core importable
without a YAML dependency, the canonical CI command snapshot from ADR-042
Addendum 6 §7.5 is encoded as data here and cross-checked against the presence
of the workflow files. When a required CI job cannot be mapped to a local
command, the evaluator fails closed for PR readiness (§7.5, §7.10).

Execution writes raw transcripts only under ``.workflow/local/**`` (gitignored)
and returns sanitized :class:`CheckEvent` payloads.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import scistudio.qa.governance.gate_record.surfaces as surfaces
from scistudio.qa.governance.gate_record.io import LOCAL_LOGS_DIR, fingerprint_paths
from scistudio.qa.governance.gate_record.ledger import CheckEvent, StrictnessTier
from scistudio.qa.governance.gate_record.parity import resolve_ci_tool_versions


@dataclass(frozen=True)
class CheckSpec:
    """A CI-equivalent local check derived from the CI command snapshot."""

    name: str
    command: tuple[str, ...]
    covered_surface: str
    # CI job this mirrors; used for parity-mapping diagnostics.
    ci_job: str
    # When True the check is PR-only review automation (recorded, never a local
    # failure), e.g. ai-review.yml.
    pr_only: bool = False
    # When True, requires PYTHONPATH=src to import scistudio.
    needs_src_import: bool = False


# Canonical CI command snapshot (Addendum 6 §7.5 table). The single mapping the
# evaluator selects from; no hand-written looser copy lives anywhere else.
CHECK_CATALOG: dict[str, CheckSpec] = {
    "lint_format": CheckSpec(
        name="lint_format",
        command=("ruff", "check", "."),
        covered_surface="python",
        ci_job="ci.yml/Lint & Format",
    ),
    "format_check": CheckSpec(
        name="format_check",
        command=("ruff", "format", "--check", "."),
        covered_surface="python",
        ci_job="ci.yml/Lint & Format",
    ),
    "type_check": CheckSpec(
        name="type_check",
        command=("mypy", "src/scistudio/", "--ignore-missing-imports"),
        covered_surface="python",
        ci_job="ci.yml/Type Check",
        needs_src_import=True,
    ),
    "architecture_tests": CheckSpec(
        name="architecture_tests",
        command=("pytest", "tests/architecture/", "-v", "--no-cov"),
        covered_surface="architecture",
        ci_job="ci.yml/Architecture Tests",
        needs_src_import=True,
    ),
    "full_audit": CheckSpec(
        name="full_audit",
        command=(
            "python",
            "-m",
            "scistudio.qa.audit.full_audit",
            "--repo-root",
            ".",
            "--format",
            "json",
            "--output",
            ".audit/full-audit.json",
        ),
        covered_surface="governance",
        ci_job="ci.yml/Full Audit",
        needs_src_import=True,
    ),
    "python_tests": CheckSpec(
        name="python_tests",
        command=("pytest", "-n", "auto", "--timeout=60", "--timeout-method=thread"),
        covered_surface="python",
        ci_job="ci.yml/Test (Python 3.11, 3.13)",
        needs_src_import=True,
    ),
    "import_contracts": CheckSpec(
        name="import_contracts",
        command=("lint-imports",),
        covered_surface="python",
        ci_job="ci.yml/Import Contracts",
        needs_src_import=True,
    ),
    "frontend": CheckSpec(
        name="frontend",
        command=("npm", "run", "lint"),
        covered_surface="frontend",
        ci_job="ci.yml/Frontend",
    ),
    "wheel_release_smoke": CheckSpec(
        name="wheel_release_smoke",
        command=("python", "-m", "build", "--wheel"),
        covered_surface="packaging",
        ci_job="ci.yml/Wheel Release Smoke",
        needs_src_import=True,
    ),
    "semantic_dup": CheckSpec(
        name="semantic_dup",
        command=(
            "python",
            "scripts/semantic_dup_scan.py",
            "--check",
            "docs/audit/baselines/semantic-dup-baseline.json",
        ),
        covered_surface="python",
        ci_job="semantic-dup-scan.yml/Semantic duplication ratchet",
    ),
    "codex_review": CheckSpec(
        name="codex_review",
        command=(),
        covered_surface="pr",
        ci_job="ai-review.yml/Codex PR Review",
        pr_only=True,
    ),
}


@dataclass
class CheckSelection:
    """The inferred required check set plus parity diagnostics."""

    required: list[str] = field(default_factory=list)
    pr_only: list[str] = field(default_factory=list)
    parity_gaps: list[str] = field(default_factory=list)


# Baseline check sets that run for every AI-authored candidate at a given tier.
_BASELINE_BY_TIER: dict[int, tuple[str, ...]] = {
    1: (
        "lint_format",
        "format_check",
        "type_check",
        "architecture_tests",
        "full_audit",
        "python_tests",
        "import_contracts",
        "semantic_dup",
    ),
    2: ("lint_format", "format_check", "full_audit"),
    3: ("full_audit",),
}


def _surface_checks(changed_files: Sequence[str]) -> set[str]:
    """Map observed surfaces to the CI jobs that cover them (§7.5 table)."""

    selected: set[str] = set()
    has_python_src = any(surfaces.normalize_path(p).startswith("src/") and p.endswith(".py") for p in changed_files)
    has_python_tests = any(p.endswith(".py") and surfaces.is_test_path(p) for p in changed_files)
    has_qa_governance = any(surfaces.normalize_path(p).startswith("src/scistudio/qa/") for p in changed_files)
    has_arch_or_spec = any(surfaces.is_architecture_doc_path(p) for p in changed_files)
    has_governed_docs = any(surfaces.is_governed_doc_path(p) for p in changed_files)
    has_frontend = any(surfaces.is_frontend_path(p) for p in changed_files)
    has_workflow_ci = any(surfaces.is_workflow_ci_path(p) for p in changed_files)
    has_packaging = any(surfaces.is_packaging_path(p) for p in changed_files)
    has_sentrux = surfaces.sentrux_applies_to_changes(changed_files)

    if has_python_src:
        selected.update({"lint_format", "format_check", "type_check", "python_tests", "import_contracts"})
    if has_python_tests:
        selected.update({"lint_format", "format_check", "python_tests"})
    if has_qa_governance:
        selected.update({"lint_format", "format_check", "type_check", "python_tests", "full_audit"})
    if has_arch_or_spec or has_governed_docs:
        selected.add("full_audit")
    if has_frontend:
        selected.add("frontend")
    if has_workflow_ci:
        selected.add("full_audit")
    if has_packaging:
        selected.add("wheel_release_smoke")
    if has_sentrux:
        selected.add("semantic_dup")
    return selected


def select_checks(
    *,
    tier: StrictnessTier,
    changed_files: Sequence[str],
    extra_checks: Sequence[str] = (),
) -> CheckSelection:
    """Infer the tier-selected required check set (§7.5).

    Tier 1 mirrors the full merge-blocking CI surface. Tier 2 runs the
    governance/lint/audit baseline plus changed-surface jobs. Tier 3 runs only
    mandatory checks for the observed diff.
    """

    selection = CheckSelection()
    chosen: set[str] = set(_BASELINE_BY_TIER.get(int(tier), ()))
    if tier == 1:
        # Full mirror regardless of observed diff (still add surface jobs).
        chosen.update(_surface_checks(changed_files))
    else:
        chosen.update(_surface_checks(changed_files))
    for name in extra_checks:
        if name in CHECK_CATALOG:
            chosen.add(name)
        else:
            selection.parity_gaps.append(f"requested check has no CI-equivalent mapping: {name}")

    for name in sorted(chosen):
        spec = CHECK_CATALOG.get(name)
        if spec is None:
            selection.parity_gaps.append(f"no CI-equivalent command for required job: {name}")
            continue
        if spec.pr_only:
            selection.pr_only.append(name)
        else:
            selection.required.append(name)
    return selection


def run_check(
    repo_root: Path,
    name: str,
    *,
    changed_files: Sequence[str],
    diff_fingerprint: str | None,
) -> CheckEvent:
    """Run a single check in the parity environment, returning a CheckEvent.

    Raw stdout/stderr go ONLY to ``.workflow/local/**`` (gitignored). The
    committed event carries a sanitized one-line summary plus a repo-relative
    ``raw_log_ref`` (§8).
    """

    spec = CHECK_CATALOG[name]
    versions = {tool: ver for tool, ver in resolve_ci_tool_versions(repo_root).items() if tool in spec.command}
    repo_relative_command = " ".join(spec.command)
    covered_paths = [p for p in changed_files if surfaces.normalize_path(p)]
    input_fp = fingerprint_paths(covered_paths) if covered_paths else diff_fingerprint

    env = None
    if spec.needs_src_import:
        import os

        env = dict(os.environ)
        existing = env.get("PYTHONPATH", "")
        src = str(repo_root / "src")
        env["PYTHONPATH"] = f"{src}{os.pathsep}{existing}" if existing else src

    import shutil

    if not spec.command or shutil.which(spec.command[0]) is None:
        return CheckEvent(
            name=name,
            command=repo_relative_command,
            tool_versions=versions,
            covered_surface=spec.covered_surface,
            input_fingerprint=input_fp,
            exit_code=None,
            status="skipped",
            summary=f"tool unavailable: {spec.command[0] if spec.command else '(none)'}",
        )

    try:
        completed = subprocess.run(
            list(spec.command),
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return CheckEvent(
            name=name,
            command=repo_relative_command,
            tool_versions=versions,
            covered_surface=spec.covered_surface,
            input_fingerprint=input_fp,
            exit_code=None,
            status="unknown",
            summary=f"execution error: {type(exc).__name__}",
        )

    raw_ref = _write_raw_log(repo_root, name, completed)
    status: Literal["pass", "fail"] = "pass" if completed.returncode == 0 else "fail"
    return CheckEvent(
        name=name,
        command=repo_relative_command,
        tool_versions=versions,
        covered_surface=spec.covered_surface,
        input_fingerprint=input_fp,
        exit_code=completed.returncode,
        status=status,
        summary="clean" if status == "pass" else f"exit {completed.returncode}",
        raw_log_ref=raw_ref,
    )


def _write_raw_log(repo_root: Path, name: str, completed: subprocess.CompletedProcess[str]) -> str:
    logs_dir = repo_root / LOCAL_LOGS_DIR
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{name}.log"
    body = f"# {name} (exit {completed.returncode})\n--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}\n"
    log_path.write_text(body, encoding="utf-8", errors="replace")
    return f"{LOCAL_LOGS_DIR}/{name}.log"


def event_is_valid_for(event: CheckEvent, *, input_fingerprint: str | None) -> bool:
    """Return True when a prior check event remains valid (§7.2 incremental).

    Evidence stays valid only when the covered surface's input fingerprint is
    unchanged. A later edit to that surface invalidates only this event.
    """

    if event.status != "pass":
        return False
    if event.input_fingerprint is None or input_fingerprint is None:
        return False
    return event.input_fingerprint == input_fingerprint
