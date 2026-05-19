from pathlib import Path

from scieasy.qa.docs import generate_reference
from scieasy.qa.docs import entry_point_catalog


def test_docs_generate_reference_collect_results_is_deterministic(tmp_path: Path) -> None:
    _docs = tmp_path / "docs"
    _docs.mkdir(parents=True, exist_ok=True)
    (_docs / "guide.md").write_text("# One\n", encoding="utf-8")

    first = generate_reference.collect_results(
        repo_root=tmp_path,
        generators=("llms_txt",),
    )
    second = generate_reference.collect_results(
        repo_root=tmp_path,
        generators=("llms_txt",),
    )

    assert len(first) == 1
    assert first[0].content == second[0].content
    assert first[0].manifest_entry["content_sha256"] == second[0].manifest_entry["content_sha256"]


def test_entry_point_catalog_uses_group_prefix(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "test"
version = "0.0.1"

[project.entry-points."scieasy.cli"]
foo = "pkg:bar"

[project.entry-points."other.group"]
baz = "pkg:baz"
""",
        encoding="utf-8",
    )

    out = tmp_path / "docs/user/reference/entry-points.md"
    result = entry_point_catalog.generate(tmp_path, output_path=out, group_prefix="scieasy")
    assert result.target_path.endswith("entry-points.md")
    assert "foo" in result.content
    again = entry_point_catalog.generate(tmp_path, output_path=out, group_prefix="scieasy")
    assert result.content == again.content


def test_generate_reference_can_run_multiple_generators(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "test"
version = "0.0.1"

[project.entry-points."scieasy.cli"]
foo = "pkg:bar"
""",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs/sample.md").write_text("# Sample\n", encoding="utf-8")

    results = generate_reference.collect_results(
        repo_root=tmp_path,
        generators=("llms_txt", "entry_point_catalog"),
    )
    assert {item.generator_id for item in results} == {"llms_txt", "entry_point_catalog"}
