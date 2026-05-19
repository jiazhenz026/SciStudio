"""Generate ``docs/user/llms.txt``."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.docs._helpers import build_result

MARKER = "<!-- generated-by: llms_txt -->"
DEFAULT_OUTPUT = Path("docs/user/llms.txt")


def _iter_markdown_paths(repo_root: Path) -> list[Path]:
    base = repo_root / "docs"
    if not base.exists():
        return []
    return sorted(
        path for path in base.rglob("*.md") if path.name != "generated-docs.yaml" and "site-packages" not in path.as_posix()
    )


def generate(
    repo_root: Path,
    *,
    output_path: Path = DEFAULT_OUTPUT,
) -> any:
    items = [f"- {path.relative_to(repo_root)}" for path in _iter_markdown_paths(repo_root)]
    content = "\n".join([MARKER, "# SciEasy Documentation Index", ""] + items) + "\n"
    return build_result(
        generator_id="llms_txt",
        repo_root=repo_root,
        target_path=output_path,
        source_paths=[Path("docs")],
        content=content,
        marker=MARKER,
    )
