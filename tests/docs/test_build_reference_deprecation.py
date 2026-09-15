"""The generated API reference shows deprecation and the panels root (#2426).

``scripts/docs/build_reference.py`` reads deprecation through
``scistudio.stability.get_deprecation`` on the symbol and on its canonical root,
and renders it on the root page, on each symbol, and in the index. These tests
render in memory; they never write the committed pages.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "docs" / "build_reference.py"


@pytest.fixture(scope="module")
def build_reference() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_build_reference_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_panels_is_a_canonical_root(build_reference: ModuleType) -> None:
    assert "scistudio.panels" in build_reference.CANONICAL_ROOTS
    assert "scistudio.previewers.models" in build_reference.CANONICAL_ROOTS
    assert "scistudio.previewers.data_access" in build_reference.CANONICAL_ROOTS


@pytest.mark.parametrize("root", ["scistudio.previewers.models", "scistudio.previewers.data_access"])
def test_every_previewer_symbol_renders_deprecated(build_reference: ModuleType, root: str) -> None:
    module = importlib.import_module(root)
    selfcontained, count = build_reference._sc_render_root_page(root)
    mkdocs_page, _, _ = build_reference._render_root_page(root)

    assert count == len(module.__all__)
    for page in (selfcontained, mkdocs_page):
        assert "Every symbol on this page is deprecated since `0.3.5` and is removed in `0.3.6`" in page
        assert "`scistudio.panels`" in page
        for name in module.__all__:
            assert f"## `{name}` — " in page
        # Non-markable constants and aliases are covered by the module-wide marker too.
        assert page.count(" · deprecated\n") == len(module.__all__)
        assert page.count("**Deprecated** since `0.3.5`; still supported until it is removed in `0.3.6`.") == len(
            module.__all__
        )


def test_panels_page_is_provisional_and_not_deprecated(build_reference: ModuleType) -> None:
    page, count = build_reference._sc_render_root_page("scistudio.panels")
    assert count == 7
    assert "deprecated" not in page.lower().replace("`deprecationwarning`", "")
    assert page.count("**Stability:** `provisional` · Since `0.3.5`") == 6
    # Runtime members marked internal stay out of the reference.
    for member in ("candidates(", "register(", "load("):
        assert member not in page


def test_index_marks_deprecated_roots_only(build_reference: ModuleType) -> None:
    stats = [(root, 1) for root in build_reference.CANONICAL_ROOTS]
    index = build_reference._sc_render_index(stats)
    deprecated_lines = [line for line in index.splitlines() if line.endswith("— **deprecated**")]
    assert len(deprecated_lines) == 2
    assert all("scistudio.previewers." in line for line in deprecated_lines)
    assert "[`scistudio.panels`](scistudio.panels.md)" in index


def test_committed_reference_is_current(build_reference: ModuleType) -> None:
    """The committed self-contained pages equal a fresh render (generated docs stay generated)."""
    for root in ("scistudio.previewers.models", "scistudio.previewers.data_access", "scistudio.panels"):
        page, _ = build_reference._sc_render_root_page(root)
        committed = (build_reference.PACKAGE_REFERENCE_DIR / f"{root}.md").read_text(encoding="utf-8")
        assert committed == page.rstrip() + "\n", f"{root}.md is stale; rerun scripts/docs/build_reference.py"
