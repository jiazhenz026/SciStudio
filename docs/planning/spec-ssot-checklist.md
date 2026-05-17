# Interface SSOT Cascade Checklist

> **Mandatory tracking doc.** Every agent edits the rows it owns and only those rows.
> Drift = protocol violation. The dispatcher (Claude as agent manager) sweeps after every phase.
> Plan file: `~/.claude/plans/single-source-of-truth-issue-issue-acce-wiggly-truffle.md`
> Session start: 2026-05-17.
> Umbrella issue: **#1090**.
> Baseline SHA: `a4b8b5f` (post-ADR-040 merge).

## Conventions
- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- "Owner" is the agent role (`S1-enumerate`, `C1..Cn`, `D1`, `X1`, `K1..K3`, `M1..M2`, `A1..An`, `AX`, `Z1..Z2`) or `manager`
- Each tick appends a one-line note: `→ <PR/commit/test-link>` or `→ <report-file-path>`
- Out-of-scope file lists per agent are encoded in dispatch prompts; agents must TODO-tag per CLAUDE.md §7.6

## Manager discipline (non-negotiable for this cascade)

1. Every `Agent` dispatch: `isolation: "worktree"`, `model: sonnet` (audit) / `opus` (consolidate/write), `subagent_type: general-purpose`, `run_in_background: true`.
2. **MANDATORY**: after every dispatch, immediate foreground `until` loop polling for the next artifact (branch on origin, PR open, report file present). Never reply "Waiting" and let stop-hook fire.
3. **Cross-agent context isolation** unique to this cascade: Phase 1.5 agents MUST NOT see each other's outputs. Forbidden paths listed verbatim in each dispatch prompt.
4. Worktree isolation forbids `pip install -e .` from within the worktree.
5. Every `pytest --timeout=60`. No `npm run dev` background.
6. Every agent PR body contains `Closes #N` (umbrella or sub-issue).
7. CI must be green before report-done.
8. Wait for `<task-notification status="completed">` before merging — Codex auto-review fires after first CI run; cap reconcile at 1 round.
9. Audit reports land at `docs/audit/2026-05-17-spec-ssot-<phase>-<agent>.md` on `chore/audit-report-N` branches (per audit-agent.md §8).
10. **N halving rule**: if N>8, Phase 1.5.A and Phase 4.1 use ceil(N/2) agents, each owning 2 modules. Manager pairs structurally similar modules together.
11. **Doc authority hierarchy**: ARCHITECTURE.md PRIMARY, ADRs SUPPLEMENTARY, ARCHITECTURE wins on conflict. Embedded in every dispatch prompt.
12. **Manager scratchpad** at `docs/planning/spec-ssot-manager-scratchpad.md` is updated after every dispatch + every decision + every authority tiebreaker. Read on every session start.
13. Dispatch prompts compose `templates/00-common-boilerplate.md` + `templates/<role>-agent.md` verbatim; marker `[DISPATCH-TEMPLATE-V1: <role>]`.
14. Out-of-scope TODOs use `# TODO(#NNN): … Out of scope per INTERFACE_SPEC.md §X.` form (CLAUDE.md §7.6).

## Classification taxonomy (used in every phase, verbatim in every prompt)

| Label | Definition | SSOT action |
|---|---|---|
| **a — Aligned** | Interface exists in code AND docs (ARCHITECTURE.md primary), identical signature/defaults/return/side-effects | Lift verbatim. No issue. |
| **b — Both, disagree** | Exists in code AND docs but disagree on something concrete (param, type, default, return) | Pick the better one. Open fix issue against losing side. |
| **c — Code missing** | Docs say it; code doesn't implement it | One of: c-impl (require impl), c-drop (remove from spec), c-defer (mark deferred). Open code-fix or doc-fix issue. |
| **d — Docs missing** | Code implements it; no doc describes it | One of: d-document (add to docs), d-private (mark `_underscore`), d-remove (delete unused). Open code-fix or doc-fix issue. |

