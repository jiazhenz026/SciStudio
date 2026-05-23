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


class CodeBlockTimeoutError(TimeoutError):
    """Raised when a CodeBlock v2 script exceeds its configured timeout."""

    def __init__(self, message: str, *, timeout_seconds: float, stdout: str | None, stderr: str | None) -> None:
        super().__init__(message)
        self.timeout_seconds = timeout_seconds
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class CodeBlockRuntimeContext:
    """Shared CodeBlock v2 execution context passed to interpreter backends."""

    config: CodeBlockConfig
    script_path: Path
    project_dir: Path
    exchange_dir: Path
    environment_config: Mapping[str, Any]


class CodeBlockBackend(Protocol):
    """Registration surface for CodeBlock v2 interpreter backends."""

    name: str
    extensions: frozenset[str]

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        """Return whether this backend can run *script_path*."""

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        """Resolve interpreter metadata for a CodeBlock run."""

    def run(
        self,
        context: CodeBlockRuntimeContext,
        interpreter: ResolvedInterpreter,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a prepared CodeBlock run."""


_CODEBLOCK_BACKENDS: list[CodeBlockBackend] = []
_BACKEND_MODULES_LOADED = False


def register_codeblock_backend(backend: CodeBlockBackend, *, replace: bool = False) -> None:
    """Register a CodeBlock v2 interpreter backend.

    Sibling ADR-041 tracks should register notebook, R/Quarto, shell, and
    MATLAB-family backends through this surface instead of editing
    ``CodeBlock`` dispatch logic.
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


def unregister_codeblock_backend(name: str) -> None:
    """Remove a registered CodeBlock backend by name."""

    _CODEBLOCK_BACKENDS[:] = [backend for backend in _CODEBLOCK_BACKENDS if backend.name != name]


def list_codeblock_backends() -> tuple[CodeBlockBackend, ...]:
    """Return registered CodeBlock v2 interpreter backends."""

    ensure_codeblock_backends_loaded()
    return tuple(_CODEBLOCK_BACKENDS)


def resolve_codeblock_backend(script_path: Path, config: CodeBlockConfig) -> CodeBlockBackend:
    """Select the registered backend for a CodeBlock v2 script."""

    ensure_codeblock_backends_loaded()
    for backend in _CODEBLOCK_BACKENDS:
        if backend.supports(script_path, config):
            return backend
    supported = sorted({extension for backend in _CODEBLOCK_BACKENDS for extension in backend.extensions})
    raise ValueError(
        f"Unsupported CodeBlock script extension {script_path.suffix or '<none>'!r}; "
        f"registered extensions: {supported}."
    )


def ensure_codeblock_backends_loaded() -> None:
    """Load built-in CodeBlock backend modules exactly once."""

    global _BACKEND_MODULES_LOADED
    if _BACKEND_MODULES_LOADED:
        return
    from scistudio.blocks.code.backends import load_codeblock_backend_modules

    load_codeblock_backend_modules()
    _BACKEND_MODULES_LOADED = True


def run_codeblock_process(
    *,
    argv: Sequence[str],
    cwd: Path,
    env_delta: Mapping[str, str],
    timeout_seconds: float | None,
) -> subprocess.CompletedProcess[str]:
    """Run an interpreter process with CodeBlock v2 environment handling."""

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
    "ensure_codeblock_backends_loaded",
    "list_codeblock_backends",
    "register_codeblock_backend",
    "resolve_codeblock_backend",
    "run_codeblock_process",
    "unregister_codeblock_backend",
]
