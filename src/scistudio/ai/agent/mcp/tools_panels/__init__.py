"""Category (g) MCP tools — panel authoring (ADR-054 spec 5 FR-014 to FR-018).

Importing this package runs the ``@mcp.tool`` decorators in :mod:`tools` as a
side effect, registering the four ``category:panel`` tools on the shared FastMCP
instance. The eager import lives in ``scistudio.ai.agent.mcp.__init__`` alongside
the other tool groups.

The four tools are the authoring loop ADR-054 §8.5 asks for: ``scaffold_panel``
writes a panel and the harness that makes it openable, ``read_panel_source``
reads one back from whichever tier it resolved from, ``list_panel_examples``
offers a worked pattern, and ``reload_panels`` is the one trigger by which a
directory on disk becomes a registered panel.
"""

from __future__ import annotations

# Side-effect import: registers the four @mcp.tool functions.
from scistudio.ai.agent.mcp.tools_panels._models import (
    DiscoveredPanelEntry,
    ListPanelExamplesResult,
    PanelExampleEntry,
    ReadPanelSourceResult,
    ReloadPanelsResult,
    ScaffoldPanelResult,
)
from scistudio.ai.agent.mcp.tools_panels.tools import (
    list_panel_examples,
    read_panel_source,
    reload_panels,
    scaffold_panel,
)

__all__ = [
    "DiscoveredPanelEntry",
    "ListPanelExamplesResult",
    "PanelExampleEntry",
    "ReadPanelSourceResult",
    "ReloadPanelsResult",
    "ScaffoldPanelResult",
    "list_panel_examples",
    "read_panel_source",
    "reload_panels",
    "scaffold_panel",
]
