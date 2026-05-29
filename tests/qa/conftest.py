"""QA test fixtures (ADR-042 Addendum 6).

The §7.10 parity layer auto-provisions an isolated per-worktree venv (creating a
real venv + installing ``-e ".[dev]"``) whenever ``gate_record check`` runs the
quality checks in a LOCAL mode. The test suite must NEVER create a real venv or
hit the network, so an autouse fixture replaces ``parity.provision_venv`` with a
deterministic in-memory success report. Tests that specifically validate the
provisioning logic mock the venv/install subprocess directly and call the real
functions, so they opt out by not exercising this seam.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scistudio.qa.governance.gate_record.parity as parity


@pytest.fixture(autouse=True)
def _stub_parity_provisioning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent real venv creation / network installs in the QA suite (§7.10)."""

    def _no_real_provision(repo_root: Path, **_kwargs: object) -> parity.ParityReport:
        return parity.ParityReport(
            importable=True,
            resolved_versions=parity.resolve_ci_tool_versions(repo_root),
            gaps=[],
            venv_path=None,
            provisioned=False,
        )

    monkeypatch.setattr(parity, "provision_venv", _no_real_provision)
