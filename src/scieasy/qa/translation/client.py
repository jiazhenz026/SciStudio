"""Translator client + providers — ADR-042 §22.3 / §22.4.

This module exposes a single facade :class:`TranslatorClient` that
dispatches to one of four pluggable providers:

- :class:`DeepLProvider` — default (ADR-042 §22.4); highest quality.
- :class:`GoogleProvider` — Google Cloud Translate v3.
- :class:`AzureProvider` — Azure Translator v3.
- :class:`ManualProvider` — offline stub (no network); used for local
  development and as the safe default before keys are configured.

The translation rule (per ADR-042 §22 and the Phase 1D dispatch
contract) is enforced by :func:`mask_non_translatable` /
:func:`unmask`: every non-translatable token is replaced by an
``<x id="N"/>`` self-closing XML placeholder before the provider call,
and restored verbatim afterwards. The placeholder shape (``x`` tag,
self-closing) is chosen because:

1. DeepL's ``tag_handling="xml"`` mode treats it as an unsplittable
   atomic token and never translates its body or attributes (ADR-042
   §22.3 references this behaviour);
2. Google / Azure both pass-through unknown XML tags by default;
3. The single-letter tag name keeps the masked document compact
   (relevant for DeepL's per-request character quotas).

We additionally pass DeepL ``ignore_tags=[code, pre, kbd, samp]`` as a
defence-in-depth layer in case our regex misses a token class — the
DeepL engine will preserve those tags' bodies even if we forgot to
mask them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

import httpx

from scieasy.qa.translation.settings import ProviderName, TranslationSettings

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Non-translatable token masking
# ---------------------------------------------------------------------------


# Order matters: more-specific patterns first. Each pattern's match is
# replaced by a placeholder; placeholders are restored after the
# provider returns its translation.
#
# Each pattern is tagged with a short label that appears in the
# placeholder's ``data-kind`` attribute. The label is purely for
# debugging — DeepL/Google/Azure don't read it.
_MASK_PATTERNS: Final[list[tuple[str, re.Pattern[str]]]] = [
    # Fenced code blocks (multi-line, with optional language tag).
    # Must come before inline-code so the inner backticks don't leak.
    ("code-fence", re.compile(r"```[\s\S]*?```", re.MULTILINE)),
    # YAML frontmatter (entire ---…--- block at start of doc).
    ("frontmatter", re.compile(r"\A---\n[\s\S]*?\n---\n", re.MULTILINE)),
    # HTML/XML tags (including self-closing, with attributes).
    # NOTE: the negative-lookahead ``(?!x )`` excludes our own
    # placeholder shape ``<x id="N" .../>`` so the html-tag pass does
    # not double-mask placeholders inserted by earlier passes.
    ("html-tag", re.compile(r"<(?!x )[a-zA-Z/][^<>]*?>")),
    # Markdown image targets — ``![alt](src)`` -> mask ``src`` only.
    # We capture ``src`` (group 2) and replace with placeholder.
    # Note: this is handled specially because we want to preserve the
    # surrounding ``![alt](`` and ``)``.
    # Implemented as a callback below — kept here for documentation.
    # ("md-image-target", re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")),
    # Markdown link targets — same as image, just without leading ``!``.
    # Also handled as callback.
    # ("md-link-target", re.compile(r"\[([^\]]*)\]\(([^)]+)\)")),
    # Inline code (single backticks, non-greedy, single-line).
    ("code-inline", re.compile(r"`[^`\n]+`")),
    # Technical identifiers: ADR-042, SPEC-007, TC-1D.9, PR #1136,
    # issue #1143, §22.5, etc. We allow optional section suffix
    # (``§<n>(\.<n>)*``).
    (
        "tech-id",
        re.compile(
            r"\b(?:ADR|SPEC|TC|PR|RFC)[-]?\d+[A-Za-z]?(?:\.\d+)*"
            r"(?:\s*§\s*\d+(?:\.\d+)*)?"
            r"|#\d{2,}"
            r"|§\s*\d+(?:\.\d+)*"
        ),
    ),
    # Dotted Python paths: at least 3 dotted segments, alnum/underscore.
    # Avoids over-matching English sentences ending in a period.
    (
        "dotted-path",
        re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*){2,}\b"),
    ),
    # File paths: anything containing ``/`` (POSIX) and not starting
    # with whitespace — matches ``src/scieasy/qa/translation/client.py``,
    # ``./scripts/x.py``, ``../docs/foo.md``, etc. Bounded to avoid
    # eating English sentences.
    (
        "file-path",
        re.compile(r"(?:\.{1,2}/)?[\w.\-]+(?:/[\w.\-]+){1,}\b"),
    ),
]


_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r'<x id="(\d+)" data-kind="[^"]*"/>')


# ---------------------------------------------------------------------------
# Markdown link/image target masking
# ---------------------------------------------------------------------------
#
# Markdown links/images need special handling: we want to translate the
# *visible* text (alt/link text) but preserve the URL. A single regex
# replacement can't easily split these, so we use a callback-based
# substitution.

_MD_LINK_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<bang>!?)\[(?P<text>[^\]]*)\]\((?P<url>[^)\s]+)(?P<title>\s+\"[^\"]*\")?\)"
)


def _mask_markdown_links(source: str, store: list[tuple[str, str]]) -> str:
    """Replace ``[text](url)`` and ``![alt](src)`` with
    ``[text](<x id=N data-kind="md-url"/>)`` so that ``text``/``alt``
    remain translatable but the URL is frozen.
    """

    def _replace(match: re.Match[str]) -> str:
        url = match.group("url")
        title = match.group("title") or ""
        # Preserve ``title="..."`` (e.g., ``[text](url "title")``)
        # alongside the URL by stashing them together.
        token = url + title
        idx = len(store)
        store.append(("md-url", token))
        bang = match.group("bang")
        text = match.group("text")
        placeholder = f'<x id="{idx}" data-kind="md-url"/>'
        return f"{bang}[{text}]({placeholder})"

    return _MD_LINK_RE.sub(_replace, source)


def mask_non_translatable(source: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace every non-translatable token with an ``<x id=N/>``
    placeholder.

    Returns ``(masked_text, store)`` where ``store`` is a list of
    ``(kind, original_token)`` tuples indexed by placeholder ``id``.

    The order of substitution is significant: more-specific patterns
    (code fences, frontmatter) run first so that their bodies don't
    leak into later patterns (e.g. an inline-code backtick pair living
    inside a code fence).
    """
    store: list[tuple[str, str]] = []
    masked = source

    # Markdown links/images first — they need special split handling.
    masked = _mask_markdown_links(masked, store)

    for kind, pattern in _MASK_PATTERNS:

        def _replace(match: re.Match[str], _kind: str = kind) -> str:
            idx = len(store)
            store.append((_kind, match.group(0)))
            return f'<x id="{idx}" data-kind="{_kind}"/>'

        masked = pattern.sub(_replace, masked)

    return masked, store


