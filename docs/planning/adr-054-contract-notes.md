---
title: "ADR-054 Phase A Contract Documentation Evidence"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [49, 52, 54, 55]
related_specs: [adr-054-panels, adr-054-miniapp]
language_source: en
---

# ADR-054 Phase A Contract Documentation Evidence

## 1. Change Summary

Documentation slice for #2293. Phase A retains the existing Previewers sidebar
entry. Phase B core migration is #2294, Phase C author guides are #2295, and
Phase D MiniApps/All Previewers is #2354. The protected ADR/spec changes remain
exact proposals in `adr-054-owner-doc-proposal.md`; no acceptance or all-phase
completion is implied.

## 2. Contract Inventory

The existing ADR-049 table schema is unchanged. New rows cover the following
runtime surfaces, with `partial` status explicitly separating runtime code from
independent package-install validator enforcement.

| Rows | Evidence surface |
|---|---|
| PV-09-007 | `PanelDescriptor`, `parse_descriptor`: schema, API major, contexts and types |
| PV-09-008 | `PanelRegistry`, `discover_panels`: four tiers and package entry-point results |
| PV-09-009 | Panel adaptation into shared preview routing and strict ambiguity |
| PV-09-010 | `validate_interactive_panel` and open-time compatibility |
| PV-09-011 | Frontend frame, bridge and dependency-free SDK |
| PV-12-005 | `resolve_panel_file`, static token confinement, separate artifact grants |
| PV-12-006 | `validate_external_references`, CDN diagnostics and opaque-origin refusal |
| PV-12-007 | Backend-frozen targets, reachable children and one-shot interactive decision |

PV-09-002 records the added panel metadata/renderer wire fields. PV-12-001 keeps
legacy frontend-manifest same-origin restrictions and backend root omission;
it distinguishes the new noncredentialed panel token path without weakening the
legacy rule. Existing evidence is preserved, with two stale FrontendManifest
wording anchors corrected to the current docstring.

These rows are evidence for contract review. The table checker verifies symbols
and text anchors; it does not run an arbitrary package candidate through a
production install pipeline. No ADR-049 addendum exists for this slice.

## 3. Public Author Surface

`panel.json`, package `scistudio.panels` entry-point directory discovery, and the
browser SDK are author-facing. Descriptor, registry and context Python modules
are internal implementation; inventory recognition does not make them public
ADR-052 import roots.

The canonical reference generator observes these existing public Python changes:

| Surface | Additive change |
|---|---|
| `PreviewDataAccess.series_points` | Optional `max_points`, keeping the legacy uncapped default |
| `PreviewDataAccess.text_chunk` | Byte `offset` and optional `length` |
| `PreviewDataAccess.collection_sample` | Optional `cursor` and `limit` |
| `PreviewDataAccess.artifact_file` | Host-side artifact path resolution, provisional since 0.3.5 |
| `SeriesPoints` | Appended `sampled`, `complete`, `decimation` fields |
| `TextChunk` | Appended `encoding`, `offset`, `next_offset` fields |
| `CollectionSample` | Appended `next_cursor` field |
| `PreviewerSpec`, `PreviewEnvelope` | Optional panel identity metadata; legacy shape remains usable |

The internal `panel_array_plane`, `panel_array_tile`, `panel_series_points`, and
`panel_table_xy` methods are explicitly excluded by generated-reference filters.
No public `scistudio.panels` Python API is introduced.

## 4. Checks And Boundaries

Initial comparison uses `origin/main` at `7b132175` and documentation dependency
baseline `4b8f948a` (A1 initial plus A3 follow-ups). Actual commands:

- `python scripts/audit/check_package_contract_tables.py --sections 09,12` on
  the unchanged main baseline: **12 errors, 3 warnings**.
- The same command after new rows, before A2 dependency import: **13 errors,
  5 warnings**. Six new panel inventory omissions are covered and two old
  FrontendManifest anchors are repaired. Three errors are missing A2 SDK/frame
  files in this slice's dependency baseline; ten are unchanged legacy failures.
  Two additional warnings were previously masked by those stale code anchors.
- `PYTHONPATH=src python scripts/docs/build_reference.py --generate-only`:
  **passed**; generated changes are the data-access reference filters and paired
  embedded data-access/models references. No `llms.txt` delta or new panels
  Python reference root was generated.
- `PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --record
  .workflow/records/2293-panel-contract-docs.json --base 4b8f948a --head HEAD`:
  **not passed**. Commit hygiene passed. Full audit found three A1 docstring
  errors and eleven planned-surface migration errors, repeated in its closure
  report. Informational planned surfaces are not counted as errors. Protected
  document changes require the proposal landing; A1 owns its docstring fixes.
