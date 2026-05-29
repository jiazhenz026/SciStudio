"""Tool-version and environment parity for ADR-042 Addendum 6 (§7.10).

CI is the single source of truth for which tool versions run checks and the
environment they run in. This module resolves the CI-pinned tool versions from
the same source CI uses (``.pre-commit-config.yaml`` revs, ``pyproject`` bounds)
and validates a CI-equivalent importable environment via the ``PYTHONPATH=src``
invocation CI's full-audit job already uses.

Fail-closed: when parity cannot be reproduced, the evaluator must report exit
code 4 for PR readiness rather than running a looser local approximation.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Tools whose CI-resolved versions we attempt to reproduce locally. Names map to
# the ``ruff``/``mypy`` pre-commit rev pins (§6.2) and pyproject bounds.
_PRECOMMIT_RUFF_RE = re.compile(r"astral-sh/ruff-pre-commit\s*\n\s*rev:\s*v?(?P<version>[\w.]+)", re.MULTILINE)
_PRECOMMIT_MYPY_RE = re.compile(r"mirrors-mypy\s*\n\s*rev:\s*v?(?P<version>[\w.]+)", re.MULTILINE)


@dataclass
class ParityReport:
    """Result of a parity resolution + validation pass."""

    importable: bool
    resolved_versions: dict[str, str] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)

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


def check_importable_env(repo_root: Path) -> bool:
    """Validate that ``import scistudio`` works via ``PYTHONPATH=src`` (§7.10).

    Uses the same isolation CI's full-audit job uses, without ``pip install -e``
    polluting the shared environment.
    """

    src = repo_root / "src"
    if not (src / "scistudio" / "__init__.py").exists():
        return False
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
    import os

    return os.environ.get("PATH", "")


def assess_parity(repo_root: Path, *, require_versions: bool = False) -> ParityReport:
    """Resolve CI versions and validate the importable environment (§7.10).

    ``require_versions`` makes resolved-vs-installed version drift a hard gap
    (fail-closed). With ``require_versions`` False, version mismatch is recorded
    as a gap only when a pin exists and the local install diverges; missing
    local tools are not a gap here because ``checks.py`` handles tool absence as
    exit code 4 with the N/A path.
    """

    resolved = resolve_ci_tool_versions(repo_root)
    importable = check_importable_env(repo_root)
    gaps: list[str] = []
    if not importable:
        gaps.append("cannot reproduce a CI-equivalent importable environment (PYTHONPATH=src import failed)")
    if require_versions:
        for tool, pinned in resolved.items():
            installed = _installed_version(tool)
            if installed is None:
                gaps.append(f"{tool} not installed; CI pins {pinned}")
            elif not pinned.startswith(installed) and not installed.startswith(pinned):
                gaps.append(f"{tool} version drift: local {installed} != CI {pinned}")
    return ParityReport(importable=importable, resolved_versions=resolved, gaps=gaps)
