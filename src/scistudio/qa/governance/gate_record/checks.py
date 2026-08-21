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

import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import scistudio.qa.governance.gate_record.parity as parity
import scistudio.qa.governance.gate_record.surfaces as surfaces
from scistudio.qa.governance.gate_record.io import LOCAL_LOGS_DIR, fingerprint_paths
from scistudio.qa.governance.gate_record.ledger import CheckEvent, StrictnessTier
from scistudio.qa.governance.gate_record.parity import resolve_ci_tool_versions


@dataclass(frozen=True)
class CheckSpec:
    """A CI-equivalent local check derived from the CI command snapshot."""

    name: str
    # The CI-mirror command: whole-repository, byte-identical in intent to the
    # CI job named by ``ci_job``. This is what CI runs and what ``--force-checks``
    # runs locally.
    command: tuple[str, ...]
    covered_surface: str
    # CI job this mirrors; used for parity-mapping diagnostics.
    ci_job: str
    # How the local variant narrows this check to the observed diff. ``none``
    # keeps the repository-scoped command locally, either because the check has
    # no meaningful file-list form (``full_audit``, ``wheel_release_smoke``) or
    # because its own runtime already bounds the work. See
    # ``diff_scoped_command`` for what each strategy builds.
    local_scope: str = "none"
    # Repo-relative working directory used by CI for this command.
    cwd: str = "."
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
        covered_surface="python_lint",
        ci_job="ci.yml/Lint & Format",
        local_scope="ruff_files",
    ),
    "format_check": CheckSpec(
        name="format_check",
        command=("ruff", "format", "--check", "."),
        covered_surface="python_lint",
        ci_job="ci.yml/Lint & Format",
        # Locally this REWRITES the changed files instead of failing on them.
        # Every one of the 98 recorded ``format_check`` failures across the
        # committed ledgers was resolvable by running the formatter, so failing
        # the gate on them only ever cost a cycle. CI still runs ``--check``.
        local_scope="ruff_format_fix",
    ),
    "type_check": CheckSpec(
        name="type_check",
        command=("mypy", "src/scistudio/", "--ignore-missing-imports"),
        covered_surface="python_types",
        ci_job="ci.yml/Type Check",
        local_scope="mypy_files",
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
        # Two-phase runner: parallel bulk (`-n auto -m "not serial"`) then serial
        # (`-n 0 -m serial`), so PTY/subprocess/thread tests cannot crash an xdist
        # worker (#1896). This is the gate's single-command equivalent of the two
        # literal `pytest` phases the CI `test` job runs inline; the weakened-CI
        # guard requires the literal `pytest` token in ci.yml, so the two diverge
        # in form but not policy. Forwarded flags apply to both phases.
        command=(
            "python",
            "-m",
            "scistudio.qa.testing.run_python_tests",
            "--timeout=60",
            "--timeout-method=thread",
        ),
        covered_surface="python_tests",
        ci_job="ci.yml/Test (Python 3.11, 3.13)",
        # The local variant appends ``--no-cov`` plus the test paths affected by
        # the diff. ``--no-cov`` is not optional: the repository-wide
        # ``--cov-fail-under`` in pyproject.toml makes ANY subset run fail by
        # construction, so without it no incremental test run is possible at all.
        # CI keeps the floor and the full suite (spec FR-003, FR-004).
        local_scope="pytest_select",
        needs_src_import=True,
    ),
    "import_contracts": CheckSpec(
        name="import_contracts",
        command=("lint-imports",),
        covered_surface="python_imports",
        ci_job="ci.yml/Import Contracts",
        needs_src_import=True,
    ),
    "frontend": CheckSpec(
        name="frontend",
        command=("npm", "run", "check:ci"),
        covered_surface="frontend",
        ci_job="ci.yml/Frontend",
        cwd="frontend",
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
        # The scanner roots at ``src/scistudio`` and rglobs ``*.py``; nothing
        # outside that tree (plus the baseline) can change its verdict.
        covered_surface="python_semantics",
        ci_job="semantic-dup-scan.yml/Semantic duplication ratchet",
    ),
    "deferral_discipline": CheckSpec(
        name="deferral_discipline",
        command=(
            "python",
            "scripts/deferral_scan.py",
            "--check",
            "docs/audit/baselines/deferral-baseline.json",
        ),
        # ``scripts/deferral_scan.py`` rglobs ``*.py`` and reads nothing else, so
        # a non-Python change cannot alter its verdict (spec FR-007).
        covered_surface="python_deferrals",
        ci_job="deferral-scan.yml/Deferral discipline ratchet",
    ),
}