def unmask(translated: str, store: list[tuple[str, str]]) -> str:
    """Restore placeholders in ``translated`` from ``store``.

    Robust against:

    - Placeholder ordering changes by the provider (translation engines
      may rearrange tokens).
    - Whitespace-normalised placeholders (some providers strip the
      ``data-kind`` attribute; we match by ``id`` only).
    """

    def _replace(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if idx >= len(store):
            logger.warning(
                "unmask: placeholder id=%d not in store (size=%d); leaving placeholder in place",
                idx,
                len(store),
            )
            return match.group(0)
        return store[idx][1]

    # Some providers downcase or rewrite our placeholder slightly.
    # Match on the ``id`` regardless of surrounding attribute order.
    relaxed = re.compile(r'<x [^>]*?id="(\d+)"[^>]*?/?>', re.IGNORECASE)
    return relaxed.sub(_replace, translated)


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TranslationProvider(Protocol):
    """Protocol every translation provider implements.

    Implementations receive *already-masked* text and return translated
    text with placeholders preserved. The :class:`TranslatorClient`
    facade handles mask/unmask and file I/O — providers only translate
    strings.
    """

    name: str

    def translate(
        self, text: str, *, source_lang: str, target_lang: str
    ) -> str:  # pragma: no cover — Protocol body, never executed
        ...


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class ManualProvider:
    """Offline stub provider — emits a ``needs-manual`` placeholder
    document. Per ADR-042 §22.5: "Local development can use the manual
    provider (no network calls; emits a stub translation marked
    'needs-manual')."

    Used by:

    - Local developer machines that don't have any provider key set.
    - Sub-PR 1's initial commit of ``docs/zh-CN/adr/ADR-04{2,3,4}.md``
      (CI re-translates with DeepL on first push after merge).
    - Unit tests that exercise the full client end-to-end without
      hitting any network.
    """

    name = "manual"

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        # Identity translation. The doc body remains in English; the
        # ``needs-manual`` marker added by :meth:`TranslatorClient.
        # translate_file` distinguishes stubs from real translations.
        return text


class DeepLProvider:
    """DeepL v2 REST provider. Default per ADR-042 §22.4.

    Uses ``tag_handling=xml`` + ``ignore_tags=code,pre,kbd,samp`` as
    defence-in-depth alongside our explicit placeholder masking.
    """

    name = "deepl"

    def __init__(self, settings: TranslationSettings, *, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.http_timeout_seconds)

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        api_key = self._settings.require_deepl_key()
        # DeepL expects ``ZH`` (uppercase, no region) for Chinese in
        # the free tier; the Pro tier accepts ``ZH-HANS`` but the free
        # one rejects it. Normalise here.
        deepl_target = _normalise_deepl_lang(target_lang)
        response = self._client.post(
            self._settings.deepl_endpoint,
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            data={
                "text": text,
                "source_lang": source_lang.upper(),
                "target_lang": deepl_target,
                "tag_handling": "xml",
                "ignore_tags": "code,pre,kbd,samp,x",
                "preserve_formatting": "1",
            },
        )
        response.raise_for_status()
        payload = response.json()
        translations = payload.get("translations") or []
        if not translations:
            raise RuntimeError(f"DeepL returned no translations for {len(text)}-char request: {payload!r}")
        return str(translations[0]["text"])


def _normalise_deepl_lang(code: str) -> str:
    """Map ``zh-CN`` / ``zh-Hans`` / ``zh`` to DeepL's accepted code.

    DeepL accepts ``ZH`` on the free tier and ``ZH-HANS`` / ``ZH-HANT``
    on Pro. We default to ``ZH`` which works on both.
    """
    upper = code.upper()
    if upper.startswith("ZH"):
        return "ZH"
    return upper


class GoogleProvider:
    """Google Cloud Translate v3 provider (basic v2 API for simplicity).

    Implementation note: we use the v2 REST endpoint
    (``https://translation.googleapis.com/language/translate/v2``)
    rather than the v3 gRPC endpoint to avoid pulling in the
    ``google-cloud-translate`` dep tree. Authentication is via the
    service-account JSON file path in ``google_credentials_path``;
    callers can also pre-set ``GOOGLE_APPLICATION_CREDENTIALS`` and
    leave ``google_credentials_path`` unset.
    """

    name = "google"

    def __init__(self, settings: TranslationSettings, *, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.http_timeout_seconds)

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        token = self._fetch_access_token()
        # Google v2 API: POST JSON body with ``q``, ``source``,
        # ``target``, ``format`` ("html" preserves our XML placeholders).
        response = self._client.post(
            "https://translation.googleapis.com/language/translate/v2",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            content=json.dumps(
                {
                    "q": text,
                    "source": source_lang,
                    "target": _normalise_google_lang(target_lang),
                    "format": "html",
                }
            ).encode("utf-8"),
        )
        response.raise_for_status()
        payload = response.json()
        translations = (payload.get("data") or {}).get("translations") or []
        if not translations:
            raise RuntimeError(f"Google returned no translations: {payload!r}")
        return str(translations[0]["translatedText"])

    def _fetch_access_token(self) -> str:
        """Resolve a Google OAuth2 access token from the service-account
        credentials file.

        We avoid importing ``google-auth`` to keep the dep footprint
        minimal — the credentials file IS itself the source of truth,
        and CI environments typically set ``GOOGLE_APPLICATION_CREDENTIALS``
        pointing at it. For now we delegate to ``google-auth`` ONLY if
        it's installed; otherwise we raise a clear error.
        """
        # TODO(#1136): light Google integration — uses ``google-auth``
        # if installed, else raises with a pointer to the optional dep.
        # Out of scope for ADR-042 §22.4 (default provider is DeepL).
        # Followup: open a dedicated issue if Google becomes a routine
        # CI provider.
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
        except ImportError as exc:
            raise RuntimeError(
                "GoogleProvider requires the optional 'google-auth' "
                "package. Install it with 'pip install google-auth' or "
                "use --provider=deepl."
            ) from exc

        creds_path = self._settings.google_credentials_path
        if not creds_path:
            raise RuntimeError(
                "GoogleProvider requires SCIEASY_TRANSLATION_GOOGLE_CREDENTIALS_PATH "
                "to point at a service-account JSON file."
            )
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/cloud-translation"],
        )
        credentials.refresh(Request())
        return str(credentials.token)


