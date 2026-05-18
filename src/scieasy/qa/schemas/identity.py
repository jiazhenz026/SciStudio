"""Pydantic models for the human identity registry (ADR-042 §25.3).

``docs/identity/humans.yml`` is the registry of human contributors and
maintainers consulted by:

- ``scripts/committer.py`` (ADR-042 §16.2) — committer-only enforcement.
- ``governance_mod_guard`` hook (ADR-043 §3.3) — Tier 2 sign-off.
- Any tier-discrimination check across the QA pipeline.

This module ships the schema only. File-validation (existence of the
registry, signing-key-presence enforcement for ``MAINTAINER`` tier,
de-duplication across entries) is layered on top in TC-1C.3 per the
Phase 1 investigation SUMMARY (Q1A.5: manager default — schema-only).

References
----------
ADR-042 §25.1 — identity registry design rationale.
ADR-042 §25.3 (lines 2957-3010) — authoritative pydantic models
(verbatim source for this file).
ADR-042 §25.4 — tier matrix consumed by the registry.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ADR-042 §25.3 verbatim imports ``GitHandle`` from ``.frontmatter``; the
# primitive's authoritative declaration is in ``._common`` (audit fix C1).
# Importing from ``_common`` directly satisfies mypy --strict's
# ``no_implicit_reexport`` policy without changing observable behaviour.
# Deviation recorded in the Phase 1A-b impl record per SUMMARY X3 policy.
from ._common import GitHandle


class HumanTier(StrEnum):
    """Human contributor classification per ADR-042 §25.4 tier matrix."""

    CONTRIBUTOR = "contributor"
    MAINTAINER = "maintainer"


#: Signing-key descriptor in ``algo:key-material`` form. The algorithm
#: prefix is one of ``ed25519`` / ``rsa`` / ``ecdsa`` / ``gpg``; the
#: key material is base64-ish (``[A-Za-z0-9+/=._-]+``). Required for
#: ``MAINTAINER`` tier per ADR-042 §25.4; validation that the field is
#: actually populated for maintainers lives in the file-validation
#: layer (TC-1C.3) rather than as a model_validator here — Q1A.5 manager
#: default per Phase 1 investigation SUMMARY.
SigningKey = Annotated[str, Field(pattern=r"^(ed25519|rsa|ecdsa|gpg):[A-Za-z0-9+/=._-]+$")]


class HumanIdentity(BaseModel):
    """Single entry in ``docs/identity/humans.yml``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    github: GitHandle
    email: EmailStr
    tier: HumanTier
    signing_key: SigningKey | None = None
    joined: date
    notes: str | None = None

    @property
    def requires_signing_key(self) -> bool:
        """Tier 2 humans must have a signing key registered."""
        return self.tier == HumanTier.MAINTAINER


class IdentityRegistry(BaseModel):
    """Full ``docs/identity/humans.yml`` file."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    humans: list[HumanIdentity]

    def lookup_by_email(self, email: str) -> HumanIdentity | None:
        """Return the registry entry with matching ``email``, else None."""
        for h in self.humans:
            if h.email == email:
                return h
        return None

    def lookup_by_github(self, github: GitHandle) -> HumanIdentity | None:
        """Return the registry entry with matching ``github`` handle, else None."""
        for h in self.humans:
            if h.github == github:
                return h
        return None
