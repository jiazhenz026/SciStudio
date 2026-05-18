"""Scan target ADR/spec docs for internal contradictions (ADR-042 §28.1).

:func:`run` walks each target ADR markdown file, parses its frontmatter
and prose, and emits findings for each contradiction class:

* ``supersedes`` cycles (A supersedes B; B supersedes A).
* ``agent_editable`` contradictions (a frontmatter declaration contradicts
  prose in §X that permits agent edits to a sub-section).
* ``governs`` vs ``excludes`` conflicts (an exclude path that is not under
  any included module/file).
* Workflow stage cycles (declared in prose tables).
* Self-references to undefined sections (``§99`` where §99 does not exist).
* Cross-ADR supersedes cycles between target files.

Per Phase 1 investigation default Q1B.7.3, prose-level
"internal-clause" heuristics (e.g., §13 "trailer required" vs §25 "Tier 1
exempt") are reported at **warning** severity rather than error. They
require human judgement to triage.

Findings are written to ``docs/audit/adr-self-audit/<adr>-<sha>.json``
when invoked via the CLI (per §28.1). The Python API just returns the
:class:`AuditReport`.

References
----------
ADR-042 §28.1 — checklist of contradiction classes (authoritative).
ADR-042 §9.6 — entry-point signature.
ADR-043 §3.5 — governance-modification workflow caller.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml

from scieasy.qa.schemas.frontmatter import ADRFrontmatter
from scieasy.qa.schemas.report import (
    AuditReport,
    Finding,
    Severity,
    ToolRun,
)

__all__ = ["run"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    repo_root: Path | None = None,
    *,
    targets: list[Path] | None = None,
) -> AuditReport:
    """Scan ``targets`` for internal contradictions per ADR-042 §28.1.

    Args:
        repo_root: Repository root (defaults to ``Path.cwd()``).
        targets: List of ADR/spec markdown files to audit. When ``None``,
            every ADR under ``docs/adr/ADR-*.md`` is audited.

    Returns:
        An :class:`AuditReport` carrying one :class:`ToolRun` named
        ``contradiction_audit``.
    """
    root = repo_root or Path.cwd()
    started_at = datetime.now(UTC)

    if targets is None:
        adr_dir = root / "docs" / "adr"
        targets = sorted(adr_dir.glob("ADR-*.md")) if adr_dir.is_dir() else []

    findings: list[Finding] = []

    # Pre-load frontmatters for the cross-ADR supersedes cycle check.
    fm_index: dict[int, ADRFrontmatter] = {}
    for target in targets:
        fm = _parse_frontmatter(target)
        if fm is not None:
            fm_index[int(fm.adr)] = fm

    for target in targets:
        rel = str(target.relative_to(root)).replace("\\", "/")
        fm = _parse_frontmatter(target)
        text = target.read_text(encoding="utf-8") if target.is_file() else ""
        prose = _strip_frontmatter(text)

        if fm is not None:
            findings.extend(_check_supersede_self(fm, rel))
            findings.extend(_check_governs_excludes(fm, rel))
            findings.extend(_check_agent_editable_pairing(fm, rel))

        findings.extend(_check_undefined_section_refs(prose, rel))
        findings.extend(_check_internal_clause_heuristic(prose, rel))

    findings.extend(_check_cross_adr_supersedes_cycles(fm_index))
    findings.extend(_check_workflow_stage_cycles(fm_index, targets, root))

    completed_at = datetime.now(UTC)
    config_hash = hashlib.sha1(
        f"contradiction_audit:repo_root={root}:targets={sorted(str(t) for t in targets)}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:16]

    tool_run = ToolRun(
        tool="contradiction_audit",
        version="1",
        config_hash=config_hash,
        started_at=started_at,
        completed_at=completed_at,
        exit_status=_exit_status(findings),
        findings=findings,
    )

    return AuditReport(
        schema_version=1,
        run_id=f"contradiction_audit-{started_at.strftime('%Y%m%dT%H%M%SZ')}",
        repo_sha=_resolve_repo_sha(root),
        repo_branch=_resolve_repo_branch(root),
        generated_at=completed_at,
        runs=[tool_run],
        total_findings=len(findings),
        by_severity=dict(Counter(f.severity for f in findings)),
        by_drift_class=dict(Counter(f.drift_class for f in findings if f.drift_class is not None)),
        bidirectional_closure_ok=True,
        translation_ok=True,
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_supersede_self(fm: ADRFrontmatter, rel: str) -> list[Finding]:
    """Catch ADRs that supersede themselves (frontmatter-validator dup, kept
    here for defence-in-depth since §28.1 lists it explicitly).
    """
    findings: list[Finding] = []
    if int(fm.adr) in [int(x) for x in fm.supersedes]:
        findings.append(
            Finding(
                rule_id="contradiction.self-supersede",
                severity=Severity.ERROR,
                file=rel,
                symbol=f"ADR-{int(fm.adr):03d}",
                message=f"ADR-{int(fm.adr):03d} lists itself in supersedes",
            )
        )
    return findings


def _check_governs_excludes(fm: ADRFrontmatter, rel: str) -> list[Finding]:
    """Catch ``excludes`` entries that don't fall under any include."""
    findings: list[Finding] = []
    if not fm.governs.excludes:
        return findings
    include_prefixes: list[str] = []
    for module in fm.governs.modules:
        include_prefixes.append("src/" + module.replace(".", "/"))
        include_prefixes.append(module.replace(".", "/"))
    for file_glob in fm.governs.files:
        include_prefixes.append(file_glob.split("*")[0].rstrip("/"))
    for excl in fm.governs.excludes:
        anchor = excl.split("*")[0].rstrip("/")
        if not include_prefixes:
            findings.append(
                Finding(
                    rule_id="contradiction.exclude-without-include",
                    severity=Severity.WARNING,
                    file=rel,
                    message=(f"excludes entry '{excl}' but governs.modules/files are empty"),
                )
            )
            continue
        if not any(_path_covers(p, anchor) for p in include_prefixes):
            findings.append(
                Finding(
                    rule_id="contradiction.exclude-outside-include",
                    severity=Severity.WARNING,
                    file=rel,
                    message=(f"excludes entry '{excl}' is not under any included module/file ({include_prefixes})"),
                )
            )
    return findings


