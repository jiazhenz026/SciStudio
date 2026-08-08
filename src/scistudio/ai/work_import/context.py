"""The session context the "Bring in my work" dialog collects.

ADR-053 spec 2 (``docs/specs/adr-053-work-import.md``) FR-021 and FR-023: every
answer the dialog collects reaches the agent's brief, and a *skipped* question is
conveyed as skipped rather than omitted, so the agent can tell "the user did not
say" from "the user said nothing applies". That distinction is the reason
``skipped`` is a field of its own rather than being inferred from a null answer.

Field names, types, and order are fixed by contract C2 in
``docs/planning/adr-053-work-import-checklist.md`` §7.2. The dialog (frontend),
the session endpoint (``POST /api/work-import/sessions``), and
:func:`scistudio.ai.work_import.brief.compose_brief` are written against this
exact shape, so a rename here breaks three call sites at once.

Layering: ``scistudio.ai.work_import`` is a leaf. It must not import from
``scistudio.api`` or ``scistudio.blocks`` (contract C2, and the "AI must not
depend on api" import-linter contract in ``pyproject.toml``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

DestinationTier = Literal["project", "user_library"]
"""Where a session's blocks and types land (FR-011)."""

PermissionMode = Literal["safe", "bypass"]
"""The agent permission mode chosen in the dialog (FR-041).

This is the *backend* spelling used by the PTY spawn. The frontend union is
``"safe" | "dangerous"`` and is mapped at the request boundary (checklist §7.4).
"""

DESTINATION_TIERS: Final[tuple[DestinationTier, ...]] = ("project", "user_library")
"""Valid :attr:`ImportSessionContext.destination_tier` values, in the order the
two alternatives appear in the brief template's destination substitution point."""

PERMISSION_MODES: Final[tuple[PermissionMode, ...]] = ("safe", "bypass")
"""Valid :attr:`ImportSessionContext.permission_mode` values."""

SKIPPABLE_QUESTIONS: Final[tuple[str, ...]] = (
    "workflow_description",
    "interaction_wishes",
    "other_software",
)
"""The questions FR-020 allows the user to skip.

Question 1 (``data_kinds``), the destination tier, and the source-or-no-codebase
choice are required, so they are not members here. Question 2
(``workflow_description``) is skippable only in codebase mode (FR-016, FR-017);
that conditionality is enforced by the dialog, not by this dataclass, which
records what the user actually did.
"""


@dataclass(frozen=True)
class ImportSessionContext:
    """Everything the "Bring in my work" dialog collects for one session.

    Frozen because the brief is composed from it and then written to disk before
    the session is spawned (FR-024); nothing downstream may mutate the record of
    what the user was asked and what they answered.

    ``data_kinds`` and ``skipped`` are normalised to a tuple and a frozenset so a
    caller deserialising a JSON request body can pass the lists it decoded.

    Raises:
        ValueError: if the context describes a state the dialog cannot produce —
            an unknown destination tier or permission mode, an unknown skippable
            question, a source location supplied alongside "I don't have a
            codebase" (or neither supplied, against FR-020), or a question marked
            skipped that nevertheless carries an answer.
    """

    source_location: str | None
    has_no_codebase: bool
    destination_tier: DestinationTier
    data_kinds: tuple[str, ...]
    data_kinds_other: str | None
    workflow_description: str | None
    interaction_wishes: str | None
    other_software: str | None
    skipped: frozenset[str]
    provider: str
    permission_mode: PermissionMode

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_kinds", tuple(self.data_kinds))
        object.__setattr__(self, "skipped", frozenset(self.skipped))

        if self.destination_tier not in DESTINATION_TIERS:
            raise ValueError(f"destination_tier must be one of {DESTINATION_TIERS!r}, got {self.destination_tier!r}")
        if self.permission_mode not in PERMISSION_MODES:
            raise ValueError(f"permission_mode must be one of {PERMISSION_MODES!r}, got {self.permission_mode!r}")
        if not self.provider.strip():
            raise ValueError("provider must be a non-empty provider-registry key (FR-040, FR-044)")

        unknown = sorted(self.skipped - set(SKIPPABLE_QUESTIONS))
        if unknown:
            raise ValueError(f"skipped may only name {SKIPPABLE_QUESTIONS!r}; got unknown entries {unknown!r}")

        has_source = bool((self.source_location or "").strip())
        if self.has_no_codebase and has_source:
            raise ValueError(
                'has_no_codebase is set, so source_location must be empty: "I don\'t have a codebase" '
                "hides the source field (FR-010)"
            )
        if not self.has_no_codebase and not has_source:
            raise ValueError(
                "a source location is required unless has_no_codebase is set (FR-020); the dialog offers "
                'the explicit "I don\'t have a codebase" option for that case (FR-009)'
            )

        for question in sorted(self.skipped):
            answer = getattr(self, question)
            if (answer or "").strip():
                raise ValueError(
                    f"{question!r} is marked skipped but carries an answer; a question is either answered "
                    "or skipped, never both (FR-021)"
                )

    def is_skipped(self, question: str) -> bool:
        """Whether ``question`` reaches the brief as skipped rather than answered.

        A question is skipped when the user pressed its skip control *or* left it
        blank: FR-021 gives the brief two renderings, the answer and the skip
        wording, so a blank answer can only be conveyed as "they did not say".
        """
        if question not in SKIPPABLE_QUESTIONS:
            raise ValueError(f"{question!r} is not a skippable question; expected one of {SKIPPABLE_QUESTIONS!r}")
        return question in self.skipped or not (getattr(self, question) or "").strip()
