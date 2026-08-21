"""Tests for the "Bring in my work" task brief (ADR-053 spec 2, issue #2002).

The brief is the feature: almost nothing about an import session is enforced by
code, so what the agent is told is what determines the outcome. These tests pin
the three properties that carry that weight:

* **Fidelity.** ``brief_template.md`` is spec §4.6's fenced block verbatim, and
  the composed brief differs from it only inside "What they told us" (FR-026).
* **Context.** Each question reaches the agent with its own text, its examples,
  and the preset options the user was shown, so an answer is read in the context
  it was given.
* **Skips.** A question the user did not answer arrives marked as skipped rather
  than missing, so the agent can tell "they did not say" from "they said nothing
  applies" (FR-021).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scistudio.ai.work_import import (
    ANSWERS_HEADING,
    DESTINATION_TIERS,
    SECTION_AFTER_ANSWERS,
    SKIPPABLE_QUESTIONS,
    ImportSessionContext,
    compose_brief,
    load_brief_template,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "specs" / "adr-053-work-import.md"
TEMPLATE_PATH = REPO_ROOT / "src" / "scistudio" / "ai" / "work_import" / "brief_template.md"

PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _extract_spec_section_4_6() -> str:
    """Return the fenced markdown block inside spec §4.6, mechanically.

    This is the transcription's source of truth. If issue #2017 edits §4.6, this
    test fails until ``brief_template.md`` is re-transcribed — which is exactly
    what FR-026 requires, since a paraphrase or a stale copy is the drift §4.6 is
    written as literal text to prevent.
    """
    assert SPEC_PATH.exists(), f"spec not found at {SPEC_PATH}; FR-026 fidelity cannot be checked"
    lines = SPEC_PATH.read_text(encoding="utf-8").split("\n")
    heading = next(i for i, line in enumerate(lines) if line.strip() == "### 4.6 The Task Brief")
    opening = next(i for i in range(heading, len(lines)) if lines[i] == "```markdown")
    closing = next(i for i in range(opening + 1, len(lines)) if lines[i] == "```")
    return "\n".join(lines[opening + 1 : closing]) + "\n"


def _answers_section(brief: str) -> str:
    return brief[brief.index(ANSWERS_HEADING) : brief.index(SECTION_AFTER_ANSWERS)]


def _outside_answers_section(brief: str) -> tuple[str, str]:
    return (
        brief[: brief.index(ANSWERS_HEADING)],
        brief[brief.index(SECTION_AFTER_ANSWERS) :],
    )


def make_context(**overrides: object) -> ImportSessionContext:
    """A fully answered codebase-mode context, with per-test overrides."""
    fields: dict[str, object] = {
        "source_location": "/home/ana/lab/pipeline",
        "has_no_codebase": False,
        "destination_tier": "project",
        "data_kinds": ("Image", "Time series"),
        "data_kinds_other": "cryo-EM tilt series",
        "workflow_description": "Load TIFFs, subtract background, segment, then measure per-cell intensity.",
        "interaction_wishes": "Picking the background region by eye.",
        "other_software": "Fiji and CellProfiler",
        "anything_else": "The folder names carry the plate id, so please keep them.",
        "skipped": frozenset(),
        "provider": "claude-code",
        "permission_mode": "safe",
    }
    fields.update(overrides)
    return ImportSessionContext(**fields)  # type: ignore[arg-type]


ALL_SKIPPED: dict[str, object] = {
    "workflow_description": None,
    "interaction_wishes": None,
    "other_software": None,
    "anything_else": None,
    "skipped": frozenset(SKIPPABLE_QUESTIONS),
}
"""Overrides for the user who skipped every skippable question (SC-006)."""


# --------------------------------------------------------------------------
# Fidelity to spec §4.6 (FR-026)
# --------------------------------------------------------------------------


def test_brief_template_is_verbatim_spec_section_4_6() -> None:
    """The template is §4.6's fenced block, character for character."""
    assert TEMPLATE_PATH.read_text(encoding="utf-8") == _extract_spec_section_4_6()


def test_loaded_template_is_the_transcribed_file() -> None:
    """``load_brief_template`` reads the packaged transcription, not a copy."""
    assert load_brief_template() == _extract_spec_section_4_6()


