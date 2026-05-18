"""Workflow-sync check (ADR-043 §3.5 + audit fix iter-7 ITER-FRESH-002).

The §3.5 recursive-self-validation workflow lives at
``.github/workflows/governance-modification.yml``. Audit fix C2 noted
that the previous design used a hand-maintained
``on.pull_request.paths:`` filter that drifted from
``.governance-paths.yaml`` (covered only ~12 of ~30 governance paths,
silently un-protecting CURSOR.md / GEMINI.md / per-subtree AGENTS.md /
audit logs / codemods / agent prompts).

The fix is two-pronged:

1. The workflow loads its path filter dynamically via
   :mod:`scieasy.qa.governance.path_filter` (no shadow YAML list).
2. **This module** verifies that the workflow file itself stays in
   the dynamic-filter shape — i.e. ``on.pull_request:`` is either an
   empty ``{}``-mapping or carries *no* literal ``paths:`` /
   ``paths-ignore:`` filter.

Entry-point (ADR-043 §4.7 audit fix F14)::

    verify(repo_root: Path | None = None) -> list[Finding]

The return type is ``list[Finding]`` per the ADR; we use a local
:class:`SyncCheckFinding` model with the same surface shape as the
other §3.5 finding types (kind / file / line / message) but no
``WeakeningKind`` / ``LoosenedAxis`` coupling — sync drift is a
distinct issue family.

References
----------
ADR-043 §3.5 (lines 722-782) — authoritative spec.
ADR-043 §4.7 line 1250 — entry-point signature.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

_WORKFLOW_REL = ".github/workflows/governance-modification.yml"


class SyncCheckFinding(BaseModel):
    """One workflow-sync drift detection.

    The shape mirrors the other §3.5 findings (file/line/message) for
    JSON-rendering consistency, but the kind is a sync-drift specific
    literal rather than :class:`WeakeningKind` / ``LoosenedAxis.axis``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "shadow-paths-filter",
        "shadow-paths-ignore-filter",
        "workflow-missing",
        "missing-path-filter-step",
        "missing-workflow-sync-step",
    ]
    file: str
    line: int | None = None
    message: str


# --------------------------------------------------------------------------- #
# Workflow parsing                                                            #
# --------------------------------------------------------------------------- #


def _read_workflow(repo_root: Path) -> tuple[str | None, list[str]]:
    """Return (raw_text, lines) for the governance-modification workflow."""
    target = repo_root / _WORKFLOW_REL
    if not target.is_file():
        return None, []
    text = target.read_text(encoding="utf-8")
    return text, text.splitlines()


