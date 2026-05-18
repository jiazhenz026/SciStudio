"""Tests for the seeded ``.governance-paths.yaml`` registry (TC-1C.1).

Validates that the file ships per ADR-043 §3.2 and parses cleanly
through ``scieasy.qa.schemas.governance.GovernancePaths``, and that
the seed contents include the path categories enumerated in the ADR.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scieasy.qa.schemas.governance import GovernancePaths

REPO_ROOT = Path(__file__).resolve().parents[2]
GOV_PATHS = REPO_ROOT / ".governance-paths.yaml"


def _load_registry() -> GovernancePaths:
    """Helper: load the seed registry from the repo root."""
    with GOV_PATHS.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return GovernancePaths(**data)


def test_governance_paths_yaml_exists() -> None:
    """The seed registry file must exist at the canonical path."""
    assert GOV_PATHS.exists(), f"missing {GOV_PATHS}"


def test_governance_paths_validates() -> None:
    """The seed file must validate against ``GovernancePaths``."""
    gp = _load_registry()
    assert gp.version == 1
    assert len(gp.governance_paths) >= 1


@pytest.mark.parametrize(
    "expected_path",
    [
        "docs/adr/**",
        "docs/specs/**",  # plural — see .governance-paths.yaml comment for rationale.
        "AGENTS.md",
        "CLAUDE.md",
        "pyproject.toml",
        ".pre-commit-config.yaml",
        ".github/workflows/**",
        ".github/CODEOWNERS",
        ".workflow/**",
        "src/scieasy/qa/**",
        "scripts/audit/**",
        "scripts/committer.py",
        "MAINTAINERS",
        "docs/identity/humans.yml",
        ".governance-paths.yaml",
    ],
)
def test_seed_includes_canonical_path(expected_path: str) -> None:
    """The seed lists every path category enumerated in ADR-043 §3.2."""
    gp = _load_registry()
    assert expected_path in gp.governance_paths, f"{expected_path} missing from seed registry"


def test_self_reference_present() -> None:
    """``.governance-paths.yaml`` must list itself per ADR-043 §3.2."""
    gp = _load_registry()
    assert ".governance-paths.yaml" in gp.governance_paths


def test_honeypot_canary_seeded() -> None:
    """A canary on ``.governance-paths.yaml`` is seeded per ADR-043 §3.6.3."""
    gp = _load_registry()
    assert len(gp.honeypot_canaries) >= 1
    canary = gp.honeypot_canaries[0]
    assert canary.path == ".governance-paths.yaml"
    assert "CANARY" in canary.marker_pattern


def test_no_duplicate_paths() -> None:
    """No path appears twice in the registry."""
    gp = _load_registry()
    paths = list(gp.governance_paths)
    assert len(paths) == len(set(paths)), f"duplicate paths: {paths}"


def test_extra_top_level_field_rejected() -> None:
    """``extra='forbid'`` blocks unknown top-level fields."""
    data = {
        "version": 1,
        "governance_paths": ["foo/**"],
        "honeypot_canaries": [],
        "unknown_field": 42,
    }
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        GovernancePaths(**data)
