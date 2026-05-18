---
title: "Phase 1H Sub-PR 3 implementation record — 11 skills + committer.py + fact extractors"
phase: 1
sub_phase: "1H"
sub_pr: 3
tcs:
  - "1H.5"
  - "1H.6"
  - "1H.7"
  - "1H.8"
issue: 1155
parent_issue: 1139
umbrella: 1113
branch: feat/issue-1155/1h-sub-pr-3-skills-committer-extractors
session: 20260518-065109-feat-1155-adr-042-phase-1h-sub-pr-3-11-s
adrs:
  - ADR-042
  - ADR-044
date: 2026-05-18
agent_editable: true
---

# Phase 1H Sub-PR 3 implementation record

## Scope

Ships TC-1H.5 through TC-1H.8 from the ADR-042/043/044 Phase 1H slice
(re-dispatched per #1155 after sub-PR 1 (#1145/#1150) merged into
`track/adr-042/1h-workflow-v2`).

- **TC-1H.5**: 5 per-namespace fact extractors + orchestrator + initial
  `docs/facts/generated.yaml` snapshot (ADR-042 §7.5.3).
- **TC-1H.6**: `scripts/committer.py` hard-tooling wrapper (ADR-042 §16).
- **TC-1H.7**: 11 required-skill pointer files + `docs/skills/required.yaml`
  manifest (ADR-042 §17.1-3 + ADR-044 §11).
- **TC-1H.8**: cross-runtime installer (`scieasy.agent_provisioning.qa_skills`)
  for Claude — other runtimes deferred to sub-PR 2 (ADR-042 §17.3).

Sub-PR 2 (AGENTS.md hierarchy migration) is intentionally NOT in scope.

## Files added

| File | LOC | Purpose |
|------|-----|---------|
| `scripts/committer.py` | 360 | ADR-042 §16 hard-tooling wrapper (`add`/`commit` subcommands) |
| `scripts/audit/extract_workflow_facts.py` | 105 | TC-1H.5 workflow namespace |
| `scripts/audit/extract_tool_facts.py` | 130 | TC-1H.5 tool namespace |
| `scripts/audit/extract_adr_facts.py` | 110 | TC-1H.5 adr namespace |
| `scripts/audit/extract_maintainers_facts.py` | 100 | TC-1H.5 maintainers namespace |
| `scripts/audit/extract_skill_facts.py` | 110 | TC-1H.5 skill namespace |
| `scripts/audit/generate_facts.py` | 180 | TC-1H.5 orchestrator → `docs/facts/generated.yaml` |
| `docs/facts/generated.yaml` | (generated) | initial snapshot of FactsRegistry |
| `docs/skills/required.yaml` | 95 | ADR-042 §17.3 manifest |
| `src/scieasy/_skills/qa/<11 names>/SKILL.md` | 17 each | source-of-truth pointer bodies (≤30 body lines) |
| `.claude/skills/<11 names>/SKILL.md` | 17 each | installed copies for this repo's self-use |
| `src/scieasy/agent_provisioning/qa_skills.py` | 175 | ADR-042 §17.3 cross-runtime installer (Claude-only v1) |
| `tests/qa/test_committer.py` | 290 | 41 tests; 97% coverage on committer.py |
| `tests/qa/test_facts_extraction.py` | 360 | 32 tests; 90-98% per-extractor coverage |
| `tests/qa/test_skill_manifest.py` | 130 | 56 tests (param × 11 skill names) on pointer-pattern shape |
| `tests/qa/test_qa_skills_installer.py` | 145 | 13 tests on installer |

## Implementation rationale

1. **`committer.py` is intentionally a stdlib-only wrapper**. No pydantic
   dependency. The wrapper is invoked from any agent runtime — Python
   3.11+ stdlib + `pyyaml` is the smallest dependency surface that
   satisfies §16 + §16.5. The wrapper reads `IdentityRegistry` data
   indirectly via raw YAML (not via the 1A-b `scieasy.qa.schemas.identity`
   pydantic model) because the script must be invocable from `python
   scripts/committer.py` in a clean checkout BEFORE `scieasy` is
   installed.

2. **Fact extractors are also stdlib + pyyaml + pydantic**. Each
   extractor:

   - reads ONE source file (or a directory in the ADR case),
   - returns ONE `*Facts` pydantic instance,
   - exposes a `main(argv)` CLI that dumps JSON.

   The orchestrator (`generate_facts.py`) calls every extractor in turn,
   stitches the `FactsRegistry`, and writes `docs/facts/generated.yaml`
   via `yaml.safe_dump`. `model_dump(mode="json")` is used so the
   `datetime` serialises to ISO-8601 and the `Literal[1]` schema_version
   round-trips as a bare integer.