- `git diff --check`: **passed** for the initial documentation changes.

Unchanged section 09/12 failures cite removed external imaging package paths,
removed plot runtime/harness paths, an old `sanitize_svg` signature, and two
uncovered tutorial inventory anchors. The command's result is not a pass and
those failures are not erased or downgraded. SDK evidence must be rechecked once
its implementation chain is integrated. Source test anchors are not claims that
this docs agent ran the runtime tests.

Implementation tests are N/A for this documentation-only slice. Sentrux MCP is
unavailable; only actual gate-selected CLI evidence is recorded. The manager
owns the mounted-app OpenAPI snapshot, integrated gate/finalize, PR provenance,
CI and browser smoke. Real JupyterHub behavior and PDF.js companion/browser
parity have not been established here.

## 5. Tracked Decisions And Remaining Work

TODO(#2293): Resolve strict FR-002 `core.*` reservation versus ADR-054 same-id
core customization before claiming that customization path. The current parser
reserves core ids. Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2293.

TODO(#2293): Land reviewed protected-document proposals and reconcile
package-validator enforcement evidence before Phase A acceptance. Follow-up:
https://github.com/jiazhenz026/SciStudio/issues/2293.

TODO(#2293): Classify and repair pre-existing ADR-049 table drift through a
manager-approved scope or linked follow-up before claiming a passing full table
check. Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2293.

TODO(#2294): Replace both temporary compiled interactive windows
`core.interactive.data_router` and `core.interactive.pair_editor` with HTML panels;
complete core preview migration and PDF rendering verification in Phase B.
Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2294.

TODO(#2295): Land full author guides and architecture narrative in Phase C.
Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2295.

TODO(#2354): Deliver MiniApps/All Previewers navigation and the call/process
runtime in Phase D. Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2354.

TODO(#2288): Retain tracked 0.6 legacy removal, preview Python, and notebook/sync
work outside Phase A. Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2288.

Owner pause boundary: stop after Phase A and wait for the owner before starting
any Phase B, C or D work. Follow-up issue links above record future scope only;
this slice does not start full author guides or architecture narrative work.

### Dependency Follow-up

Reviewed A2 commits `6d5379af`, `b8b4dde4`, `d0b2b8ba`, `f2b015c0` are now in
this documentation tree. All eight new rows have matching local code/test
anchors. The focused checker result is **10 errors, 5 warnings**, entirely the
unchanged legacy evidence described above; no new panel inventory gaps remain.

The full unfiltered checker was also compared: unchanged `origin/main` reports
**99 errors, 12 warnings**; the candidate reports **105 errors, 14 warnings**.
The exact added errors are the eight new ADR-049 master-index ids whose patches
remain proposal-only. The two repaired FrontendManifest anchors account for the
reduction from 99 baseline errors to 97 plus eight pending index rows.

A1 follow-up `0ea6f63d` was imported. The external-reference validator now lives
in `panels/files.py` and is re-exported by `panels/validation.py`; PV-12-006 points
to its real definition. PV-09-008 now also cites the dedicated four-tier registry
test. The proposed bootstrap wording records the A1/A2 agreed
`ContextResponse.bootstrap_proof` and document-bound bootstrap channel; its
implementation and final evidence remain conditional until those commits land.

### Final Source And Proposal Verification

Reviewed A1 `acdb1376` and A2 `45e52e05` are imported. The three docstring
references identified above are removed in that source. The bootstrap proposal
now matches the actual context proof, trusted entry prelude and retained
original-document channel; artifact wording matches the host byte cap,
independent 30-second body deadline and frame-local SDK blob lifecycle.
PV-09-011 and PV-12-005 cite those implementation and regression-test anchors.

Final focused table check: **10 errors, 5 warnings**, all unchanged legacy
section 09/12 evidence. Final full table check: **105 errors, 14 warnings**,
with the same eight added proposal-only ADR-049 index errors and two repaired
baseline errors described above. There are no new panel code/test-anchor or
inventory errors. These are failing checks with classified causes, not passes.

The canonical reference generator passed again after the final dependency
imports. `git apply --check` accepts the complete proposed patch, including all
four protected documents. `git diff --check` passes. Per manager instruction,
the full gate is not repeated before owner-controlled proposal application;
its earlier failure remains recorded, and the manager must run the final
integrated checks after that application. No CI, runtime-test execution, browser
rendering or Phase A acceptance is claimed by this documentation slice.
