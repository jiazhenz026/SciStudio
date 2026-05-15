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

Skeleton phase: ``GitBinary.locate()`` raises ``NotImplementedError`` per
the comment block. Impl agent (D39-2.2b) fills the body using the
algorithm documented below.
"""

from __future__ import annotations

from pathlib import Path


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
    """

    def __init__(self, path: Path) -> None:
        # Implementation note for D39-2.2b:
        # ---------------------------------
        # 1. Store ``path`` as ``self.path`` (resolve() to canonical form).
        # 2. Optionally cache ``self.version`` via a one-shot
        #    ``git --version`` subprocess call so log messages can report
        #    the bundled version. Failure here is non-fatal — log a
        #    warning and leave ``self.version = None``.
        # 3. No subprocess work in __init__ if it would slow app startup.
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    # ------------------------------------------------------------------
    # Class methods — locator API used by GitEngine and the REST layer
    # ------------------------------------------------------------------

    @classmethod
    def locate(cls) -> GitBinary:
        """Find the bundled git binary, falling back to system git.

        Purpose
        -------
        The single entry point for "give me a working git executable".
        ``GitEngine.__init__`` calls this once and reuses the instance.

        Signature contract
        ------------------
        - Input: none (locator inspects the environment).
        - Output: :class:`GitBinary` instance with a verified ``.path``.
        - Errors: :class:`BundledGitMissing` if no executable found.

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Determine the bundle root:

           a. If ``sys.frozen`` is set (PyInstaller / electron-builder
              bundle), bundle root = ``Path(sys.executable).parent``.
              On macOS app-bundle this may need adjustment to
              ``Path(sys.executable).parent.parent / "Resources"``.
              Verify exact layout against ADR-037 once that ADR's
              packaging script lands.
           b. Otherwise look for an env var override
              ``SCIEASY_GIT_BUNDLE_ROOT`` (used by integration tests to
              point at a fixture tree).
           c. Otherwise treat the developer checkout as the bundle root
              and check ``<repo>/desktop/resources/git/`` — this is
              populated by ``desktop/scripts/fetch-git-portable.{ps1,sh}``
              and may not exist in a fresh clone.

        2. Compute the candidate binary path:

              ``bundle_root / "resources" / "git" / "bin" / git_name``

           where ``git_name = "git.exe"`` on Windows else ``"git"``.

        3. If the candidate exists and is executable
           (``os.access(path, os.X_OK)``), return ``cls(path)``.

        4. Otherwise fall back to ``shutil.which("git")`` for the dev CLI
           use case. Log at INFO level "Using system git at <path>" so
           the user can see why their packaged build is not using the
           pinned bundled version.

        5. If neither path works, raise :class:`BundledGitMissing` with
           a message listing every path tried.

        Edge cases
        ----------
        - PyInstaller bundle: ``sys._MEIPASS`` is the temp extract dir;
          prefer ``Path(sys.executable).parent`` over ``_MEIPASS`` so the
          binary survives across runs (the temp dir is wiped on exit).
        - macOS app bundle: paths inside ``.app/Contents/Resources/`` are
          read-only but executable; that is fine — we never write to the
          binary.
        - Symlinks: do NOT resolve symlinks for the bundle root (the
          electron-builder layout uses symlinks in dev builds). Resolve
          the final binary path only.

        Test plan (D39-2.2b → tests/core/test_git_engine.py)
        ----------------------------------------------------
        - ``test_locate_bundled_path_wins`` — env var points at a
          tmpdir with a fake git executable; locator returns that path.
        - ``test_locate_falls_back_to_system_git`` — bundle path absent
          but ``shutil.which("git")`` resolves; locator returns system
          path.
        - ``test_locate_raises_when_nothing_found`` — both paths empty;
          locator raises ``BundledGitMissing`` mentioning every tried
          path.

        ADR references
        --------------
        - §3.1 lines 56-88 (bundled-git-CLI engine decision + per-platform
          packaging)
        - §5.1 line 432 (`git_binary.py` new file row)
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

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
    ) -> object:
        """Invoke git with the given args; return the ``subprocess.CompletedProcess``.

        Purpose
        -------
        Thin ``subprocess.run`` wrapper that prepends ``self.path`` and
        injects a SciEasy-default environment (e.g. ``GIT_TERMINAL_PROMPT=0``
        to refuse interactive auth, ``LANG=C`` for stable output).

        Signature contract
        ------------------
        - Input: ``args`` is the list of arguments AFTER the git binary
          (e.g. ``["status", "--porcelain=v2"]``); ``cwd`` is the
          repository working directory; ``check`` controls whether to
          raise on non-zero exit; ``text``/``env``/``timeout`` mirror
          ``subprocess.run``.
        - Output: ``subprocess.CompletedProcess`` with stdout/stderr.
        - Errors: :class:`GitError` (from ``git_engine``) if ``check`` and
          exit != 0.

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Build the full argv: ``[str(self.path), *args]``.
        2. Build the env: start from ``os.environ.copy()``, then overlay:
           - ``GIT_TERMINAL_PROMPT = "0"`` (never prompt for credentials)
           - ``GIT_PAGER = "cat"`` (defensive — never page output)
           - ``LANG = "C"`` (stable porcelain wording)
           - any caller-provided ``env`` overrides
        3. Call ``subprocess.run`` with
           ``capture_output=True, text=text, cwd=cwd, env=env, timeout=timeout``.
        4. If ``check`` and ``returncode != 0``: raise
           ``GitError(returncode, stderr, args)`` so the caller can render
           a structured error envelope to the REST layer.
        5. Return the ``CompletedProcess``.

        Edge cases
        ----------
        - Long-running operations (e.g. clone large repo) — pass an
          explicit ``timeout``; default is ``None`` (no timeout). v1
          operations are all local and should complete in <30s.
        - Windows path-separator quirks: pass ``cwd`` as a ``Path`` and
          let subprocess handle quoting. Do not shell=True; git args may
          contain user-provided messages that need no quoting.
        - Binary output (rare; e.g. ``git show <sha>:image.png``): pass
          ``text=False`` and decode the caller's way.

        Test plan
        ---------
        - ``test_run_passes_args`` — args echo via a fake git stub.
        - ``test_run_raises_on_nonzero`` — fake git returns 1; expect
          GitError with stderr captured.
        - ``test_run_respects_cwd`` — ``git rev-parse --show-toplevel``
          returns the cwd repo path.

        ADR references
        --------------
        - §7.3 risks — output parsing fragility; we mitigate by pinning
          ``LANG=C`` here.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")
