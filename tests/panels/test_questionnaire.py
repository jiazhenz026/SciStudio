"""ADR-054 MiniApp FR-049/FR-050/FR-052: questionnaire spec, answers, and the check (#2447)."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scistudio.panels.questionnaire import (
    ANSWERS_FILE,
    DECIDE_FOR_ME,
    QuestionnaireError,
    answers_document,
    check_questionnaire,
    load_spec,
    normalize_answers,
    notification_text,
    validate_spec,
    write_answers,
)
from scistudio.panels.watcher import counts

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "questionnaire"
CASES = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))["cases"]
GOOD: dict[str, Any] = CASES[0]["spec"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_spec_cases(case: dict[str, Any]) -> None:
    problems = validate_spec(case["spec"])
    assert (not problems) is case["valid"], problems
    for problem in problems:
        assert problem.startswith("questionnaire.json:")


def test_problems_name_the_question_and_the_fix() -> None:
    spec = {"title": "T", "questions": [{"id": "chart", "type": "single", "prompt": "Which?", "required": True}]}
    problems = validate_spec(spec)
    assert any('questions[0] (id "chart")' in p and "remove 'required'" in p for p in problems)
    assert any("needs 'options'" in p for p in problems)


def test_normalize_keeps_order_and_marks_every_status() -> None:
    entries = normalize_answers(
        GOOD,
        {
            "chart": {"status": "answered", "value": "umap"},
            "colour_by": {"status": DECIDE_FOR_ME},
            "top_genes": {"status": "answered", "value": 20},
            "opacity": {"status": "skipped"},
        },
    )
    assert [e["id"] for e in entries] == [q["id"] for q in GOOD["questions"]]
    assert entries[0] == {"id": "chart", "type": "single", "prompt": "Which view?", "status": "answered", "value": "umap", "label": "UMAP"}
    assert entries[1]["status"] == DECIDE_FOR_ME and "value" not in entries[1]
    assert entries[2]["status"] == "skipped"  # left out of the submission
    assert entries[3]["value"] == 20


def test_every_question_is_optional() -> None:
    assert {e["status"] for e in normalize_answers(GOOD, {})} == {"skipped"}


def test_other_text_and_multiple_labels() -> None:
    entries = normalize_answers(
        GOOD,
        {
            "chart": {"status": "answered", "other": "t-SNE"},
            "colour_by": {"status": "answered", "value": ["qc", "cluster"]},
        },
    )
    assert entries[0]["other"] == "t-SNE" and "value" not in entries[0]
    assert entries[1]["labels"] == ["QC metric", "Cluster"]


@pytest.mark.parametrize(
    "answers",
    [
        {"nope": {"status": "skipped"}},
        {"chart": {"status": "answered", "value": "tsne"}},
        {"chart": {"status": "maybe"}},
        {"chart": {"status": DECIDE_FOR_ME, "value": "umap"}},
        {"colour_by": {"status": "answered", "value": ["qc", "qc"]}},
        {"colour_by": {"status": "answered", "other": "x"}},  # allow_other is not set
        {"notes": {"status": "answered", "value": "   "}},
        {"top_genes": {"status": "answered", "value": 500}},
        {"opacity": {"status": "answered", "value": True}},
        [],
    ],
)
def test_submissions_that_do_not_fit_are_refused(answers: Any) -> None:
    with pytest.raises(QuestionnaireError):
        normalize_answers(GOOD, answers)


def test_answers_document_and_atomic_write(tmp_path: Path) -> None:
    document = answers_document("scatter", GOOD, {}, now=datetime(2026, 9, 15, 12, 0, tzinfo=UTC))
    assert document["version"] == 1
    assert document["panel_id"] == "scatter"
    assert document["submitted_at"] == "2026-09-15T12:00:00Z"
    path = write_answers(tmp_path, document)
    assert path == tmp_path / ANSWERS_FILE
    assert json.loads(path.read_text(encoding="utf-8")) == document
    assert [p.name for p in tmp_path.iterdir()] == [ANSWERS_FILE]


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "miniapp"
    shutil.copytree(FIXTURES / "miniapp", target)
    return target


def _check(directory: Path, contexts: tuple[str, ...] = ("miniapp",)) -> Any:
    return check_questionnaire(directory, panel_id="miniapp", contexts=contexts, entry="index.html")


def test_check_passes_a_working_questionnaire(tmp_path: Path) -> None:
    result = _check(_copy_fixture(tmp_path))
    assert result.present and result.errors == []
    assert result.question_count == len(GOOD["questions"])
    assert result.round_trip is True
    assert result.statuses_exercised == ["answered", DECIDE_FOR_ME, "skipped"]
    assert not (tmp_path / "miniapp" / ANSWERS_FILE).exists()


def test_check_ignores_a_page_without_a_questionnaire(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<p>hello</p>", encoding="utf-8")
    result = _check(tmp_path)
    assert not result.present and result.errors == []


def test_check_reports_a_broken_spec(tmp_path: Path) -> None:
    directory = _copy_fixture(tmp_path)
    spec = json.loads((directory / "questionnaire.json").read_text(encoding="utf-8"))
    spec["questions"][0]["options"] = [{"value": "umap", "label": "UMAP"}]
    (directory / "questionnaire.json").write_text(json.dumps(spec), encoding="utf-8")
    result = _check(directory)
    assert not result.round_trip
    assert any('(id "chart")' in e and "needs 'options'" in e for e in result.errors)


def test_check_reports_invalid_json_with_its_position(tmp_path: Path) -> None:
    directory = _copy_fixture(tmp_path)
    (directory / "questionnaire.json").write_text('{"title": "T",', encoding="utf-8")
    assert any("not valid JSON at line 1" in e for e in _check(directory).errors)
    assert load_spec(directory)[0] is None


def test_check_reports_an_unreachable_submit(tmp_path: Path) -> None:
    directory = _copy_fixture(tmp_path)
    page = (directory / "index.html").read_text(encoding="utf-8").replace("scistudio.submitAnswers", "undefined")
    (directory / "index.html").write_text(page, encoding="utf-8")
    errors = _check(directory).errors
    assert any("submit is not reachable" in e and "submitAnswers" in e for e in errors)


def test_check_requires_the_spec_file_and_the_miniapp_context(tmp_path: Path) -> None:
    directory = _copy_fixture(tmp_path)
    (directory / "questionnaire.json").unlink()
    errors = _check(directory, contexts=("preview",)).errors
    assert any("questionnaire.json: missing" in e for e in errors)
    assert any("Add 'miniapp' to contexts" in e for e in errors)


def test_notification_names_the_miniapp_and_the_file() -> None:
    text = notification_text("scatter", "panels/scatter/answers.json")
    assert "\n" not in text
    assert "scatter" in text and "panels/scatter/answers.json" in text


def test_answers_file_never_reloads_the_tab(tmp_path: Path) -> None:
    assert not counts(tmp_path, tmp_path / "answers.json")
    assert not counts(tmp_path, tmp_path / ".answers-abc.tmp")
    assert counts(tmp_path, tmp_path / "questionnaire.json")