def test_template_answers_section_carries_exactly_the_expected_placeholders() -> None:
    """§4.6 defines eight substitution points, all inside "What they told us"."""
    template = load_brief_template()
    assert len(PLACEHOLDER_RE.findall(_answers_section(template))) == 8

    before, after = _outside_answers_section(template)
    # The only braces elsewhere are the literal ``{project}`` destination paths
    # in "What to deliver" — path text the agent reads, not substitution points.
    assert set(PLACEHOLDER_RE.findall(before)) == {"{project}"}
    assert PLACEHOLDER_RE.findall(after) == []


@pytest.mark.parametrize(
    "context",
    [
        pytest.param(make_context(), id="codebase-fully-answered"),
        pytest.param(
            make_context(destination_tier="user_library", **ALL_SKIPPED),
            id="codebase-everything-skipped",
        ),
        pytest.param(
            make_context(
                source_location=None,
                has_no_codebase=True,
                data_kinds=(),
                data_kinds_other=None,
                interaction_wishes=None,
                other_software=None,
                anything_else=None,
                skipped=frozenset({"interaction_wishes", "other_software", "anything_else"}),
                provider="codex",
                permission_mode="bypass",
            ),
            id="no-codebase",
        ),
    ],
)
def test_composed_brief_is_verbatim_outside_the_answers_section(context: ImportSessionContext) -> None:
    """FR-026: only the final section changes; everything else is §4.6's own text."""
    composed = compose_brief(context)
    assert _outside_answers_section(composed) == _outside_answers_section(load_brief_template())


@pytest.mark.parametrize(
    "context",
    [
        pytest.param(make_context(), id="fully-answered"),
        pytest.param(make_context(**ALL_SKIPPED), id="everything-skipped"),
    ],
)
def test_no_placeholder_survives_composition(context: ImportSessionContext) -> None:
    """A brief handed to an agent with an unfilled ``{...}`` is a broken session."""
    assert PLACEHOLDER_RE.findall(_answers_section(compose_brief(context))) == []


# --------------------------------------------------------------------------
# Each question reaches the agent in the context it was asked in
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question_text",
    [
        "*What kind of data do you usually work with?*",
        "*Briefly describe your analysis workflow",
        "*Which steps would you like to be able to interact with, or see the",
        "*Which other data analysis software do you use regularly?*",
        "*Is there anything else you want to tell the agent before it",
    ],
)
def test_each_question_is_reproduced_as_the_user_saw_it(question_text: str) -> None:
    assert question_text in _answers_section(compose_brief(make_context()))


@pytest.mark.parametrize(
    "example",
    [
        "choosing a background region to subtract",
        "fixing a\nsegmentation mask by hand",
    ],
)
def test_question_3_carries_its_examples(example: str) -> None:
    """FR-018: without the examples the question is too abstract to read an answer against."""
    assert example in _answers_section(compose_brief(make_context()))


DATA_KIND_PRESETS = [
    "Array",
    "Table / dataframe",
    "Series",
    "Image",
    "Time series",
    "Spectrum",
    "Multi-omics",
    "Spatial omics",
]
"""The eight options question 1 offers, as spec §4.6 reproduces them.

Written out here, and pinned against the dialog's own list by
``test_the_dialogs_preset_labels_are_the_ones_the_brief_reproduces``, because
the property that matters is not that any one copy is right — it is that all
three agree.
"""


@pytest.mark.parametrize("preset", DATA_KIND_PRESETS)
def test_question_1_offers_its_preset_options_to_the_agent(preset: str) -> None:
    """What the user did *not* select is informative, so every option is shown."""
    assert preset in _answers_section(compose_brief(make_context(data_kinds=(), skipped=frozenset())))


COPY_TS_PATH = REPO_ROOT / "frontend" / "src" / "components" / "BringInMyWorkDialog.parts" / "copy.ts"


