"""Git-trailer validation (ADR-042 §13, ADR-043 §3.3 / §3.4.2).

:func:`run` walks every commit in ``commit_range`` and validates each
commit's trailer block against the union of trailer formats declared by:

* ADR-042 §13.1 — base trailers (``Signed-off-by:``, ``Assisted-by:``,
  ``Fixes:``, ``ADR:``, ``Reviewed-by:``, ``Co-authored-by:``,
  ``Reviewed-locally:``, ``Maintainer-Override:``, ``Human-Override:``).
* ADR-042 §13.2 — ``Assisted-by:`` agent-equality format.
* ADR-043 §3.4.2 — ``Loosening-Approved:`` / ``Loosening-Reason:``.
* ADR-043 §3.3 — ``Governance-Modification-Approved-By:``.

Three layers of enforcement are described by ADR-042 §13.3:

1. ``commit-msg`` git hook (local, fast) — pure regex.
2. Pre-push hook — same regex, on the full unpushed range.
3. CI ``trailer-lint`` job — re-validates every commit in the PR diff.

This module implements layer 1 + 2 (format regex). Layer 3's GitHub
review API cross-check (verify the cited approver actually reviewed) is
out of scope for this PR — see TODO below. The Phase-3 trailer cutoff
described in §13.5 is honoured by accepting ``commit_range`` from the
caller; the caller-side default is "no cutoff" pre-TC-1H.8 (Q1B.5.1
manager default).

References
----------
ADR-042 §13 — trailer conventions (authoritative).
ADR-042 §13.2 — Assisted-by agent-equality format.
ADR-042 §13.3 — three-layer enforcement.
ADR-042 §13.5 — no-backfill / Phase-3 cutoff.
ADR-042 §9.6 — entry-point signature (``run`` returns ``list[Finding]``).
ADR-043 §3.3 — Governance-Modification-Approved-By trailer.
ADR-043 §3.4.2 — Loosening-Approved / Loosening-Reason trailers.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Final

from scieasy.qa.schemas.frontmatter import ADRFrontmatter
from scieasy.qa.schemas.report import Finding, Severity

__all__ = [
    "TRAILER_PATTERNS",
    "extract_trailers",
    "parse_commits",
    "run",
    "validate_commit",
]


# ---------------------------------------------------------------------------
# Trailer format regexes (ADR-042 §13.1, §13.2; ADR-043 §3.3, §3.4.2)
# ---------------------------------------------------------------------------

#: ``Name <email>`` body shared by Signed-off-by, Reviewed-by, Co-authored-by.
_NAME_EMAIL = r"[^<>]+ <[^<>@\s]+@[^<>@\s]+>"

#: ``Assisted-by: <Runtime>:<ModelID> [tools]`` per ADR-042 §13.2.
_ASSISTED_BY = r"[A-Za-z][A-Za-z0-9_-]*:[A-Za-z0-9._-]+(?: \[.+\])?"

#: ``Fixes: <sha12> ("subject")`` per ADR-042 §13.1.
_FIXES = r"[0-9a-f]{7,40} \(\".+\"\)"

#: ``ADR: ADR-NNN`` per ADR-042 §13.1.
_ADR_REF = r"ADR-\d{1,4}"

#: ``Loosening-Approved: @<handle>`` per ADR-043 §3.4.2.
_LOOSENING_APPROVED = r"@[A-Za-z0-9][A-Za-z0-9_-]*"

#: ``Loosening-Reason: <free-text>`` per ADR-043 §3.4.2.
_LOOSENING_REASON = r".+"

#: ``Governance-Modification-Approved-By: @<Tier2-handle>`` per ADR-043 §3.3.
_GOV_MOD_APPROVED = r"@[A-Za-z0-9][A-Za-z0-9_-]*"

#: Free-text reason bodies for override trailers (§13.1).
_REASON = r".+"

#: Mapping of trailer key → compiled regex for its body.
TRAILER_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "Signed-off-by": re.compile(rf"^{_NAME_EMAIL}$"),
    "Assisted-by": re.compile(rf"^{_ASSISTED_BY}$"),
    "Fixes": re.compile(rf"^{_FIXES}$"),
    "ADR": re.compile(rf"^{_ADR_REF}$"),
    "Reviewed-by": re.compile(rf"^{_NAME_EMAIL}$"),
    "Co-authored-by": re.compile(rf"^{_NAME_EMAIL}$"),
    "Reviewed-locally": re.compile(rf"^{_REASON}$"),
    "Maintainer-Override": re.compile(rf"^{_REASON}$"),
    "Human-Override": re.compile(rf"^{_REASON}$"),
    "Loosening-Approved": re.compile(rf"^{_LOOSENING_APPROVED}$"),
    "Loosening-Reason": re.compile(rf"^{_LOOSENING_REASON}$"),
    "Governance-Modification-Approved-By": re.compile(rf"^{_GOV_MOD_APPROVED}$"),
}

#: Trailer keys recognised by ``git interpret-trailers``. Anything else
#: appearing in the trailer block is reported as ``trailer-lint.unknown-key``
#: at WARNING severity.
_KNOWN_TRAILER_KEYS: Final[frozenset[str]] = frozenset(TRAILER_PATTERNS)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    repo_root: Path | None = None,
    *,
    commit_range: str = "HEAD~1..HEAD",
) -> list[Finding]:
    """Validate git trailers on the specified commit range.

    Args:
        repo_root: Repository root (defaults to ``Path.cwd()``).
        commit_range: Git revision range, e.g. ``"main..HEAD"`` or a
            single SHA.

    Returns:
        Flat list of :class:`Finding`. Empty when every commit in the
        range carries well-formed trailers.

    Notes
    -----
    Phase-3 trailer cutoff (§13.5) is the caller's responsibility — pass
    a ``commit_range`` that begins at the Phase-3 boundary commit. Pre-
    TC-1H.8 the caller default is "no cutoff" (Q1B.5.1 manager default);
    once TC-1H.8 lands and `docs/audit/commit-log.jsonl` carries the
    cutoff SHA, the CI workflow will read it.
    """
    root = repo_root or Path.cwd()
    findings: list[Finding] = []

    # Load Accepted ADR refs to validate ``ADR:`` trailers resolve. We do
    # this lazily — a missing ADR table is treated as "no validation" so
    # the tool stays operable in a fresh checkout.
    accepted_adrs = _load_accepted_adr_refs(root)
    glob_to_adrs = _build_glob_to_adrs(root)

    try:
        commits = parse_commits(root, commit_range)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        findings.append(
            Finding(
                rule_id="trailer-lint.git-failed",
                severity=Severity.ERROR,
                file=str(root),
                message=f"failed to enumerate commits in {commit_range!r}: {exc}",
            )
        )
        return findings

    for commit in commits:
        findings.extend(
            validate_commit(
                commit,
                accepted_adrs=accepted_adrs,
                glob_to_adrs=glob_to_adrs,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Commit enumeration
# ---------------------------------------------------------------------------


def parse_commits(repo_root: Path, commit_range: str) -> list[dict[str, str | list[str]]]:
    """Return one dict per commit in ``commit_range``.

    The dict has shape::

        {
            "sha": str,                 # 40-char hex
            "author_email": str,
            "subject": str,
            "body": str,                # full commit message body
            "files": list[str],         # paths modified by this commit
        }

    Implementation uses ``git log --format=%x1f...`` with a sentinel field
    separator to avoid quoting hazards. ``git log --name-only`` would mix
    file lists into the same stream — we instead make a per-commit
    ``git show --name-only`` call. Cheap on small ranges; for the audit's
    intended usage (one PR diff) this is bounded.
    """
    log = subprocess.run(
        ["git", "log", commit_range, "--format=%H%x1f%ae%x1f%s%x1f%B%x1e"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if log.returncode != 0:
        # Empty range or non-existent ref. Phase-1 behaviour: surface as
        # a soft error and let the caller decide.
        raise subprocess.SubprocessError(log.stderr.strip() or f"git log failed for {commit_range!r}")

    commits: list[dict[str, str | list[str]]] = []
    raw = log.stdout
    if not raw.strip():
        return commits

    for entry in raw.split("\x1e"):
        entry = entry.strip("\n")
        if not entry:
            continue
        parts = entry.split("\x1f", 3)
        if len(parts) < 4:
            continue
        sha, author_email, subject, body = parts
        files = _git_show_files(repo_root, sha)
        commits.append(
            {
                "sha": sha,
                "author_email": author_email,
                "subject": subject,
                "body": body,
                "files": files,
            }
        )
    return commits


def _git_show_files(repo_root: Path, sha: str) -> list[str]:
    """Return the list of files modified by ``sha`` (best-effort)."""
    try:
        out = subprocess.run(
            ["git", "show", "--name-only", "--format=", sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Trailer extraction
# ---------------------------------------------------------------------------


def extract_trailers(message: str) -> list[tuple[str, str]]:
    """Return the ``(key, value)`` pairs from a commit message trailer block.

    A trailer block is the final contiguous run of ``Key: Value`` lines
    separated from the body by at least one blank line. This mirrors
    ``git interpret-trailers --parse`` semantics without shelling out.
    """
    lines = message.rstrip().splitlines()
    if not lines:
        return []
    # Walk upward from the bottom collecting trailer lines until we hit
    # a blank line. Lines that don't match ``Key: Value`` invalidate the
    # whole block — once we see one, we stop accumulating (the block is
    # what we have so far).
    trailers: list[tuple[str, str]] = []
    for line in reversed(lines):
        if not line.strip():
            break
        m = re.match(r"^([A-Za-z][A-Za-z0-9-]*):\s*(.*)$", line)
        if not m:
            # Non-trailer line before reaching a blank: the block doesn't
            # actually start where we thought. Reset and bail.
            trailers.clear()
            break
        trailers.append((m.group(1), m.group(2)))
    trailers.reverse()
    return trailers


# ---------------------------------------------------------------------------
# Per-commit validation
# ---------------------------------------------------------------------------


def validate_commit(
    commit: dict[str, str | list[str]],
    *,
    accepted_adrs: set[int],
    glob_to_adrs: dict[str, set[int]],
) -> list[Finding]:
    """Return findings for a single commit's trailer block.

    Args:
        commit: Output of :func:`parse_commits`.
        accepted_adrs: Set of Accepted ADR numbers used to validate
            ``ADR:`` trailer references resolve to real ADRs.
        glob_to_adrs: Map of ``governs.files`` glob → ADR set used by
            the ``ADR:`` applicability check (Q1B.5.2: glob-based via
            closure 1B.4).

    Returns:
        Flat list of findings; empty when the commit's trailers are
        fully valid.
    """
    findings: list[Finding] = []
    sha = str(commit["sha"])
    subject = str(commit["subject"])
    body = str(commit["body"])
    files = list(commit["files"]) if isinstance(commit["files"], list) else []

    trailers = extract_trailers(body)
    trailer_keys = {k for k, _ in trailers}

    # ── Layer 1: every trailer's value matches its regex ───────────────
    for key, value in trailers:
        pat = TRAILER_PATTERNS.get(key)
        if pat is None:
            findings.append(
                Finding(
                    rule_id="trailer-lint.unknown-key",
                    severity=Severity.WARNING,
                    file=f"<commit {sha[:7]}>",
                    symbol=sha,
                    message=f"unknown trailer key {key!r}; not listed in ADR-042 §13.1 or ADR-043 §3.3/§3.4.2",
                    git_evidence=f"{key}: {value}",
                )
            )
            continue
        if not pat.match(value):
            findings.append(
                Finding(
                    rule_id=f"trailer-lint.invalid-{key.lower()}",
                    severity=Severity.ERROR,
                    file=f"<commit {sha[:7]}>",
                    symbol=sha,
                    message=(f"{key} trailer body does not match required format (pattern: {pat.pattern!r})"),
                    git_evidence=f"{key}: {value}",
                    suggested_fix=_format_hint_for(key),
                )
            )

    # ── Required-trailer checks (per author class) ─────────────────────
    is_agent = _is_agent_authored(commit)
    if is_agent and "Assisted-by" not in trailer_keys:
        findings.append(
            Finding(
                rule_id="trailer-lint.missing-assisted-by",
                severity=Severity.ERROR,
                file=f"<commit {sha[:7]}>",
                symbol=sha,
                message=(
                    "agent-authored commit is missing 'Assisted-by:' trailer "
                    "(required by ADR-042 §13.1 + §13.3 layer 1)"
                ),
                git_evidence=str(commit.get("author_email", "")),
            )
        )

    # ── Fixes: requirement on bug-fix commits ──────────────────────────
    if _looks_like_fix(subject) and "Fixes" not in trailer_keys:
        findings.append(
            Finding(
                rule_id="trailer-lint.missing-fixes",
                severity=Severity.WARNING,
                file=f"<commit {sha[:7]}>",
                symbol=sha,
                message=(
                    "fix(...) commit is missing 'Fixes:' trailer; the §13.4 "
                    "defect-causality graph cannot include this commit"
                ),
                suggested_fix='append: Fixes: <sha12> ("subject of broken commit")',
            )
        )

    # ── ADR: requirement (glob-based applicability per Q1B.5.2) ────────
    relevant_adrs = _relevant_adrs_for_files(files, glob_to_adrs)
    if relevant_adrs and "ADR" not in trailer_keys:
        findings.append(
            Finding(
                rule_id="trailer-lint.missing-adr",
                severity=Severity.ERROR,
                file=f"<commit {sha[:7]}>",
                symbol=sha,
                message=(
                    f"commit touches files governed by Accepted ADR(s) "
                    f"{sorted(relevant_adrs)} but lacks an 'ADR:' trailer "
                    "(ADR-042 §13.1)"
                ),
                suggested_fix=f"append: ADR: ADR-{min(relevant_adrs):03d}",
            )
        )

    # ── ADR: target resolves to a real Accepted ADR ───────────────────
    for key, value in trailers:
        if key != "ADR":
            continue
        m = re.match(r"^ADR-(\d{1,4})$", value)
        if not m:
            continue
        adr_num = int(m.group(1))
        if accepted_adrs and adr_num not in accepted_adrs:
            findings.append(
                Finding(
                    rule_id="trailer-lint.adr-not-accepted",
                    severity=Severity.WARNING,
                    file=f"<commit {sha[:7]}>",
                    symbol=sha,
                    message=(
                        f"ADR: trailer cites ADR-{adr_num:03d} but no Accepted "
                        "ADR with that number was found in docs/adr/"
                    ),
                    git_evidence=f"ADR: ADR-{adr_num:03d}",
                )
            )

    # TODO(#1153-ext): wire layer-3 GitHub review API cross-check
    #   Out of scope per ADR-042 §13.3 layer 3 (CI gate, not local).
    #   Followup: open as 1B.5-ext after this PR merges; the check
    #   requires GITHUB_TOKEN + PR context which lives in CI workflow.

    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_agent_authored(commit: dict[str, str | list[str]]) -> bool:
    """Best-effort heuristic: any of the message line, ``--agent`` author
    email contains a known agent token, OR the message body already carries
    an ``Assisted-by:`` trailer (in which case the commit identifies itself
    as agent-authored and other layers can apply).
    """
    email = str(commit.get("author_email", "")).lower()
    body = str(commit.get("body", "")).lower()
    if any(token in email for token in ("claude", "codex", "cursor", "aider", "gemini", "agent[bot]")):
        return True
    return "assisted-by:" in body


def _looks_like_fix(subject: str) -> bool:
    """Heuristic: conventional-commit ``fix(...)`` prefix."""
    return bool(re.match(r"^fix(\([^)]*\))?:", subject.strip()))


def _format_hint_for(key: str) -> str:
    """Return a short example body to nudge the committer toward the right format."""
    hints = {
        "Signed-off-by": "Signed-off-by: Name <email@example.org>",
        "Assisted-by": "Assisted-by: Claude:claude-opus-4-7",
        "Fixes": 'Fixes: abc1234 ("subject of broken commit")',
        "ADR": "ADR: ADR-042",
        "Reviewed-by": "Reviewed-by: Name <email@example.org>",
        "Co-authored-by": "Co-authored-by: Name <email@example.org>",
        "Reviewed-locally": "Reviewed-locally: trivial typo fix",
        "Maintainer-Override": "Maintainer-Override: emergency hotfix; see issue #N",
        "Human-Override": "Human-Override: documented exemption per ADR-042 §25.X",
        "Loosening-Approved": "Loosening-Approved: @maintainer",
        "Loosening-Reason": "Loosening-Reason: revert breaking lint rule until tests rewritten",
        "Governance-Modification-Approved-By": "Governance-Modification-Approved-By: @maintainer",
    }
    return hints.get(key, "see ADR-042 §13.1")


def _relevant_adrs_for_files(files: list[str], glob_to_adrs: dict[str, set[int]]) -> set[int]:
    """Return ADR numbers covering any of ``files`` via their governs.files.

    Q1B.5.2 manager default: ADR-trailer applicability is glob-based,
    resolved against the closure 1B.4 outputs. We re-use a simple
    fnmatch-style match here; the canonical closure resolution lives in
    :mod:`scieasy.qa.audit.closure` and is intentionally not imported (to
    avoid a heavyweight dependency on this fast-path lint).
    """
    relevant: set[int] = set()
    if not files or not glob_to_adrs:
        return relevant
    for f in files:
        for glob, adrs in glob_to_adrs.items():
            if _fnmatch_simple(f, glob):
                relevant.update(adrs)
    return relevant


def _fnmatch_simple(path: str, glob: str) -> bool:
    """``fnmatch`` variant that recognises ``**`` as cross-separator."""
    glob_norm = glob.replace("\\", "/")
    path_norm = path.replace("\\", "/")
    if "*" not in glob_norm and "?" not in glob_norm:
        return path_norm == glob_norm
    pattern = re.escape(glob_norm)
    pattern = pattern.replace(re.escape("**"), ".*")
    pattern = pattern.replace(re.escape("*"), "[^/]*")
    pattern = pattern.replace(re.escape("?"), "[^/]")
    return re.fullmatch(pattern, path_norm) is not None


# ---------------------------------------------------------------------------
# ADR lookups
# ---------------------------------------------------------------------------


def _load_accepted_adr_refs(repo_root: Path) -> set[int]:
    """Return the set of Accepted ADR numbers under ``docs/adr/``."""
    # Import here to keep the module's import surface minimal at top-level
    # (the closure module is heavyweight; we use only one helper).
    from scieasy.qa.audit.closure import load_accepted_adrs

    try:
        adrs = load_accepted_adrs(repo_root)
    except (FileNotFoundError, OSError):
        return set()
    return {int(a.adr) for a in adrs}


def _build_glob_to_adrs(repo_root: Path) -> dict[str, set[int]]:
    """Index ``governs.files`` globs to the ADR numbers that own them."""
    from scieasy.qa.audit.closure import load_accepted_adrs

    try:
        adrs = load_accepted_adrs(repo_root)
    except (FileNotFoundError, OSError):
        return {}
    out: dict[str, set[int]] = {}
    for adr in adrs:
        if not isinstance(adr, ADRFrontmatter):
            continue
        for glob in adr.governs.files:
            out.setdefault(glob, set()).add(int(adr.adr))
        # Also seed module-derived globs so commits touching governed
        # python packages trigger the ADR: requirement.
        for module in adr.governs.modules:
            module_glob = "src/" + module.replace(".", "/") + "/**"
            out.setdefault(module_glob, set()).add(int(adr.adr))
    return out
