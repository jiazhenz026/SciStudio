"""Amendment-record lint (ADR-042 §27.5).

Flat script per §27.5 (`scripts/audit/amendment_lint.py` is the
canonical path; Q1B.8.1 manager default).

Validates every Accepted ADR's ``amends:`` frontmatter list:

1. Each ``target`` string resolves under one of the three resolution
   levels described in ADR-042 §27.5:

   * Section-heading match: ``ADR-NNN §X[.Y]`` + any descriptive suffix.
   * Section + sub-element: ``ADR-NNN §X[.Y] (component: <X>)``.
   * Whole-ADR match: ``ADR-NNN`` with no ``§X``.

2. Each amendment list is non-empty when the addendum body modifies any
   parent ADR section. (Phase 1 heuristic: ``amends`` is required when
   the ADR is an addendum — defined as ``title`` containing ``Addendum``
   or ``ADR-NNN-X`` pattern.)

3. No two amendments target the same section with conflicting
   ``replace`` declarations (two `replace` kinds on the same `(target,
   section)` is a contradiction).

4. Cross-ADR amendment chains are allowed (Q1B.8.3); we warn on
   *circular* chains where ``A.amends.target=B`` and ``B.amends.target=A``
   on overlapping sections.

Invocation::

    python -m scripts.audit.amendment_lint --repo-root .
    # or
    python scripts/audit/amendment_lint.py --repo-root .

Exit code is 0 on no findings (or only warnings) and 1 on any error-
severity finding.

References
----------
ADR-042 §27.5 — authoritative amendment-record spec.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

# Allow running as a script: insert the repo's src/ on sys.path so the
# package imports below succeed without `pip install -e .`.
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from scieasy.qa.schemas.frontmatter import (  # noqa: E402  (post-syspath setup)
    Amendment,
    AmendmentKind,
)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(prog="amendment_lint")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: cwd)",
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        type=Path,
        default=None,
        help="Optional ADR markdown files to lint (default: all)",
    )
    args = parser.parse_args(argv)

    findings = lint(args.repo_root, targets=args.targets)
    has_error = False
    for f in findings:
        line = f"{f['severity']:8s} {f['file']}: {f['message']}"
        print(line)
        if f["severity"] == "error":
            has_error = True
    return 1 if has_error else 0


# ---------------------------------------------------------------------------
# Library API
# ---------------------------------------------------------------------------


def lint(repo_root: Path, *, targets: list[Path] | None = None) -> list[dict[str, str]]:
    """Return amendment-lint findings as plain dicts.

    Returns dicts rather than ``Finding`` objects so the script remains
    runnable without pydantic at module import time when used as a flat
    script (mirrors :mod:`scripts.audit.fact_drift` style).
    """
    findings: list[dict[str, str]] = []
    adr_dir = repo_root / "docs" / "adr"
    files = sorted(targets or (adr_dir.glob("ADR-*.md") if adr_dir.is_dir() else []))

    # Pre-parse all frontmatters so cross-ADR target resolution works.
    parsed_by_adr: dict[int, dict[str, Any]] = {}
    headings_by_adr: dict[int, set[str]] = {}
    for path in files:
        fm, headings = _parse_frontmatter_and_headings(path)
        if fm is None:
            continue
        try:
            adr_num = int(fm.get("adr"))
        except (TypeError, ValueError):
            continue
        parsed_by_adr[adr_num] = fm
        headings_by_adr[adr_num] = headings

    seen_replace: dict[str, list[tuple[int, str]]] = defaultdict(list)

    for path in files:
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
        if path not in [Path(p) for p in files]:
            continue
        fm = _parse_frontmatter(path)
        if fm is None:
            continue
        try:
            adr_num = int(fm.get("adr"))
        except (TypeError, ValueError):
            continue

        amends_raw = fm.get("amends") or []
        is_addendum = _looks_like_addendum(fm, path)

        # Validate non-empty when needed.
        if is_addendum and not amends_raw:
            findings.append(
                {
                    "severity": "error",
                    "file": rel,
                    "message": (
                        f"ADR-{adr_num:03d} appears to be an addendum but its "
                        "amends: list is empty (ADR-042 §27.5 requires every "
                        "addendum to declare its amendments)"
                    ),
                }
            )

        # Validate each Amendment row.
        for raw in amends_raw:
            try:
                amend = Amendment.model_validate(raw)
            except (TypeError, ValueError) as exc:
                findings.append(
                    {
                        "severity": "error",
                        "file": rel,
                        "message": f"invalid amends entry: {exc}",
                    }
                )
                continue
            resolved, why = _resolve_target(amend.target, headings_by_adr)
            if not resolved:
                findings.append(
                    {
                        "severity": "error",
                        "file": rel,
                        "message": (
                            f"amendment target '{amend.target}' does not resolve per ADR-042 §27.5 rules ({why})"
                        ),
                    }
                )
                continue
            # Track replace declarations for conflict check below.
            if amend.kind == AmendmentKind.REPLACE:
                key = _normalise_target_key(amend.target)
                seen_replace[key].append((adr_num, rel))

    # Conflict check: two replace amendments on the same target.
    for key, owners in seen_replace.items():
        if len(owners) < 2:
            continue
        owners_desc = ", ".join(f"ADR-{a:03d} ({p})" for a, p in owners)
        findings.append(
            {
                "severity": "error",
                "file": owners[0][1],
                "message": (
                    f"multiple 'replace' amendments target {key}: {owners_desc}. "
                    "ADR-042 §27.5 forbids overlapping replaces"
                ),
            }
        )

    # Circular chain warn — A.amends.target=B AND B.amends.target=A on
    # overlapping section keys (Q1B.8.3 manager default: warn-only).
    findings.extend(_circular_chain_warnings(parsed_by_adr, files, repo_root))

    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(path: Path) -> dict[str, Any] | None:
    """Return the YAML frontmatter mapping at ``path`` or ``None``."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _parse_frontmatter_and_headings(path: Path) -> tuple[dict[str, Any] | None, set[str]]:
    """Parse frontmatter plus collect ``§X.Y`` section numbers from headings."""
    fm = _parse_frontmatter(path)
    if fm is None or not path.is_file():
        return None, set()
    text = path.read_text(encoding="utf-8")
    body = text.split("\n---", 1)
    prose = body[1] if len(body) == 2 else text
    headings: set[str] = set()
    for line in prose.splitlines():
        m = re.match(r"^(#{1,6})\s+(\d+(?:\.\d+)*)", line)
        if m:
            headings.add(m.group(2))
    return fm, headings


