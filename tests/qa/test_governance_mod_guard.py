"""Tests for ``scieasy.qa.governance.mod_guard`` (TC-1E.1).

Targets every public function plus the most surprising branches:

- Author-kind classification (Tier-2 OK; Tier-1/Agent require trailer;
  Unknown reject).
- Path-glob matching covering ``**`` recursion variants used by
  ``.governance-paths.yaml``.
- Trailer-shape validation (positive + negative).
- ``find_governance_files`` matrix against the seed
  ``.governance-paths.yaml``.
- CLI entry-point exit codes (0 / 1).

The tests are network-free: every code path that would shell out to
``git`` is exercised against a temporary repo created in-process.
"""

from __future__ import annotations

import io
import subprocess
from collections.abc import Iterator
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from scieasy.qa.governance.mod_guard import (
    CheckResult,
    _glob_match,
    check_governance_modification,
    detect_author_kind,
    find_governance_files,
    main,
)

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "tier2@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)


def _humans_yaml(
    *, tier2_email: str | None = "tier2@example.com", tier1_email: str | None = "tier1@example.com"
) -> str:
    rows = []
    if tier2_email:
        rows.append(f'  - github: "@tier2"\n    email: "{tier2_email}"\n    tier: maintainer\n    joined: 2026-01-01\n')
    if tier1_email:
        rows.append(
            f'  - github: "@tier1"\n    email: "{tier1_email}"\n    tier: contributor\n    joined: 2026-01-01\n'
        )
    return "version: 1\nhumans:\n" + "".join(rows) if rows else "version: 1\nhumans: []\n"


def _governance_yaml() -> str:
    return (
        "version: 1\n"
        "governance_paths:\n"
        '  - "docs/adr/**"\n'
        '  - "CLAUDE.md"\n'
        '  - "**/AGENTS.md"\n'
        '  - "src/scieasy/qa/**"\n'
        "honeypot_canaries: []\n"
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Iterator[Path]:
    """Initialise a fresh git repo with humans.yml + governance-paths.yaml."""
    _git_init(tmp_path)
    (tmp_path / "docs" / "identity").mkdir(parents=True)
    (tmp_path / "docs" / "identity" / "humans.yml").write_text(_humans_yaml(), encoding="utf-8")
    (tmp_path / ".governance-paths.yaml").write_text(_governance_yaml(), encoding="utf-8")
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / "ADR-099.md").write_text("# ADR-099\n", encoding="utf-8")
    yield tmp_path


def _write_commit_msg(repo: Path, msg: str) -> None:
    (repo / ".git" / "COMMIT_EDITMSG").write_text(msg, encoding="utf-8")


def _stage(repo: Path, rel: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("payload\n", encoding="utf-8")
    subprocess.run(["git", "add", str(p)], cwd=repo, check=True)
    return p


# --------------------------------------------------------------------------- #
# _glob_match unit tests                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "rel, globs, expected",
    [
        ("docs/adr/ADR-099.md", ["docs/adr/**"], True),
        ("docs/adr/_template/x.md", ["docs/adr/**"], True),
        ("docs/specs/spec.md", ["docs/adr/**"], False),
        ("CLAUDE.md", ["CLAUDE.md"], True),
        ("CLAUDE.md", ["AGENTS.md"], False),
        ("src/foo/AGENTS.md", ["**/AGENTS.md"], True),
        ("AGENTS.md", ["**/AGENTS.md"], True),
        ("src/scieasy/qa/governance/honeypot.py", ["src/scieasy/qa/**"], True),
        ("src/scieasy/core/runtime.py", ["src/scieasy/qa/**"], False),
        ("foo/bar.txt", [], False),
        ("foo/bar.txt", ["", "/"], False),
    ],
)
def test_glob_match(rel: str, globs: list[str], expected: bool) -> None:
    assert _glob_match(rel, globs) is expected


def test_glob_match_handles_middle_double_star() -> None:
    assert _glob_match("a/b/c/d.md", ["a/**/d.md"]) is True


# --------------------------------------------------------------------------- #
# detect_author_kind                                                          #
# --------------------------------------------------------------------------- #


