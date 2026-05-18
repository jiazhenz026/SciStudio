"""Doc generators for SciEasy — ADR-044 §10.3.

Five build-time generators run before ``sphinx-build`` and emit
auto-generated reference pages.  All emitted files carry
``generation: auto`` frontmatter and a ``source.last_generated_sha``
field; ``auto_generated_lint.py`` (§11.5) rejects hand-edits.

Generator modules
-----------------
* :mod:`scieasy.qa.docs.generators.llms_txt` — OpenClaw-pattern ``llms.txt``
* :mod:`scieasy.qa.docs.generators.entry_point_catalog` — entry-points RST table
* :mod:`scieasy.qa.docs.generators.cli_reference` — CLI reference skeleton
* :mod:`scieasy.qa.docs.generators.openapi_reference` — OpenAPI reference skeleton
* :mod:`scieasy.qa.docs.generators.schema_reference` — per-pydantic-model pages
"""