def _looks_like_addendum(fm: dict[str, Any], path: Path) -> bool:
    """Heuristic: title contains 'Addendum' OR filename matches ``ADR-NNN-X.md``."""
    title = str(fm.get("title", ""))
    if "addendum" in title.lower():
        return True
    return bool(re.match(r"^ADR-\d{1,4}-[A-Z]\.md$", path.name))


def _resolve_target(target: str, headings_by_adr: dict[int, set[str]]) -> tuple[bool, str]:
    """Return ``(resolved, reason)`` for an amendment target string."""
    # Level 3: whole-ADR.
    whole = re.fullmatch(r"ADR-(\d{1,4})", target.strip())
    if whole:
        adr_num = int(whole.group(1))
        if adr_num in headings_by_adr:
            return True, ""
        return False, f"no parsed ADR-{adr_num:03d} found in scan set"

    # Levels 1 + 2: ``ADR-NNN §X[.Y]`` prefix.
    m = re.match(r"^ADR-(\d{1,4})\s+§(\d+(?:\.\d+)*)", target)
    if not m:
        return False, "target does not start with 'ADR-NNN §X[.Y]' or 'ADR-NNN'"
    adr_num = int(m.group(1))
    sec_num = m.group(2)
    if adr_num not in headings_by_adr:
        return False, f"no parsed ADR-{adr_num:03d} found in scan set"
    if sec_num not in headings_by_adr[adr_num]:
        return False, f"§{sec_num} not a heading in ADR-{adr_num:03d}"
    # Level 2 sub-element check: trailing `(component: ...)` is acceptable.
    tail = target[m.end() :].strip()
    if tail and not re.match(r"^[A-Za-z][A-Za-z0-9 .,'\"-]*$", tail) and "(component" not in tail.lower():
        return False, "trailing text after section number not recognised as descriptive or component-tag"
    return True, ""


def _normalise_target_key(target: str) -> str:
    """Reduce a target string to its `(adr, section)` shape for comparison."""
    m = re.match(r"^(ADR-\d{1,4}(?:\s+§\d+(?:\.\d+)*)?)", target)
    return m.group(1) if m else target.strip()


def _circular_chain_warnings(
    parsed_by_adr: dict[int, dict[str, Any]],
    files: list[Path],
    repo_root: Path,
) -> list[dict[str, str]]:
    """Detect A→B→A target chains."""
    _ = files, repo_root
    targets_by_adr: dict[int, set[str]] = {}
    for adr_num, fm in parsed_by_adr.items():
        amends = fm.get("amends") or []
        keys: set[str] = set()
        for raw in amends:
            if isinstance(raw, dict) and "target" in raw:
                keys.add(_normalise_target_key(str(raw["target"])))
        targets_by_adr[adr_num] = keys

    findings: list[dict[str, str]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for a, keys_a in targets_by_adr.items():
        for key in keys_a:
            m = re.match(r"^ADR-(\d{1,4})", key)
            if not m:
                continue
            b = int(m.group(1))
            if b == a or b not in targets_by_adr:
                continue
            keys_b = targets_by_adr[b]
            for back_key in keys_b:
                bm = re.match(r"^ADR-(\d{1,4})", back_key)
                if bm and int(bm.group(1)) == a:
                    pair = tuple(sorted([a, b]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    findings.append(
                        {
                            "severity": "warning",
                            "file": f"docs/adr/ADR-{a:03d}.md",
                            "message": (
                                f"circular amendment chain: ADR-{a:03d} amends "
                                f"ADR-{b:03d} which amends ADR-{a:03d}. "
                                "Cross-ADR amendment chains are allowed (Q1B.8.3) "
                                "but circular references warrant review."
                            ),
                        }
                    )
    return findings


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