def test_detect_author_kind_tier2(repo: Path) -> None:
    assert detect_author_kind(repo) == "human-tier-2"


def test_detect_author_kind_tier1(repo: Path) -> None:
    subprocess.run(["git", "config", "user.email", "tier1@example.com"], cwd=repo, check=True)
    assert detect_author_kind(repo) == "human-tier-1"


def test_detect_author_kind_agent(repo: Path) -> None:
    subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=repo, check=True)
    _write_commit_msg(repo, "feat(qa): add thing\n\nAssisted-by: Claude:opus-4-7\n")
    assert detect_author_kind(repo) == "agent"


def test_detect_author_kind_unknown(repo: Path) -> None:
    subprocess.run(["git", "config", "user.email", "ghost@example.com"], cwd=repo, check=True)
    _write_commit_msg(repo, "feat(qa): unknown commit\n")
    assert detect_author_kind(repo) == "unknown"


def test_detect_author_kind_env_email_takes_precedence(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "tier2@example.com")
    subprocess.run(["git", "config", "user.email", "ghost@example.com"], cwd=repo, check=True)
    assert detect_author_kind(repo) == "human-tier-2"


def test_detect_author_kind_handles_missing_humans_yaml(repo: Path) -> None:
    (repo / "docs" / "identity" / "humans.yml").unlink()
    # No tier matches; no Assisted-by trailer either after fresh-init.
    _write_commit_msg(repo, "feat(qa): no humans registry\n")
    assert detect_author_kind(repo) == "unknown"


def test_detect_author_kind_handles_invalid_yaml(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / "docs" / "identity" / "humans.yml").write_text(": bad", encoding="utf-8")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "anyone@example.com")
    _write_commit_msg(repo, "feat(qa): broken yaml\n")
    assert detect_author_kind(repo) == "unknown"


# --------------------------------------------------------------------------- #
# find_governance_files                                                       #
# --------------------------------------------------------------------------- #


def test_find_governance_files_matches_seed(repo: Path) -> None:
    staged = [
        _stage(repo, "docs/adr/ADR-099.md"),
        _stage(repo, "src/scieasy/core/runtime.py"),  # non-governance
    ]
    matches = find_governance_files(staged, repo)
    assert [m.name for m in matches] == ["ADR-099.md"]


def test_find_governance_files_empty_when_registry_absent(repo: Path) -> None:
    (repo / ".governance-paths.yaml").unlink()
    staged = [_stage(repo, "docs/adr/ADR-099.md")]
    assert find_governance_files(staged, repo) == []


def test_find_governance_files_skips_files_outside_repo(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "other"
    outside.mkdir()
    f = outside / "stray.md"
    f.write_text("x", encoding="utf-8")
    assert find_governance_files([f], repo) == []


def test_find_governance_files_handles_broken_governance_yaml(repo: Path) -> None:
    (repo / ".governance-paths.yaml").write_text(": bad", encoding="utf-8")
    staged = [_stage(repo, "docs/adr/ADR-099.md")]
    assert find_governance_files(staged, repo) == []


# --------------------------------------------------------------------------- #
# check_governance_modification                                               #
# --------------------------------------------------------------------------- #


def test_check_returns_ok_when_no_governance_files(repo: Path) -> None:
    staged = [_stage(repo, "src/scieasy/core/runtime.py")]
    result = check_governance_modification(staged, repo_root=repo)
    assert result.ok is True
    assert result.governance_files == []


def test_check_returns_ok_for_tier2_human(repo: Path) -> None:
    staged = [_stage(repo, "docs/adr/ADR-099.md")]
    _write_commit_msg(repo, "feat(qa): edit ADR\n")
    result = check_governance_modification(staged, repo_root=repo)
    assert result.ok is True
    assert result.author_kind == "human-tier-2"


def test_check_rejects_unknown_author(repo: Path) -> None:
    subprocess.run(["git", "config", "user.email", "ghost@example.com"], cwd=repo, check=True)
    _write_commit_msg(repo, "feat(qa): edit\n")
    staged = [_stage(repo, "docs/adr/ADR-099.md")]
    result = check_governance_modification(staged, repo_root=repo)
    assert result.ok is False
    assert any("unknown-author" in f for f in result.findings)
    assert result.remediation is not None


def test_check_rejects_agent_missing_trailer(repo: Path) -> None:
    subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=repo, check=True)
    _write_commit_msg(repo, "feat(qa): edit\n\nAssisted-by: Claude:opus-4-7\n")
    staged = [_stage(repo, "docs/adr/ADR-099.md")]
    result = check_governance_modification(staged, repo_root=repo)
    assert result.ok is False
    assert any("missing-approval-trailer" in f for f in result.findings)
    assert result.author_kind == "agent"


