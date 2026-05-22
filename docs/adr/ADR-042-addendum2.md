---
adr: 42
addendum: 2
title: "Semantic Duplication Scan Gate"
status: Accepted
date_created: 2026-05-21
date_accepted: 2026-05-21
date_superseded: null

supersedes: []
superseded_by: null
related: [42]
closes_issues: [1405]
tracking_issue: 1405

is_code_implementation: true
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - scripts/semantic_dup_scan.py
    - docs/audit/baselines/semantic-dup-baseline.json
    - docs/audit/2026-05-21-semantic-dup-scan.md
    - .github/workflows/semantic-dup-scan.yml
    - docs/adr/ADR-042-addendum2.md
  excludes:
    - docs/audit/baselines/semantic-dup-current.json

tests:
  - tests/scripts/test_semantic_dup_scan.py

agent_editable: false
assisted_by:
  - "Claude:opus-4-7"

phase: implementation
tags: [qa, ci, semantic-duplication, embeddings, ratchet, full-audit]
owner: "@jiazhenz026"
co_authors: []
language_source: en
translations: []
---

# ADR-042 Addendum 2: Semantic Duplication Scan Gate

## 1. Decision Summary

This addendum extends ADR-042 governance with a semantic duplication scan gate
that complements existing Sentrux lexical/structural redundancy checks. Sentrux
detects copy-paste at the AST/file level; the new gate detects functionally
equivalent code expressed with different identifiers, ordering, and helper
shape, which AI-assisted authoring is prone to produce.

| Decision | Change | Enforcement target | Detailed section |
|---|---|---|---|
| D1. Semantic duplication ratchet | Adopt embedding-based clustering of source functions as a new ratchet-style governance gate, mirroring the existing `max_cycles` / `max_cc` pattern | CI ratchet check on PRs touching source; weekly scheduled scan | Section 3 |
| D2. Committed baseline + auto-derived ratchet | Track aggregate metrics (cluster count, duplicate LOC absolute, duplicate %, max cluster size) in a committed baseline JSON; the baseline file itself defines the failing thresholds | Local CLI + CI evidence | Section 4 |
| D3. Full audit inclusion | Include the markdown cluster report as a recurring full-audit input so humans can triage clusters and decide which to dedup or grandfather | Full-audit workflow consumes the report; periodic ratchet-down by maintainer | Section 5 |
| D4. Aggregate-only ratchet authority | Track per-cluster identities for reporting only, never for ratcheting; aggregate thresholds are the binding ratchet because cluster membership is volatile across small refactors | Ratchet schema + CI check semantics | Section 4 |

### 1.1 Problems Addressed

| Problem | Risk | Decision | Detailed section |
|---|---|---|---|
| Lexical/AST near-clone detection (Sentrux) cannot detect functions that share behavior but not text | AI agents repeatedly reinvent equivalent helpers (`_source_sha` was found copy-pasted across 9 governance scripts at cos sim 0.989; `IOBlock.run` ≈ `ProcessBlock.run` at sim 0.921). Sentrux redundancy reports the codebase as healthy (raw 0.085) while real semantic duplication concentrates in critical paths. | Add an embedding-based scan that clusters functions by behavioural similarity (cosine over a code-tuned sentence-transformer) | Section 3 |
| Per-cluster identity is too volatile to ratchet on directly | A small refactor that renames a function or merges two clusters causes per-cluster diffs even when overall duplication has decreased | Ratchet on aggregate metrics only; clusters are reported for humans, not enforced | Section 4 |
| Initial state already has 60 candidate clusters covering 10% of source LOC | Hard-failing the baseline would block every PR | Allow 5% headroom on cluster count and duplicate LOC, no headroom on largest cluster size; ratchet down after each dedup PR | Section 4 |
| The embedding model dependency is heavy (PyTorch + ~440MB model) | Per-PR cost is significant if run unconditionally | Cache the HF model in CI; run only on PRs touching `src/scistudio/**/*.py`, the scanner, the baseline, the workflow, or this addendum; weekly schedule fills coverage gaps | Section 5 |
| Cluster findings need human triage (some clusters are intentionally similar, e.g. PosixOps/WindowsOps) | A pure-machine gate would either ratchet down too slowly or generate noise PRs | Pair the CI ratchet check with full-audit-driven human triage of the markdown cluster report | Section 5 |

## 2. Scope

The semantic-duplication gate applies to Python source under `src/scistudio/`
only. It explicitly does not apply to:

- `tests/**` — test files are legitimately repetitive by design.
- `frontend/**` — frontend code uses different language tooling.
- `scripts/**` and one-off audit reports.

Aggregate metrics are tracked. Per-cluster identity is reported but not
enforced.

## 3. Tool, Modes, and Output Schema

The gate is implemented by `scripts/semantic_dup_scan.py`. The script:

1. Walks the configured root and extracts every function / method via AST,
   filtering by minimum LOC (default 5). Docstrings are stripped so that
   doc-only similarity does not dominate behavioural similarity.
2. Embeds each function with a code-tuned embedding model
   (default `BAAI/bge-base-en-v1.5` served via the `fastembed` ONNX
   runtime + int8-quantised weights; the model is configurable so that
   stronger code-tuned models can be swapped in without contract
   changes). The fastembed backend replaces the heavier
   sentence-transformers + PyTorch stack to cut CI install footprint
   from ~2GB to ~100MB and inference time by ~3x.
