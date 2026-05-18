"""ScieasyAIBlockCatalog Sphinx directive — ADR-044 §10.2 (TC-1D.4).

Discovers ADR-035 AI-blocks via the ``scieasy.blocks`` entry-point group
(filtering for AI-category blocks) and emits a list-table.

Each row shows:
- Cross-reference ``:class:`` link to the AI-block class.
- Provider (from ``config_schema``).
- Model (from ``config_schema``).
- Port specs.
- PTY route binding reference.

Usage in RST/MD source::

    .. scieasy-ai-block-catalog::
       :entry-point-group: scieasy.blocks
"""

from __future__ import annotations

import importlib.metadata
import inspect
import logging
from typing import Any, ClassVar

from docutils import nodes
from docutils.parsers.rst import directives

logger = logging.getLogger(__name__)


class ScieasyAIBlockCatalog:
    """Per-ADR-035 AI-block registry entry.

    Discovers AI-blocks from the ``scieasy.blocks`` entry-point group by
    filtering for classes whose ``type_name`` starts with ``"ai."`` or
    whose ``subcategory`` is ``"ai"``.  Emits a list-table with provider,
    model, port specs, and PTY route reference.
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
        """Build and return the AI-block-catalog node tree."""
        group = self.options.get("entry-point-group", "scieasy.blocks")
        ai_specs = _load_ai_block_specs(group)

        if not ai_specs:
            warning = nodes.warning(
                "",
                nodes.paragraph(text=f"No AI blocks found in entry-point group '{group}'."),
            )
            return [warning]

        table_node = _build_list_table(
            headers=["AI Block", "Symbol", "Provider", "Inputs", "Outputs", "PTY route"],
            rows=[_ai_spec_to_row(spec) for spec in ai_specs],
        )
        return [table_node]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_ai_block_specs(group: str) -> list[dict[str, Any]]:
    """Return specs for AI-category blocks in *group*."""
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

        if not inspect.isclass(loaded):
            continue
        if not _is_ai_block(loaded):
            continue

        spec = _extract_ai_spec(ep.name, ep.value, loaded)
        specs.append(spec)

    specs.sort(key=lambda s: s["name"])
    return specs


def _is_ai_block(cls: Any) -> bool:
    """Return True if *cls* is an AI-category block."""
    type_name = getattr(cls, "type_name", "") or ""
    subcategory = getattr(cls, "subcategory", "") or ""
    return type_name.startswith("ai.") or subcategory == "ai"


def _extract_ai_spec(ep_name: str, ep_value: str, cls: Any) -> dict[str, Any]:
    """Extract display metadata from an AI-block class."""
    config_schema = getattr(cls, "config_schema", {}) or {}
    provider_info = config_schema.get("provider", {})
    default_provider = provider_info.get("default", "claude-code") if isinstance(provider_info, dict) else "claude-code"

    model_info = config_schema.get("model", {})
    default_model = model_info.get("default", "—") if isinstance(model_info, dict) else "—"

    input_ports = getattr(cls, "input_ports", []) or []
    output_ports = getattr(cls, "output_ports", []) or []
    module = cls.__module__
    qualname = cls.__qualname__

    # PTY route: AI blocks use ai_pty.py per ADR-035 §3.2
    pty_route = "``scieasy.engine.pty_control`` (ADR-035 §3.2)"

    return {
        "name": getattr(cls, "name", ep_name),
        "symbol": f"{module}.{qualname}",
        "class_ref": f"{module}.{qualname}",
        "provider": default_provider,
        "model": default_model,
        "input_ports": input_ports,
        "output_ports": output_ports,
        "pty_route": pty_route,
    }


def _ai_spec_to_row(spec: dict[str, Any]) -> list[str]:
    """Convert an AI-block spec dict to a list-table row."""
    class_ref = spec["class_ref"]
    in_count = len(spec["input_ports"])
    out_count = len(spec["output_ports"])
    return [
        f":py:class:`{class_ref}`",
        spec["symbol"],
        f"``{spec['provider']}``",
        str(in_count),
        str(out_count),
        spec["pty_route"],
    ]


def _build_list_table(
    headers: list[str],
    rows: list[list[str]],
) -> nodes.Node:
    """Build a raw RST list-table node."""
    lines: list[str] = [
        ".. list-table::",
        "   :header-rows: 1",
        "   :widths: auto",
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
