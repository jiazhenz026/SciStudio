"""CI-side authoritative governance-modification check (ADR-043 §3.3 Tool 2).

This is the CI half of the §3.3 authority split — it runs inside the
``.github/workflows/governance-modification.yml`` workflow (Phase 1E
Sub-PR 2 deliverable), where it has a ``GITHUB_TOKEN`` and can call the
GitHub REST API for authoritative review state.

Entry-point (ADR-043 §4.7 audit fix F14)::

    verify_governance_pr(pr_number: int, repo: str) -> CheckResult

The function is the sole authoritative approval verifier in the regime;
:mod:`scieasy.qa.governance.mod_guard` is best-effort local guardrail.

Logic (ADR-043 §3.3 Tool 2):

1. List files in the PR (``GET /repos/{owner}/{repo}/pulls/{n}/files``).
2. Match against ``.governance-paths.yaml``.
3. Extract ``Governance-Modification-Approved-By:`` trailers from each
   commit in the PR (``GET /repos/{owner}/{repo}/pulls/{n}/commits``).
4. For each cited handle:
   - Verify handle is registered as Tier-2 in
     ``docs/identity/humans.yml``.
   - Verify GitHub review state for the handle is ``APPROVED`` (not
     stale) via ``GET /repos/{owner}/{repo}/pulls/{n}/reviews``.
   - Verify CODEOWNERS lists the cited handle for the modified path.
5. Confirm the §3.4 / §3.5 / §3.6 sibling checks reported OK on this PR
   (the workflow assembles their statuses and feeds them in via the
   ``sibling_check_outcomes`` arg).

Network use
-----------

To keep the module deterministic in tests, all HTTP I/O is funnelled
through a single ``GitHubClient`` protocol so tests can plug a fake.
The default client uses :mod:`urllib.request` (stdlib only — no new
dependency on ``requests``).

References
----------
ADR-043 §3.3 Tool 2 — authoritative spec.
ADR-043 §3.6 — sibling checks whose statuses are summarised here.
ADR-042 §25.4 — Tier-2 definition.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

# Re-use the local check's path matcher to keep behaviour identical
# between LOCAL and CI layers.
from .mod_guard import _glob_match, _load_governance_globs

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

_TRAILER_RE = re.compile(
    r"^Governance-Modification-Approved-By:\s*(@[A-Za-z0-9][A-Za-z0-9_-]*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class CheckResult:
    """Outcome of one CI-side governance-modification verification."""

    ok: bool
    findings: list[str] = field(default_factory=list)
    approver_handles_verified: list[str] = field(default_factory=list)
    governance_files: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# GitHub client                                                               #
# --------------------------------------------------------------------------- #


class GitHubClient(Protocol):
    """Minimal protocol the verifier needs from GitHub.

    Tests inject a fake that records call history and returns canned
    payloads.
    """

    def get(self, url: str) -> object:  # pragma: no cover — protocol
        ...


class UrllibGitHubClient:
    """Default :mod:`urllib.request`-backed client.

    Reads ``GITHUB_TOKEN`` from the env. No retry / pagination logic
    beyond the smallest needed for the §3.3 endpoints — every list
    endpoint here is bounded by typical PR sizes.
    """

    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN") or ""

    def get(self, url: str) -> object:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as exc:  # pragma: no cover — net path
            raise RuntimeError(f"GitHub API HTTP {exc.code}: {url}") from exc
        return json.loads(payload.decode("utf-8") or "null")


# --------------------------------------------------------------------------- #
# Identity / CODEOWNERS helpers                                               #
# --------------------------------------------------------------------------- #


def _load_tier2_handles(repo_root: Path) -> set[str]:
    """Return the set of Tier-2 (``maintainer``) handles from humans.yml."""
    path = repo_root / "docs" / "identity" / "humans.yml"
    if not path.is_file():
        return set()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return set()
    handles: set[str] = set()
    for entry in raw.get("humans", []) or []:
        if (entry.get("tier") or "").strip() == "maintainer":
            handle = (entry.get("github") or "").strip()
            if handle:
                handles.add(handle)
    return handles


def _load_codeowner_assignments(repo_root: Path) -> list[tuple[str, list[str]]]:
    """Parse ``.github/CODEOWNERS`` into ``[(pattern, [handles]), …]``.

    Stops short of full GitHub-CODEOWNERS-grammar fidelity (which is
    quite minimal); this is enough for the §3.3 verification logic.
    """
    path = repo_root / ".github" / "CODEOWNERS"
    if not path.is_file():
        return []
    rows: list[tuple[str, list[str]]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        handles = [p for p in parts[1:] if p.startswith("@")]
        if handles:
            rows.append((pattern, handles))
    return rows


def _codeowners_for_path(rel_path: str, repo_root: Path) -> set[str]:
    """Resolve the CODEOWNERS handles for ``rel_path``.

    GitHub's last-match-wins semantics are honoured.
    """
    last: set[str] = set()
    for pattern, handles in _load_codeowner_assignments(repo_root):
        # CODEOWNERS patterns are a subset of gitignore globs; reuse the
        # shared ``_glob_match`` for consistency.
        if _glob_match(rel_path, [pattern]):
            last = set(handles)
    return last


# --------------------------------------------------------------------------- #
# Public entry-point                                                          #
# --------------------------------------------------------------------------- #


def verify_governance_pr(
    pr_number: int,
    repo: str,
    *,
    repo_root: Path | None = None,
    client: GitHubClient | None = None,
    sibling_check_outcomes: dict[str, bool] | None = None,
) -> CheckResult:
    """CI-side governance-edit verification (authoritative).

    Parameters
    ----------
    pr_number:
        PR number on the GitHub repository.
    repo:
        ``owner/name`` slug (e.g. ``zjzcpj/SciEasy``).
    repo_root:
        Local checkout used to read ``.governance-paths.yaml``,
        ``docs/identity/humans.yml``, ``.github/CODEOWNERS``. Defaults
        to CWD.
    client:
        :class:`GitHubClient` to use. Defaults to
        :class:`UrllibGitHubClient` which reads ``GITHUB_TOKEN`` from
        the env.
    sibling_check_outcomes:
        ``{"monotonic_check": True, "contradiction_audit": True, "honeypot": True}``-
        style dict from the workflow assembler. Any ``False`` value
        causes a finding (§3.3 Tool 2 step 4).
    """
    repo_root = (repo_root or Path.cwd()).resolve()
    cli = client or UrllibGitHubClient()
    result = CheckResult(ok=True)
    api_root = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"

    # Step 1+2 — list modified files, filter to governance paths.
    files_payload = cli.get(f"{api_root}/files?per_page=100")
    if not isinstance(files_payload, list):
        result.ok = False
        result.findings.append(
            f"governance/pr-files-unavailable: GitHub returned non-list payload for {api_root}/files"
        )
        return result

    globs = _load_governance_globs(repo_root)
    if not globs:
        result.ok = False
        result.findings.append(
            "governance/missing-paths-registry: .governance-paths.yaml is missing or empty; "
            "cannot decide which files require Tier-2 approval"
        )
        return result

    governance_files: list[str] = []
    for entry in files_payload:
        if not isinstance(entry, dict):
            continue
        filename = entry.get("filename")
        if not isinstance(filename, str):
            continue
        if _glob_match(filename, globs):
            governance_files.append(filename)
    result.governance_files = governance_files
    if not governance_files:
        return result

    # Step 3 — extract trailers from each commit in the PR.
    commits_payload = cli.get(f"{api_root}/commits?per_page=250")
    cited_handles: set[str] = set()
    if isinstance(commits_payload, list):
        for c in commits_payload:
            if not isinstance(c, dict):
                continue
            commit = c.get("commit") or {}
            message = commit.get("message") or ""
            if not isinstance(message, str):
                continue
            for match in _TRAILER_RE.finditer(message):
                cited_handles.add(match.group(1))

    if not cited_handles:
        result.ok = False
        result.findings.append(
            "governance/missing-approval-trailer: PR modifies "
            f"{len(governance_files)} governance file(s) without any "
            "'Governance-Modification-Approved-By: @<Tier2>' trailer in its commits"
        )
        return result

    # Step 4a — handle is registered as Tier-2.
    tier2_handles = _load_tier2_handles(repo_root)
    unknown_or_non_tier2 = sorted(h for h in cited_handles if h not in tier2_handles)
    if unknown_or_non_tier2:
        result.ok = False
        for h in unknown_or_non_tier2:
            result.findings.append(
                f"governance/non-tier2-approver: cited approver {h} is not registered "
                "as Tier-2 (maintainer) in docs/identity/humans.yml"
            )
        # Continue — surface every failure for one PR run.

    # Step 4b — GitHub review state.
    reviews_payload = cli.get(f"{api_root}/reviews?per_page=250")
    approved_handles: set[str] = set()
    if isinstance(reviews_payload, list):
        for r in reviews_payload:
            if not isinstance(r, dict):
                continue
            state = (r.get("state") or "").upper()
            user = r.get("user") or {}
            login = user.get("login") if isinstance(user, dict) else None
            if state == "APPROVED" and isinstance(login, str) and login:
                approved_handles.add(f"@{login}")

    not_approved = sorted(h for h in cited_handles if h not in approved_handles and h in tier2_handles)
    if not_approved:
        result.ok = False
        for h in not_approved:
            result.findings.append(
                f"governance/stale-or-missing-review: cited approver {h} has no APPROVED review on PR #{pr_number}"
            )

    # Step 4c — CODEOWNERS satisfaction (per-path).
    for gf in governance_files:
        owners = _codeowners_for_path(gf, repo_root)
        cited_owners = cited_handles.intersection(owners)
        if owners and not cited_owners and not cited_handles.intersection(tier2_handles):
            # Acceptable fallback: any Tier-2 handle is cited (per §3.3
            # step 4c "...or any Tier-2 handle"). When that's absent too,
            # block the PR.
            result.ok = False
            result.findings.append(
                f"governance/codeowners-not-cited: {gf} has CODEOWNERS "
                f"{sorted(owners)} but no cited approver matches and no Tier-2 fallback"
            )

    # Step 5 — sibling-check outcomes.
    if sibling_check_outcomes:
        for check_name, ok in sibling_check_outcomes.items():
            if not ok:
                result.ok = False
                result.findings.append(
                    f"governance/sibling-check-failed: companion '{check_name}' did not report OK on this PR"
                )

    result.approver_handles_verified = sorted(h for h in cited_handles if h in tier2_handles and h in approved_handles)
    return result


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point. Designed for invocation inside the workflow."""
    parser = argparse.ArgumentParser(
        prog="python -m scieasy.qa.governance.mod_pr_check",
        description="CI-side authoritative governance-modification verifier (ADR-043 §3.3 Tool 2).",
    )
    parser.add_argument("--pr", type=int, required=True, help="Pull request number.")
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository slug (e.g. zjzcpj/SciEasy).",
    )
    parser.add_argument("--repo-root", default=None)
    parser.add_argument(
        "--sibling",
        action="append",
        default=[],
        metavar="name=true|false",
        help="Record a sibling-check outcome; may be passed multiple times.",
    )
    args = parser.parse_args(argv)

    sibling: dict[str, bool] = {}
    for entry in args.sibling:
        if "=" not in entry:
            print(f"invalid --sibling entry: {entry}", file=sys.stderr)
            return 2
        name, _, value = entry.partition("=")
        sibling[name.strip()] = value.strip().lower() == "true"

    repo_root = Path(args.repo_root or Path.cwd()).resolve()
    result = verify_governance_pr(
        args.pr,
        args.repo,
        repo_root=repo_root,
        sibling_check_outcomes=sibling,
    )
    if result.ok:
        return 0
    for f in result.findings:
        print(f, file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover — CLI entry-point
    raise SystemExit(main())