def test_check_accepts_agent_with_trailer(repo: Path) -> None:
    subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=repo, check=True)
    _write_commit_msg(
        repo,
        "feat(qa): edit\n\nAssisted-by: Claude:opus-4-7\nGovernance-Modification-Approved-By: @tier2\n",
    )
    staged = [_stage(repo, "docs/adr/ADR-099.md")]
    result = check_governance_modification(staged, repo_root=repo)
    assert result.ok is True
    assert result.author_kind == "agent"


def test_check_rejects_tier1_missing_trailer(repo: Path) -> None:
    subprocess.run(["git", "config", "user.email", "tier1@example.com"], cwd=repo, check=True)
    _write_commit_msg(repo, "feat(qa): contributor edit\n")
    staged = [_stage(repo, "docs/adr/ADR-099.md")]
    result = check_governance_modification(staged, repo_root=repo)
    assert result.ok is False
    assert result.author_kind == "human-tier-1"


def test_check_accepts_tier1_with_trailer(repo: Path) -> None:
    subprocess.run(["git", "config", "user.email", "tier1@example.com"], cwd=repo, check=True)
    _write_commit_msg(
        repo,
        "feat(qa): contributor edit\n\nGovernance-Modification-Approved-By: @tier2\n",
    )
    staged = [_stage(repo, "docs/adr/ADR-099.md")]
    result = check_governance_modification(staged, repo_root=repo)
    assert result.ok is True


def test_check_result_is_dataclass_with_defaults() -> None:
    r = CheckResult(ok=True)
    assert r.findings == []
    assert r.governance_files == []
    assert r.author_kind == "unknown"


def test_check_with_no_commit_editmsg_falls_back_to_git_log(repo: Path) -> None:
    """Trigger the fallback path through ``_read_commit_message`` by removing
    ``.git/COMMIT_EDITMSG`` and committing first so ``git log`` has content."""
    subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=repo, check=True)
    p = _stage(repo, "src/scieasy/core/something.py")
    p.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", str(p)], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "feat: prior commit\n\nAssisted-by: Claude:opus\n"],
        cwd=repo,
        check=True,
    )
    # Remove COMMIT_EDITMSG to force git log fallback in detect_author_kind.
    msg = repo / ".git" / "COMMIT_EDITMSG"
    if msg.exists():
        msg.unlink()
    assert detect_author_kind(repo) == "agent"


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_main_returns_zero_on_clean_repo(repo: Path) -> None:
    rc = main(["--repo-root", str(repo)])
    assert rc == 0


def test_main_returns_one_on_violation(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "config", "user.email", "ghost@example.com"], cwd=repo, check=True)
    _stage(repo, "docs/adr/ADR-099.md")
    _write_commit_msg(repo, "feat(qa): unauthorized\n")
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(
            [
                "--repo-root",
                str(repo),
                "docs/adr/ADR-099.md",
            ]
        )
    assert rc == 1
    assert "unknown-author" in buf.getvalue()
    assert "Governance-Modification-Approved-By" in buf.getvalue()


def test_main_accepts_absolute_file_paths(repo: Path) -> None:
    staged = _stage(repo, "src/scieasy/core/runtime.py")
    rc = main(["--repo-root", str(repo), str(staged)])
    assert rc == 0


