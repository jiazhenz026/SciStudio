# [DISPATCH-TEMPLATE-V1: audit] Phase D38-2.1 — ADR-038 code-scope audit (no-context)

> No-context audit agent for the ADR-038 implementation track.
> You have **no access** to the manager's plan, session, memory, the
> cascade checklist, or other dispatch prompts. Your inputs are ADR-038
> and the current state of `main`.

## Your task

Read ADR-038 (`docs/adr/ADR-038.md`) fully. Then scan the **entire SciEasy repository on `main`** to produce a definitive code-modification scope list. ADR-038 §5.1 and §5.2 contain the author's best estimate of the files to change. Your job is to **validate that list against reality** — find every code site that touches the concepts ADR-038 changes, and report which sites are already in the ADR's list vs. which are missing.

Specifically, scan for every callsite, definition, import, test, and string-literal reference of:

| Concept | What to grep for |
|---|---|
| Old metadata store | `MetadataStore`, `metadata_store`, `metadata.db`, `get_metadata_store`, `set_metadata_store` |
| Old lineage store | `LineageStore`, `LineageRecord`, `LineageRecorder`, `lineage.db`, `get_lineage_store` |
| Lineage write paths | `_persist_output_metadata`, `_persist_metadata`, anything calling MetadataStore.write |
| Event shape | `BLOCK_DONE` producers (`emit_block_done`, scheduler emits) and consumers (handlers); current event-data keys: `workflow_id`, `outputs` |
| Block version | `BlockSpec.version`, `block_version`, default `"unknown"` |
| Lineage IDs | `FrameworkMeta.lineage_id`, `framework.lineage_id` |
| Old paths | `<project>/metadata.db`, `<project>/checkpoints/`, `<project>/lineage/` |
| API surfaces | `api/deps.py::get_lineage_store`, `api/deps.py::get_metadata_store`, runs router (likely missing) |
| AI Block runtime ID | `run_id` inside `blocks/ai/` (will be renamed to `block_execution_id`) |
| Tests | every test that constructs `LineageStore` / `LineageRecord` / `MetadataStore` directly |
| Env snapshot | `EnvironmentSnapshot`, `key_packages`, `full_freeze` |
| Frontend | `BottomPanel.tsx` ALL_TABS, BottomTab discriminated union, `"lineage"` tab, `"jobs"` tab, lineageSlice (does not exist yet) |
| Worker envelope | `runners/local.py` lines that lift `environment` field (ADR-038 §5.2 says line 229) |
| Checkpoint path | `engine/checkpoint.py` write path; any reference to `checkpoints/` |

For each concept, walk the repository (Glob + Grep), produce a complete file × symbol × line-number table.

## Inputs you may use

- `docs/adr/ADR-038.md` — the authoritative spec
- The entire repository on `main` at HEAD (use `git log -1` to confirm you're auditing the right commit; you should see commit `167c5db` or later — the ADR-038 merge commit)

## Inputs you may NOT use

- ADR-039 (`docs/adr/ADR-039.md`) — your scope is ADR-038 only; the ADR-039 cascade has its own scope audit
- `docs/planning/` (cascade tracking — would expose session context)
- `docs/audit/` (prior audit reports — would bias you)
- `~/.claude/` (manager's plan / memory)
- Any sub-issue or umbrella issue threads on GitHub

## Output

Create `docs/audit/2026-05-15-adr-038-code-scope-audit.md` with this structure:

```markdown
# Code-scope audit — ADR-038 implementation
Date: 2026-05-15
Auditor: <no-context audit agent>
Repository state: `git log -1 --oneline` → <SHA + message>
ADR §5.2 file list reviewed against: <number of files actually scanned>

## Summary
<paragraph: how many files the ADR §5.2 lists, how many you found, how many are missing from the ADR.>

## Files that ARE in ADR §5.2 and ALSO touch the affected surfaces (confirmed in-scope)

| File | Symbols / lines | ADR §5.2 row |
|---|---|---|
| `src/scieasy/engine/scheduler.py` | line 425 (BLOCK_DONE emit), line 549 (BLOCK_DONE emit), `_run_block` body | §5.2 row "scheduler.py" |
| ... | ... | ... |

## Files MISSING from ADR §5.2 (newly discovered — manager must add to D38-2.2/2.3/2.4 owned-file lists)

| File | Symbols / lines | Concept (which D38 phase needs to touch this) |
|---|---|---|
| `<some/file.py>` | <line X: foo bar> | concept Y |
| ... | ... | ... |

## Files in ADR §5.2 that DO NOT actually appear to touch the surface (overestimated scope)

| File | ADR §5.2 row | Reason it's unnecessary |
|---|---|---|
| ... | ... | ... |

## Tests that construct lineage / metadata stores directly (need schema migration in D38-2.2)

| Test file | Test functions | Construction pattern |
|---|---|---|
| `tests/engine/test_lineage_recorder.py` | <list test functions> | `LineageStore(...)` direct construction |
| ... | ... | ... |

## Frontend touchpoints (D38-2.4b / 2.4c)

| File | Lines | What needs to change |
|---|---|---|

## Open questions for the manager

- <any spot where the ADR is ambiguous and you can't classify a callsite>
```

## Hard rules

1. **Do not write any code.** Output is exactly one new file. No file edits anywhere else.
2. **Use Grep + Glob, not Bash grep.** Faster, scope-safe.
3. **No CI runs, no test runs.** This is a static code scan.
4. **Cite line numbers**. Every entry in your tables must have a file + line number citation.
5. **Be exhaustive**. The ADR author wrote §5.2 from memory of the codebase — they may have missed callsites, especially in frontend, tests, and dynamically-imported modules. Find every one.
6. **You may NOT touch any source file**, including the ADR. Even adding a comment.

## How to submit

Commit the audit file on a branch `chore/audit-output-d38-2.1` off `track/adr-038/lineage-db` (the manager will have created this tracking branch by the time you run). PR body: `Closes <sub-issue #N>` (the manager will pass you the number). Title: `chore(audit): D38-2.1 code-scope audit for ADR-038`. PR target: `track/adr-038/lineage-db`.

After PR opens and CI runs, exit. The manager folds your findings into the D38-2.2 / 2.3 / 2.4 owned-file whitelists before dispatching implementation agents.
