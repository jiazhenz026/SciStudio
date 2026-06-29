#!/usr/bin/env python3
"""Build the combined SciStudio documentation site (#1850).

Publishes ONE site to GitHub Pages that covers everything author-facing:

  - Home
  - User Guide        <- src/scistudio/_user_guide/   (the human guide; ships in
                         the wheel and is provisioned into projects)
  - API Reference     <- src/scistudio/_user_guide/api-reference/  (self-contained,
                         generated from docstrings + stability decorators; the
                         SAME artifact provisioned into projects — single source)
  - Package Development <- docs/package-development/   (repo-only developer guide)

Unlike ``build_reference.py`` (which renders the API reference via mkdocstrings
directives), this site is plain Markdown end to end: the API reference is the
self-contained Markdown generated into the package, so the published site and the
in-project reference can never disagree.

The build stages a unified docs tree under ``build/site-src/`` (mkdocs needs a
single ``docs_dir``) and runs ``mkdocs build`` with ``mkdocs.site.yml``.

Run (never ``pip install -e .``)::

    PYTHONPATH=$PWD/src python scripts/docs/build_site.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from build_reference import generate_selfcontained  # noqa: E402

USER_GUIDE_SRC = SRC / "scistudio" / "_user_guide"
PACKAGE_DEV_SRC = REPO_ROOT / "docs" / "package-development"
STAGE_DIR = REPO_ROOT / "build" / "site-src"  # gitignored (build/)
SITE_DIR = REPO_ROOT / "build" / "site"  # gitignored (build/)
SITE_CONFIG = REPO_ROOT / "mkdocs.site.yml"

_HOME = """\
# SciStudio documentation

Author-facing documentation for [SciStudio](https://github.com/jiazhenz026/SciStudio),
an AI-native workflow runtime for multimodal scientific data.

- **[User Guide](user-guide/README.md)** — using SciStudio: building and running
  workflows, previewing data, writing your own blocks, types, and plots.
- **[API Reference](user-guide/api-reference/index.md)** — the public API you may
  rely on, with signatures, docstrings, and stability tiers.
- **[Package Development](package-development/index.md)** — building a
  distributable SciStudio package (blocks, types, previewers).

The User Guide and API Reference are the same docs SciStudio provisions into each
project, so what you read here matches what ships with the app.
"""


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def stage() -> None:
    """Assemble the unified docs tree under STAGE_DIR."""
    # Ensure the self-contained API reference exists inside the user guide tree.
    generate_selfcontained()

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    (STAGE_DIR / "index.md").write_text(_HOME, encoding="utf-8")
    _copy_tree(USER_GUIDE_SRC, STAGE_DIR / "user-guide")
    _copy_tree(PACKAGE_DEV_SRC, STAGE_DIR / "package-development")
    print(f"  staged site sources -> {STAGE_DIR}")


def build() -> int:
    cmd = [
        sys.executable,
        "-m",
        "mkdocs",
        "build",
        "--config-file",
        str(SITE_CONFIG),
        "--site-dir",
        str(SITE_DIR),
    ]
    print(f"  $ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def main() -> int:
    print("Building combined SciStudio docs site (#1850) ...")
    stage()
    rc = build()
    if rc == 0:
        print(f"mkdocs build OK -> {SITE_DIR}")
    else:
        print(f"mkdocs build FAILED (exit {rc})", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