def test_main_reads_staged_files_when_no_positional_args(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no files are passed on argv, ``main`` should call ``_staged_files``
    which uses ``git diff --cached --name-only`` to learn what to check."""
    _stage(repo, "docs/adr/ADR-099.md")
    rc = main(["--repo-root", str(repo)])
    assert rc == 0  # Tier-2 author → ok even with governance edit.


def test_staged_files_git_unavailable(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``subprocess.run`` to raise FileNotFoundError; main must succeed."""
    import scieasy.qa.governance.mod_guard as mod

    real_run = mod.subprocess.run

    def _boom(cmd, *args, **kwargs):
        if cmd[:1] == ["git"] and cmd[1:2] == ["diff"]:
            raise FileNotFoundError
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    rc = main(["--repo-root", str(repo)])
    assert rc == 0


def test_staged_files_git_returns_nonzero(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``git diff --cached`` returning non-zero must yield an empty staged list."""
    import scieasy.qa.governance.mod_guard as mod

    class _Out:
        returncode = 1
        stdout = ""

    real_run = mod.subprocess.run

    def _wrapper(cmd, *args, **kwargs):
        if cmd[:1] == ["git"] and cmd[1:2] == ["diff"]:
            return _Out()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", _wrapper)
    rc = main(["--repo-root", str(repo)])
    assert rc == 0


def test_read_commit_message_git_unavailable(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``.git/COMMIT_EDITMSG`` is missing AND git is unavailable, fall back to ''."""
    import scieasy.qa.governance.mod_guard as mod

    msg = repo / ".git" / "COMMIT_EDITMSG"
    if msg.exists():
        msg.unlink()

    def _boom(*_a, **_kw):
        raise FileNotFoundError

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    # Author email read also goes through subprocess; ensure unknown kind.
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "")
    assert detect_author_kind(repo) == "unknown"


def test_read_commit_author_email_git_returns_nonzero(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``git config user.email`` fails, email is empty → unknown author."""
    import scieasy.qa.governance.mod_guard as mod

    class _Out:
        returncode = 1
        stdout = ""

    real_run = mod.subprocess.run

    def _wrapper(cmd, *args, **kwargs):
        if cmd[:3] == ["git", "config", "user.email"]:
            return _Out()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", _wrapper)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    assert detect_author_kind(repo) == "unknown"


def test_glob_match_middle_double_star_in_nested_path() -> None:
    """Trigger the ``a/**/b`` partition branch with a real nested path."""
    assert _glob_match("src/foo/middle/bar/qq.md", ["src/**/qq.md"]) is True


def test_glob_match_double_star_then_tail_against_part_iteration() -> None:
    """Trigger the ``any(part for part in p.parts)`` branch in ``_glob_match``."""
    # `**/x` matches any single component named 'x', and our impl iterates parts.
    assert _glob_match("a/x/c", ["**/x"]) is True


def test_glob_match_double_star_then_tail_no_match() -> None:
    """Negative case for the ``**/tail`` branch — exercises the False fall-through."""
    # No part / suffix path matches `tail`.
    assert _glob_match("a/b/c", ["**/nope"]) is False


def test_glob_match_double_star_tail_matches_via_parts_iteration() -> None:
    """Trigger the part-iteration fallback inside the ``**/tail`` branch.

    For ``**/AGENTS.md`` and ``deep/path/AGENTS.md``, neither the whole
    path nor any single ``part`` directly matches; the iterator over
    suffix joins (``deep/path/AGENTS.md``, ``path/AGENTS.md``, ``AGENTS.md``)
    catches the match in the third iteration.
    """
    assert _glob_match("deep/path/AGENTS.md", ["**/AGENTS.md"]) is True


def test_resolve_real_path_handles_oserror(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``Path.resolve`` to OSError; check_governance_modification must not crash."""
    _stage(repo, "docs/adr/ADR-099.md")
    _write_commit_msg(repo, "feat(qa): edit\n")

    real_resolve = Path.resolve

    def _selective_resolve(self, *args, **kwargs):
        # Only blow up on the staged governance file. Other resolves
        # (used by find_governance_files etc.) keep working.
        if self.name == "ADR-099.md" and not kwargs.get("strict", True):
            # _resolve_real_path uses strict=False explicitly — match.
            raise OSError("simulated")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", _selective_resolve)
    # The check still completes cleanly (Tier-2 author → ok).
    result = check_governance_modification([repo / "docs" / "adr" / "ADR-099.md"], repo_root=repo)
    assert result.author_kind == "human-tier-2"


def test_find_governance_handles_resolve_value_error(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``relative_to`` to raise ValueError inside find_governance_files."""
    outside = repo.parent / "outside.md"
    outside.write_text("x", encoding="utf-8")
    # ``outside.md`` resolves cleanly but cannot be made repo-relative —
    # the implementation catches ValueError and skips it.
    result = find_governance_files([outside], repo)
    assert result == []
    outside.unlink()


def test_symlink_trickery_finding(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a `_resolve_real_path` that simulates a symlink redirect."""
    import scieasy.qa.governance.mod_guard as mod

    governance_target = _stage(repo, "docs/adr/ADR-099.md")
    fake_real = repo / "docs" / "adr" / "ADR-OTHER.md"
    fake_real.write_text("# different\n", encoding="utf-8")

    def _fake_resolve(p: Path) -> Path:
        # Pretend the staged file is actually a symlink to ADR-OTHER.md.
        return fake_real.resolve()

    monkeypatch.setattr(mod, "_resolve_real_path", _fake_resolve)
    result = check_governance_modification([governance_target], repo_root=repo)
    # Even with a Tier-2 author, the symlink trickery defense fires.
    assert result.ok is False
    assert any("symlink-trickery" in f for f in result.findings)


def test_auto_generated_handedit_rejected(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject an entry into ``_AUTO_GENERATED_PATHS`` and verify hand-edit is rejected."""
    import scieasy.qa.governance.mod_guard as mod

    rel = "docs/adr/ADR-099.md"
    monkeypatch.setattr(mod, "_AUTO_GENERATED_PATHS", frozenset({rel}))

    staged = _stage(repo, rel)
    _write_commit_msg(repo, "feat(qa): hand-edit\n")
    result = check_governance_modification([staged], repo_root=repo)
    assert result.ok is False
    assert any("auto-generated-handedit" in f for f in result.findings)


def test_auto_generated_handedit_with_value_error_path(
    repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cover the ``except ValueError`` branch inside the auto-generated loop.

    Put the file outside ``repo_root`` so ``relative_to`` raises; the impl
    must fall back to ``gf.as_posix()`` and still detect the match.
    """
    import scieasy.qa.governance.mod_guard as mod

    # ``tmp_path`` IS the repo's tmp dir; need a path outside of it.
    outside_dir = tmp_path.parent / "elsewhere_auto"
    outside_dir.mkdir(exist_ok=True)
    outside = outside_dir / "outside_auto.md"
    outside.write_text("x", encoding="utf-8")
    fallback_rel = outside.as_posix()
    monkeypatch.setattr(mod, "_AUTO_GENERATED_PATHS", frozenset({fallback_rel}))
    # Bypass find_governance_files (which would reject the outside path)
    # and feed it directly into check_governance_modification.
    monkeypatch.setattr(mod, "find_governance_files", lambda *_a, **_kw: [outside])
    result = check_governance_modification([outside], repo_root=repo)
    # ``gf.resolve().relative_to(repo_root)`` raises ValueError; impl falls
    # back to ``gf.as_posix()`` which now matches the patched set.
    assert any("auto-generated-handedit" in f for f in result.findings)


def test_symlink_trickery_outside_repo_swallowed(repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If the resolved real path is outside the repo, the symlink-trickery
    branch's ``relative_to`` raises ValueError and the loop ``continue``s."""
    import scieasy.qa.governance.mod_guard as mod

    governance_target = _stage(repo, "docs/adr/ADR-099.md")
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x", encoding="utf-8")

    def _fake_resolve(p: Path) -> Path:
        return outside.resolve()

    monkeypatch.setattr(mod, "_resolve_real_path", _fake_resolve)
    result = check_governance_modification([governance_target], repo_root=repo)
    # Tier-2 author + symlink defense couldn't compute relative path → ok.
    assert result.author_kind == "human-tier-2"
