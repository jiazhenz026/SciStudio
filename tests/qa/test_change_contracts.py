"""Tests for the baseline-aware change-contract audit (#1619/#1621)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from scistudio.qa.audit import full_audit
from scistudio.qa.audit.change_contracts import check_report
from scistudio.qa.governance.gate_record.checks import select_checks
from scistudio.qa.schemas.facts import FactsRegistry
from scistudio.qa.schemas.report import AuditReport, AuditStatus


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def _write_empty_baseline(root: Path) -> Path:
    path = root / "docs" / "audit" / "baselines" / "change-contract-baseline.json"
    _write(
        path,
        """
        {
          "findings": [],
          "generated_from": "fixture",
          "version": "1"
        }
        """,
    )
    return path


def _write_spec(
    root: Path,
    *,
    change_contract: str = "",
    governs_modules: list[str] | None = None,
    governs_files: list[str] | None = None,
    tests: list[str] | None = None,
) -> Path:
    modules = governs_modules if governs_modules is not None else ["app"]
    files = governs_files if governs_files is not None else ["src/app/**"]
    test_paths = tests if tests is not None else ["tests/test_feature.py"]
    module_lines = "\n".join(f"    - {item}" for item in modules) or "    []"
    file_lines = "\n".join(f"    - {item}" for item in files) or "    []"
    test_lines = "\n".join(f"  - {item}" for item in test_paths) or "  []"
    extra = textwrap.dedent(change_contract).strip()
    path = root / "docs" / "specs" / "feature.md"
    _write(
        path,
        "\n".join(
            line
            for line in [
                "---",
                "spec_id: fixture-feature",
                'title: "Fixture Feature"',
                "status: Draft",
                "feature_branch: fixture-feature",
                "created: 2026-06-12",
                'input: "Fixture spec"',
                "owners:",
                '  - "@jiazhenz026"',
                "related_adrs: []",
                "related_specs: []",
                "scope:",
                "  in: []",
                "  out: []",
                "governs:",
                "  modules:",
                module_lines,
                "  contracts: []",
                "  entry_points: []",
                "  files:",
                file_lines,
                "  excludes: []",
                "planned_governs:",
                "  modules: []",
                "  contracts: []",
                "  entry_points: []",
                "  files: []",
                "  excludes: []",
                "tests:",
                test_lines,
                extra,
                "acceptance_source: manual",
                "language_source: en",
                "---",
                "",
                "# Fixture Feature",
                "",
                "## 1. Change Summary",
                "",
                "Fixture.",
            ]
            if line
        ),
    )
    return path


def _write_contract(root: Path, body: str) -> Path:
    path = root / "docs" / "change-contracts" / "fixture.yml"
    _write(path, body)
    return path


def _rule_ids(report: AuditReport) -> set[str]:
    return {finding.rule_id for finding in report.findings}


def test_missing_contract_blocks_changed_implementation_spec(tmp_path: Path) -> None:
    _write_spec(tmp_path)

    report = check_report(
        tmp_path,
        baseline_path=None,
        changed_paths=["docs/specs/feature.md"],
    )

    assert report.status == AuditStatus.FAIL
    assert "change-contract.missing-contract" in _rule_ids(report)


def test_docs_only_not_applicable_declaration_passes(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        governs_modules=[],
        governs_files=[],
        tests=[],
        change_contract="""
        change_contract:
          kind: not_applicable
          rationale: "Documentation-only fixture with no implementation surface."
        """,
    )

    report = check_report(
        tmp_path,
        baseline_path=None,
        changed_paths=["docs/specs/feature.md"],
    )

    assert report.status == AuditStatus.PASS
    assert report.findings == []


def test_surface_outside_parent_governance_blocks(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        change_contract="""
        change_contract:
          path: docs/change-contracts/fixture.yml
        """,
        governs_modules=["app.allowed"],
    )
    _write_contract(
        tmp_path,
        """
        id: fixture-feature
        parent: docs/specs/feature.md
        change_kind: additive
        surfaces:
          added:
            - kind: module
              target: app.outside
              scope: production
        """,
    )

    report = check_report(
        tmp_path,
        baseline_path=None,
        changed_paths=["docs/specs/feature.md"],
    )

    assert "change-contract.surface-outside-governance" in _rule_ids(report)


def test_forbidden_prod_reference_blocks_only_production_scopes(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        change_contract="""
        change_contract:
          path: docs/change-contracts/fixture.yml
        """,
    )
    _write_contract(
        tmp_path,
        """
        id: fixture-feature
        parent: docs/specs/feature.md
        change_kind: removal
        surfaces:
          removed:
            - kind: module
              target: app.legacy
              scope: production
        forbidden_prod_references:
          - kind: import
            target: app.legacy
            allowed_scopes:
              - test
              - docs
            reason: "Legacy imports must leave production code."
        """,
    )
    _write(tmp_path / "tests" / "test_legacy.py", "import app.legacy")
    allowed = check_report(tmp_path, baseline_path=None, changed_paths=["docs/specs/feature.md"])
    assert "change-contract.forbidden-prod-reference" not in _rule_ids(allowed)

    _write(tmp_path / "src" / "app" / "main.py", "import app.legacy")
    blocked = check_report(tmp_path, baseline_path=None, changed_paths=["docs/specs/feature.md"])

    assert "change-contract.forbidden-prod-reference" in _rule_ids(blocked)
    assert blocked.status == AuditStatus.FAIL


def test_baseline_grandfathers_unchanged_findings_but_blocks_new_ones(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        change_contract="""
        change_contract:
          path: docs/change-contracts/fixture.yml
        """,
    )
    _write_contract(
        tmp_path,
        """
        id: fixture-feature
        parent: docs/specs/feature.md
        change_kind: removal
        surfaces:
          removed:
            - kind: module
              target: app.legacy
              scope: production
        forbidden_prod_references:
          - kind: import
            target: app.legacy
            reason: "Legacy imports must leave production code."
        """,
    )
    _write(tmp_path / "src" / "app" / "main.py", "import app.legacy")

    raw = check_report(tmp_path, baseline_path=None, changed_paths=["docs/specs/feature.md"])
    finding = next(f for f in raw.findings if f.rule_id == "change-contract.forbidden-prod-reference")
    baseline_path = tmp_path / "docs" / "audit" / "baselines" / "change-contract-baseline.json"
    _write(
        baseline_path,
        json.dumps(
            {
                "version": "1",
                "generated_from": "fixture",
                "findings": [
                    {
                        "id": finding.id,
                        "rule_id": finding.rule_id,
                        "fingerprint": finding.evidence["fingerprint"],
                        "source": finding.file,
                    }
                ],
            },
            indent=2,
        ),
    )

    grandfathered = check_report(
        tmp_path,
        baseline_path=baseline_path,
        changed_paths=["docs/specs/feature.md"],
    )
    assert grandfathered.status == AuditStatus.PASS
    assert grandfathered.findings[0].severity.value == "info"

    _write(tmp_path / "src" / "app" / "other.py", "import app.legacy")
    blocked = check_report(
        tmp_path,
        baseline_path=baseline_path,
        changed_paths=["docs/specs/feature.md"],
    )
    assert blocked.status == AuditStatus.FAIL
    assert any(f.severity.value == "error" for f in blocked.findings)


def test_required_reachability_blocks_test_only_module(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        change_contract="""
        change_contract:
          path: docs/change-contracts/fixture.yml
        """,
    )
    _write_contract(
        tmp_path,
        """
        id: fixture-feature
        parent: docs/specs/feature.md
        change_kind: additive
        surfaces:
          added:
            - kind: module
              target: app.orphan
              scope: production
        required_reachability:
          - surface:
              kind: module
              target: app.orphan
              scope: production
            production_roots:
              - app.main
        """,
    )
    _write(tmp_path / "src" / "app" / "__init__.py", "")
    _write(tmp_path / "src" / "app" / "main.py", "VALUE = 1")
    _write(tmp_path / "src" / "app" / "orphan.py", "VALUE = 2")
    _write(tmp_path / "tests" / "test_orphan.py", "from app import orphan")

    report = check_report(tmp_path, baseline_path=None, changed_paths=["docs/specs/feature.md"])

    assert "change-contract.reachability.python-module-unreachable" in _rule_ids(report)


def test_full_audit_includes_change_contract_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_empty_baseline(tmp_path)
    monkeypatch.setattr(
        full_audit,
        "generate_facts",
        lambda _repo_root: FactsRegistry(source_sha="fixture-sha"),
    )

    report = full_audit.run(
        tmp_path,
        check_stale=False,
        include_frontmatter_lint=False,
        include_doc_drift=False,
        include_developer_docs=False,
        include_fact_drift=False,
        include_closure=False,
        include_signature_drift=False,
        include_architecture_drift=False,
        include_vulture=False,
    )

    assert "change_contracts" in report.summary["implemented_children"]
    assert report.status == AuditStatus.PASS


def test_gate_record_selects_change_contract_check_for_spec_changes() -> None:
    selection = select_checks(tier=3, changed_files=["docs/specs/feature.md"])

    assert "change_contracts" in selection.required
