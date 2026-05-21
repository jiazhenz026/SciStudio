from __future__ import annotations

from pathlib import Path

from scistudio.qa.audit import full_audit
from scistudio.qa.audit.facts import write_facts
from scistudio.qa.audit.full_audit import render_markdown, run
from scistudio.qa.schemas.facts import FactsRegistry
from scistudio.qa.schemas.report import AuditStatus

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_full_audit_renders_human_readable_facts_summary() -> None:
    report = run(REPO_ROOT, check_stale=False)

    markdown = render_markdown(report)

    assert report.status in {AuditStatus.PASS, AuditStatus.FAIL}
    assert "# ADR-042 Facts Audit Summary" in markdown
    assert "## 3. Fact Inventory" in markdown
    assert "## 5. Largest Symbol Areas" in markdown
    assert "## 7. Child Reports" in markdown
    assert "frontmatter_lint" in markdown
    assert "fact_drift" in markdown
    assert "doc_drift" in markdown
    assert "closure" in markdown
    assert "signature_drift" in markdown
    assert "architecture_drift" in markdown
    assert "vulture" in markdown


def test_full_audit_reports_stale_generated_facts(tmp_path: Path) -> None:
    facts_path = tmp_path / "generated.yaml"
    write_facts(FactsRegistry(source_sha="stale-sha"), facts_path)

    report = run(REPO_ROOT, facts_path=facts_path)

    assert report.status == AuditStatus.FAIL
    assert report.blocks_merge
    assert [finding.rule_id for finding in report.error_findings()] == ["facts.generated-stale"]


def test_full_audit_generates_default_facts_in_memory_when_snapshot_is_missing(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        full_audit,
        "generate_facts",
        lambda repo_root: FactsRegistry(source_sha="in-memory-sha"),
    )

    report = run(
        repo_root,
        check_stale=True,
        include_frontmatter_lint=False,
        include_fact_drift=False,
        include_doc_drift=False,
        include_closure=False,
        include_signature_drift=False,
        include_architecture_drift=False,
        include_vulture=False,
    )

    facts_report = report.child_reports[0]
    assert facts_report.status == AuditStatus.PASS
    assert facts_report.source_sha == "in-memory-sha"
    assert facts_report.summary["generated_in_memory"] is True
