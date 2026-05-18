"""ScieasyBlockCatalog Sphinx directive — ADR-044 §10.2 (TC-1D.3).

Discovers every block via ``scieasy.blocks.registry.BlockRegistry``
entry-points and emits a list-table with one row per block.

Each row shows:
- Cross-reference ``:class:`` link to the block class.
- Dotted-symbol path (``module_path:class_name``).
- Declared input port count + type names.
- Declared output port count + type names.
- ``supported_extensions`` mapping.

Usage in RST/MD source::

    .. scieasy-block-catalog::
       :entry-point-group: scieasy.blocks

The ``entry-point-group`` option defaults to ``scieasy.blocks``.
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Any, ClassVar

from docutils import nodes
from docutils.parsers.rst import directives

logger = logging.getLogger(__name__)


class ScieasyBlockCatalog:
    """Render one autosummary page per block discovered via entry-points.

    Per ADR-044 §10.2 pattern adopted from scikit-learn's per-estimator
    template: every block gets a uniform row with:

    - Parameters (from config_schema pydantic model)
    - Inputs / Outputs (from block port declarations)
    - ``supported_extensions``
    - Source (linkcode-rendered GitHub line ref)
    """

    has_content: ClassVar[bool] = False
    required_arguments: ClassVar[int] = 0
    optional_arguments: ClassVar[int] = 0
    option_spec: ClassVar[dict[str, Any]] = {"entry-point-group": directives.unchanged}

    def __init__(
        self,
        name: str,
        arguments: list[str],
        options: dict[str, str],
        content: Any,
        lineno: int,
        content_offset: int,
        block_text: str,
        state: Any,
        state_machine: Any,
    ) -> None:
        self.name = name
        self.arguments = arguments
        self.options = options
        self.content = content
        self.lineno = lineno
        self.content_offset = content_offset
        self.block_text = block_text
        self.state = state
        self.state_machine = state_machine

    def run(self) -> list[nodes.Node]:
        """Build and return the block-catalog node tree."""
        group = self.options.get("entry-point-group", "scieasy.blocks")
        block_specs = _load_block_specs(group)

        if not block_specs:
            warning = nodes.warning(
                "",
                nodes.paragraph(text=f"No blocks found in entry-point group '{group}'."),
            )
            return [warning]

        # Build a list-table node
        table_node = _build_list_table(
            headers=["Block", "Symbol", "Inputs", "Outputs", "Extensions"],
            rows=[_block_spec_to_row(spec) for spec in block_specs],
        )
        return [table_node]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_block_specs(group: str) -> list[dict[str, Any]]:
    """Return lightweight spec dicts for each block in *group*."""
    specs: list[dict[str, Any]] = []
    try:
        eps = importlib.metadata.entry_points(group=group)
    except Exception:
        logger.warning("Failed to load entry-points for group %r", group)
        return specs

    for ep in eps:
        try:
            loaded = ep.load()
        except Exception:
            logger.debug("Skipping entry-point %r: failed to load", ep.name)
            continue

        spec = _extract_spec(ep.name, ep.value, loaded)
        specs.append(spec)

    specs.sort(key=lambda s: s["name"])
    return specs


def _extract_spec(ep_name: str, ep_value: str, loaded: Any) -> dict[str, Any]:
    """Extract display metadata from a loaded block class or factory."""
    import inspect

    cls = None
    if inspect.isclass(loaded):
        cls = loaded
    elif callable(loaded):
        # Factory like get_block_package — skip; emit a placeholder row
        return {
            "name": ep_name,
            "symbol": ep_value,
            "input_ports": [],
            "output_ports": [],
            "supported_extensions": {},
            "class_ref": ep_value,
        }

    input_ports = getattr(cls, "input_ports", []) or []
    output_ports = getattr(cls, "output_ports", []) or []
    supported_extensions = getattr(cls, "supported_extensions", {}) or {}
    module = cls.__module__ if cls else ""
    qualname = cls.__qualname__ if cls else ep_name

    return {
        "name": getattr(cls, "name", ep_name) if cls else ep_name,
        "symbol": f"{module}.{qualname}",
        "input_ports": input_ports,
        "output_ports": output_ports,
        "supported_extensions": supported_extensions,
        "class_ref": f"{module}.{qualname}",
    }


def _block_spec_to_row(spec: dict[str, Any]) -> list[str]:
    """Convert a spec dict to a list-table row (plain strings)."""
    symbol = spec["symbol"]
    class_ref = spec["class_ref"]

    # Port summaries
    in_count = len(spec["input_ports"])
    out_count = len(spec["output_ports"])

    in_types = _port_type_summary(spec["input_ports"])
    out_types = _port_type_summary(spec["output_ports"])

    inputs_str = f"{in_count} ({in_types})" if in_types else str(in_count)
    outputs_str = f"{out_count} ({out_types})" if out_types else str(out_count)

    ext = spec["supported_extensions"]
    ext_str = ", ".join(sorted(ext.keys())) if ext else "—"

    return [f":py:class:`{class_ref}`", symbol, inputs_str, outputs_str, ext_str]


def _port_type_summary(ports: list[Any]) -> str:
    """Return a comma-joined string of accepted type names for *ports*."""
    type_names: list[str] = []
    for port in ports:
        accepted = getattr(port, "accepted_types", []) or []
        for t in accepted:
            tn = t.__name__ if hasattr(t, "__name__") else str(t)
            if tn not in type_names:
                type_names.append(tn)
    return ", ".join(type_names)


def _build_list_table(
    headers: list[str],
    rows: list[list[str]],
) -> nodes.Node:
    """Build a docutils ``list_table`` (raw-RST paragraph fallback)."""
    # Emit a raw RST list-table so Sphinx renders it properly even when
    # the directive is processed in a MyST context.
    col_widths = "auto"
    lines: list[str] = [
        ".. list-table::",
        "   :header-rows: 1",
        f"   :widths: {col_widths}",
        "",
        "   * " + "\n     ".join(f"- {h}" for h in headers),
    ]
    for row in rows:
        first, *rest = row
        lines.append(f"   * - {first}")
        for cell in rest:
            lines.append(f"     - {cell}")
    lines.append("")
    rst_text = "\n".join(lines)
    raw_node = nodes.raw("", rst_text, format="rst")
    return raw_node
