# Implementation record: #1135

Phase 1C of the ADR-042/043/044 cascade — ownership / identity wave.
Ships the four ownership-layer artifacts that subsequent Phase 1 tools
(closure check, governance-mod guard, honeypot tripwires, agent
authorization) all depend on.

## Files modified

- `.governance-paths.yaml` — NEW. Repo-root seed of the governance
  path registry per ADR-043 §3.2 lines 463-530. 34 path entries
  spanning ADRs/specs, agent-facing rule files, tool configs, CI
  workflows, workflow state machine, QA implementation paths,
  ownership/identity files, the required-skill manifest, generated
  facts, the registry itself (self-reference), append-only audit logs,
  and the codemod surface. Includes one initial `honeypot_canaries`
  entry on `.governance-paths.yaml` per §3.6.3; SHA seeding is owned
  by TC-1B.7 orchestrators.
- `MAINTAINERS` — NEW. Repo-root reverse-ownership registry generated
  by `scripts/migrate/bootstrap_maintainers.py` from ADR-042/043/044
  `governs.modules` and `governs.files`. 132 entries; every entry has
  `humans: ["@jiazhenz026"]` and `agents_allowed: [Claude, Codex,
  Cursor, Aider, Gemini]` per ADR-042 §A.3 bootstrap defaults. Schema:
  `scieasy.qa.schemas.maintainers.Maintainers` (ADR-042 §6.2).
- `docs/identity/humans.yml` — NEW. Single Tier-2 maintainer
  (`@jiazhenz026`, email `jiazhenz026@gmail.com`, joined
  `2026-01-01`). `signing_key` left unset per Q1A.5 manager default;
  TODO marker links the deferral to a sibling sub-issue under #1113.
  Schema: `scieasy.qa.schemas.identity.IdentityRegistry`
  (ADR-042 §25.3).
- `.github/CODEOWNERS` — EXTENDED. The pre-existing default-owner
  section (`* @zjzcpj`, repo-config rules) is preserved verbatim
  above an auto-generated block delimited by
  `# BEGIN auto-generated from .governance-paths.yaml` /
  `# END auto-generated from .governance-paths.yaml`. The block
  surfaces one CODEOWNERS line per `.governance-paths.yaml` entry,
  mentioning `@jiazhenz026` as the owner.
- `scripts/migrate/__init__.py` — NEW. Package marker for migration
  scripts (Phase 1C is its first inhabitant per ADR-042 Appendix A).
- `scripts/migrate/bootstrap_maintainers.py` — NEW. ADR-042 §A.3
  bootstrap migration script. Reads frontmatter from every ADR and
  spec, extracts `governs.modules` + `governs.files`, expands modules
  to `src/<...>/**` globs per §6.4, and emits a deterministic
  `MAINTAINERS` YAML. Validates the rendered text against
  `Maintainers` before writing. Provides `render_maintainers()` (pure
  function — unit-testable without disk I/O), `_module_to_glob()`,
  and a `main()` CLI with `--check`, `--repo-root`, `--default-human`,
  `--output` flags.
- `scripts/audit/generate_codeowners.py` — NEW. CODEOWNERS generator
  per ADR-043 §3.2 lines 553-571. Reads `.governance-paths.yaml`,
  validates it through `GovernancePaths`, renders an aligned
  CODEOWNERS block, and splices it into `.github/CODEOWNERS` between
  BEGIN/END markers — preserving every byte outside the markers.
  Provides `generate()`, `render_codeowners_block()`, `_splice_block()`,
  `_column_align()`, and a `main()` CLI with `--check` mode that
  exits 2 when the on-disk file is stale.
- `tests/qa/test_identity_registry.py` — NEW (declared in ADR-042
  frontmatter line 135). 8 tests covering file presence, schema
  validation, project-owner spot check, `lookup_by_email` /
  `lookup_by_github` round-trip, unknown-handle behaviour, the
  `requires_signing_key` Tier-2 property, duplicate-handle /
  duplicate-email checks, `extra="forbid"` rejection.
- `tests/qa/test_governance_paths_seed.py` — NEW (manager addition).
  9 tests covering file presence, schema validation, presence of every
  canonical path category from ADR-043 §3.2, self-reference,
  honeypot canary seeding, duplicate-path detection, `extra="forbid"`
  rejection.
- `tests/qa/test_maintainers_seed.py` — NEW (manager addition).
  15 tests across the seed file (presence, schema validation, every
  entry has an owner, every entry permits all 5 AgentRuntime values,
  ADR-042/043/044 module coverage spot checks, ADR attribution) and
  the bootstrap script itself (idempotency, rendered text validates,
  `_module_to_glob` semantics, empty-governance fallback, `--check`
  mode side-effect freedom, ADR-attribution parametrised cases).