def _normalise_google_lang(code: str) -> str:
    """Google accepts ``zh-CN`` / ``zh-TW`` directly; pass through."""
    return code


class AzureProvider:
    """Azure Translator v3 provider.

    Authentication is via the subscription key (``azure_key``) plus
    optional region (``azure_region``).
    """

    name = "azure"

    def __init__(self, settings: TranslationSettings, *, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.http_timeout_seconds)

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        if not self._settings.azure_key:
            raise RuntimeError(
                "AzureProvider requires SCIEASY_TRANSLATION_AZURE_KEY. Set the env var or use --provider=deepl."
            )
        if not self._settings.azure_endpoint:
            raise RuntimeError("AzureProvider requires SCIEASY_TRANSLATION_AZURE_ENDPOINT.")
        headers = {
            "Ocp-Apim-Subscription-Key": self._settings.azure_key,
            "Content-Type": "application/json",
        }
        if self._settings.azure_region:
            headers["Ocp-Apim-Subscription-Region"] = self._settings.azure_region
        params = {
            "api-version": "3.0",
            "from": source_lang,
            "to": _normalise_azure_lang(target_lang),
            "textType": "html",
        }
        response = self._client.post(
            self._settings.azure_endpoint.rstrip("/") + "/translate",
            headers=headers,
            params=params,
            json=[{"text": text}],
        )
        response.raise_for_status()
        payload = response.json()
        if not payload or "translations" not in payload[0]:
            raise RuntimeError(f"Azure returned no translations: {payload!r}")
        return str(payload[0]["translations"][0]["text"])


