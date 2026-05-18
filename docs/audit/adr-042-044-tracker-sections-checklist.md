# ADR-042/043 Tracker Sections Checklist

Tracks the per-section YAML entries that must be present in
`docs/audit/adr-042-implementation-tracker.yaml`.

`done` means a corresponding `sections:` entry exists in the tracker yaml.

## ADR-042 sections

| # | Section heading | Status |
|---|---|---|
| 5 | Frontmatter Schema | done (pre-existing) |
| 6 | MAINTAINERS Schema | done (pre-existing) |
| 7 | Audit Report Schema + 7.5 Facts Registry | done (pre-existing) |
| 8 | Truth Model & Conflict Arbitration | done (pre-existing) |
| 9 | a/b/c1/c2/c3/d Drift Classification | done |
| 10 | Fact Substitution Registry + Rule-of-Rules Consistency | done |
| 11 | Bidirectional Ownership Closure | done |
| 12 | AGENTS.md / CLAUDE.md / Per-subtree Hierarchy | done |
| 13 | Git Trailer Conventions | done |
| 14 | Real-Behavior-Proof Gate | done |
| 15 | docs-agent: Active Doc Fixer with Path Allowlist | done |
| 16 | `committer.py` Hard Tooling | done |
| 17 | Required Skills & Cross-Runtime Installer | done |
| 19 | Workflow v2 (7-stage) | done |
| 20 | libCST Codemods Discipline | done |
| 21 | Tool Stack & CI Topology | done |
| 22 | Documentation Language Policy + Translator | done |
| 23 | Docs Build & Cross-reference Enforcement | done |
| 24 | Audit Reports | done |
| 25 | Human Developer Exemption Principle | done |

Excluded from this pass (not requested by owner):
- §18 Persona Routing
- §26–§29 (plan / exemptions / self-compliance / consequences) — operational, not artifact-bearing
- Appendices A–D

## ADR-043 sections

| # | Section heading | Status |
|---|---|---|
| 1 | Purpose & Relation to ADR-042 | done |
| 2 | Implementation Monitoring | done (pre-existing) |
| 3 | Rule-Modification Hard Blocks | done |
| 4 | Test Quality Enforcement | done |
| 5 | CLAUDE.md / AGENTS.md Layered Design | done |
| 6 | 2026 Convention Adoptions | done |
| 7 | Implementation Plan Adjustments | skipped (out of scope per owner directive) |
| 8 | Updated meta-compliance (M12–M15) | skipped (out of scope per owner directive) |
| 9 | Frontmatter additions to ADR-042 | skipped (out of scope per owner directive) |
| 10 | Consequences | skipped (out of scope per owner directive) |
| 11 | Known gaps (deferred to future addendums) | skipped (out of scope per owner directive) |

## Process

Each `done` row corresponds to one tracker entry produced by a dedicated
section-scoped sub-agent dispatch (one section per fresh context, per
the dispatcher instruction). Entries follow the pre-existing schema in
`adr-042-implementation-tracker.yaml`:

```yaml
- section: "ADR-04X section N <heading>"
  requires_artifacts:
    files: [...]
    symbols: [...]
    tests: [...]
  verification_checks:
    - id: ...
      description: ...
  status: not_started
  implemented_in_pr: null
  verified_at: null
  verifier_skill: null
  verifier_command: ...
```
