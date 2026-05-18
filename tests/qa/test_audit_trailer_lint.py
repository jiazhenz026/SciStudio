"""Tests for ``scieasy.qa.audit.trailer_lint`` (ADR-042 §13).

Covers:

* :func:`extract_trailers` — well-formed block, missing block, mixed
  blank lines, non-trailer line aborts collection.
* Each trailer regex in :data:`TRAILER_PATTERNS` accepts/rejects the
  canonical examples from ADR-042 §13.2 + ADR-043 §3.3/§3.4.2.
* :func:`validate_commit` — missing Assisted-by on agent commit,
  malformed Fixes, ADR trailer pointing at non-existent ADR, ADR
  trailer required when files match a governed glob.
* :func:`run` — end-to-end on a tmp git repo with a single agent commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scieasy.qa.audit.trailer_lint import (
    TRAILER_PATTERNS,
    extract_trailers,
    parse_commits,
    run,
    validate_commit,
)
from scieasy.qa.schemas.report import Severity

# ---------------------------------------------------------------------------
# extract_trailers
# ---------------------------------------------------------------------------


def test_extract_trailers_basic() -> None:
    msg = (
        "feat(qa): something\n\n"
        "Body paragraph.\n\n"
        "Signed-off-by: Alice <alice@example.org>\n"
        "Assisted-by: Claude:claude-opus-4-7\n"
    )
    assert extract_trailers(msg) == [
        ("Signed-off-by", "Alice <alice@example.org>"),
        ("Assisted-by", "Claude:claude-opus-4-7"),
    ]


def test_extract_trailers_no_block() -> None:
    msg = "fix: typo\n\nNothing here."
    assert extract_trailers(msg) == []


def test_extract_trailers_non_trailer_at_bottom_aborts() -> None:
    msg = "feat: x\n\nBody\nSome non-trailer line"
    assert extract_trailers(msg) == []


def test_extract_trailers_empty_message() -> None:
    assert extract_trailers("") == []
    assert extract_trailers("\n\n\n") == []


# ---------------------------------------------------------------------------
# Trailer regex coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key,value",
    [
        ("Signed-off-by", "Alice <alice@example.org>"),
        ("Assisted-by", "Claude:claude-opus-4-7"),
        ("Assisted-by", "Codex:gpt-5 [coccinelle sparse]"),
        ("Fixes", 'abc1234 ("subject of broken commit")'),
        ("ADR", "ADR-042"),
        ("Reviewed-by", "Bob <bob@example.org>"),
        ("Co-authored-by", "Bob <bob@example.org>"),
        ("Reviewed-locally", "trivial fix"),
        ("Maintainer-Override", "emergency hotfix"),
        ("Human-Override", "documented exemption per §25.X"),
        ("Loosening-Approved", "@maintainer"),
        ("Loosening-Reason", "revert breaking lint rule"),
        ("Governance-Modification-Approved-By", "@maintainer"),
    ],
)
def test_trailer_pattern_accepts_canonical(key: str, value: str) -> None:
    assert TRAILER_PATTERNS[key].match(value) is not None


@pytest.mark.parametrize(
    "key,value",
    [
        ("Signed-off-by", "no email"),
        ("Assisted-by", "spaces in:run"),
        ("Fixes", "no sha pattern"),
        ("ADR", "ADR-XXX"),
        ("Loosening-Approved", "no-at-sign"),
        ("Governance-Modification-Approved-By", "missingAt"),
    ],
)
def test_trailer_pattern_rejects_malformed(key: str, value: str) -> None:
    assert TRAILER_PATTERNS[key].match(value) is None


# ---------------------------------------------------------------------------
# validate_commit
# ---------------------------------------------------------------------------


def _commit(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sha": "abc1234567890abcdef1234567890abcdef12345",
        "author_email": "claude@example.org",
        "subject": "feat(qa): something",
        "body": "feat(qa): something\n\nBody.\n\nAssisted-by: Claude:claude-opus-4-7\n",
        "files": ["src/myproj/foo.py"],
    }
    base.update(overrides)
    return base


def test_validate_commit_clean() -> None:
    findings = validate_commit(_commit(), accepted_adrs=set(), glob_to_adrs={})
    assert findings == []


def test_validate_commit_missing_assisted_by_on_agent() -> None:
    commit = _commit(body="feat(qa): something\n\nbody only")
    findings = validate_commit(commit, accepted_adrs=set(), glob_to_adrs={})
    rule_ids = [f.rule_id for f in findings]
    assert "trailer-lint.missing-assisted-by" in rule_ids


def test_validate_commit_malformed_fixes() -> None:
    commit = _commit(body=("fix: typo\n\nbody\n\nAssisted-by: Claude:claude-opus-4-7\nFixes: not-a-real-fix-format\n"))
    findings = validate_commit(commit, accepted_adrs=set(), glob_to_adrs={})
    assert any(f.rule_id == "trailer-lint.invalid-fixes" for f in findings)


def test_validate_commit_unknown_key_warning() -> None:
    commit = _commit(body=("feat: x\n\nbody\n\nAssisted-by: Claude:claude-opus-4-7\nUnknown-Trailer: something\n"))
    findings = validate_commit(commit, accepted_adrs=set(), glob_to_adrs={})
    unknown = [f for f in findings if f.rule_id == "trailer-lint.unknown-key"]
    assert unknown and unknown[0].severity == Severity.WARNING


def test_validate_commit_adr_not_accepted() -> None:
    commit = _commit(body=("feat: x\n\nbody\n\nAssisted-by: Claude:claude-opus-4-7\nADR: ADR-999\n"))
    findings = validate_commit(commit, accepted_adrs={42}, glob_to_adrs={})
    assert any(f.rule_id == "trailer-lint.adr-not-accepted" for f in findings)


def test_validate_commit_missing_adr_when_governed() -> None:
    commit = _commit(files=["src/scieasy/qa/audit/foo.py"])
    glob_to_adrs = {"src/scieasy/qa/audit/**": {42}}
    findings = validate_commit(commit, accepted_adrs={42}, glob_to_adrs=glob_to_adrs)
    assert any(f.rule_id == "trailer-lint.missing-adr" for f in findings)


def test_validate_commit_missing_fixes_on_fix() -> None:
    commit = _commit(
        subject="fix: typo",
        body=("fix: typo\n\nbody\n\nAssisted-by: Claude:claude-opus-4-7\n"),
    )
    findings = validate_commit(commit, accepted_adrs=set(), glob_to_adrs={})
    assert any(f.rule_id == "trailer-lint.missing-fixes" for f in findings)


# ---------------------------------------------------------------------------
# parse_commits / run end-to-end
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.org"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)


def _commit_in(path: Path, message: str, *, files: list[tuple[str, str]] | None = None) -> None:
    for rel, body in files or [("README.md", "x")]:
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=path, check=True)


def test_parse_commits_returns_per_commit_metadata(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_in(tmp_path, "feat: one\n\nAssisted-by: Claude:claude-opus-4-7")
    _commit_in(tmp_path, "feat: two\n\nbody\n\nAssisted-by: Codex:gpt-5", files=[("a.py", "1")])
    commits = parse_commits(tmp_path, "HEAD~1..HEAD")
    assert len(commits) == 1
    assert "Codex" in str(commits[0]["body"])
    assert "a.py" in commits[0]["files"]


def test_run_finds_missing_assisted_by(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    # Author email contains "claude" → agent-classified.
    subprocess.run(["git", "config", "user.email", "agent[bot]@example.org"], cwd=tmp_path, check=True)
    _commit_in(tmp_path, "feat: missing trailer")
    findings = run(tmp_path, commit_range="HEAD")
    assert any(f.rule_id == "trailer-lint.missing-assisted-by" for f in findings)


def test_run_returns_git_failed_on_bogus_range(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_in(tmp_path, "feat: x")
    findings = run(tmp_path, commit_range="nonexistent..HEAD")
    assert any(f.rule_id == "trailer-lint.git-failed" for f in findings)
