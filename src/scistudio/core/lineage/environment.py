"""EnvironmentSnapshot — captures Python version, key packages, and full freeze.

By default the capture records a full ``uv pip freeze`` (or ``pip freeze``
fallback) so a historical run preserves the exact dependency versions it used.
Block authors do not touch this — the worker subprocess collects it and the
engine persists it alongside the run record.
"""

from __future__ import annotations

import contextlib
import platform as platform_mod
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any


@dataclass
class EnvironmentSnapshot:
    """Frozen snapshot of the execution environment at the time a block ran.

    Captures enough to reproduce or audit a run's dependency set: the Python
    version, the platform, the versions of a few key packages, and optionally a
    full dependency freeze.

    Example:
        >>> snap = EnvironmentSnapshot.capture(full=False)
        >>> "scistudio" in snap.key_packages or snap.python_version != ""
        True
    """

    python_version: str
    """Python interpreter version string."""
    platform: str
    """Operating-system / platform identifier."""
    key_packages: dict[str, str] = field(default_factory=dict)
    """Mapping of selected package names to their installed versions."""
    full_freeze: str | None = None
    """Full ``pip freeze`` / ``uv pip freeze`` output, or ``None`` when not captured."""
    conda_env: str | None = None
    """Optional conda environment export, or ``None``."""

    @classmethod
    def capture(
        cls,
        key_dependencies: list[str] | None = None,
        *,
        full: bool = True,
    ) -> EnvironmentSnapshot:
        """Capture the current runtime environment.

        Args:
            key_dependencies: Package names whose versions should be recorded
                in :attr:`key_packages`. Defaults to core SciStudio dependencies.
            full: When ``True`` (the default), also capture a full
                ``uv pip freeze`` (or ``pip freeze`` fallback) into
                :attr:`full_freeze`. Set to ``False`` to skip the freeze step
                for performance-sensitive paths (e.g. tests).

        Returns:
            A new :class:`EnvironmentSnapshot` describing the active environment.
        """
        if key_dependencies is None:
            key_dependencies = ["scistudio", "numpy", "zarr", "pyarrow", "pydantic"]

        key_packages: dict[str, str] = {}
        for pkg in key_dependencies:
            with contextlib.suppress(PackageNotFoundError):
                key_packages[pkg] = version(pkg)

        full_freeze: str | None = None
        if full:
            full_freeze = _run_pip_freeze()

        return cls(
            python_version=sys.version,
            platform=platform_mod.platform(),
            key_packages=key_packages,
            full_freeze=full_freeze,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict of this snapshot for subprocess transport.

        Returns:
            A dict with the snapshot's fields, ready to serialise to JSON.
        """
        return {
            "python_version": self.python_version,
            "platform": self.platform,
            "key_packages": dict(self.key_packages),
            "full_freeze": self.full_freeze,
            "conda_env": self.conda_env,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentSnapshot:
        """Reconstruct a snapshot from a dict produced by :meth:`to_dict`.

        Args:
            data: A dict in the shape returned by :meth:`to_dict`.

        Returns:
            The reconstructed :class:`EnvironmentSnapshot`.
        """
        return cls(
            python_version=data["python_version"],
            platform=data["platform"],
            key_packages=data.get("key_packages", {}),
            full_freeze=data.get("full_freeze"),
            conda_env=data.get("conda_env"),
        )


def _run_pip_freeze() -> str | None:
    """Best-effort full pip freeze. Tries ``uv pip freeze`` then ``pip freeze``.

    Returns the captured stdout (text) or ``None`` if both fail. This is
    intentionally non-fatal because the env snapshot is metadata, not a
    correctness requirement.
    """
    # Prefer uv (ADR-038 §5.2) if available — it is significantly faster
    # than `pip freeze` on uv-managed envs.
    uv_bin = shutil.which("uv")
    if uv_bin is not None:
        with contextlib.suppress(Exception):
            result = subprocess.run(  # uv resolved via shutil.which above
                [uv_bin, "pip", "freeze"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout

    # Fallback: invoke pip via the current interpreter so we capture the
    # active venv even when no `pip` binary is on PATH.
    with contextlib.suppress(Exception):
        result = subprocess.run(  # sys.executable is trusted
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    return None