3. **Source-SHA tracking is in-process, no Git binary required**. The
   git-blob-SHA helper computes `SHA-1("blob {len}\0" + data)` directly
   so the orchestrator stays usable in environments without `git` on
   PATH (e.g. minimal CI agents that only have `python`).

4. **Skills use the ADR-044 §11 pointer pattern**. Each of the 11
   skill files is a ≤30-line pointer with frontmatter declaring `name`,
   `description`, `kind` (procedural/tool-wrapping/bootstrap-meta),
   `priority` (P0/P1/P2), `pointer` (target doc or module path), and
   `adr: 42`. Bodies include the mandatory §17.5 phrase "When uncertain,
   prefer no edit with explanation."

5. **Two skill trees, by design**:

   - **Source of truth**: `src/scieasy/_skills/qa/<name>/SKILL.md` —
     authored once, shipped with the wheel via `tool.setuptools.package-
     data`.
   - **Installed copy**: `.claude/skills/<name>/SKILL.md` (this repo's
     own use case — SciEasy contributors ARE SciEasy-project agents).

   Drift between the two is caught by
   `tests/qa/test_skill_manifest.py::test_installed_matches_source`.

6. **`agent_provisioning.qa_skills` is a sibling of the existing
   `skills.py`** (which serves the ADR-040 user-facing multi-skill
   split). Keeping them separate avoids collapsing two different
   ownership boundaries (§17 required-skill manifest vs ADR-040 user
   skill package) into one module. Both follow the same resolution
   strategy (importlib.resources first, walk-up filesystem second,
   placeholder fallback last) for symmetry.

## Out-of-scope items (TODO-tagged per CLAUDE.md §7.6)

Every deferred item is marked with an in-repo `TODO(#1155)`:

- `scripts/audit/extract_maintainers_facts.py:25` — hardening the
  extractor to require `MAINTAINERS` once it's tracked (currently
  absent from repo).
- `scripts/audit/extract_skill_facts.py:17` — cross-runtime probe
  (currently `.claude/skills/` only; Codex/Cursor/Aider/Gemini paths
  deferred to sub-PR 2).
- `scripts/audit/extract_skill_facts.py:43` — runtime path table
  expansion beyond Claude.
- `scripts/committer.py:33` — `pre-commit run --files` graceful
  degradation (will become hard-error in Phase 1F when the
  `.pre-commit-config.yaml` audit hook set lands).
- `scripts/committer.py:39` — `docs/identity/humans.yml` is not yet
  tracked (Phase 1H sub-PR 2 ships it); current behaviour is "look up
  if it exists".
- `src/scieasy/agent_provisioning/qa_skills.py:30` — non-Claude
  runtime paths in `_RUNTIME_PATHS` are commented-out pending sub-PR 2.

## Deviations from dispatch prompt

None substantive.

Minor doc note: the manifest under `docs/skills/required.yaml` keys
each entry by `name` (not nested under runtime ID, as `installed_per_runtime`
might suggest). The runtime split happens at install time (qa_skills),
not at manifest time. This matches the ADR-042 §17.3 invocation:
`agent_provisioning install --skill-manifest docs/skills/required.yaml`.

## Tests + lint + types

- **153 new tests** added (32 + 41 + 56 + 24).
- **Full `tests/qa/` suite**: 552 tests pass; 2 pre-existing failures in
  `test_workflow_v2_shadow.py::TestV1BehaviourUnchanged::test_v2_*`
  caused by editable-install pollution from a sibling worktree
  (subprocess `gate.py` finds a stale `scieasy` package). These
  failures reproduce on the un-modified tracking branch tip; they
  are not introduced by this PR.
- **Coverage on net-new code**: 95.3% (target: ≥95%). Per-module:
  90-98% on extractors, 97% on committer, 97% on qa_skills.
- **ruff check + format --check**: clean on all new files.
- **mypy --ignore-missing-imports --explicit-package-bases**: clean.
- **Phase -0.5 `temp_review`**: 0 findings (full repo and
  `--changed-files-only` mode).
- **Real-repo `generate_facts` smoke test**: produces a valid YAML
  whose `adr.latest_adr_number == 44` and `workflow.stage_count == 7`,
  matching the live tracking-branch state.

## ADR invariants preserved

- v1 6-gate `gate.py` behaviour untouched (no edits to `.workflow/`).
- 1A schemas (`scieasy.qa.schemas.*`) untouched.
- Workflow v2 validators (`scieasy.qa.workflow.validators.*`) untouched.
- ADRs / specs / governance docs untouched.
- AGENTS.md / CLAUDE.md / per-subtree AGENTS.md untouched (sub-PR 2).
