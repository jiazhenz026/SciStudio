"""Dynamic governance-path filter for the §3.5 recursive workflow.

Audit fix iter-7 ITER-FRESH-002 (ADR-043 §3.5 lines 737-749). The
``.github/workflows/governance-modification.yml`` file used to carry a
hand-maintained ``paths:`` list under ``on.pull_request``. That list
drifted from ``.governance-paths.yaml`` (covered only ~12 of ~30
governance paths, leaving CURSOR.md / GEMINI.md / .aiderrc / per-
subtree AGENTS.md / audit logs / codemods / agent prompts
unprotected).

This module replaces the static YAML list with a *runtime* filter: at
the start of the workflow we compare the PR diff against
``.governance-paths.yaml`` and emit a ``touched=true|false`` line into
``$GITHUB_OUTPUT``. Every subsequent step gates on that variable.

Entry-point (ADR-043 §4.7 audit fix F14)::

    filter(paths_yaml: Path, base: str, head: str, output: Path) -> bool

The function returns ``True`` iff at least one governance path is
modified between ``base`` and ``head``. The boolean is also surfaced as
``touched=true|false`` in the file referenced by ``output`` (the
workflow passes ``$GITHUB_OUTPUT`` here).

References
----------
ADR-043 §3.5 lines 737-749 — workflow integration.
ADR-043 §4.7 line 1238-1245 — entry-point signature.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Re-use mod_guard's path matcher so LOCAL hooks, CI verifier, AND the
# §3.5 workflow agree on governance-path membership byte-for-byte.
from .mod_guard import _glob_match, _load_governance_globs


def _changed_files(repo_root: Path, base: str, head: str) -> list[str]:
    """Return repo-relative POSIX paths changed between ``base`` and ``head``."""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}..{head}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if out.returncode != 0:
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def filter(
    paths_yaml: Path,
    base: str,
    head: str,
    output: Path,
    *,
    repo_root: Path | None = None,
) -> bool:
    """Compare ``base..head`` diff against ``paths_yaml`` and emit ``touched=…``.

    Parameters
    ----------
    paths_yaml:
        Path to ``.governance-paths.yaml`` (used to read governance
        globs). May be a relative path; resolved against ``repo_root``.
    base, head:
        Git refs (commit SHAs or branch names).
    output:
        File to *append* ``touched=true`` or ``touched=false`` to. The
        workflow passes ``$GITHUB_OUTPUT`` here; the file must be
        appended (GitHub Actions accumulates step outputs).
    repo_root:
        Repository root. Defaults to the parent of ``paths_yaml``.

    Returns
    -------
    bool
        ``True`` iff any governance path is touched.
    """
    paths_yaml = paths_yaml.resolve()
    repo_root = (repo_root or paths_yaml.parent).resolve()

    globs = _load_governance_globs(repo_root)
    changed = _changed_files(repo_root, base, head)
    touched = any(_glob_match(p, globs) for p in changed) if globs else False

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as fh:
        fh.write(f"touched={'true' if touched else 'false'}\n")
    return touched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.path_filter",
        description="Dynamic governance-path filter for the §3.5 workflow (ADR-043).",
    )
    parser.add_argument("--paths-yaml", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument(
        "--output",
        required=True,
        help="File to append `touched=true|false` to ($GITHUB_OUTPUT).",
    )
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    paths_yaml = Path(args.paths_yaml)
    repo_root = Path(args.repo_root or Path.cwd()).resolve()
    if not paths_yaml.is_absolute():
        paths_yaml = repo_root / paths_yaml
    if not paths_yaml.is_file():
        print(f"path_filter/paths-yaml-missing: {paths_yaml}", file=sys.stderr)
        return 2

    filter(paths_yaml, args.base, args.head, Path(args.output), repo_root=repo_root)
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
