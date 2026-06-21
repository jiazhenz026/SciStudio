---
title: "Alpha Release Final Audit Report"
status: Complete
owners:
  - "@jiazhenz026"
related_issues:
  - 1733
  - 1735
related_prs:
  - 1734
related_adrs:
  - 35
  - 41
  - 42
  - 43
  - 44
language_source: en
---

# Alpha Release Final Audit Report

## 1. Verdict

Overall recommendation: **BLOCK alpha release**.

The repository has enough runtime, test, and governance structure to support an
internal alpha after remediation, but it is not alpha-ready today. The release
must not proceed until the P0 items are fixed. P1 items must either be fixed or
explicitly risk-accepted by the owner before alpha.

Audit baseline:

- Protected branch: `main`
- Remote baseline: `origin/main` at `1948ab2c18fafeb54c82c77646a2f00665e16332`
- Umbrella audit PR: `#1734` (`[DO NOT MERGE]`)
- Audit issue: `#1733`
- P0/P1 follow-up tracker: `#1735`
- Scope: core runtime only. Package and extension catalog/content completeness
  is out of scope unless it breaks core startup, execution, security, or release
  evidence.

## 2. Standard Used

The standard was recorded in
`docs/audit/2026-06-21-alpha-release-criteria.md` before dispatch.

External references used:

- Semantic Versioning: pre-release versions are unstable and may not meet normal
  compatibility expectations: https://semver.org/
- Python: alpha/beta/release-candidate versions are for advanced-user testing,
  not production use: https://devguide.python.org/developer-workflow/development-cycle/
- Django: alpha aligns with feature freeze, and unfinished features are deferred:
  https://docs.djangoproject.com/en/dev/internals/release-process/
- Kubernetes: alpha features may be buggy, disabled by default, changed or
  removed, and are recommended for short-lived testing:
  https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/
- Node.js: experimental APIs are outside normal SemVer guarantees and are not
  recommended for production: https://nodejs.org/api/documentation.html
- Rust: unstable features remain gated until enough testing supports broader
  release: https://doc.rust-lang.org/rustdoc/unstable-features.html
- OpenTelemetry: development-stage work must be isolated from stable guarantees:
  https://opentelemetry.io/docs/specs/otel/versioning-and-stability/

SciStudio alpha interpretation: non-production, short-lived internal testing,
allowed incompatibilities, but a clearly bounded and working core runtime with
visible risk classification, release evidence, and no default-scenario security
or data-loss blocker.

## 3. Agent Reports

| Agent | Report | Recommendation |
|---|---|---|
| A1-runtime-engine | `docs/audit/2026-06-21-alpha-release-runtime-engine.md` | `pass-with-must-fix` |
| A2-contracts-storage | `docs/audit/2026-06-21-alpha-release-contracts-storage-lineage.md` | `pass-with-must-fix` |
| A3-api-desktop-ai | `docs/audit/2026-06-21-alpha-release-api-desktop-ai.md` | `pass-with-must-fix` |
| A4-test-ci-governance | `docs/audit/2026-06-21-alpha-release-test-ci-governance.md` | `pass-with-must-fix` |
| A5-docs-spec-drift | `docs/audit/2026-06-21-alpha-release-docs-spec-drift.md` | `block` |
| A6-security-ops | `docs/audit/2026-06-21-alpha-release-security-ops.md` | `block` |

## 4. P0 - Alpha Release Block

### P0-1: Default CLI exposes unauthenticated API on all interfaces

Source report: A6 security/ops.

`scistudio serve` and non-bundled `scistudio gui` default to `0.0.0.0`, while
the API exposes filesystem, project, git, AI PTY, and runtime mutation surfaces
without an API-wide authentication guard. A default internal-alpha scenario can
therefore expose a local control plane to the LAN.

Required before alpha: make default interactive/local modes bind to loopback, or
add an explicit unsafe LAN opt-in plus real auth/host guard and owner risk
acceptance.

Tracking: `#1735`.

### P0-2: macOS native-dialog endpoint allows AppleScript injection

Source report: A6 security/ops.

The macOS native-dialog path interpolates request-controlled `default_filename`
and location values into AppleScript strings without escaping, then executes the
script with `osascript -e`. A6 reproduced a payload that injects
`do shell script` through the filename.

Required before alpha: escape all AppleScript string values or avoid string
interpolation, and add quote/backslash/newline/operator injection tests.

Tracking: `#1735`.

### P0-3: ADR-044 SubWorkflow contract conflicts with code and tests

Source report: A5 no-context docs/spec drift.

Accepted ADR-044 says `SubWorkflowBlock` is authoring-only and requires
flattening before runtime execution. Current code still contains executable
nested-runtime behavior, no `WorkflowDefinition.flatten_subworkflows()` API is
present, and tests actively assert the pre-ADR nested execution model.

Required before alpha: either implement ADR-044 end to end or supersede/update
ADR-044/spec/tests to match the shipped nested-runtime model.

Tracking: `#1735`.

## 5. P1 - Pass Only With Must Fix Or Risk Acceptance

- Run-start validation treats registered missing-port edges as warnings only;
  invalid typed graphs can pass start validation and fail later or drop optional
  inputs. Source: A1. Tracking: `#1735`.
- Committed representative full-path runtime coverage is missing for validation
  through `DAGScheduler`, `LocalRunner`, worker subprocess, artifact
  persistence, and lineage in one core-only check. Source: A1. Tracking:
  `#1735`.