3. Computes pairwise cosine similarity over normalised embeddings and
   clusters with union-find at a similarity threshold (default 0.92).
4. Emits a markdown report (human readable) and a JSON payload (machine
   readable), both deterministic for a given model + threshold + source.

Three modes are supported:

| Mode | Effect | When used |
|---|---|---|
| Default | Scan, emit `--out` markdown and/or `--json-out` payload | Local exploration |
| `--write-baseline PATH` | Scan and write a JSON baseline with auto-derived ratchet (current metrics plus headroom policy) | Maintainer ratchet-down |
| `--check PATH` | Scan and compare aggregate metrics against the baseline ratchet; exit 1 on violation | CI gate |

The baseline JSON has this shape:

```json
{
  "schema_version": 1,
  "captured_at": "<ISO timestamp>",
  "config": { "root": "...", "model": "...", "threshold": 0.92, "min_loc": 5 },
  "current": {
    "functions_scanned": 1248,
    "clusters": 60,
    "duplicate_loc": 3474,
    "total_loc": 34636,
    "duplicate_pct": 10.03,
    "max_cluster_size": 9
  },
  "ratchet": {
    "max_clusters": 63,
    "max_duplicate_pct": 10.53,
    "max_cluster_size": 9,
    "max_duplicate_loc": 3647
  },
  "ratchet_policy": "<human-readable policy text>"
}
```

The `current` block captures the snapshot at baseline write time; the
`ratchet` block is the set of thresholds that `--check` enforces. The two
are tracked separately so that a future tightening of the ratchet does not
require also rewriting historical snapshots.

## 4. Ratchet Policy and Ratchet-Down Workflow

The ratchet policy follows the same shape as `.sentrux/rules.toml`
`max_cycles`. Headroom is intentionally tight rather than generous so that
each successful dedup PR can ratchet the baseline down.

Initial headroom on first write:

- `max_clusters`: current × 1.05 (rounded up)
- `max_duplicate_pct`: current × 1.05
- `max_duplicate_loc`: current × 1.05 (rounded up)
- `max_cluster_size`: current (no headroom)

A maintainer ratchets the baseline down by re-running
`python scripts/semantic_dup_scan.py --write-baseline
docs/audit/baselines/semantic-dup-baseline.json` after a dedup PR merges.
The expectation is that the baseline tightens every time duplicate code is
removed, so the ratchet acts as a one-way valve.

If a legitimate code addition causes the ratchet to fail and the maintainer
decides the new duplication is acceptable (e.g. platform-branch code,
parallel reader implementations that must stay split for licensing
reasons), the addition follows the existing override-label workflow under
ADR-042 §5: the PR gains an `admin-approved:ai-override` label with a
written rationale.

## 5. CI Integration and Full Audit Integration

Per-PR CI (`.github/workflows/semantic-dup-scan.yml`) runs the scan in
`--check` mode against the committed baseline. The job:

- triggers on schedule (weekly) and on pull requests whose diff touches
  any of: `src/scistudio/**/*.py`, `scripts/semantic_dup_scan.py`,
  `docs/audit/baselines/semantic-dup-baseline.json`, or this addendum;
- caches the Hugging Face model directory across runs so that the
  bandwidth and warmup cost is paid once;
- uploads the full markdown report and JSON payload as build artifacts
  for every run, regardless of pass/fail, so that PR reviewers can read
  the current cluster list without re-running locally;
- fails the job with exit 1 on any ratchet violation.

`docs/audit/baselines/semantic-dup-current.json` is the ephemeral per-run
JSON payload produced by `--json-out`. It is `.gitignore`d to avoid
churn. Only the committed `semantic-dup-baseline.json` is durable.

Full-audit integration is by reuse: the same script invocation that
produces the markdown report for CI artifacts also produces the report
that full-audit consumes. A full-audit pass regenerates the report from
the current source tree, presents it to a human reviewer, and is the
intended trigger for ratchet-down decisions.

## 6. Verification

This addendum is verified by:

- `tests/scripts/test_semantic_dup_scan.py` covers AST extraction,
  docstring stripping, union-find clustering correctness, and
  ratchet-violation detection. The embedding model itself is not invoked
  from unit tests; CI exercises the embedding path end-to-end.
- The committed initial baseline at
  `docs/audit/baselines/semantic-dup-baseline.json`.
- The committed initial report at
  `docs/audit/2026-05-21-semantic-dup-scan.md`.
- `.github/workflows/semantic-dup-scan.yml` exercising the `--check` path
  on every PR matching the path filter and on a weekly schedule.

## 7. Out Of Scope

This addendum does not promote the scan to a first-class module under
`src/scistudio/qa/audit/`. The scanner stays at `scripts/` for the first
iteration. Promotion will be considered in a follow-up issue once the
gate has been exercised against several real PRs and the CLI surface has
stabilised.

This addendum does not propose any of the dedup work the initial scan
surfaced (governance `_source_sha` 9-way duplicate, materialisation
double-path, IOBlock/ProcessBlock `run()` near-duplicate, type-class
mixin duplicates). Each candidate is tracked as its own follow-up issue
or PR. The expectation is that those follow-ups ratchet the baseline
down over time.

This addendum does not change the default embedding model after the
gate ships. Swapping in `nomic-ai/CodeRankEmbed`,
`Salesforce/SFR-Embedding-Code-400M_R`, or another model is configurable
on the CLI but a default change requires a future addendum because
threshold semantics depend on the model.
