"""Bidirectional MAINTAINERS↔governs closure check (ADR-042 §11).

The closure invariant is:

> The union of paths covered by Accepted ADR ``governs.{modules, files}``
> equals the union of paths covered by ``MAINTAINERS`` entries.

This module computes that symmetric difference and returns one
``Finding`` per non-empty side. It also detects shared-ownership semantic
conflicts between multiple ADRs claiming the same file in
``governs.files`` (§11.3.2) using ``agent_editable`` as the conflict
attribute, per Phase 1 investigation default Q1B.4.2.

The module-to-glob expansion lives in :func:`_module_to_paths`. Most
specific match wins per §11.3.1 (mirrors §6.5 MAINTAINERS glob
resolution).

References
----------
ADR-042 §11.1 — statement.
ADR-042 §11.2 — algorithm overview.
ADR-042 §11.3 / §11.3.1 / §11.3.2 — module-to-glob, parent/child
arbitration, cross-ADR shared-ownership semantic conflicts.

Deferred work
-------------
The ADR-044 §12.3 extensions (workflow↔skill, entry-points↔reference,
schemas↔reference, CLI↔reference closure pairs) are NOT in this v1
implementation. Per Phase 1 investigation default Q1B.4.1, they ship in
follow-up sub-PR ``1B.4-ext`` after sub-phase 1D (docs translator) lands.

# TODO(#1140-ext): wire ADR-044 §12.3 closure extensions
#   Out of scope per Phase 1 investigation SUMMARY Q1B.4.1.
#   Followup: open as 1B.4-ext after 1D ships docs translator.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

from scieasy.qa.schemas.frontmatter import ADRFrontmatter, Status
from scieasy.qa.schemas.maintainers import Maintainers
from scieasy.qa.schemas.report import Finding, Severity

__all__ = [
    "check_bidirectional",
    "load_accepted_adrs",
    "load_maintainers",
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check_bidirectional(repo_root: Path) -> list[Finding]:
    """Verify MAINTAINERS↔governs closure across the repo.

    Loads every Accepted ADR's ``governs.{modules, files}`` and compares
    the union of expanded paths against the union of paths covered by
    ``MAINTAINERS`` entries' ``path_glob`` (minus ``excludes``). For
    each path in the symmetric difference, emits one
    :class:`~scieasy.qa.schemas.report.Finding` describing the asymmetry.

    Args:
        repo_root: Repository root (the working tree under audit). Must
            contain ``docs/adr/`` and a top-level ``MAINTAINERS`` file.

    Returns:
        A list of findings. Empty when closure is symmetric.
    """
    findings: list[Finding] = []

    adrs = load_accepted_adrs(repo_root)
    maintainers = load_maintainers(repo_root)

    if maintainers is None:
        findings.append(
            Finding(
                rule_id="closure.no-maintainers-file",
                severity=Severity.ERROR,
                file="MAINTAINERS",
                message=("MAINTAINERS file is missing or unreadable; cannot compute bidirectional closure."),
            )
        )
        return findings

    s_adr_by_owner = _build_adr_path_index(repo_root, adrs)
    s_adr: set[str] = set().union(*s_adr_by_owner.values()) if s_adr_by_owner else set()
    s_maintainers, m_owner_by_path = _build_maintainers_path_index(repo_root, maintainers)

    # ── Forward (ADR → MAINTAINERS) ────────────────────────────────────
    for path in sorted(s_adr - s_maintainers):
        owning_adrs = sorted(adr for adr, paths in s_adr_by_owner.items() if path in paths)
        findings.append(
            Finding(
                rule_id="closure.asymmetric",
                severity=Severity.ERROR,
                file=path,
                message=(f"path governed by Accepted ADR(s) {owning_adrs} but no MAINTAINERS entry covers it"),
                suggested_fix=(f"add a MAINTAINERS entry whose path_glob matches '{path}'"),
            )
        )

    # ── Reverse (MAINTAINERS → ADR) ────────────────────────────────────
    for path in sorted(s_maintainers - s_adr):
        owning_globs = sorted(m_owner_by_path.get(path, []))
        findings.append(
            Finding(
                rule_id="closure.asymmetric",
                severity=Severity.ERROR,
                file=path,
                message=(f"MAINTAINERS entry/entries {owning_globs} covers path not governed by any Accepted ADR"),
                suggested_fix=(
                    "add this path under some Accepted ADR's governs.files "
                    "or governs.modules, OR remove the MAINTAINERS entry "
                    "if the path no longer exists"
                ),
            )
        )

    # ── Shared-ownership semantic conflict (§11.3.2) ───────────────────
    findings.extend(_check_shared_ownership_conflicts(adrs))

    return findings


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_accepted_adrs(repo_root: Path) -> list[ADRFrontmatter]:
    """Load and return every Accepted ADR frontmatter under ``docs/adr/``.

    Args:
        repo_root: Repository root.

    Returns:
        ADR frontmatters whose status is ``Accepted``. ADRs whose
        frontmatter fails to parse are silently skipped (those errors
        are :mod:`~scieasy.qa.audit.frontmatter_lint`'s responsibility).
    """
    accepted: list[ADRFrontmatter] = []
    adr_dir = repo_root / "docs" / "adr"
    if not adr_dir.is_dir():
        return accepted
    for path in sorted(adr_dir.glob("ADR-*.md")):
        try:
            fm = _parse_adr_frontmatter(path)
        except (ValueError, yaml.YAMLError):
            continue
        if fm is None:
            continue
        if fm.status == Status.ACCEPTED:
            accepted.append(fm)
    return accepted


def load_maintainers(repo_root: Path) -> Maintainers | None:
    """Load the top-level ``MAINTAINERS`` YAML file.

    Args:
        repo_root: Repository root.

    Returns:
        Parsed :class:`~scieasy.qa.schemas.maintainers.Maintainers`, or
        ``None`` when the file is absent or malformed.
    """
    path = repo_root / "MAINTAINERS"
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return Maintainers.model_validate(data)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------


def _build_adr_path_index(repo_root: Path, adrs: Iterable[ADRFrontmatter]) -> dict[str, set[str]]:
    """Return ``{adr_ref: {repo-relative-path, ...}}`` for Accepted ADRs.

    Module dotted paths in ``governs.modules`` are expanded to the set of
    ``.py`` files under their package directory via
    :func:`_module_to_paths`. ``governs.files`` entries are taken
    verbatim with simple ``**`` glob expansion against the working tree.
    ``excludes`` are subtracted from the result.
    """
    index: dict[str, set[str]] = {}
    for adr in adrs:
        paths: set[str] = set()
        for module in adr.governs.modules:
            paths.update(_module_to_paths(repo_root, module))
        for file_glob in adr.governs.files:
            paths.update(_glob_to_paths(repo_root, file_glob))
        for excl in adr.governs.excludes:
            paths.difference_update(_glob_to_paths(repo_root, excl))
        index[f"ADR-{adr.adr:03d}"] = paths
    return index


def _build_maintainers_path_index(repo_root: Path, maintainers: Maintainers) -> tuple[set[str], dict[str, list[str]]]:
    """Return ``(all_paths, {path: [path_glob, ...]})`` for MAINTAINERS."""
    all_paths: set[str] = set()
    owner_by_path: dict[str, list[str]] = {}
    for entry in maintainers.entries:
        matched = _glob_to_paths(repo_root, entry.path_glob)
        for excl in entry.excludes:
            matched.difference_update(_glob_to_paths(repo_root, excl))
        for p in matched:
            owner_by_path.setdefault(p, []).append(entry.path_glob)
        all_paths.update(matched)
    return all_paths, owner_by_path


# ---------------------------------------------------------------------------
# Shared-ownership semantic-conflict detector (§11.3.2)
# ---------------------------------------------------------------------------


def _check_shared_ownership_conflicts(
    adrs: list[ADRFrontmatter],
) -> list[Finding]:
    """Detect §11.3.2 ``closure.multi-adr-conflict`` semantic conflicts.

    Per Phase 1 investigation default Q1B.4.2, the conflict-attribute
    source is the ADR's top-level ``agent_editable`` field. Two ADRs
    claiming the same `governs.files` path with disagreeing
    ``agent_editable`` values trigger one warning-level finding per
    conflicting path. Shared ownership with matching ``agent_editable``
    is silent (the additive default).

    # NOTE: governs.contracts (symbol-level) shared-ownership is NOT
    # checked here; per Q1B.4.3 that belongs in doc_drift's d-class.
    """
    findings: list[Finding] = []
    files_to_owners: dict[str, list[ADRFrontmatter]] = {}
    for adr in adrs:
        for path in adr.governs.files:
            files_to_owners.setdefault(path, []).append(adr)
    for path, owners in files_to_owners.items():
        if len(owners) < 2:
            continue
        agent_editable_values = {a.agent_editable.value for a in owners}
        if len(agent_editable_values) > 1:
            joint_refs = sorted(f"ADR-{a.adr:03d}({a.agent_editable.value})" for a in owners)
            findings.append(
                Finding(
                    rule_id="closure.multi-adr-conflict",
                    severity=Severity.WARNING,
                    file=path,
                    message=(f"shared-ownership semantic conflict on agent_editable: jointly governed by {joint_refs}"),
                    suggested_fix=(
                        "align agent_editable across the jointly-governing ADRs, or move the file to a single owner"
                    ),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Module-to-glob + glob-to-paths helpers
# ---------------------------------------------------------------------------


def _module_to_paths(repo_root: Path, dotted: str) -> set[str]:
    """Expand a dotted module path to the set of ``.py`` files it covers.

    The convention (ADR-042 §11.3): ``scieasy.qa.schemas`` resolves to
    every ``.py`` under ``src/scieasy/qa/schemas/``, including its
    ``__init__.py``. Submodule packages match recursively.

    Args:
        repo_root: Repository root.
        dotted: Dotted module path (e.g. ``"scieasy.qa.audit"``).

    Returns:
        Set of repo-relative ``.py`` paths covered by the module. Empty
        set when the module is not present on disk.
    """
    rel = Path(*dotted.split("."))
    candidates = [
        repo_root / "src" / rel,
        repo_root / rel,
    ]
    results: set[str] = set()
    for candidate in candidates:
        if candidate.is_dir():
            for py in candidate.rglob("*.py"):
                results.add(str(py.relative_to(repo_root)).replace("\\", "/"))
        elif candidate.with_suffix(".py").is_file():
            single = candidate.with_suffix(".py")
            results.add(str(single.relative_to(repo_root)).replace("\\", "/"))
    return results


def _glob_to_paths(repo_root: Path, glob: str) -> set[str]:
    """Expand a repo-relative glob to its current matching paths.

    Handles ``**`` (recursive), ``*`` (segment-wise), ``?``, and
    literal paths uniformly via :func:`pathlib.Path.rglob`. Non-existent
    literal paths return an empty set (treated as a missing-coverage
    finding by the caller).
    """
    glob_norm = glob.replace("\\", "/")
    if "*" not in glob_norm and "?" not in glob_norm:
        single = repo_root / glob_norm
        if single.is_file():
            return {glob_norm}
        if single.is_dir():
            return {str(p.relative_to(repo_root)).replace("\\", "/") for p in single.rglob("*") if p.is_file()}
        # Literal that doesn't currently exist — return as-is so
        # closure surfaces it as MAINTAINERS-side asymmetry (a stale
        # entry that points at deleted code).
        return {glob_norm}

    matched: set[str] = set()
    # Walk every tracked file and fnmatch against the glob. We don't
    # use Path.rglob with the glob directly because it has different
    # `**` semantics across platforms.
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        # Skip .git internals (huge + irrelevant)
        try:
            rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue
        if rel_path.startswith(".git/"):
            continue
        if _fnmatch_recursive(rel_path, glob_norm):
            matched.add(rel_path)
    return matched


def _fnmatch_recursive(path: str, glob: str) -> bool:
    """fnmatch variant that treats ``**`` as recursive across separators.

    Standard :func:`fnmatch.fnmatch` does not distinguish ``*`` from
    ``**``. We pre-translate ``**`` to a sentinel that consumes ``/``
    too, then fall back to fnmatch on the rest.
    """
    # Convert ``**`` → ``.*``  and ``*`` → ``[^/]*`` for regex match.
    import re

    pattern = re.escape(glob)
    pattern = pattern.replace(re.escape("**"), ".*")
    pattern = pattern.replace(re.escape("*"), "[^/]*")
    pattern = pattern.replace(re.escape("?"), "[^/]")
    return re.fullmatch(pattern, path) is not None


# ---------------------------------------------------------------------------
# Frontmatter parsing (lightweight; full validation lives in frontmatter_lint)
# ---------------------------------------------------------------------------


def _parse_adr_frontmatter(path: Path) -> ADRFrontmatter | None:
    """Extract the YAML frontmatter block and validate it as ADRFrontmatter.

    Returns ``None`` when the file has no frontmatter delimiters. Raises
    ``ValueError`` / ``yaml.YAMLError`` on malformed frontmatter (caller
    decides what to do).
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    data = yaml.safe_load(block)
    if not isinstance(data, dict):
        return None
    return ADRFrontmatter.model_validate(data)
