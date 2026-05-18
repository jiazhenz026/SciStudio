"""Tests for ``scieasy.qa.translation.settings`` — ADR-042 §22.5."""

from __future__ import annotations

import pytest

from scieasy.qa.translation.settings import TranslationSettings


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every ``SCIEASY_TRANSLATION_*`` env var the test inherits.

    Without this guard, a real ``SCIEASY_TRANSLATION_DEEPL_API_KEY`` in
    the developer's shell (or in CI) leaks into the default-value
    assertions below.
    """
    import os

    for key in list(os.environ):
        if key.startswith("SCIEASY_TRANSLATION_"):
            monkeypatch.delenv(key, raising=False)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    s = TranslationSettings()
    assert s.provider == "deepl"
    assert s.deepl_api_key is None
    assert s.deepl_endpoint == "https://api-free.deepl.com/v2/translate"
    assert s.google_credentials_path is None
    assert s.google_project_id is None
    assert s.azure_endpoint is None
    assert s.azure_key is None
    assert s.azure_region is None
    assert s.http_timeout_seconds == 30.0


def test_env_loading_deepl(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("SCIEASY_TRANSLATION_PROVIDER", "deepl")
    monkeypatch.setenv("SCIEASY_TRANSLATION_DEEPL_API_KEY", "test-key-xyz")
    monkeypatch.setenv(
        "SCIEASY_TRANSLATION_DEEPL_ENDPOINT",
        "https://api.deepl.com/v2/translate",
    )
    s = TranslationSettings()
    assert s.provider == "deepl"
    assert s.deepl_api_key == "test-key-xyz"
    assert s.deepl_endpoint == "https://api.deepl.com/v2/translate"


def test_env_loading_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("SCIEASY_TRANSLATION_PROVIDER", "manual")
    s = TranslationSettings()
    assert s.provider == "manual"


def test_env_loading_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("SCIEASY_TRANSLATION_PROVIDER", "azure")
    monkeypatch.setenv(
        "SCIEASY_TRANSLATION_AZURE_ENDPOINT",
        "https://example.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("SCIEASY_TRANSLATION_AZURE_KEY", "azkey")
    monkeypatch.setenv("SCIEASY_TRANSLATION_AZURE_REGION", "eastus")
    s = TranslationSettings()
    assert s.provider == "azure"
    assert s.azure_endpoint == "https://example.cognitiveservices.azure.com"
    assert s.azure_key == "azkey"
    assert s.azure_region == "eastus"


def test_extra_env_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unrelated SCIEASY_* env vars must NOT raise."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SCIEASY_TRANSLATION_PROVIDER", "manual")
    monkeypatch.setenv("SCIEASY_TRANSLATION_UNKNOWN_THING", "ignored")
    s = TranslationSettings()
    assert s.provider == "manual"


def test_invalid_provider_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    _clear_env(monkeypatch)
    monkeypatch.setenv("SCIEASY_TRANSLATION_PROVIDER", "not-a-real-provider")
    with pytest.raises(ValidationError):
        TranslationSettings()


def test_require_deepl_key_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("SCIEASY_TRANSLATION_DEEPL_API_KEY", "abc")
    s = TranslationSettings()
    assert s.require_deepl_key() == "abc"


def test_require_deepl_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    s = TranslationSettings()
    with pytest.raises(RuntimeError, match="SCIEASY_TRANSLATION_DEEPL_API_KEY"):
        s.require_deepl_key()


def test_key_does_not_appear_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """``repr=False`` on credentials prevents accidental leakage in logs."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SCIEASY_TRANSLATION_DEEPL_API_KEY", "super-secret-key")
    monkeypatch.setenv("SCIEASY_TRANSLATION_AZURE_KEY", "another-secret")
    s = TranslationSettings()
    assert "super-secret-key" not in repr(s)
    assert "another-secret" not in repr(s)