# Repository-scoped checks whose local variant narrows to the observed diff.
# Each strategy is implemented by ``diff_scoped_command``.
_RUFF_TARGET_SUFFIXES = (".py", ".pyi")


def _changed_python_files(changed_files: Sequence[str], *, under: str | None = None) -> list[str]:
    """Return existing changed Python paths, optionally limited to a subtree."""

    selected = []
    for raw in changed_files:
        path = surfaces.normalize_path(raw)
        if not path.endswith(_RUFF_TARGET_SUFFIXES):
            continue
        if under is not None and not path.startswith(under):
            continue
        selected.append(path)
    return sorted(set(selected))


def _mirror_test_targets(repo_root: Path, module_path: str) -> str | None:
    """Map a changed source module to the test path that covers it.

    Returns the longest mirrored ``tests/`` directory that exists, or a mirrored
    ``test_<stem>.py`` file, or ``None`` when neither resolves. ``None`` means
    "cannot prove which tests cover this", which the caller turns into a
    full-suite run. Under-selection is the one failure mode that would let a
    real break reach CI, so every unresolved case widens (spec FR-003).
    """

    prefix = "src/scistudio/"
    if not module_path.startswith(prefix):
        return None
    parts = module_path[len(prefix) :].split("/")
    package_parts, stem = parts[:-1], parts[-1].removesuffix(".py")
    for depth in range(len(package_parts), 0, -1):
        candidate = "tests/" + "/".join(package_parts[:depth])
        if (repo_root / candidate).is_dir():
            return candidate
    mirrored_file = "tests/" + "/".join([*package_parts, f"test_{stem}.py"])
    if (repo_root / mirrored_file).is_file():
        return mirrored_file
    return None


def select_test_targets(repo_root: Path, changed_files: Sequence[str]) -> tuple[str, ...] | None:
    """Return the test paths affected by the diff, or ``None`` to run everything.

    ``None`` is the safe answer and is returned whenever the mapping cannot be
    proven: a changed global input (pytest/coverage config, a CI workflow, a
    shared ``conftest.py``), a non-Python file under ``tests/`` such as a
    fixture, or a source module with no mirrored test location.
    """

    targets: set[str] = set()
    saw_python = False
    for raw in changed_files:
        path = surfaces.normalize_path(raw)
        if _is_global_test_input(path):
            return None
        if path.startswith("tests/"):
            if not path.endswith(".py"):
                # A fixture, golden file, or data asset: cannot tell which tests
                # read it.
                return None
            saw_python = True
            if Path(path).name == "conftest.py":
                targets.add(str(Path(path).parent).replace("\\", "/"))
            else:
                targets.add(path)
            continue
        if not path.endswith(_RUFF_TARGET_SUFFIXES):
            continue
        saw_python = True
        if not path.startswith("src/scistudio/"):
            # ``scripts/**`` and ``packages/**`` have no mirrored test tree.
            return None
        mirrored = _mirror_test_targets(repo_root, path)
        if mirrored is None:
            return None
        targets.add(mirrored)
    if not saw_python or not targets:
        return None
    return tuple(sorted(targets))


def _is_global_test_input(path: str) -> bool:
    """Return True for files that can change the outcome of any test."""

    return (
        path in {"pyproject.toml", "setup.cfg", "tox.ini", "conftest.py", "tests/conftest.py"}
        or path.startswith(".github/workflows/")
        or path == ".pre-commit-config.yaml"
    )


