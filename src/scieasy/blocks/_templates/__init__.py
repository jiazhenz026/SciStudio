"""ADR-036 §3.12 — packaged scaffolding templates served via /api/blocks/template.

This package ships block-scaffolding templates (currently just one:
``block_base_template.py``) that the embedded code editor's
"New custom block" action drops into the project's ``blocks/`` folder.

Keeping the templates inside the installed package (rather than the
frontend bundle) means they always reflect what ``scieasy.blocks.base``
actually exports — no risk of the template drifting out of sync with
the public API.
"""
