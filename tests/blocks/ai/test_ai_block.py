"""Tests for AIBlock MVP — run(), _serialize_input(), _describe_object().

ADR-035 supersedes the single-call AIBlock implementation these tests pin.
The whole module is marked xfail by ``pytestmark`` below until the
implementation phase (I35a/I35b/I35c) decides whether to rewrite each test
against the new PTY-tab runtime contract or delete them outright.

See docs/adr/ADR-035.md §4 "Delete" and the dispatch prompt for the
skeleton phase (#844).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scieasy.blocks.ai.ai_block import AIBlock
from scieasy.blocks.base.config import BlockConfig
from scieasy.core.types.text import Text

pytestmark = pytest.mark.xfail(
    reason="superseded by ADR-035 — old single-call AIBlock removed in skeleton phase",
    strict=False,
    run=False,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ai_block() -> AIBlock:
    """Return a default AIBlock instance."""
    return AIBlock()


@pytest.fixture()
def mock_provider(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Monkeypatch provider constructors to return a mock LLM provider.

    The mock's ``generate()`` returns a fixed string so tests can assert
    on the output without making real API calls.
    """
    provider = MagicMock()
    provider.generate.return_value = "LLM response text"

    monkeypatch.setattr(
        "scieasy.blocks.ai.providers.AnthropicProvider",
        lambda **kwargs: provider,
    )
    monkeypatch.setattr(
        "scieasy.blocks.ai.providers.OpenAIProvider",
        lambda **kwargs: provider,
    )
    return provider


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestAIBlockInstantiation:
    """AIBlock can be constructed and has correct metadata."""

    def test_instantiate_default(self, ai_block: AIBlock) -> None:
        assert ai_block is not None
        assert ai_block.name == "AI / LLM"
        assert ai_block.subcategory == "ai"
        assert ai_block.type_name == "ai.llm"

    def test_input_port_accepts_any(self, ai_block: AIBlock) -> None:
        data_port = ai_block.input_ports[0]
        assert data_port.name == "data"
        assert data_port.accepted_types == []  # Any
        assert data_port.required is False
        assert data_port.is_collection is True

    def test_output_port_is_text(self, ai_block: AIBlock) -> None:
        result_port = ai_block.output_ports[0]
        assert result_port.name == "result"
        assert Text in result_port.accepted_types

    def test_config_schema_has_prompt(self, ai_block: AIBlock) -> None:
        props = ai_block.config_schema["properties"]
        assert "prompt" in props
        assert "prompt" in ai_block.config_schema.get("required", [])


# ---------------------------------------------------------------------------
# _serialize_input
# ---------------------------------------------------------------------------


class TestSerializeInput:
    """_serialize_input converts various types to text for the LLM."""

    def test_none_input(self, ai_block: AIBlock) -> None:
        result = ai_block._serialize_input(None)
        assert result == "(no input data)"

    def test_text_input(self, ai_block: AIBlock) -> None:
        text_obj = Text(content="Hello world", format="plain")
        result = ai_block._serialize_input(text_obj)
        assert "Text" in result
        assert "Hello world" in result

    def test_string_fallback(self, ai_block: AIBlock) -> None:
        result = ai_block._serialize_input("raw string")
        assert result == "raw string"

    def test_collection_input(self, ai_block: AIBlock) -> None:
        from scieasy.core.types.collection import Collection

        items = [
            Text(content="First", format="plain"),
            Text(content="Second", format="plain"),
        ]
        col = Collection(items, item_type=Text)
        result = ai_block._serialize_input(col)
        assert "[Item 0]:" in result
        assert "[Item 1]:" in result
        assert "First" in result
        assert "Second" in result

    def test_array_input(self, ai_block: AIBlock) -> None:
        from scieasy.core.types.array import Array

        arr = Array(axes=["y", "x"], shape=(100, 200), dtype="uint8")
        result = ai_block._serialize_input(arr)
        assert "Array" in result
        assert "axes=" in result
        assert "shape=" in result

    def test_dataframe_input(self, ai_block: AIBlock) -> None:
        from scieasy.core.types.dataframe import DataFrame

        df = DataFrame(columns=["a", "b"], row_count=10)
        result = ai_block._serialize_input(df)
        assert "DataFrame" in result
        assert "columns=" in result
        assert "rows=" in result


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestAIBlockRun:
    """AIBlock.run() calls the LLM provider and returns Text."""

    def test_run_basic(self, ai_block: AIBlock, mock_provider: MagicMock) -> None:
        config = BlockConfig(params={"prompt": "Summarize: {data}", "provider": "anthropic"})
        text_input = Text(content="Some data", format="plain")
        result = ai_block.run({"data": text_input}, config)

        assert "result" in result
        assert isinstance(result["result"], Text)
        assert result["result"].content == "LLM response text"

        # Verify provider was called with the substituted prompt.
        call_args = mock_provider.generate.call_args
        assert "Some data" in call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")

    def test_run_no_input(self, ai_block: AIBlock, mock_provider: MagicMock) -> None:
        config = BlockConfig(params={"prompt": "Just answer: {data}", "provider": "anthropic"})
        result = ai_block.run({}, config)

        assert isinstance(result["result"], Text)
        # The {data} placeholder should be replaced with the no-input marker.
        call_args = mock_provider.generate.call_args
        prompt_used = call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")
        assert "(no input data)" in prompt_used

    def test_run_with_system_prompt(self, ai_block: AIBlock, mock_provider: MagicMock) -> None:
        config = BlockConfig(
            params={
                "prompt": "Hello {data}",
                "provider": "anthropic",
                "system_prompt": "You are a scientist.",
            }
        )
        ai_block.run({}, config)

        call_args = mock_provider.generate.call_args
        assert call_args.kwargs.get("system") == "You are a scientist."

    def test_run_missing_prompt_raises(self, ai_block: AIBlock, mock_provider: MagicMock) -> None:
        config = BlockConfig(params={})
        with pytest.raises(ValueError, match=r"prompt.*required"):
            ai_block.run({}, config)

    def test_run_empty_prompt_raises(self, ai_block: AIBlock, mock_provider: MagicMock) -> None:
        config = BlockConfig(params={"prompt": ""})
        with pytest.raises(ValueError, match=r"prompt.*required"):
            ai_block.run({}, config)

    def test_run_passes_temperature_and_max_tokens(self, ai_block: AIBlock, mock_provider: MagicMock) -> None:
        config = BlockConfig(
            params={
                "prompt": "Test {data}",
                "provider": "anthropic",
                "temperature": 0.8,
                "max_tokens": 2048,
            }
        )
        ai_block.run({}, config)

        call_args = mock_provider.generate.call_args
        ai_config = call_args.kwargs.get("config")
        assert ai_config is not None
        assert ai_config["temperature"] == 0.8
        assert ai_config["max_tokens"] == 2048


