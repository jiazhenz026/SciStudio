"""EnvironmentSnapshot — captures Python version, key packages, and full freeze.

By default the capture records a full ``uv pip freeze`` (or ``pip freeze``
fallback) so a historical run preserves the exact dependency versions it used.
Block authors do not touch this — the worker subprocess collects it and the
engine persists it alongside the run record.

**Storing a snapshot once (FR-034).** A workflow run captures one snapshot and
keeps it; an explore session captures one whenever a cell installs something
(``docs/specs/adr-054-explore-session.md`` FR-012), which over an afternoon can
be many captures of an environment that changed twice. A full freeze is tens of
kilobytes, so copying it into every record is the wrong shape.
:meth:`EnvironmentSnapshot.reference` gives a snapshot a content address, and
:class:`EnvironmentSnapshotStore` writes each distinct environment to disk once
under that address; records carry the reference string instead of the snapshot.
Two captures of an unchanged environment produce the same reference and the
second write is a no-op.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import platform as platform_mod
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from scistudio.stability import provisional

#: Prefix every environment reference carries, so a reference is recognisable
#: as one wherever it is stored and can never be confused with a bare digest.
ENVIRONMENT_REFERENCE_PREFIX = "env:sha256:"


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
        executable: str | None = None,
    ) -> EnvironmentSnapshot:
        """Capture the current runtime environment.

        Args:
            key_dependencies: Package names whose versions should be recorded
                in :attr:`key_packages`. Defaults to core SciStudio dependencies.
            full: When ``True`` (the default), also capture a full
                ``uv pip freeze`` (or ``pip freeze`` fallback) into
                :attr:`full_freeze`. Set to ``False`` to skip the freeze step
                for performance-sensitive paths (e.g. tests).
            executable: Interpreter whose installed packages the freeze should
                describe. ``None`` (the default) keeps the historical
                behaviour: prefer ``uv pip freeze`` and fall back to this
                process's own ``pip``. Pass ``sys.executable`` from inside the
                process being described — an explore session's kernel is a
                *different* interpreter from the service that captures on its
                behalf, and ``uv`` resolves an environment from the working
                directory rather than from the caller, so an unpinned freeze
                can describe the wrong one (ADR-054 FR-012).

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
            full_freeze = _run_pip_freeze(executable)

        return cls(
            python_version=sys.version,
            platform=platform_mod.platform(),
            key_packages=key_packages,
            full_freeze=full_freeze,
        )

    @provisional(since="0.3.4")
    def reference(self) -> str:
        """Return this snapshot's content address (FR-034).

        The reference is ``env:sha256:<digest>`` over the canonical JSON of
        :meth:`to_dict`, so two captures of an unchanged environment reference
        the same stored snapshot and a captured change produces a new one.
        Records carry this string; :class:`EnvironmentSnapshotStore` holds the
        snapshot itself, once.

        Example:
            >>> snap = EnvironmentSnapshot(python_version="3.11", platform="p")
            >>> snap.reference() == snap.reference()
            True
            >>> snap.reference().startswith("env:sha256:")
            True
        """
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return ENVIRONMENT_REFERENCE_PREFIX + hashlib.sha256(payload.encode("utf-8")).hexdigest()

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


