"""Validate ADR-042 fact substitutions in Markdown prose."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa.audit._util import git_tracked_relative_paths, is_tracked_path, normalise_path
from scieasy.qa.audit.facts import DEFAULT_FACTS_PATH, load_facts
from scieasy.qa.schemas.facts import FactsRegistry
from scieasy.qa.schemas.report import AuditReport, AuditStatus, DriftClass, Finding, Severity

_SUBSTITUTION_RE = re.compile(r"\{\{\s*facts(?:\[['\"](?P<bracket>[^'\"]+)['\"]\]|\.(?P<dot>[A-Za-z0-9_.:-]+))\s*\}\}")


def _target_docs(repo_root: Path, docs: Sequence[Path] | None) -> list[Path]:
    if docs is not None:
        return list(docs)
    tracked_paths = git_tracked_relative_paths(repo_root)
    return sorted(
        path for path in (repo_root / "docs").rglob("*.md") if is_tracked_path(path, repo_root, tracked_paths)
    )


def check_substitutions(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    docs: Sequence[Path] | None = None,
) -> AuditReport:
    """Validate fact substitutions against the current facts registry."""

    fact_ids = facts.by_id()
    findings: list[Finding] = []
    checked = 0
    substitutions = 0
    for path in _target_docs(repo_root, docs):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        checked += 1
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in _SUBSTITUTION_RE.finditer(line):
                substitutions += 1
                fact_id = match.group("bracket") or match.group("dot") or ""
                if fact_id not in fact_ids:
                    findings.append(
                        Finding(
                            rule_id="fact-drift.unknown-fact",
                            severity=Severity.ERROR,
                            file=normalise_path(path),
                            line=line_no,
                            message=f"fact substitution references unknown fact id: {fact_id}",
                            drift_class=DriftClass.PHANTOM_REFERENCE,
                        )
                    )

    return AuditReport(
        tool="fact_drift",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=facts.source_sha,
        findings=findings,
        summary={"docs_checked": checked, "substitutions_checked": substitutions},
    )


def check_repo(repo_root: Path, *, facts_path: Path = DEFAULT_FACTS_PATH) -> AuditReport:
    """Load generated facts and validate substitutions across docs."""

    path = facts_path if facts_path.is_absolute() else repo_root / facts_path
    return check_substitutions(repo_root, load_facts(path))
