"""Sphinx configuration for SciEasy documentation.

This file is the canonical Sphinx config per ADR-042 §23.2 with ADR-044
§10.4 additions. It is consumed by ``sphinx-build``; it MUST be a valid
Python module importable in isolation (used by the smoke test in
``tests/qa/test_sphinx_conf_smoke.py``).

Implementation status (Phase 1D sub-PR 2):
- Declares the full extension list and minimal theme/build options so
  ``sphinx-build -W --keep-going docs/sphinx _build/html`` completes on
  the minimal scaffold (``index.rst``).
- Custom directive bodies and generator hookup are deferred to 1D sub-PR
  3+; ``_ext/scieasy_directives.py`` and ``_ext/llms_txt_builder.py``
  ship as no-op ``setup()`` shells with TODO markers.

TODO(#1169-followup): Wire up the actual generators (llms_txt,
entry_point_catalog, cli_reference, openapi_reference, schema_reference)
and directive bodies (scieasy_block_catalog / scieasy_runner_catalog /
scieasy_ai_block_catalog) per ADR-044 §10.2-10.3.
  Out of scope per ADR-044 §11.5 (Phase 1D deliverable, but split across
  multiple sub-PRs for review tractability).
  Followup: open after Phase 1D sub-PR 2 merges.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# -- Path setup --------------------------------------------------------
# Custom Sphinx extensions live in docs/sphinx/_ext/ and must be on
# sys.path before the extensions list is processed.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "_ext"))

# -- Project information -----------------------------------------------
project = "SciEasy"
author = "SciEasy contributors"
copyright = "2026, SciEasy contributors"
release = "0.2.1"  # NOTE: kept in sync with pyproject.toml manually; will be
# wired to {{ facts.version }} once the fact registry lands (ADR-042 §10).

# -- General configuration ---------------------------------------------
# Verified extension module names per ADR-044 §10.4 (audit P1.1 fix).
# Order: ADR-042 §23.2 originals → ADR-044 §10.4 additions → custom.
extensions = [
    # ADR-042 §23.2 originals (names corrected per ADR-044 §10.4):
    "autoapi.extension",  # sphinx-autoapi package
    "myst_parser",  # Markdown alongside RST
    "sphinx_needs",  # requirement traceability
    "sphinx_substitution_extensions",  # {{ facts.X }} substitution
    "sphinx.ext.intersphinx",  # cross-project xref
    # ADR-044 §10.4 additions (9 from §10.1 + standard sphinx.ext.* siblings):
    "numpydoc",  # docstring grammar
    "sphinx.ext.autodoc",  # underpins autodoc-pydantic
    "sphinx.ext.autosummary",  # per-symbol page generation
    "sphinx.ext.doctest",  # doctest blocks in prose
    "sphinx.ext.linkcode",  # source line links
    "sphinx.ext.viewcode",  # inline source view
    "sphinx.ext.graphviz",  # diagrams
    "sphinx_click",  # click/typer CLIs
    "sphinxcontrib.openapi",  # FastAPI OpenAPI
    "sphinxcontrib.autodoc_pydantic",  # autodoc-pydantic package
    "sphinx_gallery.gen_gallery",  # executable .py examples
    "sphinx_design",  # tabs/grids/cards
    "sphinx_copybutton",  # copy-to-clipboard
    "sphinx_issues",  # GitHub issue/PR xref
    "sphinxext.opengraph",  # opengraph metadata
    # Custom extensions (ADR-044 §10.2 + §10.4):
    "scieasy_directives",  # _ext/scieasy_directives.py (shell)
    "llms_txt_builder",  # _ext/llms_txt_builder.py (shell)
]

templates_path = ["_templates"]
exclude_patterns: list[str] = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]

# Source-file suffixes — MyST handles Markdown, default reST for .rst.
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# -- Nitpicky cross-reference enforcement (ADR-042 §23.4) --------------
# Every :py:class:`...` reference must resolve under autoapi's symbol
# table. Phantom-symbol references in prose fail the build.
nitpicky = True
nitpick_ignore_regex = [
    # Allowlist: external types we can't resolve without intersphinx
    # for the target project (added on a case-by-case basis).
    (r"py:class", r"_typeshed\..*"),
]

# -- AutoAPI configuration (ADR-042 §23.2) -----------------------------
# Static-analysis extraction from src/scieasy without importing.
autoapi_dirs = [str(_HERE.parent.parent / "src" / "scieasy")]
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
    "imported-members",
]
autoapi_python_class_content = "both"  # combine class + __init__ docstrings
autoapi_keep_files = False
autoapi_add_toctree_entry = True

# -- intersphinx (ADR-042 §23.2 + ADR-044 §10.1) -----------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest", None),
    "fastapi": ("https://fastapi.tiangolo.com", None),
    "zarr": ("https://zarr.readthedocs.io/en/stable", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "pandas": ("https://pandas.pydata.org/docs", None),
}

# -- MyST configuration ------------------------------------------------
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "substitution",
    "tasklist",
]

# -- numpydoc ---------------------------------------------------------
numpydoc_show_class_members = False
numpydoc_class_members_toctree = False

# -- autodoc_pydantic --------------------------------------------------
autodoc_pydantic_model_show_json = False
autodoc_pydantic_model_show_config_summary = True
autodoc_pydantic_model_show_validator_summary = True

# -- sphinx-gallery ----------------------------------------------------
# Examples gallery path; the directory is created by 1D sub-PR 3+ —
# until then sphinx-gallery must not error on an empty examples_dirs.
sphinx_gallery_conf = {
    "examples_dirs": [],
    "gallery_dirs": [],
    "filename_pattern": r"/example_.*\.py",
}

# -- sphinx-issues -----------------------------------------------------
issues_github_path = "zjzcpj/SciEasy"

# -- sphinx-copybutton -------------------------------------------------
copybutton_prompt_text = r">>> |\.\.\. |\$ |# "
copybutton_prompt_is_regexp = True


# -- linkcode_resolve --------------------------------------------------
def linkcode_resolve(domain: str, info: dict) -> str | None:
    """Return GitHub URL for a Python object (sphinx.ext.linkcode hook).

    Minimal v1 implementation: only resolves ``py`` domain entries by
    module path; line numbers are not computed (would require importing
    the module, which conflicts with autoapi's static-analysis stance).
    A future revision may add a libCST-based line resolver.
    """
    if domain != "py":
        return None
    module = info.get("module")
    if not module:
        return None
    return f"https://github.com/zjzcpj/SciEasy/blob/main/src/{module.replace('.', '/')}.py"


# -- HTML output -------------------------------------------------------
# pydata-sphinx-theme per ADR-044 §10.4 (replaces furo from ADR-042 §23.1).
html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_title = f"{project} {release}"
html_theme_options = {
    "github_url": "https://github.com/zjzcpj/SciEasy",
    "use_edit_page_button": False,
    "show_toc_level": 2,
    "navigation_depth": 3,
}

# -- Environment overrides ---------------------------------------------
# CI may set SCIEASY_DOCS_FAST=1 to skip autoapi (used by the smoke
# test path that just imports conf.py).
if os.environ.get("SCIEASY_DOCS_FAST") == "1":
    autoapi_dirs = []