- `tests/qa/test_generate_codeowners.py` — NEW (manager addition).
  13 tests covering CODEOWNERS existence, marker presence, on-disk
  consistency with the generator, end-to-end idempotency, block-marker
  rendering, content-preservation outside markers, append behaviour
  on marker-less files, single-marker / reversed-marker rejection,
  end-to-end generation, `--check` mode behaviour, column alignment.
- `docs/audit/impl-records/phase-1/issue-1135-a6f6cdb.md` — this file.
- `CHANGELOG.md` — single `[#1135]` entry under `[Unreleased]`
  (added in a follow-up commit per the workflow-gate step order).

## Implementation rationale

- **YAML anchor suppression in the bootstrap output.** The default
  `yaml.safe_dump` emits anchors / aliases when the same value
  (`adrs: [42]`, the agents allow-list) recurs across entries. The
  resulting file is valid YAML but hard to read and diff for
  reviewers. The bootstrap script uses a subclass that overrides
  `ignore_aliases` to force anchor-free output. The on-disk
  `MAINTAINERS` file therefore has each entry standing alone.
- **CODEOWNERS BEGIN/END marker discipline.** The generator never
  rewrites the entire file — it splices a block between two
  well-known marker lines. This preserves the pre-existing
  `* @zjzcpj` default-owner rule, the repo-config section, and any
  manual rules a future maintainer adds outside the markers. The
  generator refuses to operate if only one of the markers is present
  or if the markers appear in the wrong order — these are explicit
  invariants the unit tests assert.
- **Schema-first contract.** Each of the three data files is
  validated against its pydantic model before write: the bootstrap
  script does so via `Maintainers(**parsed)` immediately after
  rendering; the CODEOWNERS generator does so via
  `_load_governance_paths()` (which constructs `GovernancePaths`).
  This means an out-of-spec rendered file is a hard error in the
  generator, not a downstream consumer surprise.
- **Phase 1C does not implement closure.** The bootstrap-time
  coverage relationship between MAINTAINERS and ADR governs is a
  *bidirectional closure* check that lives at TC-1B.4 (per ADR-042
  §11). Phase 1C only seeds the data; the check is out of scope and
  intentionally not implemented here. The seed is rich enough
  (132 entries) that 1B.4 will have real input to verify.
- **No signing-key for the bootstrap maintainer.** Per the Phase 1
  investigation SUMMARY Q1A.5 manager default, the
  `HumanIdentity.signing_key` field is `None` for the seed entry,
  with an explicit TODO marker in the YAML. The schema permits this;
  the file-validation layer that enforces Tier-2-must-have-key lives
  in a Phase 1.5 follow-up. Recorded in PR body and this impl record.

## Deviations from the dispatch prompt

- **Branch base.** The dispatch said "Phase 1A schemas merged on
  main", but the 1A schemas merged to `track/adr-042/1a-schemas`
  (PRs #1128/#1131/#1133, all `MERGED`) rather than `main`. To pick
  the schemas up cleanly, the branch was created off
  `track/adr-042/1a-schemas` (which contains the same Phase 1
  investigation SUMMARY commit as `track/adr-042/1c-ownership` plus
  the three 1A merges). PR will target `track/adr-042/1c-ownership`
  per the dispatch; once 1A flows through to `main`, the 1A commits
  will appear as already-merged ancestry in the 1C PR.
- **Pre-existing CODEOWNERS default-owner.** The existing stub uses
  `@zjzcpj` as the global default. The auto-generated block uses
  `@jiazhenz026` (per ADR-043 §3.2 sample + ADR-042 §25.3 humans.yml).
  Both stayed; reviewers can decide whether to migrate the default
  rule in a follow-up. The two handles refer to the same person
  (private vs public GitHub identity); not a Phase 1C concern.

## Known TODOs left in code

- `docs/identity/humans.yml` line 23: `signing_key` deferral with
  explicit `TODO(#1135)` marker referencing ADR-042 §25.4 + the
  Phase 1 investigation SUMMARY Q1A.5 default. Followup tracked
  under #1113 cascade umbrella.

No other deferrals. Every other piece of behaviour the prompt called
for is shipped in this PR.

## Coverage summary

- `scripts/migrate/bootstrap_maintainers.py`: 100% of executed lines
  (the `pragma: no cover` branch is the defensive `ImportError` for
  `scieasy.qa.schemas.maintainers`, which cannot fire in the test
  environment).
- `scripts/audit/generate_codeowners.py`: 100% of executed lines.
- New tests do not affect coverage on the 1A schema modules already
  at 100% from PRs #1128/#1131/#1133.
