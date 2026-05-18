"""Tests for ``scieasy.qa.schemas.identity`` (ADR-042 §25.3).

Covers:

- ``HumanTier`` enum values.
- ``SigningKey`` regex positive + negative.
- ``HumanIdentity.requires_signing_key`` property for both tiers.
- ``IdentityRegistry.lookup_by_email`` + ``lookup_by_github`` hit + miss.
- ``IdentityRegistry.version: Literal[1]`` rejects non-1 values.
- ``extra="forbid"`` on every model.
- ``EmailStr`` validation surfaces (requires pydantic[email]).
- Round-trip via ``model_dump_json`` / ``model_validate_json``.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import TypeAdapter, ValidationError

from scieasy.qa.schemas.identity import (
    HumanIdentity,
    HumanTier,
    IdentityRegistry,
    SigningKey,
)

# --------------------------------------------------------------------------- #
# HumanTier                                                                   #
# --------------------------------------------------------------------------- #


def test_human_tier_values() -> None:
    assert HumanTier.CONTRIBUTOR.value == "contributor"
    assert HumanTier.MAINTAINER.value == "maintainer"


def test_human_tier_membership_count() -> None:
    assert {t.value for t in HumanTier} == {"contributor", "maintainer"}


# --------------------------------------------------------------------------- #
# SigningKey regex                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    [
        "ed25519:AAAAC3NzaC1lZDI1NTE5AAAAIabcdef",
        "rsa:AAAAB3NzaC1yc2E=",
        "ecdsa:AAAAE2VjZHNhLXNoYTItbmlzdHA=",
        "gpg:0123456789ABCDEF",
        "ed25519:abc-DEF_123.=",
    ],
)
def test_signing_key_accepts(value: str) -> None:
    TypeAdapter(SigningKey).validate_python(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ed25519:",  # empty key material
        "ed25519 abc",  # missing colon
        "blowfish:abc",  # unknown algorithm
        "RSA:ABC",  # uppercase algorithm not allowed
        "ed25519:abc def",  # whitespace in key material
        ":abcdef",  # missing algorithm
    ],
)
def test_signing_key_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SigningKey).validate_python(value)


# --------------------------------------------------------------------------- #
# HumanIdentity                                                               #
# --------------------------------------------------------------------------- #


def _contributor() -> HumanIdentity:
    return HumanIdentity(
        github="@alice-dev",
        email="alice@example.org",
        tier=HumanTier.CONTRIBUTOR,
        joined=date(2026, 1, 1),
    )


def _maintainer() -> HumanIdentity:
    return HumanIdentity(
        github="@bob-maintainer",
        email="bob@example.org",
        tier=HumanTier.MAINTAINER,
        signing_key="ed25519:AAAAC3NzaC1lZDI1NTE5",
        joined=date(2026, 1, 2),
        notes="Tier 2 reviewer.",
    )


def test_human_identity_contributor_minimal() -> None:
    h = _contributor()
    assert h.signing_key is None
    assert h.notes is None
    assert h.tier == HumanTier.CONTRIBUTOR


def test_human_identity_maintainer_full() -> None:
    h = _maintainer()
    assert h.signing_key is not None
    assert h.notes == "Tier 2 reviewer."


def test_human_identity_requires_signing_key_for_maintainer() -> None:
    assert _maintainer().requires_signing_key is True


def test_human_identity_does_not_require_signing_key_for_contributor() -> None:
    assert _contributor().requires_signing_key is False


def test_human_identity_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        HumanIdentity(
            github="@x",
            email="x@example.org",
            tier=HumanTier.CONTRIBUTOR,
            joined=date(2026, 1, 1),
            rogue="field",
        )


def test_human_identity_strips_whitespace() -> None:
    # str_strip_whitespace=True applies to plain str fields (notes).
    h = HumanIdentity(
        github="@alice-dev",
        email="alice@example.org",
        tier=HumanTier.CONTRIBUTOR,
        joined=date(2026, 1, 1),
        notes="  padded   ",
    )
    assert h.notes == "padded"


def test_human_identity_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        HumanIdentity(
            github="@alice-dev",
            email="not-an-email",
            tier=HumanTier.CONTRIBUTOR,
            joined=date(2026, 1, 1),
        )


def test_human_identity_rejects_invalid_github_handle() -> None:
    # Missing leading @ is the most common error mode for this field.
    with pytest.raises(ValidationError):
        HumanIdentity(
            github="alice-dev",
            email="alice@example.org",
            tier=HumanTier.CONTRIBUTOR,
            joined=date(2026, 1, 1),
        )


def test_human_identity_schema_only_allows_maintainer_without_key() -> None:
    # Per SUMMARY Q1A.5 manager default: schema is purely structural;
    # MAINTAINER without signing_key is NOT a model-level error here.
    # File-validation layer (TC-1C.3) will enforce this. Verify the
    # schema accepts the configuration so the deferral is honest.
    h = HumanIdentity(
        github="@alice-dev",
        email="alice@example.org",
        tier=HumanTier.MAINTAINER,
        joined=date(2026, 1, 1),
    )
    assert h.signing_key is None
    assert h.requires_signing_key is True


# --------------------------------------------------------------------------- #
# IdentityRegistry                                                            #
# --------------------------------------------------------------------------- #


def _registry() -> IdentityRegistry:
    return IdentityRegistry(humans=[_contributor(), _maintainer()])


def test_identity_registry_default_version() -> None:
    assert _registry().version == 1


def test_identity_registry_explicit_version_one() -> None:
    reg = IdentityRegistry(version=1, humans=[])
    assert reg.version == 1


@pytest.mark.parametrize("bad", [0, 2, 99])
def test_identity_registry_rejects_other_versions(bad: int) -> None:
    with pytest.raises(ValidationError):
        IdentityRegistry(version=bad, humans=[])


def test_identity_registry_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        IdentityRegistry(humans=[], rogue="field")


def test_identity_registry_lookup_by_email_hit() -> None:
    reg = _registry()
    found = reg.lookup_by_email("alice@example.org")
    assert found is not None
    assert found.github == "@alice-dev"


def test_identity_registry_lookup_by_email_miss() -> None:
    reg = _registry()
    assert reg.lookup_by_email("nobody@example.org") is None


def test_identity_registry_lookup_by_github_hit() -> None:
    reg = _registry()
    found = reg.lookup_by_github("@bob-maintainer")
    assert found is not None
    assert found.tier == HumanTier.MAINTAINER


def test_identity_registry_lookup_by_github_miss() -> None:
    reg = _registry()
    assert reg.lookup_by_github("@nobody") is None


def test_identity_registry_round_trip() -> None:
    src = _registry()
    rebuilt = IdentityRegistry.model_validate_json(src.model_dump_json())
    assert rebuilt == src


def test_identity_registry_empty_humans_is_valid() -> None:
    reg = IdentityRegistry(humans=[])
    assert reg.humans == []
    assert reg.lookup_by_email("x@example.org") is None
    assert reg.lookup_by_github("@anyone") is None
