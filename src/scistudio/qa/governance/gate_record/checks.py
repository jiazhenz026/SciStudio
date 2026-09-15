"""CI-equivalent check selection and execution."""
# Maintainer context (kept outside generated API documentation):
# CI-equivalent check selection and execution for ADR-042 Addendum 6 (§7.5).
#
# The required check set is derived from three inputs (§7.5):
#
# 1. the strictness tier (task kind, escalated by observed diff per §7.6);
# 2. the observed changed-file surfaces from git;
# 3. the CI workflow graph.
#
# CI workflow YAML is the source of command truth. To keep the core importable
# without a YAML dependency, the canonical CI command snapshot from ADR-042
# Addendum 6 §7.5 is encoded as data here and cross-checked against the presence
# of the workflow files. When a required CI job cannot be mapped to a local
# command, the evaluator fails closed for PR readiness (§7.5, §7.10).
#
# Execution writes raw transcripts only under ``.workflow/local/**`` (gitignored)
# and returns sanitized :class:`CheckEvent` payloads.
# Development references: ADR-042, Addendum 6.

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

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
    # runs locally, except for ``python_tests``, which never runs at repository
    # scope outside CI (#2386).
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
    # Repo-relative path of an AuditReport JSON this check writes instead of
    # printing its findings. A check that reports only to a file leaves an empty
    # transcript, so a tail of its raw log carries nothing and the failure reads
    # as "failed, no reason given" (#2143). When set, the evaluator renders the
    # report file into the repair hint. ``None`` means the check prints its own
    # findings and the transcript is the whole story.
    report_json: str | None = None


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
        # ``--output`` above is the only place full_audit reports; stdout stays
        # empty even on failure.
        report_json=".audit/full-audit.json",
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
        # CI keeps the floor and the full suite (spec FR-003, FR-004). Locally this
        # command is never run without explicit targets: unmapped inputs are
        # deferred to CI instead of widening (#2386).
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
    # #2150: commit-time git hooks are removed; their hygiene checks moved here.
    # The pre-commit framework hooks in .pre-commit-config.yaml are all bound to
    # the `manual` stage (nothing fires on `git commit`); this check runs that
    # hygiene set over the tree at the PR-gating modes. Ruff/mypy are NOT part of
    # it — lint_format / format_check / type_check above already own them.
    "commit_hygiene": CheckSpec(
        name="commit_hygiene",
        command=("pre-commit", "run", "--all-files", "--hook-stage", "manual"),
        covered_surface="hygiene",
        ci_job="workflow-gate.yml/Verify Workflow Compliance",
    ),
}


# Repository-scoped checks whose local variant narrows to the observed diff.
# Each strategy is implemented by ``diff_scoped_command``.
_RUFF_TARGET_SUFFIXES = (".py", ".pyi")


def _changed_python_files(
    changed_files: Sequence[str],
    *,
    repo_root: Path,
    under: str | None = None,
) -> list[str]:
    """Return changed Python paths that still exist, optionally under a subtree.

    Deleted paths are dropped: the observed diff includes them, but handing a
    removed file to ruff or mypy is an execution error, not a finding. When a
    diff only deletes Python files the caller gets an empty list and falls back
    to the repository-scoped command, which is the correct answer for a deletion.
    """

    selected = []
    for raw in changed_files:
        path = surfaces.normalize_path(raw)
        if not path.endswith(_RUFF_TARGET_SUFFIXES):
            continue
        if under is not None and not path.startswith(under):
            continue
        if not (repo_root / path).is_file():
            continue
        selected.append(path)
    return sorted(set(selected))


# The local gate never runs the Python test suite over the whole repository
# (#2386, ADR-042 Addendum 7 §2.2). Paths that would name the whole suite are
# refused as test targets; ``ci.yml`` is the only place the full suite runs.
_WHOLE_SUITE_TARGETS: frozenset[str] = frozenset({"", ".", "./", "tests", "tests/"})
# Basenames too generic to identify which tests read a file.
_GENERIC_BASENAMES: frozenset[str] = frozenset({"__init__.py", "conftest.py", "setup.py", "__main__.py"})
# A module imported by more test modules than this is effectively global; its
# importers are not added to the selection.
_IMPORTER_CAP = 40
# Deferred-reason entries kept on a check event before the rest are counted off.
_DEFERRED_REASONS_SHOWN = 5


