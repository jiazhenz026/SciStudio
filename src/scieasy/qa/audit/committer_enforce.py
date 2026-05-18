"""Verify recent agent commits were made via ``scripts/committer.py``
(ADR-042 §16).

:func:`check` cross-references the git log against
``docs/audit/commit-log.jsonl`` (ADR-042 §16.5) — the append-only audit
trail written by :mod:`scripts.committer`. Any agent-authored commit
present in ``git log`` but absent from the JSONL is reported as a
``committer-enforce.missing-log-entry`` finding.

The :mod:`scripts.committer` shim (TC-1H.8) is not yet shipped at the
time of this PR; per Phase 1 investigation default Q1B.6.1 we therefore
*degrade gracefully* when the log file does not exist:

* No log file → emit one ``committer-enforce.no-log-file`` *info*
  finding and return (the audit's exit status remains ``ok``).
* Empty log file → same behaviour (treated as not-yet-bootstrapped).

Once TC-1H.8 lands the file becomes mandatory; promoting the missing-
log severity to ERROR will be a single-line follow-up.

References
----------
ADR-042 §16.1 — purpose statement.
ADR-042 §16.2 — agent-runtime detection (env-var contract).
ADR-042 §16.5 — JSONL schema (see :class:`CommitLogEntry`).
ADR-042 §21.3 — pre-commit invocation surface.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import ValidationError

from scieasy.qa.schemas.report import CommitLogEntry, Finding, Severity

__all__ = ["LOG_PATH_REL", "check", "load_commit_log"]


#: Path to the canonical append-only commit log, relative to repo root.
LOG_PATH_REL = "docs/audit/commit-log.jsonl"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check(repo_root: Path | None = None) -> list[Finding]:
    """Verify every agent-authored commit appears in the commit log.

    Args:
        repo_root: Repository root (defaults to ``Path.cwd()``).

    Returns:
        List of findings; empty when the log fully covers agent commits.
    """
    root = repo_root or Path.cwd()
    findings: list[Finding] = []

    log_path = root / LOG_PATH_REL
    if not log_path.is_file():
        findings.append(
            Finding(
                rule_id="committer-enforce.no-log-file",
                severity=Severity.INFO,
                file=LOG_PATH_REL,
                message=(
                    f"{LOG_PATH_REL} does not exist; the audit log is created "
                    "by scripts/committer.py (TC-1H.8, not yet shipped). "
                    "Pre-bootstrap behaviour: skip enforcement. Promotion to "
                    "ERROR follows TC-1H.8 landing."
                ),
            )
        )
        return findings

    try:
        entries = load_commit_log(log_path)
    except ValueError as exc:
        findings.append(
            Finding(
                rule_id="committer-enforce.malformed-log",
                severity=Severity.ERROR,
                file=LOG_PATH_REL,
                message=f"failed to parse {LOG_PATH_REL}: {exc}",
            )
        )
        return findings

    if not entries:
        findings.append(
            Finding(
                rule_id="committer-enforce.empty-log",
                severity=Severity.INFO,
                file=LOG_PATH_REL,
                message=(
                    f"{LOG_PATH_REL} is empty; pre-bootstrap behaviour: skip "
                    "enforcement (no agent commits to cross-check)."
                ),
            )
        )
        return findings

    known_shas = {entry.sha for entry in entries}
    agent_commits = _enumerate_agent_commits(root)
    for sha, author_email, subject in agent_commits:
        if not any(sha.startswith(known) or known.startswith(sha) for known in known_shas):
            findings.append(
                Finding(
                    rule_id="committer-enforce.missing-log-entry",
                    severity=Severity.ERROR,
                    file=LOG_PATH_REL,
                    symbol=sha,
                    message=(
                        f"agent-authored commit {sha[:7]} '{subject}' is not "
                        f"recorded in {LOG_PATH_REL}; was the commit made with "
                        "scripts/committer.py?"
                    ),
                    git_evidence=author_email,
                    suggested_fix=(
                        "re-author the commit via 'python scripts/committer.py "
                        'commit -m "..."\' so the JSONL line is appended'
                    ),
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------


def load_commit_log(log_path: Path) -> list[CommitLogEntry]:
    """Parse ``commit-log.jsonl`` into validated :class:`CommitLogEntry` records.

    Each non-blank line is parsed with :func:`json.loads` then validated
    via :meth:`CommitLogEntry.model_validate`. The first malformed line
    raises :exc:`ValueError` carrying the line number for fast diagnosis.

    Args:
        log_path: Absolute path to ``docs/audit/commit-log.jsonl``.

    Returns:
        Ordered list of parsed entries (oldest first by file order).
    """
    entries: list[CommitLogEntry] = []
    text = log_path.read_text(encoding="utf-8")
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {lineno}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"line {lineno}: expected JSON object, got {type(obj).__name__}")
        try:
            entries.append(CommitLogEntry.model_validate(obj))
        except ValidationError as exc:
            raise ValueError(f"line {lineno}: {exc}") from exc
    return entries


# ---------------------------------------------------------------------------
# Git enumeration
# ---------------------------------------------------------------------------


def _enumerate_agent_commits(repo_root: Path) -> list[tuple[str, str, str]]:
    """Return ``(sha, author_email, subject)`` for every agent-authored
    commit reachable from ``HEAD``.

    Phase-1 heuristic for "agent-authored":

    * author email contains one of the known runtime tokens
      (``claude``, ``codex``, ``cursor``, ``aider``, ``gemini``,
      ``agent[bot]``); OR
    * commit message body carries an ``Assisted-by:`` trailer.

    We accept that this heuristic over-flags (e.g., a human named
    "Claude" is misclassified) — the ``humans.yml`` registry (ADR-042
    §25) is the authoritative tier source. Pre-bootstrap (no registry
    yet), the heuristic is the only signal available. Once §25 lands,
    the registry lookup happens here.

    The Phase-3 cutoff (§13.5) is not applied here either — TC-1H.8
    will plumb the cutoff SHA through the commit log itself.
    """
    try:
        out = subprocess.run(
            ["git", "log", "--format=%H%x1f%ae%x1f%s%x1f%B%x1e"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []

    result: list[tuple[str, str, str]] = []
    for raw in out.stdout.split("\x1e"):
        raw = raw.strip("\n")
        if not raw:
            continue
        parts = raw.split("\x1f", 3)
        if len(parts) < 4:
            continue
        sha, email, subject, body = parts
        email_lc = email.lower()
        body_lc = body.lower()
        is_agent = any(t in email_lc for t in ("claude", "codex", "cursor", "aider", "gemini", "agent[bot]")) or (
            "assisted-by:" in body_lc
        )
        if is_agent:
            result.append((sha, email, subject))
    return result
