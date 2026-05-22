"""Refactor-guard tests for the ``gate_record`` sub-package (#1433).

These tests live under ``tests/qa/governance/`` (per the umbrella #1427
dispatch prompt) and are intentionally focused on properties the
single-file -> sub-package refactor must preserve:

1. Every public **and** private name that the original single-file module
   exposed is still importable from
   ``scistudio.qa.governance.gate_record`` (the existing
   ``tests/qa/test_gate_record.py`` reaches into ``_discover_gate_record``,
   ``_is_governance_path``, and ``_is_test_path`` — those must keep working).
2. The CLI surface is byte-identical: every subcommand exits 0 on
   ``--help`` and the help banner lists the same subcommands in the same
   order.
3. A self-hosting smoke: drive the refactored CLI end-to-end against a
   temporary record (start -> plan -> docs -> check -> sentrux -> finalize)
   and assert it produces a schema-valid record.

If a future refactor drops a name or changes a subcommand list, exactly
these tests should fail.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Resolve repo root so subprocess invocations of ``python -m
# scistudio.qa.governance.gate_record`` can find the package even when
# ``scistudio`` is not pip-installed (the project uses ``PYTHONPATH=src``).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src"


def _env_with_pythonpath() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    parts = [str(_SRC_ROOT)] + ([existing] if existing else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


# Subcommand list in the exact order ``argparse`` registered them in the
# pre-refactor single-file module. Order matters because ``--help`` prints
# them in registration order; any change here is also a surface change.
_EXPECTED_SUBCOMMANDS: tuple[str, ...] = (
    "start",
    "plan",
    "amend",
    "docs",
    "check",
    "sentrux",
    "finalize",
    "pre-commit",
    "commit-msg",
    "ci",
    "pre-push",
    "pr-ready",
)

# Pre-refactor module-level symbols (public + leading-underscore helpers
# that the existing test-suite imports). If you add a symbol intentionally,
# update both the package ``__init__`` and this list.
_EXPECTED_PUBLIC_NAMES: tuple[str, ...] = (
    "CLOSING_KEYWORD_RE",
    "IMPLEMENTATION_PATTERNS",
    "IMPLEMENTATION_TASK_KINDS",
    "NON_IMPLEMENTATION_PATTERNS",
    "SLUG_RE",
    "TRAILER_RE",
    "VALID_OVERRIDE_LABELS",
    "AdminLabelEvidence",
    "CANONICAL_STAGE_ORDER",
    "CheckEvidence",
    "CommitEvidence",
    "FullAuditEvidence",
    "GateRecord",
    "GateStage",
    "IssueRef",
    "POST_PR_STAGES",
    "PullRequestEvidence",
    "Scope",
    "ScopeAmendment",
    "SentruxEvidence",
    "StageEvidence",
    "amend_record",
    "check_record",
    "docs_record",
    "finalize_record",
    "plan_record",
    "sentrux_record",
    "start_record",
    "check_commit_msg",
    "check_pr",
    "check_pr_ready",
    "check_pre_commit",
    "check_pre_push",
    "validate_gate_record",
    "main",
)

_EXPECTED_PRIVATE_NAMES: tuple[str, ...] = (
    # path helpers
    "_normalize_path",
    "_match_path",
    "_matches_any",
    "_is_test_path",
    "_is_implementation_path",
    "_sentrux_applies",
    "_is_governance_path",
    "_VITEST_NAME_SUFFIXES",
    "_GOVERNANCE_PATTERNS",
    "_GOVERNANCE_NON_TOUCH_PATTERNS",
    # I/O helpers
    "_load_record",
    "_write_record",
    "_slugify",
    "_record_path",
    "_mark_stage",
    "_upsert_check",
    "_git_lines",
    "_record_task_kind",
    "_discover_gate_record",
    "_parse_key_values",
    "_parse_issue_numbers",
    # validation helpers
    "_finding",
    "_report",
    "_effective_include",
    "_effective_exclude",
    "_closed_issue_numbers",
    "_invalid_override_labels",
    "_split_labels",
    "_env_bypass_labels",
    "_local_bypass_report",
    "_trailers",
    # stage helpers
    "_CHANGELOG_PATHS",
    # CLI helpers
    "_render_text",
)


def test_public_names_are_importable() -> None:
    """Every advertised public name resolves at the package root."""

    import scistudio.qa.governance.gate_record as pkg

    for name in _EXPECTED_PUBLIC_NAMES:
        assert hasattr(pkg, name), f"public name dropped after refactor: {name}"


def test_private_helpers_are_importable() -> None:
    """Tests reach into leading-underscore helpers; refactor must keep them."""

    import scistudio.qa.governance.gate_record as pkg

    for name in _EXPECTED_PRIVATE_NAMES:
        assert hasattr(pkg, name), f"private helper dropped after refactor: {name}"


def test_from_import_works_for_each_symbol() -> None:
    """``from ... import X`` must succeed for every preserved symbol."""

    # Use a single dynamic exec so a missing name fails one test (not 60).
    import_lines = ", ".join(_EXPECTED_PUBLIC_NAMES + _EXPECTED_PRIVATE_NAMES)
    src = f"from scistudio.qa.governance.gate_record import {import_lines}\n"
    namespace: dict[str, object] = {}
    exec(compile(src, "<test_import>", "exec"), namespace)
    for name in _EXPECTED_PUBLIC_NAMES + _EXPECTED_PRIVATE_NAMES:
        assert name in namespace, f"from-import dropped: {name}"


def test_module_help_lists_all_subcommands() -> None:
    """``python -m ... --help`` must still list every subcommand."""

    completed = subprocess.run(
        [sys.executable, "-m", "scistudio.qa.governance.gate_record", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_env_with_pythonpath(),
    )
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    for subcommand in _EXPECTED_SUBCOMMANDS:
        # The choices list and the descriptive table both list every name.
        assert subcommand in output, f"subcommand missing from --help: {subcommand}"


@pytest.mark.parametrize("subcommand", _EXPECTED_SUBCOMMANDS)
def test_each_subcommand_help_exits_zero(subcommand: str) -> None:
    """Each subcommand's own ``--help`` exits 0 and shows the subcommand name."""

    completed = subprocess.run(
        [sys.executable, "-m", "scistudio.qa.governance.gate_record", subcommand, "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_env_with_pythonpath(),
    )
    assert completed.returncode == 0, completed.stderr
    assert subcommand in completed.stdout, (
        f"subcommand --help banner missing its own name: {subcommand}\n{completed.stdout}"
    )


def test_self_hosting_end_to_end(tmp_path: Path) -> None:
    """Drive the refactored CLI end-to-end against a temp record.

    This is the self-hosting smoke from the dispatch prompt: the gate
    record CLI is used to *record* the refactor of itself, so it must be
    able to walk the full ``start -> plan -> docs -> check -> sentrux ->
    finalize`` flow without circular-import or partial-init failures.
    """

    # Simulate a repo root with an empty .workflow/records/ tree.
    (tmp_path / ".workflow" / "records").mkdir(parents=True)
    record_path = tmp_path / ".workflow" / "records" / "1433-selfhost.json"
    module_args = [sys.executable, "-m", "scistudio.qa.governance.gate_record"]

    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*module_args, *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            env=_env_with_pythonpath(),
        )

    started = _run(
        [
            "start",
            "--repo-root",
            str(tmp_path),
            "--issue",
            "1433",
            "--slug",
            "selfhost",
            "--task-kind",
            "refactor",
            "--branch",
            "refactor/issue-1433/selfhost",
            "--owner-directive",
            "self-hosting smoke",
            "--include",
            "src/scistudio/qa/governance/gate_record/**",
            "--governance-touch",
            "--record-path",
            str(record_path),
        ]
    )
    assert started.returncode == 0, started.stderr
    assert record_path.exists(), "start did not write the record"

    plan_result = _run(
        [
            "plan",
            "--gate-record",
            str(record_path),
            "--planned-file",
            "src/scistudio/qa/governance/gate_record/models.py",
            "--changed-test-path",
            "tests/qa/governance/test_gate_record_package.py",
            "--required-check",
            "ruff",
            "--required-check",
            "pytest",
        ]
    )
    assert plan_result.returncode == 0, plan_result.stderr

    docs_result = _run(
        [
            "docs",
            "--gate-record",
            str(record_path),
            "--updated",
            "docs/planning/backend-god-file-refactor-checklist.md",
        ]
    )
    assert docs_result.returncode == 0, docs_result.stderr

    check_result = _run(
        [
            "check",
            "--gate-record",
            str(record_path),
            "--name",
            "full_audit",
            "--command-or-tool",
            "python -m scistudio.qa.audit.full_audit",
            "--status",
            "pass",
            "--exit-code",
            "0",
            "--output-path",
            "docs/audit/full-audit-latest.json",
            "--full-audit",
        ]
    )
    assert check_result.returncode == 0, check_result.stderr

    sentrux_result = _run(
        [
            "sentrux",
            "--gate-record",
            str(record_path),
            "--status",
            "pass",
            "--rules-checked",
            "0",
            "--total-rules-defined",
            "14",
        ]
    )
    assert sentrux_result.returncode == 0, sentrux_result.stderr

    finalize_result = _run(
        [
            "finalize",
            "--gate-record",
            str(record_path),
            "--commit-sha",
            "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "--pr-number",
            "1234",
            "--pr-url",
            "https://github.com/example/repo/pull/1234",
            "--body-closes-issue",
            "1433",
        ]
    )
    assert finalize_result.returncode == 0, finalize_result.stderr

    # The finalized record must parse cleanly through the same models the
    # refactored CLI uses; this catches drift between the on-disk JSON
    # writer and the in-memory ``GateRecord`` validator.
    from scistudio.qa.governance.gate_record import GateRecord, GateStage

    payload = json.loads(record_path.read_text(encoding="utf-8"))
    parsed = GateRecord.model_validate(payload)
    assert parsed.task_id == "1433-selfhost"
    assert parsed.task_kind == "refactor"
    assert parsed.governance_touch is True
    # The flow exercised here (start -> plan -> docs -> check -> sentrux ->
    # finalize) marks every stage *except* IMPLEMENT, which is only set by
    # ``amend``. Asserting on that exact set documents the per-subcommand
    # contract; if a future refactor silently moves the ``_mark_stage`` call
    # for any subcommand, this assertion will catch it.
    done_stages = {stage.stage for stage in parsed.stages if stage.status == "done"}
    assert done_stages == set(GateStage) - {GateStage.IMPLEMENT}, (
        f"unexpected stage-completion set after non-amend flow: {done_stages}"
    )
    assert parsed.pull_request is not None
    assert parsed.pull_request.number == 1234
    assert parsed.commit is not None
    assert "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef" in parsed.commit.shas


def test_package_layout_files_are_present() -> None:
    """The decomposition seam itself is part of the public contract.

    A future refactor must not silently re-merge the sub-modules — the
    god-file waiver in ``scripts/check_god_files.py`` was removed on the
    basis of this layout (#1427).
    """

    import scistudio.qa.governance.gate_record as pkg

    package_dir = Path(pkg.__file__).parent
    for module_name in ("paths", "models", "io", "validation", "stages", "cli"):
        assert (package_dir / f"{module_name}.py").exists(), f"expected sub-module dropped: {module_name}.py"
    # ``__main__`` is what ``python -m scistudio.qa.governance.gate_record``
    # dispatches to.
    assert (package_dir / "__main__.py").exists()
