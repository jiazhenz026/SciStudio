from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.signature_contracts import extract_adr_signature_contracts


def _write_adr(path: Path, *, status: str = "Accepted") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    accepted_date = "2026-05-20" if status == "Accepted" else "null"
    superseded_date = "2026-05-20" if status == "Superseded" else "null"
    superseded_by = "124" if status == "Superseded" else "null"
    path.write_text(
        f"""---
adr: 123
title: "Signature Contract Test ADR"
status: {status}
date_created: 2026-05-20
date_accepted: {accepted_date}
date_superseded: {superseded_date}
supersedes: []
superseded_by: {superseded_by}
related: []
closes_issues: []
tracking_issue: null
is_code_implementation: false
governs:
  modules:
    - sample.module
  contracts:
    - sample.module.target
    - sample.models.SampleModel
  entry_points: []
  files:
    - docs/adr/ADR-123.md
  excludes: []
tests: []
agent_editable: false
assisted_by:
  - "Codex:gpt-5"
phase: complete
tags: [qa]
owner: "@owner"
co_authors: []
language_source: en
translations: []
---

# ADR-123: Signature Contract Test ADR

## 1. Decision Summary

### 1.1 Problems Addressed

| Problem | Risk | ADR-123 response | Detailed section |
|---|---|---|---|
| Contract drift | Runtime signatures can drift from the ADR | Extract ADR signature facts | Section 2 |

## 2. Contract Details

### Signature-Level Contracts

| Command | Expected exit codes |
|---|---|
| `scieasy audit signatures` | `0` pass, `2` drift |

```python
from pydantic import BaseModel

def target(value: str) -> bool:
    ...

class SampleModel(BaseModel):
    name: str
```

### Non-Normative Example

```python
def ignored() -> None:
    ...
```
""",
        encoding="utf-8",
    )
    return path


def test_extract_adr_signature_contracts_reads_active_adr_sections(tmp_path: Path) -> None:
    adr_path = _write_adr(tmp_path / "docs" / "adr" / "ADR-123.md")
    facts = extract_adr_signature_contracts([adr_path], repo_root=tmp_path, source_sha="test-sha")

    by_kind_subject = {(fact.kind, fact.subject): fact for fact in facts}

    assert ("expected-signature", "sample.module.target") in by_kind_subject
    assert ("expected-signature", "sample.models.SampleModel") in by_kind_subject
    assert ("expected-model-field", "sample.models.SampleModel.name") in by_kind_subject
    assert ("expected-cli-command", "scieasy audit signatures") in by_kind_subject
    assert ("expected-signature", "ignored") not in by_kind_subject


def test_extract_adr_signature_contracts_records_file_line_numbers(tmp_path: Path) -> None:
    adr_path = _write_adr(tmp_path / "docs" / "adr" / "ADR-123.md")
    text = adr_path.read_text(encoding="utf-8")
    expected_line = text.splitlines().index("def target(value: str) -> bool:") + 1

    facts = extract_adr_signature_contracts([adr_path], repo_root=tmp_path, source_sha="test-sha")
    function_fact = next(
        fact for fact in facts if fact.kind == "expected-signature" and fact.subject.endswith(".target")
    )

    assert function_fact.value["line"] == expected_line


def test_extract_adr_signature_contracts_skips_inactive_adrs(tmp_path: Path) -> None:
    adr_path = _write_adr(tmp_path / "docs" / "adr" / "ADR-123.md", status="Superseded")

    facts = extract_adr_signature_contracts([adr_path], repo_root=tmp_path, source_sha="test-sha")

    assert facts == []
