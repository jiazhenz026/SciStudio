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
from .mod_guard import _glob_match


class _DiffUnavailableError(RuntimeError):
    """Raised when ``git diff`` fails — distinct from "diff returned empty".

    Per Codex P1 review (PR #1166): the workflow must fail closed in this
    case, not silently report ``touched=false`` (which would skip every
    governance check on a genuinely-failed diff computation).
    """


def _load_globs_from(paths_yaml: Path) -> list[str]:
    """Read ``governance_paths`` directly from the caller-supplied YAML.

    Per Codex P2 review (PR #1166): the previous implementation read from
    ``repo_root/.governance-paths.yaml`` regardless of ``paths_yaml``,
    silently evaluating the wrong file when a caller passed a non-default
    path. This helper honours the caller-provided file.

    Returns ``[]`` if the file is missing, malformed, or has no
    ``governance_paths`` key — the caller treats no-globs as the same
    fail-open mode an empty registry would (we will still fail-closed on
    *diff errors* in ``_changed_files``; that's a separate axis).
    """
    import yaml

    if not paths_yaml.is_file():
        return []
    try:
        raw = yaml.safe_load(paths_yaml.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    return list(raw.get("governance_paths") or [])


def _changed_files(repo_root: Path, base: str, head: str) -> list[str]:
    """Return repo-relative POSIX paths changed between ``base`` and ``head``.

    Raises :class:`_DiffUnavailableError` if the diff cannot be computed (git
    missing, non-zero exit, etc.). The caller MUST translate this into
    ``touched=true`` (fail-closed) per Codex P1 review.
    """
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}..{head}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise _DiffUnavailableError(f"git executable not found: {exc}") from exc
    if out.returncode != 0:
        stderr_tail = (out.stderr or "")[:200].strip()
        raise _DiffUnavailableError(f"git diff {base}..{head} exited {out.returncode}: {stderr_tail}")
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

    Behaviour notes (Codex P1/P2 review fixes, PR #1166):
      * **Fail-closed on diff errors**: if ``git diff`` can't run or
        returns a non-zero exit code, we treat the PR as *touching*
        governance (touched=true) so the workflow's downstream guard
        steps still run. The alternative (silent touched=false) would
        bypass enforcement whenever the diff computation breaks, which
        is exactly the failure mode a hostile commit could exploit.
      * **paths_yaml is honoured**: governance globs are loaded from
        the caller-supplied YAML file, not from a hard-coded location
        under ``repo_root``.

    Returns
    -------
    bool
        ``True`` iff any governance path is touched, OR the diff
        computation failed (fail-closed).
    """
    paths_yaml = paths_yaml.resolve()
    repo_root = (repo_root or paths_yaml.parent).resolve()

    globs = _load_globs_from(paths_yaml)
    try:
        changed = _changed_files(repo_root, base, head)
    except _DiffUnavailableError as exc:
        # Fail closed: surface the error reason in the output file so the
        # workflow log makes the bypass-attempt visible.
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8") as fh:
            fh.write("touched=true\n")
            fh.write(f"path_filter_error={exc!s}\n")
        return True

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
