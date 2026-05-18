"""Custom Sphinx directives for SciEasy documentation — ADR-044 §10.2.

Three directive classes are provided:

* :class:`scieasy_block_catalog.ScieasyBlockCatalog` — per-block catalog
* :class:`scieasy_runner_catalog.ScieasyRunnerCatalog` — per-runner catalog
* :class:`scieasy_ai_block_catalog.ScieasyAIBlockCatalog` — AI-block catalog

All three are registered via ``docs/sphinx/_ext/scieasy_directives.py``
``setup()`` function so Sphinx can invoke them from RST/MD source files.
"""
