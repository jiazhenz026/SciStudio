"""T-IMG-011 skeleton tests — impl pending (Sprint C continuation A)."""

from __future__ import annotations

import importlib

import pytest


def test_t_img_011_module_importable() -> None:
    """The T-IMG-011 module imports cleanly at skeleton time."""
    importlib.import_module("scistudio_blocks_imaging.preprocess.deconvolve")


def test_t_img_011_class_has_required_classvars() -> None:
    """Deconvolve declares the mandatory ProcessBlock/IOBlock ClassVars."""
    mod = importlib.import_module("scistudio_blocks_imaging.preprocess.deconvolve")
    cls = mod.Deconvolve
    assert hasattr(cls, "type_name")
    assert hasattr(cls, "name")
    assert hasattr(cls, "subcategory")
    assert hasattr(cls, "config_schema")


def test_deconvolve_class_exists_in_palette() -> None:
    """T-IMG-011 stub — impl pending."""
    pytest.skip("T-IMG-011 impl pending (skeleton continuation A)")


def test_deconvolve_run_raises_not_implemented() -> None:
    """T-IMG-011 stub — impl pending."""
    pytest.skip("T-IMG-011 impl pending (skeleton continuation A)")
