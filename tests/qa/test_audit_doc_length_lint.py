"""Tests for ``scieasy.qa.audit.doc_length_lint`` (ADR-044 §4.3)."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.doc_length_lint import (
    ERROR_LINE_CAP,
    ERROR_WORD_CAP,
    WARNING_LINE_CAP,
    check,
    count_metrics,
)
from scieasy.qa.schemas.report import Severity


def _write_doc(
    repo: Path,
    rel_path: str,
    *,
    frontmatter: dict[str, str] | None = None,
    body: str,
) -> Path:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = ""
    if frontmatter is not None:
        fm_lines = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
        fm_text = f"---\n{fm_lines}\n---\n"
    path.write_text(fm_text + body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# count_metrics
# ---------------------------------------------------------------------------


class TestCountMetrics:
    def test_simple_count(self) -> None:
        lines, words = count_metrics("hello world\nfoo bar baz\n")
        assert lines == 2
        assert words == 5

    def test_blank_lines_ignored(self) -> None:
        lines, _ = count_metrics("a\n\nb\n\n\nc\n")
        assert lines == 3

    def test_fenced_code_stripped_from_words(self) -> None:
        text = "hello\n```\nthis code is stripped\n```\nworld\n"
        lines, words = count_metrics(text)
        # Lines: hello, ```, this code is stripped, ```, world = 5
        assert lines == 5
        # Words: hello, world = 2.
        assert words == 2


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


class TestCheck:
    def test_no_docs_dir(self, tmp_path: Path) -> None:
        assert check(tmp_path) == []

    def test_compliant_doc_no_findings(self, tmp_path: Path) -> None:
        _write_doc(
            tmp_path,
            "docs/contributing/workflows/short.md",
            frontmatter={"workflow_id": "short"},
            body="# short\n\nbody\n",
        )
        assert check(tmp_path) == []

    def test_line_cap_exceeded_error(self, tmp_path: Path) -> None:
        body = "line\n" * (ERROR_LINE_CAP + 5)
        _write_doc(
            tmp_path,
            "docs/contributing/workflows/long.md",
            frontmatter={"workflow_id": "long"},
            body=body,
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "doc-length-lint.line-cap-exceeded" and f.severity == Severity.ERROR for f in findings)

    def test_approaching_line_cap_warning(self, tmp_path: Path) -> None:
        body = "line\n" * (WARNING_LINE_CAP + 5)
        _write_doc(
            tmp_path,
            "docs/contributing/workflows/mid.md",
            frontmatter={"workflow_id": "mid"},
            body=body,
        )
        findings = check(tmp_path)
        assert any(
            f.rule_id == "doc-length-lint.approaching-line-cap" and f.severity == Severity.WARNING for f in findings
        )

    def test_word_cap_exceeded_error(self, tmp_path: Path) -> None:
        # 700 words on a single line — exceeds word cap but not line cap.
        body = " ".join(["word"] * (ERROR_WORD_CAP + 100)) + "\n"
        _write_doc(
            tmp_path,
            "docs/contributing/workflows/wordy.md",
            frontmatter={"workflow_id": "wordy"},
            body=body,
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "doc-length-lint.word-cap-exceeded" and f.severity == Severity.ERROR for f in findings)

    def test_exception_reason_downgrades_to_info(self, tmp_path: Path) -> None:
        body = "line\n" * (ERROR_LINE_CAP + 5)
        _write_doc(
            tmp_path,
            "docs/contributing/workflows/with-exception.md",
            frontmatter={
                "workflow_id": "exc",
                "length_exception_reason": "see issue #999",
            },
            body=body,
        )
        findings = check(tmp_path)
        line_findings = [f for f in findings if f.rule_id == "doc-length-lint.line-cap-exceeded"]
        assert len(line_findings) == 1
        assert line_findings[0].severity == Severity.INFO

    def test_ag_files_exempt(self, tmp_path: Path) -> None:
        body = "line\n" * (ERROR_LINE_CAP + 50)
        _write_doc(
            tmp_path,
            "docs/user/reference/big.md",
            frontmatter={"doc_id": "big", "generation": "auto"},
            body=body,
        )
        # AG file should produce NO doc-length finding (cap doesn't apply).
        assert check(tmp_path) == []

    def test_adr_path_exempt(self, tmp_path: Path) -> None:
        body = "line\n" * (ERROR_LINE_CAP + 50)
        _write_doc(
            tmp_path,
            "docs/adr/ADR-999.md",
            frontmatter={"adr": "999"},
            body=body,
        )
        assert check(tmp_path) == []

    def test_uncovered_path_skipped(self, tmp_path: Path) -> None:
        # Outside the four covered categories.
        body = "line\n" * (ERROR_LINE_CAP + 50)
        _write_doc(
            tmp_path,
            "docs/audit/baseline.md",
            frontmatter={"name": "baseline"},
            body=body,
        )
        assert check(tmp_path) == []

    def test_user_dir_covered(self, tmp_path: Path) -> None:
        body = "line\n" * (ERROR_LINE_CAP + 5)
        _write_doc(
            tmp_path,
            "docs/user/tutorial.md",
            frontmatter={"doc_id": "tut", "generation": "hand"},
            body=body,
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "doc-length-lint.line-cap-exceeded" for f in findings)

    def test_no_frontmatter_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "docs/contributing/workflows/no-fm.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a\n" * (ERROR_LINE_CAP + 5), encoding="utf-8")
        # No frontmatter → skipped per implementation contract.
        assert check(tmp_path) == []
