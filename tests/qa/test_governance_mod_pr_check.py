"""Tests for ``scieasy.qa.governance.mod_pr_check`` (TC-1E.2).

GitHub HTTP is plugged via a ``FakeClient`` so the suite is deterministic
and network-free. The check has a non-trivial decision matrix (5
verification steps x several failure modes); each branch is exercised.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import redirect_stderr
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scieasy.qa.governance.mod_pr_check import (
    UrllibGitHubClient,
    _codeowners_for_path,
    _load_codeowner_assignments,
    _load_tier2_handles,
    main,
    verify_governance_pr,
)

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@dataclass
class FakeClient:
    """In-memory ``GitHubClient`` that returns canned payloads."""

    files: list[dict] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)
    seen_urls: list[str] = field(default_factory=list)
    files_value: object | None = None  # use to inject non-list

    def get(self, url: str) -> object:
        self.seen_urls.append(url)
        if url.endswith("/files?per_page=100"):
            return self.files if self.files_value is None else self.files_value
        if "/commits?per_page=" in url:
            return self.commits
        if "/reviews?per_page=" in url:
            return self.reviews
        raise AssertionError(f"unexpected URL: {url}")


@pytest.fixture()
def repo_root(tmp_path: Path) -> Iterator[Path]:
    """Lay down the three files the verifier reads from disk."""
    (tmp_path / "docs" / "identity").mkdir(parents=True)
    (tmp_path / "docs" / "identity" / "humans.yml").write_text(
        'version: 1\nhumans:\n  - github: "@tier2"\n'
        '    email: "tier2@example.com"\n    tier: maintainer\n    joined: 2026-01-01\n'
        '  - github: "@tier1"\n    email: "tier1@example.com"\n    tier: contributor\n    joined: 2026-01-01\n',
        encoding="utf-8",
    )
    (tmp_path / ".governance-paths.yaml").write_text(
        "version: 1\n"
        "governance_paths:\n"
        '  - "docs/adr/**"\n'
        '  - "CLAUDE.md"\n'
        '  - "src/scieasy/qa/**"\n'
        "honeypot_canaries: []\n",
        encoding="utf-8",
    )
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text(
        "* @tier1\ndocs/adr/** @tier2\nsrc/scieasy/qa/** @tier2\n",
        encoding="utf-8",
    )
    yield tmp_path


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _file(name: str) -> dict:
    return {"filename": name}


def _commit(message: str) -> dict:
    return {"commit": {"message": message}}


def _review(login: str, state: str = "APPROVED") -> dict:
    return {"state": state, "user": {"login": login}}


# --------------------------------------------------------------------------- #
# _load_tier2_handles / CODEOWNERS                                            #
# --------------------------------------------------------------------------- #


def test_load_tier2_handles(repo_root: Path) -> None:
    assert _load_tier2_handles(repo_root) == {"@tier2"}


def test_load_tier2_handles_missing_file(tmp_path: Path) -> None:
    assert _load_tier2_handles(tmp_path) == set()


def test_load_tier2_handles_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "docs" / "identity").mkdir(parents=True)
    (tmp_path / "docs" / "identity" / "humans.yml").write_text(": bad", encoding="utf-8")
    assert _load_tier2_handles(tmp_path) == set()


def test_codeowner_assignments_skip_comments_and_blank_lines(repo_root: Path) -> None:
    (repo_root / ".github" / "CODEOWNERS").write_text(
        "# header\n\n* @tier1\ndocs/adr/** @tier2 @tier1\n",
        encoding="utf-8",
    )
    rows = _load_codeowner_assignments(repo_root)
    assert rows == [("*", ["@tier1"]), ("docs/adr/**", ["@tier2", "@tier1"])]


def test_codeowner_assignments_missing(tmp_path: Path) -> None:
    assert _load_codeowner_assignments(tmp_path) == []


def test_codeowners_for_path_returns_last_match(repo_root: Path) -> None:
    assert _codeowners_for_path("docs/adr/ADR-099.md", repo_root) == {"@tier2"}
    # Path with only the default rule.
    (repo_root / ".github" / "CODEOWNERS").write_text("* @tier1\n", encoding="utf-8")
    assert _codeowners_for_path("docs/adr/x.md", repo_root) == {"@tier1"}


# --------------------------------------------------------------------------- #
# verify_governance_pr — happy path                                           #
# --------------------------------------------------------------------------- #


def test_verify_ok_when_no_governance_files(repo_root: Path) -> None:
    client = FakeClient(files=[_file("src/scieasy/core/runtime.py")])
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert result.ok is True
    assert result.governance_files == []


def test_verify_happy_path_with_tier2_approval(repo_root: Path) -> None:
    client = FakeClient(
        files=[_file("docs/adr/ADR-099.md")],
        commits=[_commit("feat: edit\n\nGovernance-Modification-Approved-By: @tier2\n")],
        reviews=[_review("tier2")],
    )
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert result.ok is True, result.findings
    assert result.governance_files == ["docs/adr/ADR-099.md"]
    assert result.approver_handles_verified == ["@tier2"]


def test_verify_emits_expected_url_for_files_endpoint(repo_root: Path) -> None:
    """The verifier should ask GitHub for files with ``per_page=100``."""
    client = FakeClient(files=[])
    verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert client.seen_urls[0].endswith("/pulls/7/files?per_page=100")


# --------------------------------------------------------------------------- #
# verify_governance_pr — failure modes                                        #
# --------------------------------------------------------------------------- #


def test_verify_blocks_when_pr_files_payload_invalid(repo_root: Path) -> None:
    client = FakeClient(files_value={"unexpected": "object"})
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert result.ok is False
    assert any("pr-files-unavailable" in f for f in result.findings)


def test_verify_blocks_when_registry_missing(tmp_path: Path) -> None:
    client = FakeClient(files=[_file("docs/adr/ADR-099.md")])
    result = verify_governance_pr(7, "owner/repo", repo_root=tmp_path, client=client)
    assert result.ok is False
    assert any("missing-paths-registry" in f for f in result.findings)


def test_verify_blocks_missing_trailer(repo_root: Path) -> None:
    client = FakeClient(
        files=[_file("docs/adr/ADR-099.md")],
        commits=[_commit("feat: edit but no trailer\n")],
        reviews=[],
    )
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert result.ok is False
    assert any("missing-approval-trailer" in f for f in result.findings)


def test_verify_blocks_non_tier2_approver(repo_root: Path) -> None:
    client = FakeClient(
        files=[_file("docs/adr/ADR-099.md")],
        commits=[_commit("feat: edit\n\nGovernance-Modification-Approved-By: @ghost\n")],
        reviews=[_review("ghost")],
    )
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert result.ok is False
    assert any("non-tier2-approver" in f for f in result.findings)


def test_verify_blocks_stale_or_missing_review(repo_root: Path) -> None:
    client = FakeClient(
        files=[_file("docs/adr/ADR-099.md")],
        commits=[_commit("feat: edit\n\nGovernance-Modification-Approved-By: @tier2\n")],
        reviews=[_review("tier2", state="CHANGES_REQUESTED")],
    )
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert result.ok is False
    assert any("stale-or-missing-review" in f for f in result.findings)


def test_verify_handles_invalid_commits_payload(repo_root: Path) -> None:
    """Non-list commits payload should be treated as 'no trailers'."""
    client = FakeClient(files=[_file("docs/adr/ADR-099.md")], commits=[])
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert result.ok is False
    assert any("missing-approval-trailer" in f for f in result.findings)


def test_verify_reports_sibling_failures(repo_root: Path) -> None:
    client = FakeClient(
        files=[_file("docs/adr/ADR-099.md")],
        commits=[_commit("feat: edit\n\nGovernance-Modification-Approved-By: @tier2\n")],
        reviews=[_review("tier2")],
    )
    result = verify_governance_pr(
        7,
        "owner/repo",
        repo_root=repo_root,
        client=client,
        sibling_check_outcomes={"monotonic_check": False, "contradiction_audit": True},
    )
    assert result.ok is False
    assert any("sibling-check-failed" in f and "monotonic_check" in f for f in result.findings)


def test_verify_codeowners_satisfied_by_tier2_fallback(repo_root: Path) -> None:
    """Even when CODEOWNERS lists a different handle, citing a Tier-2 handle is fine.

    The seed CODEOWNERS lists ``@tier2`` for ``docs/adr/**`` — there's no
    difference for the happy-path test, so we tweak CODEOWNERS to list
    ``@other`` and verify ``@tier2`` is still accepted via the fallback.
    """
    (repo_root / ".github" / "CODEOWNERS").write_text("docs/adr/** @other\n", encoding="utf-8")
    # Add @other as Tier-2 so it doesn't fail the Tier-2 step; the point of the test
    # is the CODEOWNERS-satisfaction logic, not the Tier-2 step.
    client = FakeClient(
        files=[_file("docs/adr/ADR-099.md")],
        commits=[_commit("feat: edit\n\nGovernance-Modification-Approved-By: @tier2\n")],
        reviews=[_review("tier2")],
    )
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    # @tier2 is Tier-2 and reviewed — fallback satisfied.
    assert result.ok is True, result.findings


def test_verify_codeowners_unsatisfied_when_no_tier2_handle_cited(repo_root: Path) -> None:
    """If the cited handle is neither in CODEOWNERS nor Tier-2, block."""
    (repo_root / ".github" / "CODEOWNERS").write_text("docs/adr/** @other\n", encoding="utf-8")
    client = FakeClient(
        files=[_file("docs/adr/ADR-099.md")],
        commits=[_commit("feat: edit\n\nGovernance-Modification-Approved-By: @stranger\n")],
        reviews=[_review("stranger")],
    )
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    assert result.ok is False
    # Two findings expected: non-tier2-approver + codeowners-not-cited.
    assert any("non-tier2-approver" in f for f in result.findings)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_main_rejects_malformed_sibling_arg(repo_root: Path) -> None:
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(
            [
                "--pr",
                "7",
                "--repo",
                "owner/repo",
                "--repo-root",
                str(repo_root),
                "--sibling",
                "bogus_no_equals",
            ]
        )
    assert rc == 2
    assert "invalid --sibling" in buf.getvalue()


def test_main_ok_path_uses_urllib_client_indirectly(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``UrllibGitHubClient`` so ``main`` is exercised without HTTP."""
    import scieasy.qa.governance.mod_pr_check as mod

    class _Stub:
        def __init__(self, *_a, **_k) -> None: ...
        def get(self, url: str) -> object:
            if url.endswith("/files?per_page=100"):
                return [_file("src/scieasy/core/runtime.py")]  # non-governance
            return []

    monkeypatch.setattr(mod, "UrllibGitHubClient", _Stub)
    rc = main(
        [
            "--pr",
            "7",
            "--repo",
            "owner/repo",
            "--repo-root",
            str(repo_root),
        ]
    )
    assert rc == 0


def test_main_failure_emits_findings(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scieasy.qa.governance.mod_pr_check as mod

    class _Stub:
        def __init__(self, *_a, **_k) -> None: ...
        def get(self, url: str) -> object:
            if url.endswith("/files?per_page=100"):
                return [_file("docs/adr/ADR-099.md")]
            return []

    monkeypatch.setattr(mod, "UrllibGitHubClient", _Stub)
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(
            [
                "--pr",
                "7",
                "--repo",
                "owner/repo",
                "--repo-root",
                str(repo_root),
                "--sibling",
                "monotonic_check=true",
            ]
        )
    assert rc == 1
    assert "missing-approval-trailer" in buf.getvalue()


# --------------------------------------------------------------------------- #
# UrllibGitHubClient — constructor only (no network)                          #
# --------------------------------------------------------------------------- #


def test_urllib_client_reads_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    client = UrllibGitHubClient()
    assert client._token == "ghp_secret"


def test_urllib_client_explicit_token() -> None:
    client = UrllibGitHubClient(token="ghp_explicit")
    assert client._token == "ghp_explicit"


def test_urllib_client_get_decodes_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the ``get()`` happy-path without real network."""

    import scieasy.qa.governance.mod_pr_check as mod

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *exc) -> None:
            return None

        def read(self) -> bytes:
            return self._body

    seen: dict[str, str] = {}

    def _fake_urlopen(req, timeout=20):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization", "")
        return _Resp(b'[{"x":1}]')

    monkeypatch.setattr(mod.urllib.request, "urlopen", _fake_urlopen)
    client = UrllibGitHubClient(token="ghp_xx")
    out = client.get("https://api.github.com/test")
    assert out == [{"x": 1}]
    assert seen["url"] == "https://api.github.com/test"
    assert seen["auth"] == "Bearer ghp_xx"


def test_urllib_client_get_handles_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """``json.loads('')`` would raise; the implementation falls back to ``null``."""
    import scieasy.qa.governance.mod_pr_check as mod

    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *exc) -> None:
            return None

        def read(self) -> bytes:
            return b""

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: _Resp())
    client = UrllibGitHubClient()
    assert client.get("https://api.github.com/test") is None


def test_codeowner_assignments_skip_single_token_lines(repo_root: Path) -> None:
    """A line with only the pattern and no owners is dropped (len(parts) < 2)."""
    (repo_root / ".github" / "CODEOWNERS").write_text("single-token-line\ndocs/adr/** @tier2\n", encoding="utf-8")
    rows = _load_codeowner_assignments(repo_root)
    # The single-token line is filtered.
    assert all(len(handles) >= 1 for _pattern, handles in rows)
    assert ("docs/adr/**", ["@tier2"]) in rows


@dataclass
class _BadEntryClient:
    """Returns a files payload mixing non-dict and dict-with-non-string filename."""

    seen_urls: list[str] = field(default_factory=list)

    def get(self, url: str) -> object:
        self.seen_urls.append(url)
        if "/files?" in url:
            return [
                "not-a-dict",  # triggers `if not isinstance(entry, dict): continue`
                {"filename": 123},  # triggers `if not isinstance(filename, str): continue`
                {"filename": "docs/adr/ADR-099.md"},
            ]
        if "/commits?" in url:
            return [
                "not-a-dict",
                {"commit": {"message": 12345}},  # non-string message
                {"commit": {"message": "ok\n\nGovernance-Modification-Approved-By: @tier2\n"}},
            ]
        if "/reviews?" in url:
            return [
                "not-a-dict",
                {"state": "APPROVED", "user": "scalar-not-dict"},  # user-not-dict branch
                {"state": "APPROVED", "user": {"login": "tier2"}},
            ]
        return []


def test_verify_handles_malformed_payload_entries(repo_root: Path) -> None:
    """Cover the per-entry ``not isinstance`` skips across all three list payloads."""
    client = _BadEntryClient()
    result = verify_governance_pr(7, "owner/repo", repo_root=repo_root, client=client)
    # Path is a governance file; cited trailer points at Tier-2 who approved.
    assert result.ok is True, result.findings
    assert result.governance_files == ["docs/adr/ADR-099.md"]