Decision tree (for agents):
```
code-has?  docs-has?  →  label
  Y         Y         →  a (if equal) or b (if different)
  Y         N         →  d
  N         Y         →  c
  N         N         →  NOT A CONTRACT — skip
```

---

## Phase 0 — Preflight (Owner: manager)

### 0.0 Remote sync + baseline
- [x] `git fetch origin --prune` → origin/main advanced `8ec38c4 → a4b8b5f`
- [x] CI on main green (last 5 runs)
- [x] Baseline SHA pinned in scratchpad: **`a4b8b5f`** (post-ADR-040 cascade merge)
- [x] In-flight PR survey: #1072 (A1 audit, low impact), #821 (metadata spec — relevant), #691/#686 (dependabot, irrelevant)
- [x] ADR-041 noted as new (CodeBlock v2 + ARCHITECTURE §4.7) — added to doc-audit scope

### 0.1 Manager worktree
- [x] Worktree at `C:\Users\jiazh\Desktop\workspace\scieasy-spec-ssot-mgr\` (off origin/main, branch `track/spec-ssot`)
- [x] HEAD verified: `a4b8b5f`
- [ ] Note: `import scieasy` resolves to MAIN checkout (editable-install pollution); tolerable since main is currently merged with track/adr-040 (post-ADR-040 code) — scratchpad notes this

### 0.2 Issues + branch + umbrella PR
- [x] Umbrella issue: **#1090** — "Interface SSOT cascade — INTERFACE_SPEC.md"
- [x] Tracking branch `track/spec-ssot` created off origin/main
- [x] Branch pushed to origin (commit `e11b0a3`)
- [x] Umbrella PR `[DO NOT MERGE]` opened: **#1091** — https://github.com/zjzcpj/SciEasy/pull/1091
- [x] Checklist: `docs/planning/spec-ssot-checklist.md` (this file)
- [x] Scratchpad: `docs/planning/spec-ssot-manager-scratchpad.md` with Pinned facts

### 0.3 scripts/spec_audit.py implementation
- [x] `scripts/spec_audit/extract_code.py` — AST (ABC/Protocol/Pydantic) + FastAPI OpenAPI + Typer + entry-points. **TODO(#1090)**: MCP tool + WS message extractors deferred (need running-server / deeper AST inference) — manual entry into SSOT for V1
- [x] `scripts/spec_audit/extract_spec.py` — markdown grammar parser with strict validation (Status/Source/Primary-doc-source/Issue required-iff-bcd)
- [x] `scripts/spec_audit/extract_docs.py` — fence + backtick mention extraction across ARCHITECTURE.md + ADR + CLAUDE.md
- [x] `scripts/spec_audit/diff.py` — 4-way join + 6 finding categories + 3 exit codes (0/1/2)
- [x] `scripts/spec_audit.py` — orchestrator (chains 3 extractors + diff; `--baseline` mode skips spec parse)
- [x] `scripts/hooks/check-spec-drift.sh` — pre-push + CI wrapper with `SCIEASY_SKIP_SPEC_AUDIT=1` escape
- [x] Smoke fixture at `tests/spec_audit/test_extract_spec.py` — 6 tests, all green; validates grammar invariants
- [ ] Deferred: `pyproject.toml` dev deps (griffe NOT needed — extract_code uses stdlib `ast`; markdown-it-py NOT needed — extract_spec uses regex)
- [x] `.github/workflows/ci.yml` step added with `if: false` guard (enabled in Phase 8)
- [x] **End-to-end smoke against real repo**: extract_code → 224 records (87 pydantic + 60 fastapi_route + 31 protocol + 20 abc + 17 entry_point + 9 typer_command); extract_docs → 4341 mentions across 100 interfaces; diff → 223 code-not-in-spec errors as expected (only 1 test entry in synthetic spec)
- [ ] CLAUDE.md draft amendment ready (committed in Phase 8 only)

---

## Phase 1 — Module enumeration (Owner: S1-enumerate)
- [x] Agent dispatched (general-purpose, sonnet, agent id `a3f5139605d1e5520`)
- [x] Output: `docs/audit/2026-05-17-spec-ssot-p1-modules.md` (18KB)
- [x] **N locked = 13**
- [x] Halving rule triggered (N>8): Phase 1.5 = **7 code agents** + 1 docs + 1 xcheck = **9 agents**
- [x] Module list (13): `block-abc`, `port-system`, `data-types`, `storage-backends`, `collection-transport`, `block-registry`, `execution-engine`, `lineage-db`, `rest-api`, `ws-sse-protocol`, `mcp-tools`, `versioning-git`, `agent-provisioning`
- [x] Pairing (agent recommendation, manager-approved):
  - C1: block-abc + port-system (blocks/base/)
  - C2: data-types + storage-backends (core/)
  - C3: collection-transport + block-registry (horizontal)
  - C4: execution-engine (solo, largest)
  - C5: lineage-db + versioning-git (history/persistence)
  - C6: rest-api + ws-sse-protocol (api/ layer)
  - C7: mcp-tools + agent-provisioning (agent surfaces)
- [x] d-class candidates pre-flagged: `versioning-git`, `agent-provisioning` (partial), `pty_control` (sub-surface)
- [x] Orphan reference flagged: `src/scieasy/workflow/` raises NotImplementedError

---

## Phase 1.5 — Triangulation (Owners: C1..Cn, D1, X1)
> All agents dispatched in **one message** for true parallelism. Forbidden paths embedded verbatim in each prompt.

### Per agent
- [x] C1 (id `ac3eaa6035bae9f77`): block-abc + port-system → `…-code-C1.md` (59KB, 41 ifaces)
- [x] C2 (id `a3a9fb2e86595d933`): data-types + storage-backends → `…-code-C2.md` (41KB, 27 ifaces)
- [x] C3 (id `aa7002049c9a4a4d6`): collection-transport + block-registry → `…-code-C3.md` (37KB)
- [x] C4 (id `a7c0e6b7654798b80`): execution-engine solo → `…-code-C4.md` (53KB, 47 ifaces, 10 d-hints)
- [x] C5 (id `a6af2868940d7df93`): lineage-db + versioning-git → `…-code-C5.md` (38KB) — versioning-git d-class **CONFIRMED**
- [x] C6 (id `a9d84886e9dcc97cb`): rest-api + ws-sse-protocol → `…-code-C6.md` (64KB, 42 routes + 13 WS) — `src/scieasy/workflow/` is LIVE (S1 orphan flag wrong)
- [x] C7 (id `a72a89f64dc2fd574`): mcp-tools + agent-provisioning → `…-code-C7.md` (66KB, 26 tools) — `list_block_runs` ghost in static catalog
- [x] D1 (id `abf625b1c09b8bd9a`): all 13 modules → `…-docs.md` (102KB) — 5 ADR conflicts logged
- [x] X1 (id `a704b0f099b05e7e2`): inconsistencies → `…-xcheck.md` (27KB) — 15 ARCH↔code + 2 ADR↔code + 3 ARCH↔ADR

### Manager post-phase
- [x] All 9 reports copied into spec-ssot worktree, main checkout cleaned (agents wrote outside worktree — TODO: review agent prompt for path discipline next cascade)
- [ ] Populate "Interface rows" section (below) — done implicitly via Phase 2/2.5 consolidation

---

## Phase 2 — Triple classification (Owners: K1, K2, K3)
- [x] K1 (id `a8b34ef7924fd14fc`) — 121 ifaces: a=52, b=12, c=2, d=55
- [x] K2 (id `ac5390f3efdef6163`) — ~152 ifaces (217 rows): b=22, c=2, d=47
- [x] K3 (id `af6dab94d72e8d308`) — 143 ifaces: a=73, b=18, c=2, d=50
- [x] Agreement pattern: ~40-50% a, ~10-15% b, 1-2% c, ~35-45% d across all 3. Top b-cluster = execution-engine (scheduler/runner sig drift). Top d-cluster = versioning-git (entirely d-class confirmed by all 3).
- [x] Count variance K1=121 vs K2=152 vs K3=143 — de-duplication granularity differences. M1/M2 consolidators must reconcile.

---

## Phase 2.5 — Consolidation (Owners: M1, M2)
- [ ] M1 draft landed
- [ ] M2 draft landed
- [ ] Manager populates `P2.5 M1/M2` column

---

## Phase 3 — Manager merge
- [ ] `docs/planning/spec-ssot-draft-v1.md` committed on tracking branch
- [ ] Manager populates `P3 draft line` column

---

## Phase 4 — Pre-write audit (Owners: A1..An, AX)
### Per-module audit
- [ ] A1: modules `<TBD>`, `<TBD>` → `docs/audit/2026-05-17-spec-ssot-p4-A1.md`
- [ ] A2..An: ...
### Cross-doc audit
- [ ] AX: → `docs/audit/2026-05-17-spec-ssot-p4-AX.md`

---

## Phase 5 — Manager fix
- [ ] `docs/planning/spec-ssot-draft-v2.md` committed
- [ ] Finding disposition log (per-finding accept/reject/escalate)

---

## Phase 6 — Manager writes SSOT
- [ ] `docs/specs/INTERFACE_SPEC.md` drafted
- [ ] Grammar locked, `extract_spec.py` parses cleanly
- [ ] All N modules covered
- [ ] Every entry has Status + Source + Primary-doc-source + (if b/c/d) `Issue: #TBD-<short>`
- [ ] `scripts/spec_audit.py diff.py` runs against current main + new spec; no UNEXPECTED diffs

