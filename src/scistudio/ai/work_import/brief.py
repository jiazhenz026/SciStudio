"""Composition of the "Bring in my work" agent task brief.

FR-026 (``docs/specs/adr-053-work-import.md``) states that the brief's content is
the text in spec §4.6 **verbatim**, with the user's answers substituted into its
final section. §4.6 is given as literal text rather than as a set of requirements
precisely so that no reconstitution step can drift from it, so this module never
writes brief prose of its own: ``brief_template.md`` is a byte-for-byte
transcription of §4.6's fenced block, and composition only fills the ``{...}``
substitution points §4.6 already shows in its "What they told us" section.

Two consequences follow, and both are deliberate:

* **The skip wording is read out of the template, not restated here.** Each
  answer marker has the form ``{<answer>, or "<what to say instead>"}``.
  When a question was skipped, the quoted alternative *from the template* is what
  reaches the agent, so FR-021's "conveyed as skipped rather than omitted"
  wording stays owned by §4.6 and cannot drift from it.
* **Nothing outside the answers section is substituted.** The four ``{project}``
  occurrences in "What to deliver" are literal path text the agent reads, not
  substitution points, so the scan for them is bounded to the
  "What they told us" section.

The provider and permission mode carried on
:class:`~scistudio.ai.work_import.context.ImportSessionContext` are deliberately
**not** written into the brief body. §4.6 offers them no slot of their own, and FR-026
forbids adding one; they are session configuration consumed by the spawn
(FR-044), not an answer about the user's work (FR-023, and the "Brief
composition" row of §4.4).

Layering: ``scistudio.ai.work_import`` is a leaf. It must not import from
``scistudio.api`` or ``scistudio.blocks`` (contract C2).
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from typing import Final

from scistudio.ai.work_import.context import DESTINATION_TIERS, ImportSessionContext

BRIEF_TEMPLATE_PACKAGE: Final = "scistudio.ai.work_import"
BRIEF_TEMPLATE_FILENAME: Final = "brief_template.md"

ANSWERS_HEADING: Final = "# What they told us"
"""Start of the only section :func:`compose_brief` substitutes into (§4.6)."""

SECTION_AFTER_ANSWERS: Final = "# When things come up"
"""The heading that closes the answers section (§4.6)."""

_ANSWER_SLOTS: Final[tuple[str, ...]] = (
    "source_location",
    "destination_tier",
    "data_kinds",
    "data_kinds_other",
    "workflow_description",
    "interaction_wishes",
    "other_software",
    "anything_else",
)
"""The template's answer substitution points, in the order §4.6 presents them.

Three of them — question 2's, question 4's and question 5's — carry identical
text, so slots are matched positionally rather than by their contents.
"""

_MARKER_RE: Final = re.compile(r"\{[^{}]*\}", re.DOTALL)
_OR_FALLBACK_RE: Final = re.compile(r'^\{[^,]*,\s*or\s+"(?P<fallback>.*)"\s*\}$', re.DOTALL)
_SOFT_WRAP_RE: Final = re.compile(r"\s*\n\s*")
_CHOICE_SEPARATOR: Final = "|"


class BriefTemplateError(RuntimeError):
    """The brief template no longer has the shape composition requires.

    Raised rather than silently producing a brief with an unfilled marker or
    a dropped answer: a session's only source of instructions is the brief file
    (FR-024), so a half-composed brief is unrecoverable.
    """


@lru_cache(maxsize=1)
def load_brief_template() -> str:
    """Return ``brief_template.md`` — spec §4.6's fenced block, verbatim."""
    resource = resources.files(BRIEF_TEMPLATE_PACKAGE).joinpath(BRIEF_TEMPLATE_FILENAME)
    return resource.read_text(encoding="utf-8")


