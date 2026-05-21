"""Scaffold a new SciStudio block package from templates.

Reads ``.tpl`` files from ``cli/templates/block_package/``, performs
placeholder substitution, and writes the resulting project structure
to disk.  See ADR-026 Task 3.2/3.3.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Location of the template files, relative to this module.
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "block_package"


def _to_module_name(package_name: str) -> str:
    """Convert a package name like ``scistudio-blocks-srs`` to ``scistudio_blocks_srs``."""
    return re.sub(r"[^a-zA-Z0-9]", "_", package_name)


def _to_display_name(package_name: str) -> str:
    """Derive a human-readable display name from the package name.

    ``scistudio-blocks-srs`` becomes ``Scistudio Blocks Srs``.
    """
    return package_name.replace("-", " ").replace("_", " ").title()


def _to_entry_point_name(package_name: str) -> str:
    """Derive an entry-point key from the package name.

    ``scistudio-blocks-srs`` becomes ``scistudio_blocks_srs``.
    """
    return _to_module_name(package_name)


def render_template(template_text: str, context: dict[str, str]) -> str:
    """Replace ``{placeholder}`` tokens in *template_text* with values from *context*.

    Only replaces keys that exist in *context*.  Literal braces that
    should survive (e.g. TOML inline tables ``{text = "MIT"}``) are
    escaped in the templates as ``{{...}}`` and restored here.
    """
    # First, protect escaped braces by replacing {{ / }} with sentinel.
    sentinel_open = "\x00LBRACE\x00"
    sentinel_close = "\x00RBRACE\x00"
    text = template_text.replace("{{", sentinel_open).replace("}}", sentinel_close)

    # Perform substitution.
    for key, value in context.items():
        text = text.replace(f"{{{key}}}", value)

    # Restore literal braces.
    text = text.replace(sentinel_open, "{").replace(sentinel_close, "}")
    return text


def scaffold_block_package(
    output_dir: Path,
    package_name: str,
    *,
    author: str = "",
    description: str = "",
    display_name: str = "",
) -> dict[str, Any]:
    """Create a new block package directory from templates.

    Args:
        output_dir: Parent directory where the package folder will be created.
        package_name: Name of the package (e.g. ``scistudio-blocks-srs``).
        author: Author name for metadata.
        description: One-line package description.
        display_name: Human-readable name (derived from *package_name* if empty).

    Returns:
        A dict with ``"root"`` (Path to created package) and ``"files"``
        (list of relative file paths created).

    Raises:
        FileExistsError: If the target directory already exists.
    """
    module_name = _to_module_name(package_name)
    if not display_name:
        display_name = _to_display_name(package_name)
    if not description:
        description = f"SciStudio block package: {display_name}"

    context: dict[str, str] = {
        "package_name": package_name,
        "module_name": module_name,
        "display_name": display_name,
        "author": author,
        "description": description,
        "entry_point_name": _to_entry_point_name(package_name),
    }

    root = output_dir / package_name
    if root.exists():
        raise FileExistsError(f"Directory already exists: {root}")

    # Define the mapping from template file -> output path.
    file_map: dict[str, str] = {
        "pyproject.toml.tpl": "pyproject.toml",
        "__init__.py.tpl": f"src/{module_name}/__init__.py",
        "blocks.py.tpl": f"src/{module_name}/blocks.py",
        "test_block.py.tpl": "tests/test_blocks.py",
        "README.md.tpl": "README.md",
    }

    created_files: list[str] = []

    for tpl_name, rel_path in file_map.items():
        tpl_path = _TEMPLATE_DIR / tpl_name
        if not tpl_path.exists():
            continue

        content = render_template(tpl_path.read_text(encoding="utf-8"), context)

        dest = root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        created_files.append(rel_path)

    return {"root": root, "files": created_files}
