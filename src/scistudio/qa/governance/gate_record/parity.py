"""Tool-version and environment parity for ADR-042 Addendum 6 (§7.10).

CI is the single source of truth for which tool versions run checks and the
environment they run in. This module resolves the CI-pinned tool versions from
the same source CI uses (``.pre-commit-config.yaml`` revs, ``pyproject`` bounds)
and provisions an ISOLATED per-worktree virtual environment that installs the
same CI-equivalent dependencies (``-e ".[dev]"``) so local checks run the same
commands CI runs, in an equivalent environment, without polluting the shared
environment.

§7.10 mechanism (owner-authorized): each worktree gets its own gitignored venv
under ``<worktree>/.workflow/local/venv``. AGENTS.md forbids ``pip install -e .``
because it pollutes the SHARED environment; an isolated per-worktree venv is the
sanctioned way to reproduce the CI environment. ``uv`` is used when available
(``uv venv`` + ``uv pip install``); otherwise ``python -m venv`` + ``pip``.

Provisioning is cached by a marker hash of the ``[dev]`` extras, the resolved
tool pins, and the Python version: a warm venv re-provisions only when that
marker changes. Provisioning runs only for LOCAL preflight modes; ``--mode ci``
never provisions (CI owns its own matrix environment).

Fail-closed: when the venv cannot be created or the install fails (no network,
uv/pip error), the evaluator reports exit code 4 for PR readiness rather than
running a looser local approximation.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Tools whose CI-resolved versions we attempt to reproduce locally. Names map to
# the ``ruff``/``mypy`` pre-commit rev pins (§6.2) and pyproject bounds.
_PRECOMMIT_RUFF_RE = re.compile(r"astral-sh/ruff-pre-commit\s*\n\s*rev:\s*v?(?P<version>[\w.]+)", re.MULTILINE)
_PRECOMMIT_MYPY_RE = re.compile(r"mirrors-mypy\s*\n\s*rev:\s*v?(?P<version>[\w.]+)", re.MULTILINE)

# Per-worktree isolated environment lives under the gitignored local logs root
# (``.workflow/local/**``), so it is never committed or pushed (§7.2, §8).
VENV_DIR = ".workflow/local/venv"
# Marker file recording the provisioning fingerprint; a hit means "warm".
_MARKER_NAME = ".scistudio-parity-marker"

# Modes that run the CI-equivalent quality checks locally and therefore need a
# provisioned environment. ``ci`` is intentionally absent: ci.yml owns its own
# matrix and environment, so CI mode never provisions (§7.10 CRITICAL).
PROVISION_MODES: frozenset[str] = frozenset({"local", "pre-commit", "pre-push", "pre-pr"})


@dataclass
class ParityReport:
    """Result of a parity resolution + provisioning/validation pass."""

    importable: bool
    resolved_versions: dict[str, str] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    # Absolute path to the provisioned venv when provisioning succeeded; None
    # when provisioning was not attempted or failed.
    venv_path: Path | None = None
    provisioned: bool = False

    @property
    def ok(self) -> bool:
        return self.importable and not self.gaps


def resolve_ci_tool_versions(repo_root: Path) -> dict[str, str]:
    """Read CI-pinned tool versions from the source CI uses (§7.10).

    Returns a best-effort mapping. Tools CI resolves at ``latest`` (unpinned)
    are intentionally absent; per §7.10 local resolves the same latest at run
    time, which is an accepted small drift window.
    """

    versions: dict[str, str] = {}
    precommit = repo_root / ".pre-commit-config.yaml"
    if precommit.exists():
        text = precommit.read_text(encoding="utf-8", errors="replace")
        ruff_match = _PRECOMMIT_RUFF_RE.search(text)
        if ruff_match:
            versions["ruff"] = ruff_match.group("version")
        mypy_match = _PRECOMMIT_MYPY_RE.search(text)
        if mypy_match:
            versions["mypy"] = mypy_match.group("version")
    return versions


def _installed_version(tool: str) -> str | None:
    if shutil.which(tool) is None:
        return None
    try:
        out = subprocess.check_output(
            [tool, "--version"],
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.STDOUT,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", out)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Isolated per-worktree venv provisioning (§7.10).
# ---------------------------------------------------------------------------


def venv_path(repo_root: Path) -> Path:
    """Return the absolute per-worktree venv path (gitignored, §7.10)."""

    return repo_root / VENV_DIR


def _venv_bin_dir(venv: Path) -> Path:
    """Resolve the venv's executable directory cross-platform (§7.10).

    Windows uses ``<venv>/Scripts``; POSIX uses ``<venv>/bin``. The owner runs
    Windows, so this must be correct on both.
    """

    scripts = venv / "Scripts"
    if scripts.exists() or os.name == "nt":
        return scripts
    return venv / "bin"


def _venv_exe(venv: Path, name: str) -> Path:
    """Resolve a single executable inside the venv cross-platform.

    On Windows tries ``<name>.exe`` then ``<name>.cmd`` (npm-style shims) then
    the bare name; on POSIX returns ``<bin>/<name>``.
    """

    bin_dir = _venv_bin_dir(venv)
    if os.name == "nt":
        for suffix in (".exe", ".cmd", ".bat", ""):
            candidate = bin_dir / f"{name}{suffix}"
            if candidate.exists():
                return candidate
        return bin_dir / f"{name}.exe"
    return bin_dir / name


def venv_python(venv: Path) -> Path:
    """Return the venv interpreter path cross-platform (§7.10)."""

    bin_dir = _venv_bin_dir(venv)
    return bin_dir / ("python.exe" if os.name == "nt" else "python")


def resolve_venv_executable(repo_root: Path, name: str) -> Path | None:
    """Return the venv's executable for ``name`` when the venv exists (§7.10).

    Returns ``None`` when the venv has not been provisioned or the executable is
    absent, so callers fall back to the ambient tool only when no parity env
    exists. ``python`` always resolves to the venv interpreter when present.
    """

    venv = venv_path(repo_root)
    if not venv.exists():
        return None
    candidate = venv_python(venv) if name == "python" else _venv_exe(venv, name)
    return candidate if candidate.exists() else None


def _dev_extras(repo_root: Path) -> list[str]:
    """Read the ``[project.optional-dependencies].dev`` list from pyproject.

    Returns the raw requirement strings so the marker hash tracks the exact CI
    dev-extras set. Falls back to an empty list when pyproject is unreadable;
    the marker still includes the install spec and python version.
    """

    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return []
    try:
        import tomllib  # stdlib on the repo's >=3.11 baseline

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    optional = data.get("project", {}).get("optional-dependencies", {})
    dev = optional.get("dev", [])
    return [str(item) for item in dev] if isinstance(dev, list) else []


def provisioning_marker(repo_root: Path) -> str:
    """Compute the cache marker for the parity env (§7.10).

    The marker is a hash of the ``[dev]`` extras, the resolved CI tool pins, and
    the local Python (major.minor + implementation). Re-provision only when the
    marker changes; a warm venv with a matching marker is reused as-is.
    """

    parts = [
        "scistudio-parity-v1",
        f"python={sys.version_info.major}.{sys.version_info.minor}",
        f"impl={sys.implementation.name}",
        "deps=" + "\x1f".join(sorted(_dev_extras(repo_root))),
        "pins=" + "\x1f".join(f"{k}={v}" for k, v in sorted(resolve_ci_tool_versions(repo_root).items())),
        "spec=-e .[dev]",
    ]
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _read_marker(venv: Path) -> str | None:
    marker = venv / _MARKER_NAME
    if not marker.exists():
        return None
    try:
        return marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _uv_available() -> bool:
    return shutil.which("uv") is not None


# Strip local-machine detail (absolute paths, home/venv refs) from any error
# tail before it becomes a gap message. Mirrors io.sanitize_ledger so a parity
# gap never carries an absolute path into committed ledger events (§8).
_LEAK_RE = re.compile(
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]\S*)"  # Windows drive path
    r"|(?:/(?:home|Users|root|tmp|var|mnt)/\S*)"  # POSIX system paths
    r"|(?:~/\S*)|(?:\$HOME\S*)|(?:%USERPROFILE%\S*)"  # home refs
    r"|(?:\S*(?:site-packages|\.venv|virtualenvs)\S*)"  # venv/dep-cache paths
)


def _sanitize_hint(text: str) -> str:
    """Replace any local-path/home/venv token in an error hint with ``<path>``."""

    return _LEAK_RE.sub("<path>", text).strip() or "see local logs"


def _basename(tool_path: str) -> str:
    """Return a tool's bare name (never an absolute path) for gap messages."""

    return Path(tool_path).name


