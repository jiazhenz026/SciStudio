"""Tests for the ADR-042 Addendum 6 append-only gate ledger (spec §10.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scistudio.qa.governance.gate_record import io
from scistudio.qa.governance.gate_record.checks import event_is_valid_for
from scistudio.qa.governance.gate_record.ledger import (
    LEDGER_SCHEMA_VERSION,
    CheckEvent,
    DeclaredScope,
    DirectiveEvent,
    DocsEvent,
    GateLedger,
    ScopeEvent,
    TestEvent,
)


def _ledger(**overrides: object) -> GateLedger:
    base: dict[str, object] = {
        "record_id": "1509-core",
        "session_id": "sess-1",
        "runtime": "claude-code",
        "task_kind": "bugfix",
        "persona": "implementer",
        "branch": "track/x",
        "owner_directive": "fix it",
    }
    base.update(overrides)
    return GateLedger.model_validate(base)


def test_schema_version_is_two() -> None:
    ledger = _ledger()
    assert ledger.schema_version == LEDGER_SCHEMA_VERSION == 2


def test_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValidationError):
        GateLedger.model_validate(
            {
                "schema_version": 1,
                "record_id": "x",
                "runtime": "r",
                "task_kind": "bugfix",
                "persona": "implementer",
                "branch": "b",
                "owner_directive": "d",
            }
        )


def test_events_accumulate_and_are_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    ledger = _ledger()
    ledger.directive_events.append(DirectiveEvent(owner_directive="first"))
    io.write_ledger(path, ledger)

    # Reload and append a second directive (simulating a later command).
    reloaded = io.load_ledger(path)
    reloaded.directive_events.append(DirectiveEvent(owner_directive="second"))
    io.write_ledger(path, reloaded)

    final = io.load_ledger(path)
    assert [e.owner_directive for e in final.directive_events] == ["first", "second"]


def test_effective_scope_applies_add_and_remove_events() -> None:
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/a/**"]))
    ledger.scope_events.append(ScopeEvent(action="add-include", pattern="src/b/**"))
    ledger.scope_events.append(ScopeEvent(action="remove-include", pattern="src/a/**"))
    ledger.scope_events.append(ScopeEvent(action="add-exclude", pattern="src/b/legacy/**"))
    assert ledger.effective_include() == ["src/b/**"]
    assert ledger.effective_exclude() == ["src/b/legacy/**"]


def test_docs_and_test_path_events_expose_declared_paths() -> None:
    ledger = _ledger()
    ledger.docs_events.append(DocsEvent(kind="path", path="docs/x.md"))
    ledger.docs_events.append(DocsEvent.model_validate({"kind": "na", "class": "implementation", "rationale": "n/a"}))
    ledger.test_events.append(TestEvent(kind="path", path="tests/test_x.py"))
    assert ledger.declared_docs_paths() == ["docs/x.md"]
    assert ledger.declared_test_paths() == ["tests/test_x.py"]


def test_docs_na_event_requires_rationale() -> None:
    with pytest.raises(ValidationError):
        DocsEvent.model_validate({"kind": "na", "class": "implementation"})


def test_check_event_pass_cannot_have_nonzero_exit() -> None:
    with pytest.raises(ValidationError):
        CheckEvent(name="lint", command="ruff check .", covered_surface="python", status="pass", exit_code=1)


def test_check_event_validity_is_scoped_to_input_fingerprint() -> None:
    event = CheckEvent(
        name="lint",
        command="ruff check .",
        covered_surface="python",
        status="pass",
        exit_code=0,
        input_fingerprint="sha256:abc",
    )
    # Same surface fingerprint -> still valid.
    assert event_is_valid_for(event, input_fingerprint="sha256:abc")
    # A later edit changes the fingerprint -> evidence is invalid.
    assert not event_is_valid_for(event, input_fingerprint="sha256:def")


def test_failed_check_event_is_never_reused_as_valid() -> None:
    event = CheckEvent(
        name="lint",
        command="ruff check .",
        covered_surface="python",
        status="fail",
        exit_code=1,
        input_fingerprint="sha256:abc",
    )
    assert not event_is_valid_for(event, input_fingerprint="sha256:abc")


def test_serialized_ledger_roundtrips_as_one_object(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    ledger = _ledger()
    io.write_ledger(path, ledger)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["schema_version"] == 2
    # docs N/A events serialize the alias key "class", not "doc_class".
    ledger.docs_events.append(DocsEvent.model_validate({"kind": "na", "class": "impl", "rationale": "x"}))
    io.write_ledger(path, ledger)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["docs_events"][0]["class"] == "impl"
