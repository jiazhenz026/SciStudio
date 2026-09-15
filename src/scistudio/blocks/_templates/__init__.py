"""Packaged block starter templates, one per kind of block."""
# Maintainer context (kept outside generated API documentation):
# ADR-036 §3.12 — packaged scaffolding templates served via /api/blocks/template.
# #2384 — per-kind templates shared by the GUI endpoint and scaffold_block.
#
# The same template files back two surfaces: ``GET /api/blocks/template`` serves
# a kind verbatim to the embedded code editor's "New custom block" action, and
# the agent's ``scaffold_block`` MCP tool renders a kind with a class name,
# labels, ports, and imports through ``render.render_starter``. One source per
# kind keeps the two from drifting apart.
#
# Keeping the templates inside the installed package (rather than the
# frontend bundle) means they always reflect what the ``scistudio.blocks``
# public roots actually export. The template files are ordinary modules of
# this package, so the wheel ships them without extra package-data entries.
# Development references: ADR-036, #2384.

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class TemplateKind:
    """One starter template: where it lives and what it subclasses."""

    kind: str
    """Stable key used by ``?kind=`` and by ``scaffold_block``."""
    resource: str
    """File name of the template inside this package."""
    suggested_filename: str
    """File name the GUI proposes when a user creates a block from it."""
    base_class: str
    """Public base class the template's block subclasses."""
    body_method: str | None
    """Method holding the user's logic (the last one in the class), if any."""


TEMPLATE_KINDS: dict[str, TemplateKind] = {
    kind.kind: kind
    for kind in (
        TemplateKind("basic", "block_base_template.py", "my_block.py", "Block", "run"),
        TemplateKind("process", "process_block_template.py", "my_process_block.py", "ProcessBlock", "process_item"),
        TemplateKind("io_load", "io_loader_template.py", "my_loader.py", "SimpleLoader", "load_file"),
        TemplateKind("io_save", "io_saver_template.py", "my_saver.py", "SimpleSaver", "save_file"),
        TemplateKind("app", "app_block_template.py", "my_app_block.py", "AppBlock", None),
    )
}


def read_template(kind: str) -> str:
    """Return the verbatim source of the template registered under *kind*.

    Raises:
        KeyError: if *kind* is not a registered template kind.
    """
    return (resources.files(__name__) / TEMPLATE_KINDS[kind].resource).read_text(encoding="utf-8")


__all__ = ["TEMPLATE_KINDS", "TemplateKind", "read_template"]
