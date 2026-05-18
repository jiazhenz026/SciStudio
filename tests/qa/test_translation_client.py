"""Tests for ``scieasy.qa.translation.client`` — ADR-042 §22.3.

Covers placeholder masking + unmasking, the manual-stub annotator,
``source_sha`` round-tripping, and the file-pair walker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.qa.translation.client import (
    ManualProvider,
    TranslatorClient,
    _annotate_manual_stub,
    _ensure_source_sha,
    _normalise_azure_lang,
    _normalise_deepl_lang,
    _normalise_google_lang,
    diagnose_text,
    extract_source_sha,
    file_sha,
    mask_non_translatable,
    translation_is_up_to_date,
    unmask,
    walk_pairs,
    write_translation,
)
from scieasy.qa.translation.settings import TranslationSettings

# ---------------------------------------------------------------------------
# Masking / unmasking
# ---------------------------------------------------------------------------


def test_mask_unmask_roundtrip_identity() -> None:
    """A document with no translatable prose round-trips unchanged."""
    source = "```python\nimport os\n```\n"
    masked, store = mask_non_translatable(source)
    assert len(store) == 1
    assert store[0][0] == "code-fence"
    # Unmask the (unchanged) masked text — should match source.
    assert unmask(masked, store) == source


def test_mask_protects_fenced_code() -> None:
    source = "Translate me.\n\n```python\nprint('hello world')\n```\n\nDone."
    masked, store = mask_non_translatable(source)
    assert "print('hello world')" not in masked
    assert any(kind == "code-fence" for kind, _ in store)
    assert unmask(masked, store) == source


def test_mask_protects_inline_code() -> None:
    source = "Run `pytest --timeout=60` to test."
    masked, store = mask_non_translatable(source)
    assert "pytest --timeout=60" not in masked
    # Should mask the inline code.
    assert any(kind == "code-inline" for kind, _ in store)


def test_mask_protects_frontmatter() -> None:
    source = "---\ntitle: Foo\nkey: value\n---\n\nProse here."
    masked, store = mask_non_translatable(source)
    assert "title: Foo" not in masked
    assert any(kind == "frontmatter" for kind, _ in store)
    assert unmask(masked, store) == source


def test_mask_protects_markdown_link_url_translates_text() -> None:
    source = "See [the docs](https://example.com/foo.html) for details."
    masked, store = mask_non_translatable(source)
    # Link text remains visible to the translator.
    assert "the docs" in masked
    # URL is masked.
    assert "https://example.com/foo.html" not in masked
    # Round-trip restores the URL.
    assert unmask(masked, store) == source


def test_mask_protects_image_target() -> None:
    source = "![alt text](images/foo.png)"
    masked, store = mask_non_translatable(source)
    assert "alt text" in masked  # alt is translatable
    assert "images/foo.png" not in masked
    assert unmask(masked, store) == source


def test_mask_protects_markdown_link_with_title() -> None:
    source = 'See [docs](https://example.com "Tooltip text") please.'
    masked, store = mask_non_translatable(source)
    # URL + title both inside the URL slot — both masked together.
    assert "https://example.com" not in masked
    assert "Tooltip text" not in masked
    assert unmask(masked, store) == source


def test_mask_protects_tech_ids() -> None:
    source = "Per ADR-042 §22.5 and PR #1136, fix TC-1D.9 (see SPEC-007)."
    masked, store = mask_non_translatable(source)
    kinds = [k for k, _ in store]
    assert "tech-id" in kinds
    assert "ADR-042" not in masked
    assert "TC-1D.9" not in masked
    assert "#1136" not in masked
    assert "§22.5" not in masked


def test_mask_protects_dotted_paths() -> None:
    source = "Import scieasy.qa.translation.client to use the facade."
    masked, store = mask_non_translatable(source)
    assert "scieasy.qa.translation.client" not in masked
    assert any(kind == "dotted-path" for kind, _ in store)


def test_mask_protects_file_paths() -> None:
    source = "Edit src/scieasy/qa/translation/client.py and re-run tests."
    masked, store = mask_non_translatable(source)
    assert "src/scieasy/qa/translation/client.py" not in masked
    assert any(kind == "file-path" for kind, _ in store)


def test_mask_protects_html_tags() -> None:
    source = "Use <strong>this</strong> for emphasis."
    masked, _store = mask_non_translatable(source)
    assert "<strong>" not in masked
    assert "</strong>" not in masked
    assert "this" in masked  # body still translatable


def test_unmask_tolerates_provider_attribute_reordering() -> None:
    """Some providers re-order or strip placeholder attributes; unmask
    must still identify them by ``id``."""
    store = [("code-fence", "```py\nx=1\n```")]
    # Simulate provider that strips ``data-kind`` and re-orders.
    translated = 'Beep <x ID="0"/> boop.'
    out = unmask(translated, store)
    assert "```py\nx=1\n```" in out


def test_unmask_handles_unknown_placeholder_id_gracefully() -> None:
    """If the provider hallucinates a placeholder id we never created,
    leave it in place rather than crashing."""
    store: list[tuple[str, str]] = [("code-fence", "```\nx\n```")]
    translated = 'before <x id="0"/> middle <x id="999"/> after'
    out = unmask(translated, store)
    assert "```\nx\n```" in out
    assert '<x id="999"/>' in out  # left in place


def test_complete_roundtrip_complex_doc() -> None:
    """A realistic ADR-style snippet round-trips through mask/unmask
    without losing any byte of non-prose."""
    source = (
        "---\n"
        "title: ADR-042\n"
        "status: Accepted\n"
        "---\n"
        "\n"
        "# Header text\n"
        "\n"
        "Per ADR-042 §22.5, install via `pip install pydantic-settings`.\n"
        "\n"
        "```python\n"
        "from scieasy.qa.translation import TranslatorClient\n"
        "client = TranslatorClient.from_provider_name('manual')\n"
        "```\n"
        "\n"
        "See [the spec](https://example.com/spec) and edit "
        "src/scieasy/qa/translation/client.py to extend.\n"
    )
    masked, store = mask_non_translatable(source)
    restored = unmask(masked, store)
    assert restored == source


# ---------------------------------------------------------------------------
# diagnose_text / file_sha
# ---------------------------------------------------------------------------


def test_diagnose_text_counts_kinds() -> None:
    text = "Per ADR-042 §22.5 install `pip` from src/scieasy/x.py."
    diag = diagnose_text(text)
    assert diag["total_chars_source"] == len(text)
    assert diag["tokens_masked"] >= 3
    assert "tokens_by_kind" in diag
    assert sum(diag["tokens_by_kind"].values()) == diag["tokens_masked"]


def test_file_sha_stable(tmp_path: Path) -> None:
    p = tmp_path / "doc.md"
    p.write_text("hello", encoding="utf-8")
    a = file_sha(p)
    b = file_sha(p)
    assert a == b
    assert len(a) == 16


def test_file_sha_changes_with_content(tmp_path: Path) -> None:
    p = tmp_path / "doc.md"
    p.write_text("hello", encoding="utf-8")
    a = file_sha(p)
    p.write_text("world", encoding="utf-8")
    b = file_sha(p)
    assert a != b


# ---------------------------------------------------------------------------
# Frontmatter sha / annotation helpers
# ---------------------------------------------------------------------------


def test_ensure_source_sha_inserts_when_missing() -> None:
    text = "---\ntitle: Foo\n---\nBody."
    out = _ensure_source_sha(text, "abc123")
    assert "source_sha: 'abc123'" in out
    assert "title: Foo" in out


def test_ensure_source_sha_replaces_existing() -> None:
    text = "---\ntitle: Foo\nsource_sha: 'old'\n---\nBody."
    out = _ensure_source_sha(text, "new123")
    assert "source_sha: 'new123'" in out
    assert "source_sha: 'old'" not in out


def test_ensure_source_sha_prepends_when_no_frontmatter() -> None:
    text = "Body without frontmatter."
    out = _ensure_source_sha(text, "deadbeef")
    assert out.startswith("---\nsource_sha: 'deadbeef'\n---\n")


def test_extract_source_sha_present() -> None:
    text = "---\nsource_sha: 'abcdef0123'\n---\nbody"
    assert extract_source_sha(text) == "abcdef0123"


def test_extract_source_sha_absent() -> None:
    assert extract_source_sha("no frontmatter here") is None


def test_annotate_manual_stub_with_frontmatter() -> None:
    text = "---\ntitle: Foo\n---\nBody."
    out = _annotate_manual_stub(text, "needs-manual")
    assert "translation_status: needs-manual" in out


def test_annotate_manual_stub_no_frontmatter() -> None:
    text = "Just body."
    out = _annotate_manual_stub(text, "needs-manual")
    assert out.startswith("<!-- translation_status: needs-manual -->")


def test_annotate_manual_stub_idempotent() -> None:
    """Re-annotating an already-annotated stub does not double the marker."""
    text = "---\ntitle: Foo\ntranslation_status: needs-manual\n---\nBody."
    out = _annotate_manual_stub(text, "needs-manual")
    assert out.count("translation_status: needs-manual") == 1


def test_annotate_manual_stub_replaces_other_status() -> None:
    text = "---\ntitle: Foo\ntranslation_status: complete\n---\nBody."
    out = _annotate_manual_stub(text, "needs-manual")
    assert "translation_status: needs-manual" in out
    assert "translation_status: complete" not in out


# ---------------------------------------------------------------------------
# translation_is_up_to_date / walk_pairs / write_translation
# ---------------------------------------------------------------------------


def test_translation_up_to_date_missing(tmp_path: Path) -> None:
    src = tmp_path / "src.md"
    src.write_text("hello", encoding="utf-8")
    tgt = tmp_path / "tgt.md"
    assert translation_is_up_to_date(src, tgt) is False


def test_translation_up_to_date_no_source_sha(tmp_path: Path) -> None:
    src = tmp_path / "src.md"
    src.write_text("hello", encoding="utf-8")
    tgt = tmp_path / "tgt.md"
    tgt.write_text("body without frontmatter", encoding="utf-8")
    assert translation_is_up_to_date(src, tgt) is False


def test_translation_up_to_date_match(tmp_path: Path) -> None:
    src = tmp_path / "src.md"
    src.write_text("hello world", encoding="utf-8")
    tgt = tmp_path / "tgt.md"
    sha = file_sha(src)
    tgt.write_text(f"---\nsource_sha: '{sha}'\n---\n你好世界\n", encoding="utf-8")
    assert translation_is_up_to_date(src, tgt) is True


def test_translation_up_to_date_mismatch(tmp_path: Path) -> None:
    src = tmp_path / "src.md"
    src.write_text("hello", encoding="utf-8")
    tgt = tmp_path / "tgt.md"
    tgt.write_text("---\nsource_sha: 'stale'\n---\n你好\n", encoding="utf-8")
    assert translation_is_up_to_date(src, tgt) is False


def test_write_translation_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "out.md"
    write_translation(target, "translated body", source_sha="abc")
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "source_sha: 'abc'" in text
    assert "translated body" in text


def test_walk_pairs_single_file_source(tmp_path: Path) -> None:
    src = tmp_path / "doc.md"
    src.write_text("hi", encoding="utf-8")
    target_root = tmp_path / "out"
    pairs = list(walk_pairs(src, target_root))
    assert len(pairs) == 1
    assert pairs[0][0] == src
    # When source is a single file the target is target_root/<name>.
    assert pairs[0][1] == target_root / "doc.md"


def test_walk_pairs_directory_recurses_and_skips_target(tmp_path: Path) -> None:
    src_root = tmp_path / "docs"
    target_root = src_root / "zh-CN"
    (src_root / "a").mkdir(parents=True)
    target_root.mkdir(parents=True)
    (src_root / "top.md").write_text("a", encoding="utf-8")
    (src_root / "a" / "deep.md").write_text("b", encoding="utf-8")
    # File under the target tree must be skipped.
    (target_root / "stale.md").write_text("c", encoding="utf-8")
    pairs = list(walk_pairs(src_root, target_root))
    src_paths = sorted(p[0].name for p in pairs)
    assert src_paths == ["deep.md", "top.md"]


def test_walk_pairs_ignores_non_md_files(tmp_path: Path) -> None:
    src_root = tmp_path / "docs"
    src_root.mkdir()
    (src_root / "doc.md").write_text("md", encoding="utf-8")
    (src_root / "data.json").write_text("{}", encoding="utf-8")
    pairs = list(walk_pairs(src_root, tmp_path / "out"))
    names = [p[0].name for p in pairs]
    assert "doc.md" in names
    assert "data.json" not in names


# ---------------------------------------------------------------------------
# TranslatorClient facade
# ---------------------------------------------------------------------------


def test_translator_client_from_provider_name_manual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCIEASY_TRANSLATION_PROVIDER", raising=False)
    client = TranslatorClient.from_provider_name("manual")
    assert client.provider.name == "manual"


def test_translator_client_from_provider_name_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        TranslatorClient.from_provider_name("babelfish")  # type: ignore[arg-type]


def test_translator_client_from_settings_dispatches_all_providers() -> None:
    for name in ("deepl", "google", "azure", "manual"):
        s = TranslationSettings(provider=name)  # type: ignore[arg-type]
        client = TranslatorClient.from_settings(s)
        assert client.provider.name == name


def test_translate_text_manual_provider_preserves_code() -> None:
    s = TranslationSettings(provider="manual")
    client = TranslatorClient.from_settings(s)
    src = "Hello, ```code()``` world."
    out = client.translate_text(src)
    # Manual provider is identity; code body untouched.
    assert "code()" in out
    assert "Hello, " in out


def test_translate_file_manual_marks_stub(tmp_path: Path) -> None:
    src = tmp_path / "src.md"
    src.write_text("# Title\n\nBody.\n", encoding="utf-8")
    s = TranslationSettings(provider="manual")
    client = TranslatorClient.from_settings(s)
    out = client.translate_file(src)
    assert "translation_status: needs-manual" in out


def test_translator_client_provider_property() -> None:
    provider = ManualProvider()
    client = TranslatorClient(provider)
    assert client.provider is provider


# ---------------------------------------------------------------------------
# Language-code normalisers
# ---------------------------------------------------------------------------


def test_normalise_deepl_lang_zh_variants() -> None:
    assert _normalise_deepl_lang("zh-CN") == "ZH"
    assert _normalise_deepl_lang("zh-Hans") == "ZH"
    assert _normalise_deepl_lang("zh") == "ZH"


def test_normalise_deepl_lang_other() -> None:
    assert _normalise_deepl_lang("de") == "DE"
    assert _normalise_deepl_lang("fr") == "FR"


def test_normalise_google_lang_passthrough() -> None:
    assert _normalise_google_lang("zh-CN") == "zh-CN"
    assert _normalise_google_lang("zh-TW") == "zh-TW"


def test_normalise_azure_lang_zh_variants() -> None:
    assert _normalise_azure_lang("zh-CN") == "zh-Hans"
    assert _normalise_azure_lang("zh-Hans") == "zh-Hans"
    assert _normalise_azure_lang("zh") == "zh-Hans"
    assert _normalise_azure_lang("zh-TW") == "zh-Hant"
    assert _normalise_azure_lang("zh-Hant") == "zh-Hant"
    assert _normalise_azure_lang("de") == "de"
