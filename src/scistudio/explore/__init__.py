"""The Explore Session runtime (ADR-054 §4 to §7).

An Explore Session is a notebook in the project's ``explore/`` directory plus
an optional ipykernel. This package holds the runtime behind it: the notebook
store, the kernel handle and its in-kernel bridge, the execution queue, the
marks, packaging, and the session service that owns them.

The subsystem sits beside the engine and must not import the API, AI, or
engine layers (``docs/specs/adr-054-explore-session.md`` FR-008).

Submodules are imported directly; this package deliberately re-exports
nothing, so importing one module never drags a kernel or a queue in with it.
"""

from __future__ import annotations

__all__: list[str] = []
