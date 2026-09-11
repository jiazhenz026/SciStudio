"""Regression coverage for the documentation-language audit."""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.qa.audit.docstrings import check


def _source(root: Path, text: str) -> Path:
    path = root / "src/scistudio/example.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "marker",
    [
        "ADR-050",
        "FR-001",
        "adr_050",
        "ADR\u2013050",
        "NFR-002",
        "DSN-3",
        "SC-004",
        "OQ-1",
        "T-ECA-205",
        "OBS-2",
        "BCP-3",
        "AC-1",
        "TRK-9",
        "BUG-7",
        "REQ-2",
        "SPEC 2",
        "PR-321",
        "Addendum 6",
        "#1234",
        "TODO",
        "FIXME",
        "dispatch prompt",
        "skeleton agent",
        "Implementation plan",
        "Test plan",
        "docs/specs/design.md",
        "ADR §3.4",
        "spec §6.1",
        "checklist §2",
        "I40c",
        "S40b",
        "D38-2.3",
        "T-012",
        "Phase 2a",
        "Task 18",
    ],
)
def test_rejects_internal_markers(tmp_path: Path, marker: str) -> None:
    _source(tmp_path, f'"""Load data.\n\nSee {marker}.\n"""\n')
    report = check(tmp_path)
    assert report.blocks_merge
    assert report.findings[0].line == 3
    assert report.findings[0].file == "src/scistudio/example.py"
    assert marker in report.findings[0].message or marker == "T-ECA-205"


def test_covers_all_documentation_owners_without_imports(tmp_path: Path) -> None:
    _source(
        tmp_path,
        '''"""ADR-001."""
import missing_optional_dependency
field = 1
"""FR-001."""
class Example:
    """ADR-002."""
    value: str = "value"
    """FR-002."""
    def __init__(self):
        self.value = "value"
        """FR-003."""
    @property
    def size(self):
        """FR-004."""
        return 1
    async def fetch(self):
        """FR-005."""
        def nested():
            """FR-006."""
def _private():
    """FR-007."""
    """FR-008."""
''',
    )
    report = check(tmp_path)
    assert len(report.findings) == 10
    assert any("Example.__init__.self.value:" in finding.message for finding in report.findings)
    assert any("Example.fetch.nested:" in finding.message for finding in report.findings)


def test_preserves_comments_runtime_strings_and_external_technical_content(tmp_path: Path) -> None:
    _source(
        tmp_path,
        '''"""Read UTF-8, ISO-8601, RFC 3339, SHA-256 and RUF001.
See :class:`Example` and :meth:`Example.run`; use application/json.
"""
# ADR-050 FR-001 TODO(#1234): maintainer traceability.
error = "See ADR-050"
pattern = r"FR-\\d+"
def run():
    print("ADR-050")
    return "FR-001"
''',
    )
    report = check(tmp_path)
    assert not report.blocks_merge
    assert report.summary["docstrings_checked"] == 1


def test_decodes_escapes_and_concatenated_literals(tmp_path: Path) -> None:
    _source(tmp_path, 'def run():\n    ("FR-" "001 and ADR\\x2d050")\n')
    assert check(tmp_path).blocks_merge


def test_parse_failure_blocks_audit(tmp_path: Path) -> None:
    _source(tmp_path, "def broken(:\n")
    report = check(tmp_path)
    assert report.blocks_merge
    assert report.findings[0].rule_id == "docstrings.unreadable-source"


def test_actual_package_docstrings_are_clean() -> None:
    report = check(Path(__file__).resolve().parents[2])
    assert not report.blocks_merge, report.model_dump_json(indent=2)