def _check_agent_editable_pairing(fm: ADRFrontmatter, rel: str) -> list[Finding]:
    """``agent_editable=false`` should not have a non-empty allowlist."""
    findings: list[Finding] = []
    # The frontmatter validator already raises on the inconsistent pairs;
    # this is defence-in-depth in case the scan target has the validator
    # turned off (e.g., a corrupted frontmatter that still parses as YAML).
    if fm.agent_editable.value != "allowlist" and fm.agent_editable_allowlist:
        findings.append(
            Finding(
                rule_id="contradiction.agent-editable-pairing",
                severity=Severity.ERROR,
                file=rel,
                message=(f"agent_editable={fm.agent_editable.value} but agent_editable_allowlist is non-empty"),
            )
        )
    return findings


def _check_undefined_section_refs(prose: str, rel: str) -> list[Finding]:
    """Surface ``§X.Y`` references that have no matching heading in the file."""
    findings: list[Finding] = []
    section_nums = _collect_section_numbers(prose)
    refs = set(re.findall(r"§(\d+(?:\.\d+)*)", prose))
    for ref in sorted(refs):
        if ref in section_nums:
            continue
        # Allow cross-ADR refs: "ADR-NNN §X" — we only flag bare §X that
        # don't resolve internally.
        if not _is_bare_section_ref(ref, prose):
            continue
        findings.append(
            Finding(
                rule_id="contradiction.undefined-section",
                severity=Severity.WARNING,
                file=rel,
                message=f"reference to §{ref} but no such Markdown heading found",
            )
        )
    return findings


