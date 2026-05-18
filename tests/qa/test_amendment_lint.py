"""Tests for ``scripts/audit/amendment_lint.py`` (ADR-042 §27.5)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "audit" / "amendment_lint.py"


def _load_module():
    """Load the flat script as a module for testing."""
    spec = importlib.util.spec_from_file_location("amendment_lint", _SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def amendment_lint():
    return _load_module()


def _write_adr(
    path: Path,
    *,
    adr: int,
    body: str,
    amends: str = "[]",
    title: str = "Test ADR",
) -> None:
    contents = (
        f"---\n"
        f"adr: {adr}\n"
        f'title: "{title}"\n'
        f"status: Accepted\n"
        f"date_created: 2026-05-17\n"
        f"date_accepted: 2026-05-18\n"
        f"is_code_implementation: false\n"
        f"governs:\n"
        f"  modules: []\n"
        f"  files: []\n"
        f"tests: []\n"
        f'agent_editable: "false"\n'
        f'owner: "@you"\n'
        f"amends: {amends}\n"
        f"---\n\n"
        f"{body}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def test_lint_clean_base_no_findings(tmp_path: Path, amendment_lint) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 1. Intro\n",
    )
    findings = amendment_lint.lint(tmp_path)
    assert findings == []


def test_lint_section_match_resolves(tmp_path: Path, amendment_lint) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 17. Required Skills\n\nDetails.\n",
    )
    amends_yaml = (
        '\n  - target: "ADR-042 §17 Required Skills"\n    kind: extend\n    summary: "Adds 4 new required skills"\n'
    )
    _write_adr(
        tmp_path / "docs/adr/ADR-042-A.md",
        adr=4201,
        title="Addendum to ADR-042",
        body="# 1. Intro\n",
        amends=amends_yaml,
    )
    findings = amendment_lint.lint(tmp_path)
    rule_messages = [f["message"] for f in findings]
    assert not any("does not resolve" in m for m in rule_messages)


def test_lint_addendum_must_have_amends(tmp_path: Path, amendment_lint) -> None:
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body="# 1. Intro\n")
    _write_adr(
        tmp_path / "docs/adr/ADR-042-A.md",
        adr=4201,
        title="Addendum to ADR-042",
        body="# 1. Intro\n",
        amends="[]",
    )
    findings = amendment_lint.lint(tmp_path)
    assert any("amends: list is empty" in f["message"] for f in findings)


def test_lint_unresolved_target(tmp_path: Path, amendment_lint) -> None:
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body="# 1. Intro\n")
    amends_yaml = '\n  - target: "ADR-042 §99 Nonexistent"\n    kind: extend\n    summary: "Adds stuff"\n'
    _write_adr(
        tmp_path / "docs/adr/ADR-042-A.md",
        adr=4201,
        title="Addendum to ADR-042",
        body="# 1. Intro\n",
        amends=amends_yaml,
    )
    findings = amendment_lint.lint(tmp_path)
    assert any("§99 not a heading" in f["message"] for f in findings)


def test_lint_conflicting_replaces(tmp_path: Path, amendment_lint) -> None:
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body="# 17. Required Skills\n")
    amends_yaml = '\n  - target: "ADR-042 §17"\n    kind: replace\n    summary: "New skills v1"\n'
    _write_adr(
        tmp_path / "docs/adr/ADR-042-A.md",
        adr=4201,
        title="Addendum A to ADR-042",
        body="# 1. Intro\n",
        amends=amends_yaml,
    )
    _write_adr(
        tmp_path / "docs/adr/ADR-042-B.md",
        adr=4202,
        title="Addendum B to ADR-042",
        body="# 1. Intro\n",
        amends=amends_yaml,
    )
    findings = amendment_lint.lint(tmp_path)
    assert any("multiple 'replace' amendments" in f["message"] for f in findings)


def test_lint_circular_chain_warning(tmp_path: Path, amendment_lint) -> None:
    a_yaml = '\n  - target: "ADR-043"\n    kind: extend\n    summary: "x"\n'
    b_yaml = '\n  - target: "ADR-042"\n    kind: extend\n    summary: "y"\n'
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body="# 1. Intro\n", amends=a_yaml)
    _write_adr(tmp_path / "docs/adr/ADR-043.md", adr=43, body="# 1. Intro\n", amends=b_yaml)
    findings = amendment_lint.lint(tmp_path)
    assert any("circular amendment chain" in f["message"] and f["severity"] == "warning" for f in findings)


def test_main_returns_zero_on_clean(tmp_path: Path, amendment_lint, monkeypatch) -> None:
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body="# 1. Intro\n")
    monkeypatch.chdir(tmp_path)
    rc = amendment_lint.main([])
    assert rc == 0


def test_main_returns_one_on_error(tmp_path: Path, amendment_lint, monkeypatch) -> None:
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body="# 1. Intro\n")
    _write_adr(
        tmp_path / "docs/adr/ADR-042-A.md",
        adr=4201,
        title="Addendum to ADR-042",
        body="# 1. Intro\n",
        amends="[]",
    )
    monkeypatch.chdir(tmp_path)
    rc = amendment_lint.main([])
    assert rc == 1


# Keep sys.path clean across runs (the flat script appends to it).
def teardown_module() -> None:
    src_dir = str(_REPO_ROOT / "src")
    if src_dir in sys.path:
        sys.path.remove(src_dir)
