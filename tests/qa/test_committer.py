"""Tests for ``scripts/committer.py`` (Phase 1H sub-PR 3, TC-1H.6).

References
----------
ADR-042 §16 — committer.py hard tooling.
ADR-042 §16.2 — runtime detection.
ADR-042 §16.3 — forbidden patterns.
ADR-042 §16.5 — commit-log JSONL.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts import committer

# ---------------------------------------------------------------------------
# Forbidden-token rejection (§16.3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", ["-A", "--all", "-a", ".", "*"])
def test_reject_forbidden_args(forbidden: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        committer._reject_forbidden([forbidden])
    assert forbidden in str(excinfo.value)


def test_reject_forbidden_skipped_for_normal_paths() -> None:
    # Should NOT raise for normal paths.
    committer._reject_forbidden(["src/x.py", "docs/y.md"])


# ---------------------------------------------------------------------------
# _is_forbidden direct
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg, expected",
    [
        ("-A", True),
        ("--all", True),
        ("-a", True),
        (".", True),
        ("*", True),
        ("src/foo.py", False),
        ("", False),
    ],
)
def test_is_forbidden(arg: str, expected: bool) -> None:
    assert committer._is_forbidden(arg) == expected


# ---------------------------------------------------------------------------
# Actor resolution (§16.2 + §25.2)
# ---------------------------------------------------------------------------


def test_resolve_actor_agent_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SCIEASY_AGENT_RUNTIME", "Claude")
    monkeypatch.setenv("SCIEASY_AGENT_MODEL", "claude-opus-4-7")
    monkeypatch.delenv("SCIEASY_HUMAN_OVERRIDE", raising=False)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    actor = committer._resolve_actor(tmp_path)
    assert actor["kind"] == "agent"
    assert actor["runtime"] == "Claude"
    assert actor["model"] == "claude-opus-4-7"


def test_resolve_actor_invalid_runtime_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SCIEASY_AGENT_RUNTIME", "Bogus")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not in"):
        committer._resolve_actor(tmp_path)


def test_resolve_actor_human_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SCIEASY_AGENT_RUNTIME", raising=False)
    monkeypatch.setenv("SCIEASY_HUMAN_OVERRIDE", "@jiazhenz026")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    actor = committer._resolve_actor(tmp_path)
    assert actor["kind"] == "human"
    assert actor["github"] == "@jiazhenz026"


def test_resolve_actor_no_signal_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SCIEASY_AGENT_RUNTIME", raising=False)
    monkeypatch.delenv("SCIEASY_HUMAN_OVERRIDE", raising=False)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    # Force git_author_email to return an unmatched address.
    monkeypatch.setattr(committer, "_git_author_email", lambda _cwd: "stranger@example.com")
    with pytest.raises(SystemExit, match="no actor identity"):
        committer._resolve_actor(tmp_path)


def test_resolve_actor_identity_registry_match(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SCIEASY_AGENT_RUNTIME", raising=False)
    monkeypatch.delenv("SCIEASY_HUMAN_OVERRIDE", raising=False)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    identity_dir = tmp_path / "docs" / "identity"
    identity_dir.mkdir(parents=True)
    (identity_dir / "humans.yml").write_text(
        "humans:\n  - email: alice@example.com\n    github: '@alice'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(committer, "_git_author_email", lambda _cwd: "alice@example.com")
    actor = committer._resolve_actor(tmp_path)
    assert actor["kind"] == "human"
    assert actor["github"] == "@alice"


# ---------------------------------------------------------------------------
# Trailer construction (§13.2 / §16.2)
# ---------------------------------------------------------------------------


def test_build_trailer_agent() -> None:
    trailer = committer._build_trailer(
        {"kind": "agent", "runtime": "Claude", "model": "opus-4-7", "email": "", "github": ""}
    )
    assert trailer == "Assisted-by: Claude/opus-4-7"


def test_build_trailer_human_returns_none() -> None:
    assert committer._build_trailer({"kind": "human", "runtime": "", "model": "", "email": "", "github": "@x"}) is None


def test_build_trailer_unknown_model_fallback() -> None:
    trailer = committer._build_trailer({"kind": "agent", "runtime": "Codex", "model": "", "email": "", "github": ""})
    assert trailer == "Assisted-by: Codex/unknown-model"


def test_append_trailer_simple() -> None:
    msg = "feat(x): hello"
    out = committer._append_trailer(msg, "Assisted-by: Claude/m")
    assert out.endswith("Assisted-by: Claude/m\n")
    assert "\n\nAssisted-by:" in out  # blank line precedes trailer block


def test_append_trailer_existing_block() -> None:
    # Use real Key-Value git trailers (matched by _TRAILER_RE).
    # Note: GitHub's "Closes #1" is NOT a git trailer (no colon-space).
    msg = "feat(x): hi\n\nADR: 42\n"
    out = committer._append_trailer(msg, "Assisted-by: Claude/m")
    # No extra blank line; appended within trailer block.
    assert out.endswith("ADR: 42\nAssisted-by: Claude/m\n")


def test_append_trailer_idempotent() -> None:
    msg = "feat(x): hi\n\nAssisted-by: Claude/m\n"
    out = committer._append_trailer(msg, "Assisted-by: Claude/m")
    # No duplicate.
    assert out.count("Assisted-by: Claude/m") == 1


def test_append_trailer_no_trailer_passthrough() -> None:
    msg = "feat(x): hi"
    assert committer._append_trailer(msg, "") == msg


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


def test_add_rejects_empty_files() -> None:
    with pytest.raises(SystemExit, match="at least one"):
        committer._cmd_add([], cwd=Path("."))


def test_main_add_rejects_forbidden(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        committer.main(["add", "-A"])


def test_main_commit_rejects_a_flag(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        committer.main(["commit", "-a", "-m", "feat: x"])


def test_main_commit_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``commit --dry-run`` prints plan without invoking git."""
    monkeypatch.setenv("SCIEASY_AGENT_RUNTIME", "Claude")
    monkeypatch.setenv("SCIEASY_AGENT_MODEL", "opus-4-7")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(committer, "_find_repo_root", lambda: tmp_path)
    # Pretend the index has one staged file.
    monkeypatch.setattr(
        committer,
        "_git",
        lambda args, cwd, capture=False: subprocess.CompletedProcess(args, 0, stdout="src/x.py\n", stderr=""),
    )
    rc = committer.main(["commit", "-m", "feat(qa): hello", "--dry-run"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Commit log append (§16.5)
# ---------------------------------------------------------------------------


def test_append_commit_log_writes_jsonl(tmp_path: Path) -> None:
    actor = {
        "kind": "agent",
        "runtime": "Claude",
        "model": "opus-4-7",
        "email": "a@b.com",
        "github": "@a",
    }
    committer._append_commit_log(
        tmp_path,
        sha="abc1234567",
        actor=actor,
        files=["src/x.py"],
        message="feat(x): hi\n\nAssisted-by: Claude/opus-4-7",
    )
    log_path = tmp_path / "docs" / "audit" / "commit-log.jsonl"
    assert log_path.is_file()
    record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["sha"] == "abc1234567"
    assert record["runtime"] == "Claude"
    assert record["message_first_line"] == "feat(x): hi"


def test_append_commit_log_appends_not_overwrites(tmp_path: Path) -> None:
    actor = {"kind": "agent", "runtime": "Claude", "model": "m", "email": "", "github": "@a"}
    committer._append_commit_log(tmp_path, sha="aaa", actor=actor, files=[], message="m1")
    committer._append_commit_log(tmp_path, sha="bbb", actor=actor, files=[], message="m2")
    lines = (tmp_path / "docs" / "audit" / "commit-log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


# ---------------------------------------------------------------------------
# Pre-commit graceful degradation (§16.4)
# ---------------------------------------------------------------------------


def test_run_pre_commit_skips_when_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(committer.shutil, "which", lambda _: None)
    rc = committer._run_pre_commit(["src/x.py"], cwd=tmp_path)
    assert rc == 0
    captured = capsys.readouterr()
    assert "pre-commit" in captured.err.lower()


def test_run_pre_commit_skips_when_no_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Even if `pre-commit` exists, no files → no-op.
    monkeypatch.setattr(committer.shutil, "which", lambda _: "/usr/bin/pre-commit")
    rc = committer._run_pre_commit([], cwd=tmp_path)
    assert rc == 0


def test_run_pre_commit_invokes_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(committer.shutil, "which", lambda _: "/usr/bin/pre-commit")
    calls = []

    def fake_run(cmd: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(committer.subprocess, "run", fake_run)
    rc = committer._run_pre_commit(["a.py"], cwd=tmp_path)
    assert rc == 0
    assert calls and calls[0][:3] == ["/usr/bin/pre-commit", "run", "--files"]


# ---------------------------------------------------------------------------
# Identity-registry corner cases
# ---------------------------------------------------------------------------


def test_identity_match_missing_registry(tmp_path: Path) -> None:
    """No humans.yml file → None (the most common bootstrap case)."""
    assert committer._identity_match("x@example.com", tmp_path) is None


def test_identity_match_empty_email(tmp_path: Path) -> None:
    """Empty email short-circuits before reading any file."""
    assert committer._identity_match("", tmp_path) is None


def test_identity_match_malformed_yaml(tmp_path: Path) -> None:
    """A malformed humans.yml is treated as no-match."""
    (tmp_path / "docs" / "identity").mkdir(parents=True)
    (tmp_path / "docs" / "identity" / "humans.yml").write_text(
        "not: valid: yaml: this:\n: is: bad",
        encoding="utf-8",
    )
    assert committer._identity_match("x@example.com", tmp_path) is None


def test_git_author_email_safe_on_missing_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(*_args: object, **_kw: object) -> object:
        raise FileNotFoundError("no git here")

    monkeypatch.setattr(committer.subprocess, "run", boom)
    assert committer._git_author_email(tmp_path) == ""


# ---------------------------------------------------------------------------
# _cmd_add coverage
# ---------------------------------------------------------------------------


def test_cmd_add_invokes_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Successful add path runs pre-commit then git add."""
    monkeypatch.setattr(committer.shutil, "which", lambda _: None)  # skip pre-commit
    calls = []

    def fake_git(args: list[str], cwd: Path, capture: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(committer, "_git", fake_git)
    rc = committer._cmd_add(["src/x.py", "src/y.py"], cwd=tmp_path)
    assert rc == 0
    assert calls and calls[0][:2] == ["add", "--"]


def test_cmd_add_propagates_pre_commit_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(committer, "_run_pre_commit", lambda _f, _c: 1)
    rc = committer._cmd_add(["src/x.py"], cwd=tmp_path)
    assert rc == 1


# ---------------------------------------------------------------------------
# _cmd_commit coverage
# ---------------------------------------------------------------------------


def test_cmd_commit_invokes_git_and_writes_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Non-dry-run commit path runs git commit, rev-parse, and appends log."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.setattr(committer, "_find_repo_root", lambda: tmp_path)

    call_count = {"n": 0}

    def fake_git(args: list[str], cwd: Path, capture: bool = False) -> subprocess.CompletedProcess[str]:
        call_count["n"] += 1
        if "diff" in args:
            return subprocess.CompletedProcess(args, 0, stdout="src/x.py\n", stderr="")
        if "rev-parse" in args:
            return subprocess.CompletedProcess(args, 0, stdout="abc1234\n", stderr="")
        # commit
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(committer, "_git", fake_git)
    actor = {"kind": "agent", "runtime": "Claude", "model": "m", "email": "", "github": "@x"}
    rc = committer._cmd_commit("feat(x): hi", cwd=tmp_path, actor=actor)
    assert rc == 0
    assert call_count["n"] == 3  # diff + commit + rev-parse
    log = (tmp_path / "docs" / "audit" / "commit-log.jsonl").read_text(encoding="utf-8")
    assert "abc1234" in log


def test_cmd_commit_propagates_git_commit_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.setattr(committer, "_find_repo_root", lambda: tmp_path)

    def fake_git(args: list[str], cwd: Path, capture: bool = False) -> subprocess.CompletedProcess[str]:
        if "diff" in args:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if "commit" in args:
            return subprocess.CompletedProcess(args, 5, stdout="", stderr="nothing to commit")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(committer, "_git", fake_git)
    actor = {"kind": "human", "runtime": "", "model": "", "email": "", "github": "@x"}
    rc = committer._cmd_commit("feat(x): hi", cwd=tmp_path, actor=actor)
    assert rc == 5
    # No log written when commit fails.
    assert not (tmp_path / "docs" / "audit" / "commit-log.jsonl").exists()


def test_main_add_dispatches_to_cmd_add(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_add(files: list[str], cwd: Path) -> int:
        captured["files"] = files
        return 0

    monkeypatch.setattr(committer, "_cmd_add", fake_add)
    rc = committer.main(["add", "a.py", "b.py"])
    assert rc == 0
    assert captured["files"] == ["a.py", "b.py"]
