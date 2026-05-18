"""SciEasy QA infrastructure namespace (ADR-042/043/044 cascade).

This package owns the quality-assurance infrastructure introduced by the
ADR-042/043/044 cascade: pydantic schemas describing ADR/spec frontmatter,
MAINTAINERS, audit reports, facts registry, identity, and so on; audit
tools that classify drift between docs and code; codemods that apply
mechanical fixes; the workflow-v2 gate state machine; the identity
registry; and the tracker schemas for the implementation pipeline.

Phase 1A-a (this initial shipment) ships ONLY the schemas subpackage —
audit/codemod/workflow/facts/identity/tracker subpackages arrive in
later Phase 1 sub-waves per ``docs/planning/polished-zooming-shell.md``.
"""
