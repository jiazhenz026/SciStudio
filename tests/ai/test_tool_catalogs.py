"""Every registered MCP tool appears in every live catalog (ADR-054 spec 5 FR-026).

ADR-054 §8.4 states the cost this file makes visible: adding an MCP tool moves a
set of count assertions and a set of *catalog documents* that enumerate the tool
set, and a tool added without updating them leaves the catalogs quietly wrong —
the failure surfaces nowhere near the tool. The catalogs are prose, so nothing
else in the suite reads them; this file does.

The assertion is one-directional on purpose: **every registered tool name must
appear in each catalog**, but a catalog may name something the registry does not
yet expose. A catalog is teaching material assembled by hand, and a document
that describes a tool group landing alongside it is not a defect; a document
that omits a tool the agent can actually call is.

Excluded catalog: ``docs/architecture/ARCHITECTURE.md``.
    Its tool table is a real catalog, but the document is a guarded,
    owner-controlled path (``docs/ai-developer/rules.md`` §4:
    ``admin-approved:architecture-doc``), so it cannot be updated by
    implementation work. ADR-054 spec 5 §4.5 and A-006 put its update in the
    documentation spec's batch, tracked by **#2236**, and say the catalog test
    excludes the guarded document until then. When #2236 lands, add the
    architecture document to ``_CATALOGS`` and delete this paragraph.
"""

from __future__ import annotations

import asyncio
import collections
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest

from scistudio.ai.agent.mcp import mcp
from tests.mcp_tool_expectations import EXPECTED_GROUP_COUNTS, EXPECTED_TOOL_GROUPS

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The catalogs implementation work owns. Each is read whole and searched for
#: every registered tool name.
_CATALOGS: dict[str, Path] = {
    "base skill static fallback": _REPO_ROOT / "src" / "scistudio" / "_skills" / "scistudio" / "SKILL.md",
    "embedded coding agent spec": _REPO_ROOT / "docs" / "specs" / "embedded-coding-agent-spec.md",
    # TODO(#2236): docs/architecture/ARCHITECTURE.md carries a tool table and
    #   belongs in this mapping, but the document is a guarded owner-controlled
    #   path and its update lands in the ADR-054 documentation batch.
    #   Out of scope per ADR-054 spec 5 §4.5 / A-006 and the S5-B4 dispatch.
    #   Followup: docs/planning/adr-054-assembly-followups.md, "## S5-B4".
}


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _registered_tool_names() -> set[str]:
    return {tool.name for tool in _run(mcp.list_tools())}


def _tool_groups() -> dict[str, int]:
    """Registered tool count per ``category:`` tag — the per-group assertion's input."""
    counts: collections.Counter[str] = collections.Counter()
    for tool in _run(mcp.list_tools()):
        category = next(
            (tag.split(":", 1)[1] for tag in (tool.tags or set()) if tag.startswith("category:")),
            "uncategorised",
        )
        counts[category] += 1
    return dict(counts)


@pytest.mark.parametrize("catalog_name", sorted(_CATALOGS))
def test_catalog_lists_every_registered_tool(catalog_name: str) -> None:
    """FR-026: each catalog names every tool the MCP server registers."""
    path = _CATALOGS[catalog_name]
    assert path.is_file(), f"catalog {catalog_name} is missing at {path}"
    text = path.read_text(encoding="utf-8")

    missing = sorted(name for name in _registered_tool_names() if name not in text)
    assert not missing, (
        f"{catalog_name} ({path.relative_to(_REPO_ROOT).as_posix()}) does not name "
        f"{len(missing)} registered tool(s): {missing}. Every tool change moves the "
        f"catalogs that list tools (ADR-054 §8.4, spec 5 FR-026)."
    )


def test_base_skill_tool_catalog_block_lists_every_tool() -> None:
    """The base skill's catalog must be complete *between its splice markers*.

    On Claude Code the live FastMCP catalog is spliced over everything between
    ``<!-- tool_catalog:begin -->`` and ``<!-- tool_catalog:end -->``. On Codex
    the splice does not run and the file is read verbatim, so the static
    fallback is the only catalog that agent ever sees. A tool named elsewhere in
    the file but not inside the markers is invisible to it.
    """
    text = _CATALOGS["base skill static fallback"].read_text(encoding="utf-8")
    begin = text.find("<!-- tool_catalog:begin -->")
    end = text.find("<!-- tool_catalog:end -->")
    assert begin >= 0 and end > begin, "tool_catalog splice markers missing from the base skill"
    fallback = text[begin : end + len("<!-- tool_catalog:end -->")]

    missing = sorted(name for name in _registered_tool_names() if name not in fallback)
    assert not missing, (
        f"the base skill's static tool-catalog fallback does not name {len(missing)} "
        f"registered tool(s): {missing}. Codex agents read this block verbatim."
    )


def test_tool_group_counts_match_the_declared_breakdown() -> None:
    """FR-025: the per-group counts are asserted, not only the total.

    A group is the ``category:`` tag the server reports on ``tools/list``, so
    this reads the same breakdown the catalogs are written from. Adding a tool
    to an existing group moves one number in
    ``tests/mcp_tool_expectations.py``; adding a *group* adds a row there.
    Nothing moves here.
    """
    assert _tool_groups() == EXPECTED_GROUP_COUNTS


def test_group_membership_matches_the_declared_breakdown() -> None:
    """Counting right while grouping wrong is a real failure mode.

    A tool that moved between groups keeps every count intact and still
    breaks the catalogs, which are organised by group.
    """
    actual: dict[str, set[str]] = {}
    for tool in _run(mcp.list_tools()):
        category = next(
            (tag.split(":", 1)[1] for tag in (tool.tags or set()) if tag.startswith("category:")),
            "uncategorised",
        )
        actual.setdefault(category, set()).add(tool.name)
    expected = {group: set(names) for group, names in EXPECTED_TOOL_GROUPS.items()}
    assert actual == expected


def test_every_registered_tool_declares_a_category() -> None:
    """An uncategorised tool is invisible to the group counts and to the catalogs."""
    uncategorised = _tool_groups().get("uncategorised", 0)
    assert uncategorised == 0, (
        f"{uncategorised} registered tool(s) carry no ``category:`` tag; they are "
        f"grouped nowhere and would be missed by every per-group assertion."
    )