class FullPythonSuiteRefusedError(RuntimeError):
    """Raised when a local invocation would run the whole Python test suite."""


def running_in_ci() -> bool:
    """Return True inside a CI runner (GitHub Actions sets ``CI=true``)."""

    return os.environ.get("CI", "").strip().lower() in {"true", "1", "yes"}


@dataclass(frozen=True)
class PythonTestSelection:
    """The bounded test selection derived from a diff.

    ``targets`` are the test paths the local gate runs. ``deferred`` names the
    changed inputs whose effect on the suite could not be mapped to tests; their
    coverage is deferred to the full-suite run in ``ci.yml``. An empty
    ``targets`` means no local test run at all, never "run everything".
    """

    targets: tuple[str, ...] = ()
    deferred: tuple[str, ...] = ()

    @property
    def coverage_deferred_to_ci(self) -> bool:
        return bool(self.deferred) or not self.targets

    def deferred_reason(self) -> str | None:
        """Return a short, repo-relative reason line, or None when nothing is deferred."""

        if not self.coverage_deferred_to_ci:
            return None
        reasons = list(self.deferred) or ["no test target derivable from the diff"]
        shown = reasons[:_DEFERRED_REASONS_SHOWN]
        hidden = len(reasons) - len(shown)
        return "; ".join(shown) + (f"; ... {hidden} more" if hidden > 0 else "")


