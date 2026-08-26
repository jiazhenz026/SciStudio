"""Scaffold an interactive block together with the panel module it opens (#2197).

An interactive block is two files, not one: the Python block and the ES module
that draws its window. Scaffolding only the Python half is what produced the two
failures this module exists to prevent — a panel that never loads (the module
did not use a **default** export, or its ``module_url`` did not match the route
the backend serves), and a panel that loads but strands the user on a paused run
because it renders no way to confirm or cancel.

So this scaffold emits both halves, already wired to each other:

- ``blocks/<name>.py`` — ``InteractiveMixin`` + ``execution_mode = INTERACTIVE``,
  a ``PanelManifest`` whose ``panel_id``, ``module_url`` and ``asset_root``
  agree with where the panel is actually written, and a ``prepare_prompt`` stub.
- ``blocks/<name>_panel/panel.mjs`` — a default-exported module carrying
  ``apiVersion`` and a ``mount`` that returns ``{ unmount }``, with confirm and
  cancel already bound to ``host.confirm`` / ``host.cancel``.

The generated pair is correct as generated: it registers, and it mounts with
working controls, with no further edits. What the author fills in afterwards is
the payload reduction, the panel's content area, and the compute body.

This module is deliberately self-contained — one public entry point,
:func:`scaffold_interactive_block`, with no dependency on the MCP tool surface —
so the ``scaffold_block`` tool can delegate to it in one call.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_PANEL_NAMESPACE",
    "PANEL_ASSET_ROUTE",
    "PANEL_MODULE_FILENAME",
    "InteractiveScaffold",
    "scaffold_interactive_block",
]

_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "cli" / "templates" / "interactive_block"

PANEL_MODULE_FILENAME = "panel.mjs"
"""Filename the panel module is written under, and the one ``module_url`` names.

``.mjs`` rather than ``.js`` because it is unambiguously an ES module and it is
what the only shipped panel example uses; the asset route's suffix allowlist
serves both.
"""

PANEL_ASSET_ROUTE = "/api/blocks/panels/{panel_id}/{asset_path}"
"""The one route shape a package panel's ``module_url`` may take.

The backend serves panel assets from ``GET /api/blocks/panels/{panel_id}/{path}``
(router prefix ``/api/blocks``). A ``module_url`` of any other shape resolves to
nothing and the panel host reports ``import_failed``.
"""

DEFAULT_PANEL_NAMESPACE = "project"
"""Namespace prefix for a scaffolded ``panel_id`` (``project.<name>``).

``core.*`` is reserved for the built-in panels that ship with the frontend and
are resolved from its registry rather than from an ``asset_root``.
"""

# Types a scaffolded port may name without the generated file needing an import
# the author has to add by hand. Anything else is scaffolded as ``DataObject``
# with a warning naming what was asked for, so the pair still registers.
_CORE_TYPE_NAMES = frozenset(
    {
        "Array",
        "Artifact",
        "CompositeData",
        "DataFrame",
        "DataObject",
        "Series",
        "Text",
    }
)

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class InteractiveScaffold:
    """What :func:`scaffold_interactive_block` wrote, and what to tell the author."""

    block_path: Path
    """The generated ``blocks/<name>.py``."""

    panel_path: Path
    """The generated panel module (``blocks/<name>_panel/panel.mjs``)."""

    panel_id: str
    """The manifest's ``panel_id``, e.g. ``project.pick_baseline``."""

    module_url: str
    """The manifest's ``module_url`` — the route the panel is served on."""

    asset_root: Path
    """The directory the panel module lives in (the manifest's ``asset_root``)."""

    class_name: str
    """The generated block class name."""

    warnings: list[str] = field(default_factory=list)
    """Author-facing warnings. Every entry must be read before proceeding."""


def _to_class_name(name: str) -> str:
    """``pick_baseline`` -> ``PickBaseline``."""
    return "".join(part.title() for part in name.split("_") if part)


def _to_label(name: str) -> str:
    """``pick_baseline`` -> ``Pick Baseline`` (the palette text, pre-filled)."""
    return " ".join(part.capitalize() for part in name.split("_") if part)


def _render_ports(
    spec_map: Mapping[str, Mapping[str, Any]] | None,
    port_class: str,
    fallback_name: str,
    warnings: list[str],
) -> tuple[str, str, set[str]]:
    """Render one port list body.

    Returns the rendered lines, the first port's name (the one the stub body
    wires through), and the set of core type names the file must import.
    """
    entries = list((spec_map or {}).items())
    if not entries:
        entries = [(fallback_name, {})]

    used: set[str] = set()
    lines: list[str] = []
    for port_name, spec in entries:
        requested = str((spec or {}).get("type") or "DataObject")
        if requested in _CORE_TYPE_NAMES:
            type_name = requested
            if type_name == "DataObject":
                warnings.append(
                    f"port {port_name!r} accepts DataObject, which means 'anything'. Call list_types "
                    f"and narrow it to the most specific applicable type before you ship the block."
                )
        else:
            # Package types (Image, Spectrum, ...) are not importable from a
            # canonical root, and an unresolvable import would stop the block
            # registering at all. Scaffold something that works and say so.
            type_name = "DataObject"
            warnings.append(
                f"port {port_name!r}: type {requested!r} is not exported by scistudio.core.types, so the "
                f"port was scaffolded as DataObject (accepts anything). Import {requested} from the "
                f"package that defines it and replace the accepted_types entry."
            )
        used.add(type_name)
        description = str((spec or {}).get("description") or "").strip()
        described = f', description="{description}"' if description else ""
        lines.append(f'        {port_class}(name="{port_name}", accepted_types=[{type_name}]{described}),')
    return "\n".join(lines), str(entries[0][0]), used


