"""Audit helper scripts.

This package is a small sibling tree of one-off CLIs that support the
ADR-042/043/044 cascade. The Phase -0.5 temporary review system
(``temp_review``) lives here so that the eventual decommission PR can
delete the file (or the whole package) without touching
``src/scieasy/qa/**`` — the location of the full Phase 1 review stack.
"""
