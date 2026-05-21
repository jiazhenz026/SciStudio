"""Tests for the vulture dead-code child report (#1340)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scistudio.qa.audit import vulture_audit
from scistudio.qa.audit.vulture_audit import _load_pyproject_vulture_config, check, main
from scistudio.qa.schemas.report import AuditStatus, Severity


def test_check_reports_skipped_when_vulture_not_importable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vulture_audit, "_vulture_available", lambda: False)

    report = check(tmp_path)

    assert report.status == AuditStatus.SKIPPED
    assert not report.blocks_merge
    assert [finding.rule_id for finding in report.findings] == ["vulture.unavailable"]
    assert report.findings[0].severity == Severity.INFO
    assert report.summary["vulture_available"] is False


def test_check_returns_pass_with_zero_findings_when_no_targets_resolve(tmp_path: Path) -> None:
    report = check(tmp_path, paths=("nonexistent_subdir",), allowlist=None)

    assert report.status == AuditStatus.PASS
    assert not report.blocks_merge
    assert report.findings == []
    assert report.summary["targets_resolved"] == 0
    assert report.summary["vulture_available"] is True


def test_check_emits_warning_findings_for_dead_code(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "dead.py").write_text(
        textwrap.dedent(
            """
            def never_called():
                return 42

            UNUSED_CONSTANT = 7
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    report = check(tmp_path, paths=("pkg",), allowlist=None, min_confidence=60)

    assert report.status == AuditStatus.PASS
    assert not report.blocks_merge, "vulture child report must never block merge in v1 (#1340)"
    assert report.findings, "expected at least one dead-code finding for never_called or UNUSED_CONSTANT"
    for finding in report.findings:
        assert finding.severity == Severity.WARNING
        assert finding.rule_id == "vulture.dead-code"
        assert "confidence" in finding.evidence
    assert report.summary["total_findings"] == len(report.findings)
    assert report.summary["targets_resolved"] == 1


def test_check_uses_allowlist_to_suppress_known_intentional_names(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "lib.py").write_text(
        "def keep_me_callback():\n    return 1\n",
        encoding="utf-8",
    )
    allowlist = tmp_path / "vulture_allowlist.py"
    allowlist.write_text(
        textwrap.dedent(
            """
            _ = None
            _.keep_me_callback  # noqa: F821
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    report = check(tmp_path, paths=("pkg",), allowlist=allowlist, min_confidence=60)

    assert report.status == AuditStatus.PASS
    assert not any("keep_me_callback" in finding.message for finding in report.findings)
    assert report.summary["allowlist"] == "vulture_allowlist.py"


def test_main_returns_zero_when_only_warnings_are_emitted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "dead.py").write_text("def unused():\n    return 1\n", encoding="utf-8")

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--path",
            "pkg",
            "--min-confidence",
            "60",
            "--format",
            "text",
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0, "vulture child report must not exit non-zero on WARNING-only findings"
    assert "vulture:" in out


def test_load_pyproject_vulture_config_returns_empty_when_pyproject_absent(tmp_path: Path) -> None:
    assert _load_pyproject_vulture_config(tmp_path) == {}


def test_load_pyproject_vulture_config_returns_tool_vulture_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [tool.vulture]
            paths = ["src/foo"]
            ignore_decorators = ["@app.*", "@router.*"]
            ignore_names = ["dummy_keep"]
            exclude = ["src/foo/static/**"]
            min_confidence = 80
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    config = _load_pyproject_vulture_config(tmp_path)

    assert config["ignore_decorators"] == ["@app.*", "@router.*"]
    assert config["ignore_names"] == ["dummy_keep"]
    assert config["exclude"] == ["src/foo/static/**"]


def test_load_pyproject_vulture_config_tolerates_malformed_toml(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.vulture\nbroken = ", encoding="utf-8")

    assert _load_pyproject_vulture_config(tmp_path) == {}


def test_check_honors_ignore_decorators_from_pyproject(tmp_path: Path) -> None:
    """#1340 P2: ``ignore_decorators`` in ``[tool.vulture]`` must reach the
    Vulture instance. Without this wiring, FastAPI ``@app.get`` / ``@router.*``
    handlers would surface as 'unused function' false positives.
    """

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "routes.py").write_text(
        textwrap.dedent(
            """
            def app_get(path):
                def decorator(fn):
                    return fn
                return decorator

            class App:
                get = staticmethod(app_get)

            app = App()

            @app.get("/health")
            def health_check():
                return {"ok": True}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    # pyproject WITHOUT ignore_decorators: vulture should flag health_check.
    (tmp_path / "pyproject.toml").write_text(
        "[tool.vulture]\nmin_confidence = 60\n",
        encoding="utf-8",
    )
    baseline = check(tmp_path, paths=("pkg",), allowlist=None, min_confidence=60)
    baseline_messages = [f.message for f in baseline.findings]
    assert any("health_check" in m for m in baseline_messages), (
        "sanity check: with no ignore_decorators, vulture should report the decorated function"
    )

    # Now with ignore_decorators: health_check must be suppressed.
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [tool.vulture]
            ignore_decorators = ["@app.*"]
            min_confidence = 60
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    honored = check(tmp_path, paths=("pkg",), allowlist=None, min_confidence=60)

    assert honored.status == AuditStatus.PASS
    assert not any("health_check" in f.message for f in honored.findings), (
        "ignore_decorators from pyproject.toml must reach Vulture()"
    )
    assert honored.summary["pyproject_config_honored"]["ignore_decorators"] == ["@app.*"]


def test_check_honors_exclude_from_pyproject(tmp_path: Path) -> None:
    """``exclude`` in ``[tool.vulture]`` must reach ``scavenge(exclude=...)``."""

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "kept.py").write_text("def kept_dead():\n    return 1\n", encoding="utf-8")
    skip = pkg / "skip"
    skip.mkdir()
    (skip / "ignored.py").write_text("def excluded_dead():\n    return 2\n", encoding="utf-8")

    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [tool.vulture]
            exclude = ["*/skip/*"]
            min_confidence = 60
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    report = check(tmp_path, paths=("pkg",), allowlist=None, min_confidence=60)

    messages = [f.message for f in report.findings]
    assert any("kept_dead" in m for m in messages), "non-excluded dead code must still be reported"
    assert not any("excluded_dead" in m for m in messages), "exclude pattern from pyproject.toml must reach scavenge()"
    assert report.summary["pyproject_config_honored"]["exclude"] == ["*/skip/*"]


def test_main_returns_zero_when_vulture_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(vulture_audit, "_vulture_available", lambda: False)

    exit_code = main(["--repo-root", str(tmp_path), "--format", "text"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "skipped" in out