def diff_scoped_command(
    spec: CheckSpec,
    *,
    repo_root: Path,
    changed_files: Sequence[str],
) -> tuple[str, ...] | None:
    """Return the local diff-scoped command, or ``None`` to use the CI mirror.

    ``None`` means this invocation runs the repository-scoped command: either the
    check has no diff-scoped strategy, or the strategy could not narrow safely.
    """

    if spec.local_scope == "none":
        return None
    if spec.local_scope == "ruff_files":
        files = _changed_python_files(changed_files)
        return (*spec.command[:-1], *files) if files else None
    if spec.local_scope == "ruff_format_fix":
        files = _changed_python_files(changed_files)
        # Drop ``--check`` and the ``.`` target: format the changed files.
        return ("ruff", "format", *files) if files else None
    if spec.local_scope == "mypy_files":
        files = _changed_python_files(changed_files, under="src/scistudio/")
        return ("mypy", *files, "--ignore-missing-imports") if files else None
    if spec.local_scope == "pytest_select":
        targets = select_test_targets(repo_root, changed_files)
        return (*spec.command, "--no-cov", *targets) if targets else None
    return None


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
        "deferral_discipline",
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
    # Tier breadth lives entirely in ``_BASELINE_BY_TIER``: Tier 1 names the full
    # merge-blocking set up front, lower tiers name a baseline that the observed
    # diff then extends. The surface jobs are added identically at every tier —
    # this used to be an ``if tier == 1 / else`` whose two arms executed the same
    # statement (spec gate-local-incremental-checks FR-011). How *broadly* each
    # selected check runs locally is a separate axis, owned by the evaluator's
    # per-mode scope decision, not by selection.
    chosen: set[str] = set(_BASELINE_BY_TIER.get(int(tier), ()))
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


# Signatures in check output that indicate an ENVIRONMENT-PARITY cause (a local
# environment that is not CI-equivalent), NOT a genuine code/assertion failure.
# A pytest collection ``ImportError``/``ModuleNotFoundError`` means an optional
# plugin or dependency CI has is absent locally; a "No module named" from any
# tool is the same class of gap. These must read as parity gaps (§7.10), never
# as code failures, so a real test failure still reads as a code failure.
_PARITY_CAUSE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"ModuleNotFoundError: No module named ['\"]?(?P<name>[\w.]+)"), "missing module: {name}"),
    (re.compile(r"No module named ['\"]?(?P<name>[\w.]+)"), "missing module: {name}"),
    (
        re.compile(r"ImportError(?:\s+while importing| collecting)?[^\n]*?(?P<name>[\w./-]+)?"),
        "import error during collection",
    ),
    (re.compile(r"error in (?P<name>[\w.-]+) setup command"), "build/setup dependency error: {name}"),
    (re.compile(r"DistributionNotFound|pkg_resources\.\w*NotFound"), "missing distribution/dependency"),
    (re.compile(r"executable not found|command not found|not recognized as an internal"), "tool/interpreter not found"),
)

# A pytest collection error specifically (distinct from test-body failures).
_PYTEST_COLLECTION_ERROR_RE = re.compile(r"errors? during collection|ERROR collecting", re.IGNORECASE)
_PYTEST_TEST_FAILURE_RE = re.compile(r"=+\s+FAILURES\s+=+|^FAILED\s+", re.IGNORECASE | re.MULTILINE)


def detect_parity_cause(output: str) -> str | None:
    """Classify a nonzero check exit as an environment-parity cause, or None.

    Returns a short human-readable detail of what is missing when the failure is
    caused by the LOCAL environment not being CI-equivalent (missing optional
    plugin / dependency / interpreter / tool, or a pytest collection ImportError
    /ModuleNotFoundError). Returns ``None`` for genuine assertion/code failures so
    they still read as code failures (§7.10).
    """

    if not output:
        return None
    has_pytest_body_failure = _PYTEST_TEST_FAILURE_RE.search(output) is not None
    has_pytest_collection_error = _PYTEST_COLLECTION_ERROR_RE.search(output) is not None
    for pattern, template in _PARITY_CAUSE_PATTERNS:
        match = pattern.search(output)
        if match is None:
            continue
        if (
            (
                template in {"tool/interpreter not found", "missing distribution/dependency"}
                or template.startswith("missing module")
            )
            and has_pytest_body_failure
            and not has_pytest_collection_error
        ):
            continue
        # An ImportError reported INSIDE a normal test body (not at collection)
        # could be a genuine bug; only treat import/module errors as parity gaps
        # when they look like collection-time or top-level import problems.
        if template == "import error during collection" and not has_pytest_collection_error:
            # A bare ImportError without a collection marker is ambiguous; if a
            # ModuleNotFoundError/No-module signature also matched it is covered
            # by an earlier pattern, so here we skip to avoid false positives.
            continue
        try:
            named = match.groupdict().get("name")
        except (IndexError, AttributeError):
            named = None
        return template.format(name=named) if "{name}" in template and named else template.replace(" {name}", "")
    return None