- Zarr overwrite is not failure-atomic; a failed overwrite can remove the prior
  array store before the replacement lands. Source: A2. Tracking: `#1735`.
- Unknown dynamic port type strings silently widen to `DataObject` or skip
  workflow boundary validation. Source: A2. Tracking: `#1735`.
- AI Block tab cancel maps to `mark_done.json`, so user cancel can become
  completion/validation instead of `CANCELLED`. Source: A3. Tracking: `#1735`.
- ADR-035 remains proposed/stale while alpha-facing AI Block PTY behavior is
  implemented. Source: A3. Tracking: `#1735`.
- CI and workflow-gate jobs still use editable installs, which conflicts with
  the no-`pip install -e .` alpha/agent bar and harms reproducibility. Source:
  A4. Tracking: `#1735`.
- Sentrux baseline evidence is missing; local `sentrux` is unavailable and the
  manager checklist had no baseline/N/A evidence before finalization. Source:
  A4. Tracking: `#1735`.
- Default branch has 18 open Dependabot alerts, including one high-severity
  `vite` alert; npm Dependabot coverage is not configured. Source: A4/A6.
  Tracking: `#1735`.
- MCP `inspect_data` and `preview_data` can read arbitrary storage-reference
  paths outside the active project. Source: A6. Tracking: `#1735`.

Release evidence note: A4 found the manager gate evidence stale at the audit
head. The manager must rerun final `gate_record check` and finalize after this
report lands.

## 6. P2 - Pass, Good To Fix

- Directory-backed Zarr lineage integrity is `unknown`; recursive directory
  digest or backend manifests remain needed. Source: A2. Existing tracker:
  `#1517`.
- Block schema contract hardening still has expected xfails for stable schema
  envelope and MCP/API schema parity. Source: A2/A5. Existing tracker: `#1454`.
- Resource request gating is documented but not wired to block declarations.
  Source: A1. Existing tracker: `#887`.
- Active workflow context can surface orphan/stale workflow IDs to the AI agent.
  Source: A3.
- MCP-triggered workflow runs depend on launch-path environment for AI Block PTY
  callback URL. Source: A3.
- Architecture project tree still documents deleted `ViewProxy` and old nested
  SubWorkflow runtime surfaces. Source: A5.
- CodeBlock v2 docs/tests still mix accepted v2 semantics with legacy
  inline/function runner evidence. Source: A5.
- IO capability roundtrip contract has tracked xfail drift for save-only JSON
  groups. Source: A5. Existing tracker: `#1454`.
- Coverage fail-under remains lowered to 70 with tracked restoration TODO.
  Source: A4. Existing tracker: `#1540`.
- Full audit passes but reports advisory/planned findings outside core alpha
  scope. Source: A4.
- MCP `get_block_logs` accepts unsanitized path components. Source: A6.
- Explicit runtime `output_dir` can write artifacts outside the project root.
  Source: A6.
- Arrow/Parquet writes are direct-to-final-path while adjacent storage paths use
  atomic helpers. Source: A6.

## 7. P3 - Good To Fix

- Frontend runtime bridge tests pass but emit noisy active-context URL warnings.
  Source: A3.
- Gate wrapper/discovery ergonomics caused audit friction: wrapper preflight
  uses `--skip-execution`, while gate check reports skip-execution as non-final
  readiness in this flow. Source: A4 and manager checklist.

## 8. Checks And Evidence Summary

Agent-reported checks:

- A1: targeted workflow/validator/engine/local-runner/worker/lineage pytest
  slices passed with `PYTHONPATH=src`; scratch real-runtime probe executed a
  block, persisted an artifact, and wrote lineage rows.
- A2: targeted contract/storage/lineage pytest slice passed with `--no-cov`;
  failure-injection probes reproduced Zarr overwrite loss, dynamic-port fallback,
  and Zarr-directory lineage `unknown`.
- A3: targeted API/AI pytest passed (`49 passed`), desktop/package tests passed
  (`12 passed`), and frontend Vitest bridge tests passed (`46 passed`) with
  warnings recorded.
- A4: QA/governance test slice passed (`404 passed`), full audit passed,
  deferral scans passed, Sentrux CLI was unavailable, Dependabot API reported
  18 alerts, and PR CI was observed green for an earlier audit head.
- A5: no-context targeted docs/spec/runtime checks passed; SubWorkflow tests
  passed while asserting the rejected runtime model.
- A6: targeted security tests passed with `--no-cov`; non-destructive repros
  demonstrated macOS AppleScript injection and MCP outside-project preview.

Manager evidence:

- `gate_record check --mode local` passed before dispatch.
- `gate_record check --mode pre-pr` passed before umbrella PR creation.
- Draft umbrella PR `#1734` was opened as `[DO NOT MERGE]`.
- Final gate check/finalize still must run after this final report commit.

## 9. Alpha Decision

Alpha release status: **blocked**.

Minimum unblock path:

1. Fix all P0 items.
2. Fix or explicitly owner-risk-accept all P1 items in `#1735`.
3. Re-run final manager gate check and CI for the final release candidate.
4. Update this report or add a follow-up release signoff note showing the P0/P1
   disposition.

Package and extension content completeness should remain out of the alpha gate,
but package/extension-adjacent behavior remains in scope when it affects core
startup, execution, security, or release evidence.
