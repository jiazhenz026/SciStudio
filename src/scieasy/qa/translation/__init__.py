"""Translator package — ADR-042 §22.

Provider-agnostic translation client used by ``scripts/translate_docs.py``
and the ``.github/workflows/translation.yml`` workflow to auto-translate
English source docs to ``docs/zh-CN/**``.

The translation rule (locked into ``mask_non_translatable``/``unmask`` +
DeepL XML tag-handling, per ADR-042 §22 and the dispatch contract):

  Translate meaningful prose only.

  DO NOT translate: code blocks (fenced ``` … ```), inline code
  (backticks), pseudocode blocks, class names, function names, dotted
  module paths, file paths, frontmatter YAML keys/values, Markdown link
  targets, image references, technical identifiers (TC-1D.9, ADR-042 §9,
  etc.).

Public surface:

- ``TranslatorClient`` — facade; pick a provider via
  :py:meth:`TranslatorClient.from_provider_name` or pass one explicitly.
- ``TranslationProvider`` — protocol every provider implements.
- ``DeepLProvider`` / ``GoogleProvider`` / ``AzureProvider`` /
  ``ManualProvider`` — concrete providers.
- ``TranslationSettings`` — pydantic-settings config (env prefix
  ``SCIEASY_TRANSLATION_``).
- ``mask_non_translatable`` / ``unmask`` — public helpers (also reused
  by tests and by the future doc-drift tool).
"""

from scieasy.qa.translation.client import (
    AzureProvider,
    DeepLProvider,
    GoogleProvider,
    ManualProvider,
    TranslationProvider,
    TranslatorClient,
    mask_non_translatable,
    unmask,
)
from scieasy.qa.translation.settings import TranslationSettings

__all__ = [
    "AzureProvider",
    "DeepLProvider",
    "GoogleProvider",
    "ManualProvider",
    "TranslationProvider",
    "TranslationSettings",
    "TranslatorClient",
    "mask_non_translatable",
    "unmask",
]
