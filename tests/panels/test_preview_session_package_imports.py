"""Package panels render with the plugin import roots active (#2112, FR-044).

A package panel module is importable at render time only because discovery
cached it in ``sys.modules`` under a scoped ``prepended_sys_paths`` that was
then reverted. A *lazy* third-party import inside the provider therefore runs a
fresh import with the plugin ``site-packages`` off ``sys.path`` — which is how
opening a TIFF through the imaging package's viewer produced
``No module named 'tifffile'``.

These use a minimal in-memory registry and a temporary import root; they never
require a package install.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scistudio.panels.models import (
    EnvelopeKind,
    OwnerKind,
    PanelSpec,
    PreviewEnvelope,
    PreviewMetadata,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)
from scistudio.panels.registry import PanelRegistry
from scistudio.panels.session import PreviewSessionManager


def _target() -> PreviewTarget:
    return PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="r",
        recorded_type="Widget",
        type_chain=("DataObject", "Widget"),
    )


def _manager_for(spec: PanelSpec) -> PreviewSessionManager:
    registry = PanelRegistry()
    registry.register(spec)
    return PreviewSessionManager(registry)


def _spec(owner_kind: OwnerKind, provider) -> PanelSpec:
    return PanelSpec(
        previewer_id="pkg.widget",
        owner_kind=owner_kind,
        owner_name="pkg",
        target_type="Widget",
        priority=100,
        backend_provider=provider,
    )


@pytest.fixture
def plugin_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand in for an installed plugin's import root."""
    root = tmp_path / "plugin-site-packages"
    root.mkdir()
    monkeypatch.setattr(
        "scistudio.desktop.paths.installed_package_import_roots",
        lambda: [root],
    )
    return root


def test_package_provider_sees_the_plugin_roots(plugin_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The deferred-import window is open for the duration of the render."""
    seen: list[bool] = []

    def provider(request: PreviewRequest) -> PreviewEnvelope:
        seen.append(str(plugin_root) in sys.path)
        return PreviewEnvelope(
            previewer_id=request.spec.previewer_id,
            target=request.target,
            kind=EnvelopeKind.ARRAY,
            metadata=PreviewMetadata(),
        )

    manager = _manager_for(_spec(OwnerKind.PACKAGE, provider))
    envelope = manager.render_target(_target())

    assert seen == [True]
    assert envelope.kind is EnvelopeKind.ARRAY
    # The window closes again: this is an activation for one call, not a
    # permanent addition to the process's import path.
    assert str(plugin_root) not in sys.path


def test_a_lazy_import_inside_a_package_provider_resolves(plugin_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression itself: an import written inside the render function."""
    (plugin_root / "pretend_tifffile.py").write_text("VALUE = 42\n", encoding="utf-8")
    monkeypatch.delitem(sys.modules, "pretend_tifffile", raising=False)

    def provider(request: PreviewRequest) -> PreviewEnvelope:
        import pretend_tifffile

        return PreviewEnvelope(
            previewer_id=request.spec.previewer_id,
            target=request.target,
            kind=EnvelopeKind.ARRAY,
            payload={"value": pretend_tifffile.VALUE},
            metadata=PreviewMetadata(),
        )

    envelope = _manager_for(_spec(OwnerKind.PACKAGE, provider)).render_target(_target())
    assert envelope.error is None
    assert envelope.payload["value"] == 42


def test_core_providers_are_left_alone(plugin_root: Path) -> None:
    """Core providers import from the base installation, so nothing is activated."""
    seen: list[bool] = []

    def provider(request: PreviewRequest) -> PreviewEnvelope:
        seen.append(str(plugin_root) in sys.path)
        return PreviewEnvelope(
            previewer_id=request.spec.previewer_id,
            target=request.target,
            kind=EnvelopeKind.ARRAY,
            metadata=PreviewMetadata(),
        )

    _manager_for(_spec(OwnerKind.CORE, provider)).render_target(_target())
    assert seen == [False]
