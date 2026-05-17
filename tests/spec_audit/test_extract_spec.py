"""Smoke tests for scripts/spec_audit/extract_spec.py grammar parser."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable. spec_audit lives at scripts/spec_audit/.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.spec_audit.extract_spec import SpecParseError, parse_spec  # noqa: E402


def test_parse_well_formed_entry(tmp_path: Path) -> None:
    spec = tmp_path / "INTERFACE_SPEC.md"
    spec.write_text(
        """# Interface Specification

## 1. block-abc

### `block-abc.Block.run` — abstract entry point for every block

Status: a
Source: `src/scieasy/blocks/base/block.py:L48-L120`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1`
Supplementary-doc-source: ADR-027 D7

```python
def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]: ...
```
""",
        encoding="utf-8",
    )

    records = parse_spec(spec)
    assert len(records) == 1
    r = records[0]
    assert r.interface_id == "block-abc.Block.run"
    assert r.module == "block-abc"
    assert r.status == "a"
    assert r.source_file == "src/scieasy/blocks/base/block.py"
    assert r.source_lines == "L48-L120"
    assert r.primary_doc_source.endswith("§5.1")
    assert "ADR-027 D7" in r.supplementary_doc_source


def test_missing_status_raises(tmp_path: Path) -> None:
    spec = tmp_path / "bad.md"
    spec.write_text(
        """## 1. mod

### `mod.Foo` — no status

Source: `src/foo.py:L1-L2`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §1`

```python
class Foo: ...
```
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecParseError, match="missing Status"):
        parse_spec(spec)


def test_b_status_requires_issue(tmp_path: Path) -> None:
    spec = tmp_path / "bad.md"
    spec.write_text(
        """## 1. mod

### `mod.Foo` — disagrees

Status: b
Source: `src/foo.py:L1-L2`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §1`

```python
class Foo: ...
```
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecParseError, match="requires Issue"):
        parse_spec(spec)


def test_empty_spec_is_valid(tmp_path: Path) -> None:
    """During Phase 6 draft, an empty spec must parse cleanly to 0 records."""
    spec = tmp_path / "empty.md"
    spec.write_text("# Interface Specification\n\n(WIP)\n", encoding="utf-8")
    records = parse_spec(spec)
    assert records == []


def test_missing_file_is_valid(tmp_path: Path) -> None:
    spec = tmp_path / "does-not-exist.md"
    records = parse_spec(spec)
    assert records == []


def test_c_label_with_issue_parses(tmp_path: Path) -> None:
    """A docs-only feature (status=c) requires an Issue: line."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        """## 1. mod

### `mod.Future` — promised but not implemented

Status: c
Source: `src/scieasy/future/missing.py:L1-L2`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §99`
Issue: #TBD-future-feature

```python
class Future: ...
```
""",
        encoding="utf-8",
    )
    records = parse_spec(spec)
    assert len(records) == 1
    assert records[0].status == "c"
    assert records[0].issue == "#TBD-future-feature"
