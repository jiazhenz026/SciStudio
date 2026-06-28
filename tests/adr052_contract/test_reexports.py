"""Re-exports land on the canonical root (ADR-052 §2: public = canonical root).

Spec: §3.1/§8.5 (StorageReference public via the core.types re-export), §4.7/§7
(BlockCancelledByAppError re-exported into blocks.app), §4.8 (interactive surface
+ PackageOtaSource re-exported from blocks.base).

Asserts each re-exported symbol is importable from its canonical root AND is a
member of that root's ``__all__`` (membership is what makes it public, §2).

EXPECTED TO FAIL in the pre-implementation tree: the interactive surface is only
reachable via the deep ``scistudio.blocks.base.interactive`` path today,
BlockCancelledByAppError is not yet re-exported into blocks.app, and
PackageOtaSource is not yet in blocks.base.__all__. Written correct-by-spec.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from _spec_data import REEXPORTS, import_root, module_all

_CASES = [(root, name) for root, names in REEXPORTS.items() for name in names]


@pytest.mark.parametrize(("root", "name"), _CASES)
def test_reexport_importable_from_root(root: str, name: str) -> None:
    module = import_root(root)
    assert module is not None, f"{root} failed to import"
    assert getattr(module, name, None) is not None, (
        f"{name} must be importable from the canonical root {root} (ADR-052 §2)"
    )


@pytest.mark.parametrize(("root", "name"), _CASES)
def test_reexport_in_root_all(root: str, name: str) -> None:
    module = import_root(root)
    assert module is not None, f"{root} failed to import"
    assert name in module_all(module), (
        f"{name} must be a member of {root}.__all__ -- __all__ membership is what makes it public (ADR-052 §2)"
    )


def test_interactive_surface_resolves_to_same_object() -> None:
    """The blocks.base re-export is the same object as the deep interactive path.

    A re-export is a curated alias of the home symbol, not a copy (ADR-052 §2).
    """
    base = import_root("scistudio.blocks.base")
    interactive = import_root("scistudio.blocks.base.interactive")
    assert base is not None and interactive is not None
    for name in ("InteractiveMixin", "InteractivePrompt", "PanelManifest"):
        root_obj = getattr(base, name, None)
        deep_obj = getattr(interactive, name, None)
        assert root_obj is not None, f"{name} not re-exported from blocks.base"
        assert deep_obj is not None, f"{name} missing from blocks.base.interactive"
        assert root_obj is deep_obj, f"{name}: blocks.base re-export must alias the home object"
