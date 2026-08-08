"""The "Bring in my work" agent task brief (ADR-053 spec 2, issue #2002).

The feature is a toolbar entry that spawns a preconfigured agent session; almost
nothing about the session is enforced by code, so the brief the agent receives is
what makes the feature work. This package owns two things and nothing else:

* :class:`~scistudio.ai.work_import.context.ImportSessionContext` — the answers
  the dialog collected, in the shape the endpoint and the dialog both use.
* :func:`~scistudio.ai.work_import.brief.compose_brief` — spec §4.6's text with
  those answers substituted into its final section (FR-021, FR-023, FR-026).

Writing the brief to disk and spawning the session belong to the work-import
session endpoint, not here: this package is a leaf and must not import from
``scistudio.api`` or ``scistudio.blocks``
(``docs/planning/adr-053-work-import-checklist.md`` §7.2).
"""

from scistudio.ai.work_import.brief import (
    ANSWERS_HEADING,
    BRIEF_TEMPLATE_FILENAME,
    SECTION_AFTER_ANSWERS,
    BriefTemplateError,
    compose_brief,
    load_brief_template,
)
from scistudio.ai.work_import.context import (
    DESTINATION_TIERS,
    PERMISSION_MODES,
    SKIPPABLE_QUESTIONS,
    DestinationTier,
    ImportSessionContext,
    PermissionMode,
)

__all__ = [
    "ANSWERS_HEADING",
    "BRIEF_TEMPLATE_FILENAME",
    "DESTINATION_TIERS",
    "PERMISSION_MODES",
    "SECTION_AFTER_ANSWERS",
    "SKIPPABLE_QUESTIONS",
    "BriefTemplateError",
    "DestinationTier",
    "ImportSessionContext",
    "PermissionMode",
    "compose_brief",
    "load_brief_template",
]
