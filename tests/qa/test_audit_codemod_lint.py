"""Tests for ``scieasy.qa.audit.codemod_lint`` (ADR-042 §20.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.qa.audit.codemod_lint import check, parse, parse_model
from scieasy.qa.schemas.codemod import CodemodMeta
from scieasy.qa.schemas.report import Severity


def _write_codemod(path: Path, docstring: str, *, body: str = "pass\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'"""{docstring}"""\n\n{body}', encoding="utf-8")


# ---------------------------------------------------------------------------
# parse / parse_model
# ---------------------------------------------------------------------------


class TestParse:
    def test_full_example(self, tmp_path: Path) -> None:
        path = tmp_path / "tools/codemods/adr-042-rename.py"
        _write_codemod(
            path,
            """
ADR: 42
Description: Rename scieasy.X.foo to scieasy.X.bar per ADR-042 §N
Affects:
  - scieasy.X.foo (renamed to scieasy.X.bar)
Tests:
  - tests/codemods/test_adr_042_rename.py
""",
        )
        raw = parse(path)
        assert raw["adr"] == 42
        assert "Rename" in raw["description"]
        assert raw["affects"] == ["scieasy.X.foo (renamed to scieasy.X.bar)"]
        assert raw["tests"] == ["tests/codemods/test_adr_042_rename.py"]

    def test_parse_model_returns_typed(self, tmp_path: Path) -> None:
        path = tmp_path / "tools/codemods/adr-100-x.py"
        _write_codemod(
            path,
            """
ADR: 100
Description: x
Affects:
  - foo
""",
        )
        meta = parse_model(path)
        assert isinstance(meta, CodemodMeta)
        assert meta.adr == 100

    def test_missing_docstring_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "tools/codemods/adr-1-x.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no module-level docstring"):
            parse(path)

    def test_missing_adr_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "tools/codemods/adr-1-x.py"
        _write_codemod(path, "\nDescription: x\n")
        with pytest.raises(ValueError, match="`ADR:`"):
            parse(path)

    def test_missing_description_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "tools/codemods/adr-1-x.py"
        _write_codemod(path, "\nADR: 1\n")
        with pytest.raises(ValueError, match="`Description:`"):
            parse(path)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            parse(tmp_path / "does-not-exist.py")

    def test_syntax_error_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "tools/codemods/adr-1-x.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("this is not python !@#$\ndef (\n", encoding="utf-8")
        with pytest.raises(ValueError, match="failed to parse"):
            parse(path)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


class TestCheck:
    def test_empty_repo_returns_no_findings(self, tmp_path: Path) -> None:
        assert check(tmp_path) == []

    def test_valid_codemod_no_findings(self, tmp_path: Path) -> None:
        codemod_path = tmp_path / "tools/codemods/adr-42-rename.py"
        _write_codemod(
            codemod_path,
            """
ADR: 42
Description: Rename foo to bar
Affects:
  - scieasy.X.foo
Tests:
  - tests/codemods/test_adr_042_rename.py
""",
        )
        # Create the referenced test file.
        test_file = tmp_path / "tests/codemods/test_adr_042_rename.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_x(): pass\n", encoding="utf-8")
        findings = check(tmp_path)
        assert findings == []

    def test_missing_metadata_error(self, tmp_path: Path) -> None:
        codemod_path = tmp_path / "tools/codemods/adr-42-x.py"
        codemod_path.parent.mkdir(parents=True, exist_ok=True)
        codemod_path.write_text("pass\n", encoding="utf-8")
        findings = check(tmp_path)
        assert any(f.rule_id == "codemod-lint.missing-metadata" and f.severity == Severity.ERROR for f in findings)

    def test_malformed_field_error(self, tmp_path: Path) -> None:
        codemod_path = tmp_path / "tools/codemods/adr-42-x.py"
        _write_codemod(codemod_path, "\nDescription: x\n")  # no ADR:
        findings = check(tmp_path)
        assert any(f.rule_id == "codemod-lint.malformed-field" for f in findings)

    def test_filename_adr_mismatch_warning(self, tmp_path: Path) -> None:
        codemod_path = tmp_path / "tools/codemods/adr-42-x.py"
        _write_codemod(
            codemod_path,
            """
ADR: 999
Description: x
Tests:
  - tests/foo.py
""",
        )
        (tmp_path / "tests/foo.py").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "tests/foo.py").write_text("pass\n", encoding="utf-8")
        findings = check(tmp_path)
        assert any(f.rule_id == "codemod-lint.adr-ref-mismatch" for f in findings)

    def test_filename_format_warning(self, tmp_path: Path) -> None:
        # Filename doesn't match adr-NNN-<slug>.
        codemod_path = tmp_path / "tools/codemods/adr-bad.py"
        _write_codemod(
            codemod_path,
            """
ADR: 1
Description: x
Tests:
  - tests/foo.py
""",
        )
        (tmp_path / "tests/foo.py").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "tests/foo.py").write_text("pass\n", encoding="utf-8")
        findings = check(tmp_path)
        # adr-bad.py does NOT match adr-NNN-<slug>.py pattern, but the
        # check() glob is `adr-*.py` which DOES match adr-bad.py, so a
        # warning is emitted.
        assert any(f.rule_id == "codemod-lint.filename-format" for f in findings)

    def test_missing_tests_block_warning(self, tmp_path: Path) -> None:
        codemod_path = tmp_path / "tools/codemods/adr-42-x.py"
        _write_codemod(
            codemod_path,
            """
ADR: 42
Description: x
""",
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "codemod-lint.missing-tests" and f.severity == Severity.WARNING for f in findings)

    def test_broken_test_ref_warning(self, tmp_path: Path) -> None:
        codemod_path = tmp_path / "tools/codemods/adr-42-x.py"
        _write_codemod(
            codemod_path,
            """
ADR: 42
Description: x
Tests:
  - tests/codemods/does_not_exist.py
""",
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "codemod-lint.broken-test-ref" for f in findings)

    def test_invalid_schema_emits_violation(self, tmp_path: Path) -> None:
        # ADR out of bounds (>9999) — schema rejects.
        codemod_path = tmp_path / "tools/codemods/adr-10042-x.py"
        _write_codemod(
            codemod_path,
            """
ADR: 10042
Description: x
""",
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "codemod-lint.schema-violation" for f in findings)

    def test_default_repo_root_uses_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        assert check() == []
