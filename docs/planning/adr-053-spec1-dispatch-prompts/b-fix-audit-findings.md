[DISPATCH-TEMPLATE-V1: fix]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs, with no deferred scope. This slice fixes the findings the two Track B audits raised.
- Task kind: bugfix
- Persona: implementer
- Issues: #1996 (P2-2), #2024 (P2-1), plus any AUDIT-SEC findings
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Tracking branch (your merge target): feat/1995-adr-053-personal-tool-library
- Agent branch: fix/1996-track-b-audit-findings
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-bfix
- Gate record: create with `gate_record init --slug 1996-track-b-audit-findings`

Read both audit reports first and re-run their reproductions:

- `docs/audit/2026-08-07-adr-053-spec1-track-b.md` (with-context, on `audit/adr-053-spec1-track-b`)
- `docs/audit/2026-08-07-adr-053-spec1-write-path.md` (no-context adversarial, on `audit/adr-053-spec1-write-path`)

## Required Rules

- AGENTS.md · docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/{gated-workflow,agent-dispatch,bug-fix}.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §3 (FR-003), §4, §6 (FR-019, FR-025), §7.1

## Scope

You own the files each finding names, plus their tests, `CHANGELOG.md`, and
`docs/specs/adr-053-personal-tool-library.md`. You must not touch `docs/planning/**`
(the manager owns the checklist) or `docs/ai-developer/**`.

## P2-2 — the MCP promotion tool applies a second, narrower origin rule

**This is the FR-003 violation the requirement was written to prevent**, and it has already
produced divergence rather than merely risked it.

FR-003: *"Origin resolution MUST be a single shared implementation used by both the block and
the type surfaces, not two path comparisons that can diverge."*

E1, E2 and E5 hide promotion unless the resolved origin is `project`. E3 —
`promote_to_user_library` in `src/scistudio/ai/agent/mcp/tools_library.py:167` — instead
tests `source.parent == library_root`. A block whose origin resolves to the FR-002 `custom`
fallback is therefore **hidden by the three frontend entry points and accepted by the
agent**. The repository currently claims "refusal for refusal" in a module docstring, in
`CHANGELOG.md`, and in the manager checklist; that claim is false as written.

The root cause is layering, not carelessness. `resolve_origin` lives in
`scistudio.api._block_source`, and the import-linter contract **"AI must not depend on api"**
forbids `scistudio.ai` from importing it, so a second rule was the only thing available.

**Fix the layering, not the symptom.** Move the shared origin resolver — `resolve_origin`,
`OriginSurface`, `BLOCK_SURFACE`, `TYPE_SURFACE` — into a layer both `api` and `ai` can
import. `src/scistudio/core/dropins.py` already sets the precedent: it lives in
`scistudio.core` precisely because consumers span layers, and it holds the tier definitions
this resolver compares against. Put it beside that, or in a sibling `scistudio.core` module,
and keep `scistudio.api._block_source` re-exporting for its existing callers so the API-side
diff stays small.

Then make E3 consume it, so all four entry points share one rule. Requirements:

- Every import-linter contract must still pass. `scistudio.core` must not gain a dependency
  on `scistudio.blocks`, `scistudio.api`, or `scistudio.ai`.
- Add a test asserting **E3 and the frontend predicate agree across the whole origin
  vocabulary**, `custom` included. That parity test is the deliverable; the move is just how
  you get there.
- If the docstring / CHANGELOG "refusal for refusal" claim is still not literally true after
  your change, correct the claim rather than leaving it.

## P2-1 — the FR-066 dead-field guard cannot fail

`test_type_hierarchy_still_carries_its_dead_colour_field` uses the shared `client` fixture,
whose only registered types are the six core bases — none of which declares a colour. A
reintroduced `ui_ring_color=entry.ui_ring_color` at `src/scistudio/api/routes/blocks.py:446`
would still leave the field `None`, so **the test would pass anyway**. Its docstring claims
it guards the rejected second colour supply point; it does not.

Fix: register a type that **declares** `ui_color` / `ui_ring_color`, then assert
`TypeHierarchyEntry.ui_ring_color` is still `None` on the block schema response while the
types endpoint reports the declared value. Verify your new test **fails** if you temporarily
populate the field, and say so in your report. Correct the docstring.

## AUDIT-SEC findings

Fix every P1 and P2 in `docs/audit/2026-08-07-adr-053-spec1-write-path.md` at the severity
the report assigns. That audit ran without task context and attacked the write endpoints and
the `sys.path` widening directly, so treat its reproductions as authoritative and re-run
them before and after.

If it reports that a containment case could not be executed on this Windows host (symlink
creation is not permitted here), **do not mark that case verified**. Add the test so Linux CI
executes it, and say plainly in your report which cases you could not exercise locally.

## P3s — address, do not defer

Work through the P3s in both reports. The owner directive is complete delivery with no
deferred scope; if one genuinely cannot land, stop and report it as a blocker with reasoning
rather than writing a `TODO`.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests --no-cov -q`
- `cd frontend && npm run check:ci`
- The repository's import-linter command — all contracts must stay kept.
- `SCISTUDIO_GATE_BASE=feat/1995-adr-053-personal-tool-library python -m scistudio.qa.governance.gate_record check --mode pre-pr --admin-label admin-approved:core-change`

## Output Required

- Changed file paths.
- Where the shared origin resolver now lives, every consumer, and the import-linter result.
- The E3-versus-frontend parity test, and proof it covers `custom`.
- Proof the FR-066 guard now fails when the field is populated.
- Per AUDIT-SEC finding: the reproduction before and after.
- Which containment cases could not be executed on this host.
- Commit SHA and branch name.

## Stop Conditions

Stop and report back if:

- Moving the resolver cannot satisfy every import-linter contract.
- An AUDIT-SEC finding needs a change outside this spec's scope.
- Making E3 and the frontend agree would change a behaviour the spec requires.