def _check_internal_clause_heuristic(prose: str, rel: str) -> list[Finding]:
    """Heuristic: emit warning when prose contains both "required" and
    "exempt"/"may skip" within 600 chars on the same topic key.

    This is intentionally a low-precision warning — §28.1 manager default
    Q1B.7.3 says "warning severity" for the internal-clause heuristic so
    humans triage. Topic keys come from a small built-in list of
    contradiction-prone terms (trailer, override, tier, gate, hook).
    """
    findings: list[Finding] = []
    topics = ("trailer", "override", "tier 1", "tier 2", "gate", "hook")
    for topic in topics:
        for m in re.finditer(rf"\b{re.escape(topic)}\b", prose, re.IGNORECASE):
            start = max(0, m.start() - 600)
            end = min(len(prose), m.end() + 600)
            window = prose[start:end].lower()
            has_required = "required" in window or "must" in window
            has_exempt = "exempt" in window or "may skip" in window or "optional" in window
            if has_required and has_exempt:
                findings.append(
                    Finding(
                        rule_id="contradiction.internal-clause-heuristic",
                        severity=Severity.WARNING,
                        file=rel,
                        message=(
                            f"text mentions topic '{topic}' alongside both "
                            "required/must AND exempt/may-skip/optional within 600 "
                            "chars; manual review to confirm Tier-1/Tier-2 "
                            "consistency"
                        ),
                    )
                )
                # Only one warning per topic per file (don't flood).
                break
    return findings


def _check_cross_adr_supersedes_cycles(fm_index: dict[int, ADRFrontmatter]) -> list[Finding]:
    """Detect supersedes cycles across the loaded ADR set."""
    findings: list[Finding] = []
    # Build a directed graph and run a DFS for back-edges.
    graph: dict[int, set[int]] = {adr: {int(x) for x in fm.supersedes} for adr, fm in fm_index.items()}
    visited: set[int] = set()
    stack: set[int] = set()

    def _dfs(node: int) -> list[int] | None:
        if node in stack:
            return [node]
        if node in visited:
            return None
        visited.add(node)
        stack.add(node)
        for nxt in graph.get(node, ()):
            if nxt not in fm_index:
                continue
            cycle = _dfs(nxt)
            if cycle is not None:
                if cycle[0] == node:
                    return [*cycle, node]
                cycle.append(node)
                return cycle
        stack.discard(node)
        return None

    for start_node in sorted(graph):
        cycle = _dfs(start_node)
        if cycle:
            cycle_refs = [f"ADR-{n:03d}" for n in cycle]
            findings.append(
                Finding(
                    rule_id="contradiction.supersedes-cycle",
                    severity=Severity.ERROR,
                    file=f"docs/adr/ADR-{start_node:03d}.md",
                    symbol=" -> ".join(cycle_refs),
                    message=f"supersedes cycle detected: {' -> '.join(cycle_refs)}",
                )
            )
            # Reset DFS state so other unrelated cycles surface too.
            visited.clear()
            stack.clear()
    return findings


