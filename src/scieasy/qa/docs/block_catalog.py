"""Generate block catalog documentation from discovered block-like modules."""

from __future__ import annotations

import ast
from pathlib import Path

from scieasy.qa.docs._helpers import build_result, join_markdown_lines

MARKER = "<!-- generated-by: block_catalog -->"


def _list_blocks(package_root: Path) -> list[str]:
    items: list[str] = []
    for py_file in package_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name.endswith("Block"):
                rel = py_file.relative_to(package_root.parent).as_posix()
                module_name = rel[:-3].replace("/", ".")
                items.append(f"{module_name}:{node.name}")
    return sorted(set(items))


def generate(
    repo_root: Path,
    *,
    output_dir: Path = Path("docs/user/reference/blocks"),
) -> list:
    blocks_root = repo_root / "src/scieasy/blocks"
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = [MARKER, "# Block Catalog", ""]
    models = _list_blocks(blocks_root) if blocks_root.exists() else []
    if models:
        for item in models:
            lines.append(f"- {item}")
    else:
        lines.append("No block classes discovered.")
    output_path = output_dir / "blocks.md"
    return [
        build_result(
            generator_id="block_catalog",
            repo_root=repo_root,
            target_path=output_path,
            source_paths=[Path("src/scieasy/blocks")],
            content=join_markdown_lines(lines),
            marker=MARKER,
        )
    ]