def _normalise_azure_lang(code: str) -> str:
    """Azure expects ``zh-Hans`` for Simplified Chinese (not ``zh-CN``)."""
    if code.lower() in ("zh-cn", "zh-hans", "zh"):
        return "zh-Hans"
    if code.lower() in ("zh-tw", "zh-hant"):
        return "zh-Hant"
    return code


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class TranslatorClient:
    """Facade over the four providers.

    Construct via :meth:`from_provider_name` or :meth:`from_settings`
    in normal use; the constructor accepts a pre-built provider for
    dependency injection in tests.
    """

    NEEDS_MANUAL_MARKER: Final[str] = "needs-manual"

    def __init__(self, provider: TranslationProvider) -> None:
        self._provider = provider

    @property
    def provider(self) -> TranslationProvider:
        return self._provider

    @classmethod
    def from_settings(cls, settings: TranslationSettings) -> TranslatorClient:
        """Build a client from explicit settings (skips env loading)."""
        return cls(_build_provider(settings.provider, settings))

    @classmethod
    def from_provider_name(
        cls,
        name: ProviderName | str,
        *,
        settings: TranslationSettings | None = None,
    ) -> TranslatorClient:
        """Build a client by provider name.

        ``settings`` defaults to a fresh :class:`TranslationSettings`
        (which reads from env vars). Pass an explicit settings object
        to override credentials / endpoints from code.
        """
        settings = settings or TranslationSettings()
        if name not in ("deepl", "google", "azure", "manual"):
            raise ValueError(f"Unknown provider {name!r}. Expected one of: deepl, google, azure, manual.")
        return cls(_build_provider(name, settings))

    # ------------------------------------------------------------------
    # String / file translation
    # ------------------------------------------------------------------

    def translate_text(
        self,
        text: str,
        *,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
    ) -> str:
        """Translate a single string, applying mask/unmask around the
        provider call.

        Returns the translated text with non-translatable tokens
        restored in-place.
        """
        masked, store = mask_non_translatable(text)
        translated = self._provider.translate(masked, source_lang=source_lang, target_lang=target_lang)
        return unmask(translated, store)

    def translate_file(
        self,
        src_path: Path,
        *,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
    ) -> str:
        """Translate a file's contents and return the translated string.

        The caller is responsible for writing the result to disk via
        :func:`write_translation`. ADR-042 §22.3's reference
        implementation uses this exact split.
        """
        text = src_path.read_text(encoding="utf-8")
        translated = self.translate_text(text, source_lang=source_lang, target_lang=target_lang)
        if self._provider.name == "manual":
            translated = _annotate_manual_stub(translated, self.NEEDS_MANUAL_MARKER)
        return translated


