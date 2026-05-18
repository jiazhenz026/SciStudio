"""ScieasyRunnerCatalog Sphinx directive — ADR-044 §10.2 (TC-1D.4).

Discovers every runner (Python / R / Julia) via the
``scieasy.runners`` entry-point group and emits a list-table.

Each row shows:
- Runner name.
- Language.
- Executable path resolution policy.
- Environment-detection hook (``shutil.which`` based).

Usage in RST/MD source::

    .. scieasy-runner-catalog::
       :entry-point-group: scieasy.runners
"""

from __future__ import annotations

import importlib.metadata
import logging
import shutil
from typing import Any, ClassVar

from docutils import nodes
from docutils.parsers.rst import directives

logger = logging.getLogger(__name__)

# Well-known language inference by module/class name.
_LANGUAGE_MAP: dict[str, str] = {
    "python": "Python",
    "r": "R",
    "julia": "Julia",
    "pythonrunner": "Python",
    "rrunner": "R",
    "juliarunner": "Julia",
}

# Executable candidates per runner name.
_EXECUTABLE_CANDIDATES: dict[str, list[str]] = {
    "python": ["python3", "python"],
    "r": ["Rscript", "R"],
    "julia": ["julia"],
}


class ScieasyRunnerCatalog:
    """Per-runner doc page (Python / R / Julia) from runner plugin metadata.

    Discovers runners from ``scieasy.runners`` entry-points and emits a
    list-table with name, language, executable resolution policy, and
    environment-detection status.
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
        """Build and return the runner-catalog node tree."""
        group = self.options.get("entry-point-group", "scieasy.runners")
        runner_specs = _load_runner_specs(group)

        if not runner_specs:
            warning = nodes.warning(
                "",
                nodes.paragraph(text=f"No runners found in entry-point group '{group}'."),
            )
            return [warning]

        table_node = _build_list_table(
            headers=["Runner", "Language", "Executables", "Detected on this host"],
            rows=[_runner_spec_to_row(spec) for spec in runner_specs],
        )
        return [table_node]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_runner_specs(group: str) -> list[dict[str, Any]]:
    """Return lightweight spec dicts for each runner in *group*."""
    specs: list[dict[str, Any]] = []
    try:
        eps = importlib.metadata.entry_points(group=group)
    except Exception:
        logger.warning("Failed to load entry-points for group %r", group)
        return specs

    for ep in eps:
        spec = _extract_runner_spec(ep.name, ep.value)
        specs.append(spec)

    specs.sort(key=lambda s: s["name"])
    return specs


def _extract_runner_spec(ep_name: str, ep_value: str) -> dict[str, Any]:
    """Build a display spec for a runner entry-point."""
    language = _infer_language(ep_name)
    executables = _EXECUTABLE_CANDIDATES.get(ep_name.lower(), [ep_name])
    detected = _detect_executable(executables)

    return {
        "name": ep_name,
        "symbol": ep_value,
        "language": language,
        "executables": executables,
        "detected": detected,
    }


def _infer_language(ep_name: str) -> str:
    """Return a human-readable language name for *ep_name*."""
    return _LANGUAGE_MAP.get(ep_name.lower(), ep_name.capitalize())


def _detect_executable(candidates: list[str]) -> str:
    """Return first found executable path, or 'not found'."""
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return "not found"


def _runner_spec_to_row(spec: dict[str, Any]) -> list[str]:
    """Convert a runner spec dict to a list-table row."""
    return [
        f"``{spec['name']}``",
        spec["language"],
        ", ".join(f"``{e}``" for e in spec["executables"]),
        f"``{spec['detected']}``",
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
