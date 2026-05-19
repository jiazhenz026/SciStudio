"""Generate runner catalog from configured and in-repo runners."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.docs._helpers import build_result, join_markdown_lines, parse_pyproject_groups

MARKER = "<!-- generated-by: runner_catalog -->"


def generate(
    repo_root: Path,
    *,
    output_dir: Path = Path("docs/user/reference/runners"),
) -> list:
    output_dir.mkdir(parents=True, exist_ok=True)
    entry_points = parse_pyproject_groups(repo_root)
    runners = entry_points.get("scieasy.runners", {}) if isinstance(entry_points, dict) else {}
    lines = [MARKER, "# Runner Catalog", ""]
    if isinstance(runners, dict) and runners:
        for name, target in sorted(runners.items()):
            lines.append(f"- `{name}`: `{target}`")
    else:
        lines.append("No runners discovered from entry-points.")
    output = output_dir / "runners.md"
    return [
        build_result(
            generator_id="runner_catalog",
            repo_root=repo_root,
            target_path=output,
            source_paths=[Path("pyproject.toml")],
            content=join_markdown_lines(lines),
            marker=MARKER,
        )
    ]
