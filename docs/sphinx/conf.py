from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

project = "SciEasy"
author = "SciEasy Contributors"
copyright = "2026, SciEasy Contributors"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.linkcode",
    "sphinx_needs",
    "sphinx_autoapi.extension",
    "numpydoc",
    "sphinx_click",
    "sphinxcontrib.autodoc_pydantic",
    "sphinxcontrib.openapi",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinx_issues",
    "sphinx_gallery.gen_gallery",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"
nitpicky = True
keep_warnings = True
html_theme = "pydata_sphinx_theme"

autoapi_type = "python"
autoapi_dirs = [str(ROOT / "src" / "scieasy")]
autoapi_keep_files = False
autosummary_generate = True
numpydoc_show_class_members = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", {}),
    "pydantic": ("https://docs.pydantic.dev/latest", {}),
}

sphinx_gallery_conf = {
    "examples_dirs": [str(ROOT / "docs" / "user" / "tutorials")],
    "gallery_dirs": [str(ROOT / "docs" / "user" / "examples-gallery")],
}


def linkcode_resolve(domain: str, info: dict[str, str]) -> str | None:
    if domain != "py" or not info.get("module"):
        return None
    module_path = info["module"].replace(".", "/")
    return f"https://github.com/jiazhenz026/SciEasy/blob/main/src/{module_path}.py"
