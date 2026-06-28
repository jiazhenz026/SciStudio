"""CodeBlock v2 backend-registry primitives.

Issue #1482: extracted from :mod:`scistudio.blocks.code.code_block` to
break the static import cycle between ``code_block`` and
:mod:`scistudio.blocks.code.validation`. ``validation._script_extension_diagnostics``
needs ``list_codeblock_backends`` to surface the registered extension
set; importing it from ``code_block`` (which itself imports
``validate_codeblock_config`` from ``validation``) creates the cycle
that sentrux flags. Putting the registry primitives in their own
module makes ``validation → _backends_registry`` a one-way edge and
keeps ``code_block`` free to depend on both without re-introducing a
cycle.

Public surface (re-exported by ``code_block`` for backward
compatibility with the ``backends/*`` modules that import these
names from ``code_block``):

- :class:`CodeBlockBackend` — Protocol every backend implements.
- :class:`CodeBlockRuntimeContext` — frozen dataclass passed to backends.
- :func:`register_codeblock_backend` / :func:`unregister_codeblock_backend`
  — mutate the in-process registry.
- :func:`list_codeblock_backends` / :func:`resolve_codeblock_backend`
  — read the registry; both trigger
  :func:`ensure_codeblock_backends_loaded` so first use lazy-loads the
  built-in backend modules.
- :func:`ensure_codeblock_backends_loaded` — idempotent entry point.
- :func:`run_codeblock_process` — interpreter subprocess wrapper.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scistudio.blocks.code.config import CodeBlockConfig
from scistudio.blocks.code.interpreters import ResolvedInterpreter
from scistudio.stability import provisional


@provisional(since="0.3.1")
class CodeBlockTimeoutError(TimeoutError):
    """Raised when a Code Block script runs longer than its allowed time.

    A Code Block can set a wall-clock time limit for its script. When the
    launched interpreter process exceeds that limit it is stopped and this
    error is raised, carrying whatever the script printed before it was
    killed so you can see how far it got.

    Example:
        >>> try:
        ...     run_codeblock_process(
        ...         argv=["python", "slow.py"],
        ...         cwd=Path("."),
        ...         env_delta={},
        ...         timeout_seconds=1.0,
        ...     )
        ... except CodeBlockTimeoutError as err:
        ...     print(err.timeout_seconds, err.stderr)
    """

    def __init__(self, message: str, *, timeout_seconds: float, stdout: str | None, stderr: str | None) -> None:
        super().__init__(message)
        self.timeout_seconds = timeout_seconds
        """Time limit, in seconds, that the script exceeded before it was stopped."""
        self.stdout = stdout
        """Standard output captured before the timeout, or ``None`` if unavailable."""
        self.stderr = stderr
        """Standard error captured before the timeout, or ``None`` if unavailable."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class CodeBlockRuntimeContext:
    """Everything a backend needs to resolve and launch one script run.

    The Code Block builds this read-only bundle once per run and hands it to
    the selected backend's :meth:`CodeBlockBackend.resolve` and
    :meth:`CodeBlockBackend.run` methods. It names the script to run, where the
    project lives, and the exchange folder where the runtime wrote the declared
    inputs and expects the declared outputs.
    """

    config: CodeBlockConfig
    """The validated Code Block configuration for this run."""
    script_path: Path
    """Absolute path to the project-local script to execute."""
    project_dir: Path
    """Absolute path to the project root the script belongs to."""
    exchange_dir: Path
    """Per-run folder holding the ``inputs/`` and ``outputs/`` subfolders."""
    environment_config: Mapping[str, Any]
    """Interpreter and environment hints (interpreter path, environment variables)."""


