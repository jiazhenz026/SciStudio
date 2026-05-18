"""Translation settings — ADR-042 §22.5.

``TranslationSettings`` reads provider credentials from environment
variables prefixed with ``SCIEASY_TRANSLATION_``. CI injects the DeepL
key via GitHub Secrets (``SCIEASY_TRANSLATION_DEEPL_API_KEY``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["deepl", "google", "azure", "manual"]


class TranslationSettings(BaseSettings):
    """Runtime configuration for the translator stack.

    All fields read from environment variables prefixed with
    ``SCIEASY_TRANSLATION_``. The ``manual`` provider requires no
    credentials and is the safe default for local development; CI uses
    DeepL via the ``SCIEASY_TRANSLATION_DEEPL_API_KEY`` secret per
    ADR-042 §22.5.
    """

    model_config = SettingsConfigDict(
        env_prefix="SCIEASY_TRANSLATION_",
        # Be tolerant of extra env vars (other SCIEASY_* prefixes exist
        # for ai/runtime config; we don't want to error on them).
        extra="ignore",
        # Avoid loading a global .env file from the cwd by default —
        # tests and CI both rely on explicit env-var injection.
        env_file=None,
    )

    provider: ProviderName = "deepl"
    """Active translation provider. ``manual`` skips network calls and
    emits a stub translation marked ``needs-manual`` (ADR-042 §22.5)."""

    deepl_api_key: str | None = Field(default=None, repr=False)
    """DeepL API key. Required when ``provider == 'deepl'``."""

    deepl_endpoint: str = "https://api-free.deepl.com/v2/translate"
    """DeepL endpoint. Use ``https://api.deepl.com/v2/translate`` for
    the Pro plan; default is the free tier for development affordance."""

    google_credentials_path: str | None = None
    """Path to a Google Cloud service-account JSON credentials file.
    Required when ``provider == 'google'``."""

    google_project_id: str | None = None
    """Google Cloud project ID. Required when ``provider == 'google'``."""

    azure_endpoint: str | None = None
    """Azure Translator endpoint. Required when ``provider == 'azure'``."""

    azure_key: str | None = Field(default=None, repr=False)
    """Azure Translator subscription key. Required when ``provider == 'azure'``."""

    azure_region: str | None = None
    """Azure Translator region (e.g. ``eastus``). Optional but
    recommended; some Azure subscriptions require it."""

    http_timeout_seconds: float = 30.0
    """Per-request HTTP timeout in seconds. Wraps the underlying
    ``httpx.Client`` timeout to avoid hung CI jobs."""

    def require_deepl_key(self) -> str:
        """Return the DeepL key or raise a clear error.

        Centralised so all DeepL code paths produce the same error
        message when the key is missing (matches ADR-042 §22.5's intent
        of failing loudly rather than silently degrading).
        """
        if not self.deepl_api_key:
            raise RuntimeError(
                "DeepL provider requested but SCIEASY_TRANSLATION_DEEPL_API_KEY "
                "is not set. Set the env var (CI injects it from GitHub "
                "Secrets) or use --provider=manual for local development."
            )
        return self.deepl_api_key
