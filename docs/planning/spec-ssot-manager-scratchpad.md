# Manager scratchpad — Interface SSOT cascade

> **Append-only.** Updated after every dispatch + every decision + every authority tiebreaker + every git pull + every blocker + every Codex override. Read on every session start (especially after context compression).
>
> Path: `docs/planning/spec-ssot-manager-scratchpad.md` on `track/spec-ssot` (committed to tracking branch, never main).

---

## Pinned facts (session-invariant)

- **Cascade**: Interface SSOT (single-source-of-truth spec doc)
- **Plan file**: `~/.claude/plans/single-source-of-truth-issue-issue-acce-wiggly-truffle.md`
- **Umbrella issue**: **#1090** — https://github.com/zjzcpj/SciEasy/issues/1090
- **Umbrella PR**: **#1091** (DRAFT, `[DO NOT MERGE]`) — https://github.com/zjzcpj/SciEasy/pull/1091
- **Tracking branch**: `track/spec-ssot` (off origin/main, will never merge directly to main; final clean PR is separate)
- **Manager worktree**: `C:\Users\jiazh\Desktop\workspace\scieasy-spec-ssot-mgr\` (worktree on track/spec-ssot)
- **Main checkout** (user's primary, do NOT perturb): `C:\Users\jiazh\Desktop\workspace\SciEasy\` (currently on `track/adr-040`, has 10+ in-flight ADR-040 sub-worktrees)
- **Baseline SHA (Phase 0.0)**: `a4b8b5f` — `feat(adr-040): production-environment agent reliability cascade (#1040)` — post-ADR-040 cascade merge
- **N (locked Phase 1)**: **13** (block-abc, port-system, data-types, storage-backends, collection-transport, block-registry, execution-engine, lineage-db, rest-api, ws-sse-protocol, mcp-tools, versioning-git, agent-provisioning)
- **SSOT file path (final output)**: `docs/specs/INTERFACE_SPEC.md`
- **Authority hierarchy**: ARCHITECTURE.md PRIMARY > ADR SUPPLEMENTARY > CLAUDE.md (conventions only). ARCHITECTURE wins on conflict. ADR↔ADR conflicts logged not reconciled.
- **N halving rule**: if N>8, Phase 1.5.A and Phase 4.1 use ceil(N/2) agents, each owning 2 structurally-similar modules.

---

## Recovery checklist (read this if you just woke up from context compression)

1. Read **Pinned facts** above
2. Read **Active dispatches** — are any still running? Check `git ls-remote origin '<branch-pattern>'` or `ls docs/audit/2026-05-17-spec-ssot-*` to see if artifacts landed
3. Read **Phase status** — which phase is current?
4. Read latest 5 entries in **Decisions log**
5. Re-read the latest agent report you were processing (path in Phase status)
6. Confirm scratchpad's "Recovery checklist" against current TaskList state
7. If still unclear: **ask user** — don't guess

---

## Phase status

| Phase | Status | Owner | Artifacts | Notes |
|---|---|---|---|---|
| 0.0 sync | ✅ done | manager | baseline SHA pinned | a4b8b5f — origin/main moved from 8ec38c4 |
| 0.1 worktree | ✅ done | manager | `../scieasy-spec-ssot-mgr/` | branch `track/spec-ssot` |
| 0.2 issues + branch + umbrella PR | ⏳ in flight | manager | issue #1090, checklist, scratchpad | umbrella PR pending first commit + push |
| 0.3 spec_audit.py | not started | manager | — | ~600 LOC; locks spec grammar |
| 1 enumerate | not started | S1-enumerate | — | locks N |
| 1.5 triangulate | not started | C1..Cn, D1, X1 | — | n+2 parallel, no shared context |
| 2 classify | not started | K1..K3 | — | triple independent |
| 2.5 consolidate | not started | M1, M2 | — | full interface list each |
| 3 merge | not started | manager | draft v1 | — |
| 4 audit | not started | A1..An, AX | — | per-module + cross-architecture |
| 5 fix | not started | manager | draft v2 | — |
| 6 write | not started | manager | INTERFACE_SPEC.md | 3-4h manager-write |
| 7 audit | not started | Z1, Z2 | — | post-write verification |
| 8 final + CI live | not started | manager | hook enabled, CLAUDE.md amended | — |
| 9 issue rollout | not started | manager | drift umbrella + per-b/c/d child issues + clean merge PR | — |

---

## Active dispatches

(Empty when no agent in flight. Each entry: agent role, dispatch time, expected output path, `until` watcher pattern, current status.)

(none — Phase 1 done; Phase 1.5 dispatch pending)

### Completed dispatches log
- **S1-enumerate** (id `a3f5139605d1e5520`) — Phase 1 module taxonomy. ✅ Completed. N = 13. Report copied to manager worktree at `docs/audit/2026-05-17-spec-ssot-p1-modules.md`. Worktree branch `worktree-agent-a3f5139605d1e5520` (not pushed).

---

## Decisions log (append-only)

> Format: `YYYY-MM-DD HH:MM — <topic>. Decision: <X>. Reason: <Y>. Source: <agent report / user quote>.`

- **2026-05-17 — Baseline SHA = `a4b8b5f`.** Reason: user chose post-ADR-040 baseline. Source: user clarification on AskUserQuestion "Baseline 选择". Implication: SSOT will include all ADR-040 surfaces (FastMCP, hooks, scaffold_block new signature, provisioning API).
- **2026-05-17 — SSOT file = `docs/specs/INTERFACE_SPEC.md` (single file).** Reason: easiest grep/diff. Source: user clarification on AskUserQuestion "Spec 文档位置". Implication: spec_audit.py extractor targets one file.
- **2026-05-17 — Frontend in scope.** Reason: `frontend/src/types/api.ts` is hand-mirror, real drift risk. Source: user clarification. Implication: one Phase-1 module = `frontend-be-boundary`; N likely 11–14.
- **2026-05-17 — Legacy `docs/specs/*` NOT in audit scope.** Reason: noise reduction. Source: user clarification. Implication: D1 / X1 only read ARCHITECTURE.md + ADR + CLAUDE.md.
- **2026-05-17 — Phase 6 SSOT author = manager (not agent).** Reason: cross-referencing risk too high for agent omission. Source: user clarification. Implication: ~3-4h manager-write task; agent prep work is consolidator drafts (M1/M2) + audit findings.
- **2026-05-17 — Doc authority hierarchy: ARCHITECTURE.md PRIMARY, ADR SUPPLEMENTARY.** Reason: "ADR太多，里面有噪声和矛盾点". Source: user verbatim. Implication: embedded in every Phase 1.5.B / 1.5.C / 2 / 2.5 / 4.2 / 7 prompt; manager enforces in Phase 3 / 5 / 6 / 8.
- **2026-05-17 — N>8 → halve agent count (1 agent / 2 modules).** Reason: token savings without quality drop. Source: user verbatim. Implication: With N≈11-14, Phase 1.5 = 6-7 code agents (not 11-14).
- **2026-05-17 — Today's session scope = full 10-phase cascade.** Reason: user verbatim "全流程走完". Source: user clarification on session scope. Implication: marathon session, manager scratchpad usage will be critical for survival.
- **2026-05-17 — N = 13 locked.** Source: S1-enumerate report `docs/audit/2026-05-17-spec-ssot-p1-modules.md`. Pairing accepted as recommended (C1..C7). Implication: Phase 1.5 dispatches 9 agents in parallel.
- **2026-05-17 — Phase 1.5 pre-flagged d-class candidates**: `versioning-git`, `agent-provisioning`, `pty_control` sub-surface, `workflow.yaml`/`project.yaml` Pydantic schemas, `metadata_store.py` legacy. These are HINTS for downstream agents, not pre-decisions — Phase 1.5 D1/X1 agents will independently surface them.

---

## TBDs (open questions)

- [ ] N value (locks at end of Phase 1)
- [ ] Phase 1.5 agent pairing (which 2 modules per code-view agent — manager curates after N locks)
- [ ] Spec grammar exact shape (manager locks during Phase 0.3 alongside `extract_spec.py`)
- [ ] ADR-041 surface impact on doc-audit scope (need to read it before Phase 1.5.B prompt)

---

## Authority-hierarchy tiebreakers

> Every ARCHITECTURE vs ADR conflict + every ADR vs ADR conflict encountered. Manager logs even if "resolved by hierarchy" — the log feeds the follow-up ADR-reconciliation cascade.

(none yet)

---

## Sync log

> Every `git pull` or rebase the manager performs on `track/spec-ssot`. Each entry: timestamp, old SHA, new SHA, commits pulled, impact on phase scope.

- **2026-05-17 — Phase 0.0 initial sync.** origin/main moved `8ec38c4 → a4b8b5f`. Commits pulled into local main (via fetch only — local checkout still on track/adr-040, did not perturb). Impact: ADR-040 cascade merged; baseline locked at `a4b8b5f`.

---

## Codex P1/P2 override log

> Per `feedback_audit_p1_override`: every Codex P1 the manager fixes in-PR despite auditor "defer" gets logged here.

(none yet)

---

## Notes & gotchas

- **Editable-install pollution**: `import scieasy` from any shell resolves to `C:\Users\jiazh\Desktop\workspace\SciEasy\src\scieasy\__init__.py` (the main checkout). When running `scripts/spec_audit.py` from the spec-ssot worktree, the introspected code is from MAIN checkout, NOT this worktree. Tolerable since main currently has post-ADR-040 code (track/adr-040 merged main back in). If main and spec-ssot diverge later, will need `PYTHONPATH=src` override or pip install in the spec-ssot worktree (forbidden per hygiene rules).
- **Concurrent worktrees**: 10+ ADR-040 worktrees still locked but stale (cascade merged). Will prune in Phase 9 cleanup. Main checkout is currently on `track/adr-040` — do NOT switch branches there during this cascade.
- **#1072 open PR** (A1 audit for ADR-040, targets `track/adr-040`) — ignore, will be closed when track/adr-040 is deleted.
- **#821 open PR** (`docs(#819): spec for scieasy-blocks-metadata plugin package`) — touches plugin metadata spec, may be relevant. Decision: if it merges before Phase 1.5, fold into scope; if after, ignore (out of scope per "no packages/" rule, since it's a plugin spec).