@provisional(since="0.3.1")
def codeblock_exchange_env(context: CodeBlockRuntimeContext) -> dict[str, str]:
    """Build the ``SCISTUDIO_*`` environment variables a script uses to find its files.

    A Code Block script does not receive its inputs as function arguments; the
    runtime writes them to files and the script reads and writes files. These
    environment variables tell the script where those folders are, so it can
    locate its declared inputs and write its declared outputs regardless of the
    language it is written in.

    Args:
        context: The run context whose exchange directory and script path the
            variables point at.

    Returns:
        A mapping with the ``SCISTUDIO_EXCHANGE_DIR``, ``SCISTUDIO_INPUTS_DIR``,
        ``SCISTUDIO_OUTPUTS_DIR``, and ``SCISTUDIO_SCRIPT_PATH`` keys.
    """

    return {
        "SCISTUDIO_EXCHANGE_DIR": str(context.exchange_dir),
        "SCISTUDIO_INPUTS_DIR": str(context.exchange_dir / "inputs"),
        "SCISTUDIO_OUTPUTS_DIR": str(context.exchange_dir / "outputs"),
        "SCISTUDIO_SCRIPT_PATH": str(context.script_path),
    }


@provisional(since="0.3.1")
class CodeBlockBackend(Protocol):
    """Interface an interpreter backend must implement to run Code Block scripts.

    A backend teaches the Code Block how to run scripts written in one language
    family (Python, R/Quarto, shell, MATLAB/Octave, or Jupyter notebooks). Each
    backend declares the file extensions it owns, decides whether it can run a
    given script, resolves the interpreter command, and launches the process.
    Register your own backend with :func:`register_codeblock_backend` to add a
    new language without changing the Code Block itself.

    Example:
        >>> class JuliaBackend:
        ...     name = "julia"
        ...     extensions = frozenset({".jl"})
        ...     def supports(self, script_path, config):
        ...         return script_path.suffix.lower() in self.extensions
        ...     def resolve(self, context): ...
        ...     def run(self, context, interpreter): ...
        >>> register_codeblock_backend(JuliaBackend())
    """

    name: str
    """Unique backend identifier, for example ``"python"`` or ``"r-quarto"``."""
    extensions: frozenset[str]
    """Lowercase file extensions this backend handles, each with a leading dot."""

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        """Return whether this backend can run the script at *script_path*."""

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        """Resolve the interpreter command and environment for a run."""

    def run(
        self,
        context: CodeBlockRuntimeContext,
        interpreter: ResolvedInterpreter,
    ) -> subprocess.CompletedProcess[str]:
        """Launch the resolved interpreter and return the finished process."""


_CODEBLOCK_BACKENDS: list[CodeBlockBackend] = []
_BACKEND_MODULES_LOADED = False


@provisional(since="0.3.1")
def register_codeblock_backend(backend: CodeBlockBackend, *, replace: bool = False) -> None:
    """Add an interpreter backend to the in-process Code Block registry.

    Use this to teach the Code Block a new language (for example a Julia or Go
    backend) without editing the Code Block itself. Once registered, the Code
    Block routes any script whose extension the backend declares to that
    backend. The notebook, R/Quarto, shell, and MATLAB-family backends register
    themselves through this same entry point.

    Args:
        backend: The backend to register. Its ``name`` must not be empty and
            each of its ``extensions`` must start with a dot.
        replace: When ``True``, replace any existing backend that shares the
            same name or any extension. When ``False`` (the default), a clash
            raises instead of overwriting.

    Raises:
        ValueError: If the backend declares no name, declares no extensions,
            declares an extension without a leading dot, or clashes with an
            already-registered backend while *replace* is ``False``.
    """

    normalized_extensions = frozenset(extension.lower() for extension in backend.extensions)
    if not backend.name:
        raise ValueError("CodeBlock backend name must not be empty")
    if not normalized_extensions:
        raise ValueError("CodeBlock backend must declare at least one extension")
    if any(not extension.startswith(".") for extension in normalized_extensions):
        raise ValueError("CodeBlock backend extensions must include a leading dot")

    conflicts = [
        existing
        for existing in _CODEBLOCK_BACKENDS
        if existing.name == backend.name or existing.extensions.intersection(normalized_extensions)
    ]
    if conflicts and not replace:
        names = ", ".join(sorted(existing.name for existing in conflicts))
        raise ValueError(f"CodeBlock backend conflicts with existing backend(s): {names}")

    _CODEBLOCK_BACKENDS[:] = [
        existing
        for existing in _CODEBLOCK_BACKENDS
        if existing.name != backend.name and not existing.extensions.intersection(normalized_extensions)
    ]
    _CODEBLOCK_BACKENDS.append(backend)


