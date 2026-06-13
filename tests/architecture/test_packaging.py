"""Architecture enforcement: packaging + import-graph visibility (#1591).

`src/scistudio/ai/agent/` shipped without an ``__init__.py``, so two silent
failures occurred:

* ``[tool.setuptools.packages.find]`` uses regular (non-namespace) discovery,
  which only collects directories that contain ``__init__.py``. The agent
  runtime (`terminal`, `system_prompt`, `mcp`) was therefore **dropped from the
  built wheel** — installs that ran the AI block hit an ``ImportError`` for
  ``scistudio.ai.agent.terminal`` that never reproduced in an editable/src
  checkout.
* import-linter / grimp build their graph from regular packages, so the
  ``blocks.ai.ai_block -> ai.agent.terminal`` boundary crossing was **invisible
  to the architecture contracts** — a real blocks→ai edge went unchecked.

These tests hold the line on both: the package must be discoverable by the
wheel build, and the import graph must contain the agent runtime module.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from setuptools import find_packages

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def test_ai_agent_is_a_discoverable_wheel_package() -> None:
    """``setuptools.packages.find`` must collect ``scistudio.ai.agent``.

    Guards the #1591 packaging regression: a missing ``__init__.py`` makes
    regular discovery skip the directory, dropping the agent runtime from the
    wheel.
    """
    packages = find_packages(where=str(SRC_ROOT))
    assert "scistudio.ai.agent" in packages, (
        "scistudio.ai.agent is not collected by setuptools.packages.find — it "
        "would be dropped from the built wheel. Ensure src/scistudio/ai/agent/"
        "__init__.py exists (#1591)."
    )
    # The whole ai/ tree must be regular packages so none are silently dropped.
    assert (SRC_ROOT / "scistudio" / "ai" / "agent" / "__init__.py").is_file()


def test_ai_agent_is_a_regular_package_visible_to_import_linter() -> None:
    """``ai.agent`` must be a regular (non-namespace) package.

    Guards the #1591 architecture-visibility regression: grimp / import-linter
    only graph regular packages (those with an ``__init__.py``). A namespace
    package would make the ``blocks.ai.ai_block -> ai.agent.terminal`` edge
    invisible to the blocks→ai contract. A regular package has a concrete
    ``__file__`` pointing at its ``__init__.py``; a namespace package has
    ``__file__ is None``. The terminal module must also import cleanly (the
    symptom that only reproduced from the wheel, never the src checkout).
    """
    agent_pkg = importlib.import_module("scistudio.ai.agent")
    assert agent_pkg.__file__ is not None and agent_pkg.__file__.endswith("__init__.py"), (
        "scistudio.ai.agent is a namespace package (no __init__.py) — its modules "
        "are invisible to grimp/import-linter and dropped from the wheel (#1591)."
    )
    importlib.import_module("scistudio.ai.agent.terminal")
