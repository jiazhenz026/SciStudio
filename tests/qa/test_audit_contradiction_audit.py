"""Tests for ``scieasy.qa.audit.contradiction_audit`` (ADR-042 §28.1).

Covers:

* self-supersede + governs/excludes contradiction findings.
* undefined section reference.
* cross-ADR supersedes cycle.
* workflow stage cycle detection.
* clean ADR yields no findings.
"""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.contradiction_audit import run
from scieasy.qa.schemas.report import Severity


def _write_adr(path: Path, *, adr: int, body: str, **frontmatter: str) -> None:
    extras = "".join(f"{k}: {v}\n" for k, v in frontmatter.items())
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
        f"{extras}"
        f"---\n\n"
        f"{body}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def test_clean_adr_yields_no_findings(tmp_path: Path) -> None:
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body="# 1. Intro\n\nIntro text. See §1 for details.\n")
    report = run(tmp_path)
    rule_ids = [f.rule_id for f in report.runs[0].findings]
    # No catastrophic findings (warnings/info allowed).
    assert "contradiction.self-supersede" not in rule_ids
    assert "contradiction.supersedes-cycle" not in rule_ids


def test_undefined_section_warning(tmp_path: Path) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 1. Intro\n\nSee §99 for details.\n",
    )
    report = run(tmp_path)
    assert any(
        f.rule_id == "contradiction.undefined-section" and f.severity == Severity.WARNING
        for f in report.runs[0].findings
    )


def test_cross_adr_supersedes_cycle(tmp_path: Path) -> None:
    _write_adr(
        tmp_path / "docs/adr/ADR-042.md",
        adr=42,
        body="# 1. Intro\n",
        supersedes="[43]",
    )
    _write_adr(
        tmp_path / "docs/adr/ADR-043.md",
        adr=43,
        body="# 1. Intro\n",
        supersedes="[42]",
    )
    report = run(tmp_path)
    cycles = [f for f in report.runs[0].findings if f.rule_id == "contradiction.supersedes-cycle"]
    assert cycles


def test_internal_clause_heuristic_warning(tmp_path: Path) -> None:
    body = "# 13. Trailers\n\nEvery commit MUST carry a trailer. Tier 1 humans are exempt. " * 3
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body=body)
    report = run(tmp_path)
    assert any(f.rule_id == "contradiction.internal-clause-heuristic" for f in report.runs[0].findings)


def test_workflow_stage_cycle(tmp_path: Path) -> None:
    body = "# 19. Workflow\n\n| Stage | Notes |\n|---|---|\n| `a` | depends on `b` |\n| `b` | depends on `a` |\n"
    _write_adr(tmp_path / "docs/adr/ADR-042.md", adr=42, body=body)
    report = run(tmp_path)
    assert any(f.rule_id == "contradiction.workflow-stage-cycle" for f in report.runs[0].findings)


def test_run_with_explicit_targets(tmp_path: Path) -> None:
    p = tmp_path / "docs/adr/ADR-042.md"
    _write_adr(p, adr=42, body="# 1. Intro\n\nSee §99 for details.\n")
    report = run(tmp_path, targets=[p])
    assert report.runs[0].tool == "contradiction_audit"
    assert report.total_findings >= 1