@provisional(since="0.3.1")
def unregister_codeblock_backend(name: str) -> None:
    """Remove a previously registered backend by its name.

    Args:
        name: The backend's ``name``. An unknown name is ignored.
    """

    _CODEBLOCK_BACKENDS[:] = [backend for backend in _CODEBLOCK_BACKENDS if backend.name != name]


@provisional(since="0.3.1")
def list_codeblock_backends() -> tuple[CodeBlockBackend, ...]:
    """Return every currently registered interpreter backend.

    The first call loads the built-in backends (Python, notebook, R/Quarto,
    shell, MATLAB/Octave) on demand, so the result always includes them.

    Returns:
        A tuple of the registered backends, in registration order.
    """

    ensure_codeblock_backends_loaded()
    return tuple(_CODEBLOCK_BACKENDS)


@provisional(since="0.3.1")
def resolve_codeblock_backend(script_path: Path, config: CodeBlockConfig) -> CodeBlockBackend:
    """Pick the registered backend that can run a given script.

    Args:
        script_path: Path to the script whose extension selects the backend.
        config: The Code Block configuration, passed to each backend's
            :meth:`CodeBlockBackend.supports` check.

    Returns:
        The first registered backend that reports it can run *script_path*.

    Raises:
        ValueError: If no registered backend handles the script's extension.
    """

    ensure_codeblock_backends_loaded()
    for backend in _CODEBLOCK_BACKENDS:
        if backend.supports(script_path, config):
            return backend
    supported = sorted({extension for backend in _CODEBLOCK_BACKENDS for extension in backend.extensions})
    raise ValueError(
        f"Unsupported CodeBlock script extension {script_path.suffix or '<none>'!r}; "
        f"registered extensions: {supported}."
    )


@provisional(since="0.3.1")
def ensure_codeblock_backends_loaded() -> None:
    """Import the built-in backend modules once so they self-register.

    Reading the registry through :func:`list_codeblock_backends` or
    :func:`resolve_codeblock_backend` calls this for you; it does nothing after
    the first call.
    """

    global _BACKEND_MODULES_LOADED
    if _BACKEND_MODULES_LOADED:
        return
    from scistudio.blocks.code.backends import load_codeblock_backend_modules

    load_codeblock_backend_modules()
    _BACKEND_MODULES_LOADED = True


@provisional(since="0.3.1")
def run_codeblock_process(
    *,
    argv: Sequence[str],
    cwd: Path,
    env_delta: Mapping[str, str],
    timeout_seconds: float | None,
) -> subprocess.CompletedProcess[str]:
    """Launch an interpreter as a subprocess and capture its output.

    Backends call this to actually run a script. It starts from the current
    process environment, layers the backend's extra variables on top, captures
    standard output and standard error as text, and enforces an optional time
    limit.

    Args:
        argv: The full command to run, for example ``["python", "script.py"]``.
        cwd: Working directory to launch the process from.
        env_delta: Extra environment variables to add on top of the current
            environment.
        timeout_seconds: Wall-clock limit in seconds, or ``None`` for no limit.

    Returns:
        The completed process, with its exit code and captured text output. A
        non-zero exit code is returned rather than raised, so the caller decides
        how to react to a failing script.

    Raises:
        CodeBlockTimeoutError: If the process runs longer than *timeout_seconds*.
    """

    env = os.environ.copy()
    env.update({str(key): str(value) for key, value in env_delta.items()})
    try:
        return subprocess.run(
            [str(arg) for arg in argv],
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeBlockTimeoutError(
            f"CodeBlock script timed out after {timeout_seconds} seconds.",
            timeout_seconds=float(timeout_seconds or 0),
            stdout=exc.stdout if isinstance(exc.stdout, str) else None,
            stderr=exc.stderr if isinstance(exc.stderr, str) else None,
        ) from exc


__all__ = [
    "CodeBlockBackend",
    "CodeBlockRuntimeContext",
    "CodeBlockTimeoutError",
    "codeblock_exchange_env",
    "ensure_codeblock_backends_loaded",
    "list_codeblock_backends",
    "register_codeblock_backend",
    "resolve_codeblock_backend",
    "run_codeblock_process",
    "unregister_codeblock_backend",
]
