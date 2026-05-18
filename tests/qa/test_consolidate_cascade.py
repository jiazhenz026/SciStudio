"""Tests for ``scripts/audit/consolidate_cascade.py`` (ADR-042 §27.5)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "audit" / "consolidate_cascade.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("consolidate_cascade", _SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def consolidator():
    return _load_module()


def _write_adr(path: Path, *, adr: int, body: str, amends: str = "[]") -> None:
    contents = (
        f"---\n"
        f"adr: {adr}\n"
        f'title: "Test ADR {adr}"\n'
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


def test_consolidate_base_only(tmp_path: Path, consolidator) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 1. Intro\n\nBase intro.\n\n# 2. Body\n\nBase body.\n",
    )
    md = consolidator.consolidate(tmp_path, base_adr=42)
    assert "AUTO-GENERATED" in md
    assert "Base intro." in md
    assert "Base body." in md


def test_consolidate_extend_appends_note(tmp_path: Path, consolidator) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 1. Intro\n\nBase intro.\n\n# 17. Skills\n\nOriginal skills list.\n",
    )
    amends_yaml = '\n  - target: "ADR-042 §17 Skills"\n    kind: extend\n    summary: "Adds new skills"\n'
    _write_adr(
        tmp_path / "docs/adr/ADR-042-A.md",
        adr=4201,
        body="# 1. Intro\n",
        amends=amends_yaml,
    )
    md = consolidator.consolidate(tmp_path, base_adr=42)
    assert "Original skills list." in md
    assert "ADR-4201 extends this section" in md
    assert "Adds new skills" in md


def test_consolidate_replace_substitutes_section(tmp_path: Path, consolidator) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 17. Skills\n\nOriginal skills list.\n",
    )
    amends_yaml = '\n  - target: "ADR-042 §17"\n    kind: replace\n    summary: "Full rewrite"\n'
    _write_adr(
        tmp_path / "docs/adr/ADR-042-A.md",
        adr=4201,
        body="# 1. Intro\n",
        amends=amends_yaml,
    )
    md = consolidator.consolidate(tmp_path, base_adr=42)
    assert "Replaced by ADR-4201" in md
    assert "Original skills list." not in md


def test_consolidate_constrain_adds_restriction(tmp_path: Path, consolidator) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 17. Skills\n\nOriginal skills list.\n",
    )
    amends_yaml = '\n  - target: "ADR-042 §17"\n    kind: constrain\n    summary: "Tightens to N-1 skills"\n'
    _write_adr(
        tmp_path / "docs/adr/ADR-042-A.md",
        adr=4201,
        body="# 1. Intro\n",
        amends=amends_yaml,
    )
    md = consolidator.consolidate(tmp_path, base_adr=42)
    assert "Original skills list." in md
    assert "Additional restriction" in md
    assert "Tightens to N-1 skills" in md


def test_consolidate_missing_base_emits_empty(tmp_path: Path, consolidator) -> None:
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    md = consolidator.consolidate(tmp_path, base_adr=999)
    assert "no consolidation produced" in md


def test_main_writes_output(tmp_path: Path, consolidator, monkeypatch) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 1. Intro\n",
    )
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out.md"
    rc = consolidator.main(["--output", str(out), "--base", "42"])
    assert rc == 0
    assert out.is_file()
    assert "AUTO-GENERATED" in out.read_text(encoding="utf-8")
