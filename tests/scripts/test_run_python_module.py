"""Tests for ``scripts/hooks/run_python_module.py`` (issue #1609 git-env scrub).

The launcher scrubs inherited git env before running a hook's target module, so
the gate/pytest child it spawns in a linked worktree cannot redirect its git ops
onto the real shared ``.git``.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_LAUNCHER = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "run_python_module.py"


@pytest.fixture(scope="module")
def mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_python_module", _LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_python_module"] = module
    spec.loader.exec_module(module)
    return module


class TestScrubGitEnv:
    def test_removes_repo_locating_and_identity_vars(self, mod: ModuleType) -> None:
        env = {
            "GIT_DIR": "/repo/.git/worktrees/x",
            "GIT_WORK_TREE": "/repo/wt",
            "GIT_INDEX_FILE": "/repo/.git/worktrees/x/index",
            "GIT_COMMON_DIR": "/repo/.git",
            "GIT_OBJECT_DIRECTORY": "/repo/.git/objects",
            "GIT_AUTHOR_NAME": "Bad Actor",
            "GIT_COMMITTER_EMAIL": "bad@example.com",
            "PATH": "/usr/bin",
            "HOME": "/home/u",
        }
        removed = mod.scrub_git_env(env)
        assert env == {"PATH": "/usr/bin", "HOME": "/home/u"}
        assert set(removed) == {
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_COMMON_DIR",
            "GIT_OBJECT_DIRECTORY",
            "GIT_AUTHOR_NAME",
            "GIT_COMMITTER_EMAIL",
        }

    def test_is_idempotent(self, mod: ModuleType) -> None:
        env = {"GIT_DIR": "/x", "PATH": "/usr/bin"}
        assert mod.scrub_git_env(env) == ["GIT_DIR"]
        assert mod.scrub_git_env(env) == []
        assert env == {"PATH": "/usr/bin"}

    def test_clean_env_is_noop(self, mod: ModuleType) -> None:
        env = {"PATH": "/usr/bin", "LANG": "C"}
        assert mod.scrub_git_env(env) == []
        assert env == {"PATH": "/usr/bin", "LANG": "C"}

    def test_defaults_to_os_environ(self, mod: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setenv("GIT_DIR", "/leaked")
        monkeypatch.setenv("KEEP_ME", "1")
        mod.scrub_git_env()
        assert "GIT_DIR" not in os.environ
        assert os.environ.get("KEEP_ME") == "1"

    def test_identity_vars_separate_from_local_env_vars(self, mod: ModuleType) -> None:
        # Identity vars are intentionally tracked separately: they are NOT part
        # of ``git rev-parse --local-env-vars`` (which only covers repo location).
        assert not set(mod._GIT_IDENTITY_ENV_VARS) & set(mod._GIT_LOCAL_ENV_VARS)
        assert "GIT_AUTHOR_NAME" in mod.GIT_INHERITED_ENV_VARS


class TestLocalEnvVarParity:
    """Guard against git-version drift in the hardcoded repo-locating list."""

    def test_matches_git_rev_parse_local_env_vars(self, mod: ModuleType) -> None:
        git = shutil.which("git")
        if git is None:
            pytest.skip("git not available")
        assert git is not None  # narrow for type-checkers without pytest.skip NoReturn stubs
        result = subprocess.run([git, "rev-parse", "--local-env-vars"], capture_output=True, text=True)
        if result.returncode != 0:
            pytest.skip("git rev-parse --local-env-vars unavailable")
        actual = set(result.stdout.split())
        assert set(mod._GIT_LOCAL_ENV_VARS) == actual, (
            "_GIT_LOCAL_ENV_VARS is out of sync with `git rev-parse --local-env-vars`; "
            "update scripts/hooks/run_python_module.py."
        )
