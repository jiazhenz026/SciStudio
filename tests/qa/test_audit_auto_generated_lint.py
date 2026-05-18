"""Tests for ``scieasy.qa.audit.auto_generated_lint`` (ADR-044 §11.5)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scieasy.qa.audit.auto_generated_lint import (
    BASELINE_RELPATH,
    check,
    compute_body_hash,
    load_baseline,
)
from scieasy.qa.schemas.report import Severity


def _write_ag_doc(
    repo: Path,
    rel_path: str,
    *,
    generation: str = "auto",
    body: str = "auto body\n",
) -> Path:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\ngeneration: {generation}\n---\n"
    path.write_text(frontmatter + body, encoding="utf-8")
    return path


def _write_baseline(repo: Path, mapping: dict[str, str]) -> Path:
    path = repo / BASELINE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# compute_body_hash / load_baseline
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_compute_body_hash_is_sha256(self, tmp_path: Path) -> None:
        path = tmp_path / "x.md"
        path.write_text("abc", encoding="utf-8")
        assert compute_body_hash(path) == hashlib.sha256(b"abc").hexdigest()

    def test_load_baseline_missing(self, tmp_path: Path) -> None:
        assert load_baseline(tmp_path) == {}

    def test_load_baseline_malformed_json(self, tmp_path: Path) -> None:
        baseline = tmp_path / BASELINE_RELPATH
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text("{not valid json", encoding="utf-8")
        assert load_baseline(tmp_path) == {}

    def test_load_baseline_non_dict(self, tmp_path: Path) -> None:
        baseline = tmp_path / BASELINE_RELPATH
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text("[1, 2, 3]", encoding="utf-8")
        assert load_baseline(tmp_path) == {}

    def test_load_baseline_filters_non_string_values(self, tmp_path: Path) -> None:
        _write_baseline(tmp_path, {})
        baseline = tmp_path / BASELINE_RELPATH
        baseline.write_text('{"a.md": "abc", "b.md": 123}', encoding="utf-8")
        result = load_baseline(tmp_path)
        assert result == {"a.md": "abc"}


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


class TestCheck:
    def test_no_docs_dir(self, tmp_path: Path) -> None:
        assert check(tmp_path) == []

    def test_no_ag_files(self, tmp_path: Path) -> None:
        # File without generation: auto frontmatter is skipped.
        _write_ag_doc(tmp_path, "docs/x.md", generation="hand")
        findings = check(tmp_path)
        # No AG files → no findings.
        assert findings == []

    def test_first_run_info_for_unknown_ag_file(self, tmp_path: Path) -> None:
        _write_ag_doc(tmp_path, "docs/user/reference/cli.md")
        findings = check(tmp_path)
        assert len(findings) == 1
        assert findings[0].rule_id == "auto-generated-lint.no-baseline"
        assert findings[0].severity == Severity.INFO

    def test_matching_hash_no_finding(self, tmp_path: Path) -> None:
        path = _write_ag_doc(tmp_path, "docs/user/x.md")
        sha = compute_body_hash(path)
        _write_baseline(tmp_path, {"docs/user/x.md": sha})
        assert check(tmp_path) == []

    def test_hand_edit_emits_error(self, tmp_path: Path) -> None:
        path = _write_ag_doc(tmp_path, "docs/user/x.md", body="original\n")
        original_sha = compute_body_hash(path)
        _write_baseline(tmp_path, {"docs/user/x.md": original_sha})
        # Hand-edit:
        path.write_text("---\ngeneration: auto\n---\nedited!\n", encoding="utf-8")
        findings = check(tmp_path)
        assert len(findings) == 1
        assert findings[0].rule_id == "auto-generated-lint.hand-edit"
        assert findings[0].severity == Severity.ERROR

    def test_no_frontmatter_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "docs/raw.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("no frontmatter at all", encoding="utf-8")
        assert check(tmp_path) == []

    def test_malformed_frontmatter_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "docs/bad.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\nbad yaml: : :\n---\nbody\n", encoding="utf-8")
        assert check(tmp_path) == []

    def test_partial_frontmatter_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "docs/no-close.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\nkey: value\nno closing", encoding="utf-8")
        assert check(tmp_path) == []

    def test_txt_files_also_scanned(self, tmp_path: Path) -> None:
        _write_ag_doc(tmp_path, "docs/user/llms.txt")
        findings = check(tmp_path)
        assert any(f.file == "docs/user/llms.txt" for f in findings)
