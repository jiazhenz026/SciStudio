"""Tests for ``scieasy.qa.governance.workflow_sync_check`` (TC-1E.6 §3.5 audit-fix C2)."""

from __future__ import annotations

import io
from contextlib import redirect_stderr
from pathlib import Path

from scieasy.qa.governance.workflow_sync_check import main, verify

_WF_DIR = ".github/workflows"
_WF_NAME = "governance-modification.yml"


def _write_workflow(repo: Path, body: str) -> Path:
    workflows = repo / _WF_DIR
    workflows.mkdir(parents=True, exist_ok=True)
    p = workflows / _WF_NAME
    p.write_text(body, encoding="utf-8")
    return p


def test_clean_workflow_yields_no_findings(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "name: gov\non:\n  pull_request: {}\njobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    assert verify(tmp_path) == []


def test_static_paths_list_rejected(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "name: gov\non:\n  pull_request:\n    paths:\n      - 'docs/adr/**'\njobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    findings = verify(tmp_path)
    assert len(findings) == 1
    assert findings[0].rule_id == "governance/workflow-static-path-filter"
    assert "paths:" in findings[0].message


def test_static_paths_ignore_list_rejected(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "name: gov\non:\n  pull_request:\n    paths-ignore:\n      - 'README.md'\n"
        "jobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    findings = verify(tmp_path)
    assert any(f.rule_id == "governance/workflow-static-path-filter" for f in findings)


def test_both_paths_and_paths_ignore_rejected(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "name: gov\non:\n  pull_request:\n    paths:\n      - 'a/**'\n    paths-ignore:\n      - 'b/**'\n"
        "jobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    findings = verify(tmp_path)
    assert len(findings) == 2


def test_missing_workflow_yields_error(tmp_path: Path) -> None:
    findings = verify(tmp_path)
    assert len(findings) == 1
    assert findings[0].rule_id == "governance/workflow-missing"


def test_invalid_yaml_yields_error(tmp_path: Path) -> None:
    _write_workflow(tmp_path, ": [unclosed\n")
    findings = verify(tmp_path)
    assert len(findings) == 1
    assert findings[0].rule_id == "governance/workflow-invalid-yaml"


def test_workflow_with_list_form_on_block_ignored(tmp_path: Path) -> None:
    """When ``on:`` is the list form (no ``pull_request`` dict), no finding."""
    _write_workflow(
        tmp_path,
        "name: gov\non: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    assert verify(tmp_path) == []


def test_workflow_with_pull_request_as_non_dict(tmp_path: Path) -> None:
    """``on.pull_request: null`` (i.e. empty `{}`) is fine — no filter."""
    _write_workflow(
        tmp_path,
        "name: gov\non:\n  pull_request:\njobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    assert verify(tmp_path) == []


def test_pyyaml_on_key_boolean_coercion(tmp_path: Path) -> None:
    """PyYAML coerces bare ``on:`` to boolean ``True``; the impl must handle that."""
    _write_workflow(
        tmp_path,
        "name: gov\non:\n  pull_request:\n    paths:\n      - 'x'\njobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    # PyYAML's default loader keeps "on" as string with YAML 1.2; with 1.1 it
    # becomes True. Either way the impl branch is exercised.
    findings = verify(tmp_path)
    assert any(f.rule_id == "governance/workflow-static-path-filter" for f in findings)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_main_returns_zero_on_clean(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "name: gov\non:\n  pull_request: {}\njobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 0


def test_main_returns_one_on_violation(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "name: gov\non:\n  pull_request:\n    paths:\n      - 'x'\njobs:\n  x:\n    runs-on: ubuntu-latest\n",
    )
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(["--repo-root", str(tmp_path)])
    assert rc == 1
    assert "workflow-static-path-filter" in buf.getvalue()


def test_main_returns_one_on_missing_workflow(tmp_path: Path) -> None:
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(["--repo-root", str(tmp_path)])
    assert rc == 1