def _resolve_execution(
    repo_root: Path,
    spec: CheckSpec,
    command: Sequence[str] | None = None,
) -> tuple[list[str] | None, dict[str, str] | None]:
    """Map a check spec to a concrete argv + env using the parity venv (§7.10).

    ``command`` overrides ``spec.command`` so the diff-scoped local variant runs
    through exactly the same tool resolution as the CI-mirror command.

    When the isolated per-worktree venv is provisioned, the check's tool resolves
    to the venv's executable (so local == CI tool versions), and a ``needs_src_
    import`` check runs through the venv interpreter, which already imports
    ``scistudio`` via the editable install — no ``PYTHONPATH`` hack needed.

    Falls back to the ambient executable + ``PYTHONPATH=src`` when no venv exists
    (CI mode, or a non-provisioned environment), preserving the prior behaviour.
    Returns ``(None, None)`` when the tool cannot be resolved anywhere (skipped).
    """

    effective = tuple(command) if command is not None else spec.command
    if not effective:
        return None, None
    tool = effective[0]
    rest = list(effective[1:])
    venv = parity.venv_path(repo_root)
    venv_exists = venv.exists()

    # Python-module invocations (``python -m ...``) run via the venv interpreter
    # when present so the editable-installed scistudio is importable directly.
    if tool == "python":
        if venv_exists:
            py = parity.venv_python(venv)
            if py.exists():
                return [str(py), *rest], None
        py_env = dict(os.environ)
        existing = py_env.get("PYTHONPATH", "")
        src = str(repo_root / "src")
        py_env["PYTHONPATH"] = f"{src}{os.pathsep}{existing}" if existing else src
        return list(effective), py_env

    # Console-script tools (ruff, mypy, pytest, lint-imports, npm). Prefer the
    # venv shim; the venv interpreter already imports scistudio for the
    # import-needing tools, so no PYTHONPATH is required there.
    venv_tool = parity.resolve_venv_executable(repo_root, tool) if venv_exists else None
    if venv_tool is not None:
        return [str(venv_tool), *rest], None

    ambient = shutil.which(tool)
    if ambient is None:
        return None, None
    env: dict[str, str] | None = None
    if spec.needs_src_import:
        env = dict(os.environ)
        existing = env.get("PYTHONPATH", "")
        src = str(repo_root / "src")
        env["PYTHONPATH"] = f"{src}{os.pathsep}{existing}" if existing else src
    return [ambient, *rest], env


def _with_check_env(name: str, env: dict[str, str] | None) -> dict[str, str] | None:
    """Mirror CI-only environment knobs for local check execution.

    No CI-only env knobs are currently required: plugin packages are
    discovered through their installed ``scistudio.*`` entry points (the
    monorepo source-scan dev fallback was removed in #1770), so the local
    check environment matches CI without extra flags.
    """
    return env