def _on_pull_request_block(lines: list[str]) -> tuple[int, int] | None:
    """Locate the ``on.pull_request:`` sub-block.

    Returns the half-open ``(start, end)`` line indices (0-based) of the
    block body (lines between the ``pull_request:`` key and the next
    sibling at the same or shallower indent), or ``None`` if the block
    is absent.
    """
    # First find ``on:`` at column 0
    on_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"^on:\s*$", line):
            on_idx = i
            break
    if on_idx is None:
        return None

    # Walk forward to find ``  pull_request:`` (indent 2)
    pr_idx: int | None = None
    for i in range(on_idx + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            continue
        # If we hit a column-0 key, on: block ended without a pull_request
        if line[0:1] != " " and not line.startswith("#"):
            return None
        if re.match(r"^  pull_request:", line):
            pr_idx = i
            break
        # If we hit another at-indent-2 sibling key, skip
    if pr_idx is None:
        return None

    # Find the end: next line at indent <= 2 that isn't blank/comment/list-item
    end_idx = len(lines)
    for j in range(pr_idx + 1, len(lines)):
        line = lines[j]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent <= 2:
            end_idx = j
            break
    return pr_idx + 1, end_idx


def _block_has_filter(lines: list[str], start: int, end: int) -> dict[str, int]:
    """Look for ``paths:`` / ``paths-ignore:`` keys inside the block."""
    found: dict[str, int] = {}
    for i in range(start, end):
        line = lines[i]
        s = line.strip()
        if s.startswith("paths:"):
            found.setdefault("paths", i + 1)
        elif s.startswith("paths-ignore:"):
            found.setdefault("paths-ignore", i + 1)
    return found


def _has_step(text: str, signature: str) -> bool:
    """Return ``True`` iff the ``recursive-self-check`` job has a step whose
    ``run:`` command contains *signature* as a stripped line.

    The check walks the parsed YAML structure
    (``doc['jobs']['recursive-self-check']['steps']``) so that a *signature*
    appearing only inside a YAML comment is **not** counted as a match
    (#1179 audit finding).

    Falls back to the raw-text substring search when YAML parsing fails (e.g.
    the file is not valid YAML) so the caller still gets a useful signal.

    Parameters
    ----------
    text:
        Raw YAML text of the governance-modification workflow.
    signature:
        Module invocation string to look for (e.g.
        ``"scieasy.qa.governance.path_filter"``).
    """
    try:
        doc: Any = yaml.safe_load(text)
    except yaml.YAMLError:
        # Malformed YAML: fall back to substring search so we don't false-
        # negative on workflows that are otherwise correct.
        return signature in text

    if not isinstance(doc, dict):
        return signature in text

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return False

    job = jobs.get("recursive-self-check")
    if not isinstance(job, dict):
        return False

    steps = job.get("steps")
    if not isinstance(steps, list):
        return False

    for step in steps:
        if not isinstance(step, dict):
            continue
        run_block = step.get("run", "")
        if not isinstance(run_block, str):
            continue
        for line in run_block.splitlines():
            if signature in line.strip():
                return True
    return False


# --------------------------------------------------------------------------- #
# Public entry-point                                                          #
# --------------------------------------------------------------------------- #


def verify(repo_root: Path | None = None) -> list[SyncCheckFinding]:
    """Verify governance-modification.yml uses the dynamic path filter.

    Returns ``[]`` when the workflow is structurally correct (uses
    :mod:`scieasy.qa.governance.path_filter` and has no shadow
    ``paths:`` / ``paths-ignore:`` hand-list). Otherwise returns one
    :class:`SyncCheckFinding` per detected drift.

    Drift categories:

    - ``workflow-missing`` — file does not exist at the expected path.
    - ``shadow-paths-filter`` — ``on.pull_request.paths:`` is present.
    - ``shadow-paths-ignore-filter`` — ``on.pull_request.paths-ignore:``
      is present.
    - ``missing-path-filter-step`` — workflow has no step invoking
      ``scieasy.qa.governance.path_filter``.
    - ``missing-workflow-sync-step`` — workflow has no step invoking
      ``scieasy.qa.governance.workflow_sync_check``.
    """
    root = (repo_root or Path.cwd()).resolve()
    text, lines = _read_workflow(root)
    if text is None:
        return [
            SyncCheckFinding(
                kind="workflow-missing",
                file=_WORKFLOW_REL,
                line=None,
                message=f"workflow file not found at {_WORKFLOW_REL}",
            )
        ]

    findings: list[SyncCheckFinding] = []
    bounds = _on_pull_request_block(lines)
    if bounds is not None:
        start, end = bounds
        hit = _block_has_filter(lines, start, end)
        if "paths" in hit:
            findings.append(
                SyncCheckFinding(
                    kind="shadow-paths-filter",
                    file=_WORKFLOW_REL,
                    line=hit["paths"],
                    message=(
                        "on.pull_request.paths: is a shadow hand-list — "
                        "use scieasy.qa.governance.path_filter instead "
                        "(ADR-043 §3.5 audit fix C2)."
                    ),
                )
            )
        if "paths-ignore" in hit:
            findings.append(
                SyncCheckFinding(
                    kind="shadow-paths-ignore-filter",
                    file=_WORKFLOW_REL,
                    line=hit["paths-ignore"],
                    message=(
                        "on.pull_request.paths-ignore: is a shadow "
                        "hand-list — use scieasy.qa.governance.path_filter "
                        "instead (ADR-043 §3.5 audit fix C2)."
                    ),
                )
            )

    if not _has_step(text, "scieasy.qa.governance.path_filter"):
        findings.append(
            SyncCheckFinding(
                kind="missing-path-filter-step",
                file=_WORKFLOW_REL,
                line=None,
                message=("workflow does not invoke scieasy.qa.governance.path_filter; required by ADR-043 §3.5."),
            )
        )
    if not _has_step(text, "scieasy.qa.governance.workflow_sync_check"):
        findings.append(
            SyncCheckFinding(
                kind="missing-workflow-sync-step",
                file=_WORKFLOW_REL,
                line=None,
                message=(
                    "workflow does not invoke scieasy.qa.governance.workflow_sync_check; required by ADR-043 §3.5."
                ),
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.workflow_sync_check",
        description="Workflow-sync check for governance-modification.yml (ADR-043 §3.5).",
    )
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    root = Path(args.repo_root or Path.cwd()).resolve()
    findings = verify(root)
    if not findings:
        return 0
    for f in findings:
        print(f.model_dump_json(), file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
