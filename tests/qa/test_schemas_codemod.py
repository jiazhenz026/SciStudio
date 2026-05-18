"""Tests for ``scieasy.qa.schemas.codemod`` (ADR-042 §20.3).

Covers:
* ``CodemodMeta`` validates the §20.3 verbatim metadata example.
* Required-field enforcement (``adr``, ``description``).
* ADR range bound (``[1, 9999]``).
* Default-empty ``affects`` and ``tests`` lists.
* ``RepoRelativePath`` constraint on each ``tests`` entry.
* ``extra="forbid"`` on unknown keys.
* Whitespace trimming via ``str_strip_whitespace``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.codemod import CodemodMeta


class TestCodemodMeta:
    def test_minimal_valid(self) -> None:
        meta = CodemodMeta(adr=42, description="x")
        assert meta.adr == 42
        assert meta.description == "x"
        assert meta.affects == []
        assert meta.tests == []

    def test_full_example_verbatim(self) -> None:
        meta = CodemodMeta(
            adr=42,
            description="Rename scieasy.X.foo to scieasy.X.bar per ADR-042 §N",
            affects=["scieasy.X.foo (renamed to scieasy.X.bar)"],
            tests=["tests/codemods/test_adr_042_rename.py"],
        )
        assert meta.adr == 42
        assert "Rename" in meta.description
        assert meta.affects[0].endswith("scieasy.X.bar)")
        assert meta.tests == ["tests/codemods/test_adr_042_rename.py"]

    def test_adr_lower_bound(self) -> None:
        with pytest.raises(ValidationError):
            CodemodMeta(adr=0, description="x")

    def test_adr_upper_bound(self) -> None:
        with pytest.raises(ValidationError):
            CodemodMeta(adr=10000, description="x")

    def test_description_required(self) -> None:
        with pytest.raises(ValidationError):
            CodemodMeta.model_validate({"adr": 42})

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodemodMeta(adr=42, description="")

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CodemodMeta.model_validate({"adr": 42, "description": "x", "unknown_field": True})

    def test_tests_entry_must_be_repo_relative(self) -> None:
        # Leading slash is rejected by RepoRelativePath.
        with pytest.raises(ValidationError):
            CodemodMeta(adr=42, description="x", tests=["/abs/path.py"])

    def test_whitespace_stripped(self) -> None:
        meta = CodemodMeta(adr=42, description="  hello  ")
        assert meta.description == "hello"

    def test_multiple_affects_entries_preserved(self) -> None:
        meta = CodemodMeta(
            adr=42,
            description="multi",
            affects=["scieasy.a.foo", "scieasy.b.bar", "scieasy.c.baz"],
        )
        assert len(meta.affects) == 3
