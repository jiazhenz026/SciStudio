"""Package-shape + self-hosting guard for the ADR-042 Addendum 6 gate ledger.

Rewritten from the pre-Addendum-6 single-file -> sub-package refactor guard
(#1433). Addendum 6 replaces that layout delete-and-replace: the flat-document
``GateRecord`` model, the ``validate_gate_record`` / ``check_*`` validators, the
``paths``/``models``/``validation``/``stages`` sub-modules, and the
``docs``/``sentrux`` subcommands are gone. This module pins the NEW contract:

1. The new public surface (``GateLedger``, ``reconcile``, ``GUARD_REGISTRY``,
   event models, label vocabulary) resolves at the package root.
2. The new module layout (ledger / evaluator / surfaces / checks / parity /
   guards / workflow / cli / instructions / labels / io) is present and the
   legacy sub-modules are gone.
3. The five workflow commands plus the compatibility aliases all exit 0 on
   ``--help`` (the ``python -m`` entry point is preserved).
4. A self-hosting smoke drives ``init -> plan -> check -> finalize`` end to end
   against a temp ledger and re-validates the resulting schema-v2 ledger.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src"


def _env_with_pythonpath() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    parts = [str(_SRC_ROOT)] + ([existing] if existing else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    # §7.10: this self-hosting smoke runs the CLI as a real subprocess (the
    # autouse conftest stub does not reach it). Disable real venv provisioning so
    # the smoke never creates a venv or attempts a network install.
    env["SCISTUDIO_GATE_NO_PROVISION"] = "1"
    return env


# The five workflow commands (§7.5) plus the compatibility aliases (§5.8).
_EXPECTED_COMMANDS: tuple[str, ...] = (
    "init",
    "plan",
    "amend",
    "check",
    "finalize",
    "start",
    "pre-commit",
    "commit-msg",
    "pre-push",
    "pr-ready",
    "ci",
)

# The new public surface re-exported from the package root (§5.8 / __init__).
_EXPECTED_PUBLIC_NAMES: tuple[str, ...] = (
    "GateLedger",
    "GuardInputs",
    "Guard",
    "GUARD_REGISTRY",
    "EvaluatorMode",
    "ReconcileResult",
    "reconcile",
    "classify_surfaces",
    "derive_tier",
    "IssueRef",
    "DeclaredScope",
    "DirectiveEvent",
    "ScopeEvent",
    "ObservedDiff",
    "CheckEvent",
    "DocsEvent",
    "TestEvent",
    "GuardEvent",
    "ReconcileEvent",
    "RequiredObligations",
    "CommitEvidence",
    "PullRequestEvidence",
    "AdminLabel",
    "BYPASS_LABEL",
    "CORE_CHANGE_LABEL",
    "MERGE_LABEL",
    "HUMAN_AUTHORED_LABEL",
    "ADMIN_LABELS",
    "VALID_LABELS",
    "SUPPORTED_TASK_KINDS",
    "SUPPORTED_PERSONAS",
    "LEDGER_SCHEMA_VERSION",
    "main",
)

# Legacy names that the delete-and-replace explicitly dropped (ADR §3).
_DROPPED_NAMES: tuple[str, ...] = (
    "GateRecord",
    "GateStage",
    "CANONICAL_STAGE_ORDER",
    "validate_gate_record",
    "check_pr",
    "check_pre_commit",
    "check_pre_push",
    "check_pr_ready",
    "check_commit_msg",
    "start_record",
    "docs_record",
    "sentrux_record",
    "_discover_gate_record",
    "_is_governance_path",
    "_sentrux_applies",
)


def test_new_public_names_are_importable() -> None:
    import scistudio.qa.governance.gate_record as pkg

    for name in _EXPECTED_PUBLIC_NAMES:
        assert hasattr(pkg, name), f"new public name missing: {name}"


def test_legacy_names_are_dropped() -> None:
    import scistudio.qa.governance.gate_record as pkg

    for name in _DROPPED_NAMES:
        assert not hasattr(pkg, name), f"legacy name survived the delete-and-replace: {name}"


def test_from_import_works_for_each_new_symbol() -> None:
    import_lines = ", ".join(_EXPECTED_PUBLIC_NAMES)
    src = f"from scistudio.qa.governance.gate_record import {import_lines}\n"
    namespace: dict[str, object] = {}
    exec(compile(src, "<test_import>", "exec"), namespace)
    for name in _EXPECTED_PUBLIC_NAMES:
        assert name in namespace, f"from-import dropped: {name}"


def test_new_module_layout_present_and_legacy_gone() -> None:
    import scistudio.qa.governance.gate_record as pkg

    package_dir = Path(pkg.__file__).parent
    for module_name in (
        "ledger",
        "evaluator",
        "surfaces",
        "checks",
        "parity",
        "workflow",
        "cli",
        "instructions",
        "labels",
        "io",
    ):
        assert (package_dir / f"{module_name}.py").exists(), f"expected new sub-module missing: {module_name}.py"
    assert (package_dir / "guards").is_dir(), "guards/ package missing"
    assert (package_dir / "__main__.py").exists()
    # Legacy single-file-refactor sub-modules are gone (ADR §3 delete-and-replace).
    for legacy in ("models", "validation", "stages", "paths"):
        assert not (package_dir / f"{legacy}.py").exists(), f"legacy sub-module survived: {legacy}.py"


def test_module_help_lists_all_commands() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "scistudio.qa.governance.gate_record", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_env_with_pythonpath(),
    )
    assert completed.returncode == 0, completed.stderr
    for command in _EXPECTED_COMMANDS:
        assert command in completed.stdout, f"command missing from --help: {command}"


@pytest.mark.parametrize("command", _EXPECTED_COMMANDS)
def test_each_command_help_exits_zero(command: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "scistudio.qa.governance.gate_record", command, "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_env_with_pythonpath(),
    )
    assert completed.returncode == 0, completed.stderr
    assert command in completed.stdout


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_self_hosting_init_plan_check_finalize(tmp_path: Path) -> None:
    """Drive the new CLI end to end and re-validate the schema-v2 ledger.

    A self-hosting smoke for the workflow flow (``init -> plan -> check -> pre-PR
    finalize``) without circular-import or partial-init failures. Uses a real git
    repo so the evaluator can observe a diff; ``check --skip-execution`` keeps the
    smoke independent of host check tooling.
    """

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "refactor/issue-1509/selfhost")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")

    module_args = [sys.executable, "-m", "scistudio.qa.governance.gate_record", "--repo-root", str(repo)]

    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*module_args, *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            env=_env_with_pythonpath(),
        )

    started = _run(
        [
            "init",
            "--issue",
            "1509",
            "--slug",
            "selfhost",
            "--task-kind",
            "refactor",
            "--persona",
            "implementer",
            "--runtime",
            "claude-code",
            "--branch",
            "refactor/issue-1509/selfhost",
            "--owner-directive",
            "self-hosting smoke",
            "--include",
            "src/scistudio/**",
            "--include",
            "tests/**",
            "--print-instructions",
            "false",
        ]
    )
    assert started.returncode == 0, started.stderr
    record_path = repo / ".workflow" / "records" / "1509-selfhost.json"
    assert record_path.exists(), f"init did not write the ledger: {started.stdout}"

    plan = _run(
        [
            "plan",
            "--test-path",
            "tests/qa/test_x.py",
            "--docs-na",
            "implementation:self-hosting smoke, no public contract change",
        ]
    )
    assert plan.returncode == 0, plan.stderr

    # Make an in-scope implementation + test change so the diff is observable.
    (repo / "src" / "scistudio").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "scistudio" / "x.py").write_text("y = 1\n", encoding="utf-8")
    (repo / "tests" / "qa").mkdir(parents=True, exist_ok=True)
    (repo / "tests" / "qa" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "impl+test")

    check = _run(["check", "--mode", "local", "--base", "HEAD~1", "--head", "HEAD", "--skip-execution"])
    # check completes; exit code may be 0 or 1 (env guards) — assert it ran.
    assert check.returncode in (0, 1), check.stderr
    assert "mode=local" in check.stdout

    body = repo / "body.md"
    body.write_text("Closes #1509\n", encoding="utf-8")
    finalize = _run(
        [
            "finalize",
            "--base",
            "HEAD~1",
            "--head",
            "HEAD",
            "--commit",
            "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "--pr-body-file",
            str(body),
            "--closes",
            "1509",
        ]
    )
    assert finalize.returncode in (0, 1, 4), finalize.stderr

    # Re-validate the resulting ledger through the schema-v2 model.
    from scistudio.qa.governance.gate_record import GateLedger

    payload = json.loads(record_path.read_text(encoding="utf-8"))
    parsed = GateLedger.model_validate(payload)
    assert parsed.schema_version == 2
    assert parsed.record_id == "1509-selfhost"
    assert parsed.task_kind == "refactor"
    assert any(ref.number == 1509 for ref in parsed.issues)
    assert parsed.commit is not None
    assert "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef" in parsed.commit.shas
    assert parsed.pull_request is not None
    assert 1509 in parsed.pull_request.closes
    # Events accumulated across commands (append-only); reconcile ran.
    assert parsed.reconcile_events
