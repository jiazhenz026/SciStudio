"""Tests for ``docs/audit/ci-implementability.schema.json``.

Codex review (PR #1147) flagged that ``minItems: 20`` + per-item enum
alone allowed payloads with 20 duplicate entries to validate while
omitting other required tools.  These tests pin the strengthened
contract: every tool in the §21.1 stack must appear exactly once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

_SCHEMA_PATH = Path("docs/audit/ci-implementability.schema.json")

_TOOLS = [
    "ruff",
    "mypy",
    "pyright",
    "interrogate",
    "pydoclint",
    "griffe",
    "vulture",
    "xenon",
    "bandit",
    "pip-audit",
    "mutmut",
    "pytest-examples",
    "markdownlint-cli2",
    "sphinx-lint",
    "sphinx-build",
    "actionlint",
    "zizmor",
    "codespell",
    "yamllint",
    "import-linter",
]


def _load_schema() -> dict[str, object]:
    if not _SCHEMA_PATH.exists():
        pytest.skip(f"schema not present at {_SCHEMA_PATH}")
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _tool_entry(tool: str) -> dict[str, object]:
    return {
        "tool": tool,
        "version": "0.0.0",
        "ran_to_completion": True,
        "exit_code": 0,
        "duration_seconds": 0.1,
        "total_findings": 0,
        "sarif_emitted": True,
        "ratchet_decision": "success",
    }


def _valid_artifact() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "phase_1_end_sha": "0123456789abcdef0123456789abcdef01234567",
        "generated_at": "2026-06-01T12:34:56Z",
        "tools": [_tool_entry(t) for t in _TOOLS],
    }


def test_valid_artifact_passes() -> None:
    schema = _load_schema()
    artifact = _valid_artifact()
    jsonschema.validate(artifact, schema)


def test_duplicate_tools_rejected() -> None:
    schema = _load_schema()
    artifact = _valid_artifact()
    # Replace last entry with a duplicate of the first to break uniqueness
    # AND violate the per-tool `contains` requirement for "import-linter".
    artifact["tools"][-1] = _tool_entry("ruff")  # type: ignore[index]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(artifact, schema)


def test_missing_tool_rejected() -> None:
    schema = _load_schema()
    artifact = _valid_artifact()
    # Drop the last entry (import-linter) AND duplicate an existing one so
    # the array still has 20 items.  The `contains` block for
    # "import-linter" must reject the payload.
    artifact["tools"][-1] = _tool_entry("ruff")  # type: ignore[index]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(artifact, schema)


def test_too_few_tools_rejected() -> None:
    schema = _load_schema()
    artifact = _valid_artifact()
    artifact["tools"] = artifact["tools"][:19]  # type: ignore[index]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(artifact, schema)


def test_too_many_tools_rejected() -> None:
    schema = _load_schema()
    artifact = _valid_artifact()
    artifact["tools"].append(_tool_entry("ruff"))  # type: ignore[union-attr]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(artifact, schema)


def test_unknown_tool_rejected() -> None:
    schema = _load_schema()
    artifact = _valid_artifact()
    artifact["tools"][-1]["tool"] = "totally-not-a-tool"  # type: ignore[index]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(artifact, schema)
