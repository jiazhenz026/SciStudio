"""Shared fixtures for ``tests/agent_provisioning/`` (ADR-040 §3.8).

The ``tmp_project_dir`` fixture creates a minimal SciStudio-shaped project
directory under ``tmp_path`` for provisioning tests. It is intentionally
lighter than a full ApiRuntime-created project — provisioning sub-step
tests only need a writable directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_project_dir(tmp_path: Path) -> Path:
    """A throwaway project root directory.

    Returns ``tmp_path`` itself — the agent_provisioning module creates
    subdirectories (.claude/, .codex/, .agents/, etc.) as needed; this
    fixture just guarantees an empty writable parent.
    """
    return tmp_path
