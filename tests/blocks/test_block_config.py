"""Tests for BlockConfig and BlockResult."""
# ADR-020: BatchResult tests removed — BatchResult class deleted.

from __future__ import annotations

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.result import BlockResult


class TestBlockConfig:
    """BlockConfig — validated parameter container."""

    def test_get_existing_key(self) -> None:
        config = BlockConfig(params={"threshold": 0.5})
        assert config.get("threshold") == 0.5

    def test_get_missing_returns_default(self) -> None:
        config = BlockConfig(params={"threshold": 0.5})
        assert config.get("missing", "fallback") == "fallback"

    def test_get_missing_no_default_returns_none(self) -> None:
        config = BlockConfig(params={})
        assert config.get("missing") is None

    def test_default_params_empty(self) -> None:
        config = BlockConfig()
        assert config.params == {}

    def test_extra_fields_allowed(self) -> None:
        config = BlockConfig(params={"a": 1}, custom_field="hello")
        assert config.custom_field == "hello"  # type: ignore[attr-defined]

    def test_get_finds_extra_fields(self) -> None:
        """Enriched runtime keys (block_id, project_dir) are accessible via get() (#565)."""
        config = BlockConfig(params={"a": 1}, block_id="blk-42", project_dir="/proj")
        assert config.get("block_id") == "blk-42"
        assert config.get("project_dir") == "/proj"

    def test_get_params_takes_priority_over_extra(self) -> None:
        """If a key exists in both params and extra fields, params wins."""
        config = BlockConfig(params={"key": "from_params"}, key="from_extra")
        assert config.get("key") == "from_params"

    def test_get_extra_field_default(self) -> None:
        """Default is returned when key is in neither params nor extra fields."""
        config = BlockConfig(params={}, block_id="blk-1")
        assert config.get("missing", "fallback") == "fallback"


class TestBlockResult:
    """BlockResult — single block execution outcome."""

    def test_creation(self) -> None:
        err = ValueError("test")
        result = BlockResult(outputs={"out": 42}, duration_ms=100, error=err)
        assert result.outputs == {"out": 42}
        assert result.duration_ms == 100
        assert result.error is err

    def test_defaults(self) -> None:
        result = BlockResult(outputs={})
        assert result.duration_ms == 0
        assert result.error is None


# ADR-020: TestBatchResult removed — BatchResult class deleted.
# Collection iteration is block-internal; engine no longer performs batch execution.
