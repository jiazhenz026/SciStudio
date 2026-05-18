"""Tests for ``scieasy.qa.schemas.maintainers`` (ADR-042 §6)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.maintainers import (
    AgentRuntime,
    Maintainers,
    MaintainersEntry,
)


def test_agent_runtime_values() -> None:
    """AgentRuntime is a closed set of 5 values exactly."""
    assert {r.value for r in AgentRuntime} == {
        "Claude",
        "Codex",
        "Cursor",
        "Aider",
        "Gemini",
    }


def test_maintainers_entry_minimal() -> None:
    e = MaintainersEntry(path_glob="src/scieasy/qa/**")
    assert e.path_glob == "src/scieasy/qa/**"
    assert e.adrs == [] and e.humans == [] and e.agents_allowed == []
    assert e.notes is None


def test_maintainers_entry_full() -> None:
    e = MaintainersEntry(
        path_glob="src/scieasy/qa/**",
        adrs=[42],
        humans=["@jiazhenz026"],
        agents_allowed=[AgentRuntime.CLAUDE, AgentRuntime.CODEX],
        excludes=["src/scieasy/qa/excluded/**"],
        notes="QA subsystem",
    )
    assert e.adrs == [42]
    assert AgentRuntime.CLAUDE in e.agents_allowed


def test_maintainers_entry_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        MaintainersEntry.model_validate({"path_glob": "src/**", "unknown": "x"})


def test_maintainers_entry_invalid_adr_ref() -> None:
    with pytest.raises(ValidationError):
        MaintainersEntry.model_validate({"path_glob": "src/**", "adrs": [0]})


def test_maintainers_entry_invalid_handle() -> None:
    with pytest.raises(ValidationError):
        MaintainersEntry.model_validate({"path_glob": "src/**", "humans": ["jiazhenz026"]})


def test_maintainers_entry_invalid_runtime() -> None:
    with pytest.raises(ValidationError):
        MaintainersEntry.model_validate({"path_glob": "src/**", "agents_allowed": ["NotARuntime"]})


def test_maintainers_entry_empty_path_glob_rejected() -> None:
    with pytest.raises(ValidationError):
        MaintainersEntry.model_validate({"path_glob": ""})


def test_maintainers_minimum_one_entry() -> None:
    """``entries`` requires at least one item (audit fix I1)."""
    with pytest.raises(ValidationError):
        Maintainers.model_validate({"version": 1, "entries": []})


def test_maintainers_version_literal() -> None:
    with pytest.raises(ValidationError):
        Maintainers.model_validate({"version": 2, "entries": [{"path_glob": "src/**"}]})


def test_maintainers_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        Maintainers.model_validate(
            {
                "version": 1,
                "entries": [{"path_glob": "src/**"}],
                "unknown": "x",
            }
        )


def test_maintainers_round_trip() -> None:
    m = Maintainers(
        entries=[
            MaintainersEntry(
                path_glob="src/scieasy/qa/**",
                adrs=[42],
                humans=["@jiazhenz026"],
                agents_allowed=[AgentRuntime.CLAUDE, AgentRuntime.GEMINI],
            ),
            MaintainersEntry(path_glob="src/scieasy/core/**", adrs=[1]),
        ]
    )
    dumped = m.model_dump_json()
    reloaded = Maintainers.model_validate_json(dumped)
    assert reloaded == m


def test_maintainers_json_schema_export() -> None:
    for model in (MaintainersEntry, Maintainers):
        schema = model.model_json_schema()
        assert isinstance(schema, dict)
        if "$schema" in schema:
            assert "2020-12" in schema["$schema"]
