"""a/b/c1/c2/c3/d drift classification (ADR-042 §9).

:func:`classify_repo` is the top-level entry point. It:

1. Builds a code-symbol index via :mod:`griffe` (static, no import
   side effects).
2. Parses every Accepted ADR's frontmatter.
3. Runs a **forward** pass: every ``governs.contracts`` symbol must
   resolve in code; signatures of resolved functions must match
   (b/c1/c2/c3 findings on disagreement).
4. Runs a **reverse** pass: every public class must be cited by some
   Accepted ADR's ``governs.contracts`` (or be a member of a
   ``governs.modules`` package); every public function/method must
   carry a docstring (d-class findings).
5. Delegates bidirectional MAINTAINERS↔governs closure to
   :func:`scieasy.qa.audit.closure.check_bidirectional`.
6. Aggregates into an :class:`~scieasy.qa.schemas.report.AuditReport`.

The companion file
``docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md`` holds the
prose-form algorithm reference (kept out of the ADR per §28.0 so
``pytest-examples`` doesn't try to execute it).

References
----------
ADR-042 §9 — full drift-class definitions and algorithms.
ADR-042 §9.6 — entry-point signature.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import griffe

from scieasy.qa.audit.closure import (
    check_bidirectional,
    load_accepted_adrs,
)
from scieasy.qa.schemas.frontmatter import ADRFrontmatter
from scieasy.qa.schemas.report import (
    AuditReport,
    DriftClass,
    Finding,
    Severity,
    ToolRun,
)

__all__ = [
    "build_code_symbol_index",
    "classify_repo",
    "is_public",
    "signatures_match",
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def classify_repo(repo_root: Path) -> AuditReport:
    """Top-level drift classification entry point.

    Steps (full pseudocode in
    ``docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md``):

    1. Build code symbol table via :mod:`griffe`.
    2. Parse all ADR frontmatters; keep ``Accepted`` only.
    3. Build doc-cited symbols index from ``governs.contracts``.
    4. Forward pass.
    5. Reverse pass.
    6. Delegated bidirectional closure.
    7. Aggregate.

    Args:
        repo_root: Repository root.

    Returns:
        :class:`AuditReport` carrying one :class:`ToolRun` for the
        ``doc_drift`` tool. Closure delegation findings (from
        :func:`scieasy.qa.audit.closure.check_bidirectional`) are
        included in that ToolRun's findings list so downstream
        consumers see a single drift report covering forward + reverse
        + closure.
    """
    started_at = datetime.now(UTC)

    code_index = build_code_symbol_index(repo_root)
    adrs = load_accepted_adrs(repo_root)
    doc_cited = _collect_doc_cited_symbols(adrs)
    governed_modules = _collect_governed_modules(adrs)

    findings: list[Finding] = []

    # ── Forward pass: every governs.contracts symbol resolves ──────
    for adr in adrs:
        for symbol in adr.governs.contracts:
            if symbol in code_index:
                obj = code_index[symbol]
                if _is_callable_like(obj):
                    matched, why = signatures_match(obj, adr)
                    if not matched:
                        findings.append(
                            Finding(
                                rule_id="doc-drift.signature-mismatch",
                                severity=Severity.ERROR,
                                drift_class=DriftClass.B,
                                file=_griffe_filepath(obj),
                                symbol=symbol,
                                message=(f"signature mismatch: {why} (cited by ADR-{adr.adr:03d})"),
                            )
                        )
            else:
                evidence = _git_history_for_symbol(symbol, repo_root)
                findings.append(_c_class_finding(symbol, adr, evidence, code_index))

    # ── Reverse pass: public-class ADR coverage + function docstrings ──
    for dotted_path, obj in code_index.items():
        if not is_public(obj):
            continue
        if isinstance(obj, griffe.Class):
            if not _class_is_governed(dotted_path, doc_cited, governed_modules):
                findings.append(
                    Finding(
                        rule_id="doc-drift.orphan-class",
                        severity=Severity.ERROR,
                        drift_class=DriftClass.D,
                        file=_griffe_filepath(obj),
                        symbol=dotted_path,
                        message=(
                            "public class is not cited by any Accepted ADR's "
                            "governs.contracts and not a member of any "
                            "governs.modules package"
                        ),
                        suggested_fix=(
                            f"add '{dotted_path}' to some Accepted ADR's "
                            "governs.contracts, OR add its parent package to "
                            "governs.modules"
                        ),
                    )
                )
        elif isinstance(obj, griffe.Function) and (not obj.docstring or not str(obj.docstring.value).strip()):
            findings.append(
                Finding(
                    rule_id="doc-drift.missing-docstring",
                    severity=Severity.WARNING,
                    drift_class=DriftClass.D,
                    file=_griffe_filepath(obj),
                    symbol=dotted_path,
                    message=("public function/method has no docstring (Google-style required)"),
                )
            )

    # ── Reverse pass: __all__ presence (warning during Phase 1) ────
    findings.extend(_check_all_presence(code_index))

    # ── Delegated bidirectional closure ────────────────────────────
    closure_findings = check_bidirectional(repo_root)
    findings.extend(closure_findings)

    # Translation freshness placeholder; Phase 1D ships the real check.
    translation_ok = True

    completed_at = datetime.now(UTC)
    config_hash = hashlib.sha1(
        f"doc_drift:repo_root={repo_root}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:16]

    tool_run = ToolRun(
        tool="doc_drift",
        version="1",
        config_hash=config_hash,
        started_at=started_at,
        completed_at=completed_at,
        exit_status=_compute_exit_status(findings),
        findings=findings,
    )

    return AuditReport(
        schema_version=1,
        run_id=f"doc_drift-{started_at.strftime('%Y%m%dT%H%M%SZ')}",
        repo_sha=_resolve_repo_sha(repo_root),
        repo_branch=_resolve_repo_branch(repo_root),
        generated_at=completed_at,
        runs=[tool_run],
        total_findings=len(findings),
        by_severity=dict(Counter(f.severity for f in findings)),
        by_drift_class=dict(Counter(f.drift_class for f in findings if f.drift_class is not None)),
        bidirectional_closure_ok=not any(f.rule_id.startswith("closure.") for f in closure_findings),
        translation_ok=translation_ok,
    )


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------


def build_code_symbol_index(repo_root: Path) -> dict[str, griffe.Object | griffe.Alias]:
    """Build ``{dotted_path: griffe.Object}`` for every importable symbol.

    Walks every package under ``src/`` via :class:`griffe.GriffeLoader`
    (static; no import side effects). Each leaf member is registered
    by its fully-qualified dotted path.
    """
    src = repo_root / "src"
    if not src.is_dir():
        return {}
    loader = griffe.GriffeLoader(search_paths=[str(src)])
    index: dict[str, griffe.Object | griffe.Alias] = {}
    for top_pkg in _top_level_packages(src):
        try:
            module = loader.load(top_pkg)
        except (ImportError, OSError, griffe.LoadingError):  # pragma: no cover - defensive
            continue
        _walk_module(module, index)
    return index


def _top_level_packages(src: Path) -> list[str]:
    """Yield every top-level package name under ``src/``."""
    out: list[str] = []
    for entry in src.iterdir():
        if entry.is_dir() and (entry / "__init__.py").is_file():
            out.append(entry.name)
    return out


def _walk_module(node: griffe.Object | griffe.Alias, index: dict[str, griffe.Object | griffe.Alias]) -> None:
    if isinstance(node, griffe.Alias):
        return
    index[node.canonical_path] = node
    for child in node.members.values():
        if isinstance(child, griffe.Alias):
            continue
        index[child.canonical_path] = child
        if isinstance(child, griffe.Class | griffe.Module):
            _walk_module(child, index)


# ---------------------------------------------------------------------------
# Forward-pass helpers
# ---------------------------------------------------------------------------


def _collect_doc_cited_symbols(adrs: Iterable[ADRFrontmatter]) -> set[str]:
    cited: set[str] = set()
    for adr in adrs:
        cited.update(adr.governs.contracts)
    return cited


def _collect_governed_modules(adrs: Iterable[ADRFrontmatter]) -> set[str]:
    modules: set[str] = set()
    for adr in adrs:
        modules.update(adr.governs.modules)
    return modules


def _class_is_governed(dotted_path: str, doc_cited: set[str], governed_modules: set[str]) -> bool:
    if dotted_path in doc_cited:
        return True
    return any(dotted_path.startswith(mod + ".") or dotted_path == mod for mod in governed_modules)


def signatures_match(obj: griffe.Object | griffe.Alias, adr: ADRFrontmatter) -> tuple[bool, str]:
    """Compare a griffe function/method object against its ADR-declared shape.

    The ADR currently records only the dotted symbol path, not a full
    signature; Phase 1 implements *structural* checks (symbol exists,
    is callable, has docstring). Detailed parameter/type/return matching
    requires either an embedded ADR signature record (deferred) or
    reflective comparison against a sibling test fixture.

    For Phase 1, this returns ``(True, "")`` unconditionally for
    callables that resolve in code. The function is kept as a public
    contract so b-class checks can be tightened in Phase 2 without
    changing the ``classify_repo`` algorithm shape.

    Args:
        obj: The griffe object resolved at ``adr.governs.contracts[i]``.
        adr: The ADR citing the symbol.

    Returns:
        ``(matched, reason)``. ``matched=True`` means the signature is
        acceptable. ``matched=False`` means a b-class finding should be
        emitted; ``reason`` describes the disagreement.
    """
    # Phase 1: trust the dotted-path resolution. Phase 2 will compare
    # against an explicit ADR signature record.
    _ = adr  # reserved for Phase-2 signature comparison
    if isinstance(obj, griffe.Function):
        if not obj.parameters:
            # Zero-parameter callables are fine
            return True, ""
        return True, ""
    if isinstance(obj, griffe.Class):
        return True, ""
    return True, ""


def _is_callable_like(obj: griffe.Object | griffe.Alias) -> bool:
    return isinstance(obj, griffe.Function | griffe.Class)


def _c_class_finding(
    symbol: str,
    adr: ADRFrontmatter,
    evidence: dict[str, Any],
    code_index: dict[str, griffe.Object | griffe.Alias],
) -> Finding:
    """Build a c1/c2/c3 finding based on git evidence."""
    if evidence.get("was_present_then_deleted"):
        drift = DriftClass.C1
        msg = (
            f"symbol '{symbol}' cited by ADR-{adr.adr:03d} was deleted in "
            f"{evidence.get('deleting_commit_sha', 'unknown')} "
            f"(author {evidence.get('deleting_commit_author', 'unknown')}). "
            "Per ADR-042 §8: if ADR is Accepted, restore the symbol or "
            "supersede the ADR."
        )
        fix = "restore the deleted symbol or update the ADR to match code"
    elif evidence.get("never_existed"):
        drift = DriftClass.C2
        near = _nearest_existing_symbol(symbol, code_index)
        msg = (
            f"symbol '{symbol}' cited by ADR-{adr.adr:03d} never existed in "
            "git history (likely doc hallucination)" + (f"; did you mean '{near}'?" if near else "")
        )
        fix = f"remove or correct the citation; nearest match: {near}" if near else "remove or correct the citation"
    else:
        drift = DriftClass.C3
        msg = (
            f"symbol '{symbol}' cited by ADR-{adr.adr:03d}: mixed git "
            "evidence (the dotted path matched a different kind of symbol "
            "historically). Manual review required."
        )
        fix = "review git history manually and decide which side is wrong"

    return Finding(
        rule_id=f"doc-drift.{drift.value}",
        severity=Severity.ERROR,
        drift_class=drift,
        file=f"docs/adr/ADR-{adr.adr:03d}.md",
        symbol=symbol,
        message=msg,
        suggested_fix=fix,
        git_evidence=str(evidence),
    )


def _nearest_existing_symbol(symbol: str, code_index: dict[str, griffe.Object | griffe.Alias]) -> str | None:
    """Return the nearest existing symbol by Levenshtein-on-segments distance.

    Returns ``None`` when no symbol is within edit distance 3.
    """
    best: tuple[int, str] | None = None
    target = symbol.split(".")
    for candidate in code_index:
        cand_segs = candidate.split(".")
        d = _levenshtein(target, cand_segs)
        if d > 3:
            continue
        if best is None or d < best[0]:
            best = (d, candidate)
    return best[1] if best else None


def _levenshtein(a: list[str], b: list[str]) -> int:
    """Standard Levenshtein distance on lists (no external deps)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ai in enumerate(a, start=1):
        cur = [i]
        for j, bj in enumerate(b, start=1):
            cost = 0 if ai == bj else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------------------
