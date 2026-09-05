"""Shared fixtures for the ADR-054 panel-contract tests.

The on-disk form is a directory holding ``panel.json`` and an entry document
(FR-002, D-007), so nearly every test in this suite needs to write one. Writing
it through one helper keeps the tests arguing about behaviour rather than about
JSON, and means a change to the form is a change in one place.

The core tier is tested against a fixture root these helpers build, never
against the shipped ``src/scistudio/panels/builtin/`` directory: a test that
asserted against the real built-in panels would fail every time one of them was
edited, which is the opposite of what the four-tier discovery tests are for.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


def write_panel(
    root: Path,
    panel_id: str,
    *,
    capability: str = "displaying",
    target_types: list[str] | None = None,
    display_name: str | None = None,
    entry: str = "index.html",
    api_version: str = "1",
    directory_name: str | None = None,
    write_entry: bool = True,
    **extra: Any,
) -> Path:
    """Write one panel directory under *root* and return it.

    Everything D-007 makes required is supplied by default so a test naming only
    what it cares about still produces a valid declaration; a test about
    *invalid* declarations passes ``None`` for the field it is removing through
    ``extra`` or writes the JSON itself.
    """
    directory = root / (directory_name or panel_id)
    directory.mkdir(parents=True, exist_ok=True)
    declaration: dict[str, Any] = {
        "panel_id": panel_id,
        "display_name": display_name if display_name is not None else panel_id,
        "target_types": target_types if target_types is not None else ["DataFrame"],
        "capability": capability,
        "entry": entry,
        "api_version": api_version,
    }
    declaration.update(extra)
    for key in [key for key, value in declaration.items() if value is None]:
        del declaration[key]
    (directory / "panel.json").write_text(json.dumps(declaration, indent=2) + "\n", encoding="utf-8")
    if write_entry:
        (directory / entry).write_text("<!doctype html><title>panel</title>\n", encoding="utf-8")
    return directory


@pytest.fixture
def panel_writer() -> Callable[..., Path]:
    """Return :func:`write_panel` as a fixture, for tests that prefer injection."""
    return write_panel


@pytest.fixture
def tier_roots(tmp_path: Path) -> dict[str, Path]:
    """Return one empty root per tier, already created.

    Keyed by the :class:`~scistudio.core.panels.PanelTier` value so a test reads
    ``tier_roots["project"]`` rather than remembering a tuple order.
    """
    roots = {name: tmp_path / name for name in ("core", "package", "user", "project")}
    for root in roots.values():
        root.mkdir()
    return roots
