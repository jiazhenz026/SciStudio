"""Entry-point catalog generator — ADR-044 §10.3 (TC-1D.6).

Emits ``docs/user/reference/entry-points.md`` by walking
``importlib.metadata.entry_points()`` for all SciEasy groups
(``scieasy.blocks``, ``scieasy.runners``, ``scieasy.types``).

Entry-point signature per ADR-044 §11.5::

    def generate(docs_root: Path, output: Path) -> None: ...
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

# All known SciEasy entry-point groups.
_SCIEASY_GROUPS = [
    "scieasy.blocks",
    "scieasy.runners",
    "scieasy.types",
]

_FRONTMATTER_TEMPLATE = """\
---
generation: auto
source.last_generated_sha: {source_sha}
---

<!-- generated — do not hand-edit; re-run `python -m scieasy.qa.docs.generators.entry_point_catalog` -->
"""

_TABLE_HEADER = """\
| Entry-point name | Value (module:class) | Group |
|---|---|---|
"""


def generate(
    docs_root: Path,
    output: Path,
    source_sha: str = "unknown",
) -> None:
    """Emit ``docs/user/reference/entry-points.md``.

    Walks ``importlib.metadata.entry_points()`` for all SciEasy groups
    and writes an RST table (rendered as GitHub-flavoured Markdown for
    MyST compatibility) to *output*.

    Parameters
    ----------
    docs_root:
        Root of the Sphinx source directory (unused here but kept for
        API symmetry with the other generators).
    output:
        Destination file path.  Parent directories are created if needed.
    source_sha:
        Git SHA recorded in the frontmatter for drift detection.
    """
    output.parent.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, str]] = _collect_entry_points()

    lines: list[str] = [_FRONTMATTER_TEMPLATE.format(source_sha=source_sha)]
    lines.append("# Entry-Point Catalog\n")
    lines.append(
        "All SciEasy extension points registered via `pyproject.toml` "
        "[entry-points](https://packaging.python.org/en/latest/specifications/pyproject-toml/#entry-points).\n"
    )

    if rows:
        lines.append(_TABLE_HEADER)
        for name, value, group in rows:
            lines.append(f"| `{name}` | `{value}` | `{group}` |")
        lines.append("")
    else:
        lines.append("*No entry-points registered.*\n")

    output.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_entry_points() -> list[tuple[str, str, str]]:
    """Return (name, value, group) tuples for all SciEasy entry-points."""
    rows: list[tuple[str, str, str]] = []
    for group in _SCIEASY_GROUPS:
        try:
            eps = importlib.metadata.entry_points(group=group)
        except Exception:
            continue
        for ep in eps:
            rows.append((ep.name, ep.value, group))
    rows.sort(key=lambda r: (r[2], r[0]))
    return rows