def _run(cmd: list[str], *, cwd: Path, timeout: int = 600) -> tuple[bool, str]:
    """Run a provisioning subprocess; return ``(ok, sanitized_summary)``.

    Raw output stays local-only by design — we return only a short, SANITIZED
    class of the error (never stdout/stderr transcripts, never absolute paths)
    so nothing local-machine-specific leaks into the ledger or console (§8).
    """

    tool = _basename(cmd[0])
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout running {tool}"
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"{type(exc).__name__} running {tool}"
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        hint = _sanitize_hint(tail[-1]) if tail else f"exit {completed.returncode}"
        return False, f"{tool} failed: {hint}"
    return True, "ok"


def _create_venv(repo_root: Path, venv: Path) -> tuple[bool, str]:
    """Create the venv with uv (preferred) or the stdlib venv module."""

    if _uv_available():
        return _run(
            ["uv", "venv", str(venv), "--python", f"{sys.version_info.major}.{sys.version_info.minor}"],
            cwd=repo_root,
        )
    return _run([sys.executable, "-m", "venv", str(venv)], cwd=repo_root)


def _install_deps(repo_root: Path, venv: Path) -> tuple[bool, str]:
    """Install ``-e ".[dev]"`` into the venv with uv (preferred) or pip.

    ``uv pip install --python <venv-python>`` targets the isolated env; the
    stdlib path uses the venv's own pip. The editable install makes ``scistudio``
    importable inside the venv (so mypy/pytest resolve it without PYTHONPATH).
    """

    py = venv_python(venv)
    if _uv_available():
        return _run(["uv", "pip", "install", "--python", str(py), "-e", ".[dev]"], cwd=repo_root)
    ok, summary = _run([str(py), "-m", "pip", "install", "--upgrade", "pip"], cwd=repo_root)
    if not ok:
        return ok, summary
    return _run([str(py), "-m", "pip", "install", "-e", ".[dev]"], cwd=repo_root)


