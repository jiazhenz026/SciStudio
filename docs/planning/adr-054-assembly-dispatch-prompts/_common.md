---
title: "ADR-054 Assembly Dispatch — Shared Preamble"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Assembly Dispatch — Shared Preamble

Every work prompt in this directory includes this preamble by reference. It
is not a policy source; it collects the parts of the dispatch that are the
same for every agent so each prompt can state only what is its own.

## Required Rules

Read and follow, in this order:

- The GitHub issue named in your prompt, and every owner instruction in it.
- `AGENTS.md`
- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/agent-dispatch.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/personas/<your persona>.md`
- `docs/ai-developer/specific_rules/new-feature.md` for implementer rows;
  `docs/ai-developer/specific_rules/test-engineering.md` for test_engineer rows.
- `docs/adr/ADR-054.md` and the spec named in your prompt.

## Coordination

- You are not alone in this codebase. Several agents are running in parallel
  on sibling branches off the same base.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Run everything with `PYTHONPATH=./src`.
- Do not revert or overwrite another agent's work.
- Do not broaden scope. If you need a path outside your write set, stop and
  report back to the manager rather than editing it.
- MUST target your PR to `track/adr-054-spec4-explore-frontend` or
  `track/adr-054-spec5-agent-enablement` as your prompt says. **Never** target
  `main`.
- MUST NOT merge any PR.
- Edit only your own rows in
  `docs/planning/adr-054-assembly-checklist.md`.
- Record every completed row with a PR, commit, test command, report path, or
  gate-record entry. A chat message is not evidence.

## The Base You Are Building On

Your base branch already contains ADR-054 specs 1, 2 and 3:

- **Spec 1** — the unified panel contract. `src/scistudio/core/panels.py`
  carries the manifest, the capability declaration and `PANEL_API_VERSION`;
  `src/scistudio/panels/**` is the subsystem (renamed from `previewers/`);
  `src/scistudio/api/routes/panels.py` routes descriptors and assets.
- **Spec 2** — the notebook dependency analysis.
  `src/scistudio/explore/dependency_analysis.py` and `fingerprint.py`. These
  two modules are held to an import allowlist asserted by
  `tests/architecture/test_layer_deps.py`; do not import into them.
- **Spec 3** — the Explore Session runtime. `src/scistudio/explore/session.py`,
  `notebook.py`, `notebook_api.py`, `queue.py`, `packaging.py`, `lineage.py`,
  and the API surface at `src/scistudio/api/routes/explore.py`.

Read the code that already exists before writing anything. Prefer the
contracts, helpers and patterns it establishes over new local inventions.
Where the spec and the landed code disagree, the landed code is the fact and
the disagreement is a finding to report, not something to quietly paper over.

## TODO And Deferral Rule

Deferred work must be visible in the repository. Use:

```python
# TODO(#NNN): <what is deferred and why>
#   Out of scope per <ADR/spec/PR/owner decision>.
#   Followup: <issue URL or tracking reference>.
```

**Do not open a GitHub issue.** The owner has forbidden new issues beyond the
two implementation issues (`#2253`, `#2254`). Append every follow-up, edge
case, cleanup and deferral you find to
`docs/planning/adr-054-assembly-followups.md` under a heading with your agent
label, and cite that file's entry from the `TODO`. Untracked "later", "MVP" or
"V1" deferrals are a gate failure.

## Gate Workflow

Your branch is stacked on a track branch, not on `main`. **You must record the
base**, or `check` and `finalize` will measure your branch against `origin/main`
and read the whole of specs 1 to 3 as work you authored:

```bash
export PYTHONPATH=./src
python -m scistudio.qa.governance.gate_record init \
  --task-kind feature --persona <persona> --runtime claude-code \
  --branch <your branch> --issue <your issue> \
  --base-ref <your track branch> \
  --owner-directive "<the one-sentence task from your prompt>" \
  --include "<each path in your write set>"
```

Then, in order: `plan`, implement, `amend` for any scope change, `check`,
pre-PR `finalize`, `scripts/scistudio_pr_create.py`, post-PR `finalize`.

```bash
python -m scistudio.qa.governance.gate_record check --mode pre-pr \
  --base <your track branch> --head HEAD \
  --pr-body-file .workflow/local/pr-body.md
```

`gate_record check` is the single local preflight. Do not run ruff, mypy,
pytest, the frontend checks or the full audit one by one and call that
evidence; `check` selects and runs them, and its ledger events are what
counts. Read the whole of an "Unsatisfied obligations" repair hint before
re-running: it is written to state the entire failure in one pass.

Commit trailers on every commit:

```text
Gate-Record: .workflow/records/<record>.json
Task-Kind: feature
Issue: #<your issue>
Assisted-by: claude-code:<model>
```

Run `git add -A` before every commit so the ledger lands with the code.

## Documentation

The human-facing documentation revision is ADR-054 spec 6, tracked by `#2236`,
and is **out of scope for every agent in this dispatch**. Record it as:

```bash
python -m scistudio.qa.governance.gate_record amend \
  --reason "human docs are spec 6's" \
  --docs-na "user-docs:the human documentation revision is ADR-054 spec 6, issue #2236"
```

Agent-facing reference documents under `src/scistudio/_agent_reference/**` are
a different thing and **are** in scope, for the S5-B2 agent only.

## Output Required

Before reporting done:

- Changed file paths.
- Tests and checks run, with their actual results. If something failed, say so
  and paste the output; do not report a suite as green that you did not watch
  go green.
- Checklist rows you updated.
- PR number and commit sha.
- Every follow-up you appended to the follow-up register.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need a file outside your write set.
- The task conflicts with `AGENTS.md`, the ADR, the spec, or the gate record.
- CI or local checks fail for reasons you cannot explain.
- Another agent's work blocks yours.
- You cannot add or update the required tests.
