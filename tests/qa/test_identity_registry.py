"""Tests for the seeded ``docs/identity/humans.yml`` registry (TC-1C.3).

Validates that the file ships per ADR-042 §25.3 and parses cleanly
through ``scieasy.qa.schemas.identity.IdentityRegistry``. This is the
test declared in ADR-042 frontmatter line 135 (``test_identity_registry.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scieasy.qa.schemas.identity import HumanTier, IdentityRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
HUMANS_PATH = REPO_ROOT / "docs" / "identity" / "humans.yml"


def _load_registry() -> IdentityRegistry:
    """Helper: load the seed registry from the repo root."""
    with HUMANS_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return IdentityRegistry(**data)


def test_humans_yml_exists() -> None:
    """The seed registry file must exist at the canonical path."""
    assert HUMANS_PATH.exists(), f"missing {HUMANS_PATH}"


def test_humans_yml_parses_against_schema() -> None:
    """The seed file must validate against ``IdentityRegistry``."""
    reg = _load_registry()
    assert reg.version == 1
    assert len(reg.humans) >= 1, "registry must have at least one human"


def test_seed_contains_project_owner() -> None:
    """Phase 1C bootstraps with a single Tier-2 owner @jiazhenz026."""
    reg = _load_registry()
    owner = reg.lookup_by_github("@jiazhenz026")
    assert owner is not None, "expected @jiazhenz026 in seed registry"
    assert owner.tier == HumanTier.MAINTAINER
    assert owner.email == "jiazhenz026@gmail.com"


def test_lookup_by_email_roundtrip() -> None:
    """``lookup_by_email`` returns the same entry as ``lookup_by_github``."""
    reg = _load_registry()
    by_github = reg.lookup_by_github("@jiazhenz026")
    by_email = reg.lookup_by_email("jiazhenz026@gmail.com")
    assert by_github is not None
    assert by_email is not None
    assert by_github.github == by_email.github


def test_lookup_returns_none_for_unknown() -> None:
    """Lookups for non-registered handles/emails return ``None``."""
    reg = _load_registry()
    assert reg.lookup_by_github("@nobody-here") is None
    assert reg.lookup_by_email("nobody@example.com") is None


def test_maintainer_requires_signing_key_property() -> None:
    """``requires_signing_key`` is True for Tier-2 humans regardless of value.

    Per the Phase 1 investigation SUMMARY Q1A.5 manager default, the
    schema permits ``signing_key=None`` for maintainers; the
    ``requires_signing_key`` property is informational only at this
    layer. Enforcement is deferred to a Phase 1.5 file-validation
    layer.
    """
    reg = _load_registry()
    owner = reg.lookup_by_github("@jiazhenz026")
    assert owner is not None
    assert owner.requires_signing_key is True


def test_no_duplicate_github_handles() -> None:
    """Each ``github`` handle appears at most once in the registry."""
    reg = _load_registry()
    handles = [h.github for h in reg.humans]
    assert len(handles) == len(set(handles)), f"duplicate github handles: {handles}"


def test_no_duplicate_emails() -> None:
    """Each ``email`` appears at most once in the registry."""
    reg = _load_registry()
    emails = [h.email for h in reg.humans]
    assert len(emails) == len(set(emails)), f"duplicate emails: {emails}"


def test_extra_field_rejected() -> None:
    """``extra='forbid'`` blocks unknown top-level fields."""
    data = {
        "version": 1,
        "humans": [
            {
                "github": "@unknown",
                "email": "unknown@example.com",
                "tier": "contributor",
                "joined": "2026-01-01",
            }
        ],
        "unexpected_field": True,
    }
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError shape varies
        IdentityRegistry(**data)
