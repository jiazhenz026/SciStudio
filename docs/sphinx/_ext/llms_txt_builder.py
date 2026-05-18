"""llms.txt builder Sphinx extension — shell module.

Per ADR-044 §10.3 + §10.4, this extension emits ``docs/user/llms.txt``
(OpenClaw-pattern AI-consumption index) BEFORE ``sphinx-build`` runs.
The actual generator lives at ``src/scieasy/qa/docs/generators/llms_txt.py``
(stubbed in ADR-044 §11.5); this Sphinx wrapper merely invokes that
generator via the ``builder-inited`` event.

Phase 1D sub-PR 2 ships only the ``setup()`` shell so ``conf.py`` can
list ``llms_txt_builder`` in ``extensions``. Generator wiring follows
in 1D sub-PR 3+.

TODO(#1169-followup): wire ``builder-inited`` event handler to invoke
  ``scieasy.qa.docs.generators.llms_txt.generate(...)``. Out of scope
  per ADR-044 §10.3 generation-order note (the generator itself is a
  Phase 1D deliverable but ships in a later sub-PR).
  Followup: open after 1D sub-PR 2 merges.
"""

from __future__ import annotations

from typing import Any


def setup(app: Any) -> dict[str, Any]:
    """Sphinx extension entry point — shell."""
    # TODO(#1169-followup): app.connect("builder-inited", _on_init)
    #   where _on_init walks source toctrees and emits llms.txt per
    #   ADR-044 §10.3 generation-order note.
    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
