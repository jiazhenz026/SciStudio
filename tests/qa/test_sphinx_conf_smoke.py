"""Smoke test for docs/sphinx/conf.py.

We don't run a full ``sphinx-build`` here (the docs CI job lands in
1D sub-PR 3+); instead we exercise the Python contract: the module
imports, declares the expected extensions per ADR-042 §23.2 + ADR-044
§10.4, and exposes the canonical settings (nitpicky, autoapi_dirs,
intersphinx_mapping, html_theme).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONF_PATH = REPO_ROOT / "docs" / "sphinx" / "conf.py"


@pytest.fixture
def conf_module():
    """Import docs/sphinx/conf.py as an isolated module.

    We use ``SCIEASY_DOCS_FAST=1`` so autoapi_dirs is cleared, removing
    the need for the real ``src/scieasy`` source tree to be importable
    by Sphinx (avoids autoapi running its own analysis at import time).
    """
    assert CONF_PATH.is_file(), f"conf.py missing at {CONF_PATH}"

    # The conf.py inserts docs/sphinx/_ext onto sys.path; capture and
    # restore so we don't bleed across tests.
    saved_path = list(sys.path)
    saved_env = os.environ.get("SCIEASY_DOCS_FAST")
    os.environ["SCIEASY_DOCS_FAST"] = "1"

    try:
        spec = importlib.util.spec_from_file_location("scieasy_sphinx_conf", CONF_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path[:] = saved_path
        if saved_env is None:
            os.environ.pop("SCIEASY_DOCS_FAST", None)
        else:
            os.environ["SCIEASY_DOCS_FAST"] = saved_env


def test_conf_module_imports(conf_module):
    assert conf_module is not None
    assert conf_module.project == "SciEasy"


def test_conf_declares_nitpicky(conf_module):
    # ADR-042 §23.4 — phantom-symbol references must fail the build.
    assert conf_module.nitpicky is True


def test_conf_declares_pydata_theme(conf_module):
    # ADR-044 §10.4 — replaces furo from ADR-042 §23.1.
    assert conf_module.html_theme == "pydata_sphinx_theme"


def test_conf_extensions_include_adr_042_originals(conf_module):
    required = {
        "autoapi.extension",
        "myst_parser",
        "sphinx_needs",
        "sphinx_substitution_extensions",
        "sphinx.ext.intersphinx",
    }
    missing = required - set(conf_module.extensions)
    assert not missing, f"missing ADR-042 §23.2 extensions: {missing}"


def test_conf_extensions_include_all_nine_adr_044_additions(conf_module):
    # ADR-044 §10.1 — the nine new tools.
    required = {
        "numpydoc",
        "sphinxcontrib.autodoc_pydantic",  # autodoc-pydantic
        "sphinx_click",
        "sphinxcontrib.openapi",
        "sphinx_gallery.gen_gallery",
        "sphinx_design",
        "sphinx_copybutton",
        "sphinx_issues",
        # pydata-sphinx-theme is a theme (not an extension); its presence
        # is validated by test_conf_declares_pydata_theme above.
    }
    missing = required - set(conf_module.extensions)
    assert not missing, f"missing ADR-044 §10.1 extensions: {missing}"


def test_conf_extensions_include_custom_directives(conf_module):
    # ADR-044 §10.2 + §10.4 — custom in-tree extensions.
    assert "scieasy_directives" in conf_module.extensions
    assert "llms_txt_builder" in conf_module.extensions


def test_conf_intersphinx_mapping_includes_core_targets(conf_module):
    # ADR-042 §23.2 + ADR-044 §10.1 reference list.
    required_keys = {"python", "pydantic", "fastapi", "zarr", "numpy", "pandas"}
    missing = required_keys - set(conf_module.intersphinx_mapping.keys())
    assert not missing, f"missing intersphinx targets: {missing}"


def test_conf_autoapi_dirs_cleared_under_fast_mode(conf_module):
    # With SCIEASY_DOCS_FAST=1, autoapi_dirs is empty to keep the smoke
    # test fast and free of dependency on the source tree layout.
    assert conf_module.autoapi_dirs == []


def test_conf_linkcode_resolve_returns_github_url(conf_module):
    url = conf_module.linkcode_resolve("py", {"module": "scieasy.qa.audit.foo"})
    assert url is not None
    assert "github.com/zjzcpj/SciEasy" in url
    assert "scieasy/qa/audit/foo.py" in url


def test_conf_linkcode_resolve_returns_none_for_non_py_domain(conf_module):
    assert conf_module.linkcode_resolve("js", {"module": "anything"}) is None


def test_conf_linkcode_resolve_returns_none_when_no_module(conf_module):
    assert conf_module.linkcode_resolve("py", {}) is None


def test_custom_ext_modules_importable():
    """The two custom extension modules must export setup()."""
    # We have to import them via the _ext directory path injection that
    # conf.py does.
    ext_dir = REPO_ROOT / "docs" / "sphinx" / "_ext"
    saved = list(sys.path)
    sys.path.insert(0, str(ext_dir))
    try:
        # Force fresh imports.
        sys.modules.pop("scieasy_directives", None)
        sys.modules.pop("llms_txt_builder", None)
        import llms_txt_builder  # type: ignore[import-not-found]
        import scieasy_directives  # type: ignore[import-not-found]

        meta_a = scieasy_directives.setup(app=None)
        meta_b = llms_txt_builder.setup(app=None)
        for meta in (meta_a, meta_b):
            assert "version" in meta
            assert meta["parallel_read_safe"] is True
    finally:
        sys.path[:] = saved
