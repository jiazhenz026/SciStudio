"""Extract tool facts from ``pyproject.toml`` + ``.pre-commit-config.yaml`` (ADR-042 §7.5.3).

Produces a :class:`scieasy.qa.schemas.facts.ToolFacts` instance with:

- ``python_version``: from ``[tool.mypy] python_version`` (canonical pin).
- ``min_coverage_percent``: from ``--cov-fail-under=N`` in ``[tool.pytest.ini_options].addopts``.
- ``lint_rules``: from ``[tool.ruff.lint] select`` (the active rule prefixes).
- ``type_checkers``: from ``.pre-commit-config.yaml`` hook ids that look like
  type checkers (``mypy``, ``pyright``, ``pyre`` — matched on stem).
- ``docs_engine``: hard-pinned to ``"sphinx"`` per ADR-042 §22 / ADR-044 §10.
  (No alternative docs engine is in scope for the cascade.)

This is a stdlib + pyyaml read; we deliberately avoid importing TOML libraries
directly via ``tomllib`` is stdlib on Python 3.11+ which is the repo floor.

Reads
-----
``pyproject.toml`` — repo root.
``.pre-commit-config.yaml`` — repo root.

References
----------
ADR-042 §7.5.3 — generation table (tool namespace row).
ADR-042 §22 / ADR-044 §10 — Sphinx as the canonical docs engine.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa.schemas.facts import ToolFacts

_TYPE_CHECKER_STEMS = ("mypy", "pyright", "pyre")
_COV_RE = re.compile(r"--cov-fail-under=(\d+)")


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("could not locate repo root from extract_tool_facts.py")


def _parse_pyproject(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)
    return data


def extract(
    pyproject_path: Path | None = None,
    pre_commit_path: Path | None = None,
) -> ToolFacts:
    """Read tool configuration files and return a :class:`ToolFacts` instance.

    Args:
        pyproject_path: Optional explicit path to ``pyproject.toml``.
        pre_commit_path: Optional explicit path to ``.pre-commit-config.yaml``.

    Raises:
        FileNotFoundError: If ``pyproject.toml`` is absent.
        ValueError: If the required substructures are missing.
    """
    root = _find_repo_root()
    pyproject_path = pyproject_path or (root / "pyproject.toml")
    pre_commit_path = pre_commit_path or (root / ".pre-commit-config.yaml")

    if not pyproject_path.is_file():
        raise FileNotFoundError(f"pyproject.toml not found: {pyproject_path}")

    py = _parse_pyproject(pyproject_path)
    tool = py.get("tool") or {}
    mypy_cfg = tool.get("mypy") or {}
    python_version_obj = mypy_cfg.get("python_version") or py.get("project", {}).get("requires-python", "")
    python_version = str(python_version_obj).lstrip(">=")
    if not python_version:
        raise ValueError("could not derive python_version from pyproject.toml")

    pytest_cfg = tool.get("pytest", {}).get("ini_options") or {}
    addopts = pytest_cfg.get("addopts") or ""
    if isinstance(addopts, list):
        addopts = " ".join(str(item) for item in addopts)
    match = _COV_RE.search(str(addopts))
    min_coverage = int(match.group(1)) if match else 0

    ruff_lint = tool.get("ruff", {}).get("lint") or {}
    lint_rules = [str(r) for r in (ruff_lint.get("select") or [])]

    type_checkers: list[str] = []
    if pre_commit_path.is_file():
        pc = yaml.safe_load(pre_commit_path.read_text(encoding="utf-8")) or {}
        for repo in pc.get("repos") or []:
            for hook in (repo or {}).get("hooks") or []:
                hook_id = (hook or {}).get("id")
                if not isinstance(hook_id, str):
                    continue
                stem = hook_id.lower()
                for tc in _TYPE_CHECKER_STEMS:
                    if tc in stem and tc not in type_checkers:
                        type_checkers.append(tc)
    # Fall back to mypy presence in pyproject if no pre-commit hook matched.
    if not type_checkers and mypy_cfg:
        type_checkers.append("mypy")

    return ToolFacts(
        python_version=python_version,
        min_coverage_percent=min_coverage,
        lint_rules=lint_rules,
        type_checkers=type_checkers,
        docs_engine="sphinx",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints a JSON dump of the tool facts to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyproject", type=Path, default=None)
    parser.add_argument("--pre-commit", type=Path, default=None)
    args = parser.parse_args(argv)
    facts = extract(args.pyproject, args.pre_commit)
    print(json.dumps(facts.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
