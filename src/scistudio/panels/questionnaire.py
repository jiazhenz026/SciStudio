"""MiniApp questionnaires: the spec, the answers file, and the check an agent runs."""
# MiniApp questionnaires (ADR-054 MiniApp FR-049 to FR-054, #2447).
#
# Before an agent builds a MiniApp it may ask the user what they want. It
# declares the questions as data in ``panels/<id>/questionnaire.json``; the
# page renders them with the SDK's ``Questionnaire`` component and submits
# with ``scistudio.submitAnswers``; the backend normalizes the submission
# against the same spec and writes ``panels/<id>/answers.json``.
#
# This module is the one authority on what a valid spec and a valid submission
# are. The submit route, ``validate_panel``, and ``wait_for_answers`` all call
# it, and the JavaScript component mirrors the spec rules only to show a visible
# error state instead of a silently broken form. The shared cases in
# ``tests/fixtures/questionnaire/cases.json`` keep the two in step.
#
# Every question is optional and every question offers "Decide for me". Both
# are properties of the format, not of a spec: a spec cannot make a question
# required or hide the decide-for-me choice, and the check refuses one that
# tries, so a questionnaire the agent writes always has those two properties.

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeGuard

#: The spec file, beside the MiniApp's ``panel.json``.
QUESTIONNAIRE_FILE = "questionnaire.json"
#: The answers file the submit route writes, beside the spec.
ANSWERS_FILE = "answers.json"
#: Version of the answers document.
ANSWERS_VERSION = 1
#: The reserved answer status and option value for "Decide for me".
DECIDE_FOR_ME = "decide_for_me"
#: The answer statuses a submission may carry.
ANSWER_STATUSES = ("answered", DECIDE_FOR_ME, "skipped")
#: The question types the component renders.
QUESTION_TYPES = ("single", "multiple", "text", "number", "range")

MAX_QUESTIONS = 50
MAX_OPTIONS = 30
MAX_TEXT_CHARS = 4000
MAX_SPEC_BYTES = 256 * 1024

_ID = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_TOP_KEYS = {"title", "intro", "submit_label", "questions"}
_COMMON_KEYS = {"id", "type", "prompt", "help"}
_TYPE_KEYS: dict[str, set[str]] = {
    "single": {"options", "allow_other"},
    "multiple": {"options", "allow_other"},
    "text": {"multiline", "placeholder"},
    "number": {"min", "max", "step", "unit", "placeholder"},
    "range": {"min", "max", "step", "unit"},
}
_OPTION_KEYS = {"value", "label", "description"}


class QuestionnaireError(ValueError):
    """A submission that does not fit its questionnaire."""


