"""Dynamic governance-path filter (ADR-043 §3.5 + audit fix iter-7 ITER-FRESH-002).

The §3.5 recursive-self-validation workflow needs to decide whether the
current PR touches any of the ~30 governance paths enumerated in
``.governance-paths.yaml``. Hand-maintaining a YAML ``paths:`` list on
the workflow trigger creates a shadow registry that drifts (audit fix
C2 in ADR-043 §3.5) — this module loads the registry **at runtime**
and matches the PR diff against it.

Entry-point (ADR-043 §4.7 audit fix F14)::

    filter(paths_yaml: Path, base: str, head: str, output: Path) -> bool

CLI contract — invoked by the workflow's
``Determine governance-path matches`` step::

    python -m scieasy.qa.governance.path_filter \\
        --paths-yaml .governance-paths.yaml \\
        --base <base-sha> \\
        --head <head-sha> \\
        --output "$GITHUB_OUTPUT"

The CLI writes one line to ``$GITHUB_OUTPUT`` in the
``touched=true|false`` form. Returns exit code 0 in both cases; the
boolean is consumed downstream by ``if: steps.gov_paths.outputs.touched
== 'true'`` step gating.

References
----------
ADR-043 §3.5 (lines 722-782) — authoritative spec.
ADR-043 §4.7 line 1241 — entry-point signature.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

import yaml

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _git_diff_names(repo_root: Path, base: str, head: str) -> list[str]:
    """Return list of files changed between two refs (best-effort)."""
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
    return [ln.strip().replace("\\", "/") for ln in out.stdout.splitlines() if ln.strip()]


def _load_governance_globs(paths_yaml: Path) -> list[str]:
    """Return the ``governance_paths`` glob list from the YAML registry.

    Honeypot canary entries (``honeypot_canaries:``) are intentionally
    *not* part of the filter — they are covered by the dedicated
    ``honeypot_check`` step in the §3.5 workflow.
    """
    try:
        raw = yaml.safe_load(paths_yaml.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    entries = raw.get("governance_paths") or []
    return [g for g in entries if isinstance(g, str)]


def _matches_any(path: str, globs: list[str]) -> bool:
    """Return True when ``path`` matches any glob (``**`` aware)."""
    norm = path.replace("\\", "/")
    for g in globs:
        gn = g.replace("\\", "/")
        if _matches(norm, gn):
            return True
    return False


def _matches(path: str, glob: str) -> bool:
    """Match ``path`` against a glob with ``**`` semantics.

    Implementation strategy: split the glob on ``/`` and walk component
    by component. ``**`` matches any number of components (including
    zero) — the rest of the glob is then matched against the
    remaining suffix.
    """
    p_parts = path.split("/")
    g_parts = glob.split("/")

    def _walk(pi: int, gi: int) -> bool:
        # Both consumed → match
        if gi == len(g_parts) and pi == len(p_parts):
            return True
        # Glob exhausted but path remains
        if gi == len(g_parts):
            return False
        token = g_parts[gi]
        if token == "**":
            # ``**`` is at end → match anything
            if gi + 1 == len(g_parts):
                return True
            # Try matching zero or more path components
            return any(_walk(j, gi + 1) for j in range(pi, len(p_parts) + 1))
        if pi == len(p_parts):
            return False
        if fnmatch.fnmatchcase(p_parts[pi], token):
            return _walk(pi + 1, gi + 1)
        return False

    return _walk(0, 0)


# --------------------------------------------------------------------------- #
# Public entry-point                                                          #
# --------------------------------------------------------------------------- #


def filter(
    paths_yaml: Path,
    base: str,
    head: str,
    output: Path,
    *,
    repo_root: Path | None = None,
) -> bool:
    """Match the PR diff against ``.governance-paths.yaml`` entries.

    Side-effects:
        Appends ``touched=true`` or ``touched=false`` to ``output``
        (typically ``$GITHUB_OUTPUT``).

    Returns:
        ``True`` iff at least one governance path is modified between
        ``base`` and ``head``.
    """
    root = (repo_root or paths_yaml.parent if paths_yaml.is_file() else Path.cwd()).resolve()
    globs = _load_governance_globs(paths_yaml)
    if not globs:
        _emit(output, touched=False, matched=[])
        return False
    changed = _git_diff_names(root, base, head)
    matched = sorted({f for f in changed if _matches_any(f, globs)})
    touched = bool(matched)
    _emit(output, touched=touched, matched=matched)
    return touched


def _emit(output: Path, *, touched: bool, matched: list[str]) -> None:
    """Append GITHUB_OUTPUT-format lines to ``output``."""
    lines = [f"touched={'true' if touched else 'false'}\n"]
    if matched:
        # Multi-line outputs use the ``name<<EOF\n...\nEOF`` heredoc syntax.
        lines.append("matched<<EOF_GOV\n")
        for f in matched:
            lines.append(f + "\n")
        lines.append("EOF_GOV\n")
    try:
        with output.open("a", encoding="utf-8") as fh:
            fh.writelines(lines)
    except OSError:
        # Fall back to stdout when $GITHUB_OUTPUT is unwritable (e.g. in
        # local invocation without a real Actions runner).
        sys.stdout.writelines(lines)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.path_filter",
        description="Dynamic governance-path filter (ADR-043 §3.5).",
    )
    parser.add_argument(
        "--paths-yaml",
        default=".governance-paths.yaml",
        help="Path to .governance-paths.yaml (default: ./.governance-paths.yaml).",
    )
    parser.add_argument("--base", required=True, help="Base git ref / SHA.")
    parser.add_argument("--head", required=True, help="Head git ref / SHA.")
    parser.add_argument(
        "--output",
        required=True,
        help="Path to append GITHUB_OUTPUT-format lines (typically $GITHUB_OUTPUT).",
    )
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    root = Path(args.repo_root or Path.cwd()).resolve()
    paths_yaml = Path(args.paths_yaml)
    if not paths_yaml.is_absolute():
        paths_yaml = root / paths_yaml
    output = Path(args.output)

    if not paths_yaml.is_file():
        # No registry → workflow should treat as "no governance paths
        # touched" rather than crash. Still emit touched=false so the
        # downstream ``if:`` evaluates cleanly.
        _emit(output, touched=False, matched=[])
        print(f"path_filter: paths-yaml missing: {paths_yaml}", file=sys.stderr)
        return 0

    filter(paths_yaml, args.base, args.head, output, repo_root=root)
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