class _TestCorpus:
    """Lazily read ``tests/**/*.py`` once per selection for reference lookups."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._files: list[tuple[str, str]] | None = None

    def files(self) -> list[tuple[str, str]]:
        if self._files is None:
            loaded: list[tuple[str, str]] = []
            tests_root = self._repo_root / "tests"
            if tests_root.is_dir():
                for file in sorted(tests_root.rglob("*.py")):
                    try:
                        text = file.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    loaded.append((file.relative_to(self._repo_root).as_posix(), text))
            self._files = loaded
        return self._files

    def test_modules_matching(self, predicate: Callable[[str], bool]) -> list[str]:
        """Return collectable test modules whose text satisfies ``predicate``.

        A matching helper module that pytest does not collect contributes the
        test modules in its own directory instead.
        """

        selected: set[str] = set()
        for rel, text in self.files():
            if not predicate(text):
                continue
            if _is_test_module(rel):
                selected.add(rel)
            else:
                selected.update(_directory_test_modules(self._repo_root, str(Path(rel).parent)))
        return sorted(selected)


def _is_test_module(path: str) -> bool:
    return Path(path).name.startswith("test_") and path.endswith(".py")


def _directory_test_modules(repo_root: Path, directory: str) -> list[str]:
    """Return the ``test_*.py`` modules directly inside ``directory``."""

    directory = directory.replace("\\", "/").rstrip("/")
    if directory in _WHOLE_SUITE_TARGETS:
        return []
    folder = repo_root / directory
    if not folder.is_dir():
        return []
    return sorted(f"{directory}/{file.name}" for file in folder.glob("test_*.py") if file.is_file())


def _mirror_test_targets(repo_root: Path, module_path: str) -> str | None:
    """Map a source module to its mirrored test file, else its mirrored directory.

    Prefers the nearest mirrored ``test_<stem>.py`` along the package chain, then
    the longest mirrored ``tests/<package>`` directory that exists. Never returns
    the ``tests/`` root itself. ``None`` means no mirrored location exists.
    """
    # Development references: FR-003, #2386.

    prefix = "src/scistudio/"
    if not module_path.startswith(prefix):
        return None
    parts = module_path[len(prefix) :].split("/")
    package_parts, stem = parts[:-1], parts[-1].removesuffix(".pyi").removesuffix(".py")
    if stem != "__init__":
        for depth in range(len(package_parts), -1, -1):
            mirrored_file = "tests/" + "/".join([*package_parts[:depth], f"test_{stem}.py"])
            if (repo_root / mirrored_file).is_file():
                return mirrored_file
    for depth in range(len(package_parts), 0, -1):
        candidate = "tests/" + "/".join(package_parts[:depth])
        if (repo_root / candidate).is_dir():
            return candidate
    return None


def _module_name(module_path: str) -> str | None:
    """Return the dotted name of a ``src/`` module below the top package, or None."""

    if not module_path.startswith("src/"):
        return None
    parts = module_path[len("src/") :].removesuffix(".pyi").removesuffix(".py").split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if len(parts) >= 2 else None


def _importers(corpus: _TestCorpus, module_path: str) -> list[str]:
    """Return test modules importing the module; empty when none or too broadly imported."""

    dotted = _module_name(module_path)
    if dotted is None:
        return []
    package, _, leaf = dotted.rpartition(".")
    pattern = re.compile(
        rf"\b{re.escape(dotted)}\b|\bfrom\s+{re.escape(package)}\s+import\s+[^\n]*\b{re.escape(leaf)}\b"
    )
    found = corpus.test_modules_matching(lambda text: pattern.search(text) is not None)
    return found if len(found) <= _IMPORTER_CAP else []


def _referencing_tests(corpus: _TestCorpus, path: str) -> list[str]:
    """Return test modules naming ``path`` by repo path, tests-relative path, or basename."""

    tokens = {path}
    if path.startswith("tests/"):
        tokens.add(path[len("tests/") :])
    name = Path(path).name
    if name and name not in _GENERIC_BASENAMES:
        tokens.add(name)
    return corpus.test_modules_matching(lambda text: any(token in text for token in tokens))


def select_python_tests(repo_root: Path, changed_files: Sequence[str]) -> PythonTestSelection:
    """Return the bounded test selection for the diff; never the whole suite.

    Each changed input either maps to concrete test paths or is recorded as
    deferred to CI. Nothing widens: a global input (pytest/coverage config, a CI
    workflow, the root ``conftest.py``), an asset no test references, or a module
    with no mirrored or importing test is deferred, while the rest of the diff
    still selects its tests (ADR-042 Addendum 7 §2.2, #2386).
    """

    corpus = _TestCorpus(repo_root)
    targets: set[str] = set()
    deferred: list[str] = []

    def _add(paths: Sequence[str]) -> bool:
        usable = [p for p in paths if p.rstrip("/") not in _WHOLE_SUITE_TARGETS]
        targets.update(usable)
        return bool(usable)

    for raw in changed_files:
        path = surfaces.normalize_path(raw)
        if not path:
            continue
        if _is_global_test_input(path):
            deferred.append(f"global test input: {path}")
            continue
        exists = (repo_root / path).exists()
        if path.startswith("tests/"):
            parent = str(Path(path).parent).replace("\\", "/")
            if not path.endswith(".py"):
                # A fixture, golden file, or snapshot: select the tests that read it.
                found = [*_referencing_tests(corpus, path), *_directory_test_modules(repo_root, parent)]
                if not _add(found):
                    deferred.append(f"unreferenced test asset: {path}")
                continue
            if Path(path).name == "conftest.py":
                if not (exists and _add([parent])):
                    deferred.append(f"conftest without a test package: {path}")
                continue
            if exists:
                _add([path])
            elif not _add([parent] if (repo_root / parent).is_dir() else []):
                deferred.append(f"deleted test module: {path}")
            continue
        if not path.endswith(_RUFF_TARGET_SUFFIXES):
            continue
        if path.startswith("src/scistudio/"):
            if exists:
                mirrored = _mirror_test_targets(repo_root, path)
                # The mirrored location plus every test that imports the module
                # (tests do not always live under the mirrored package path).
                found = [mirrored] if mirrored else []
                found.extend(_importers(corpus, path))
            else:
                # A deleted module: its package's mirrored tests plus any test that
                # still imports it (those would now fail to import).
                package_init = str(Path(path).parent / "__init__.py").replace("\\", "/")
                package_dir = _mirror_test_targets(repo_root, package_init)
                found = [package_dir] if package_dir else []
                found.extend(_importers(corpus, path))
            if not _add(found):
                deferred.append(f"no mirrored or importing test: {path}")
            continue
        # ``scripts/**``, ``packages/**``, and other Python outside the package.
        found = []
        if path.startswith("scripts/"):
            mirrored_script = f"tests/scripts/test_{Path(path).stem}.py"
            if (repo_root / mirrored_script).is_file():
                found.append(mirrored_script)
        found.extend(_referencing_tests(corpus, path))
        if not _add(found):
            deferred.append(f"no test references: {path}")
    return PythonTestSelection(targets=tuple(sorted(targets)), deferred=tuple(deferred))


def select_test_targets(repo_root: Path, changed_files: Sequence[str]) -> tuple[str, ...]:
    """Return the bounded test paths affected by the diff (possibly empty, never everything)."""

    return select_python_tests(repo_root, changed_files).targets


def assert_bounded_python_test_argv(argv: Sequence[str]) -> None:
    """Refuse a test-runner invocation outside CI that names no explicit test target.

    The chokepoint for local Python test execution: a target-less invocation, or
    one naming the whole ``tests/`` tree or the repository root, runs the full
    suite, which is forbidden outside CI (#2386). Raises
    :class:`FullPythonSuiteRefusedError`.
    """

    if running_in_ci():
        return
    targets = [arg for arg in argv if _looks_like_test_target(arg)]
    if not targets:
        raise FullPythonSuiteRefusedError(
            "refusing to run the Python test suite without explicit test targets outside CI "
            "(the full suite runs only in ci.yml; #2386)"
        )
    whole = [arg for arg in targets if arg.split("::", 1)[0].rstrip("/") in _WHOLE_SUITE_TARGETS]
    if whole:
        raise FullPythonSuiteRefusedError(
            f"refusing to run the whole Python test tree outside CI: {', '.join(whole)} (#2386)"
        )


def _looks_like_test_target(arg: str) -> bool:
    """Return True for a positional pytest path argument (not an option or option value)."""

    if arg.startswith("-"):
        return False
    head = arg.split("::", 1)[0]
    return head in _WHOLE_SUITE_TARGETS or head.startswith("tests") or head.endswith(".py") or "/" in head


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
    ``python_tests`` (``pytest_select``) never returns ``None``; its selection may
    be empty, which means no local test run with coverage deferred to CI.
    """

    if spec.local_scope == "none":
        return None
    if spec.local_scope == "ruff_files":
        files = _changed_python_files(changed_files, repo_root=repo_root)
        return (*spec.command[:-1], *files) if files else None
    if spec.local_scope == "ruff_format_fix":
        files = _changed_python_files(changed_files, repo_root=repo_root)
        # Drop ``--check`` and the ``.`` target: format the changed files.
        return ("ruff", "format", *files) if files else None
    if spec.local_scope == "mypy_files":
        files = _changed_python_files(changed_files, repo_root=repo_root, under="src/scistudio/")
        return ("mypy", *files, "--ignore-missing-imports") if files else None
    if spec.local_scope == "pytest_select":
        # Never ``None``: the repository-scoped suite is not a local fallback
        # (#2386). An empty selection is handled by ``run_check`` as a deferral.
        targets = select_test_targets(repo_root, changed_files)
        return (*spec.command, "--no-cov", *targets)
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
        "deferral_discipline",
    ),
    2: ("lint_format", "format_check", "full_audit"),
    3: ("full_audit",),
}


