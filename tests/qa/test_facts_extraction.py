"""Tests for ``scripts/audit/extract_*_facts.py`` + ``generate_facts.py`` (Phase 1H sub-PR 3).

Each extractor is exercised against a synthetic fixture directory under
``tmp_path``; we deliberately avoid coupling to the live repo files so
the test suite is hermetic. The orchestrator (``generate_facts``) is
exercised once against the live repo to confirm end-to-end shape.

References
----------
ADR-042 §7.5.3 — generation table.
TC-1H.5 — fact-extractor deliverable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from scripts.audit import (
    extract_adr_facts,
    extract_maintainers_facts,
    extract_skill_facts,
    extract_tool_facts,
    extract_workflow_facts,
    generate_facts,
)

from scieasy.qa.schemas.facts import (
    ADRFacts,
    FactsRegistry,
    MaintainersFacts,
    SkillFacts,
    ToolFacts,
    WorkflowFacts,
)

# ---------------------------------------------------------------------------
# Workflow extractor
# ---------------------------------------------------------------------------


def test_extract_workflow_facts_basic(tmp_path: Path) -> None:
    schema = tmp_path / "schema.yaml"
    schema.write_text(
        yaml.safe_dump(
            {
                "version": "2.0.0",
                "stages": [
                    {"id": "stage_one", "validations": ["v1.shape", "v1.dep"]},
                    {"id": "stage_two", "validations": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    facts = extract_workflow_facts.extract(schema)
    assert isinstance(facts, WorkflowFacts)
    assert facts.stage_count == 2
    assert facts.stages == ["stage_one", "stage_two"]
    assert facts.blocking_validations == {
        "stage_one": ["v1.shape", "v1.dep"],
        "stage_two": [],
    }


def test_extract_workflow_facts_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_workflow_facts.extract(tmp_path / "nope.yaml")


def test_extract_workflow_facts_missing_stages(tmp_path: Path) -> None:
    schema = tmp_path / "schema.yaml"
    schema.write_text(yaml.safe_dump({"version": "2.0.0", "stages": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="no 'stages'"):
        extract_workflow_facts.extract(schema)


def test_extract_workflow_facts_stage_without_id(tmp_path: Path) -> None:
    schema = tmp_path / "schema.yaml"
    schema.write_text(
        yaml.safe_dump({"stages": [{"validations": []}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing 'id'"):
        extract_workflow_facts.extract(schema)


def test_extract_workflow_facts_validations_must_be_list(tmp_path: Path) -> None:
    schema = tmp_path / "schema.yaml"
    schema.write_text(
        yaml.safe_dump({"stages": [{"id": "s", "validations": "not-a-list"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-list 'validations'"):
        extract_workflow_facts.extract(schema)


def test_extract_workflow_facts_stage_not_a_mapping(tmp_path: Path) -> None:
    schema = tmp_path / "schema.yaml"
    schema.write_text(yaml.safe_dump({"stages": ["not-a-dict"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a mapping"):
        extract_workflow_facts.extract(schema)


def test_extract_workflow_facts_default_path_walks_up(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify the walk-up default-path resolver."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / ".workflow").mkdir()
    (tmp_path / ".workflow" / "schema-v2.yaml").write_text(
        yaml.safe_dump({"stages": [{"id": "s", "validations": []}]}),
        encoding="utf-8",
    )
    sub = tmp_path / "scripts" / "audit"
    sub.mkdir(parents=True)
    monkeypatch.setattr(extract_workflow_facts, "__file__", str(sub / "extract_workflow_facts.py"))
    facts = extract_workflow_facts.extract()
    assert facts.stage_count == 1


def test_extract_workflow_facts_default_path_falls_back_to_nonexistent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If pyproject is found but no .workflow/schema-v2.yaml exists, surface FileNotFoundError."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    sub = tmp_path / "scripts" / "audit"
    sub.mkdir(parents=True)
    monkeypatch.setattr(extract_workflow_facts, "__file__", str(sub / "extract_workflow_facts.py"))
    with pytest.raises(FileNotFoundError, match="schema not found"):
        extract_workflow_facts.extract()


def test_extract_workflow_facts_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    schema = tmp_path / "schema.yaml"
    schema.write_text(
        yaml.safe_dump({"stages": [{"id": "s1", "validations": []}]}),
        encoding="utf-8",
    )
    rc = extract_workflow_facts.main(["--schema", str(schema)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage_count"] == 1


# ---------------------------------------------------------------------------
# Tool extractor
# ---------------------------------------------------------------------------


def _write_pyproject(tmp_path: Path, *, with_pytest: bool = True, with_ruff: bool = True) -> Path:
    """Build a minimal pyproject.toml for testing."""
    pyproject = tmp_path / "pyproject.toml"
    parts = [
        "[project]",
        'name = "demo"',
        'requires-python = ">=3.11"',
        "",
        "[tool.mypy]",
        'python_version = "3.11"',
        "",
    ]
    if with_pytest:
        parts.extend(
            [
                "[tool.pytest.ini_options]",
                'addopts = "-ra -q --cov=demo --cov-fail-under=85"',
                "",
            ]
        )
    if with_ruff:
        parts.extend(
            [
                "[tool.ruff.lint]",
                'select = ["E", "F", "I"]',
                "",
            ]
        )
    pyproject.write_text("\n".join(parts), encoding="utf-8")
    return pyproject


def test_extract_tool_facts_basic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    py = _write_pyproject(tmp_path)
    pc = tmp_path / ".pre-commit-config.yaml"
    pc.write_text(
        yaml.safe_dump(
            {
                "repos": [
                    {"hooks": [{"id": "mypy"}]},
                    {"hooks": [{"id": "ruff"}]},
                ]
            }
        ),
        encoding="utf-8",
    )
    # The extractor walks up looking for pyproject.toml; place this fixture
    # so the walk finds OUR fixture first.
    monkeypatch.chdir(tmp_path)
    facts = extract_tool_facts.extract(py, pc)
    assert isinstance(facts, ToolFacts)
    assert facts.python_version == "3.11"
    assert facts.min_coverage_percent == 85
    assert facts.lint_rules == ["E", "F", "I"]
    assert "mypy" in facts.type_checkers
    assert facts.docs_engine == "sphinx"


def test_extract_tool_facts_no_pytest_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    py = _write_pyproject(tmp_path, with_pytest=False)
    monkeypatch.chdir(tmp_path)
    facts = extract_tool_facts.extract(py, tmp_path / "missing.yaml")
    assert facts.min_coverage_percent == 0
    # mypy fallback (no pre-commit file).
    assert facts.type_checkers == ["mypy"]


def test_extract_tool_facts_missing_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Need a sentinel pyproject elsewhere so _find_repo_root succeeds.
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    (sentinel / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    monkeypatch.chdir(sentinel)
    with pytest.raises(FileNotFoundError):
        extract_tool_facts.extract(tmp_path / "nope.toml", tmp_path / "nope.yaml")


def test_extract_tool_facts_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    py = _write_pyproject(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = extract_tool_facts.main(["--pyproject", str(py)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["docs_engine"] == "sphinx"


# ---------------------------------------------------------------------------
# ADR extractor
# ---------------------------------------------------------------------------


def test_extract_adr_facts_basic(tmp_path: Path) -> None:
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "ADR-001.md").write_text(
        "---\nadr: 1\nstatus: Accepted\n---\n\nbody\n",
        encoding="utf-8",
    )
    (adr_dir / "ADR-002.md").write_text(
        "---\nadr: 2\nstatus: Proposed\n---\n\nbody\n",
        encoding="utf-8",
    )
    (adr_dir / "ADR-003.md").write_text(
        "---\nadr: 3\nstatus: Accepted\n---\n\nbody\n",
        encoding="utf-8",
    )
    (adr_dir / "ADR.md").write_text("not an ADR\n", encoding="utf-8")  # ignored
    facts = extract_adr_facts.extract(adr_dir)
    assert isinstance(facts, ADRFacts)
    assert facts.total_count == 3
    assert facts.by_status == {"Accepted": 2, "Proposed": 1}
    assert facts.latest_adr_number == 3


def test_extract_adr_facts_missing_dir(tmp_path: Path) -> None:
    facts = extract_adr_facts.extract(tmp_path / "missing")
    assert facts.total_count == 0
    assert facts.latest_adr_number == 0
    assert facts.by_status == {}


def test_extract_adr_facts_malformed_frontmatter(tmp_path: Path) -> None:
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "ADR-005.md").write_text("no frontmatter here\n", encoding="utf-8")
    facts = extract_adr_facts.extract(adr_dir)
    assert facts.total_count == 1
    assert facts.by_status == {"unknown": 1}


def test_extract_adr_facts_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "ADR-007.md").write_text(
        "---\nadr: 7\nstatus: Draft\n---\n",
        encoding="utf-8",
    )
    # Need pyproject for _find_repo_root.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = extract_adr_facts.main(["--adr-dir", str(adr_dir)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["latest_adr_number"] == 7


# ---------------------------------------------------------------------------
# Maintainers extractor
# ---------------------------------------------------------------------------


def test_extract_maintainers_facts_basic(tmp_path: Path) -> None:
    m = tmp_path / "MAINTAINERS"
    m.write_text(
        "---\nowners: ['@alice', '@bob']\npaths: ['src/scieasy/**']\n---\n"
        "owners: ['@alice']\npaths: ['docs/**', 'tests/**']\n",
        encoding="utf-8",
    )
    facts = extract_maintainers_facts.extract(m)
    assert isinstance(facts, MaintainersFacts)
    assert facts.entry_count == 2
    assert facts.human_count == 2  # alice + bob
    assert facts.paths_covered_count == 3


def test_extract_maintainers_facts_missing(tmp_path: Path) -> None:
    facts = extract_maintainers_facts.extract(tmp_path / "MISSING")
    assert facts.entry_count == 0
    assert facts.human_count == 0


def test_extract_maintainers_facts_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    m = tmp_path / "MAINTAINERS"
    m.write_text("owners: ['@x']\npaths: ['p']\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = extract_maintainers_facts.main(["--maintainers", str(m)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["entry_count"] == 1


# ---------------------------------------------------------------------------
# Skill extractor
# ---------------------------------------------------------------------------


def test_extract_skill_facts_basic(tmp_path: Path) -> None:
    # Required manifest.
    docs_skills = tmp_path / "docs" / "skills"
    docs_skills.mkdir(parents=True)
    (docs_skills / "required.yaml").write_text(
        yaml.safe_dump(
            {"skills": [{"name": "a"}, {"name": "b"}, "c"]},
        ),
        encoding="utf-8",
    )
    # Claude install paths for two of the three.
    cs = tmp_path / ".claude" / "skills"
    (cs / "a").mkdir(parents=True)
    (cs / "a" / "SKILL.md").write_text("---\nname: a\n---\n", encoding="utf-8")
    (cs / "b").mkdir()
    (cs / "b" / "SKILL.md").write_text("---\nname: b\n---\n", encoding="utf-8")
    # pyproject for _find_repo_root.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    facts = extract_skill_facts.extract(docs_skills / "required.yaml", repo_root=tmp_path)
    assert isinstance(facts, SkillFacts)
    assert facts.required_skills == ["a", "b", "c"]
    assert sorted(facts.installed_per_runtime["claude"]) == ["a", "b"]


def test_extract_skill_facts_missing_manifest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    facts = extract_skill_facts.extract(tmp_path / "missing.yaml", repo_root=tmp_path)
    assert facts.required_skills == []
    assert facts.installed_per_runtime == {"claude": []}


def test_extract_skill_facts_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = extract_skill_facts.main(["--repo-root", str(tmp_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "required_skills" in payload


# ---------------------------------------------------------------------------
# Generator orchestrator
# ---------------------------------------------------------------------------


def _build_full_repo_fixture(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\nname='demo'\nrequires-python='>=3.11'\n"
        "[tool.mypy]\npython_version='3.11'\n"
        "[tool.pytest.ini_options]\naddopts='--cov-fail-under=70'\n"
        "[tool.ruff.lint]\nselect=['E']\n",
        encoding="utf-8",
    )
    workflow_dir = root / ".workflow"
    workflow_dir.mkdir()
    (workflow_dir / "schema-v2.yaml").write_text(
        yaml.safe_dump({"stages": [{"id": "s", "validations": []}]}),
        encoding="utf-8",
    )
    (root / "docs" / "adr").mkdir(parents=True)
    (root / "docs" / "adr" / "ADR-042.md").write_text(
        "---\nadr: 42\nstatus: Accepted\n---\n",
        encoding="utf-8",
    )
    (root / "docs" / "skills").mkdir()
    (root / "docs" / "skills" / "required.yaml").write_text(
        yaml.safe_dump({"skills": [{"name": "skill-a"}]}),
        encoding="utf-8",
    )
    (root / ".claude" / "skills" / "skill-a").mkdir(parents=True)
    (root / ".claude" / "skills" / "skill-a" / "SKILL.md").write_text("body\n", encoding="utf-8")


def test_generate_writes_yaml(tmp_path: Path) -> None:
    _build_full_repo_fixture(tmp_path)
    registry = generate_facts.generate(tmp_path)
    assert isinstance(registry, FactsRegistry)
    out = tmp_path / "docs" / "facts" / "generated.yaml"
    generate_facts.write_yaml(registry, out)
    assert out.is_file()
    reread = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert reread["schema_version"] == 1
    assert reread["adr"]["latest_adr_number"] == 42


def test_generate_records_source_shas(tmp_path: Path) -> None:
    _build_full_repo_fixture(tmp_path)
    registry = generate_facts.generate(tmp_path)
    assert ".workflow/schema-v2.yaml" in registry.source_shas
    # SHA-1 hex is 40 chars when present, empty when absent.
    sha = registry.source_shas[".workflow/schema-v2.yaml"]
    assert len(sha) == 40
    # MAINTAINERS absent → empty sha.
    assert registry.source_shas["MAINTAINERS"] == ""


def test_generate_cli_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _build_full_repo_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "docs" / "facts" / "generated.yaml"
    rc = generate_facts.main(["--output", str(out)])
    assert rc == 0
    assert out.is_file()


def test_generate_check_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _build_full_repo_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "docs" / "facts" / "generated.yaml"
    # First, write a fresh file.
    rc = generate_facts.main(["--output", str(out)])
    assert rc == 0
    # Check passes against the file we just wrote.
    rc = generate_facts.main(["--output", str(out), "--check"])
    assert rc == 0
    # Mutate the file → check fails.
    out.write_text("not-yaml-like\n", encoding="utf-8")
    rc = generate_facts.main(["--output", str(out), "--check"])
    assert rc == 1


def test_generate_check_missing_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _build_full_repo_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "docs" / "facts" / "generated.yaml"
    rc = generate_facts.main(["--output", str(out), "--check"])
    assert rc == 1