def _build_provider(name: ProviderName, settings: TranslationSettings) -> TranslationProvider:
    if name == "deepl":
        return DeepLProvider(settings)
    if name == "google":
        return GoogleProvider(settings)
    if name == "azure":
        return AzureProvider(settings)
    if name == "manual":
        return ManualProvider()
    raise ValueError(f"Unknown provider: {name!r}")  # pragma: no cover


def _annotate_manual_stub(text: str, marker: str) -> str:
    """Stamp ``needs-manual`` into a manual-provider stub.

    Per ADR-042 §22.5: the manual provider emits a stub translation
    marked ``needs-manual``. We inject the marker into the
    frontmatter (if present) or at the top of the document.
    """
    fm_match = re.match(r"\A(---\n)([\s\S]*?)(\n---\n)", text)
    if fm_match:
        front_open, body, front_close = fm_match.groups()
        if f"translation_status: {marker}" in body:
            return text  # already annotated
        if "translation_status:" in body:
            # Replace existing value.
            body = re.sub(
                r"^translation_status:.*$",
                f"translation_status: {marker}",
                body,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            body = body.rstrip() + f"\ntranslation_status: {marker}"
        return front_open + body + front_close + text[fm_match.end() :]
    # No frontmatter — prepend an HTML comment so we don't break
    # downstream parsers.
    return f"<!-- translation_status: {marker} -->\n{text}"


# ---------------------------------------------------------------------------
# File-pair walking + freshness check (used by the CLI)
# ---------------------------------------------------------------------------


_SOURCE_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^source_sha:\s*['\"]?([0-9a-f]{6,64})['\"]?\s*$", re.MULTILINE)


def file_sha(path: Path) -> str:
    """Stable content hash for incremental-translation freshness checks
    (ADR-042 §22.6).

    We use SHA-256 truncated to 16 hex chars; collisions are
    cryptographically improbable for the doc-set size we care about.
    """
    h = hashlib.sha256(path.read_bytes())
    return h.hexdigest()[:16]


def translation_is_up_to_date(src_path: Path, target_path: Path) -> bool:
    """Return True iff ``target_path`` exists and its frontmatter
    ``source_sha`` matches ``file_sha(src_path)``.

    Used by ``translate_docs.py --incremental`` per ADR-042 §22.6.
    """
    if not target_path.exists():
        return False
    try:
        target_text = target_path.read_text(encoding="utf-8")
    except OSError:
        return False
    match = _SOURCE_SHA_RE.search(target_text)
    if not match:
        return False
    return match.group(1) == file_sha(src_path)


def walk_pairs(
    source_root: Path,
    target_root: Path,
    *,
    suffixes: tuple[str, ...] = (".md",),
) -> Iterator[tuple[Path, Path]]:
    """Yield ``(src_path, target_path)`` pairs for every Markdown file
    under ``source_root``, excluding files already under
    ``target_root`` (so translating ``docs/`` does not re-translate
    ``docs/zh-CN/`` recursively).
    """
    source_root = source_root.resolve()
    target_root_resolved = target_root.resolve()
    # If the target root sits inside the source root (the standard
    # docs/ -> docs/zh-CN/ case), make sure we skip it.
    if source_root.is_file():
        # Single-file source.
        yield source_root, target_root / source_root.name
        return
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in suffixes:
            continue
        try:
            path.resolve().relative_to(target_root_resolved)
            continue  # under target tree
        except ValueError:
            pass
        rel = path.resolve().relative_to(source_root)
        target_path = target_root / rel
        yield path, target_path


def write_translation(target_path: Path, translated: str, *, source_sha: str) -> None:
    """Write ``translated`` to ``target_path`` and ensure the
    frontmatter carries ``source_sha: <sha>`` (ADR-042 §22.6).

    Creates parent dirs as needed.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    body = _ensure_source_sha(translated, source_sha)
    target_path.write_text(body, encoding="utf-8")


def _ensure_source_sha(text: str, source_sha: str) -> str:
    """Inject or replace top-level ``source_sha: <sha>`` in the
    document frontmatter. If no frontmatter exists, prepend one with
    the SHA.

    Uses a line-anchored regex so indented occurrences of
    ``source_sha:`` (e.g. inside a nested ``translations:`` list — ADRs
    track translation metadata that way per ADR-042 §22.6) are not
    rewritten by accident.
    """
    fm_match = re.match(r"\A(---\n)([\s\S]*?)(\n---\n)", text)
    top_level_sha = re.compile(r"^source_sha:.*$", re.MULTILINE)
    if fm_match:
        front_open, body, front_close = fm_match.groups()
        if top_level_sha.search(body):
            body = top_level_sha.sub(f"source_sha: '{source_sha}'", body, count=1)
        else:
            body = body.rstrip() + f"\nsource_sha: '{source_sha}'"
        return front_open + body + front_close + text[fm_match.end() :]
    return f"---\nsource_sha: '{source_sha}'\n---\n{text}"


def extract_source_sha(text: str) -> str | None:
    """Read ``source_sha`` from frontmatter, returning None if absent.

    Public helper exposed for the future ``complete_artifacts.check``
    tool (TC-1B.7) and for tests.
    """
    match = _SOURCE_SHA_RE.search(text)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Public helpers exposed for downstream tools (e.g. closure check)
# ---------------------------------------------------------------------------


def diagnose_text(text: str) -> dict[str, Any]:
    """Return a small diagnostic dict for ``text``.

    Used by the future ``translation_ok`` audit check (ADR-042 §22.6)
    to surface coverage stats without re-implementing the masking.
    """
    masked, store = mask_non_translatable(text)
    counts: dict[str, int] = {}
    for kind, _ in store:
        counts[kind] = counts.get(kind, 0) + 1
    return {
        "total_chars_source": len(text),
        "total_chars_masked": len(masked),
        "tokens_masked": len(store),
        "tokens_by_kind": counts,
    }