def _dialog_preset_labels() -> list[str]:
    """The option strings from ``DATA_KIND_GROUPS`` in the dialog's copy module.

    Read out of the TypeScript source rather than imported: there is no shared
    build step between the two languages, and this is the cheap direction — the
    brief's side of the property is Python, spec §4.6 is a file this suite
    already parses, and a Python test can read a ``.ts`` file with no toolchain
    at all. A vitest test would have to reach the spec AND the template AND
    agree with this suite about how §4.6 is extracted.
    """
    source = COPY_TS_PATH.read_text(encoding="utf-8")
    start = source.index("export const DATA_KIND_GROUPS")
    declaration = source[start : source.index("\n];", start)]
    labels: list[str] = []
    # One `options: [...]` per group, in declaration order — which is the order
    # the user reads them in, so it is part of what is being pinned.
    for block in re.findall(r"options:\s*\[([^\]]*)\]", declaration, re.DOTALL):
        labels.extend(re.findall(r'"([^"]+)"', block))
    assert labels, f"no preset options found in {COPY_TS_PATH}; the declaration's shape changed"
    return labels


def test_the_dialogs_preset_labels_are_the_ones_the_brief_reproduces() -> None:
    """The eight options are the same strings on both sides of the boundary.

    ``copy.ts`` states the property in as many words — "The option labels are
    reproduced verbatim in the brief's 'What they told us' section (spec §4.6),
    so what the user saw and what the agent reads are the same strings" — and
    until now nothing enforced it. The brief's own preamble depends on it: it
    tells the agent each question is reproduced "as they saw it, including the
    examples and options we offered them", so an edit to either list on its own
    makes the brief misreport what the user was actually shown, silently and in
    the one direction nobody would look.

    Order is asserted too, not just membership: the brief lists the options in
    one line and the user read them in one order.
    """
    assert _dialog_preset_labels() == DATA_KIND_PRESETS


def _dialog_string_constant(name: str) -> str:
    """The value of a single ``export const <name> = "…" + "…";`` in ``copy.ts``.

    Read out of the TypeScript source for the same reason
    :func:`_dialog_preset_labels` is: the property being pinned spans the two
    languages, and this side is the one that can read a ``.ts`` file with no
    toolchain. The copy module wraps its longer strings across lines with ``+``,
    so the segments are concatenated back together here.
    """
    source = COPY_TS_PATH.read_text(encoding="utf-8")
    start = source.index(f"export const {name} =")
    declaration = source[start : source.index(";", start)]
    segments = re.findall(r'"((?:[^"\\]|\\.)*)"', declaration)
    assert segments, f"{name} not found as a string constant in {COPY_TS_PATH}"
    return "".join(segments)


def _unwrapped(text: str) -> str:
    """Collapse the template's soft line wrapping, as the dialog's copy has none."""
    return re.sub(r"\s+", " ", text)


@pytest.mark.parametrize("constant", ["Q5_LABEL", "Q5_HELP"])
def test_question_5_reaches_the_agent_in_the_dialogs_own_words(constant: str) -> None:
    """FR-019a: question 5 is open, so its wording is the whole of what was asked.

    The other four questions each name a subject, and an agent reading a short
    answer to one of them can tell what it is an answer to. Question 5 names
    nothing: without the prompt the user actually saw — the question and the
    line under it listing the kinds of thing it wanted — an answer like "the
    plate ids matter" arrives with no indication of what it was a reply to.

    So both strings are pinned, and they are pinned in the direction that can
    silently go wrong: the dialog is what the user read, and §4.6 is what the
    agent is told they read.
    """
    answers = _unwrapped(_answers_section(compose_brief(make_context())))
    assert _unwrapped(_dialog_string_constant(constant)) in answers


@pytest.mark.parametrize("preset", DATA_KIND_PRESETS)
def test_each_preset_label_appears_in_spec_section_4_6(preset: str) -> None:
    """The third copy — the spec's own prose list — agrees with the other two.

    ``test_brief_template_is_verbatim_spec_section_4_6`` already ties the
    template to §4.6, so this closes the triangle: dialog == template == spec.
    """
    assert preset in _extract_spec_section_4_6()


def test_selected_presets_and_free_text_are_rendered_separately() -> None:
    answers = _answers_section(compose_brief(make_context()))
    assert "**They selected:** Image, Time series" in answers
    assert "**They added:** cryo-EM tilt series" in answers


def test_unselected_presets_and_missing_free_text_use_the_template_wording() -> None:
    answers = _answers_section(compose_brief(make_context(data_kinds=(), data_kinds_other=None)))
    assert "**They selected:** Nothing from the list." in answers
    assert "**They added:** Nothing." in answers


