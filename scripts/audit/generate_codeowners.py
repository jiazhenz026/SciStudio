"""Generate ``.github/CODEOWNERS`` from ``.governance-paths.yaml`` (ADR-043 §3.2).

CODEOWNERS is the GitHub platform-level enforcement layer that no agent
can bypass: branch protection on ``main`` configures "require review
from Code Owners for governance paths" (ADR-043 §3.2 lines 573-575).

This generator is the canonical source of the governance section of
``.github/CODEOWNERS``. The existing default-owner section above the
auto-generated block is preserved verbatim on every re-run, so manual
non-governance owner rules survive regeneration.

Idempotency contract
--------------------
Running this script twice in a row on a clean repo produces a
byte-identical file (the test suite asserts this via the
``test_generate_codeowners`` roundtrip test).

Section markers
---------------
The auto-generated block is delimited by:

    # BEGIN auto-generated from .governance-paths.yaml
    ...
    # END auto-generated from .governance-paths.yaml

Re-runs replace only the content between these markers; anything outside
is left alone. If the markers are missing (first run), the block is
appended to the file.

References
----------
ADR-043 §3.2 lines 552-571 — CODEOWNERS sample produced from
  ``.governance-paths.yaml``.
ADR-042 §6 — MAINTAINERS schema (companion ownership file; the
  ``humans`` field there is what we surface as the @-mention in
  CODEOWNERS lines).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_BEGIN_MARKER = "# BEGIN auto-generated from .governance-paths.yaml"
_END_MARKER = "# END auto-generated from .governance-paths.yaml"


def _load_governance_paths(repo_root: Path) -> list[str]:
    """Read ``.governance-paths.yaml`` and return its ``governance_paths`` list.

    Validates against the pydantic schema before returning so a malformed
    registry produces a clear error rather than malformed CODEOWNERS.
    """
    path = repo_root / ".governance-paths.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    # Local import: we want this script to be runnable from a checkout
    # before ``pip install -e .`` has completed (e.g., bootstrap CI).
    try:
        from scieasy.qa.schemas.governance import GovernancePaths
    except ImportError as exc:
        print(
            f"ERROR: cannot import scieasy.qa.schemas.governance: {exc}",
            file=sys.stderr,
        )
        raise

    gp = GovernancePaths(**data)
    return list(gp.governance_paths)


def _column_align(path: str, owner: str, min_pad: int = 4, width: int = 50) -> str:
    """Format a CODEOWNERS line with column alignment.

    Returns ``<path><padding><owner>`` where the padding ensures the
    owner column starts at column ``width`` (with at least ``min_pad``
    spaces for very long paths).
    """
    pad = max(min_pad, width - len(path))
    return f"{path}{' ' * pad}{owner}"


def render_codeowners_block(
    governance_paths: list[str],
    default_owner: str = "@jiazhenz026",
) -> str:
    """Render the auto-generated CODEOWNERS block from a path list.

    Lines are emitted in the order paths appear in
    ``.governance-paths.yaml`` (matching the order in ADR-043 §3.2 lines
    463-524 — semantically grouped, not alphabetical).
    """
    lines = [
        _BEGIN_MARKER,
        f"# Source: .governance-paths.yaml ({len(governance_paths)} paths).",
        "# Edit policy: do not modify lines between BEGIN/END markers by hand.",
        "# Regenerate via: python scripts/audit/generate_codeowners.py",
        "#",
        "# See ADR-043 §3.2 for the governance-path → CODEOWNERS contract.",
    ]
    for path in governance_paths:
        lines.append(_column_align(path, default_owner))
    lines.append(_END_MARKER)
    return "\n".join(lines) + "\n"


def _splice_block(existing: str, block: str) -> str:
    """Replace the existing auto-generated block in ``existing`` with ``block``.

    If the BEGIN/END markers are missing, append ``block`` to the end
    of ``existing`` (with a separating blank line). If markers are
    present, replace only the content between them (inclusive).

    Guarantees: the bytes outside the auto-generated block are unchanged.
    """
    begin_idx = existing.find(_BEGIN_MARKER)
    end_idx = existing.find(_END_MARKER)

    if begin_idx == -1 and end_idx == -1:
        # First run: append the block.
        sep = "" if existing.endswith("\n") else "\n"
        return existing + sep + "\n" + block

    if begin_idx == -1 or end_idx == -1:
        raise ValueError(
            "CODEOWNERS file has only one of the BEGIN/END auto-generated "
            "markers — manual repair required before regeneration."
        )

    if begin_idx > end_idx:
        raise ValueError(
            "CODEOWNERS file has BEGIN marker AFTER END marker — manual repair required before regeneration."
        )

    # Find end-of-line after the END marker so we don't leave a trailing
    # marker-line fragment.
    end_line_break = existing.find("\n", end_idx)
    end_replace = len(existing) if end_line_break == -1 else end_line_break + 1
    return existing[:begin_idx] + block + existing[end_replace:]


def generate(repo_root: Path, default_owner: str = "@jiazhenz026") -> str:
    """Compute the new CODEOWNERS file content.

    Reads:
      - ``<repo_root>/.governance-paths.yaml``
      - ``<repo_root>/.github/CODEOWNERS`` (if it exists; preserved
        outside the auto-generated block)

    Returns the proposed new file content (does not write).
    """
    paths = _load_governance_paths(repo_root)
    block = render_codeowners_block(paths, default_owner=default_owner)

    codeowners_path = repo_root / ".github" / "CODEOWNERS"
    existing = codeowners_path.read_text(encoding="utf-8") if codeowners_path.exists() else ""

    return _splice_block(existing, block)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns POSIX exit status."""
    parser = argparse.ArgumentParser(
        description=("Generate .github/CODEOWNERS from .governance-paths.yaml (ADR-043 §3.2).")
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the SciEasy repo root (default: current working directory).",
    )
    parser.add_argument(
        "--default-owner",
        type=str,
        default="@jiazhenz026",
        help="GitHub handle used as default owner for governance paths.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Do not write; print the rendered text to stdout and exit 0. "
            "Exit 2 if the would-be output differs from the current file."
        ),
    )
    args = parser.parse_args(argv)

    new_content = generate(repo_root=args.repo_root, default_owner=args.default_owner)

    codeowners_path = args.repo_root / ".github" / "CODEOWNERS"

    if args.check:
        current = codeowners_path.read_text(encoding="utf-8") if codeowners_path.exists() else ""
        if current != new_content:
            print(
                "CODEOWNERS is stale — regenerate via scripts/audit/generate_codeowners.py",
                file=sys.stderr,
            )
            return 2
        return 0

    codeowners_path.parent.mkdir(parents=True, exist_ok=True)
    codeowners_path.write_text(new_content, encoding="utf-8")
    print(f"Wrote {codeowners_path} ({len(new_content)} bytes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
