"""T-001 (MiniApp FR-001/FR-002): the miniapp context, the one-type rule, and
``panel.py`` detection. Discovery records whether ``panel.py`` is present but
never imports it, and its presence alone never adds an operation to any context.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.panels.descriptor import parse_descriptor
from scistudio.previewers.models import OwnerKind

_TYPES = {"Image", "Text", "DataFrame"}


def _panel(directory: Path, descriptor: dict, *, python: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "panel.json").write_text(json.dumps(descriptor), encoding="utf-8")
    (directory / "index.html").write_text("<p>panel</p>", encoding="utf-8")
    if python is not None:
        (directory / "panel.py").write_text(python, encoding="utf-8")
    return directory


def _parse(directory: Path, owner_kind: OwnerKind = OwnerKind.PROJECT):
    return parse_descriptor(directory, owner_kind=owner_kind, owner_name="project", registered_types=_TYPES)


def test_miniapp_context_is_accepted_with_exactly_one_type(tmp_path: Path) -> None:
    directory = _panel(
        tmp_path / "lab.viewer", {"id": "lab.viewer", "api_version": "1.0", "contexts": ["miniapp"], "types": ["Image"]}
    )
    descriptor, notes = _parse(directory)
    assert descriptor.contexts == ("miniapp",)
    assert descriptor.types == ("Image",)
    assert notes == []


def test_miniapp_requires_exactly_one_type(tmp_path: Path) -> None:
    zero = _panel(tmp_path / "a.zero", {"id": "a.zero", "api_version": "1.0", "contexts": ["miniapp"], "types": []})
    with pytest.raises(ValueError, match="exactly one type"):
        _parse(zero)
    two = _panel(
        tmp_path / "a.two",
        {"id": "a.two", "api_version": "1.0", "contexts": ["miniapp"], "types": ["Image", "Text"]},
    )
    with pytest.raises(ValueError, match="exactly one type"):
        _parse(two)


def test_miniapp_accepts_single_collection_type(tmp_path: Path) -> None:
    directory = _panel(
        tmp_path / "c.grid",
        {"id": "c.grid", "api_version": "1.0", "contexts": ["miniapp"], "types": ["Collection[Image]"]},
    )
    descriptor, notes = _parse(directory)
    assert descriptor.types == ("Collection[Image]",)
    assert notes == []


def test_panel_py_detected_and_never_imported(tmp_path: Path) -> None:
    directory = _panel(
        tmp_path / "m.app",
        {"id": "m.app", "api_version": "1.0", "contexts": ["miniapp"], "types": ["Image"]},
        python="raise RuntimeError('discovery must never import panel.py')",
    )
    descriptor, notes = _parse(directory)
    assert descriptor.has_python is True
    assert descriptor.to_dict()["has_python"] is True
    assert notes == []


def test_no_panel_py_reports_has_python_false(tmp_path: Path) -> None:
    directory = _panel(
        tmp_path / "m.plain",
        {"id": "m.plain", "api_version": "1.0", "contexts": ["miniapp"], "types": ["Image"]},
    )
    descriptor, notes = _parse(directory)
    assert descriptor.has_python is False
    assert notes == []


def test_panel_py_without_call_context_emits_note_and_enables_nothing(tmp_path: Path) -> None:
    # FR-002: panel.py in a panel that declares no context providing ``call``
    # (only preview/interactive do not provide it) records the file but adds an
    # informational diagnostic; Python is never started for such a panel.
    directory = _panel(
        tmp_path / "p.preview",
        {"id": "p.preview", "api_version": "1.0", "contexts": ["preview", "interactive"], "types": ["Text"]},
        python="def setup(data):\n    return None\n",
    )
    descriptor, notes = _parse(directory)
    assert descriptor.has_python is True
    assert "miniapp" not in descriptor.contexts
    assert any("panel.py present but no context provides call" in note for note in notes)


def test_preview_context_still_ignores_types_rule_for_miniapp(tmp_path: Path) -> None:
    # A panel may declare both preview and miniapp; the one-type rule binds the
    # miniapp declaration, and preview keeps requiring at least one type.
    directory = _panel(
        tmp_path / "d.both",
        {"id": "d.both", "api_version": "1.0", "contexts": ["preview", "miniapp"], "types": ["Image", "Text"]},
    )
    # miniapp requires exactly one type, so two types must still be refused.
    with pytest.raises(ValueError, match="exactly one type"):
        _parse(directory)