# ---------------------------------------------------------------------------
# prompt_file
# ---------------------------------------------------------------------------


class TestAIBlockPromptFile:
    """AIBlock supports loading prompts from .md / .txt files."""

    def test_prompt_file_overrides_prompt_field(
        self,
        ai_block: AIBlock,
        mock_provider: MagicMock,
        tmp_path: Path,  # noqa: F821
    ) -> None:

        prompt_file = tmp_path / "my_prompt.md"
        prompt_file.write_text("File prompt: {data}", encoding="utf-8")

        config = BlockConfig(
            params={
                "prompt": "Ignored prompt",
                "prompt_file": str(prompt_file),
                "provider": "anthropic",
            }
        )
        ai_block.run({}, config)

        call_args = mock_provider.generate.call_args
        prompt_used = call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")
        assert "File prompt:" in prompt_used
        assert "Ignored prompt" not in prompt_used

    def test_prompt_file_txt_supported(
        self,
        ai_block: AIBlock,
        mock_provider: MagicMock,
        tmp_path: Path,  # noqa: F821
    ) -> None:

        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("TXT prompt: {data}", encoding="utf-8")

        config = BlockConfig(
            params={
                "prompt": "",
                "prompt_file": str(prompt_file),
                "provider": "anthropic",
            }
        )
        ai_block.run({}, config)

        call_args = mock_provider.generate.call_args
        prompt_used = call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")
        assert "TXT prompt:" in prompt_used

    def test_prompt_file_missing_raises(
        self,
        ai_block: AIBlock,
        mock_provider: MagicMock,
        tmp_path: Path,  # noqa: F821
    ) -> None:
        config = BlockConfig(
            params={
                "prompt": "",
                "prompt_file": str(tmp_path / "nonexistent.md"),
                "provider": "anthropic",
            }
        )
        with pytest.raises(FileNotFoundError, match="prompt_file not found"):
            ai_block.run({}, config)

    def test_prompt_file_wrong_extension_raises(
        self,
        ai_block: AIBlock,
        mock_provider: MagicMock,
        tmp_path: Path,  # noqa: F821
    ) -> None:

        bad_file = tmp_path / "prompt.py"
        bad_file.write_text("print('hello')", encoding="utf-8")

        config = BlockConfig(
            params={
                "prompt": "",
                "prompt_file": str(bad_file),
                "provider": "anthropic",
            }
        )
        with pytest.raises(ValueError, match=r"\.md or \.txt"):
            ai_block.run({}, config)

    def test_config_schema_has_prompt_file(self, ai_block: AIBlock) -> None:
        props = ai_block.config_schema["properties"]
        assert "prompt_file" in props
        assert props["prompt_file"]["ui_widget"] == "file_browser"