def _surface_checks(changed_files: Sequence[str]) -> set[str]:
    """Map observed surfaces to the CI jobs that cover them."""
    # Maintainer context:
    # Map observed surfaces to the CI jobs that cover them (§7.5 table).

    selected: set[str] = set()
    has_python_src = any(surfaces.normalize_path(p).startswith("src/") and p.endswith(".py") for p in changed_files)
    has_python_tests = any(p.endswith(".py") and surfaces.is_test_path(p) for p in changed_files)
    has_qa_governance = any(surfaces.normalize_path(p).startswith("src/scistudio/qa/") for p in changed_files)
    has_arch_or_spec = any(surfaces.is_architecture_doc_path(p) for p in changed_files)
    has_governed_docs = any(surfaces.is_governed_doc_path(p) for p in changed_files)
    has_frontend = any(surfaces.is_frontend_path(p) for p in changed_files)
    has_workflow_ci = any(surfaces.is_workflow_ci_path(p) for p in changed_files)
    has_packaging = any(surfaces.is_packaging_path(p) for p in changed_files)

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
    return selected


def select_checks(
    *,
    tier: StrictnessTier,
    changed_files: Sequence[str],
    extra_checks: Sequence[str] = (),
) -> CheckSelection:
    """Infer the tier-selected required check set.

    Tier 1 mirrors the full merge-blocking CI surface. Tier 2 runs the
    governance/lint/audit baseline plus changed-surface jobs. Tier 3 runs only
    mandatory checks for the observed diff.
    """
    # Maintainer context:
    # Infer the tier-selected required check set (§7.5).

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
    they still read as code failures.
    """
    # Maintainer context:
    # Returns a short human-readable detail of what is missing when the failure is
    # caused by the LOCAL environment not being CI-equivalent (missing optional
    # plugin / dependency / interpreter / tool, or a pytest collection ImportError
    # /ModuleNotFoundError). Returns ``None`` for genuine assertion/code failures so
    # they still read as code failures (§7.10).

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
    """Map a check spec to a concrete argv + env using the parity venv.

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
    # Maintainer context:
    # Map a check spec to a concrete argv + env using the parity venv (§7.10).

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
    monorepo source-scan dev fallback was removed in), so the local
    check environment matches CI without extra flags.
    """
    # Development references: #1770.
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
    ``raw_log_ref``.

    ``scope="diff"`` asks for the local variant narrowed to ``changed_files``.
    When the requested check has no diff-scoped strategy, or its strategy cannot
    narrow safely, this falls back to the repository-scoped CI-mirror command and
    records ``scope="repo"`` — the event always states which command actually
    ran, never which one was requested.

    ``python_tests`` is the exception: outside CI it never runs at repository
    scope, whatever scope was requested (#2386). It runs the bounded diff-derived
    selection; when that selection is empty no test process starts, and the event
    passes with ``coverage_deferred_to_ci`` set. Any invocation that still reaches
    the runner without explicit targets raises
    :class:`FullPythonSuiteRefusedError`.
    """
    # Maintainer context:
    # Raw stdout/stderr go ONLY to ``.workflow/local/**`` (gitignored). The
    # committed event carries a sanitized one-line summary plus a repo-relative
    # ``raw_log_ref`` (§8).

    spec = CHECK_CATALOG[name]
    selection: PythonTestSelection | None = None
    if spec.local_scope == "pytest_select" and not (scope == "repo" and running_in_ci()):
        selection = select_python_tests(repo_root, changed_files)
        scoped_command: tuple[str, ...] | None = (*spec.command, "--no-cov", *selection.targets)
    else:
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
    deferred_reason = selection.deferred_reason() if selection is not None else None
    common: dict[str, Any] = {
        "name": name,
        "command": repo_relative_command,
        "tool_versions": versions,
        "covered_surface": spec.covered_surface,
        "scope": event_scope,
        "input_fingerprint": input_fp,
        "coverage_deferred_to_ci": deferred_reason is not None,
        "deferred_reason": deferred_reason,
    }

    if selection is not None and not selection.targets:
        # Nothing selectable: no local test process at all. The full suite is
        # ci.yml's job on the same PR; this event records the deferral and
        # satisfies the local/pre-PR obligation (ADR-042 Addendum 7 §2.2).
        return CheckEvent(
            **{**common, "command": f"{repo_relative_command} (no targets; not executed)"},
            exit_code=None,
            status="pass",
            summary=f"no local tests selected; full coverage deferred to CI: {deferred_reason}",
        )
    if spec.local_scope == "pytest_select":
        # Single chokepoint: a target-less test invocation outside CI is refused.
        assert_bounded_python_test_argv(effective_command[1:])

    argv, env = _resolve_execution(repo_root, spec, effective_command)
    env = _with_check_env(name, env)

    if argv is None:
        return CheckEvent(
            **common,
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
            **common,
            exit_code=None,
            status="unknown",
            summary=f"execution error: {type(exc).__name__}",
        )

    raw_ref = _write_raw_log(repo_root, name, completed)
    if completed.returncode == 0:
        return CheckEvent(
            **common,
            exit_code=completed.returncode,
            status="pass",
            summary="clean" if deferred_reason is None else f"clean; coverage deferred to CI for: {deferred_reason}",
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
        **common,
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
    """Return True when a prior check event remains valid.

    Evidence stays valid only when the covered surface's input fingerprint is
    unchanged. A later edit to that surface invalidates only this event.

    ``require_repo_scope`` rejects diff-scoped evidence. A diff-scoped run proves
    the changed files, not the whole surface, so it cannot stand in for a
    CI-mirror obligation (spec gate-local-incremental-checks).
    """
    # Maintainer context:
    # Return True when a prior check event remains valid (§7.2 incremental).
    # Development references: FR-008.

    if event.status != "pass":
        return False
    if require_repo_scope and event.scope != "repo":
        return False
    if event.input_fingerprint is None or input_fingerprint is None:
        return False
    return event.input_fingerprint == input_fingerprint


# Findings rendered per failing sub-report before the rest are counted off. A
# repair hint has to stay readable, but the count of what it left out is always
# printed -- silently dropping findings is the defect this renderer exists to
# fix (#2143).
_REPORT_FINDINGS_SHOWN = 10
_REPORT_MESSAGE_CHARS = 200


def _report_fails(report: Mapping[str, Any]) -> bool:
    """Return True when a report node is itself a failure (not just a parent)."""

    if str(report.get("status", "")).lower() == "fail":
        return True
    findings = report.get("findings") or []
    return any(str(f.get("severity", "")).lower() == "error" for f in findings if isinstance(f, Mapping))


def _failing_leaves(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the deepest failing nodes, so a parent never masks its children."""

    children = [c for c in (report.get("child_reports") or []) if isinstance(c, Mapping)]
    leaves: list[Mapping[str, Any]] = []
    for child in children:
        leaves.extend(_failing_leaves(child))
    if leaves:
        return leaves
    return [report] if _report_fails(report) else []


# Blocking findings come first: only ``error`` fails the check, and a report
# that leads with advisory findings can push every blocking one past the display
# cap -- reintroducing, inside the summary, the same hiding this renderer exists
# to end (#2143).
_SEVERITY_ORDER: dict[str, int] = {"error": 0, "warning": 1, "info": 2}


def _severity_rank(finding: Mapping[str, Any]) -> int:
    return _SEVERITY_ORDER.get(str(finding.get("severity", "")).lower(), len(_SEVERITY_ORDER))


def _finding_line(finding: Mapping[str, Any]) -> str:
    """Render one finding as ``[severity] file: message`` on a single line."""

    severity = str(finding.get("severity", "") or "?").lower()
    where = str(finding.get("file") or finding.get("path") or "").strip()
    message = " ".join(str(finding.get("message", "") or "").split())
    if len(message) > _REPORT_MESSAGE_CHARS:
        message = message[: _REPORT_MESSAGE_CHARS - 3] + "..."
    return f"[{severity}] {where}: {message}" if where else f"[{severity}] {message}"


def report_json_summary(repo_root: Path, name: str) -> list[str]:
    """Render a failed check's JSON report into lines for its repair hint.

    A check whose :attr:`CheckSpec.report_json` is set writes its findings to a
    file instead of printing them, so its transcript is empty and a tail of the
    raw log tells the reader nothing: the failure reads as "failed, no reason
    given" while the reasons sit unread in the report file. This reads
    that file and returns the failing sub-reports with their findings.

    Returns ``[]`` when the check writes no report, the file is missing, or it
    cannot be parsed -- the caller then falls back to the raw transcript.
    Parsed with ``json`` rather than the pydantic ``AuditReport`` model on
    purpose: the file is written by a separate process, and a schema mismatch
    must degrade to "no summary" rather than raise inside failure reporting.
    """
    # Development references: #2143.

    spec = CHECK_CATALOG.get(name)
    if spec is None or not spec.report_json:
        return []
    try:
        raw = (repo_root / spec.report_json).read_text(encoding="utf-8", errors="replace")
        document = json.loads(raw)
    except (OSError, ValueError):
        return []
    if not isinstance(document, Mapping):
        return []

    failing = _failing_leaves(document)
    if not failing:
        return []

    lines = [f"report: {spec.report_json}"]
    for report in failing:
        findings = sorted(
            (f for f in (report.get("findings") or []) if isinstance(f, Mapping)),
            key=_severity_rank,
        )
        tool = str(report.get("tool", "") or "?")
        status = str(report.get("status", "") or "?")
        lines.append(f"{tool}: {status} ({len(findings)} findings)")
        for finding in findings[:_REPORT_FINDINGS_SHOWN]:
            lines.append(f"  {_finding_line(finding)}")
        hidden = len(findings) - _REPORT_FINDINGS_SHOWN
        if hidden > 0:
            lines.append(f"  ... {hidden} more findings in {tool} (see {spec.report_json})")
    return lines
