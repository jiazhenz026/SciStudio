[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs; this slice is spec §12.2 steps 3, 5, and 17 — the backend half of the personal tool library.
- Task kind: feature
- Persona: implementer
- Issues: #1995 (backend half) and #1996 (backend half)
- Issue URLs: https://github.com/jiazhenz026/SciStudio/issues/1995 , https://github.com/jiazhenz026/SciStudio/issues/1996
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Tracking branch (your merge target): feat/1995-adr-053-personal-tool-library
- Agent branch: feat/1995-origin-tiers-and-user-library-write
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-b1
- Gate record: create with `gate_record init --slug 1995-origin-tiers-and-user-library-write`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§8.3 rows B1)

Your branch is based on `feat/1995-adr-053-personal-tool-library`, which is itself based on
the Track A defect branch. Track A (#2020, #2021, #2009, #2022) has already landed there:
the shared drop-in provisioning helper `src/scistudio/core/dropins.py` exists, registry
reload symmetry is fixed, and a drop-in block can import a drop-in type. Build on that;
do not re-implement or modify it.

## Required Rules

Read and follow:

- The GitHub issues `#1995` and `#1996`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §2.2, §2.3, §3 (FR-001 – FR-005), §4 (FR-006 – FR-011), §6 (FR-017 – FR-019 for the origin condition), §14
- docs/adr/ADR-053.md §3

## Scope

You own only:

- `src/scistudio/api/_block_source.py`
- `src/scistudio/api/routes/blocks.py` (origin field only)
- `src/scistudio/api/routes/user_library.py` (new)
- `src/scistudio/api/schemas.py` (block-origin and user-library models only)
- `src/scistudio/api/__init__.py` or wherever routers are registered
- `src/scistudio/ai/agent/mcp/**` (the promotion tool, FR-011)
- `tests/api/test_block_origin_tiers.py` (new)
- `tests/api/test_user_library_write.py` (new)
- MCP promotion tool tests under `tests/ai/`
- `CHANGELOG.md` (one entry)

You must not touch:

- `src/scistudio/core/**` — B2 owns `core/types/base.py` and `core/types/registry.py`; A1 owns `core/dropins.py`
- `src/scistudio/api/routes/types.py` — B2 owns it
- `src/scistudio/blocks/**`
- Any `frontend/**` path — B3, B4, B5 own the frontend
- `docs/ai-developer/**`

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone. B3 works the frontend palette in parallel; B2 lands after you and
  will consume your shared origin resolver; a second manager's spec 2 track touches
  `src/scistudio/ai/agent/mcp/` for session spawn.
- MUST work only on your assigned branch, in your assigned worktree.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- MUST NOT open a PR. Push your branch and report; the manager integrates.
- Edit only your own checklist rows (§8.3 rows beginning `B1`).

## TODO And Deferral Rule

Deferred work must be tracked with `TODO(#NNN): <reason>` citing an issue, ADR, spec, or
follow-up ticket. The owner directive is **complete delivery with no deferred scope** —
if something must be deferred, stop and report it as a blocker.

Known deferred items: N/A

## Frozen Contracts (manager-set; parallel agents code against these)

**Block origin vocabulary** (FR-001, FR-002, FR-004):
`builtin` | `user` | `project` | `package` | `custom`.
`custom` is the unresolvable-path fallback ONLY. `builtin` is unchanged from today so
existing consumers keep working.

**Type origin vocabulary** (FR-005), which B2 will use through your resolver:
`core` | `user` | `project` | `package` | `custom`.

**Shared origin resolver** (FR-003): ONE function, used by both the block surface and the
type surface. You create it. B2 consumes it and is forbidden from writing a second path
comparison. Design its signature so a type spec can be resolved through it without
importing anything block-specific, and say what that signature is in your report.

**User library roots**: `~/.scistudio/blocks/` and `~/.scistudio/types/`, obtained from
A1's `src/scistudio/core/dropins.py` helper. Do NOT hardcode `Path.home() / ".scistudio"`
anywhere — that is exactly the drift #2020 removed (FR-058).

## Work To Do

1. **FR-001** — `map_block_origin` resolves a `tier1` block to `user` when its `file_path`
   is under the user-wide blocks root, and to `project` when it is under the active
   project's blocks directory. Today it collapses both to `custom`
   (`src/scistudio/api/_block_source.py:23`).

2. **FR-002** — when the path resolves to neither root (absent `file_path`, a symlink
   escaping both, a differing Windows drive), fall back to `custom`. Behaviour degrades; it
   does not break. Existing consumers of `custom` MUST keep working. This repository runs
   on Windows — test the differing-drive case, not just POSIX symlinks.

3. **FR-003** — one shared resolver implementation, per the frozen contract above.

4. **FR-004** — the block list response carries the resolved origin.

5. **FR-006** — a new endpoint accepts writes into the user-wide library. It serves both
   targets (`~/.scistudio/blocks/` and `~/.scistudio/types/`), **selected explicitly by the
   caller, never inferred from file content**.

6. **FR-007** — the path constraint is the **inverse** of the project endpoint's: the
   resolved target MUST be inside the relevant user library root. Traversal and symlink
   escapes are rejected with 403, matching `PUT /api/projects/{project_id}/file`
   (`src/scistudio/api/routes/projects.py:286`) in behaviour and error shape.

   Spec §14 names this "the highest-risk surface in the spec". A separate no-context audit
   agent will review it independently. Write it as if it will be attacked: resolve symlinks
   before comparing, compare resolved real paths not string prefixes, reject absolute paths
   and drive-relative paths, and reject anything that is not a `.py` file directly in the
   target root.

7. **FR-008** — no silent overwrite. An existing file at the target MUST be reported to the
   caller so the UI can prompt. Overwrite requires an explicit caller opt-in. Also provide
   the existence probe the frontend needs (FR-031 gives `probeProjectFileExistence` a user
   library counterpart) — B5 will call it.

8. **FR-009** — `PUT /api/projects/{project_id}/file` MUST keep rejecting paths outside the
   project root. You are adding a second door, not widening the first. Add or keep a test
   proving the project endpoint is unchanged.

9. **FR-010** — after a successful write, refresh the affected registry so the new block or
   type is discoverable without a restart. A2 (#2021) built the entry point:

   ```python
   ApiRuntime.refresh_all_registries()   # types, then blocks, then previewers
   ```

   Call that rather than refreshing one registry, and rather than adding a fourth call
   site — FR-062 exists so callers name the *event*, not the registry set.

9a. **FR-065 cross-process refresh — SEQUENCED INTO YOUR SLICE.** Not optional, not
   deferred; the manager moved it here deliberately, recorded in checklist §7.3 and §9.

   A2 delivered the in-process half: `_RuntimeAdapter` exposes `block_registry` and
   `type_registry` as read-through properties, so a refresh in the API process is
   immediately visible to the in-process MCP agent. That is the desktop path.

   The half A2 could not land is the standalone `scistudio mcp-bridge`. It builds its
   registries once in `make_mcp_runtime` (`src/scistudio/ai/agent/mcp/runtime.py`) and has
   **no invalidation channel at all**. A2 could not add one: it needed changes in
   `ai/agent/mcp/**` (outside A2's write set) and there was no trigger for it until your
   write endpoint existed. Both are now true for you — `ai/agent/mcp/**` is in your write
   set, and FR-011's MCP promotion tool is the trigger.

   Deliver it. FR-065's own acceptance sentence is: *"A block promoted through the agent
   MUST become visible in the palette without a restart."* Test exactly that.

   If after investigation the standalone bridge genuinely cannot be invalidated without
   machinery beyond this spec's scope, **stop and report it as a blocker with your
   reasoning** — do not write a `TODO` and move on. The owner directive is complete
   delivery.

10. **FR-011** — the agent performs the same promotion through an MCP tool. Without it the
    agent cannot act on the promotion opportunities ADR-053 §3 expects it to offer. Follow
    the existing MCP tool patterns in `src/scistudio/ai/agent/mcp/`; do not invent a new
    registration mechanism.

11. **FR-019 support** — promotion is offered only when the resolved origin is `project`.
    The frontend (B5) enforces the visibility rule, but your API must make that decision
    possible: a user-library block is also tier-1 with a resolvable `file_path`, so the
    origin field is what distinguishes it. Make sure a promoted block resolves to `user`
    afterwards.

12. **Tests** — `tests/api/test_block_origin_tiers.py`: a block resolved from each
    directory returns its distinct origin, and an unresolvable path falls back to `custom`.
    `tests/api/test_user_library_write.py`: writes land in the user library; traversal and
    symlink escapes 403; an existing file is reported rather than overwritten; the project
    endpoint still 403s on escaping paths; a written block is discoverable without restart.
    Plus a test that the MCP tool promotes a block and the result is discoverable.

13. Update `CHANGELOG.md` with one entry.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/api/test_block_origin_tiers.py tests/api/test_user_library_write.py -q`
- `PYTHONPATH=./src python -m pytest tests/api tests/ai -q`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base feat/1995-adr-053-personal-tool-library --head HEAD`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1995"`
- Do NOT run `scripts/scistudio_pr_create.py`; you are not opening a PR.

No wrapper, hook, gate-record, CI, or AI-runtime governance behavior changes, so
`docs/ai-developer/**` needs no update; record that N/A rationale. Record `CHANGELOG.md`
as the docs update. Note that adding an MCP tool is a product change, not a governance
change.

## Output Required

- Changed file paths.
- The shared origin resolver's module path and exact signature — the manager freezes it
  and hands it to B2, who must consume it rather than writing a second path comparison.
- The user library write endpoint's method, path, request model, response model, and its
  overwrite/collision semantics — B5 codes the frontend against this.
- The existence-probe endpoint shape for FR-031.
- The MCP tool name and arguments.
- Whether FR-065 cross-process refresh landed here or was already done by A2.
- Tests/checks run and results.
- Checklist rows updated.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- A1's `core/dropins.py` does not expose the user-library roots you need.
- FR-007's inverse path constraint cannot be made safe on Windows within your write set.
- The MCP tool registration requires touching files the spec 2 track owns.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
