"""CLI reference generator — ADR-044 §10.3 (TC-1D.6).

Emits ``docs/user/reference/cli.md`` — an ``auto_generated_lint``-
compliant skeleton with a ``<!-- generated -->`` marker and
``generation: auto`` frontmatter.  The actual CLI content is rendered at
Sphinx-build time by the ``sphinx-click`` extension (configured in
``docs/sphinx/conf.py``); this generator's job is to ensure the file
exists with correct frontmatter so ``auto_generated_lint`` (ADR-044
§11.5) can validate it.

Entry-point signature per ADR-044 §11.5::

    def generate(docs_root: Path, output: Path) -> None: ...
"""

from __future__ import annotations

from pathlib import Path

_CONTENT_TEMPLATE = """\
---
generation: auto
source.last_generated_sha: {source_sha}
---

<!-- generated — do not hand-edit; content is emitted by sphinx-click at build time -->

# CLI Reference

```{{eval-rst}}
.. click:: scieasy.cli.main:app
   :prog: scieasy
   :nested: full
```
"""


def generate(
    docs_root: Path,
    output: Path,
    source_sha: str = "unknown",
) -> None:
    """Emit ``docs/user/reference/cli.md`` with sphinx-click directive.

    The file contains a MyST ``eval-rst`` fence that invokes the
    ``sphinx-click`` ``.. click::`` directive.  Sphinx renders the full
    CLI documentation at build time; this generator only ensures the
    skeleton exists with valid ``generation: auto`` frontmatter.

    Parameters
    ----------
    docs_root:
        Root of the Sphinx source directory (unused here but kept for
        API symmetry).
    output:
        Destination file path.  Parent directories are created if needed.
    source_sha:
        Git SHA recorded in the frontmatter for drift detection.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_CONTENT_TEMPLATE.format(source_sha=source_sha), encoding="utf-8")
