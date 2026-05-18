from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts/audit/addendum_propagate.py"
spec = importlib.util.spec_from_file_location("addendum_propagate", MODULE_PATH)
assert spec and spec.loader
addendum_propagate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(addendum_propagate)


def test_addendum_propagate_inserts_not_started_entry(tmp_path: Path) -> None:
    addendum = tmp_path / "ADR-099.md"
    tracker = tmp_path / "tracker.yaml"
    addendum.write_text(
        """---
adr: 99
governs:
  files:
    - scripts/audit/example.py
  contracts:
    - scieasy.qa.example.run
tests:
  - tests/qa/test_example.py
---
# ADR-099
""",
        encoding="utf-8",
    )
    tracker.write_text("adr: 42\nschema_version: 1\nsections: []\n", encoding="utf-8")

    assert addendum_propagate.propagate(addendum, tracker) is True

    payload = yaml.safe_load(tracker.read_text(encoding="utf-8"))
    entry = payload["sections"][0]
    assert entry["section"] == "ADR-099 addendum propagation"
    assert entry["status"] == "not_started"
    assert entry["requires_artifacts"]["files"] == ["scripts/audit/example.py"]
    assert entry["requires_artifacts"]["symbols"] == ["scieasy.qa.example.run"]
    assert entry["requires_artifacts"]["tests"] == ["tests/qa/test_example.py"]


def test_addendum_propagate_does_not_overwrite_existing_entry(tmp_path: Path) -> None:
    addendum = tmp_path / "ADR-099.md"
    tracker = tmp_path / "tracker.yaml"
    addendum.write_text(
        """---
adr: 99
governs:
  files:
    - scripts/audit/new.py
---
# ADR-099
""",
        encoding="utf-8",
    )
    tracker.write_text(
        """
adr: 42
schema_version: 1
sections:
  - section: "ADR-099 addendum propagation"
    requires_artifacts:
      files: ["scripts/audit/original.py"]
      symbols: []
      tests: []
    verification_checks: []
    status: not_started
    implemented_in_pr: null
    verified_at: null
    verifier_skill: null
    verifier_command: "python scripts/audit/adr_implementation_check.py"
""".strip(),
        encoding="utf-8",
    )

    assert addendum_propagate.propagate(addendum, tracker) is False

    payload = yaml.safe_load(tracker.read_text(encoding="utf-8"))
    assert payload["sections"][0]["requires_artifacts"]["files"] == ["scripts/audit/original.py"]