def _is_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _nonempty_text(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _where(index: int, question: Any) -> str:
    qid = question.get("id") if isinstance(question, dict) else None
    return f"questions[{index}]" + (f' (id "{qid}")' if isinstance(qid, str) and qid else "")


def validate_spec(spec: Any) -> list[str]:
    """Every problem with a questionnaire spec, each naming where and how to fix it.

    An empty list means the spec renders: every question has a type the
    component draws, the fields that type needs, and nothing that would make it
    required or hide "Decide for me".
    """
    name = QUESTIONNAIRE_FILE
    if not isinstance(spec, dict):
        return [f"{name}: the top level must be a JSON object with 'title' and 'questions'."]
    problems: list[str] = []
    for key in sorted(set(spec) - _TOP_KEYS):
        problems.append(
            f"{name}: unknown top-level key '{key}'. Allowed keys are {sorted(_TOP_KEYS)}; remove or rename it."
        )
    if not _nonempty_text(spec.get("title")):
        problems.append(f"{name}: 'title' is missing or empty. Give the questionnaire a short title.")
    for key in ("intro", "submit_label"):
        if key in spec and not isinstance(spec[key], str):
            problems.append(f"{name}: '{key}' must be a string.")
    questions = spec.get("questions")
    if not isinstance(questions, list) or not questions:
        problems.append(f"{name}: 'questions' must be a non-empty list of question objects.")
        return problems
    if len(questions) > MAX_QUESTIONS:
        problems.append(f"{name}: {len(questions)} questions is more than {MAX_QUESTIONS}; ask fewer.")
    seen: dict[str, int] = {}
    for index, question in enumerate(questions):
        problems.extend(_question_problems(index, question, seen))
    return problems


def _question_problems(index: int, question: Any, seen: dict[str, int]) -> list[str]:
    name = QUESTIONNAIRE_FILE
    where = f"{name}: {_where(index, question)}"
    if not isinstance(question, dict):
        return [f"{where}: each question must be a JSON object."]
    problems: list[str] = []
    qid = question.get("id")
    if not isinstance(qid, str) or not _ID.fullmatch(qid):
        problems.append(
            f"{where}: 'id' must be lowercase letters, digits and underscores, starting with a letter "
            f"(for example 'chart_type')."
        )
    elif qid in seen:
        problems.append(
            f"{where}: id '{qid}' is already used by questions[{seen[qid]}]. Give each question its own id."
        )
    else:
        seen[qid] = index
    if "required" in question:
        problems.append(f"{where}: remove 'required'. Every question is optional; the user may skip any of them.")
    if DECIDE_FOR_ME in question or "decideForMe" in question:
        problems.append(f"{where}: remove '{DECIDE_FOR_ME}'. 'Decide for me' is always shown and cannot be turned off.")
    qtype = question.get("type")
    if qtype not in QUESTION_TYPES:
        problems.append(f"{where}: 'type' is {qtype!r}; use one of {list(QUESTION_TYPES)}.")
        return problems
    if not _nonempty_text(question.get("prompt")):
        problems.append(f"{where}: 'prompt' is missing or empty. Write the question the user reads.")
    if "help" in question and not isinstance(question["help"], str):
        problems.append(f"{where}: 'help' must be a string.")
    allowed = _COMMON_KEYS | _TYPE_KEYS[qtype]
    for key in sorted(set(question) - allowed - {"required", DECIDE_FOR_ME, "decideForMe"}):
        problems.append(
            f"{where}: key '{key}' does not apply to a '{qtype}' question. Allowed keys are {sorted(allowed)}."
        )
    if qtype in ("single", "multiple"):
        problems.extend(_option_problems(where, qtype, question))
    elif qtype == "text":
        for key in ("multiline",):
            if key in question and not isinstance(question[key], bool):
                problems.append(f"{where}: '{key}' must be true or false.")
        if "placeholder" in question and not isinstance(question["placeholder"], str):
            problems.append(f"{where}: 'placeholder' must be a string.")
    else:
        problems.extend(_number_problems(where, qtype, question))
    return problems


def _option_problems(where: str, qtype: str, question: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if "allow_other" in question and not isinstance(question["allow_other"], bool):
        problems.append(f"{where}: 'allow_other' must be true or false.")
    options = question.get("options")
    if not isinstance(options, list) or len(options) < 2:
        return [
            *problems,
            f"{where}: a '{qtype}' question needs 'options', a list of at least two {{\"value\": ..., \"label\": ...}} "
            f"objects — the alternative answers you suggest.",
        ]
    if len(options) > MAX_OPTIONS:
        problems.append(f"{where}: {len(options)} options is more than {MAX_OPTIONS}.")
    values: set[str] = set()
    for position, option in enumerate(options):
        at = f"{where} options[{position}]"
        if not isinstance(option, dict):
            problems.append(
                f'{at}: each option must be an object like {{"value": "scatter", "label": "Scatter plot"}}.'
            )
            continue
        for key in sorted(set(option) - _OPTION_KEYS):
            problems.append(f"{at}: unknown key '{key}'. Allowed keys are {sorted(_OPTION_KEYS)}.")
        value = option.get("value")
        if not _nonempty_text(value):
            problems.append(f"{at}: 'value' must be a non-empty string.")
        elif value == DECIDE_FOR_ME:
            problems.append(
                f"{at}: '{DECIDE_FOR_ME}' is reserved; 'Decide for me' is added for you. Remove this option."
            )
        elif value in values:
            problems.append(f"{at}: value '{value}' is repeated. Each option needs its own value.")
        else:
            values.add(value)
        if not _nonempty_text(option.get("label")):
            problems.append(f"{at}: 'label' must be a non-empty string — the text the user sees.")
        if "description" in option and not isinstance(option["description"], str):
            problems.append(f"{at}: 'description' must be a string.")
    return problems


def _number_problems(where: str, qtype: str, question: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for key in ("min", "max", "step"):
        if key in question and not _is_number(question[key]):
            problems.append(f"{where}: '{key}' must be a finite number.")
    for key in ("unit", "placeholder"):
        if key in question and not isinstance(question[key], str):
            problems.append(f"{where}: '{key}' must be a string.")
    low, high = question.get("min"), question.get("max")
    if qtype == "range" and not (_is_number(low) and _is_number(high)):
        problems.append(f"{where}: a 'range' question is a slider and needs both 'min' and 'max'.")
    if _is_number(low) and _is_number(high) and low >= high:
        problems.append(f"{where}: 'min' ({low}) must be less than 'max' ({high}).")
    if "step" in question and _is_number(question["step"]) and question["step"] <= 0:
        problems.append(f"{where}: 'step' must be greater than zero.")
    return problems


def load_spec(directory: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Read and validate ``questionnaire.json``; ``(None, [])`` when there is none."""
    path = Path(directory) / QUESTIONNAIRE_FILE
    if not path.is_file():
        return None, []
    try:
        if path.stat().st_size > MAX_SPEC_BYTES:
            return None, [f"{QUESTIONNAIRE_FILE}: larger than {MAX_SPEC_BYTES} bytes; ask fewer, shorter questions."]
        spec = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"{QUESTIONNAIRE_FILE}: not valid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}."]
    except (OSError, UnicodeDecodeError) as exc:
        return None, [f"{QUESTIONNAIRE_FILE}: cannot be read ({exc})."]
    problems = validate_spec(spec)
    return (spec if not problems else None), problems


def _normalize_one(question: dict[str, Any], raw: Any) -> dict[str, Any]:
    qid, qtype = question["id"], question["type"]
    entry: dict[str, Any] = {"id": qid, "type": qtype, "prompt": question["prompt"]}
    if raw is None:
        raw = {"status": "skipped"}
    if not isinstance(raw, dict) or raw.get("status") not in ANSWER_STATUSES:
        raise QuestionnaireError(f'Answer to "{qid}" must be an object whose status is one of {list(ANSWER_STATUSES)}')
    status = raw["status"]
    entry["status"] = status
    if status != "answered":
        extra = set(raw) - {"status"}
        if extra:
            raise QuestionnaireError(f'Answer to "{qid}" is {status} and cannot carry {sorted(extra)}')
        return entry
    value, other = raw.get("value"), raw.get("other")
    if set(raw) - {"status", "value", "other"}:
        raise QuestionnaireError(
            f'Answer to "{qid}" has unknown keys {sorted(set(raw) - {"status", "value", "other"})}'
        )
    if qtype in ("single", "multiple"):
        labels = {o["value"]: o["label"] for o in question["options"]}
        if other is not None:
            if not question.get("allow_other") or not _nonempty_text(other) or len(other) > MAX_TEXT_CHARS:
                raise QuestionnaireError(f'Answer to "{qid}" gives "other" text the question does not accept')
            entry["other"] = other.strip()
        if qtype == "single":
            if value is None and other is None:
                raise QuestionnaireError(f'Answer to "{qid}" is answered but has no value')
            if value is not None:
                if other is not None or value not in labels:
                    raise QuestionnaireError(f'Answer to "{qid}" must be one of {sorted(labels)} or "other" text')
                entry["value"], entry["label"] = value, labels[value]
        else:
            chosen = [] if value is None else value
            if not isinstance(chosen, list) or any(v not in labels for v in chosen) or len(set(chosen)) != len(chosen):
                raise QuestionnaireError(f'Answer to "{qid}" must be a list of distinct values from {sorted(labels)}')
            if not chosen and other is None:
                raise QuestionnaireError(f'Answer to "{qid}" is answered but chooses nothing')
            entry["value"], entry["labels"] = chosen, [labels[v] for v in chosen]
        return entry
    if other is not None:
        raise QuestionnaireError(f'Answer to "{qid}" cannot carry "other" text')
    if qtype == "text":
        if not _nonempty_text(value) or len(value) > MAX_TEXT_CHARS:
            raise QuestionnaireError(f'Answer to "{qid}" must be non-empty text of at most {MAX_TEXT_CHARS} characters')
        entry["value"] = value
        return entry
    if not _is_number(value):
        raise QuestionnaireError(f'Answer to "{qid}" must be a number')
    low, high = question.get("min"), question.get("max")
    if (_is_number(low) and value < low) or (_is_number(high) and value > high):
        raise QuestionnaireError(f'Answer to "{qid}" is outside {low}..{high}')
    entry["value"] = value
    return entry


def normalize_answers(spec: dict[str, Any], answers: Any) -> list[dict[str, Any]]:
    """Check a submission against its spec and return one entry per question, in order.

    A question the submission leaves out is ``skipped``; an id the spec does not
    have is refused, so a page cannot silently answer a question nobody asked.
    """
    if not isinstance(answers, dict):
        raise QuestionnaireError("Answers must be an object keyed by question id")
    questions = spec["questions"]
    known = {q["id"] for q in questions}
    unknown = sorted(set(answers) - known)
    if unknown:
        raise QuestionnaireError(f"Answers name questions the questionnaire does not have: {unknown}")
    return [_normalize_one(q, answers.get(q["id"])) for q in questions]


def answers_document(
    panel_id: str, spec: dict[str, Any], answers: Any, *, now: datetime | None = None
) -> dict[str, Any]:
    """The ``answers.json`` document for one submission."""
    stamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "version": ANSWERS_VERSION,
        "panel_id": panel_id,
        "title": spec["title"],
        "submitted_at": stamp,
        "answers": normalize_answers(spec, answers),
    }


def write_answers(directory: Path, document: dict[str, Any]) -> Path:
    """Write ``answers.json`` atomically, so a reader never sees half a file."""
    target = Path(directory) / ANSWERS_FILE
    handle, staging = tempfile.mkstemp(prefix=".answers-", suffix=".tmp", dir=str(directory))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(staging)
        raise
    return target


def _sample_answer(question: dict[str, Any], index: int) -> dict[str, Any]:
    """A valid answer for the round trip, cycling answered / decide / skipped."""
    status = ANSWER_STATUSES[index % len(ANSWER_STATUSES)] if index else "answered"
    if status != "answered":
        return {"status": status}
    qtype = question["type"]
    if qtype == "single":
        return {"status": "answered", "value": question["options"][0]["value"]}
    if qtype == "multiple":
        return {"status": "answered", "value": [o["value"] for o in question["options"][:2]]}
    if qtype == "text":
        return {"status": "answered", "value": "sample answer"}
    low = question.get("min")
    return {"status": "answered", "value": low if _is_number(low) else 1}


#: What a page must contain for a submit to be reachable from it.
_PAGE_MARKERS = (
    ("Questionnaire", "render the questionnaire with the Questionnaire component from ../../sdk/1/panel-ui.js"),
    (QUESTIONNAIRE_FILE, f"load the questions from {QUESTIONNAIRE_FILE} (fetch it beside the page)"),
    ("submitAnswers", "pass scistudio.submitAnswers to the Questionnaire as onSubmit"),
    ("scistudio-panel.js", "load the SDK with <script src='../../sdk/1/scistudio-panel.js'>"),
)


@dataclass
class QuestionnaireCheck:
    """What ``check_questionnaire`` found."""

    present: bool
    errors: list[str] = field(default_factory=list)
    question_count: int = 0
    statuses_exercised: list[str] = field(default_factory=list)
    round_trip: bool = False


def _page_sources(directory: Path) -> str:
    texts: list[str] = []
    for path in sorted(Path(directory).rglob("*")):
        if path.suffix.lower() in (".html", ".js", ".mjs") and "__pycache__" not in path.parts and path.is_file():
            try:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(texts)


def check_questionnaire(directory: Path, *, panel_id: str, contexts: tuple[str, ...], entry: str) -> QuestionnaireCheck:
    """Exercise a MiniApp's questionnaire the way the user's submit will.

    Validates the spec, confirms the page wires the component, the spec, and
    ``submitAnswers`` together, then submits a synthetic set of answers —
    one answered, one "Decide for me", one skipped, and so on through every
    question — through the same normalization the submit route uses and parses
    the resulting ``answers.json`` document back. Nothing is written to disk.

    A directory with neither ``questionnaire.json`` nor a page that uses the
    ``Questionnaire`` component reports ``present=False`` and no errors.
    """
    directory = Path(directory)
    page = _page_sources(directory)
    has_spec = (directory / QUESTIONNAIRE_FILE).is_file()
    uses_component = "Questionnaire" in page and "panel-ui.js" in page
    check = QuestionnaireCheck(present=has_spec or uses_component)
    if not check.present:
        return check
    if not has_spec:
        check.errors.append(
            f"{QUESTIONNAIRE_FILE}: missing. The page uses the Questionnaire component, so write the questions "
            f"to {QUESTIONNAIRE_FILE} beside panel.json; the check and the submit route read them from there."
        )
    if "miniapp" not in contexts:
        check.errors.append(
            "panel.json: a questionnaire submits through scistudio.submitAnswers, which only the 'miniapp' "
            "context provides. Add 'miniapp' to contexts."
        )
    for marker, fix in _PAGE_MARKERS:
        if marker not in page:
            check.errors.append(f"{entry}: submit is not reachable — the page never mentions '{marker}'. Fix: {fix}.")
    spec, problems = load_spec(directory) if has_spec else (None, [])
    check.errors.extend(problems)
    if spec is None:
        return check
    questions = spec["questions"]
    check.question_count = len(questions)
    # Three submits: a mix of every status, "Decide for me" on everything, and
    # nothing answered at all — the last proves every question is optional.
    submissions = [
        {q["id"]: _sample_answer(q, i) for i, q in enumerate(questions)},
        {q["id"]: {"status": DECIDE_FOR_ME} for q in questions},
        {},
    ]
    seen: set[str] = set()
    for submission in submissions:
        try:
            document = json.loads(json.dumps(answers_document(panel_id, spec, submission), allow_nan=False))
        except (QuestionnaireError, TypeError, ValueError) as exc:  # pragma: no cover - validator bug
            check.errors.append(f"{QUESTIONNAIRE_FILE}: a sample submit was refused ({exc}); the spec needs fixing.")
            return check
        entries = document.get("answers", [])
        if [e.get("id") for e in entries] != [q["id"] for q in questions]:  # pragma: no cover - validator bug
            check.errors.append(f"{ANSWERS_FILE}: a sample submit did not produce one entry per question.")
            return check
        seen.update(str(e.get("status")) for e in entries)
    check.statuses_exercised = sorted(seen)
    check.round_trip = True
    return check


def notification_text(panel_id: str, answers_path: str) -> str:
    """The one line typed into the agent session after a submit."""
    return (
        f"The user submitted the questionnaire for MiniApp {panel_id}. "
        f"Read the answers in {answers_path} and build the MiniApp from them."
    )


__all__ = [
    "ANSWERS_FILE",
    "ANSWERS_VERSION",
    "ANSWER_STATUSES",
    "DECIDE_FOR_ME",
    "QUESTIONNAIRE_FILE",
    "QUESTION_TYPES",
    "QuestionnaireCheck",
    "QuestionnaireError",
    "answers_document",
    "check_questionnaire",
    "load_spec",
    "normalize_answers",
    "notification_text",
    "validate_spec",
    "write_answers",
]
