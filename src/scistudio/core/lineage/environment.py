"""EnvironmentSnapshot — captures Python version, key packages, and full freeze.

Per ADR-038 §5.2, the default capture now records a full ``uv pip freeze`` (or
``pip freeze`` fallback) so historical runs preserve the exact dependency
versions used at execution time. Block authors do not touch this — it is
collected by the worker subprocess (``runners/worker.py``) and persisted by the
engine-side ``LineageRecorder`` into ``runs.environment_snapshot``.
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

    Attributes:
        python_version: Python interpreter version string.
        platform: OS / platform identifier.
        key_packages: Mapping of package name to version for critical dependencies.
        full_freeze: Optional ``pip freeze`` / ``uv pip freeze`` output (the full
            dependency set). ADR-038 §5.2 makes this the default.
        conda_env: Optional conda environment export.
    """

    python_version: str
    platform: str
    key_packages: dict[str, str] = field(default_factory=dict)
    full_freeze: str | None = None
    conda_env: str | None = None

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
            full: When True (ADR-038 §5.2 default), also captures a full
                ``uv pip freeze`` (or ``pip freeze`` fallback) into
                :attr:`full_freeze`. Set to ``False`` to skip the freeze step
                for performance-sensitive paths (e.g. tests).
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
        """Serialize to a JSON-compatible dict for subprocess transport."""
        return {
            "python_version": self.python_version,
            "platform": self.platform,
            "key_packages": dict(self.key_packages),
            "full_freeze": self.full_freeze,
            "conda_env": self.conda_env,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentSnapshot:
        """Reconstruct from a dict produced by :meth:`to_dict`."""
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
