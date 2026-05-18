"""Tests for the four translation providers — ADR-042 §22.4.

DeepL/Google/Azure use httpx mocks (``httpx.MockTransport``); Manual
runs identity.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from scieasy.qa.translation.client import (
    AzureProvider,
    DeepLProvider,
    GoogleProvider,
    ManualProvider,
)
from scieasy.qa.translation.settings import TranslationSettings


def _settings(**overrides: Any) -> TranslationSettings:
    defaults: dict[str, Any] = {
        "provider": "manual",
        "deepl_api_key": "fake-deepl-key",
        "azure_endpoint": "https://example.cognitiveservices.azure.com",
        "azure_key": "fake-azure-key",
        "azure_region": "eastus",
        "http_timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return TranslationSettings(**defaults)


# ---------------------------------------------------------------------------
# Manual
# ---------------------------------------------------------------------------


def test_manual_provider_is_identity() -> None:
    p = ManualProvider()
    out = p.translate("hello world", source_lang="en", target_lang="zh-CN")
    assert out == "hello world"


def test_manual_provider_name() -> None:
    assert ManualProvider().name == "manual"


# ---------------------------------------------------------------------------
# DeepL
# ---------------------------------------------------------------------------


def _deepl_mock_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "translations": [
                {
                    "detected_source_language": "EN",
                    "text": "你好",
                }
            ]
        },
    )


def test_deepl_provider_happy_path() -> None:
    transport = httpx.MockTransport(_deepl_mock_response)
    client_http = httpx.Client(transport=transport)
    provider = DeepLProvider(_settings(), client=client_http)
    out = provider.translate("hello", source_lang="en", target_lang="zh-CN")
    assert out == "你好"


def test_deepl_provider_sends_xml_tag_handling() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = dict(httpx.QueryParams(request.content.decode("utf-8")))
        captured.update(body)
        return _deepl_mock_response(request)

    transport = httpx.MockTransport(handler)
    client_http = httpx.Client(transport=transport)
    provider = DeepLProvider(_settings(), client=client_http)
    provider.translate("hi", source_lang="en", target_lang="zh-CN")
    assert captured["tag_handling"] == "xml"
    assert "x" in captured["ignore_tags"].split(",")
    # Target lang normalised to ``ZH`` for DeepL.
    assert captured["target_lang"] == "ZH"


def test_deepl_provider_missing_key_raises() -> None:
    provider = DeepLProvider(_settings(deepl_api_key=None))
    with pytest.raises(RuntimeError, match="DEEPL_API_KEY"):
        provider.translate("hello", source_lang="en", target_lang="zh-CN")


def test_deepl_provider_empty_translations_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"translations": []})

    transport = httpx.MockTransport(handler)
    client_http = httpx.Client(transport=transport)
    provider = DeepLProvider(_settings(), client=client_http)
    with pytest.raises(RuntimeError, match="no translations"):
        provider.translate("hi", source_lang="en", target_lang="zh-CN")


def test_deepl_provider_http_error_propagates() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    transport = httpx.MockTransport(handler)
    client_http = httpx.Client(transport=transport)
    provider = DeepLProvider(_settings(), client=client_http)
    with pytest.raises(httpx.HTTPStatusError):
        provider.translate("hi", source_lang="en", target_lang="zh-CN")


def test_deepl_provider_authorization_header() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return _deepl_mock_response(request)

    transport = httpx.MockTransport(handler)
    client_http = httpx.Client(transport=transport)
    provider = DeepLProvider(_settings(), client=client_http)
    provider.translate("hi", source_lang="en", target_lang="zh-CN")
    assert "fake-deepl-key" in captured_headers["authorization"]


# ---------------------------------------------------------------------------
# Azure
# ---------------------------------------------------------------------------


def _azure_mock(text: str = "你好") -> httpx.MockTransport:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"translations": [{"text": text, "to": "zh-Hans"}]}],
        )

    return httpx.MockTransport(handler)


def test_azure_provider_happy_path() -> None:
    client_http = httpx.Client(transport=_azure_mock())
    provider = AzureProvider(_settings(), client=client_http)
    out = provider.translate("hello", source_lang="en", target_lang="zh-CN")
    assert out == "你好"


def test_azure_provider_sends_region_header() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(200, json=[{"translations": [{"text": "x", "to": "zh-Hans"}]}])

    client_http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = AzureProvider(_settings(azure_region="westus"), client=client_http)
    provider.translate("hi", source_lang="en", target_lang="zh-CN")
    assert captured.get("ocp-apim-subscription-region") == "westus"


def test_azure_provider_missing_key_raises() -> None:
    provider = AzureProvider(_settings(azure_key=None))
    with pytest.raises(RuntimeError, match="AZURE_KEY"):
        provider.translate("hi", source_lang="en", target_lang="zh-CN")


def test_azure_provider_missing_endpoint_raises() -> None:
    provider = AzureProvider(_settings(azure_endpoint=None))
    with pytest.raises(RuntimeError, match="AZURE_ENDPOINT"):
        provider.translate("hi", source_lang="en", target_lang="zh-CN")


def test_azure_provider_empty_response_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{}])

    client_http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = AzureProvider(_settings(), client=client_http)
    with pytest.raises(RuntimeError, match="no translations"):
        provider.translate("hi", source_lang="en", target_lang="zh-CN")


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


def test_google_provider_missing_credentials_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``google-auth`` is not installed OR no credentials path is
    set, GoogleProvider must raise with a clear message rather than
    silently degrading."""
    provider = GoogleProvider(_settings(google_credentials_path=None))
    # Monkeypatch the import to simulate google-auth absent.
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - branch test
        if name.startswith("google"):
            raise ImportError("simulated absence")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="google-auth"):
        provider.translate("hi", source_lang="en", target_lang="zh-CN")


def test_google_provider_translates_when_token_fetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If google-auth is present and yields a token, the HTTP call goes
    out and the response is parsed."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Verify the Authorization header carries our fake token.
        assert request.headers["authorization"].startswith("Bearer ")
        body = json.loads(request.content)
        assert body["q"] == "hello"
        return httpx.Response(
            200,
            json={"data": {"translations": [{"translatedText": "你好"}]}},
        )

    client_http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GoogleProvider(
        _settings(google_credentials_path="/tmp/creds.json"),
        client=client_http,
    )
    # Bypass actual google-auth by patching the method that fetches the
    # token; we are testing the HTTP path, not Google's auth library.
    monkeypatch.setattr(provider, "_fetch_access_token", lambda: "fake-token")
    out = provider.translate("hello", source_lang="en", target_lang="zh-CN")
    assert out == "你好"


def test_google_provider_empty_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"translations": []}})

    client_http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GoogleProvider(
        _settings(google_credentials_path="/tmp/creds.json"),
        client=client_http,
    )
    monkeypatch.setattr(provider, "_fetch_access_token", lambda: "fake-token")
    with pytest.raises(RuntimeError, match="no translations"):
        provider.translate("hi", source_lang="en", target_lang="zh-CN")
