"""Workflow shadow-list defense (ADR-043 §3.5 audit fix iter-7 ITER-FRESH-002).

If a maintainer (or a careless agent) reintroduces a hand-edited
``paths:`` list to ``.github/workflows/governance-modification.yml``,
the dynamic-filter design (TC-1E.6 ``path_filter``) is silently
defeated — the workflow runs only on PRs whose diff matches the static
list, leaving the broader governance surface unprotected again.

This module performs a static syntactic check on
``.github/workflows/governance-modification.yml`` and rejects any
hardcoded ``paths:`` (or ``paths-ignore:``) entry under
``on.pull_request``.

Entry-point (ADR-043 §4.7 audit fix F14)::

    verify(repo_root: Path | None = None) -> list[Finding]

The Finding shape comes from :class:`scieasy.qa.schemas.report.Finding`
so the result composes cleanly into ``AuditReport``.

References
----------
ADR-043 §3.5 lines 753-757 — sync-check intent.
ADR-043 §4.7 lines 1247-1254 — entry-point signature.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from scieasy.qa.schemas.report import Finding, Severity

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

_WORKFLOW_PATH = Path(".github/workflows/governance-modification.yml")


# --------------------------------------------------------------------------- #
# Public entry-point                                                          #
# --------------------------------------------------------------------------- #


def verify(repo_root: Path | None = None) -> list[Finding]:
    """Static-parse ``governance-modification.yml`` and reject shadow path lists.

    Defends against the drift mode where the YAML ``paths:`` list lags
    ``.governance-paths.yaml``. Returns one Finding per offending entry
    (``paths`` and ``paths-ignore`` are both rejected).
    """
    repo_root = (repo_root or Path.cwd()).resolve()
    workflow = repo_root / _WORKFLOW_PATH

    if not workflow.is_file():
        return [
            Finding(
                rule_id="governance/workflow-missing",
                severity=Severity.ERROR,
                file=_WORKFLOW_PATH.as_posix(),
                message=("governance-modification workflow file is missing; the §3.5 recursive self-check cannot run"),
                suggested_fix="Restore .github/workflows/governance-modification.yml per ADR-043 §3.5.",
            )
        ]

    try:
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [
            Finding(
                rule_id="governance/workflow-invalid-yaml",
                severity=Severity.ERROR,
                file=_WORKFLOW_PATH.as_posix(),
                message=f"governance-modification workflow contains invalid YAML: {exc}",
            )
        ]

    findings: list[Finding] = []
    # ``on:`` may parse as either ``on`` (str key) OR ``True`` (YAML 1.1
    # boolean coercion of the bare word "on" — PyYAML default behaviour).
    on_block = doc.get("on") if isinstance(doc.get("on"), dict) else doc.get(True)
    if not isinstance(on_block, dict):
        return findings  # Workflow has no `on:` block at all — different problem.

    pull_request = on_block.get("pull_request")
    if not isinstance(pull_request, dict):
        return findings

    for key in ("paths", "paths-ignore"):
        if key in pull_request:
            findings.append(
                Finding(
                    rule_id="governance/workflow-static-path-filter",
                    severity=Severity.ERROR,
                    file=_WORKFLOW_PATH.as_posix(),
                    message=(
                        f"hand-maintained `{key}:` list found under `on.pull_request`; "
                        "use the dynamic path_filter step from ADR-043 §3.5 instead"
                    ),
                    suggested_fix=(
                        f"Delete the `{key}:` block; the workflow should call "
                        "`python -m scieasy.qa.governance.path_filter` and gate "
                        "subsequent steps on its `touched` output."
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
        description="Reject hand-maintained path lists in governance-modification.yml (ADR-043 §3.5).",
    )
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root or Path.cwd()).resolve()
    findings = verify(repo_root)
    if not findings:
        return 0
    for f in findings:
        print(f.model_dump_json(), file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
