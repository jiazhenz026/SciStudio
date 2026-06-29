"""Tests for the editor completion manifest emitted by
``scripts/docs/build_reference.py`` (#1875).

The in-app Monaco editor loads
``frontend/src/components/CodeEditor.parts/apiManifest.generated.json`` to offer
SciStudio-API completion + hover. It is a generated artifact built from the same
``__all__`` + ``scistudio.stability`` + docstring introspection as the human API
reference, so these tests cover (1) the manifest's shape and (2) that the
committed JSON has not drifted from the live public surface.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "docs" / "build_reference.py"


@pytest.fixture(scope="module")
def build_reference() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_reference", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_reference"] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_covers_the_nine_canonical_roots(build_reference: ModuleType) -> None:
    manifest = build_reference.build_completion_manifest()
    roots = {root["module"] for root in manifest["roots"]}
    assert roots == set(build_reference.CANONICAL_ROOTS)
    assert len(manifest["roots"]) == 9
    total = sum(len(root["symbols"]) for root in manifest["roots"])
    assert total >= 130  # 138 symbols at #1875; guard against accidental shrink.


def test_manifest_symbols_carry_signature_summary_and_stability(
    build_reference: ModuleType,
) -> None:
    manifest = build_reference.build_completion_manifest()
    by_name = {sym["name"]: sym for root in manifest["roots"] for sym in root["symbols"]}

    assert "Block" in by_name
    assert by_name["Block"]["module"] == "scistudio.blocks.base"

    array = by_name["Array"]
    assert array["kind"] == "class"
    assert "axes" in array["signature"]
    assert array["stability"] == "stable"
    assert array["summary"]  # non-empty one-line summary
    # Classes expose their public members for hover docs.
    member_names = {m["name"] for m in array.get("members", [])}
    assert "to_memory" in member_names


def test_committed_manifest_matches_regeneration(build_reference: ModuleType) -> None:
    """Drift guard: the committed JSON must equal a fresh regeneration.

    If this fails, regenerate with::

        PYTHONPATH=$PWD/src python scripts/docs/build_reference.py --generate-only
    """
    committed = build_reference.FRONTEND_COMPLETION_MANIFEST.read_text(encoding="utf-8")
    regenerated = build_reference._manifest_json(build_reference.build_completion_manifest())
    assert committed == regenerated, (
        "apiManifest.generated.json is stale; regenerate with "
        "`PYTHONPATH=$PWD/src python scripts/docs/build_reference.py --generate-only`"
    )
