"""One-shot migration scripts for the ADR-042/043/044 cascade.

This package hosts non-recurring bootstrap utilities. Each script is
designed to run once during Phase 1 and then either become idempotent
documentation or be retired in the Phase -0.5 decommission PR. See
ADR-042 Appendix A for the catalog of migration scripts.
"""
