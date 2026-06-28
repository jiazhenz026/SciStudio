"""Tests for ``resolve_display_name`` — the single canonical name resolver (#1812).

The resolver is the one precedence authority shared by the interactive-panel
label path (``interactive_item_label`` on a live ``DataObject``) and the
previewer/API path (the serialized wire ``metadata`` dict stamped onto each
item descriptor). These tests pin the precedence order and the dual input-shape
contract (live object vs wire mapping).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.core.meta._display_name import resolve_display_name


class _Meta:
    """Attribute-style stand-in for a Pydantic ``meta`` slot."""

    def __init__(self, *, source_file=None, file_path=None):
        self.source_file = source_file
        self.file_path = file_path


class _Framework:
    def __init__(self, *, source=""):
        self.source = source


class _Obj:
    """Minimal duck-typed live ``DataObject`` stand-in."""

    def __init__(self, *, name=None, user=None, meta=None, framework=None, file_path=None):
        self.name = name
        self.user = user if user is not None else {}
        self.meta = meta
        self.framework = framework
        self.file_path = file_path


# -- Precedence (wire-dict input) ------------------------------------------


def test_user_display_name_wins_over_everything():
    md = {
        "user": {"display_name": "exp.xlsx — beta"},
        "meta": {"source_file": "/data/exp.xlsx"},
        "framework": {"source": "/data/exp.xlsx"},
    }
    assert resolve_display_name(md, fallback="item_0") == "exp.xlsx — beta"


def test_name_used_when_no_display_name():
    assert resolve_display_name({"name": "My Object"}, fallback="x") == "My Object"


def test_meta_source_file_basename():
    assert resolve_display_name({"meta": {"source_file": "/data/beads.tif"}}, fallback="x") == "beads.tif"


def test_meta_source_file_windows_separator():
    assert resolve_display_name({"meta": {"source_file": "C:\\runs\\a.csv"}}, fallback="x") == "a.csv"


def test_root_level_source_file_wire_variant():
    assert resolve_display_name({"source_file": "/a/root.csv"}, fallback="x") == "root.csv"


def test_file_path_basename():
    assert resolve_display_name({"file_path": "/x/y/photo.png"}, fallback="x") == "photo.png"


def test_framework_source_basename_when_path():
    assert resolve_display_name({"framework": {"source": "/p/img.ome.tiff"}}, fallback="x") == "img.ome.tiff"


def test_framework_source_ignored_when_package_name():
    # Package-name provenance is not a filename — fall through to the fallback.
    md = {"framework": {"source": "scistudio-blocks-spectroscopy"}}
    assert resolve_display_name(md, fallback="item_7") == "item_7"


def test_source_file_beats_framework_source():
    md = {"meta": {"source_file": "/data/real.tif"}, "framework": {"source": "/prov/other.tif"}}
    assert resolve_display_name(md, fallback="x") == "real.tif"


def test_empty_metadata_returns_fallback():
    assert resolve_display_name({}, fallback="item_3") == "item_3"


def test_none_source_returns_fallback():
    assert resolve_display_name(None, fallback="item_9") == "item_9"


# -- Dual input shape: the same precedence over a live object --------------


def test_live_object_display_name():
    obj = _Obj(user={"display_name": "A — s1"})
    assert resolve_display_name(obj, fallback="item_0") == "A — s1"


def test_live_object_meta_source_file():
    obj = _Obj(meta=_Meta(source_file="/data/spectrum.dx"))
    assert resolve_display_name(obj, fallback="item_0") == "spectrum.dx"


def test_live_object_artifact_path_uses_name():
    # An Artifact-style ``file_path`` is a ``Path``; its ``.name`` is the basename.
    obj = _Obj(framework=_Framework(source=""), file_path=Path("/x/y/photo.png"))
    assert resolve_display_name(obj, fallback="z") == "photo.png"


def test_live_object_framework_source():
    obj = _Obj(framework=_Framework(source="/data/run.mzML"))
    assert resolve_display_name(obj, fallback="item_0") == "run.mzML"


def test_live_object_empty_returns_fallback():
    obj = _Obj()
    assert resolve_display_name(obj, fallback="item_5") == "item_5"


@pytest.mark.parametrize("blank", ["", None])
def test_blank_display_name_falls_through(blank):
    md = {"user": {"display_name": blank}, "meta": {"source_file": "/d/f.tif"}}
    assert resolve_display_name(md, fallback="x") == "f.tif"