def provision_venv(repo_root: Path, *, force: bool = False) -> ParityReport:
    """Ensure an isolated per-worktree venv with CI-equivalent deps (§7.10).

    Idempotent: when the venv exists and its marker matches the current
    ``provisioning_marker``, it is reused untouched (warm => near-instant).
    Otherwise it is (re)created and ``-e ".[dev]"`` is installed, then the marker
    is written. On any failure the report carries a fail-closed gap and
    ``provisioned`` stays False.
    """

    resolved = resolve_ci_tool_versions(repo_root)
    venv = venv_path(repo_root)
    marker = provisioning_marker(repo_root)

    if not force and venv.exists() and _read_marker(venv) == marker:
        importable = check_importable_env(repo_root, venv=venv)
        gaps = [] if importable else ["isolated venv exists but cannot import scistudio; remove the venv and re-run"]
        return ParityReport(
            importable=importable,
            resolved_versions=resolved,
            gaps=gaps,
            venv_path=venv if importable else None,
            provisioned=importable,
        )

    venv.parent.mkdir(parents=True, exist_ok=True)
    created, create_summary = _create_venv(repo_root, venv)
    if not created:
        return ParityReport(
            importable=False,
            resolved_versions=resolved,
            gaps=[f"cannot create isolated per-worktree venv: {create_summary}"],
        )
    installed, install_summary = _install_deps(repo_root, venv)
    if not installed:
        return ParityReport(
            importable=False,
            resolved_versions=resolved,
            gaps=[f"cannot install CI-equivalent deps into isolated venv: {install_summary}"],
        )
    importable = check_importable_env(repo_root, venv=venv)
    if not importable:
        return ParityReport(
            importable=False,
            resolved_versions=resolved,
            gaps=["provisioned venv cannot import scistudio (install incomplete)"],
        )
    try:
        (venv / _MARKER_NAME).write_text(marker + "\n", encoding="utf-8")
    except OSError as exc:
        return ParityReport(
            importable=True,
            resolved_versions=resolved,
            gaps=[f"venv provisioned but could not write cache marker: {type(exc).__name__}"],
            venv_path=venv,
            provisioned=True,
        )
    return ParityReport(
        importable=True,
        resolved_versions=resolved,
        gaps=[],
        venv_path=venv,
        provisioned=True,
    )


