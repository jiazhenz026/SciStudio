"""PR commit-order test-first verifier (TC-1F.2, ADR-043 §4.3.2).

The public entry point :func:`verify_ordering` examines the commit chain
of one pull request and emits a finding when a new ``test_X`` was *not*
introduced before the implementation of ``X``. The heuristic is
intentionally conservative — per ADR-043 §4.1 "test-name→symbol mapping
is best-effort" — and **report-only by default**: findings carry
:data:`scieasy.qa.schemas.report.Severity.WARNING` unless the caller
sets ``enforce=True`` (the CLI shim sets that only when the GitHub
workflow detects the ``tdd-required`` label on the PR).

The verifier deliberately stays at the metadata layer:

1. Pull the commit list for the PR via ``gh api``.
2. For each commit, list added files (``git diff --name-only --diff-filter=A``).
3. Pair every newly added ``tests/**/test_<stem>.py`` with the earliest
   commit that added a matching ``src/**/<stem>.py`` (or that introduced
   a symbol whose name overlaps with ``<stem>``).
4. If the test commit's position in the PR's commit list is **later** than
   the implementation commit's position, emit a finding.

The Phase-1 implementation does NOT run pytest at parent commits to
confirm the new test actually failed — that doubles CI time on every
PR. The heuristic flags the order violation; reviewers run the failure
check manually if the heuristic catches something interesting.

Exemption — ``Backfill-Test:`` trailer
--------------------------------------

Per ADR-043 §4.3.2 last paragraph, tests added for **existing** code
carry a ``Backfill-Test:`` trailer in the commit message; those commits
are skipped by the order check.

Subprocess boundary
-------------------

All ``gh``/``git`` invocations go through :func:`_run_capture`, which is
a thin wrapper around :func:`subprocess.run` exposed for unit-test
patching. Tests under ``tests/qa/test_test_first_check.py`` monkeypatch
this single seam to feed synthetic commit graphs into the verifier.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Sequence

from scieasy.qa.schemas.report import Finding, Severity

#: Trailer that exempts a commit from the order check (§4.3.2 carve-out).
_BACKFILL_TRAILER_RE = re.compile(r"^Backfill-Test:\s+", re.IGNORECASE | re.MULTILINE)

#: Regex extracting the stem from ``tests/**/test_<stem>.py`` paths.
_TEST_FILE_RE = re.compile(r"^tests/.*test_([A-Za-z0-9_]+)\.py$")

#: Regex extracting the stem from ``src/**/<stem>.py`` paths.
_SRC_FILE_RE = re.compile(r"^src/.*/([A-Za-z0-9_]+)\.py$")


def _run_capture(args: Sequence[str]) -> tuple[int, str, str]:
    """Run ``args`` capturing stdout/stderr; returns ``(rc, stdout, stderr)``.

    Single subprocess seam — unit tests monkeypatch this name. UTF-8
    decoding with ``replace`` keeps the function safe on Windows zh-CN
    consoles (same rationale as ``scripts/audit/temp_review.py``).
    """
    if not args:
        return 2, "", "no command"
    if shutil.which(args[0]) is None:
        return 2, "", f"{args[0]} not on PATH"
    proc = subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


# --------------------------------------------------------------------------- #
# Internal helpers (subprocess-bound; unit-tested via patched _run_capture)   #
# --------------------------------------------------------------------------- #


def _fetch_pr_commits(pr_number: int, repo: str) -> list[dict[str, object]]:
    """Return ``[{sha, message}, …]`` in PR order (oldest first)."""
    rc, out, _err = _run_capture(
        [
            "gh",
            "api",
            f"repos/{repo}/pulls/{pr_number}/commits",
            "--paginate",
            "-q",
            ".[] | {sha: .sha, message: .commit.message}",
        ]
    )
    if rc != 0 or not out.strip():
        return []
    commits: list[dict[str, object]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            commits.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return commits


def _files_added_in_commit(sha: str) -> list[str]:
    """Return file paths added (``A``) in commit ``sha``."""
    rc, out, _ = _run_capture(["git", "show", "--name-only", "--diff-filter=A", "--format=", sha])
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _has_backfill_trailer(commit_message: object) -> bool:
    """Return True iff the commit message contains a ``Backfill-Test:`` trailer."""
    if not isinstance(commit_message, str):
        return False
    return bool(_BACKFILL_TRAILER_RE.search(commit_message))


def _extract_test_stem(path: str) -> str | None:
    """Return the test-stem of ``tests/**/test_<stem>.py`` or None."""
    m = _TEST_FILE_RE.match(path)
    return m.group(1) if m else None


def _extract_src_stem(path: str) -> str | None:
    """Return the module-stem of ``src/**/<stem>.py`` or None."""
    m = _SRC_FILE_RE.match(path)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# Heuristic core                                                              #
# --------------------------------------------------------------------------- #


def _build_test_impl_pairs(
    commits: Sequence[dict[str, object]],
) -> list[tuple[int, int, str, str, str]]:
    """Pair each new test stem with its earliest matching impl stem.

    Returns a list of ``(test_idx, impl_idx, stem, test_path, impl_path)``
    tuples where the indices are positions in ``commits`` (oldest = 0).
    """
    # First pass: collect first-seen positions per stem for impl + test files.
    first_test: dict[str, tuple[int, str]] = {}
    first_impl: dict[str, tuple[int, str]] = {}
    for idx, commit in enumerate(commits):
        sha = commit.get("sha")
        if not isinstance(sha, str):
            continue
        added = _files_added_in_commit(sha)
        for path in added:
            t_stem = _extract_test_stem(path)
            if t_stem and t_stem not in first_test:
                first_test[t_stem] = (idx, path)
            s_stem = _extract_src_stem(path)
            if s_stem and s_stem not in first_impl:
                first_impl[s_stem] = (idx, path)
    pairs: list[tuple[int, int, str, str, str]] = []
    for stem, (test_idx, test_path) in first_test.items():
        impl_entry = first_impl.get(stem)
        if impl_entry is None:
            continue  # No impl pair → no order to check.
        impl_idx, impl_path = impl_entry
        pairs.append((test_idx, impl_idx, stem, test_path, impl_path))
    return pairs


def verify_ordering(
    pr_number: int,
    repo: str,
    *,
    enforce: bool = False,
) -> list[Finding]:
    """Heuristic: tests committed before impl in same PR (ADR-043 §4.3.2).

    Parameters
    ----------
    pr_number:
        GitHub PR number.
    repo:
        ``owner/repo`` slug, e.g. ``"zjzcpj/SciEasy"``.
    enforce:
        When ``True``, findings carry :class:`Severity.ERROR`; otherwise
        :class:`Severity.WARNING` (default — report-only per §4.3.2).
        The CLI shim sets ``enforce=True`` only when the GitHub
        workflow detects a ``tdd-required`` label on the PR.

    Returns
    -------
    list[Finding]
        One finding per order violation (impl committed before its
        paired test). Commits carrying a ``Backfill-Test:`` trailer in
        their message are skipped per §4.3.2 carve-out.
    """
    commits = _fetch_pr_commits(pr_number, repo)
    if not commits:
        return []
    # Resolve which commit indices carry the backfill exemption.
    exempt_idx: set[int] = {idx for idx, commit in enumerate(commits) if _has_backfill_trailer(commit.get("message"))}
    severity = Severity.ERROR if enforce else Severity.WARNING
    pairs = _build_test_impl_pairs(commits)
    findings: list[Finding] = []
    for test_idx, impl_idx, stem, test_path, impl_path in pairs:
        if test_idx in exempt_idx or impl_idx in exempt_idx:
            continue
        if test_idx <= impl_idx:
            continue  # Test came first → compliant.
        test_sha_raw = commits[test_idx].get("sha")
        impl_sha_raw = commits[impl_idx].get("sha")
        test_sha = test_sha_raw if isinstance(test_sha_raw, str) else "<unknown>"
        impl_sha = impl_sha_raw if isinstance(impl_sha_raw, str) else "<unknown>"
        findings.append(
            Finding(
                rule_id="TQTF-impl-before-test",
                severity=severity,
                drift_class=None,
                file=test_path,
                line=None,
                symbol=stem,
                message=(
                    f"impl '{impl_path}' added in {impl_sha[:7]} (position "
                    f"{impl_idx}) before its paired test '{test_path}' added "
                    f"in {test_sha[:7]} (position {test_idx}); ADR-043 §4.3.2 "
                    "requires the failing test to land first."
                ),
                suggested_fix=(
                    "Either reorder the commits (interactive rebase), or add a "
                    "``Backfill-Test:`` trailer to the test commit if this is a "
                    "debt-cleanup backfill."
                ),
                git_evidence=f"{impl_sha}<{test_sha}",
            )
        )
    return findings


# TODO(#1144): Genuinely-failing-at-parent verification (run pytest at each
#   test commit's parent and confirm the new test was previously failing).
#   Out of scope per ADR-043 §4.3.2 second paragraph (Phase 1 report-only;
#   verification deferred — doubles CI time and is moot until Phase 3 enforce).
#   Followup: open a fresh issue when Phase 3 cleanup-track work begins.