def _check_workflow_stage_cycles(
    fm_index: dict[int, ADRFrontmatter],
    targets: list[Path],
    repo_root: Path,
) -> list[Finding]:
    """Detect declared workflow stage dependencies that form a cycle.

    Phase-1 heuristic: parse Markdown tables whose first column header is
    "Stage" or "#" and look for "depends on" cells; build the
    dependency graph and DFS-check. We do not require full prose
    understanding — just the table form documented in ADR-042 §19.2.
    """
    findings: list[Finding] = []
    _ = fm_index  # reserved for future cross-ADR stage matrix
    for target in targets:
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8", errors="ignore")
        rel = str(target.relative_to(repo_root)).replace("\\", "/")
        deps = _parse_stage_dependencies(text)
        cycle = _detect_cycle(deps)
        if cycle:
            findings.append(
                Finding(
                    rule_id="contradiction.workflow-stage-cycle",
                    severity=Severity.ERROR,
                    file=rel,
                    symbol=" -> ".join(cycle),
                    message=(f"declared workflow stage dependencies form a cycle: {' -> '.join(cycle)}"),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(path: Path) -> ADRFrontmatter | None:
    """Best-effort frontmatter parse; ``None`` on any failure."""
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
    if not isinstance(data, dict):
        return None
    try:
        return ADRFrontmatter.model_validate(data)
    except (ValueError, TypeError):
        return None


def _strip_frontmatter(text: str) -> str:
    """Return prose with the leading ``---`` frontmatter block stripped."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4 :]


def _collect_section_numbers(prose: str) -> set[str]:
    """Return the set of ``§X.Y`` numbers attached to Markdown headings."""
    nums: set[str] = set()
    for line in prose.splitlines():
        m = re.match(r"^(#{1,6})\s+(\d+(?:\.\d+)*)", line)
        if m:
            nums.add(m.group(2))
    return nums


def _is_bare_section_ref(ref: str, prose: str) -> bool:
    """True when ``§REF`` appears NOT preceded by ``ADR-NNN``.

    Cross-ADR references like ``ADR-040 §3.7`` are not contradictions in
    the target file; only bare ``§3.7`` (i.e. self-reference) is.
    """
    pattern = re.compile(rf"§{re.escape(ref)}")
    for match in pattern.finditer(prose):
        prefix_start = max(0, match.start() - 16)
        prefix = prose[prefix_start : match.start()]
        if re.search(r"ADR-\d{1,4}\s+$", prefix):
            continue
        return True
    return False


def _path_covers(prefix: str, candidate: str) -> bool:
    return candidate == prefix or candidate.startswith(prefix.rstrip("/") + "/")


def _parse_stage_dependencies(text: str) -> dict[str, set[str]]:
    """Parse ``depends on``-style stage-table cells.

    Phase 1 form: each row of a Markdown table whose any header contains
    "Stage" is scanned for ``A -> B`` or ``A depends on B`` patterns.
    Result keys point at dependants; values are dependencies.
    """
    deps: dict[str, set[str]] = {}
    in_stage_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and "stage" in stripped.lower() and "---" not in stripped:
            in_stage_table = True
            continue
        if in_stage_table:
            if not stripped.startswith("|"):
                in_stage_table = False
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 2:
                continue
            stage_name = cells[0]
            for cell in cells[1:]:
                lower = cell.lower()
                if "depends on" not in lower and "→" not in cell and "->" not in cell:
                    continue
                # Only consider tokens inside backticks — that is the
                # convention in ADR-042 §19.2's stage table.
                m = re.findall(r"`([a-z][a-z0-9_-]*)`", cell)
                for dep in m:
                    if dep == stage_name.strip("`"):
                        continue
                    deps.setdefault(stage_name.strip("`"), set()).add(dep)
    return deps


def _detect_cycle(deps: dict[str, set[str]]) -> list[str] | None:
    """Return one cycle as a path of node names, or ``None`` if acyclic."""
    visited: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()

    def _dfs(node: str) -> list[str] | None:
        if node in on_stack:
            i = stack.index(node)
            return [*stack[i:], node]
        if node in visited:
            return None
        visited.add(node)
        on_stack.add(node)
        stack.append(node)
        for nxt in deps.get(node, ()):
            r = _dfs(nxt)
            if r:
                return r
        on_stack.discard(node)
        stack.pop()
        return None

    for n in sorted(deps):
        r = _dfs(n)
        if r:
            return r
    return None


def _exit_status(findings: list[Finding]) -> Literal["ok", "warnings", "errors", "crash"]:
    if not findings:
        return "ok"
    if any(f.severity == Severity.ERROR for f in findings):
        return "errors"
    if any(f.severity == Severity.WARNING for f in findings):
        return "warnings"
    return "ok"


def _resolve_repo_sha(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"


def _resolve_repo_branch(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"