# --------------------------------------------------------------------------
# Skipped is conveyed, never omitted (FR-021)
# --------------------------------------------------------------------------

SKIP_WORDING = {
    "workflow_description": "Skipped. They did not answer this.",
    "interaction_wishes": (
        "Skipped. They did not answer this — which means we do not know, not that there are none. "
        "Work out for yourself where a human judgement is being made, and propose it."
    ),
    "other_software": "Skipped. They did not answer this.",
    "anything_else": "Skipped. They did not answer this.",
}


@pytest.mark.parametrize("question", SKIPPABLE_QUESTIONS)
def test_skipped_question_renders_as_explicitly_skipped(question: str) -> None:
    """The agent must be able to tell "they did not say" from "nothing applies"."""
    context = make_context(**{question: None}, skipped=frozenset({question}))
    answers = _answers_section(compose_brief(context))
    assert SKIP_WORDING[question] in answers


@pytest.mark.parametrize("question", SKIPPABLE_QUESTIONS)
def test_skipped_question_keeps_its_prompt_rather_than_being_omitted(question: str) -> None:
    """The question and its answer slot both stay; only the answer is replaced."""
    skipped = compose_brief(make_context(**{question: None}, skipped=frozenset({question})))
    answered = compose_brief(make_context())
    assert _answers_section(skipped).count("**We asked:**") == _answers_section(answered).count("**We asked:**")
    assert _answers_section(skipped).count("**They said:**") == _answers_section(answered).count("**They said:**")


@pytest.mark.parametrize("question", SKIPPABLE_QUESTIONS)
def test_blank_answer_is_conveyed_as_skipped(question: str) -> None:
    """A blank answer has only one honest rendering: they did not say."""
    context = make_context(**{question: "   "})
    assert SKIP_WORDING[question] in _answers_section(compose_brief(context))


def test_interaction_skip_tells_the_agent_to_work_it_out_itself() -> None:
    """§4.6's skip wording for question 3 is not a generic "skipped" marker."""
    context = make_context(interaction_wishes=None, skipped=frozenset({"interaction_wishes"}))
    answers = _answers_section(compose_brief(context))
    assert "which means we do not know, not that there are none" in answers
    assert "Work out for yourself where a human judgement is being made" in answers


def test_every_optional_question_can_be_skipped_at_once() -> None:
    """SC-006: skipping everything still produces a brief that distinguishes skips."""
    answers = _answers_section(compose_brief(make_context(**ALL_SKIPPED)))
    assert answers.count("Skipped. They did not answer this.") == 3
    assert SKIP_WORDING["interaction_wishes"] in answers


# --------------------------------------------------------------------------
# Source and destination
# --------------------------------------------------------------------------


def test_source_location_reaches_the_brief() -> None:
    assert "**Where their work is:** /home/ana/lab/pipeline" in _answers_section(compose_brief(make_context()))


def test_no_codebase_uses_the_template_wording_for_a_missing_source() -> None:
    """FR-009: the no-codebase path is first class, not a blank field."""
    context = make_context(source_location=None, has_no_codebase=True)
    answers = _answers_section(compose_brief(context))
    assert "**Where their work is:** They said they do not have a codebase." in answers


@pytest.mark.parametrize(
    ("tier", "expected", "not_expected"),
    [
        ("project", "**Where the results should go:** this project only", "their personal library"),
        (
            "user_library",
            "**Where the results should go:** their personal library, available in every project",
            "**Where the results should go:** this project only",
        ),
    ],
)
def test_each_destination_tier_renders_its_own_answer(tier: str, expected: str, not_expected: str) -> None:
    answers = _answers_section(compose_brief(make_context(destination_tier=tier)))
    assert expected in answers
    assert not_expected not in answers


@pytest.mark.parametrize("tier", DESTINATION_TIERS)
def test_both_tiers_carry_the_full_destination_guidance(tier: str) -> None:
    """§4.6's "Where things go" guidance is fixed text, so it reaches both tiers.

    This is what carries the library-mode constraint (FR-026): a personal-library
    block must not depend on a project-local type, and a personal-library
    previewer must not depend on one either (#2017 added the user tier).
    """
    brief = compose_brief(make_context(destination_tier=tier))
    assert "A block in the personal library must not depend on a type that only exists in" in brief
    assert "A previewer in the personal library must not depend on a type that only" in brief


