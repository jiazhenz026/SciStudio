"""OpenAPI reference generator — ADR-044 §10.3 (TC-1D.6).

Emits ``docs/user/reference/server-api.md`` — an ``auto_generated_lint``-
compliant skeleton with a ``<!-- generated -->`` marker and
``generation: auto`` frontmatter.  The actual OpenAPI content is rendered
at Sphinx-build time by ``sphinxcontrib-openapi`` (configured in
``docs/sphinx/conf.py``); this generator's job is to ensure the file
exists with correct frontmatter and the ``openapi::`` directive.

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

<!-- generated — do not hand-edit; content is emitted by sphinxcontrib-openapi at build time -->

# Server API Reference

```{{eval-rst}}
.. openapi:: ../../openapi.json
   :group:
```

.. note::
   The OpenAPI specification is exported from the FastAPI application via
   ``app.openapi()``.  Run ``python -m scieasy.api.export_openapi`` to
   regenerate ``openapi.json`` before building the docs.
"""

# TODO(#1184): Phase 5 — add a pre-build step that calls `app.openapi()`
#   and writes openapi.json automatically, so the docs are always in sync.
#   Out of scope per ADR-044 §10.3 (generator emits skeleton; full
#   integration deferred to Phase 5 docs CI).
#   Followup: open as part of Phase 5 docs CI work.


def generate(
    docs_root: Path,
    output: Path,
    source_sha: str = "unknown",
) -> None:
    """Emit ``docs/user/reference/server-api.md`` with openapi directive.

    The file contains a MyST ``eval-rst`` fence that invokes the
    ``sphinxcontrib-openapi`` ``.. openapi::`` directive.  Sphinx renders
    the full API documentation at build time; this generator only ensures
    the skeleton exists with valid ``generation: auto`` frontmatter.

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
