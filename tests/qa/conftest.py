"""QA-local test fixtures for tools that return ``AuditReport`` shaped objects."""

from __future__ import annotations

import sys
import types
from datetime import datetime

import pytest
from pydantic import BaseModel, Field


class _FakeAuditFinding(BaseModel):
    id: str
    tool: str
    severity: str
    finding_class: str
    message: str
    path: str | None = None
    line: int | None = None
    subject: str | None = None
    expected: object | None = None
    actual: object | None = None
    remediation: str | None = None
    evidence: dict[str, object] = Field(default_factory=dict)


class _FakeAuditReport(BaseModel):
    tool: str
    status: str
    generated_at: datetime
    source_sha: str
    findings: list[_FakeAuditFinding] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)
    child_reports: list[_FakeAuditReport] = Field(default_factory=list)

    @property
    def blocks_merge(self) -> bool:
        return not self.findings

    def error_findings(self) -> list[_FakeAuditFinding]:
        return [finding for finding in self.findings if str(finding.severity) == "error"]


@pytest.fixture(autouse=True)
def _qa_report_schema_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests for documentation tools run without ``scieasy.qa.schemas``."""

    fake_module = types.ModuleType("scieasy.qa.schemas.report")
    fake_module.AuditFinding = _FakeAuditFinding
    fake_module.AuditReport = _FakeAuditReport
    fake_module.__all__ = ["AuditFinding", "AuditReport"]
    monkeypatch.setitem(sys.modules, "scieasy.qa.schemas.report", fake_module)
    return None
