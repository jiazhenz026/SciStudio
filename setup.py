"""Custom setuptools shim that bundles the frontend SPA into the wheel.

Most project metadata lives in ``pyproject.toml``. This file exists only to
hook a frontend-build step into ``python -m build`` / ``pip install .`` so
that end users get a working SPA out of ``scistudio gui`` without needing
Node locally at install time.

Flow
----
Whenever setuptools runs the ``build_py`` command (which happens during
wheel building, source installs, and editable installs), we:

1. Check whether ``src/scistudio/api/static/`` already contains a complete
   SPA bundle: ``index.html``, ``assets/``, and at least one JavaScript asset.
   If yes, we assume a previous invocation (or a pre-built sdist) already
   populated it and skip the build. This keeps offline / no-Node installs
   working as long as the static dir was pre-populated.
2. Otherwise, shell out to ``npm ci && npm run build`` inside
   ``frontend/`` and copy the resulting ``dist/`` tree into
   ``src/scistudio/api/static/``.
3. If Node is not available and the static dir is empty, we print a
   warning but do NOT fail the install — the runtime falls back to the
   Swagger panel so at least the API is reachable. See #389.

The runtime also has a dev fallback (``src/scistudio/api/app.py`` →
``_resolve_spa_static_dir``) that serves ``frontend/dist/`` directly when
the packaged static dir is empty, so editable installs work without ever
running this hook.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

_REPO_ROOT = Path(__file__).parent.resolve()
_FRONTEND_DIR = _REPO_ROOT / "frontend"
_FRONTEND_DIST = _FRONTEND_DIR / "dist"
_PACKAGED_STATIC = _REPO_ROOT / "src" / "scistudio" / "api" / "static"


def _log(msg: str) -> None:
    print(f"[scistudio-build] {msg}", file=sys.stderr)


def _is_complete_spa_bundle(static_dir: Path) -> bool:
    assets_dir = static_dir / "assets"
    return (
        (static_dir / "index.html").is_file()
        and assets_dir.is_dir()
        and any(path.is_file() for path in assets_dir.rglob("*.js"))
    )


def _has_prebuilt_spa() -> bool:
    return _is_complete_spa_bundle(_PACKAGED_STATIC)


def _npm_available() -> bool:
    # ``shutil.which`` handles Windows ``.cmd`` shims correctly.
    return shutil.which("npm") is not None


def _run_frontend_build(*, required: bool = False) -> None:
    if not _FRONTEND_DIR.is_dir():
        msg = f"no frontend/ directory at {_FRONTEND_DIR}; skipping SPA build"
        if required:
            raise RuntimeError(msg)
        _log(msg)
        return

    if not _npm_available():
        msg = (
            "npm not found on PATH; skipping SPA build. Install Node.js to "
            "bundle the SPA, or set SCISTUDIO_SKIP_FRONTEND_BUILD=1 to silence "
            "this warning. The runtime will redirect GET / to /docs."
        )
        if required:
            raise RuntimeError(msg)
        _log(msg)
        return

    _log("running `npm ci` in frontend/")
    subprocess.check_call(["npm", "ci"], cwd=_FRONTEND_DIR, shell=sys.platform == "win32")
    _log("running `npm run build` in frontend/")
    subprocess.check_call(["npm", "run", "build"], cwd=_FRONTEND_DIR, shell=sys.platform == "win32")

    if not _is_complete_spa_bundle(_FRONTEND_DIST):
        raise RuntimeError(
            "frontend build did not produce a complete SPA bundle "
            f"(expected index.html, assets/, and at least one JS asset under {_FRONTEND_DIST})"
        )

    if _PACKAGED_STATIC.exists():
        shutil.rmtree(_PACKAGED_STATIC)
    shutil.copytree(_FRONTEND_DIST, _PACKAGED_STATIC)
    _log(f"copied SPA bundle to {_PACKAGED_STATIC}")


class build_py(_build_py):  # noqa: N801 - setuptools command name must stay lowercase
    """Extend ``build_py`` to bundle the frontend SPA before collecting package data."""

    def run(self) -> None:
        if os.environ.get("SCISTUDIO_SKIP_FRONTEND_BUILD") == "1":
            _log("SCISTUDIO_SKIP_FRONTEND_BUILD=1 set; skipping SPA build")
        elif _has_prebuilt_spa():
            _log(f"found pre-built SPA at {_PACKAGED_STATIC}; skipping rebuild")
        else:
            required = os.environ.get("SCISTUDIO_REQUIRE_FRONTEND_BUILD") == "1"
            try:
                _run_frontend_build(required=required)
            except subprocess.CalledProcessError as exc:
                if required:
                    raise RuntimeError(f"frontend build failed with exit {exc.returncode}") from exc
                _log(f"frontend build failed with exit {exc.returncode}; continuing without SPA")
            except Exception as exc:  # pragma: no cover - defensive
                if required:
                    raise
                _log(f"unexpected error bundling frontend SPA: {exc!r}; continuing without SPA")
        super().run()


setup(cmdclass={"build_py": build_py})
