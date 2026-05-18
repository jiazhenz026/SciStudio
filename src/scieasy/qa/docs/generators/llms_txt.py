"""llms.txt generator — ADR-044 §10.3 (TC-1D.5).

Generates an OpenClaw-pattern ``llms.txt`` index for AI consumption by
walking source toctrees BEFORE ``sphinx-build`` runs (generation-order
note, ADR-044 §10.3 audit P1.3 fix).

The output file carries ``generation: auto`` frontmatter and a
``source.last_generated_sha`` field.  ``auto_generated_lint.py``
(ADR-044 §11.5) refuses hand-edits by comparing mtime vs this sha field.

Entry-point signature per ADR-044 §11.5::

    def generate(docs_root: Path, output: Path) -> None: ...

The extended signature used internally also accepts ``source_sha`` so
the Sphinx builder callback can pass the HEAD sha.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

PROJECT_BLURB = (
    "SciEasy — AI-native, inclusive workflow runtime for multimodal "
    "scientific data.  Supports Python, R, Julia, GUI tools, and AI agents "
    "in the same typed workflow graph."
)


def generate(
    docs_root: Path,
    output: Path,
    source_sha: str = "unknown",
) -> None:
    """Walk source toctrees and emit OpenClaw-pattern ``llms.txt``.

    The function walks ``*.rst`` and ``*.md`` files under *docs_root*,
    discovers toctree headings, and produces a hierarchical index at
    *output* suitable for LLM consumption.

    Runs BEFORE ``sphinx-build``; uses source toctrees not rendered HTML
    so that cross-reference resolution is NOT required.  A second pass
    after sphinx-build (for resolved anchors) may be added in Phase 5.

    Parameters
    ----------
    docs_root:
        Root of the Sphinx source directory (the directory containing
        ``conf.py``).
    output:
        Path to write the generated ``llms.txt`` file.  Parent
        directories are created if needed.
    source_sha:
        Git SHA of the source at generation time; recorded in the
        ``source.last_generated_sha`` field so ``auto_generated_lint``
        can detect hand-edits.
    """
    output.parent.mkdir(parents=True, exist_ok=True)

    toctree_entries = list(_walk_toctrees(docs_root))

    lines: list[str] = []

    # --- OpenClaw frontmatter block ---
    lines.append("---")
    lines.append("generation: auto")
    lines.append(f"source.last_generated_sha: {source_sha}")
    lines.append("---")
    lines.append("")

    # --- Project blurb ---
    lines.append(f"# {_read_project_title(docs_root)}")
    lines.append("")
    lines.append(f"> {PROJECT_BLURB}")
    lines.append("")

    # --- Toctree section ---
    lines.append("## Table of Contents")
    lines.append("")
    for entry in toctree_entries:
        indent = "  " * entry["depth"]
        title = entry["title"]
        path = entry["path"]
        lines.append(f"{indent}- [{title}]({path})")
    lines.append("")

    output.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _read_project_title(docs_root: Path) -> str:
    """Return the project title from the index file, or a sensible default."""
    for fname in ("index.rst", "index.md"):
        candidate = docs_root / fname
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            # RST: first non-empty line before a ====== underline
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("..") and not line.startswith("#"):
                    return line
            # Markdown: first # heading
            m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            if m:
                return m.group(1).strip()
    return "SciEasy"


def _walk_toctrees(docs_root: Path) -> Generator[dict, None, None]:
    """Yield toctree entries discovered from source files.

    Walks RST ``.. toctree::`` directives and MD ``(toc)`` fences, then
    resolves each listed path to a title + file-system path.  The walk
    is breadth-first starting from the root ``index.rst`` / ``index.md``.
    """
    visited: set[Path] = set()
    queue: list[tuple[Path, int]] = []

    root_index = _find_root_index(docs_root)
    if root_index is None:
        return

    queue.append((root_index, 0))

    while queue:
        current_path, depth = queue.pop(0)
        resolved = current_path.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)

        title = _extract_title(current_path)
        rel = _relative_url(current_path, docs_root)
        yield {"title": title, "path": rel, "depth": depth}

        for child_ref in _parse_toctree_refs(current_path):
            child_path = _resolve_ref(child_ref, current_path.parent, docs_root)
            if child_path and child_path.exists():
                queue.append((child_path, depth + 1))


def _find_root_index(docs_root: Path) -> Path | None:
    for fname in ("index.rst", "index.md"):
        p = docs_root / fname
        if p.exists():
            return p
    return None


def _extract_title(path: Path) -> str:
    """Extract the first heading from an RST or MD file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem
    # Markdown: first # heading
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # RST: title with underline (=, -, ~, ^, ...)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if i + 1 < len(lines):
            underline = lines[i + 1].strip()
            if underline and len(underline) >= len(line_stripped) and all(c in "=-~^#*+`" for c in underline):
                return line_stripped
    return path.stem


def _parse_toctree_refs(path: Path) -> list[str]:
    """Return child refs from toctree directives in *path*."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    refs: list[str] = []
    # RST: .. toctree:: block
    in_toctree = False
    toctree_indent: int | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if re.match(r"\.\.\s+toctree::", line):
            in_toctree = True
            toctree_indent = None
            continue
        if in_toctree:
            if not stripped:
                continue  # blank line inside toctree is OK
            if toctree_indent is None and stripped.startswith(":"):
                continue  # option line like :maxdepth:
            if toctree_indent is None:
                toctree_indent = indent
            if indent < (toctree_indent or 0):
                in_toctree = False
                toctree_indent = None
            elif not stripped.startswith(":"):
                # strip caption: prefix
                ref = re.sub(r"^[^<]+<(.+)>$", r"\1", stripped)
                refs.append(ref.strip())
    # MD: ```{toctree} blocks (MyST)
    in_myst_toc = False
    for line in text.splitlines():
        if re.match(r"```\{toctree\}", line):
            in_myst_toc = True
            continue
        if in_myst_toc:
            if line.strip() == "```":
                in_myst_toc = False
                continue
            if line.strip() and not line.strip().startswith(":"):
                refs.append(line.strip())
    return refs


def _resolve_ref(ref: str, base_dir: Path, docs_root: Path) -> Path | None:
    """Resolve a toctree ref string to an absolute Path."""
    for ext in (".rst", ".md", ""):
        candidate = base_dir / (ref + ext)
        if candidate.exists():
            return candidate
    # Try relative to docs_root
    for ext in (".rst", ".md", ""):
        candidate = docs_root / (ref + ext)
        if candidate.exists():
            return candidate
    return None


def _relative_url(path: Path, docs_root: Path) -> str:
    """Return a URL-style relative path from *docs_root*."""
    try:
        rel = path.relative_to(docs_root)
        return str(rel).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
