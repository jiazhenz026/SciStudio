"""Bundled git binary locator (ADR-039 §3.1).

Locates the portable git executable shipped inside the ADR-037 desktop
bundle. The bundle layout — verified against
``docs/architecture/PROJECT_TREE.md`` — places the binary at:

- Windows:  ``<install>/resources/git/bin/git.exe``  (MinGit)
- macOS:    ``<install>/resources/git/bin/git``     (static universal2)
- Linux:    ``<install>/resources/git/bin/git``     (static musl)

For the ``scieasy gui`` developer CLI (no desktop bundle), the locator
falls back to a system ``git`` resolved via ``shutil.which``. The
developer fallback is *not* used in packaged desktop builds — users do
not need git installed.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class BundledGitMissing(RuntimeError):  # noqa: N818 — name part of public API surface
    """Raised when neither bundled nor system git can be located.

    Surfaced to users as a "Version control unavailable" toast in the
    desktop UI. The packaged build should never raise this — CI verifies
    the bundle includes ``resources/git/bin/git[.exe]`` before publishing
    artifacts.
    """


class GitBinary:
    """Resolved path to the git executable + invocation helpers.

    Construction is via :meth:`locate`. Direct instantiation with an
    explicit path is supported for tests (e.g. pointing at a known git
    fixture in a tmpdir).

    Attributes
    ----------
    path : pathlib.Path
        Absolute path to the git executable. Existence is verified at
        ``locate()`` time but the path is not re-checked on every call —
        callers expect a long-lived ``GitBinary`` instance.
    version : str | None
        Cached ``git --version`` string (best-effort; ``None`` on
        failure).
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.version: str | None = None
        # Best-effort version probe — log only.
        try:
            proc = subprocess.run(
                [str(self.path), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0:
                self.version = proc.stdout.strip()
        except Exception:  # pragma: no cover — diagnostic only
            logger.debug("git --version probe failed for %s", self.path, exc_info=True)

    # ------------------------------------------------------------------
    # Class methods — locator API used by GitEngine and the REST layer
    # ------------------------------------------------------------------

    @classmethod
    def locate(cls) -> GitBinary:
        """Find the bundled git binary, falling back to system git.

        See module docstring + ADR-039 §3.1 lines 56-88.

        Raises :class:`BundledGitMissing` if no executable found.
        """
        tried: list[str] = []

        # 1. Determine bundle root candidates.
        bundle_roots: list[Path] = []
        env_override = os.environ.get("SCIEASY_GIT_BUNDLE_ROOT")
        if env_override:
            bundle_roots.append(Path(env_override))

        if getattr(sys, "frozen", False):  # PyInstaller / packaged build
            exe_parent = Path(sys.executable).parent
            bundle_roots.append(exe_parent)
            # macOS app bundle layout
            if sys.platform == "darwin":
                bundle_roots.append(exe_parent.parent / "Resources")

        # Developer checkout: walk up from this file to find <repo>/desktop/.
        for parent in Path(__file__).resolve().parents:
            candidate_dev = parent / "desktop"
            if candidate_dev.is_dir():
                bundle_roots.append(candidate_dev)
                break

        git_name = "git.exe" if sys.platform == "win32" else "git"

        # 2. Try candidate paths inside each bundle root.
        for root in bundle_roots:
            for sub in (
                Path("resources") / "git" / "bin" / git_name,
                Path("resources") / "git" / "cmd" / git_name,
                Path("resources") / "git" / "mingw64" / "bin" / git_name,
            ):
                candidate = root / sub
                tried.append(str(candidate))
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    logger.info("Using bundled git at %s", candidate)
                    return cls(candidate)

        # 3. Fall back to system git.
        system_git = shutil.which("git")
        if system_git:
            tried.append(f"shutil.which('git') -> {system_git}")
            logger.info("Using system git at %s", system_git)
            return cls(Path(system_git))

        raise BundledGitMissing("No git binary found. Tried:\n  " + "\n  ".join(tried))

    # ------------------------------------------------------------------
    # Convenience invocation helpers
    # ------------------------------------------------------------------

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
        text: bool = True,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Invoke git with the given args.

        Thin ``subprocess.run`` wrapper that prepends ``self.path`` and
        injects SciEasy default env (``GIT_TERMINAL_PROMPT=0``,
        ``LANG=C``, ``GIT_PAGER=cat``).

        Raises :class:`GitError` (from ``git_engine``) when ``check`` and
        exit != 0.
        """
        # Lazy import to avoid circular dependency (git_engine imports
        # git_binary at module load time).
        from scieasy.core.versioning.git_engine import GitError

        argv = [str(self.path), *args]
        full_env = os.environ.copy()
        full_env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_PAGER": "cat",
                "LANG": "C",
                "LC_ALL": "C",
            }
        )
        if env:
            full_env.update(env)

        proc = subprocess.run(
            argv,
            capture_output=True,
            text=text,
            cwd=str(cwd) if cwd is not None else None,
            env=full_env,
            timeout=timeout,
            check=False,
        )
        if check and proc.returncode != 0:
            stderr = proc.stderr if isinstance(proc.stderr, str) else ""
            raise GitError(proc.returncode, stderr, args)
        return proc