def check_importable_env(repo_root: Path, *, venv: Path | None = None) -> bool:
    """Validate that ``import scistudio`` works in the parity env (§7.10).

    With a provisioned ``venv`` the venv interpreter is used (the editable
    install makes ``scistudio`` importable directly). Without a venv it falls
    back to the ``PYTHONPATH=src`` invocation CI's full-audit job already uses,
    without ``pip install -e`` polluting the shared environment.
    """

    src = repo_root / "src"
    if not (src / "scistudio" / "__init__.py").exists():
        return False

    if venv is not None:
        py = venv_python(venv)
        if not py.exists():
            return False
        try:
            result = subprocess.run(
                [str(py), "-c", "import scistudio"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except (subprocess.SubprocessError, OSError):
            return False
        return result.returncode == 0

    env_pythonpath = str(src)
    try:
        result = subprocess.run(
            ["python", "-c", "import scistudio"],
            cwd=repo_root,
            env={"PYTHONPATH": env_pythonpath, "PATH": _path_env()},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0


def _path_env() -> str:
    return os.environ.get("PATH", "")


def assess_parity(
    repo_root: Path,
    *,
    require_versions: bool = False,
    mode: str | None = None,
    provision: bool = True,
) -> ParityReport:
    """Resolve CI versions and ensure a CI-equivalent environment (§7.10).

    For LOCAL preflight modes (``local``/``pre-commit``/``pre-push``/``pre-pr``)
    this AUTO-PROVISIONS the isolated per-worktree venv with CI-equivalent deps
    and validates importability inside it. For ``ci`` mode (or when ``provision``
    is False) it does NOT provision — CI owns its own matrix environment — and
    only validates the ``PYTHONPATH=src`` importable fallback.

    ``require_versions`` makes resolved-vs-installed version drift a hard gap
    (fail-closed). Missing local tools are not a gap here because the venv
    install carries them; ``checks.py`` still records tool absence as skipped.
    """

    # Escape hatch: ``SCISTUDIO_GATE_NO_PROVISION=1`` disables real venv creation
    # (used by CI and by the self-hosting test that runs the CLI as a real
    # subprocess where a real network install must not happen). When set, fall
    # back to the PYTHONPATH=src importable validation only.
    no_provision = os.environ.get("SCISTUDIO_GATE_NO_PROVISION", "").strip() in ("1", "true", "yes")
    should_provision = provision and not no_provision and (mode is None or mode in PROVISION_MODES)
    if should_provision:
        report = provision_venv(repo_root)
        resolved = report.resolved_versions
    else:
        resolved = resolve_ci_tool_versions(repo_root)
        importable = check_importable_env(repo_root)
        gaps: list[str] = []
        if not importable:
            gaps.append("cannot reproduce a CI-equivalent importable environment (PYTHONPATH=src import failed)")
        report = ParityReport(importable=importable, resolved_versions=resolved, gaps=gaps)

    if require_versions:
        for tool, pinned in resolved.items():
            installed = _installed_version(tool)
            if installed is None:
                report.gaps.append(f"{tool} not installed; CI pins {pinned}")
            elif not pinned.startswith(installed) and not installed.startswith(pinned):
                report.gaps.append(f"{tool} version drift: local {installed} != CI {pinned}")
    return report