@provisional(since="0.3.4")
class EnvironmentSnapshotStore:
    """A directory of environment snapshots, each stored once (FR-034).

    Snapshots are written as JSON named by :meth:`EnvironmentSnapshot.reference`,
    so a repeated capture of an unchanged environment costs one hash and no
    write. A record that needs to name an environment stores the reference
    string and reads the snapshot back through :meth:`get` when it needs the
    detail.

    The store is a plain content-addressed directory, not a database: writes
    are idempotent, nothing is ever rewritten in place, and a reader that only
    has the reference needs nothing else.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> with tempfile.TemporaryDirectory() as tmp:
        ...     store = EnvironmentSnapshotStore(Path(tmp))
        ...     snap = EnvironmentSnapshot(python_version="3.11", platform="p")
        ...     ref = store.put(snap)
        ...     ref == store.put(snap) and len(store.references()) == 1
        True
    """

    def __init__(self, root: str | Path) -> None:
        """Open (and create) the store rooted at *root*.

        Args:
            root: Directory the snapshots live in. Created on first write.
        """
        self._root = Path(root)

    @property
    def root(self) -> Path:
        """The directory this store writes into."""
        return self._root

    def put(self, snapshot: EnvironmentSnapshot) -> str:
        """Store *snapshot* if this environment is not stored already.

        Args:
            snapshot: The snapshot to store.

        Returns:
            The snapshot's reference, whether it was written now or already
            present. Calling this twice with equal snapshots writes one file.
        """
        reference = snapshot.reference()
        path = self._path_for(reference)
        if path.exists():
            return reference
        self._root.mkdir(parents=True, exist_ok=True)
        # Write through a scratch file in the same directory so a reader never
        # sees a half-written snapshot, and so two processes storing the same
        # environment at once cannot corrupt it.
        scratch = path.with_name(path.name + f".{id(snapshot):x}.tmp")
        scratch.write_text(
            json.dumps(snapshot.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        try:
            scratch.replace(path)
        except OSError:  # another writer won the race; its content is identical
            scratch.unlink(missing_ok=True)
        return reference

    def has(self, reference: str) -> bool:
        """Whether *reference* names a snapshot this store holds."""
        return self._path_for(reference).exists()

    def get(self, reference: str) -> EnvironmentSnapshot:
        """Read back the snapshot *reference* names.

        Args:
            reference: A reference returned by :meth:`put`.

        Returns:
            The stored :class:`EnvironmentSnapshot`.

        Raises:
            KeyError: The store holds no snapshot under that reference.
        """
        path = self._path_for(reference)
        if not path.exists():
            raise KeyError(f"No environment snapshot stored under {reference!r} in {self._root}.")
        return EnvironmentSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def references(self) -> list[str]:
        """Every reference this store holds, sorted."""
        if not self._root.is_dir():
            return []
        return sorted(ENVIRONMENT_REFERENCE_PREFIX + path.stem for path in self._root.glob("*.json"))

    def _path_for(self, reference: str) -> Path:
        """The file *reference* is stored in.

        Raises:
            ValueError: *reference* is not an environment reference. Refusing
                a foreign string here is what keeps the store's filenames from
                becoming an unvalidated path join.
        """
        if not reference.startswith(ENVIRONMENT_REFERENCE_PREFIX):
            raise ValueError(
                f"Not an environment reference: {reference!r} (expected {ENVIRONMENT_REFERENCE_PREFIX}...)."
            )
        digest = reference[len(ENVIRONMENT_REFERENCE_PREFIX) :]
        if len(digest) != 64 or not all(char in "0123456789abcdef" for char in digest):
            raise ValueError(f"Environment reference {reference!r} does not carry a sha256 digest.")
        return self._root / f"{digest}.json"


def _run_pip_freeze(executable: str | None = None) -> str | None:
    """Best-effort full pip freeze. Tries ``uv pip freeze`` then ``pip freeze``.

    Args:
        executable: When given, describe *that* interpreter's environment and
            skip ``uv`` entirely — ``uv pip freeze`` resolves an environment
            from the working directory, which is the wrong answer whenever the
            caller is asking about an interpreter other than the ambient one.

    Returns the captured stdout (text) or ``None`` if both fail. This is
    intentionally non-fatal because the env snapshot is metadata, not a
    correctness requirement.
    """
    # Prefer uv (ADR-038 §5.2) if available — it is significantly faster
    # than `pip freeze` on uv-managed envs.
    uv_bin = shutil.which("uv") if executable is None else None
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

    # Fallback: invoke pip via the named interpreter (this process's own by
    # default) so we capture the active venv even when no `pip` binary is on
    # PATH.
    with contextlib.suppress(Exception):
        result = subprocess.run(  # the interpreter path is the caller's, or ours
            [executable or sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    return None
