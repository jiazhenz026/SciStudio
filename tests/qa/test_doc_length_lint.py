from pathlib import Path

from scieasy.qa.audit import doc_length_lint


def test_doc_length_lint_flags_long_hand_written_doc(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "contributing" / "guide.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Guide\n\n" + "\n".join(f"Line {index} with enough words to count quickly." for index in range(130)),
        encoding="utf-8",
    )

    report = doc_length_lint.check([target], repo_root=tmp_path)
    assert report.status == "failed"
    assert any(finding.id == "doc-length-lines" for finding in report.findings)


def test_doc_length_lint_exempts_generated_docs(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "user" / "reference" / "cli.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "<!-- generated-by: cli_reference -->\n# Generated\n\n"
        + "\n".join(f"Long line {index} with enough words to count quickly." for index in range(130)),
        encoding="utf-8",
    )
    manifest = tmp_path / "docs/user/reference/generated-docs.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        "schema_version: \"1\"\nentries:\n  - target_path: docs/user/reference/cli.md\n    generator_id: cli_reference\n    source_paths: []\n    source_sha: \"x\"\n    content_sha256: \"\"\n    marker: \"<!-- generated-by: cli_reference -->\"\n",
        encoding="utf-8",
    )

    report = doc_length_lint.check([target], repo_root=tmp_path)
    assert report.status == "passed"
    assert report.findings == []


def test_doc_length_lint_ignores_non_target_docs(tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("# Root readme\ncontent line", encoding="utf-8")
    report = doc_length_lint.check([target], repo_root=tmp_path)
    assert report.status == "passed"