def _render(template_name: str, tokens: Mapping[str, str]) -> str:
    """Read a template and substitute its ``@@TOKEN@@`` markers.

    ``@@TOKEN@@`` rather than ``{token}`` because one of the two templates is
    JavaScript, where braces are on nearly every line.
    """
    text = (_TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
    for token, value in tokens.items():
        text = text.replace(f"@@{token}@@", value)
    return text


def scaffold_interactive_block(
    project_dir: Path | str,
    name: str,
    *,
    input_ports: Mapping[str, Mapping[str, Any]] | None = None,
    output_ports: Mapping[str, Mapping[str, Any]] | None = None,
    panel_namespace: str = DEFAULT_PANEL_NAMESPACE,
) -> InteractiveScaffold:
    """Write an interactive block and the panel module it opens.

    Args:
        project_dir: The SciStudio project root. The block lands under its
            ``blocks/`` directory, which is created when absent.
        name: Snake-case block name (``pick_baseline``). Becomes the file name,
            the ``type_name``, the class name, and the panel id suffix.
        input_ports: Optional ``{port_name: {"type": ..., "description": ...}}``.
            Defaults to a single ``input`` port accepting ``DataObject``.
        output_ports: Same shape for outputs. Defaults to a single ``output``.
        panel_namespace: Prefix for the generated ``panel_id``. ``core`` is
            refused — it is reserved for the frontend's built-in panels.

    Returns:
        An :class:`InteractiveScaffold` naming both written files, the manifest
        values they agree on, and the warnings the author must read.

    Raises:
        ValueError: *name* is not a snake-case identifier, or *panel_namespace*
            is empty or the reserved ``core`` namespace.
        FileExistsError: the block file or the panel directory already exists.
            Nothing is written in that case.
    """
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"block name must be snake_case starting with a letter, got {name!r}")
    namespace = panel_namespace.strip()
    if not namespace:
        raise ValueError("panel_namespace must not be empty")
    if namespace == "core" or namespace.startswith("core."):
        raise ValueError("the 'core' panel namespace is reserved for the frontend's built-in panels")

    root = Path(project_dir)
    blocks_dir = root / "blocks"
    block_path = blocks_dir / f"{name}.py"
    panel_dirname = f"{name}_panel"
    asset_root = blocks_dir / panel_dirname
    panel_path = asset_root / PANEL_MODULE_FILENAME

    # Check both halves before writing either: a half-written pair is a block
    # that registers and then fails to open.
    if block_path.exists():
        raise FileExistsError(f"block already exists: {block_path}")
    if asset_root.exists():
        raise FileExistsError(f"panel directory already exists: {asset_root}")

    panel_id = f"{namespace}.{name}"
    module_url = PANEL_ASSET_ROUTE.format(panel_id=panel_id, asset_path=PANEL_MODULE_FILENAME)
    class_name = _to_class_name(name)
    label = _to_label(name)

    warnings: list[str] = []
    inputs_rendered, primary_input, input_types = _render_ports(input_ports, "InputPort", "input", warnings)
    outputs_rendered, primary_output, output_types = _render_ports(output_ports, "OutputPort", "output", warnings)

    imported = sorted({"Collection", *input_types, *output_types})
    type_import_line = f"from scistudio.core.types import {', '.join(imported)}"

    block_text = _render(
        "block.py.tpl",
        {
            "BLOCK_LABEL": label,
            "CLASS_NAME": class_name,
            "TYPE_NAME": name,
            "PANEL_ID": panel_id,
            "MODULE_URL": module_url,
            "PANEL_DIRNAME": panel_dirname,
            "PANEL_FILENAME": PANEL_MODULE_FILENAME,
            "TYPE_IMPORT_LINE": type_import_line,
            "INPUT_PORTS": inputs_rendered,
            "OUTPUT_PORTS": outputs_rendered,
            "PRIMARY_INPUT": primary_input,
            "PRIMARY_OUTPUT": primary_output,
        },
    )
    panel_text = _render(
        "panel.mjs.tpl",
        {"BLOCK_LABEL": label, "PANEL_HEADING": label},
    )

    blocks_dir.mkdir(parents=True, exist_ok=True)
    asset_root.mkdir(parents=True, exist_ok=False)
    panel_path.write_text(panel_text, encoding="utf-8", newline="\n")
    block_path.write_text(block_text, encoding="utf-8", newline="\n")

    warnings.append(
        "The panel already renders working controls bound to host.confirm and host.cancel. "
        "Whatever you put in its content area, both must stay on screen and reachable — a "
        "panel with no exit strands the user on a paused run."
    )
    warnings.append(
        f"Three things are left for you, each marked in the generated files: the payload "
        f"reduction in prepare_prompt, the content area of "
        f"{panel_dirname}/{PANEL_MODULE_FILENAME}, and the compute body of run()."
    )
    warnings.append(
        "Then call reload_blocks and read its diagnostics: it is what tells you whether the "
        "block registered and the panel resolves."
    )

    return InteractiveScaffold(
        block_path=block_path,
        panel_path=panel_path,
        panel_id=panel_id,
        module_url=module_url,
        asset_root=asset_root,
        class_name=class_name,
        warnings=warnings,
    )
