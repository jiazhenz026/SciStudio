from datetime import UTC, datetime
from pathlib import Path

from scieasy.qa.audit.closure import check_bidirectional
from scieasy.qa.audit.doc_drift import classify_repo
from scieasy.qa.audit.fact_drift import check_substitutions
from scieasy.qa.audit.full_audit import run as run_full_audit
from scieasy.qa.audit.signature_drift import check_expected_signatures
from scieasy.qa.schemas.facts import Fact, FactsRegistry


def _registry(facts: list[Fact]) -> FactsRegistry:
    return FactsRegistry(
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_sha="test",
        facts=facts,
    )


def _fact(**kwargs) -> Fact:
    defaults = {
        "source": "docs/specs/test.md",
        "owner": "@owner",
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "source_sha": "test",
        "confidence": "normative",
        "stability": "stable",
    }
    defaults.update(kwargs)
    return Fact(**defaults)


def test_fact_drift_reports_missing_fact_substitution(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("Uses {{ fact:missing.fact }}.\n", encoding="utf-8")
    report = check_substitutions(tmp_path, _registry([]))
    assert report.status == "failed"
    assert report.findings[0].finding_class == "phantom-reference"


def test_doc_drift_reports_missing_path_reference(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("See `src/scieasy/missing.py`.\n", encoding="utf-8")
    report = classify_repo(tmp_path, _registry([]))
    assert report.status == "failed"
    assert report.findings[0].id == "doc-drift-phantom-reference"


def test_closure_reports_phantom_governed_file(tmp_path: Path) -> None:
    facts = _registry(
        [
            _fact(
                id="file:missing",
                kind="file",
                subject="src/scieasy/missing.py",
                value={"governed_by": "ADR-999"},
            )
        ]
    )
    report = check_bidirectional(tmp_path, facts)
    assert report.status == "failed"
    assert any(finding.id == "closure-phantom-governed-file" for finding in report.findings)


def test_signature_drift_reports_missing_symbol(tmp_path: Path) -> None:
    facts = _registry(
        [
            _fact(
                id="expected:missing",
                kind="expected-signature",
                subject="scieasy.missing.symbol",
                value={
                    "symbol": "scieasy.missing.symbol",
                    "kind": "function",
                    "parameters": [],
                    "return_annotation": None,
                    "source_spec": "docs/specs/test.md",
                    "source_line": 1,
                },
            )
        ]
    )
    report = check_expected_signatures(tmp_path, facts)
    assert report.status == "failed"
    assert report.findings[0].finding_class == "signature-drift"


def test_signature_drift_resolves_short_model_names(tmp_path: Path) -> None:
    facts = _registry(
        [
            _fact(
                id="symbol:adr-frontmatter",
                kind="symbol",
                subject="scieasy.qa.schemas.frontmatter.ADRFrontmatter",
                value={"kind": "ClassDef"},
            ),
            _fact(
                id="expected:adr-field",
                kind="expected-model-field",
                subject="ADRFrontmatter.adr",
                value={
                    "model_symbol": "ADRFrontmatter",
                    "field_name": "adr",
                    "annotation": "int",
                    "default": None,
                    "required": True,
                    "source_spec": "docs/specs/test.md",
                    "source_line": 1,
                },
            ),
        ]
    )
    report = check_expected_signatures(tmp_path, facts)
    assert report.status == "passed"


def test_full_audit_preserves_child_failures(tmp_path: Path) -> None:
    facts_dir = tmp_path / "docs" / "facts"
    facts_dir.mkdir(parents=True)
    facts_path = facts_dir / "generated.yaml"
    facts_path.write_text(
        """schema_version: '1'
generated_at: '2026-01-01T00:00:00Z'
source_sha: test
facts:
  - id: file:missing
    kind: file
    source: docs/specs/test.md
    subject: src/scieasy/missing.py
    value: {governed_by: ADR-999}
    owner: '@owner'
    generated_at: '2026-01-01T00:00:00Z'
    source_sha: test
    confidence: normative
    stability: stable
""",
        encoding="utf-8",
    )
    report = run_full_audit(tmp_path, facts_path=facts_path)
    assert report.status == "failed"
    assert any(child.tool == "closure" for child in report.child_reports)
