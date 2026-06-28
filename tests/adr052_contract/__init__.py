"""Dedicated, self-contained ADR-052 public API contract suite (#1833).

This package is an INDEPENDENT contract suite for the ADR-052 public API surface
(``docs/specs/adr-052-public-api-surface.md`` + ``docs/adr/ADR-052.md``). It is
derived purely from the spec, not from any implementation, so it is a second,
disjoint witness to the contract alongside the in-repo ``tests/api/**`` set.

Most assertions here will FAIL until the #1817 implementation lands the
``__all__`` / stability-decorator surface, the ergonomic accessors, the
de-underscored hooks, the re-exports, and the demotions. That is intentional:
the suite is written correct-by-spec and is not weakened to pass against the
pre-implementation tree.
"""
