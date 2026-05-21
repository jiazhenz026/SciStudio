"""Subprocess wrapper around the bundled git CLI (ADR-039 §3.1, §3.5).

The :class:`GitEngine` is the **only** module in SciStudio allowed to shell
out to git. All API routes (`scistudio.api.routes.git`) and runtime hooks
(``ApiRuntime.create_project``, ``ApiRuntime.start_workflow``) call into
this class.

Stable wire format
------------------

Per ADR-039 §3.1 lines 71-72: we use **plumbing commands with stable
machine-readable output** — never porcelain v1.

- ``git status --porcelain=v2``  (NOT plain ``--porcelain``)
- ``git log --format=...``       (custom delimited template)
- ``git diff --raw`` or unified diff text (stable)
- ``git rev-parse HEAD``         (single SHA, no ambiguity)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from scistudio.core.versioning.errors import GitError
from scistudio.core.versioning.git_binary import GitBinary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------
#
# ``GitError`` is defined in :mod:`scistudio.core.versioning.errors` and
# re-exported here so ``scistudio.core.versioning.git_engine.GitError``
# continues to resolve for every existing importer (REST layer, package
# ``__init__``, downstream tests). The extraction broke the former lazy-
# import pair-cycle with :mod:`scistudio.core.versioning.git_binary` (see
# #1337 / PR #1344).

__all__ = [
    "GitEngine",
    "GitError",
    "HeadState",
    "MergeResult",
]


# ---------------------------------------------------------------------------
# Typed return shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadState:
    """Result of :meth:`GitEngine.head_state` — used by ADR-038 join."""

    commit_sha: str
    dirty: bool


MergeResult = Literal["fast-forward", "clean", "conflict"]


# Default identity for the seed initial commit (OQ-1 placeholder).
_DEFAULT_AUTHOR_NAME = "SciStudio User"
_DEFAULT_AUTHOR_EMAIL = "noreply@scistudio.local"
_DEFAULT_AUTHOR = f"{_DEFAULT_AUTHOR_NAME} <{_DEFAULT_AUTHOR_EMAIL}>"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class GitEngine:
    """Subprocess wrapper exposing the operations enumerated in ADR-039 §3.5.

    One instance per repository. Lazily resolves the bundled git binary
    on first use via :class:`GitBinary`.
    """

    def __init__(self, project_path: Path) -> None:
        self.project_path = Path(project_path).resolve()
        # Lazy GitBinary — keeps construction cheap.
        self._binary: Any | None = None

    @property
    def _git(self) -> Any:
        """Lazy-resolved :class:`GitBinary`."""
        if self._binary is None:
            self._binary = GitBinary.locate()
        return self._binary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
    ) -> Any:
        """Invoke git with project_path as default cwd."""
        return self._git.run(args, cwd=cwd or self.project_path, check=check)

    def _author_env(self) -> dict[str, str]:
        """Identity env that lets commit succeed on a fresh machine."""
        return {
            "GIT_AUTHOR_NAME": _DEFAULT_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": _DEFAULT_AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": _DEFAULT_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": _DEFAULT_AUTHOR_EMAIL,
        }

    # ------------------------------------------------------------------
    # Repository lifecycle
    # ------------------------------------------------------------------

    def init_repository(self, project_path: Path) -> str:
        """Initialize new git repo + write .gitignore + initial commit.

        Returns the SHA of the initial commit. See ADR-039 §3.2, §3.9.
        """
        from scistudio.core.versioning.gitignore_template import write_default_gitignore

        target = Path(project_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Project path does not exist: {target}")
        if not target.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {target}")
        if (target / ".git").exists():
            raise FileExistsError(f".git already exists at {target}")

        # git init. ``--initial-branch=main`` requires git ≥ 2.28.
        self._git.run(
            ["init", "--initial-branch=main", str(target)],
            cwd=target.parent if target.parent.exists() else None,
        )

        # Write .gitignore so the first commit captures at least one file.
        write_default_gitignore(target)

        # Stage everything.
        self._git.run(["add", "-A"], cwd=target)

        # Commit with config-injected identity so this succeeds even
        # on a fresh machine with no global user.name / user.email.
        self._git.run(
            [
                "-c",
                f"user.name={_DEFAULT_AUTHOR_NAME}",
                "-c",
                f"user.email={_DEFAULT_AUTHOR_EMAIL}",
                "commit",
                "-m",
                "Initial commit (auto-generated by SciStudio)",
                f"--author={_DEFAULT_AUTHOR}",
            ],
            cwd=target,
        )
        return self._rev_parse_head(target)

    def _rev_parse_head(self, cwd: Path) -> str:
        proc = self._git.run(["rev-parse", "HEAD"], cwd=cwd)
        return str(proc.stdout).strip()

    def is_repository(self, path: Path) -> bool:
        """Check whether ``path`` is the root of a git repository.

        See ADR-039 §3.2 line 94.
        """
        try:
            if (Path(path) / ".git").exists():
                return True
            # Rare fallback for unusual layouts.
            proc = self._git.run(["-C", str(path), "rev-parse", "--git-dir"], check=False)
            return bool(proc.returncode == 0)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Commit / log / diff / restore
    # ------------------------------------------------------------------

    def commit(
        self,
        message: str,
        *,
        files: list[str] | None = None,
        author: str | None = None,
        prefix: str | None = None,
    ) -> str:
        """Create a new commit; return the new HEAD SHA. See ADR-039 §3.4."""
        if not message or not message.strip():
            raise ValueError("Commit message must not be empty.")

        if prefix is not None:
            if prefix not in ("auto", "agent"):
                raise ValueError(f"Invalid commit prefix {prefix!r} — only 'auto' or 'agent' allowed.")
            final_message = f"{prefix}: {message}"
        else:
            final_message = message

        # Stage.
        if files is None:
            self._run(["add", "-A"])
        else:
            self._run(["add", "--", *files])

        # D39-3.2 (#968) P2-C: empty-repo edge case.
        #
        # ``git diff --cached --quiet`` against a missing HEAD (a freshly
        # ``git init``-ed repo with no commits) historically returned 0
        # even when the index was non-empty — making the empty-tree guard
        # below raise ``nothing to commit`` for what is actually the
        # repo's initial commit. Detect the no-HEAD case first via
        # ``git rev-parse --verify HEAD`` (rc != 0). When HEAD is missing,
        # fall back to ``git diff --cached --quiet HEAD`` against the
        # empty-tree object so the staged-files check is correct.
        head_check = self._run(["rev-parse", "--verify", "-q", "HEAD"], check=False)
        has_head = head_check.returncode == 0
        if has_head:
            proc = self._run(["diff", "--cached", "--quiet"], check=False)
            tree_is_empty = proc.returncode == 0
        else:
            # No HEAD: ask git directly whether the index has anything
            # staged. ``ls-files --cached`` prints one line per staged
            # entry; empty stdout means the index is empty.
            ls_proc = self._run(["ls-files", "--cached"], check=False)
            tree_is_empty = not (ls_proc.stdout or "").strip()
        if tree_is_empty:
            raise GitError(1, "nothing to commit, working tree clean", ["commit"])

        # Build commit invocation with config-injected identity so
        # commits succeed even when the user has no global user.name.
        commit_args = [
            "-c",
            f"user.name={_DEFAULT_AUTHOR_NAME}",
            "-c",
            f"user.email={_DEFAULT_AUTHOR_EMAIL}",
            "commit",
            "-m",
            final_message,
            "--cleanup=strip",
        ]
        if author:
            commit_args.extend(["--author", author])
        self._run(commit_args)
        return self._rev_parse_head(self.project_path)

    def log(
        self,
        *,
        branch: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return commit history. See ADR-039 §3.5 line 218."""
        US = "\x1f"  # noqa: N806 — unit separator
        RS = "\x1e"  # noqa: N806 — record separator
        template = f"%H{US}%h{US}%P{US}%an{US}%ae{US}%aI{US}%s{US}%b{RS}"

        args = ["log", f"--format={template}"]
        if branch is None:
            args.append("--all")
        else:
            args.append(branch)
        if limit is not None:
            args.extend(["-n", str(limit)])

        proc = self._run(args, check=False)
        if proc.returncode != 0:
            stderr_lower = (proc.stderr or "").lower()
            if (
                "does not have any commits" in stderr_lower
                or "bad default revision" in stderr_lower
                or ("unknown revision" in stderr_lower and branch is None)
            ):
                return []
            raise GitError(proc.returncode, proc.stderr or "", args)

        # Build ref-tip map. Hotfix #1011: include remote-tracking refs
        # (refs/remotes/) and tags (refs/tags/) in addition to local
        # branches (refs/heads/). Pre-fix, commits that were tips of a
        # remote ref or a tag but had no children in the local history
        # rendered with `branches: []` — the frontend graph then had no
        # label to render next to the dot, producing the "断头" look
        # (orphan merge dot with no incoming line and no name attached).
        # Including all three scan paths gives the frontend a label set
        # to anchor every orphan tip with a chip the way vscode-git-graph
        # / GitLens do.
        ref_proc = self._run(
            [
                "for-each-ref",
                "--format=%(refname:short)\t%(objectname)",
                "refs/heads/",
                "refs/remotes/",
                "refs/tags/",
            ],
            check=False,
        )
        sha_to_branches: dict[str, list[str]] = {}
        if ref_proc.returncode == 0:
            for line in (ref_proc.stdout or "").splitlines():
                if "\t" not in line:
                    continue
                name, sha = line.split("\t", 1)
                # Skip the synthetic "origin/HEAD" symbolic ref which just
                # mirrors the default branch — would render as a duplicate
                # chip with no extra info.
                if name.endswith("/HEAD"):
                    continue
                sha_to_branches.setdefault(sha, []).append(name)

        records = (proc.stdout or "").split(RS)
        out: list[dict[str, Any]] = []
        for rec in records:
            rec = rec.lstrip("\n")
            if not rec:
                continue
            fields = rec.split(US)
            if len(fields) < 8:
                continue
            sha, short_sha, parents_raw, an, ae, ai, subject, body = fields[:8]
            parents = parents_raw.split() if parents_raw else []
            out.append(
                {
                    "sha": sha,
                    "short_sha": short_sha,
                    "parents": parents,
                    "author_name": an,
                    "author_email": ae,
                    "author_date": ai,
                    "subject": subject,
                    "body": body,
                    "branches": sha_to_branches.get(sha, []),
                }
            )
        return out

    def diff(
        self,
        from_sha: str,
        to_sha: str | None = None,
        *,
        files: list[str] | None = None,
    ) -> str:
        """Return a unified diff string. See ADR-039 §3.5 line 219."""
        args = ["diff", "--unified=3"]
        if to_sha is None or to_sha == "WORKING":
            args.append(from_sha)
        elif to_sha == "HEAD":
            args.extend([from_sha, "HEAD"])
        else:
            args.extend([from_sha, to_sha])
        if files:
            args.append("--")
            args.extend(files)
        proc = self._run(args)
        return proc.stdout or ""

    def restore(self, commit_sha: str, *, files: list[str] | None = None) -> None:
        """Soft restore (no HEAD move). See ADR-039 §3.6.

        Hotfix #997: when every target file's content at ``commit_sha``
        is byte-identical to its current working-tree content, restore
        is a no-op — skip the actual ``git checkout``. Pre-fix, clicking
        "Restore this run's workflow" on a run whose recorded commit
        happened to match the current working tree still triggered an
        auto-handler against a tree that was dirty in *any* file (even
        unrelated ones). The no-op short-circuit eliminates that
        false-dirty cascade for the specific-files variant (the most
        common Lineage tab path: ``files=['workflows/<id>.yaml']``).
        """
        # Skip-if-unchanged short-circuit (files variant only).
        if files:
            try:
                all_unchanged = self._files_unchanged_vs_commit(commit_sha, files)
            except GitError:
                # If we can't compare (commit doesn't exist, etc.) let
                # the subsequent checkout produce the real error message.
                all_unchanged = False
            if all_unchanged:
                logger.debug(
                    "restore: %s @ %s already matches working tree; skipping checkout",
                    files,
                    commit_sha[:7],
                )
                return

        args = ["checkout", commit_sha, "--"]
        if files:
            args.extend(files)
        else:
            args.append(".")
        self._run(args)

    def _files_unchanged_vs_commit(self, commit_sha: str, files: list[str]) -> bool:
        """Return True iff every file's worktree content equals its
        content at *commit_sha*.

        Uses ``git diff --quiet <commit> -- <files>``: rc 0 means no
        diff, rc 1 means diff, rc other means error.

        Helper for the hotfix #997 skip-if-unchanged short-circuit in
        :meth:`restore`.
        """
        diff_args = ["diff", "--quiet", commit_sha, "--", *files]
        proc = self._run(diff_args, check=False)
        if proc.returncode == 0:
            return True
        if proc.returncode == 1:
            return False
        # Any other return code: treat as unable-to-determine; let the
        # caller fall through to the normal checkout path.
        raise GitError(proc.returncode, proc.stderr or "", diff_args)

    # ------------------------------------------------------------------
    # Branch operations
    # ------------------------------------------------------------------

    def branches(self) -> list[dict[str, Any]]:
        """List all local branches. See ADR-039 §3.5 line 221."""
        current = self.current_branch()
        proc = self._run(
            [
                "for-each-ref",
                "--format=%(refname:short)\t%(objectname)",
                "refs/heads/",
            ]
        )
        out: list[dict[str, Any]] = []
        for line in (proc.stdout or "").splitlines():
            if "\t" not in line:
                continue
            name, sha = line.split("\t", 1)
            out.append(
                {
                    "name": name,
                    "head_sha": sha,
                    "is_current": (name == current),
                }
            )
        # Sort: current first, then alphabetical.
        out.sort(key=lambda x: (not x["is_current"], x["name"]))
        return out

    def current_branch(self) -> str | None:
        """Return the name of the currently checked-out branch, or None."""
        proc = self._run(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if proc.returncode != 0:
            return None
        name = (proc.stdout or "").strip()
        if not name or name == "HEAD":
            return None
        return name

    def branch_create(self, name: str, base: str | None = None) -> None:
        """Create a new branch (at HEAD by default)."""
        args = ["branch", name]
        if base:
            args.append(base)
        self._run(args)

    def branch_switch(self, name: str) -> None:
        """Switch to an existing branch. Caller must resolve dirty tree first."""
        self._run(["checkout", name])

    def branch_delete(self, name: str, *, force: bool = False) -> None:
        """Delete a local branch (refuses to delete current)."""
        if self.current_branch() == name:
            raise GitError(
                1,
                f"Cannot delete the currently checked-out branch '{name}'.",
                ["branch", "-d", name],
            )
        flag = "-D" if force else "-d"
        self._run(["branch", flag, name])

    # ------------------------------------------------------------------
    # Working-tree status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return working-tree status via ``--porcelain=v2``.

        See ADR-039 §3.5 line 222.
        """
        proc = self._run(["status", "--porcelain=v2", "--branch"], check=False)
        if proc.returncode != 0:
            # Most common cause: not a git repo. Return clean defaults.
            return {
                "dirty": False,
                "modified": [],
                "staged": [],
                "untracked": [],
                "conflicted": [],
            }

        modified: list[str] = []
        staged: list[str] = []
        untracked: list[str] = []
        conflicted: list[str] = []

        for raw_line in (proc.stdout or "").splitlines():
            if not raw_line:
                continue
            tag = raw_line[0]
            if tag == "#":
                continue
            if tag == "?":
                # Untracked: ``? <path>``
                parts = raw_line.split(" ", 1)
                if len(parts) == 2:
                    untracked.append(parts[1])
                continue
            if tag == "!":
                # Ignored — skip.
                continue
            if tag == "u":
                # Unmerged entry: ``u <XY> <sub> <m1> <m2> <m3> <mw> <h1> <h2> <h3> <path>``
                parts = raw_line.split(" ", 10)
                if len(parts) >= 11:
                    conflicted.append(parts[10])
                continue
            if tag == "1":
                # Ordinary changed: ``1 <XY> ... <path>``
                parts = raw_line.split(" ", 8)
                if len(parts) < 9:
                    continue
                xy = parts[1]
                path = parts[8]
                x, y = xy[0], xy[1]
                if x != ".":
                    staged.append(path)
                if y != ".":
                    modified.append(path)
                continue
            if tag == "2":
                # Rename / copy: ``2 <XY> ... <path><tab><origPath>``
                parts = raw_line.split(" ", 9)
                if len(parts) < 10:
                    continue
                xy = parts[1]
                rest = parts[9]
                # rest is "<path>\t<origPath>"
                path = rest.split("\t", 1)[0]
                x, y = xy[0], xy[1]
                if x != ".":
                    staged.append(path)
                if y != ".":
                    modified.append(path)
                continue

        dirty = bool(modified or staged or untracked or conflicted)
        return {
            "dirty": dirty,
            "modified": sorted(set(modified)),
            "staged": sorted(set(staged)),
            "untracked": sorted(set(untracked)),
            "conflicted": sorted(set(conflicted)),
        }

    def head_state(self) -> HeadState:
        """Return (HEAD SHA, dirty). Used by ADR-038 lineage join."""
        proc = self._run(["rev-parse", "HEAD"], check=False)
        if proc.returncode != 0:
            return HeadState("", False)
        sha = (proc.stdout or "").strip()
        return HeadState(sha, self.status()["dirty"])

    # ------------------------------------------------------------------
    # Merge / cherry-pick
    # ------------------------------------------------------------------

    def merge(self, source_branch: str) -> dict[str, Any]:
        """Merge source into current. Returns ``{result, conflicted_files}``.

        See ADR-039 §3.5 line 223 + §3.5a.
        """
        # Capture HEAD before to detect FF.
        before = self._rev_parse_head(self.project_path)
        ff_possible = (
            self._run(
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
        proc = self._git.run(
            [
                "-c",
                f"user.name={_DEFAULT_AUTHOR_NAME}",
                "-c",
                f"user.email={_DEFAULT_AUTHOR_EMAIL}",
                "merge",
                "--no-edit",
                source_branch,
            ],
            cwd=self.project_path,
            check=False,
            env=env_overrides,
        )

        if proc.returncode == 0:
            after = self._rev_parse_head(self.project_path)
            if before == after:
                # Already up to date.
                return {"result": "fast-forward", "conflicted_files": []}
            # Detect FF: if HEAD moved but new commit has only one parent
            # AND it was a known ancestor relationship.
            head_parents = self._run(["rev-list", "--parents", "-n", "1", "HEAD"]).stdout.strip().split()
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
            status = self.status()
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

    def cherry_pick(self, commit_sha: str) -> dict[str, Any]:
        """Cherry-pick a commit. See ADR-039 §3.5 line 224."""
        env_overrides = {
            "GIT_AUTHOR_NAME": _DEFAULT_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": _DEFAULT_AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": _DEFAULT_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": _DEFAULT_AUTHOR_EMAIL,
        }
        proc = self._git.run(
            [
                "-c",
                f"user.name={_DEFAULT_AUTHOR_NAME}",
                "-c",
                f"user.email={_DEFAULT_AUTHOR_EMAIL}",
                "cherry-pick",
                commit_sha,
            ],
            cwd=self.project_path,
            check=False,
            env=env_overrides,
        )
        if proc.returncode == 0:
            return {"result": "clean", "conflicted_files": []}
        if proc.returncode == 1:
            status = self.status()
            if not status["conflicted"]:
                # "nothing to commit" — treat as no-op.
                # Abort any pending state.
                self._run(["cherry-pick", "--abort"], check=False)
                return {"result": "clean", "conflicted_files": []}
            return {"result": "conflict", "conflicted_files": status["conflicted"]}
        raise GitError(
            proc.returncode,
            proc.stderr or "",
            ["cherry-pick", commit_sha],
        )

    # ------------------------------------------------------------------
    # Conflict-resolution finalization
    # ------------------------------------------------------------------

    def merge_stage_file(self, file: str) -> None:
        """Stage a file after the user resolved its conflict markers."""
        full_path = self.project_path / file
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
        self._run(["add", "--", file])

    def merge_complete(self) -> str:
        """Finalize merge after all conflicts staged. Returns new commit SHA."""
        status = self.status()
        if status["conflicted"]:
            raise GitError(
                1,
                "cannot complete merge: conflicted entries remain",
                ["commit", "--no-edit"],
            )
        self._run(
            [
                "-c",
                f"user.name={_DEFAULT_AUTHOR_NAME}",
                "-c",
                f"user.email={_DEFAULT_AUTHOR_EMAIL}",
                "commit",
                "--no-edit",
            ]
        )
        return self._rev_parse_head(self.project_path)

    def merge_abort(self) -> None:
        """Abort a merge or cherry-pick in progress."""
        git_dir = self.project_path / ".git"
        if (git_dir / "CHERRY_PICK_HEAD").exists():
            self._run(["cherry-pick", "--abort"])
        elif (git_dir / "MERGE_HEAD").exists():
            self._run(["merge", "--abort"])
        else:
            raise GitError(
                1,
                "no merge or cherry-pick in progress",
                ["merge", "--abort"],
            )