def run_check(
    repo_root: Path,
    name: str,
    *,
    changed_files: Sequence[str],
    diff_fingerprint: str | None,
    input_fingerprint: str | None = None,
    scope: Literal["repo", "diff"] = "repo",
) -> CheckEvent:
    """Run a single check in the parity environment, returning a CheckEvent.

    Raw stdout/stderr go ONLY to ``.workflow/local/**`` (gitignored). The
    committed event carries a sanitized one-line summary plus a repo-relative
    ``raw_log_ref`` (§8).

    ``scope="diff"`` asks for the local variant narrowed to ``changed_files``.
    When the requested check has no diff-scoped strategy, or its strategy cannot
    narrow safely, this silently falls back to the repository-scoped CI-mirror
    command and records ``scope="repo"`` — the event always states which command
    actually ran, never which one was requested.
    """

    spec = CHECK_CATALOG[name]
    scoped_command = (
        diff_scoped_command(spec, repo_root=repo_root, changed_files=changed_files) if scope == "diff" else None
    )
    effective_command = scoped_command or spec.command
    event_scope: Literal["repo", "diff"] = "diff" if scoped_command is not None else "repo"
    versions = {tool: ver for tool, ver in resolve_ci_tool_versions(repo_root).items() if tool in effective_command}
    command_text = " ".join(effective_command)
    repo_relative_command = command_text if spec.cwd == "." else f"(cd {spec.cwd} && {command_text})"
    covered_paths = [p for p in changed_files if surfaces.normalize_path(p)]
    input_fp = input_fingerprint or (fingerprint_paths(covered_paths) if covered_paths else diff_fingerprint)

    argv, env = _resolve_execution(repo_root, spec, effective_command)
    env = _with_check_env(name, env)

    if argv is None:
        return CheckEvent(
            name=name,
            command=repo_relative_command,
            tool_versions=versions,
            covered_surface=spec.covered_surface,
            scope=event_scope,
            input_fingerprint=input_fp,
            exit_code=None,
            status="skipped",
            summary=f"tool unavailable: {spec.command[0] if spec.command else '(none)'}",
        )

    try:
        completed = subprocess.run(
            argv,
            cwd=repo_root / spec.cwd,
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
            scope=event_scope,
            input_fingerprint=input_fp,
            exit_code=None,
            status="unknown",
            summary=f"execution error: {type(exc).__name__}",
        )

    raw_ref = _write_raw_log(repo_root, name, completed)
    if completed.returncode == 0:
        return CheckEvent(
            name=name,
            command=repo_relative_command,
            tool_versions=versions,
            covered_surface=spec.covered_surface,
            scope=event_scope,
            input_fingerprint=input_fp,
            exit_code=completed.returncode,
            status="pass",
            summary="clean",
            raw_log_ref=raw_ref,
        )

    # Nonzero exit: distinguish an environment-parity cause from a genuine code
    # failure (§7.10). A parity cause (collection ImportError / missing module /
    # missing tool) is NOT a code failure; it means the local env is not
    # CI-equivalent. We still record status="fail" so the surface is not treated
    # as passing, but flag ``parity_gap`` so the evaluator reports it distinctly
    # and never as a misleading code failure.
    combined_output = f"{completed.stdout}\n{completed.stderr}"
    parity_detail = detect_parity_cause(combined_output)
    return CheckEvent(
        name=name,
        command=repo_relative_command,
        tool_versions=versions,
        covered_surface=spec.covered_surface,
        scope=event_scope,
        input_fingerprint=input_fp,
        exit_code=completed.returncode,
        status="fail",
        summary=(f"parity gap: {parity_detail}" if parity_detail else f"exit {completed.returncode}"),
        raw_log_ref=raw_ref,
        parity_gap=parity_detail is not None,
        parity_detail=parity_detail,
    )


def _write_raw_log(repo_root: Path, name: str, completed: subprocess.CompletedProcess[str]) -> str:
    logs_dir = repo_root / LOCAL_LOGS_DIR
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{name}.log"
    body = f"# {name} (exit {completed.returncode})\n--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}\n"
    log_path.write_text(body, encoding="utf-8", errors="replace")
    return f"{LOCAL_LOGS_DIR}/{name}.log"


def event_is_valid_for(
    event: CheckEvent,
    *,
    input_fingerprint: str | None,
    require_repo_scope: bool = False,
) -> bool:
    """Return True when a prior check event remains valid (§7.2 incremental).

    Evidence stays valid only when the covered surface's input fingerprint is
    unchanged. A later edit to that surface invalidates only this event.

    ``require_repo_scope`` rejects diff-scoped evidence. A diff-scoped run proves
    the changed files, not the whole surface, so it cannot stand in for a
    CI-mirror obligation (spec gate-local-incremental-checks FR-008).
    """

    if event.status != "pass":
        return False
    if require_repo_scope and event.scope != "repo":
        return False
    if event.input_fingerprint is None or input_fingerprint is None:
        return False
    return event.input_fingerprint == input_fingerprint
