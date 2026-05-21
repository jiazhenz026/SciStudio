"""LLM provider abstraction (Anthropic, OpenAI, local).

This module defines the ``LLMProvider`` protocol and two concrete
implementations:

* **AnthropicProvider** -- calls the Anthropic Messages API via the
  ``anthropic`` SDK (optional dependency).
* **OpenAIProvider** -- calls the OpenAI Chat Completions API via the
  ``openai`` SDK (optional dependency).

Both SDKs are optional.  If neither is installed the framework still
works -- only AI-powered features become unavailable (ADR-013).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional SDK imports -- guarded so the module always loads
# ---------------------------------------------------------------------------

try:
    import anthropic as _anthropic_sdk
except ImportError:  # pragma: no cover
    _anthropic_sdk = None  # type: ignore[assignment]

try:
    import openai as _openai_sdk
except ImportError:  # pragma: no cover
    _openai_sdk = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers.

    All AI features call through this interface so that the concrete
    backend (Anthropic, OpenAI, local, ...) can be swapped via
    configuration.
    """

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        config: Any = None,
    ) -> str:
        """Send *prompt* to the LLM and return the text response.

        Parameters
        ----------
        prompt:
            The user message / main prompt.
        system:
            Optional system-level instruction.
        config:
            Optional per-call configuration override (typically an
            ``AIConfig`` instance).  When *None* the provider uses
            its own defaults.

        Returns
        -------
        str
            The model's text response.
        """
        ...


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """LLM provider backed by the Anthropic Messages API.

    Parameters
    ----------
    api_key:
        Anthropic API key.  Falls back to the ``ANTHROPIC_API_KEY``
        environment variable when empty or *None*.
    model:
        Model identifier, e.g. ``"claude-sonnet-4-20250514"``.
    max_tokens:
        Default maximum tokens for responses.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ) -> None:
        if _anthropic_sdk is None:
            raise ImportError(
                "The 'anthropic' package is required for AnthropicProvider. Install it with: pip install 'scistudio[ai]'"
            )
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "No Anthropic API key provided. Set ANTHROPIC_API_KEY or pass api_key to AnthropicProvider."
            )
        self._client = _anthropic_sdk.Anthropic(api_key=resolved_key)
        self._model = model
        self._max_tokens = max_tokens

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        config: Any = None,
    ) -> str:
        """Call the Anthropic Messages API and return the text response."""
        model = self._model
        max_tokens = self._max_tokens
        temperature: float = 0.2

        if config is not None:
            if config.model:
                model = config.model
            if config.max_tokens:
                max_tokens = config.max_tokens
            temperature = config.temperature

        kwargs: dict[str, object] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        try:
            response = self._client.messages.create(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:
            logger.error("Anthropic API call failed: %s", exc)
            raise

        # Extract text from the first content block.
        if response.content and hasattr(response.content[0], "text"):
            return str(response.content[0].text)
        return ""


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """LLM provider backed by the OpenAI Chat Completions API.

    Parameters
    ----------
    api_key:
        OpenAI API key.  Falls back to the ``OPENAI_API_KEY`` environment
        variable when empty or *None*.
    model:
        Model identifier, e.g. ``"gpt-4o"``.
    max_tokens:
        Default maximum tokens for responses.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o",
        max_tokens: int = 4096,
    ) -> None:
        if _openai_sdk is None:
            raise ImportError(
                "The 'openai' package is required for OpenAIProvider. Install it with: pip install 'scistudio[ai]'"
            )
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key:
            raise ValueError("No OpenAI API key provided. Set OPENAI_API_KEY or pass api_key to OpenAIProvider.")
        self._client = _openai_sdk.OpenAI(api_key=resolved_key)
        self._model = model
        self._max_tokens = max_tokens

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        config: Any = None,
    ) -> str:
        """Call the OpenAI Chat Completions API and return the text response."""
        model = self._model
        max_tokens = self._max_tokens
        temperature: float = 0.2

        if config is not None:
            if config.model:
                model = config.model
            if config.max_tokens:
                max_tokens = config.max_tokens
            temperature = config.temperature

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            logger.error("OpenAI API call failed: %s", exc)
            raise

        # Extract text from the first choice.
        if response.choices and response.choices[0].message.content:
            return str(response.choices[0].message.content)
        return ""
