"""Private sibling for ``GitEngine`` merge / cherry-pick / conflict ops.

This module is **package-private** per ADR-028 Addendum 1 §C9 +
ADR-046 Addendum 1 ("private functions, not helper classes"): every
public symbol is prefixed with an underscore, the module name itself
starts with an underscore, and it contains zero ``class`` definitions.
External callers must import :class:`GitEngine` from
:mod:`scistudio.core.versioning.git_engine`; importing helpers
directly is unsupported and the names may change without notice.

The functions here were extracted from
:mod:`scistudio.core.versioning.git_engine` in issue #1472 (Phase 3
of the backend god-file refactor umbrella #1427) per ADR-046
Addendum 1. Bound-method bodies are byte-identical to the originals;
only ``self.`` was rewritten to ``engine.``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scistudio.core.versioning.errors import GitError

if TYPE_CHECKING:
    from scistudio.core.versioning.git_engine import GitEngine

# Identity constants (duplicated from git_engine to avoid a cycle at
# import-time; values must stay in sync with the canonical definitions
# in ``scistudio.core.versioning.git_engine``).
_DEFAULT_AUTHOR_NAME = "SciStudio User"
_DEFAULT_AUTHOR_EMAIL = "noreply@scistudio.local"


def _merge(engine: GitEngine, source_branch: str) -> dict[str, Any]:
    """Merge source into current. Returns ``{result, conflicted_files}``.

    See ADR-039 §3.5 line 223 + §3.5a.
    """
    # Capture HEAD before to detect FF.
    before = engine._rev_parse_head(engine.project_path)
    ff_possible = (
        engine._run(
            ["merge-base", "--is-ancestor", "HEAD", source_branch],
            check=False,
        ).returncode
        == 0
    )

    env_overrides = {
        "GIT_AUTHOR_NAME": _DEFAULT_AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": _DEFAULT_AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": _DEFAULT_AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": _DEFAULT_AUTHOR_EMAIL,
    }
    proc = engine._git.run(
        [
            "-c",
            f"user.name={_DEFAULT_AUTHOR_NAME}",
            "-c",
            f"user.email={_DEFAULT_AUTHOR_EMAIL}",
            "merge",
            "--no-edit",
            source_branch,
        ],
        cwd=engine.project_path,
        check=False,
        env=env_overrides,
    )

    if proc.returncode == 0:
        after = engine._rev_parse_head(engine.project_path)
        if before == after:
            # Already up to date.
            return {"result": "fast-forward", "conflicted_files": []}
        # Detect FF: if HEAD moved but new commit has only one parent
        # AND it was a known ancestor relationship.
        head_parents = engine._run(["rev-list", "--parents", "-n", "1", "HEAD"]).stdout.strip().split()
        if ff_possible and len(head_parents) == 2:
            return {"result": "fast-forward", "conflicted_files": []}
        return {"result": "clean", "conflicted_files": []}

    if proc.returncode == 1:
        # Exit 1 covers BOTH real conflicts AND non-conflict errors
        # like "merge: <name> - not something we can merge". Use the
        # ``status()`` ``conflicted`` bucket as the ground truth: if
        # git did not put any files into conflict state, the exit
        # was due to invalid input (or a different failure mode), so
        # surface it as a structured GitError so the REST layer can
        # return 404/400 instead of a misleading 200/"conflict".
        status = engine.status()
        if status["conflicted"]:
            return {
                "result": "conflict",
                "conflicted_files": status["conflicted"],
            }
        raise GitError(
            proc.returncode,
            proc.stderr or "",
            ["merge", source_branch],
        )

    raise GitError(
        proc.returncode,
        proc.stderr or "",
        ["merge", source_branch],
    )


def _cherry_pick(engine: GitEngine, commit_sha: str) -> dict[str, Any]:
    """Cherry-pick a commit. See ADR-039 §3.5 line 224."""
    env_overrides = {
        "GIT_AUTHOR_NAME": _DEFAULT_AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": _DEFAULT_AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": _DEFAULT_AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": _DEFAULT_AUTHOR_EMAIL,
    }
    proc = engine._git.run(
        [
            "-c",
            f"user.name={_DEFAULT_AUTHOR_NAME}",
            "-c",
            f"user.email={_DEFAULT_AUTHOR_EMAIL}",
            "cherry-pick",
            commit_sha,
        ],
        cwd=engine.project_path,
        check=False,
        env=env_overrides,
    )
    if proc.returncode == 0:
        return {"result": "clean", "conflicted_files": []}
    if proc.returncode == 1:
        status = engine.status()
        if not status["conflicted"]:
            # "nothing to commit" — treat as no-op.
            # Abort any pending state.
            engine._run(["cherry-pick", "--abort"], check=False)
            return {"result": "clean", "conflicted_files": []}
        return {"result": "conflict", "conflicted_files": status["conflicted"]}
    raise GitError(
        proc.returncode,
        proc.stderr or "",
        ["cherry-pick", commit_sha],
    )


def _merge_stage_file(engine: GitEngine, file: str) -> None:
    """Stage a file after the user resolved its conflict markers."""
    full_path = engine.project_path / file
    if full_path.exists():
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            if "<<<<<<<" in content or ">>>>>>>" in content:
                raise GitError(
                    1,
                    f"file '{file}' still has conflict markers",
                    ["add", file],
                )
        except OSError:
            pass
    engine._run(["add", "--", file])


def _merge_complete(engine: GitEngine) -> str:
    """Finalize merge after all conflicts staged. Returns new commit SHA."""
    status = engine.status()
    if status["conflicted"]:
        raise GitError(
            1,
            "cannot complete merge: conflicted entries remain",
            ["commit", "--no-edit"],
        )
    engine._run(
        [
            "-c",
            f"user.name={_DEFAULT_AUTHOR_NAME}",
            "-c",
            f"user.email={_DEFAULT_AUTHOR_EMAIL}",
            "commit",
            "--no-edit",
        ]
    )
    return engine._rev_parse_head(engine.project_path)


def _merge_abort(engine: GitEngine) -> None:
    """Abort a merge or cherry-pick in progress."""
    git_dir = engine.project_path / ".git"
    if (git_dir / "CHERRY_PICK_HEAD").exists():
        engine._run(["cherry-pick", "--abort"])
    elif (git_dir / "MERGE_HEAD").exists():
        engine._run(["merge", "--abort"])
    else:
        raise GitError(
            1,
            "no merge or cherry-pick in progress",
            ["merge", "--abort"],
        )
