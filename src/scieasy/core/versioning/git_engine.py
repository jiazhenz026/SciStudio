"""Subprocess wrapper around the bundled git CLI (ADR-039 §3.1, §3.5).

The :class:`GitEngine` is the **only** module in SciEasy allowed to shell
out to git. All API routes (`scieasy.api.routes.git`) and runtime hooks
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

Parser strategy
---------------

Each method parses git stdout into typed dicts that the REST layer can
return to the frontend without further transformation. The shape of
those dicts is defined per-method in the comment blocks below and must
match the contract that `scieasy.api.routes.git` declares to clients.

Skeleton phase (D39-2.2a)
-------------------------

All methods raise :class:`NotImplementedError`. The detailed comment
blocks tell D39-2.2b exactly which subprocess invocation to run, how to
parse the output, what error envelope to raise, and which edge cases to
cover. The impl agent should not need to re-read ADR-039 for any method
— if a comment is insufficient, file a clarification issue rather than
guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class GitError(RuntimeError):
    """A git invocation returned non-zero exit.

    Carries enough information to render a structured 500 / 409 / 422
    response in the REST layer.

    Attributes
    ----------
    returncode : int
        Subprocess exit code from git.
    stderr : str
        Captured stderr (with ``LANG=C`` so wording is stable).
    git_args : list[str]
        The git args (after the binary) that produced the failure, for
        debugging / bug reports. Named ``git_args`` (not ``args``) to
        avoid shadowing :attr:`BaseException.args`.
    """

    def __init__(self, returncode: int, stderr: str, args: list[str]) -> None:
        super().__init__(f"git {' '.join(args)} → exit {returncode}: {stderr.strip()}")
        self.returncode = returncode
        self.stderr = stderr
        self.git_args = args


# ---------------------------------------------------------------------------
# Typed return shapes used by multiple methods
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadState:
    """Result of :meth:`GitEngine.head_state` — used by ADR-038 join.

    Attributes
    ----------
    commit_sha : str
        Full 40-char HEAD SHA.
    dirty : bool
        ``True`` if the working tree has uncommitted changes.
    """

    commit_sha: str
    dirty: bool


MergeResult = Literal["fast-forward", "clean", "conflict"]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class GitEngine:
    """Subprocess wrapper exposing the operations enumerated in ADR-039 §3.5.

    One instance per repository. Constructed with a project path; lazily
    resolves the bundled git binary on first use via :class:`GitBinary`.

    Method naming follows ADR-039 §3.5 table verbatim so REST endpoint
    names map 1:1 onto method names.
    """

    def __init__(self, project_path: Path) -> None:
        # Implementation note for D39-2.2b:
        # ---------------------------------
        # 1. Store ``self.project_path = project_path.resolve()``.
        # 2. Do NOT verify ``.git/`` exists here — :meth:`is_repository`
        #    is the explicit predicate. The engine must construct cleanly
        #    even for paths that are about to be ``init``-ed.
        # 3. Lazy-resolve the binary: ``self._binary: GitBinary | None = None``
        #    and ``self._git`` property that calls ``GitBinary.locate()``
        #    on first access, then caches. Lazy resolution lets the unit
        #    tests construct an engine without a real git on PATH.
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    # ------------------------------------------------------------------
    # Repository lifecycle
    # ------------------------------------------------------------------

    def init_repository(self, project_path: Path) -> str:
        """Initialize a new git repo + write default ``.gitignore`` + initial commit.

        Purpose
        -------
        Called by :meth:`ApiRuntime.create_project` and :meth:`open_project`
        when ``.git/`` is missing. Implements ADR-039 §3.2's auto-init
        contract.

        Signature contract
        ------------------
        - Input: ``project_path`` (must already exist as a directory; we
          do NOT create it).
        - Output: the SHA of the initial commit (40-char hex).
        - Errors: :class:`GitError` if any git step fails; ``OSError`` if
          we cannot write ``.gitignore``; :class:`FileExistsError` if
          ``.git/`` already exists (caller should detect this earlier).

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Verify ``project_path`` exists and is a directory; raise
           ``FileNotFoundError`` otherwise.
        2. Verify ``(project_path / ".git").exists()`` is False; raise
           ``FileExistsError`` otherwise (init on existing repo would
           be a programming error — the caller should branch on
           :meth:`is_repository`).
        3. Run ``git init --initial-branch=main <project_path>``.
           - Using ``--initial-branch=main`` avoids relying on the
             user's global ``init.defaultBranch`` config (which may be
             ``master`` on older installs).
           - This argument is supported on git ≥ 2.28 — verified against
             our pinned bundled version.
        4. Call :func:`write_default_gitignore(project_path)` (from
           ``gitignore_template`` module) — returns True if it wrote.
        5. Stage everything: ``git add -A`` (cwd=project_path). This
           captures workflow YAML, blocks/*.py, notes/*.md, project.yaml,
           README.md per ADR-039 §3.9.
        6. Commit with the canonical initial message:
           ``git commit -m "Initial commit (auto-generated by SciEasy)" --author="SciEasy User <noreply@scieasy.local>"``
           See OQ-1: until first-commit author prompt lands, use the
           noreply identity for the seed commit.
        7. Return the SHA from ``git rev-parse HEAD``.

        Edge cases
        ----------
        - Empty project (no files to commit) — ``git commit`` would fail
          on an empty tree. Solution: write a placeholder
          ``.scieasy/.gitkeep`` before staging. Actually simpler: write
          the default ``.gitignore`` (step 4) which guarantees at least
          one tracked file. Verify the index is non-empty before step 6.
        - User's global ``user.name`` / ``user.email`` unset — git would
          normally refuse the commit. We sidestep with ``--author=`` and
          pass ``-c user.email=...`` ``-c user.name=...`` as additional
          ``-c`` flags so the commit succeeds even on a fresh machine.
        - Project path on a network share / case-insensitive FS — git
          handles these; our only concern is the path must be writable.

        Test plan
        ---------
        - ``test_init_creates_git_dir`` — empty tmpdir → init → ``.git/``
          exists.
        - ``test_init_writes_default_gitignore`` — verify
          ``.gitignore`` exists with the template content.
        - ``test_init_creates_initial_commit`` — ``git log --oneline``
          shows one commit whose message starts with "Initial commit".
        - ``test_init_idempotence_via_is_repository`` — call
          :meth:`is_repository` after init returns True; second init
          should raise (caller must guard).

        ADR references
        --------------
        - §3.2 lines 90-97 (auto-init contract)
        - §3.9 lines 380-388 (initial commit captures existing files)
        - OQ-1 line 589 (author placeholder)
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def is_repository(self, path: Path) -> bool:
        """Check whether ``path`` is the root of a git repository.

        Purpose
        -------
        Called by :meth:`ApiRuntime.open_project` to decide between
        auto-init and "use as-is" (ADR-039 §3.2 step 1 vs step 2).

        Signature contract
        ------------------
        - Input: ``path`` — any directory.
        - Output: ``True`` if ``path/.git/`` exists OR if ``git -C path
          rev-parse --git-dir`` succeeds; ``False`` otherwise.
        - Errors: none (returns ``False`` on any failure).

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Cheap fast path: ``(path / ".git").exists()`` → True. This
           covers >99% of cases.
        2. Fallback (rare): run ``git -C <path> rev-parse --git-dir`` and
           check for exit 0. This handles unusual layouts (worktrees,
           bare repos referenced via ``.git`` file pointer) — but
           SciEasy projects never use those, so step 1 normally suffices.
        3. Catch all exceptions from the subprocess and return False —
           this method must never raise.

        Edge cases
        ----------
        - ``.git`` is a file (worktree pointer) — step 1 still returns
          True because ``.exists()`` is True for files. That is the
          correct behavior.
        - ``path`` does not exist — step 1 returns False; we never call
          subprocess on a missing path.

        Test plan
        ---------
        - ``test_is_repository_after_init`` — init then ``is_repository``
          returns True.
        - ``test_is_repository_empty_dir_false`` — fresh tmpdir returns
          False.
        - ``test_is_repository_handles_missing_path`` — non-existent
          path returns False without raising.

        ADR references
        --------------
        - §3.2 line 94 ("If `<project>/.git/` exists → use it as-is.")
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

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
        """Create a new commit; return the new HEAD SHA.

        Purpose
        -------
        Backs ``POST /api/git/commit``. Also called from
        :meth:`ApiRuntime.start_workflow` for the ``auto:`` pre-run
        commit, and from agent code paths for ``agent:`` commits.

        Signature contract
        ------------------
        - Inputs:
            - ``message`` — the commit message body (subject line +
              optional details). The pre-filled template's ``# `` lines
              are stripped by git itself (we pass with ``--cleanup=strip``).
            - ``files`` — optional list of paths to limit the commit to;
              if ``None``, commit all staged + tracked changes. Paths are
              relative to ``self.project_path``.
            - ``author`` — optional ``"Name <email>"`` string; if None,
              use the git config (set on init per OQ-1).
            - ``prefix`` — optional one of ``"auto"`` / ``"agent"`` /
              ``None``. If set, the final message is
              ``f"{prefix}: {message}"`` per ADR §3.4a. If None, message
              passes through as user-authored.
        - Output: 40-char commit SHA.
        - Errors:
            - :class:`GitError` on git failure.
            - ``ValueError`` if message is empty or whitespace-only.

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Validate ``message.strip()`` is non-empty.
        2. Compute final message:
              ``final = f"{prefix}: {message}" if prefix else message``
           Accepted prefixes are ``"auto"`` and ``"agent"`` only — raise
           ``ValueError`` for anything else.
        3. Stage:
           a. If ``files`` is None: ``git add -A`` (cwd=project_path).
           b. Else: ``git add -- <files>`` (cwd=project_path).
        4. Detect empty staged tree (``git diff --cached --quiet`` exits
           0 if nothing staged). If nothing to commit, raise
           :class:`GitError` with a clear "nothing to commit" envelope so
           the REST layer can return 409 Conflict. Do NOT silently
           succeed — the caller wants to know.
        5. Build commit args:
              ``["commit", "-m", final, "--cleanup=strip"]``
           append ``"--author", author`` if provided.
        6. Run; on non-zero exit, raise :class:`GitError`.
        7. Return ``git rev-parse HEAD`` (full SHA).

        Edge cases
        ----------
        - Empty tree pre-run-auto-commit — ``start_workflow`` should
          check :meth:`head_state().dirty` first and skip commit if
          clean. If commit is called with nothing dirty, raise
          ``GitError`` as above; do not silently no-op.
        - Files outside the repo — ``git add`` would error; that
          GitError propagates as a 400 in the REST layer.
        - Detached HEAD (rare; user did ``git checkout <sha>`` externally)
          — git still commits but creates a dangling commit. We accept
          this; the next branch switch creates a real ref or warns.
        - Files containing newlines in paths — git supports this with
          ``-z``; we don't, so document the limitation. Not a real
          concern for SciEasy workflows.

        Test plan
        ---------
        - ``test_commit_creates_new_sha`` — round-trip: init, write file,
          commit, log shows the SHA.
        - ``test_commit_with_auto_prefix`` — message starts with "auto:".
        - ``test_commit_raises_on_empty_message`` — ValueError.
        - ``test_commit_raises_on_clean_tree`` — GitError "nothing to
          commit".
        - ``test_commit_with_explicit_files`` — only listed files are
          committed even though others are dirty.

        ADR references
        --------------
        - §3.4 lines 142-154 (pre-run auto-commit semantics)
        - §3.4a lines 192-208 (agent commit prefix)
        - §3.5 line 217 (REST endpoint)
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def log(
        self,
        *,
        branch: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return commit history as a list of dicts.

        Purpose
        -------
        Backs ``GET /api/git/log``. Feeds the GitHistoryList and GitGraph
        views.

        Signature contract
        ------------------
        - Inputs:
            - ``branch`` — branch name to log; if None, log all branches
              (use ``--all``) so the graph view sees the full DAG.
            - ``limit`` — max commits to return; if None, no limit.
              Default limit chosen by the REST layer (typical 500).
        - Output: list of dicts, newest first, each with keys:
            - ``sha`` (str, full 40-char)
            - ``short_sha`` (str, 7-char)
            - ``parents`` (list[str], 0..N full SHAs)
            - ``author_name`` (str)
            - ``author_email`` (str)
            - ``author_date`` (str, ISO-8601 with tz)
            - ``subject`` (str, first line of message)
            - ``body`` (str, rest of message; may be "")
            - ``branches`` (list[str], refs/heads/* tips pointing here)
        - Errors: :class:`GitError`.

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Build the format template with a unit-separator delimiter
           (\\x1f) that is safe inside any commit message:
              ``%H%x1f%h%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b%x1e``
           - ``%aI`` is strict ISO-8601 (with timezone).
           - ``%x1f`` is the unit separator (US, 0x1f).
           - ``%x1e`` is the record separator (RS, 0x1e) — used to split
             commits since ``%b`` may contain newlines.
        2. Build args:
              ``["log", f"--format={template}"]``
           append ``"--all"`` if branch is None, else append the branch
           name.
           append ``"-n", str(limit)`` if limit is not None.
        3. Run; split stdout on ``\\x1e``; drop trailing empty.
        4. For each record, split on ``\\x1f`` into 8 fields.
        5. ``parents = field[2].split() if field[2] else []``.
        6. Build the per-commit dict.
        7. Resolve branch tips: separately call
              ``git for-each-ref --format="%(refname:short)\\t%(objectname)" refs/heads/``
           parse into ``sha → [branch_name]`` map, then attach to each
           commit dict's ``branches`` field. (Most commits will have
           empty list.)
        8. Return the list.

        Edge cases
        ----------
        - Empty repo (no commits) — git log exits 128 with "does not
          have any commits yet". Catch this specific case and return
          ``[]`` rather than raising; the REST layer surfaces an empty
          list to the GitHistoryList component which renders "No
          history yet".
        - Commit message contains the delimiter literally (extremely
          unlikely; \\x1f / \\x1e are non-printable) — accept the
          ambiguity in v1, document the edge case. If it becomes a
          real concern, switch to ``git log -z`` which is null-delimited.
        - Repos with thousands of commits — pass limit by default at
          the REST layer (e.g. 500); virtualization in the UI handles
          scrolling beyond that.

        Test plan
        ---------
        - ``test_log_returns_newest_first`` — make 3 commits;
          ``log()[0]["subject"]`` is the most recent.
        - ``test_log_includes_branches`` — create branch ``foo`` at
          HEAD; log entry for HEAD has ``branches=["foo", ...]``.
        - ``test_log_empty_repo_returns_list`` — fresh init pre-commit
          → empty list, no exception.
        - ``test_log_with_limit`` — 10 commits; ``log(limit=3)`` returns
          3 entries.

        ADR references
        --------------
        - §3.5 line 218 (REST endpoint shape)
        - §3.5b lines 286-336 (graph view consumes this data)
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def diff(
        self,
        from_sha: str,
        to_sha: str | None = None,
        *,
        files: list[str] | None = None,
    ) -> str:
        """Return a unified diff string.

        Purpose
        -------
        Backs ``GET /api/git/diff``. Frontend feeds the string to
        ``react-diff-viewer-continued`` (which accepts unified diff
        format directly).

        Signature contract
        ------------------
        - Inputs:
            - ``from_sha`` — source ref (SHA / branch / "HEAD").
            - ``to_sha`` — target ref; special values:
                - ``None`` or ``"WORKING"`` → working tree
                - ``"HEAD"`` → current HEAD (compare commit vs working)
                - full SHA → commit-to-commit
            - ``files`` — optional path filter.
        - Output: unified diff text. Empty string if no differences.
        - Errors: :class:`GitError` on invalid refs.

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Build args:
           - ``to_sha`` is None / "WORKING": ``["diff", from_sha]``
             (diff WORKING against from_sha — but we want from→working,
             so use ``"diff", from_sha]`` which compares from_sha to
             the working tree).
           - ``to_sha == "HEAD"``: ``["diff", from_sha, "HEAD"]``.
           - Otherwise: ``["diff", from_sha, to_sha]``.
        2. Append ``"--"`` + file paths if ``files`` provided. This is
           critical — without ``--`` git may misinterpret paths that
           look like refs.
        3. Append ``"--unified=3"`` for stable context lines.
        4. Run; return stdout. Empty stdout = no diff (caller renders
           "No changes").

        Edge cases
        ----------
        - Binary files — git emits "Binary files X and Y differ". The
          frontend recognizes this and renders a "binary" placeholder
          instead of feeding to react-diff-viewer.
        - Renamed files — git's default rename detection (50% similarity)
          emits ``rename from/to`` headers. ``react-diff-viewer`` does
          not render these natively; we accept the limitation in v1.
        - ``from_sha`` doesn't exist — GitError → REST returns 404.

        Test plan
        ---------
        - ``test_diff_commit_to_commit`` — two commits with different
          content → diff contains expected hunks.
        - ``test_diff_commit_to_working`` — uncommitted change → diff
          shows it.
        - ``test_diff_files_filter`` — restrict to one path; other
          changed files absent from output.
        - ``test_diff_empty_when_identical`` — same SHA twice → empty.

        ADR references
        --------------
        - §3.5 line 219 (diff endpoint)
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def restore(self, commit_sha: str, *, files: list[str] | None = None) -> None:
        """Restore files from a prior commit into the working tree.

        Purpose
        -------
        Backs ``POST /api/git/restore``. Default mode is **soft restore**
        per ADR-039 §3.6 — files are checked out without moving HEAD,
        leaving them as uncommitted changes the user can then commit
        manually.

        Signature contract
        ------------------
        - Inputs:
            - ``commit_sha`` — commit to restore from.
            - ``files`` — list of paths to restore; if None or empty,
              restore the whole worktree.
        - Output: None.
        - Errors: :class:`GitError`.

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Soft restore (default): ``git checkout <sha> -- <files...>``.
           - When ``files`` is None/empty, use
             ``git checkout <sha> -- .`` to restore everything.
           - This does NOT move HEAD — the user keeps their current
             branch position; the restored files appear as modifications
             in ``git status``.
        2. The "Hard restore" option (``git reset --hard``) is
           DEFERRED in v1 per ADR §3.6 — do not implement here.
        3. Working-tree stash protection: BEFORE step 1, check
           :meth:`is_dirty`. If dirty, auto-stash via
           ``git stash push -m "auto-stash before restore"`` and emit a
           log line for the UI to render the StashApplyDialog
           ("Your unsaved changes are stashed. Apply now? / Keep
           stashed / Discard"). The REST layer reads this side-effect
           via the next ``GET /api/git/stash`` call.

        Edge cases
        ----------
        - Commit doesn't exist — GitError → 404.
        - File doesn't exist in that commit — git creates the file in
          working tree as deleted (relative to HEAD); user sees it
          unstaged. Acceptable behavior.
        - Path traversal in ``files`` (``../../etc/passwd``) — git
          rejects paths outside the repo; we rely on git's own
          validation. Do NOT add a redundant path sanitizer here.

        Test plan
        ---------
        - ``test_restore_single_file`` — write content A, commit, write
          content B, restore from first commit; file is back to A.
        - ``test_restore_whole_worktree`` — same with files=None.
        - ``test_restore_dirty_tree_auto_stashes`` — modify file, call
          restore; stash list shows the auto-stash.
        - ``test_restore_nonexistent_sha`` — GitError.

        ADR references
        --------------
        - §3.5 line 220 (restore endpoint)
        - §3.6 lines 349-355 (soft restore default + auto-stash)
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    # ------------------------------------------------------------------
    # Branch operations
    # ------------------------------------------------------------------

    def branches(self) -> list[dict[str, Any]]:
        """List all local branches.

        Purpose
        -------
        Backs ``GET /api/git/branches``.

        Output shape
        ------------
        ``[{"name": "main", "head_sha": "...", "is_current": True}, ...]``

        Implementation steps
        --------------------
        1. Get current branch from :meth:`current_branch`.
        2. ``git for-each-ref --format="%(refname:short)\\t%(objectname)" refs/heads/``.
        3. Parse each line into ``{name, head_sha}``; set
           ``is_current = (name == current)``.
        4. Sort: current branch first, then alphabetical.

        Edge cases
        ----------
        - Detached HEAD — ``current_branch`` returns None; no branch
          marked current; UI renders a "(detached at <sha>)" badge.
        - No branches (fresh init pre-first-commit) — empty list.

        Test plan
        ---------
        - ``test_branches_lists_default_main`` — after init+commit, one
          branch named "main", current.
        - ``test_branches_lists_multiple`` — create two branches; both
          listed with correct ``is_current`` flag.

        ADR references
        --------------
        - §3.5 line 221.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def current_branch(self) -> str | None:
        """Return the name of the currently checked-out branch.

        Implementation
        --------------
        ``git rev-parse --abbrev-ref HEAD``. If output is ``"HEAD"``,
        we are in detached HEAD state → return None.

        Test plan
        ---------
        - ``test_current_branch_after_init`` → ``"main"``.
        - ``test_current_branch_detached_returns_none`` — checkout a
          SHA directly; returns None.

        ADR references
        --------------
        - §3.5 / §3.7.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def branch_create(self, name: str, base: str | None = None) -> None:
        """Create a new branch at ``base`` (or HEAD if None).

        Implementation
        --------------
        1. Validate name: no slashes that would conflict with refs, no
           empty, no whitespace. Let ``git check-ref-format`` decide —
           run it and surface its error.
        2. ``git branch <name> [<base>]`` — base defaults to HEAD.
        3. Do NOT switch to the new branch — :meth:`branch_switch` is a
           separate explicit action.

        Edge cases
        ----------
        - Name already exists — git fails; surface GitError.
        - Base ref doesn't exist — GitError.

        Test plan
        ---------
        - ``test_branch_create_at_head`` — new branch points to HEAD.
        - ``test_branch_create_at_sha`` — new branch points to specified
          SHA.
        - ``test_branch_create_rejects_invalid_name`` — GitError.

        ADR references
        --------------
        - §3.5 line 221 (REST endpoint), §3.7 line 363.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def branch_switch(self, name: str) -> None:
        """Switch to an existing branch.

        Implementation
        --------------
        1. Check :meth:`is_dirty` — if dirty, do NOT auto-stash here.
           The REST layer must prompt the user (StashApplyDialog) before
           calling switch; engine assumes the caller already resolved
           the dirty-tree question.
        2. ``git checkout <name>``.
        3. Emit a structured log line so the API can broadcast
           ``git.head_changed`` (already wired in D39-2.1 via
           ``workflow_watcher`` — engine does not push events directly).

        Edge cases
        ----------
        - Branch doesn't exist — GitError → 404.
        - Working tree dirty + caller forgot to stash — git refuses;
          GitError propagates as a 409 to caller.

        Test plan
        ---------
        - ``test_switch_branch_changes_head`` — switch, then
          ``current_branch()`` returns the new name.
        - ``test_switch_branch_dirty_tree_raises`` — modify file, switch
          to other branch with conflicting content → GitError.

        ADR references
        --------------
        - §3.5 line 221, §3.6 (stash-on-restore — analogous flow), §3.7.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def branch_delete(self, name: str, *, force: bool = False) -> None:
        """Delete a local branch.

        Implementation
        --------------
        1. Refuse to delete the currently-checked-out branch — return
           GitError early (with a clear message; matches git's own
           behavior but we want to fail with a structured envelope).
        2. ``git branch -d <name>`` (safe delete — fails if unmerged).
        3. If ``force=True``, use ``-D`` (force delete unmerged commits).

        Edge cases
        ----------
        - Branch is the only one — git allows deletion; we follow.
        - Unmerged commits + force=False — GitError; UI prompts user
          for confirmation, then retries with force=True.

        Test plan
        ---------
        - ``test_branch_delete_merged`` — succeeds.
        - ``test_branch_delete_unmerged_no_force_fails`` — GitError.
        - ``test_branch_delete_unmerged_force_succeeds`` — succeeds.

        ADR references
        --------------
        - §3.5 line 221 (DELETE endpoint), §3.7 line 364.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    # ------------------------------------------------------------------
    # Working-tree status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return working-tree status using ``--porcelain=v2``.

        Purpose
        -------
        Backs ``GET /api/git/status``. Also called by :meth:`head_state`,
        :meth:`is_dirty`, and the CommitDialog's auto-detected-files
        list (ADR §3.5 lines 230-244).

        Output shape
        ------------
        ``{"dirty": bool, "modified": [str, ...], "staged": [str, ...],
        "untracked": [str, ...], "conflicted": [str, ...]}``

        Implementation steps
        --------------------
        1. Run ``git status --porcelain=v2 --branch``.
        2. Parse each line per the v2 spec:
           - Line type ``"# "`` headers carry branch info.
           - Line type ``"1 "`` is a "ordinary changed entry" — fields
             include XY status, mode, OID, path.
             - X is index status (staged); Y is worktree status.
             - ``M`` = modified, ``A`` = added, ``D`` = deleted, ``.`` = clean.
           - Line type ``"2 "`` is a rename entry.
           - Line type ``"u "`` is an unmerged (conflicted) entry.
           - Line type ``"? "`` is untracked.
        3. Bucket each path:
           - staged: any X != ``"."``
           - modified: any Y != ``"."`` and not unmerged
           - untracked: ``"? "`` entries
           - conflicted: ``"u "`` entries
        4. ``dirty = bool(modified or staged or untracked or conflicted)``.
        5. Return the dict.

        Edge cases
        ----------
        - Empty repo (no HEAD yet) — branch header reports "(detached)";
          all entries untracked. Return shape still valid.
        - Submodules — out of scope per §3.10; we don't recurse.
        - Files with whitespace in path — porcelain=v2 quotes them; the
          parser must handle the quoting. Test with a fixture file
          ``"with space.txt"``.

        Test plan
        ---------
        - ``test_status_clean`` — fresh commit → dirty=False, all empty.
        - ``test_status_modified_unstaged`` — edit file → modified list
          has it, staged empty.
        - ``test_status_staged`` — git add → staged has it.
        - ``test_status_untracked`` — new file → untracked has it.
        - ``test_status_conflicted_after_merge`` — synthesize merge
          conflict → conflicted list non-empty.

        ADR references
        --------------
        - §3.5 line 222 (REST endpoint).
        - §3.5 line 244 (CommitDialog uses this to populate
          auto-detected list).
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def head_state(self) -> HeadState:
        """Return ``HeadState(commit_sha, dirty)`` for ADR-038 join.

        Purpose
        -------
        Called by :meth:`ApiRuntime.start_workflow` to populate
        ``runs.workflow_git_commit`` and the `workflow_dirty` flag in
        the ADR-038 lineage row.

        Implementation
        --------------
        1. ``commit_sha = git rev-parse HEAD`` (full SHA).
        2. ``dirty = self.status()["dirty"]``.
        3. Return ``HeadState(commit_sha, dirty)``.

        Edge cases
        ----------
        - Empty repo (no HEAD) — ``rev-parse HEAD`` fails. Return
          ``HeadState("", True)`` or raise? The caller in
          ``start_workflow`` only invokes head_state AFTER auto-init has
          guaranteed a HEAD exists, so raising GitError is acceptable —
          but the safer contract is to return ``("", False)`` and let
          the caller decide. Document the choice in the test plan.

        Test plan
        ---------
        - ``test_head_state_clean`` — after commit → dirty=False, SHA
          matches.
        - ``test_head_state_dirty`` — modify file → dirty=True.

        ADR references
        --------------
        - §3.4 line 152 (workflow_git_commit populates from this).
        - ADR-038 §3.1 (the join key).
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    # ------------------------------------------------------------------
    # Merge / cherry-pick
    # ------------------------------------------------------------------

    def merge(self, source_branch: str) -> dict[str, Any]:
        """Merge ``source_branch`` into current branch.

        Purpose
        -------
        Backs ``POST /api/git/merge``. Implements ADR-039 §3.5a flow.

        Output shape (matches §3.5 table line 223)
        ------------------------------------------
        ``{
            "result": "fast-forward" | "clean" | "conflict",
            "conflicted_files": [str, ...]  # empty unless result == "conflict"
        }``

        Implementation steps
        --------------------
        1. Detect FF possibility:
              ``git merge-base --is-ancestor HEAD <source_branch>``
           If exit 0, the current HEAD is an ancestor of source → FF
           possible.
        2. Run ``git merge --no-ff=auto <source_branch>``:
           - If exit 0 and HEAD moved (rev-parse HEAD before vs after):
             - If we detected FF in step 1 AND no merge commit was
               created → return ``{"result": "fast-forward", "conflicted_files": []}``
             - Else → ``{"result": "clean", "conflicted_files": []}``
               (git auto-created a merge commit; nothing further needed).
           - If exit 1: conflict.
             - Parse :meth:`status` for unmerged entries.
             - Return ``{"result": "conflict", "conflicted_files": [...]}``.
             - Working tree is left in merge state; git wrote conflict
               markers into the files in-place. The frontend's
               MergeFlow.tsx (D39-2.4b) drives the resolution UI from
               here.
           - Other non-zero exit: raise :class:`GitError`.

        Edge cases
        ----------
        - Source branch doesn't exist — GitError before step 2.
        - Already up to date — git emits "Already up to date." and exits
          0 with no HEAD movement. Return ``{"result": "fast-forward",
          "conflicted_files": []}`` (semantically: no work needed,
          treated as FF).
        - Octopus merge (multiple sources) — out of scope in v1.
        - Pre-existing dirty working tree — git refuses; GitError.
          Caller (REST layer) must call :meth:`is_dirty` first and
          prompt user via StashApplyDialog.

        Test plan
        ---------
        - ``test_merge_fast_forward`` — branch ahead of main; merge → FF.
        - ``test_merge_clean_three_way`` — divergent edits in different
          files → clean merge commit.
        - ``test_merge_conflict`` — divergent edits on same line →
          result == "conflict"; conflicted_files lists the file;
          ``status()["conflicted"]`` corroborates.
        - ``test_merge_nonexistent_branch`` — GitError.

        ADR references
        --------------
        - §3.5 lines 211-227 (merge endpoint + return shape).
        - §3.5a lines 246-283 (conflict resolution UI consumes the
          conflicted_files list).
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def cherry_pick(self, commit_sha: str) -> dict[str, Any]:
        """Cherry-pick a single commit onto current branch.

        Output shape — same as :meth:`merge`
        ------------------------------------
        ``{"result": "clean" | "conflict", "conflicted_files": [...]}``
        (cherry-pick never produces fast-forward — it always creates a
        new commit.)

        Implementation steps
        --------------------
        1. ``git cherry-pick <commit_sha>``.
        2. Exit 0 → ``{"result": "clean", "conflicted_files": []}``.
        3. Exit 1 → conflict; parse :meth:`status` for unmerged entries;
           return ``{"result": "conflict", ...}``.
        4. Other → GitError.

        Edge cases
        ----------
        - Empty cherry-pick (target already contains the change) — git
          exits 1 with "nothing to commit". Treat as "no-op success":
          ``{"result": "clean", "conflicted_files": []}``. Differentiate
          from a real conflict by checking that
          ``status()["conflicted"]`` is empty.
        - SHA doesn't exist — GitError.

        Test plan
        ---------
        - ``test_cherry_pick_clean`` — pick a commit from another branch
          that touches different files → clean.
        - ``test_cherry_pick_conflict`` — pick a commit that touches the
          same line as a local commit → conflict; same shape as merge.
        - ``test_cherry_pick_no_op_when_already_present`` — pick a
          commit already in history → result="clean".

        ADR references
        --------------
        - §3.5 line 224.
        - §3.7 line 366 (full branch ops in v1).
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    # ------------------------------------------------------------------
    # Stash
    # ------------------------------------------------------------------

    def stash_list(self) -> list[dict[str, Any]]:
        """List stashed changes.

        Output shape
        ------------
        ``[{"stash_id": "stash@{0}", "message": "...", "date": "<iso>"}, ...]``

        Implementation steps
        --------------------
        1. ``git stash list --format="%gd%x1f%gs%x1f%ai"``
        2. Parse each line on ``\\x1f``.
        3. Return list.

        Edge cases
        ----------
        - No stashes → empty list.

        Test plan
        ---------
        - ``test_stash_list_empty`` — fresh repo → [].
        - ``test_stash_list_after_save`` — stash_save then list → 1 entry.

        ADR references
        --------------
        - §3.5 line 225.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def stash_save(self, message: str | None = None) -> str:
        """Save current changes to a new stash; return the stash_id.

        Implementation
        --------------
        1. ``git stash push -m <message>`` (or no -m if None).
        2. After success, run :meth:`stash_list` and return ``[0]["stash_id"]``
           — the new stash is always at position 0.

        Edge cases
        ----------
        - Nothing to stash — git emits "No local changes to save" and
          exits 0. Treat as no-op: raise GitError("nothing to stash") so
          REST returns 409.

        Test plan
        ---------
        - ``test_stash_save_creates_entry`` — modify file, stash_save,
          status clean, stash_list shows one entry.
        - ``test_stash_save_clean_tree_raises`` — GitError.

        ADR references
        --------------
        - §3.5 line 225.
        - §3.6 lines 354-355 (auto-stash before restore uses this).
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def stash_apply(self, stash_id: str) -> None:
        """Apply a stash without dropping it.

        Implementation
        --------------
        ``git stash apply <stash_id>``. Use ``apply`` not ``pop`` — the
        REST layer offers a separate Drop action.

        Edge cases
        ----------
        - Conflict during apply — git leaves working tree in conflict
          state; conflicted files appear in :meth:`status`. The REST
          layer must surface this to the user (UI not specified in v1;
          punt to inline error toast + manual resolution).
        - stash_id doesn't exist — GitError → 404.

        Test plan
        ---------
        - ``test_stash_apply_restores_changes`` — save, clean, apply →
          changes back in working tree, stash still in list.

        ADR references
        --------------
        - §3.5 line 225.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def stash_drop(self, stash_id: str) -> None:
        """Drop a stash entry without applying it.

        Implementation
        --------------
        ``git stash drop <stash_id>``.

        Test plan
        ---------
        - ``test_stash_drop_removes_entry`` — save, drop, list is empty.

        ADR references
        --------------
        - §3.5 line 225.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    # ------------------------------------------------------------------
    # Conflict-resolution finalization
    # ------------------------------------------------------------------

    def merge_stage_file(self, file: str) -> None:
        """Stage a file after the user has resolved its conflict markers.

        Implementation
        --------------
        ``git add <file>`` (cwd=project_path). Called by the frontend's
        "Mark Resolved" button per ADR §3.5a step 3c.

        Edge cases
        ----------
        - File still has unresolved markers — git stages anyway; the
          impl should pre-grep for ``"<<<<<<"`` and refuse with a
          GitError("file still has conflict markers") so the UI can
          guide the user.

        Test plan
        ---------
        - ``test_merge_stage_file_clears_conflict`` — after stage,
          ``status()["conflicted"]`` does not contain the file.

        ADR references
        --------------
        - §3.5a lines 270-272.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def merge_complete(self) -> str:
        """Finalize a merge after all conflicts staged. Return new commit SHA.

        Implementation
        --------------
        1. Verify ``status()["conflicted"]`` is empty; else GitError.
        2. ``git commit --no-edit`` — git carries the merge state and
           default merge-commit message.
        3. Return ``git rev-parse HEAD``.

        Edge cases
        ----------
        - Called when no merge in progress — git errors; surface
          GitError as 409.

        Test plan
        ---------
        - ``test_merge_complete_creates_merge_commit`` — full
          conflict→resolve→complete flow; commit has two parents.

        ADR references
        --------------
        - §3.5a lines 273-276.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def merge_abort(self) -> None:
        """Abort a merge or cherry-pick in progress.

        Implementation
        --------------
        1. Detect mode by checking for ``MERGE_HEAD`` or ``CHERRY_PICK_HEAD``
           files in ``.git/``.
        2. Run the corresponding abort:
           - ``git merge --abort`` (if MERGE_HEAD)
           - ``git cherry-pick --abort`` (if CHERRY_PICK_HEAD)
           - else GitError("no merge / cherry-pick in progress")
        3. Verify working tree clean afterward; else GitError.

        Edge cases
        ----------
        - Both files present (very unusual) — prefer cherry-pick abort
          (more specific signal).

        Test plan
        ---------
        - ``test_merge_abort_restores_state`` — conflict, abort, status
          clean, no MERGE_HEAD.
        - ``test_cherry_pick_abort_restores_state`` — same for cherry.

        ADR references
        --------------
        - §3.5 line 225 (REST entry).
        - §3.5a lines 275-276.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")