---

## Phase 7 — Post-write audit (Owners: Z1, Z2)
- [ ] Z1 report landed
- [ ] Z2 report landed

---

## Phase 8 — Manager final fix + flip CI live
- [ ] INTERFACE_SPEC.md ACCEPTED banner
- [ ] CI hook live (no `if: false`)
- [ ] CLAUDE.md amendment merged
- [ ] CHANGELOG cascade summary entry

---

## Phase 9 — Drift issue rollout + final merge
- [ ] Drift umbrella issue **#K** opened
- [ ] One child issue per b/c/d entry; INTERFACE_SPEC.md `#TBD-<short>` placeholders replaced with real numbers
- [ ] Clean PR `spec-ssot → main` opened, CI green, user sign-off
- [ ] Squash-merge into main
- [ ] Umbrella `[DO NOT MERGE]` PR closed without merge
- [ ] `track/spec-ssot` deleted from origin
- [ ] Worktree pruned
- [ ] Umbrella issue #1090 closed

---

## Interface rows (populated in Phase 1.5)

| ID | Module | Interface | code-says | docs-says | xcheck | P2 K1/K2/K3 | P2.5 M1/M2 | P3 draft | P4 audit | P5 fix | P6 spec | P7 flag | P9 issue |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (rows added by manager after Phase 1.5) | | | | | | | | | | | | | |

---

## Drift log (append-only)
> Format: `YYYY-MM-DD HH:MM — <owner> <action>. Reason: <quote>. Resolution: <fix-link>`

(empty until first violation)

---

## Out-of-scope from this cascade (TODO-tag references)

Per CLAUDE.md §7.6, every deferred item must have an in-repo TODO pointing here.

- `packages/scieasy-blocks-*/` — plugin consumers, not contract definers. Plugins MUST conform to SSOT, not influence it. Follow-up cascade for plugin contract spec if needed.
- `docs/specs/phase11-*` — legacy per-block specs. Will be reconciled in follow-up cascade.
- `docs/block-development/*` — derived/expository docs. Will be reconciled in follow-up cascade.
- ADR↔ADR contradictions encountered during Phase 1.5/2/2.5/4.2 — logged in audit reports, **not** reconciled in this cascade. Follow-up cascade.
- Per-interface telemetry / OpenAPI auto-gen / FE codegen — future enhancement.