# --------------------------------------------------------------------------
# Every collected answer reaches the brief (FR-023)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "/home/ana/lab/pipeline",
        "Image, Time series",
        "cryo-EM tilt series",
        "Load TIFFs, subtract background, segment, then measure per-cell intensity.",
        "Picking the background region by eye.",
        "Fiji and CellProfiler",
        "The folder names carry the plate id, so please keep them.",
    ],
)
def test_every_collected_answer_reaches_the_brief(answer: str) -> None:
    """No answer the dialog collects may be silently dropped."""
    assert answer in _answers_section(compose_brief(make_context()))


def test_multiline_free_text_survives_composition() -> None:
    description = "Step 1: import the plate reader export.\nStep 2: drop the blank wells.\nStep 3: fit the curve."
    assert description in compose_brief(make_context(workflow_description=description))


def test_provider_and_permission_mode_stay_out_of_the_brief_body() -> None:
    """FR-026 gives them no placeholder, and FR-044 sends them to the spawn instead.

    They are session configuration, not an answer about the user's work: §4.4's
    "Brief composition" row asks for every *dialog answer* and the source
    location. Adding a line for them would put text in the brief that §4.6 does
    not contain, which FR-026 forbids.
    """
    brief = compose_brief(make_context(provider="codex", permission_mode="bypass"))
    assert "codex" not in brief
    assert "bypass" not in brief


# --------------------------------------------------------------------------
# ImportSessionContext (checklist §7.2 contract C2)
# --------------------------------------------------------------------------


def test_context_matches_contract_c2_field_names_and_order() -> None:
    """A3 and A4 write producers of this shape; a rename breaks both."""
    from dataclasses import fields

    assert tuple(f.name for f in fields(ImportSessionContext)) == (
        "source_location",
        "has_no_codebase",
        "destination_tier",
        "data_kinds",
        "data_kinds_other",
        "workflow_description",
        "interaction_wishes",
        "other_software",
        "anything_else",
        "skipped",
        "provider",
        "permission_mode",
    )


def test_context_normalises_decoded_json_collections() -> None:
    """A request body decodes lists; the contract stores a tuple and a frozenset."""
    context = make_context(data_kinds=["Image"], skipped=["other_software"], other_software=None)
    assert context.data_kinds == ("Image",)
    assert context.skipped == frozenset({"other_software"})


def test_context_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        make_context().source_location = "/elsewhere"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param({"destination_tier": "user-library"}, "destination_tier", id="unknown-tier"),
        pytest.param({"permission_mode": "dangerous"}, "permission_mode", id="frontend-permission-spelling"),
        pytest.param({"provider": "  "}, "provider", id="blank-provider"),
        pytest.param({"skipped": frozenset({"data_kinds"})}, "skipped may only name", id="unskippable-question"),
        pytest.param({"has_no_codebase": True}, "source_location must be empty", id="source-and-no-codebase"),
        pytest.param({"source_location": None}, "source location is required", id="neither-source-nor-no-codebase"),
        pytest.param(
            {"skipped": frozenset({"other_software"})},
            "marked skipped but carries an answer",
            id="skipped-and-answered",
        ),
    ],
)
def test_context_rejects_states_the_dialog_cannot_produce(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        make_context(**overrides)


def test_is_skipped_covers_both_the_skip_control_and_a_blank_answer() -> None:
    assert make_context(other_software=None, skipped=frozenset({"other_software"})).is_skipped("other_software")
    assert make_context(other_software="   ").is_skipped("other_software")
    assert not make_context().is_skipped("other_software")
    with pytest.raises(ValueError, match="not a skippable question"):
        make_context().is_skipped("data_kinds")


# --------------------------------------------------------------------------
# Layering (contract C2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", ["scistudio.api", "scistudio.blocks"])
def test_work_import_is_a_leaf_package(forbidden: str) -> None:
    """The endpoint imports this package, so the edge must not run the other way."""
    package_dir = REPO_ROOT / "src" / "scistudio" / "ai" / "work_import"
    offenders = [
        path.name
        for path in sorted(package_dir.glob("*.py"))
        if re.search(rf"^\s*(from|import)\s+{re.escape(forbidden)}\b", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert offenders == []
