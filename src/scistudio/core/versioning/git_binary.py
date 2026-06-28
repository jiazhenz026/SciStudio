"""Locator for the bundled git binary.

Finds the portable git executable shipped inside the desktop bundle:

- Windows:  ``<install>/resources/git/bin/git.exe``  (MinGit)
- macOS:    ``<install>/resources/git/bin/git``       (static universal2)
- Linux:    ``<install>/resources/git/bin/git``       (static musl)

For the developer CLI (no desktop bundle), the locator falls back to a system
``git`` found on ``PATH``. Packaged desktop builds do not use that fallback —
users do not need git installed.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scistudio.core.versioning.errors import GitError

logger = logging.getLogger(__name__)


class BundledGitMissing(RuntimeError):  # noqa: N818 — name part of public API surface
    """Neither a bundled nor a system git binary could be found.

    Surfaced to users as a "version control unavailable" message. A packaged
    build should never raise this, because the bundle is verified to include a
    git binary before release.
    """


class GitBinary:
    """A resolved git executable plus helpers to invoke it.

    Construct via :meth:`locate`, which finds the bundled (or system) git.
    Direct construction with an explicit path is supported for tests (e.g.
    pointing at a known git fixture in a temporary directory).
    """

    def __init__(self, path: Path) -> None:
        """Wrap the git executable at *path* and probe its version.

        Args:
            path: Filesystem path to the git executable.
        """
        self.path = Path(path).resolve()
        """Absolute path to the resolved git executable."""
        self.version: str | None = None
        """Cached ``git --version`` string (best-effort; ``None`` on failure)."""
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

        Returns:
            A :class:`GitBinary` for the first git executable found.

        Raises:
            BundledGitMissing: When no git executable can be located.
        """
        tried: list[str] = []

        # 1. Determine bundle root candidates.
        bundle_roots: list[Path] = []
        env_override = os.environ.get("SCISTUDIO_GIT_BUNDLE_ROOT")
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
        """Invoke git with *args* and return the completed process.

        A thin :func:`subprocess.run` wrapper that prepends the resolved git
        path, injects SciStudio's default environment
        (``GIT_TERMINAL_PROMPT=0``, ``GIT_PAGER=cat``, ``LANG``/``LC_ALL=C``),
        and decodes git's output as UTF-8.

        Args:
            args: Git arguments (without the leading ``git``).
            cwd: Working directory for the invocation.
            check: When ``True``, raise on a non-zero exit.
            text: Decode stdout/stderr as text (UTF-8) rather than bytes.
            env: Extra environment variables to add or override.
            timeout: Optional timeout in seconds.

        Returns:
            The completed :class:`subprocess.CompletedProcess`.

        Raises:
            GitError: When *check* is ``True`` and git exits non-zero.
        """
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

        # ADR-039 #983: pin stdout/stderr decode to UTF-8 (with replacement
        # fallback) rather than the system locale. On Chinese Windows the
        # default locale is GBK/cp936, and ``text=True`` makes Python
        # auto-decode subprocess output using that locale. Git always emits
        # UTF-8 (commit messages, author names, paths) regardless of the
        # ``LANG=C`` / ``LC_ALL=C`` env we already inject, because those
        # localize git's own error messages but do not affect repo data
        # passed through. Any non-GBK byte (em dash, Chinese chars, emoji,
        # any rare unicode in commit subjects) would crash the reader
        # thread with ``UnicodeDecodeError``, leaving an empty stdout and
        # the frontend rendering "No commits yet" even when the repo is
        # healthy. ``errors='replace'`` is the defensive guard against any
        # remaining edge case (binary blob slipping through, malformed
        # input from an external tool). Only meaningful when ``text=True``.
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
            cwd=str(cwd) if cwd is not None else None,
            env=full_env,
            timeout=timeout,
            check=False,
        )
        if check and proc.returncode != 0:
            stderr = proc.stderr if isinstance(proc.stderr, str) else ""
            raise GitError(proc.returncode, stderr, args)
        return proc
