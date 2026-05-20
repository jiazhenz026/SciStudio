from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.architecture_drift import check
from scieasy.qa.schemas.facts import Fact, FactsRegistry
from scieasy.qa.schemas.report import AuditStatus


def _symbol(subject: str, kind: str, **value) -> Fact:
    payload = {"kind": kind, "path": subject, **value}
    return Fact(
        id=f"symbol:{subject}",
        kind="symbol",
        source="fixture",
        subject=subject,
        value=payload,
        source_sha="abc123",
        confidence="generated",
    )


def _facts() -> FactsRegistry:
    return FactsRegistry(
        source_sha="abc123",
        facts=[
            _symbol("scieasy.sample", "module"),
            _symbol("scieasy.sample.runtime", "module"),
            _symbol("scieasy.sample.runtime.Runner", "class"),
            _symbol(
                "scieasy.sample.runtime.Runner.run",
                "function",
                parameters=[
                    {"name": "self", "annotation": None, "required": True},
                    {"name": "value", "annotation": "str", "required": True},
                ],
                return_annotation="bool",
            ),
            _symbol(
                "scieasy.sample.runtime.load_config",
                "function",
                parameters=[{"name": "path", "annotation": "Path", "required": True}],
                return_annotation="dict[str, object]",
            ),
        ],
    )


def _write_architecture(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "docs" / "architecture" / "ARCHITECTURE.md"
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_architecture_drift_accepts_valid_module_symbol_and_signature_references(tmp_path: Path) -> None:
    path = _write_architecture(
        tmp_path,
        """# Architecture

The runtime lives in `scieasy.sample.runtime` and exposes `Runner`.

```python
from scieasy.sample.runtime import Runner

class Runner:
    def run(self, value: str) -> bool:
        ...
```
""",
    )

    report = check(tmp_path, _facts(), architecture_path=path)

    assert report.status == AuditStatus.PASS


def test_architecture_drift_reports_stale_signature_in_python_code_block(tmp_path: Path) -> None:
    path = _write_architecture(
        tmp_path,
        """# Architecture

```python
from scieasy.sample.runtime import Runner

class Runner:
    def run(self, value: int) -> bool:
        ...
```
""",
    )

    report = check(tmp_path, _facts(), architecture_path=path)

    assert report.status == AuditStatus.FAIL
    assert [finding.rule_id for finding in report.findings] == ["architecture-drift.parameters-mismatch"]


def test_architecture_drift_reports_missing_symbol_in_backticks(tmp_path: Path) -> None:
    path = _write_architecture(
        tmp_path,
        """# Architecture

The runtime exposes `MissingRunner` for execution.
""",
    )

    report = check(tmp_path, _facts(), architecture_path=path)

    assert report.status == AuditStatus.FAIL
    assert report.findings[0].rule_id == "architecture-drift.missing-bare-symbol"


def test_architecture_drift_reports_missing_module_path(tmp_path: Path) -> None:
    path = _write_architecture(
        tmp_path,
        """# Architecture

The stale module path is `scieasy.missing.runtime`.
""",
    )

    report = check(tmp_path, _facts(), architecture_path=path)

    assert report.status == AuditStatus.FAIL
    assert report.findings[0].rule_id == "architecture-drift.missing-dotted-reference"


def test_architecture_drift_skips_explicit_non_normative_examples(tmp_path: Path) -> None:
    path = _write_architecture(
        tmp_path,
        """# Architecture

Non-normative pseudocode example:

```python
from scieasy.missing.runtime import MissingRunner

class MissingRunner:
    def run(self, value: int) -> str:
        ...
```
""",
    )

    report = check(tmp_path, _facts(), architecture_path=path)

    assert report.status == AuditStatus.PASS
    assert report.summary["fences_skipped"] == 1
