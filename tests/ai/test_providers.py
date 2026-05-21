"""Tests for LLM provider protocol, implementations, and factory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scistudio.blocks.ai.providers import (
    AnthropicProvider,
    LLMProvider,
    OpenAIProvider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeConfig:
    """Minimal stand-in for AIConfig to avoid import-linter issues in tests."""

    provider: str = "anthropic"
    model: str = ""
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 4096
    max_retries: int = 3


class _ProtocolConformant:
    """Minimal class that structurally satisfies LLMProvider."""

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        config: Any = None,
    ) -> str:
        return "hello"


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


class TestLLMProviderProtocol:
    """Verify the LLMProvider protocol behaves as expected."""

    def test_runtime_checkable(self) -> None:
        """LLMProvider is runtime-checkable with isinstance."""
        obj = _ProtocolConformant()
        assert isinstance(obj, LLMProvider)

    def test_non_conformant_fails(self) -> None:
        """An object missing generate() does not satisfy LLMProvider."""

        class Bad:
            pass

        assert not isinstance(Bad(), LLMProvider)

    def test_wrong_name_fails(self) -> None:
        """A method with the wrong name does not satisfy the protocol."""

        class WrongName:
            def produce(self, prompt: str) -> str:
                return ""

        assert not isinstance(WrongName(), LLMProvider)


# ---------------------------------------------------------------------------
# AnthropicProvider tests (mocked SDK)
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    """Test AnthropicProvider with mocked anthropic SDK."""

    def _make_provider(self, mock_sdk: MagicMock) -> AnthropicProvider:
        """Create an AnthropicProvider with a mocked SDK."""
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}),
            patch("scistudio.blocks.ai.providers._anthropic_sdk", mock_sdk),
        ):
            return AnthropicProvider()

    def test_generate_basic(self) -> None:
        """generate() calls client.messages.create and returns text."""
        mock_sdk = MagicMock()
        content_block = SimpleNamespace(text="Generated response")
        mock_sdk.Anthropic.return_value.messages.create.return_value = SimpleNamespace(content=[content_block])

        provider = self._make_provider(mock_sdk)
        result = provider.generate("Write a test")

        assert result == "Generated response"
        mock_sdk.Anthropic.return_value.messages.create.assert_called_once()

    def test_generate_with_system(self) -> None:
        """generate() passes system instruction when provided."""
        mock_sdk = MagicMock()
        content_block = SimpleNamespace(text="response")
        mock_sdk.Anthropic.return_value.messages.create.return_value = SimpleNamespace(content=[content_block])

        provider = self._make_provider(mock_sdk)
        provider.generate("prompt", system="Be helpful")

        call_kwargs = mock_sdk.Anthropic.return_value.messages.create.call_args
        assert call_kwargs.kwargs.get("system") == "Be helpful"

    def test_generate_with_config_override(self) -> None:
        """generate() uses config overrides when provided."""
        mock_sdk = MagicMock()
        content_block = SimpleNamespace(text="response")
        mock_sdk.Anthropic.return_value.messages.create.return_value = SimpleNamespace(content=[content_block])

        provider = self._make_provider(mock_sdk)
        config = _FakeConfig(model="claude-opus-4-20250514", max_tokens=1024, temperature=0.5)
        provider.generate("prompt", config=config)

        call_kwargs = mock_sdk.Anthropic.return_value.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-opus-4-20250514"
        assert call_kwargs.kwargs["max_tokens"] == 1024
        assert call_kwargs.kwargs["temperature"] == 0.5

    def test_generate_empty_response(self) -> None:
        """generate() returns '' when API returns empty content."""
        mock_sdk = MagicMock()
        mock_sdk.Anthropic.return_value.messages.create.return_value = SimpleNamespace(content=[])

        provider = self._make_provider(mock_sdk)
        result = provider.generate("prompt")

        assert result == ""

    def test_generate_api_error_propagates(self) -> None:
        """generate() propagates API exceptions."""
        mock_sdk = MagicMock()
        mock_sdk.Anthropic.return_value.messages.create.side_effect = RuntimeError("rate limit exceeded")

        provider = self._make_provider(mock_sdk)
        with pytest.raises(RuntimeError, match="rate limit"):
            provider.generate("prompt")

    def test_missing_sdk_raises_import_error(self) -> None:
        """AnthropicProvider raises ImportError when SDK is not installed."""
        with patch("scistudio.blocks.ai.providers._anthropic_sdk", None), pytest.raises(ImportError, match="anthropic"):
            AnthropicProvider(api_key="key")

    def test_missing_api_key_raises(self) -> None:
        """AnthropicProvider raises ValueError when no key is available."""
        mock_sdk = MagicMock()
        env_no_key = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with (
            patch("scistudio.blocks.ai.providers._anthropic_sdk", mock_sdk),
            patch.dict(os.environ, env_no_key, clear=True),
            pytest.raises(ValueError, match="No Anthropic API key"),
        ):
            AnthropicProvider()

    def test_explicit_api_key(self) -> None:
        """AnthropicProvider uses the explicitly provided key."""
        mock_sdk = MagicMock()
        with patch("scistudio.blocks.ai.providers._anthropic_sdk", mock_sdk):
            AnthropicProvider(api_key="explicit-key")
            mock_sdk.Anthropic.assert_called_once_with(api_key="explicit-key")

    def test_env_api_key(self) -> None:
        """AnthropicProvider falls back to env var."""
        mock_sdk = MagicMock()
        with (
            patch("scistudio.blocks.ai.providers._anthropic_sdk", mock_sdk),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}),
        ):
            AnthropicProvider()
            mock_sdk.Anthropic.assert_called_once_with(api_key="env-key")

    def test_satisfies_protocol(self) -> None:
        """AnthropicProvider instances satisfy LLMProvider protocol."""
        mock_sdk = MagicMock()
        provider = self._make_provider(mock_sdk)
        assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# OpenAIProvider tests (mocked SDK)
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    """Test OpenAIProvider with mocked openai SDK."""

    def _make_provider(self, mock_sdk: MagicMock) -> OpenAIProvider:
        """Create an OpenAIProvider with a mocked SDK."""
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-456"}),
            patch("scistudio.blocks.ai.providers._openai_sdk", mock_sdk),
        ):
            return OpenAIProvider()

    def test_generate_basic(self) -> None:
        """generate() calls client.chat.completions.create and returns text."""
        mock_sdk = MagicMock()
        choice = SimpleNamespace(message=SimpleNamespace(content="OpenAI response"))
        mock_sdk.OpenAI.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[choice])

        provider = self._make_provider(mock_sdk)
        result = provider.generate("Write a test")

        assert result == "OpenAI response"
        mock_sdk.OpenAI.return_value.chat.completions.create.assert_called_once()

    def test_generate_with_system(self) -> None:
        """generate() adds system message when provided."""
        mock_sdk = MagicMock()
        choice = SimpleNamespace(message=SimpleNamespace(content="response"))
        mock_sdk.OpenAI.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[choice])

        provider = self._make_provider(mock_sdk)
        provider.generate("prompt", system="Be helpful")

        call_kwargs = mock_sdk.OpenAI.return_value.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "Be helpful"}
        assert messages[1] == {"role": "user", "content": "prompt"}

    def test_generate_without_system(self) -> None:
        """generate() omits system message when not provided."""
        mock_sdk = MagicMock()
        choice = SimpleNamespace(message=SimpleNamespace(content="response"))
        mock_sdk.OpenAI.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[choice])

        provider = self._make_provider(mock_sdk)
        provider.generate("prompt")

        call_kwargs = mock_sdk.OpenAI.return_value.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "prompt"}

    def test_generate_with_config_override(self) -> None:
        """generate() uses config overrides when provided."""
        mock_sdk = MagicMock()
        choice = SimpleNamespace(message=SimpleNamespace(content="response"))
        mock_sdk.OpenAI.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[choice])

        provider = self._make_provider(mock_sdk)
        config = _FakeConfig(model="gpt-4-turbo", max_tokens=2048, temperature=0.8)
        provider.generate("prompt", config=config)

        call_kwargs = mock_sdk.OpenAI.return_value.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4-turbo"
        assert call_kwargs.kwargs["max_tokens"] == 2048
        assert call_kwargs.kwargs["temperature"] == 0.8

    def test_generate_empty_response(self) -> None:
        """generate() returns '' when API returns empty choices."""
        mock_sdk = MagicMock()
        mock_sdk.OpenAI.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[])

        provider = self._make_provider(mock_sdk)
        result = provider.generate("prompt")

        assert result == ""

    def test_generate_null_content(self) -> None:
        """generate() returns '' when message content is None."""
        mock_sdk = MagicMock()
        choice = SimpleNamespace(message=SimpleNamespace(content=None))
        mock_sdk.OpenAI.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[choice])

        provider = self._make_provider(mock_sdk)
        result = provider.generate("prompt")

        assert result == ""

    def test_generate_api_error_propagates(self) -> None:
        """generate() propagates API exceptions."""
        mock_sdk = MagicMock()
        mock_sdk.OpenAI.return_value.chat.completions.create.side_effect = ConnectionError("connection refused")

        provider = self._make_provider(mock_sdk)
        with pytest.raises(ConnectionError, match="connection refused"):
            provider.generate("prompt")

    def test_missing_sdk_raises_import_error(self) -> None:
        """OpenAIProvider raises ImportError when SDK is not installed."""
        with patch("scistudio.blocks.ai.providers._openai_sdk", None), pytest.raises(ImportError, match="openai"):
            OpenAIProvider(api_key="key")

    def test_missing_api_key_raises(self) -> None:
        """OpenAIProvider raises ValueError when no key is available."""
        mock_sdk = MagicMock()
        env_no_key = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with (
            patch("scistudio.blocks.ai.providers._openai_sdk", mock_sdk),
            patch.dict(os.environ, env_no_key, clear=True),
            pytest.raises(ValueError, match="No OpenAI API key"),
        ):
            OpenAIProvider()

    def test_explicit_api_key(self) -> None:
        """OpenAIProvider uses the explicitly provided key."""
        mock_sdk = MagicMock()
        with patch("scistudio.blocks.ai.providers._openai_sdk", mock_sdk):
            OpenAIProvider(api_key="explicit-key")
            mock_sdk.OpenAI.assert_called_once_with(api_key="explicit-key")

    def test_satisfies_protocol(self) -> None:
        """OpenAIProvider instances satisfy LLMProvider protocol."""
        mock_sdk = MagicMock()
        provider = self._make_provider(mock_sdk)
        assert isinstance(provider, LLMProvider)
