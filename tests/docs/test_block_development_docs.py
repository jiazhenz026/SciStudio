from __future__ import annotations

from pathlib import Path

from scistudio.qa.audit.developer_docs import check_report
from scistudio.qa.schemas.report import AuditStatus


def _write_doc(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
doc_type: block-development
title: "Package Development Guide"
status: living
owner: "@owner"
last_updated: 2026-06-11
governed_by: ["ADR-042", "docs/specs/package-development.md"]
summary: "Guidance for building package-facing developer documentation."
---

{body}
""",
        encoding="utf-8",
    )


def test_block_development_docs_accept_valid_frontmatter_and_links(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "block-development" / "guide.md"
    _write_doc(
        path,
        """# Package Development Guide

See [Details](#custom-details).

Inline code such as `Collection[Image](length=1)` is not a Markdown link.

## Details {#custom-details}

Use current block package contracts.
""",
    )

    report = check_report(tmp_path, docs=[path])

    assert report.status == AuditStatus.PASS
    assert report.findings == []


def test_block_development_docs_report_stale_developer_guidance(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "block-development" / "guide.md"
    _write_doc(
        path,
        """# Package Development Guide

Run `pip install -e .` before testing a block package.
""",
    )

    report = check_report(tmp_path, docs=[path])

    assert report.status == AuditStatus.FAIL
    assert {finding.rule_id for finding in report.findings} == {"developer-docs.stale-editable-install"}


def test_block_development_docs_report_broken_links(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "block-development" / "guide.md"
    _write_doc(
        path,
        """# Package Development Guide

See [Missing](missing.md).
""",
    )

    report = check_report(tmp_path, docs=[path])

    assert report.status == AuditStatus.FAIL
    assert {finding.rule_id for finding in report.findings} == {"developer-docs.link-missing-target"}
