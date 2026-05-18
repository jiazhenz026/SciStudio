"""llms.txt builder Sphinx extension — ADR-044 §10.3 (TC-1D.5).

Per ADR-044 §10.3 + §10.4, this extension emits ``docs/user/llms.txt``
(OpenClaw-pattern AI-consumption index) BEFORE ``sphinx-build`` renders
output pages.

The actual generator lives at
``src/scieasy/qa/docs/generators/llms_txt.py``; this Sphinx wrapper
invokes that generator via the ``builder-inited`` event so it fires
before any source files are read.

Design choice: ``connect('builder-inited', ...)`` is used rather than a
custom Builder subclass because:

1. We only need to run a pre-build side-effect, not replace the entire
   Sphinx rendering pipeline.
2. A custom builder would require the user to invoke ``sphinx-build -b
   llms_txt``, losing all the HTML output in one run.
3. The ``builder-inited`` hook is the standard Sphinx extension pattern
   for "run something once before the build starts".

Per ADR-044 §10.3 generation-order note (audit P1.3 fix): the generator
reads source toctrees from ``*.rst``/``*.md`` files, NOT rendered HTML,
so it can safely run before Sphinx processes any source.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _on_builder_inited(app: Any) -> None:
    """Generate ``llms.txt`` before Sphinx reads any source files.

    Called by Sphinx immediately after the builder is created.  Runs the
    ``scieasy.qa.docs.generators.llms_txt.generate`` function, writing
    output to ``docs/user/llms.txt`` relative to the Sphinx source
    directory's parent.
    """
    from scieasy.qa.docs.generators.llms_txt import generate

    docs_sphinx_dir = Path(app.srcdir)
    # docs/user/llms.txt is relative to the repo docs/ root
    repo_docs_dir = docs_sphinx_dir.parent
    output_path = repo_docs_dir / "user" / "llms.txt"

    source_sha = _get_head_sha(docs_sphinx_dir)

    try:
        generate(
            docs_root=docs_sphinx_dir,
            output=output_path,
            source_sha=source_sha,
        )
    except Exception as exc:  # pragma: no cover — Sphinx swallows runtime errors
        import warnings

        warnings.warn(
            f"llms_txt_builder: failed to generate llms.txt: {exc}",
            stacklevel=1,
        )


def _get_head_sha(docs_sphinx_dir: Path) -> str:
    """Return the current HEAD git SHA, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(docs_sphinx_dir),
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def setup(app: Any) -> dict[str, Any]:
    """Sphinx extension entry point — wires the pre-build llms.txt generator."""
    app.connect("builder-inited", _on_builder_inited)
    return {
        "version": "1.0.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
