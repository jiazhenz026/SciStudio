"""Generate entry-point catalog from ``pyproject.toml``."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.docs._helpers import build_result, join_markdown_lines, parse_pyproject_groups
from scieasy.qa.docs._models import GeneratorResult

MARKER = "<!-- generated-by: entry_point_catalog -->"
DEFAULT_TARGET_PATH = Path("docs/user/reference/entry-points.md")


def generate(
    repo_root: Path,
    *,
    output_path: Path = DEFAULT_TARGET_PATH,
    group_prefix: str = "scieasy",
) -> GeneratorResult:
    entry_points = parse_pyproject_groups(repo_root)
    lines = [MARKER, "# Entry Points", ""]
    if not entry_points:
        lines.append(f"No entry-points available in {repo_root / 'pyproject.toml'}.")
    else:
        for group, entries in sorted(entry_points.items()):
            if not isinstance(entries, dict) or not group.startswith(group_prefix):
                continue
            lines.append(f"## {group}")
            for name, target in sorted(entries.items()):
                lines.append(f"- `{name}`: `{target}`")
            lines.append("")
    content = join_markdown_lines(lines)
    return build_result(
        generator_id="entry_point_catalog",
        repo_root=repo_root,
        target_path=output_path,
        source_paths=[Path("pyproject.toml")],
        content=content,
        marker=MARKER,
    )