def compose_brief(context: ImportSessionContext) -> str:
    """Compose the task brief for one import session.

    Returns spec §4.6's text with the dialog's answers substituted into its
    "What they told us" section (FR-023, FR-026). Every other character is the
    template's own, including the four ``{project}`` path literals earlier in the
    document.

    Raises:
        BriefTemplateError: if the template's answers section does not present
            exactly the substitution points §4.6 defines, or one of them is not
            in either form composition understands.
    """
    template = load_brief_template()
    prefix, answers, suffix = _split_answers_section(template)

    markers = list(_MARKER_RE.finditer(answers))
    if len(markers) != len(_ANSWER_SLOTS):
        raise BriefTemplateError(
            f"{BRIEF_TEMPLATE_FILENAME} answers section has {len(markers)} substitution points, "
            f"expected {len(_ANSWER_SLOTS)} ({', '.join(_ANSWER_SLOTS)}). "
            "Re-transcribe the template from docs/specs/adr-053-work-import.md §4.6."
        )

    parts: list[str] = []
    cursor = 0
    for slot, marker in zip(_ANSWER_SLOTS, markers, strict=True):
        parts.append(answers[cursor : marker.start()])
        parts.append(_render_slot(slot, marker.group(0), context))
        cursor = marker.end()
    parts.append(answers[cursor:])

    return prefix + "".join(parts) + suffix


def _split_answers_section(template: str) -> tuple[str, str, str]:
    """Split the template into (before, answers section, after)."""
    start = _heading_offset(template, ANSWERS_HEADING)
    end = _heading_offset(template, SECTION_AFTER_ANSWERS)
    if end < start:
        raise BriefTemplateError(f"{SECTION_AFTER_ANSWERS!r} precedes {ANSWERS_HEADING!r} in {BRIEF_TEMPLATE_FILENAME}")
    return template[:start], template[start:end], template[end:]


def _heading_offset(template: str, heading: str) -> int:
    match = re.search(rf"^{re.escape(heading)}$", template, re.MULTILINE)
    if match is None:
        raise BriefTemplateError(
            f"{BRIEF_TEMPLATE_FILENAME} has no {heading!r} heading. "
            "Re-transcribe the template from docs/specs/adr-053-work-import.md §4.6."
        )
    return match.start()


def _render_slot(slot: str, marker: str, context: ImportSessionContext) -> str:
    """Render one substitution point from the context, or from the template's own fallback."""
    if slot == "source_location":
        if context.has_no_codebase:
            return _fallback(marker)
        return (context.source_location or "").strip()

    if slot == "destination_tier":
        return _choice(marker, DESTINATION_TIERS.index(context.destination_tier))

    if slot == "data_kinds":
        selected = [kind.strip() for kind in context.data_kinds if kind.strip()]
        return ", ".join(selected) if selected else _fallback(marker)

    return _answer_or_fallback(getattr(context, slot), marker)


def _answer_or_fallback(answer: str | None, marker: str) -> str:
    """The user's answer, or the template's wording for not having one (FR-021)."""
    text = (answer or "").strip()
    return text if text else _fallback(marker)


def _fallback(marker: str) -> str:
    """Extract the quoted alternative from a ``{<answer>, or "<...>"}`` marker.

    Taking the wording from the template rather than restating it here is what
    keeps FR-021's skip wording identical to §4.6's.
    """
    match = _OR_FALLBACK_RE.match(marker)
    if match is None:
        raise BriefTemplateError(
            f'{marker!r} is not of the form {{<answer>, or "<alternative>"}}. '
            "Re-transcribe the template from docs/specs/adr-053-work-import.md §4.6."
        )
    return _unwrap(match.group("fallback"))


def _choice(marker: str, index: int) -> str:
    """Pick one alternative from a ``{<a> | <b>}`` marker."""
    options = [_unwrap(option) for option in marker[1:-1].split(_CHOICE_SEPARATOR)]
    if len(options) != len(DESTINATION_TIERS):
        raise BriefTemplateError(
            f"{marker!r} offers {len(options)} alternatives, "
            f"expected {len(DESTINATION_TIERS)} ({', '.join(DESTINATION_TIERS)}). "
            "Re-transcribe the template from docs/specs/adr-053-work-import.md §4.6."
        )
    return options[index]


def _unwrap(text: str) -> str:
    """Collapse the template's soft line wrapping into a single line."""
    return _SOFT_WRAP_RE.sub(" ", text).strip()