# Reverse-pass helpers
# ---------------------------------------------------------------------------


def is_public(obj: griffe.Object | griffe.Alias) -> bool:
    """ADR-042 §9.4 public-symbol definition: ``__all__`` if present, else
    not-leading-underscore.
    """
    if not hasattr(obj, "name"):
        return False
    parent = getattr(obj, "parent", None)
    if parent is not None and hasattr(parent, "exports") and parent.exports:
        return obj.name in parent.exports
    return not obj.name.startswith("_")


def _check_all_presence(code_index: dict[str, griffe.Object | griffe.Alias]) -> list[Finding]:
    """Phase-1 warning when a public module lacks ``__all__`` (§9.4).

    Promotes to ``error`` from Phase 2 onwards (manager default).
    """
    findings: list[Finding] = []
    seen_modules: set[str] = set()
    for dotted_path, obj in code_index.items():
        if not isinstance(obj, griffe.Module):
            continue
        if dotted_path in seen_modules:
            continue
        seen_modules.add(dotted_path)
        if obj.name.startswith("_"):
            continue
        if not obj.exports:
            findings.append(
                Finding(
                    rule_id="doc-drift.missing-all",
                    severity=Severity.WARNING,
                    drift_class=DriftClass.D,
                    file=_griffe_filepath(obj),
                    symbol=dotted_path,
                    message=(
                        "module has no __all__; Phase 1 reports as warning (promoted to error from Phase 2 onwards)"
                    ),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_history_for_symbol(symbol: str, repo_root: Path) -> dict[str, Any]:
    """Best-effort: ``git log -S`` to detect deletion vs never-existed.

    A more thorough implementation would parse the matching diff hunks
    to differentiate addition vs deletion; this Phase-1 version assumes
    any ``-S`` hit is a deletion and returns the most recent matching
    commit's metadata.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-S", symbol, "--format=%H|%an|%ae|%ad", "--diff-filter=D", "-1"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"never_existed": True}
    if out.returncode != 0:
        return {"never_existed": True}
    line = out.stdout.strip()
    if not line:
        return {"never_existed": True}
    parts = line.split("|", 3)
    return {
        "was_present_then_deleted": True,
        "deleting_commit_sha": parts[0] if parts else None,
        "deleting_commit_author": parts[1] if len(parts) > 1 else None,
    }


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


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def _griffe_filepath(obj: griffe.Object | griffe.Alias) -> str:
    fp = getattr(obj, "filepath", None)
    if fp is None:
        return "<unknown>"
    return str(fp).replace("\\", "/")


def _compute_exit_status(
    findings: list[Finding],
) -> Literal["ok", "warnings", "errors", "crash"]:
    if not findings:
        return "ok"
    if any(f.severity == Severity.ERROR for f in findings):
        return "errors"
    if any(f.severity == Severity.WARNING for f in findings):
        return "warnings"
    return "ok"
