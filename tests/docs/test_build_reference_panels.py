"""The generated API reference: the panels root and deprecation rendering (#2426, #2493).

``scripts/docs/build_reference.py`` reads deprecation through
``scistudio.stability.get_deprecation`` on the symbol and on its canonical root,
and renders it on the root page, on each symbol, and in the index. The two
previewer roots that carried it were removed with the legacy previewer forms
(#2493), so the rendering is checked against a probe root. These tests render in
memory; they never write the committed pages.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scistudio.stability import deprecated, provisional

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "docs" / "build_reference.py"
_PROBE_ROOT = "_scistudio_deprecated_reference_probe"


@pytest.fixture(scope="module")
def build_reference() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_build_reference_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def deprecated_root(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A root whose whole public surface is deprecated, as the previewer roots were."""
    probe = ModuleType(_PROBE_ROOT)
    probe.__doc__ = "A deprecated probe root."
    marker = deprecated(since="0.3.5", removed_in="0.3.6", replacement="`scistudio.panels`.")

    @marker
    @provisional(since="0.3.1")
    class Probe:
        """A deprecated probe symbol."""

    Probe.__module__ = _PROBE_ROOT
    probe.Probe = Probe  # type: ignore[attr-defined]
    probe.__all__ = ["Probe"]  # type: ignore[attr-defined]
    marker(probe)
    monkeypatch.setitem(sys.modules, _PROBE_ROOT, probe)
    return probe


def test_panels_is_a_canonical_root_and_the_previewer_roots_are_gone(build_reference: ModuleType) -> None:
    assert "scistudio.panels" in build_reference.CANONICAL_ROOTS
    assert not any(root.startswith("scistudio.previewers") for root in build_reference.CANONICAL_ROOTS)
    assert "scistudio.panels.models" not in build_reference.CANONICAL_ROOTS
    assert "scistudio.panels.data_access" not in build_reference.CANONICAL_ROOTS


def test_a_deprecated_root_renders_its_deprecation(build_reference: ModuleType, deprecated_root: ModuleType) -> None:
    selfcontained, count = build_reference._sc_render_root_page(_PROBE_ROOT)
    mkdocs_page, _, _ = build_reference._render_root_page(_PROBE_ROOT)

    assert count == 1
    for page in (selfcontained, mkdocs_page):
        assert "Every symbol on this page is deprecated since `0.3.5` and is removed in `0.3.6`" in page
        assert "`scistudio.panels`" in page
        assert "## `Probe` — " in page
        assert page.count(" · deprecated\n") == 1
        assert page.count("**Deprecated** since `0.3.5`; still supported until it is removed in `0.3.6`.") == 1


def test_panels_page_is_provisional_and_not_deprecated(build_reference: ModuleType) -> None:
    page, count = build_reference._sc_render_root_page("scistudio.panels")
    assert count == 8
    assert "## `OwnerKind` — " in page
    assert "deprecated" not in page.lower().replace("`deprecationwarning`", "")
    assert page.count("**Stability:** `provisional` · Since `0.3.5`") == 7
    # Runtime members marked internal stay out of the reference.
    for member in ("candidates(", "register(", "load("):
        assert member not in page


def test_index_marks_no_root_deprecated(build_reference: ModuleType) -> None:
    stats = [(root, 1) for root in build_reference.CANONICAL_ROOTS]
    index = build_reference._sc_render_index(stats)
    assert not [line for line in index.splitlines() if line.endswith("— **deprecated**")]
    assert "[`scistudio.panels`](scistudio.panels.md)" in index


def test_committed_reference_is_current(build_reference: ModuleType) -> None:
    """The committed self-contained panels page equals a fresh render (generated docs stay generated)."""
    page, _ = build_reference._sc_render_root_page("scistudio.panels")
    committed = (build_reference.PACKAGE_REFERENCE_DIR / "scistudio.panels.md").read_text(encoding="utf-8")
    assert committed == page.rstrip() + "\n", "scistudio.panels.md is stale; rerun scripts/docs/build_reference.py"
    for removed in ("scistudio.previewers.models.md", "scistudio.previewers.data_access.md"):
        assert not (build_reference.PACKAGE_REFERENCE_DIR / removed).exists(), removed
