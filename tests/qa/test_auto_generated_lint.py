import hashlib
from pathlib import Path

import pytest

from scieasy.qa.audit import auto_generated_lint
from scieasy.qa.audit.auto_generated_lint import check
from scieasy.qa.docs._helpers import build_result


def _fake_results(path: Path, target: str, content: str, source_sha: str):
    result = build_result(
        generator_id="cli_reference",
        repo_root=path,
        target_path=Path(target),
        source_paths=[Path("src/scieasy/cli.py")],
        content=content,
        marker="<!-- generated-by: cli_reference -->",
    )
    # force deterministic source sha for this test
    result.manifest_entry["source_sha"] = source_sha
    return result


def test_auto_generated_lint_clean_when_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generated = tmp_path / "docs/user/reference/cli.md"
    generated.parent.mkdir(parents=True, exist_ok=True)

    result = _fake_results(tmp_path, "docs/user/reference/cli.md", "# cli\n", source_sha="source-a")
    generated.write_text(result.content, encoding="utf-8")

    manifest_path = tmp_path / "docs/user/reference/generated-docs.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        f"""
schema_version: "1"
entries:
  - target_path: docs/user/reference/cli.md
    generator_id: cli_reference
    source_paths: [src/scieasy/cli.py]
    source_sha: "{result.manifest_entry['source_sha']}"
    content_sha256: "{result.manifest_entry['content_sha256']}"
    marker: "<!-- generated-by: cli_reference -->"
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(auto_generated_lint, "collect_results", lambda **_: [result])
    report = check(repo_root=tmp_path, manifest_path=manifest_path.relative_to(tmp_path))
    assert report.status == "passed"
    assert report.findings == []


def test_auto_generated_lint_reports_stale_or_edited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generated = tmp_path / "docs/user/reference/cli.md"
    generated.parent.mkdir(parents=True, exist_ok=True)

    result = _fake_results(tmp_path, "docs/user/reference/cli.md", "# cli\n", source_sha="source-new")
    generated.write_text("# cli\nmanually edited", encoding="utf-8")

    manifest_path = tmp_path / "docs/user/reference/generated-docs.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        f"""
schema_version: "1"
entries:
  - target_path: docs/user/reference/cli.md
    generator_id: cli_reference
    source_paths: [src/scieasy/cli.py]
    source_sha: "source-old"
    content_sha256: "{hashlib.sha256('# cli\\n'.encode('utf-8')).hexdigest()}"
    marker: "<!-- generated-by: cli_reference -->"
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(auto_generated_lint, "collect_results", lambda **_: [result])
    report = check(repo_root=tmp_path, manifest_path=manifest_path.relative_to(tmp_path))
    assert report.status == "failed"
    assert any(finding.id == "generated-doc-stale" for finding in report.findings)
    assert any(finding.id in {"generated-doc-stale", "generated-doc-content"} for finding in report.findings)


def test_auto_generated_lint_reports_missing_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = tmp_path / "docs/user/reference/generated-docs.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("schema_version: \"1\"\nentries:\n", encoding="utf-8")

    result = _fake_results(tmp_path, "docs/user/reference/cli.md", "# cli\n", source_sha="source-a")
    monkeypatch.setattr(auto_generated_lint, "collect_results", lambda **_: [result])
    report = check(repo_root=tmp_path, manifest_path=manifest_path.relative_to(tmp_path))
    assert report.status == "failed"
    assert any("untracked" in finding.id or "missing" in finding.id for finding in report.findings)
