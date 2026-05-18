"""Custom Sphinx extensions for SciEasy documentation.

This package hosts in-tree Sphinx extensions referenced from
``docs/sphinx/conf.py`` per ADR-044 §10.2 and §10.4. The extension
modules ship as no-op ``setup()`` shells in Phase 1D sub-PR 2; bodies
are added by 1D sub-PR 3+.

The package directory is added to ``sys.path`` by ``conf.py`` so each
module is importable by its top-level name (e.g. ``scieasy_directives``,
``llms_txt_builder``) — Sphinx requires extension names to be importable
strings.
"""
