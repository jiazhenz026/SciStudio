---
title: "ADR-054 Assembly Dispatch — S5-B4 Skills, Provisioning, Examples, Catalogs"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S5-B4 — The Skills, The Provisioning Counts, The Examples, And The Catalogs

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 5's teaching and arithmetic half — the
  panel skill, the packaged-notebook shape in the block skill, the base
  skill's routing and focus rule, the provisioning counts, the examples
  corpus, and every catalog and count assertion the two new tool groups move.
- Task kind: feature
- Persona: implementer
- Issue: #2254
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2254
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec5-agent-enablement
- Agent branch: feat/2254-skills-and-counts
- Agent worktree: .worktrees/s5-b4
- Gate record: .workflow/records/2254-feat-2254-skills-and-counts.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/specs/adr-054-agent-enablement.md` — your spec. You implement
  **T-005, T-007, T-008 and T-009** of its §4.3, covering FR-006 to FR-009 and
  FR-025 to FR-027.
- ADR-054 §8.2 — the layering: a skill stays **short**, carries **no inline
  code**, and points at the reference documents and the example-listing tools.
  A skill that inlines a code sample is the thing this layering exists to stop.
- ADR-033 and ADR-040 for the provisioning mechanism, which is unchanged.

## Scope

You own only:

- `src/scistudio/_skills/scistudio/scistudio-write-panel/**` — new.
- `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md`.
- `src/scistudio/_skills/scistudio/SKILL.md` — the base skill.
- `src/scistudio/agent_provisioning/_orchestrate.py`, `skills.py`,
  `templates/claude_agents_md.md`.
- `src/scistudio/ai/agent/mcp/tools_authoring.py` — example listing gains the
  panel and the packaged notebook.
- The examples corpus — one panel and one packaged notebook. Find where the
  corpus lives before writing; do not invent a second location.
- `src/scistudio/_agent_reference/public-api.md` and `data-types.md`.
- `docs/specs/embedded-coding-agent-spec.md` — the tool catalog only.
- `tests/ai/test_mcp_fastmcp.py`, `tests/ai/test_mcp_server_skeleton.py`,
  `tests/ai/test_finish_ai_block_skeleton.py` — count assertions.
- `tests/agent_provisioning/test_skills.py` — the written-file count.
- One new test that reads each catalog and asserts every registered tool name
  appears in it.

You must not touch:

- `src/scistudio/_agent_reference/panel-contract.md` and the panel section of
  `block-contract.md` — S5-B2.
- `src/scistudio/ai/agent/mcp/tools_panels/**` — S5-B2.
- `src/scistudio/ai/agent/mcp/tools_explore/**` — S5-B3.
- `src/scistudio/ai/agent/mcp/server.py` — S5-B2 and S5-B3 register their own
  groups there.
- The workspace-focus files — S5-B1.
- Every `frontend/**` path.
- `docs/architecture/**` — **its tool table is a guarded path** and lands in
  spec 6's batch (#2236). Your catalog test must **exclude** the architecture
  document until then, and must say in a comment why, citing #2236.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

Everything in the shared preamble. In addition: **your counts depend on the
other three agents' tool names.** Spec 5 adds eleven tools across two groups:
four panel tools (S5-B2) and seven session tools (S5-B3). Land the skills, the
examples and the reference updates first; take the exact registered tool names
from S5-B2's and S5-B3's reports before writing the count assertions and the
catalogs. If those reports have not arrived when you reach T-009, say so and
stop rather than guessing a name.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S5-B4`.

## Work To Do

1. **T-005 — the panel skill and the provisioning counts.**
   `scistudio-write-panel` follows the flow: decide the capability, choose the
   tier, write the document, check it in the harness, register it (FR-006). It
   is short, carries no inline code, and points at `panel-contract.md` and the
   panel examples.
   The provisioning side counts skills in four places and all four move by
   one: the orchestration list, the skills index, the template's prose count,
   and the provisioning test that counts written files (FR-009). Find all four
   — a count that moves in three places and not the fourth is the failure mode
   this requirement exists for.
2. **T-007 — the block skill and the base skill.**
   `scistudio-write-block` presents the packaged-notebook shape beside the
   shapes it presents today, states that it is chosen **when the computation is
   not yet understood**, and routes to `scistudio-write-panel` when what the
   person wants is a window (FR-007).
   The base skill routes to the panel skill and tells the agent to confirm the
   workspace focus before acting on a request that could be a cell or a
   workflow edit (FR-008). Note in the skill that this rule is advice and the
   tools' refusal is the guarantee — a workflow edit while a session is
   focused is **not** refused, because the person may want it, so the skill
   tells the agent to ask.
3. **T-008 — the examples.**
   The corpus gains a panel and a packaged notebook, reachable through the
   existing example-listing tools (FR-027). The panel examples must include at
   least one **displaying** and one **producing** panel (FR-017's corpus half).
   These are worked patterns, so they carry the code the skills do not.
4. **T-009 — the counts and the catalogs.**
   Update the tool-count assertions for the eleven added tools and gain the
   two new per-group assertions (FR-025). Update the catalogs that list tools:
   the base skill and `docs/specs/embedded-coding-agent-spec.md` (FR-026).
   Update `public-api.md` with the three notebook helpers at the top-level
   package and the explore subsystem's public symbols, and `data-types.md`
   with the statement that a notebook holds native objects and how the helpers
   convert at the boundary (FR-012).
   Add the test that reads each catalog and asserts every registered tool name
   appears — excluding the architecture document, per §Scope.

## Required Tests And Checks

- `tests/agent_provisioning/test_skills.py` — the written-file count moved;
  provisioning writes the seventh task skill.
- The existing skill tests extended to the added skill.
- The moved count assertions in the three MCP test files, including the two
  new per-group counts.
- The new catalog test: every registered tool name appears in each catalog,
  architecture document excluded with a comment citing #2236.
- A test that the example-listing tools return the added panel and packaged
  notebook.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec5-agent-enablement --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, then `python scripts/scistudio_pr_create.py`, then
  post-PR `finalize`. Base your PR on `track/adr-054-spec5-agent-enablement`.
- Docs: `--docs-updated` for the reference and spec-catalog paths you change;
  `--docs-na "user-docs:the human documentation revision is ADR-054 spec 6,
  issue #2236"` for the human guides.

## Output Required

Per the shared preamble. Additionally: state the four places the skill count
moved and their new value, so the manager can verify none was missed.

## Stop Conditions

Per the shared preamble. Additionally: stop if you reach T-009 without S5-B2's
and S5-B3's registered tool names.
```
