---
title: "ADR-043 Package Migration Phase D Owner-Authored E2E Test Cases"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 41
  - 43
related_specs:
  - adr-043-package-migration
language_source: en
---

# ADR-043 Package Migration — Phase D Owner-Authored E2E Test Cases

## Purpose

Owner-authored end-to-end test scenarios that go beyond the Phase C2
golden-path coverage. SC-006 acceptance requires every P1 case in this file
to PASS before the umbrella PR #1297 is allowed to merge into `main`.

This file is committed to the repository as Phase D evidence and tracked in
the manager checklist §14 (Phase D — Owner-Authored E2E) and §15 (SC-006
row).

## Conventions

- **Case ID**: `E2E-<NNN>` (contiguous, no gaps).
- **Category**: see §1 (`WF`, `XP`, `UI`, `BF`, `RG`, `SE`).
- **Priority**:
  - `P1` MUST pass before final umbrella merge into `main`.
  - `P2` SHOULD pass; deferral requires owner sign-off + tracked follow-up issue.
  - `P3` nice-to-have; deferral allowed at owner discretion.
- **Status checkboxes**:
  - `[ ]` not run yet
  - `[~]` running / in-progress
  - `[x]` pass
  - `[!]` fail (link the bug-fix issue in the **Issue** field)
- **Evidence on pass**: cite a committed test name, screenshot path, gate
  record check entry, or specific commit SHA. Chat reports are not evidence.
- **Evidence on fail**: open a tracked bug-fix issue with `#NNNN` reference.

## 1. Categories

| Code | Description | Mostly covers |
|---|---|---|
| **WF** | Real-world workflow path (typical lab pipeline owner runs in production) | spec acceptance for full pipelines |
| **XP** | Cross-package interaction (imaging → SRS, core IO → imaging, frontend → backend, etc.) | integration risk between phase merges |
| **UI** | Frontend flow exercised live in a real browser (capability dropdown / OME browser / lossy-save warning) | **SC-005 live evidence** (substitutes for the missing Chrome MCP / Playwright harness; A3's JSDOM smoke is not enough alone) |
| **BF** | Bio-Formats live fixture (requires JVM environment) | **SC-002 live evidence** (CI runners do not have JVM; tests skip there) |
| **RG** | Regression scenario (prior incident or behavior the owner wants protected) | preventing re-introduction of past bugs |
| **SE** | Spec edge case (FR or SC boundary, e.g. ambiguity, empty Collection, missing extras, cross-format save) | hardening contract surfaces |

## 2. Test Cases

> Owner fills in the rows below. One example per category is provided to
> illustrate the expected format — replace with real cases, then add more.

---

### E2E-001 — Real microplastic SRS calibration pipeline reproduced as a SciEasy block graph

- **Category**: WF
- **Priority**: P1
- **Related FR / SC**: FR-004, FR-006, FR-009, FR-010, FR-011, SC-001, SC-003
- **Owner project**: `C:/Users/jiazh/Box/Jiazhen Zhang/04 Data/microplastics/processed/microplastic-size-calibration/` (a real SciEasy project with `project.yaml`, custom `blocks/`, and 12 SRS TIFF fixtures under `data/raw/`).
- **Given**: the project's existing custom blocks (`microplastics.parse_metadata`, `melt_spectra`, `find_peaks`, `calibrate_size`) plus the ADR-043 + ADR-041 integrated umbrella's imaging + srs blocks.
- **When**: workflow `workflows/microplastic-size-calibration-v3.yaml` (written for this case) is run via `python run_workflow.py workflows/microplastic-size-calibration-v3.yaml`. The graph is
  `parse_metadata → imaging.load_image → srs.calibrate (scale=50000) → imaging.axis_projection (max along λ) → imaging.cellpose_segment (cyto3, diameter=8) → srs.extract_spectrum (3D stack + 2D labels) → microplastics.melt_spectra → find_peaks → calibrate_size → save_data`.
- **Then**:
  - Workflow runs to completion across all 12 TIFFs.
  - Final outputs land under `data/parquet/calibration.parquet` + `data/artifacts/size_calibration.zarr`.
  - The calibration's log-log slope/intercept matches the notebook within numerical tolerance.
  - Every `Image` flowing through `imaging.axis_projection` and `imaging.cellpose_segment` preserves `meta.ome` through to the downstream consumer (FR-009 Mode B + Mode C propagation).
- **Expected**: PASS — exercises the full ADR-043 capability dispatch + ADR-041 propagation contract on real data.
- **Status**: `[ ]`
- **Evidence (pass)**: `workflows/microplastic-size-calibration-v3.yaml` committed in the owner's Box project; run record under `lineage/` of that project.
- **Issue (fail)**:

---

### E2E-002 — Same calibration notebook run end-to-end as a single ADR-041 CodeBlock v2 node

- **Category**: WF (also exercises ADR-041 CodeBlock v2)
- **Priority**: P1
- **Related FR / SC**: FR-009 (propagation N/A — single node), ADR-041 §4 (Python + Jupyter notebook backend), ADR-041 §7 (auto-captured `_executed_notebook` artifact)
- **Owner project**: same as E2E-001.
- **Given**: the same project's `size_intensity_calibration_pipeline.ipynb` at the project root; CodeBlock v2 + Jupyter notebook backend integrated in the umbrella branch (ADR-041 Track C2 from PR #1235).
- **When**: workflow `workflows/microplastic-codeblock-direct.yaml` (written for this case) is run. The graph is a single `code_block` node with `script_path: size_intensity_calibration_pipeline.ipynb`, `working_directory: "."`, `inputs: []`, `outputs: []`, `timeout_seconds: 1800`. The notebook reads `data/raw/*.tif` and writes `calibration_outputs/...` natively via project-cwd.
- **Then**:
  - CodeBlock launches `jupyter nbconvert --execute` (or equivalent) on the notebook.
  - Notebook runs to completion against the project's `data/raw/` directory.
  - `_executed_notebook` Artifact output is captured per ADR-041 §7 and visible in the run's lineage.
  - On-disk outputs at `calibration_outputs/` are equivalent to the manual notebook run (existing `size_intensity_calibration_pipeline_executed.ipynb` is the reference baseline).
- **Expected**: PASS — proves CodeBlock v2 can wrap an existing real-world notebook with zero source edits.
- **Status**: `[ ]`
- **Evidence (pass)**: workflow YAML committed in the owner's Box project; lineage entry for the run; size + content parity check between the auto-captured executed notebook and the reference `size_intensity_calibration_pipeline_executed.ipynb`.
- **Issue (fail)**:

---

### E2E-003 — _(example WF; replace with a real case)_

- **Category**: WF
- **Priority**: P1
- **Related FR / SC**: FR-009 (propagation), FR-010 (imaging audit), SC-003
- **Given**: a Zeiss CZI acquisition at `examples/sample.czi` with known
  `physical_size_x = 0.3 μm/px`, 5 channels, axes `tczyx`.
- **When**: workflow `LoadImage(sample.czi) → Resize(factor=0.5) → ChannelSplit → SaveImage(out_<ch>.ome.tif)` runs end-to-end.
- **Then**:
  - Each `out_<ch>.ome.tif` reloads to an `Image` with
    `meta.ome.images[0].pixels.physical_size_x == 0.6 μm/px` (doubled from
    source under the resize 0.5x).
  - Each saved file's `meta.ome.images[0].pixels.size_c == 1` (channel split
    drops the c axis).
  - Each saved file's `meta.ome.images[0].channels[0].name` matches the
    upstream channel name.
- **Expected**: PASS — all assertions hold; workflow run record shows the
  capability_id chain `imaging.image.czi.load → ... → scieasy-blocks-imaging.image.tiff.save`.
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

### E2E-002 — _(example XP; replace with a real case)_

- **Category**: XP
- **Priority**: P1
- **Related FR / SC**: FR-009 / FR-011
- **Given**: an `SRSImage` instance loaded with `meta.ome.physical_size_x = 0.5 μm/px` and `meta.wavenumbers_cm1 = [...]`.
- **When**: workflow `LoadData → cast-to-SRSImage → SRSSpectralDenoise → SRSCalibrate → SRSKMeansCluster → SaveData(label.npy)` runs.
- **Then**:
  - The intermediate SRSImage after `SRSSpectralDenoise` preserves both
    `ome.physical_size_x` and `wavenumbers_cm1` (Mode A propagation).
  - The Label output of `SRSKMeansCluster` carries `meta.ome` matching the
    input SRSImage (Mode C fix verified in B2).
- **Expected**: PASS — ome flows end-to-end through the SRS pipeline; no
  silent drop between phases.
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

### E2E-003 — _(example UI; replace with a real case)_

- **Category**: UI
- **Priority**: P1 (substitutes for SC-005 live Chrome coverage)
- **Related FR / SC**: FR-012, FR-013, FR-014, SC-005
- **Given**: SciEasy frontend open in Chrome at `http://localhost:5173`
  against a backend that exposes the merged umbrella branch. A workflow
  with an AppBlock node whose port has `type=Image, extension=.tif`.
- **When**:
  1. Open the port editor for that port.
  2. Inspect the capability dropdown.
  3. Select `imaging.image.tiff.load` (or whichever the dropdown surfaces).
  4. Run the workflow; click "OME metadata" on the output preview.
  5. Edit the workflow to route the loaded Image into `SaveImage(out.png)`.
- **Then**:
  - Dropdown shows ≥ 2 capability options for `(load, Image, .tif)` with
    metadata-fidelity badges.
  - After selection, `capability_id` is persisted on the port (visible in
    workflow YAML / API export).
  - "OME metadata" button opens a panel that renders `pixels.physical_size_x`
    as a navigable field.
  - LossySaveWarning chip appears on the SaveImage node listing the OME
    fields PNG cannot persist.
- **Expected**: PASS — verifies SC-005 live in a real browser, closing the
  Chrome MCP / Playwright gap A3 surfaced.
- **Status**: `[ ]`
- **Evidence (pass)**: screenshot path or Chrome devtools recording committed under `docs/audit/e2e/`
- **Issue (fail)**:

---

### E2E-004 — _(example BF; replace with a real case)_

- **Category**: BF
- **Priority**: P1 (this is the SC-002 live evidence path)
- **Related FR / SC**: FR-004, FR-008, SC-002
- **Given**: a local Python environment with JVM + `python-bioformats` +
  `javabridge` + `ome-types` installed via `pip install scieasy-blocks-imaging[bioformats]`.
  Fixture files at `tests/fixtures/microscopy/{sample.czi, sample.nd2, sample.lif, sample.oir, sample.oib}` (paths
  owner-supplied; can be downloaded or committed under git-lfs).
- **When**: for each fixture file, run
  `LoadImage(<fixture>, capability_id="imaging.image.<format>.load")` and
  inspect the returned Image.
- **Then**:
  - Returned `image.meta.ome.images[0].pixels.physical_size_x` is not None.
  - Returned `image.meta.ome.images[0].pixels.size_x` matches the file's
    actual pixel width.
  - Returned `image.meta.ome.images[0].channels` is non-empty (at least one
    channel populated).
- **Expected**: PASS for each fixture; failures imply Bio-Formats handler
  gap or `ome-types` parse issue.
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

### E2E-005 — _(example RG; replace with a real case)_

- **Category**: RG
- **Priority**: P2
- **Related FR / SC**: FR-001, FR-002, FR-003, SC-001
- **Given**: a workflow YAML saved in 2026-04 (pre-ADR-043) that uses
  `LoadData(core_type=DataFrame, path="data.csv")` upstream and
  `SaveData(core_type=DataFrame, path="out.csv")` downstream.
- **When**: load the YAML in the migrated runtime and execute.
- **Then**:
  - Workflow runs to completion with zero new errors.
  - Output CSV is byte-identical to the pre-migration baseline (cross-check
    via SHA-256).
  - Workflow run record names the new capability ids (`core.dataframe.csv.load`,
    `core.dataframe.csv.save`).
- **Expected**: PASS — confirms no behavior drift for the 6 core types post
  FR-003 ClassVar removal.
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

### E2E-006 — _(example SE; replace with a real case)_

- **Category**: SE
- **Priority**: P2
- **Related FR / SC**: FR-008 (missing-extras failure mode), spec §2.5 edge cases
- **Given**: a Python environment without the `bioformats` extra installed.
- **When**: a workflow with `LoadImage(sample.czi)` is loaded and execution
  attempted.
- **Then**:
  - Failure is raised before any IO with a clear message naming the install
    command `pip install scieasy-blocks-imaging[bioformats]`.
  - The CapabilityLookupError or ImportError is typed (not a bare RuntimeError).
- **Expected**: PASS — verifies FR-008 final clause that missing-extras
  produces a clear, actionable error. **Note**: this case also surfaces the
  FR-008 vs §4.5 internal inconsistency flagged by the C1 audit — owner
  should confirm which behavior they want before this case is run.
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

<!-- ADD MORE CASES BELOW. Copy a template row and fill in. Keep IDs contiguous. -->

### E2E-007 — _(your case)_

- **Category**:
- **Priority**:
- **Related FR / SC**:
- **Given**:
- **When**:
- **Then**:
- **Expected**:
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

### E2E-008 — _(your case)_

- **Category**:
- **Priority**:
- **Related FR / SC**:
- **Given**:
- **When**:
- **Then**:
- **Expected**:
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

### E2E-009 — _(your case)_

- **Category**:
- **Priority**:
- **Related FR / SC**:
- **Given**:
- **When**:
- **Then**:
- **Expected**:
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

### E2E-010 — _(your case)_

- **Category**:
- **Priority**:
- **Related FR / SC**:
- **Given**:
- **When**:
- **Then**:
- **Expected**:
- **Status**: `[ ]`
- **Evidence (pass)**:
- **Issue (fail)**:

---

## 3. Execution Plan (Phase D2)

After owner finalizes §2:

1. Manager (or a dispatched D2 implementer agent) translates each case into
   the appropriate runnable harness:
   - **WF / XP / RG / SE / BF** → Python pytest under
     `tests/e2e/adr-043-package-migration/` (or in package-specific tests
     directories as appropriate).
   - **UI** → manual Chrome walkthrough following the steps in the case;
     screenshot evidence committed under `docs/audit/e2e/<case-id>/`.
2. Each case executed against the latest integrated umbrella branch HEAD.
3. Pass/fail recorded inline in §2 with an evidence link or issue number.
4. For each fail: open a tracked bug-fix issue (label `bug`,
   `adr-043-phase-d-fix`), dispatch a fix agent or fix in-PR per audit
   protocol, re-run the failing case.

## 4. SC-006 Gate

| Gate | Required | Status |
|---|---|---|
| All P1 cases in §2 are `[x]` PASS | yes | pending |
| All P2 cases are `[x]` PASS or have an owner-approved defer with tracked follow-up issue | yes | pending |
| P3 cases recorded but no gate | informational | pending |
| Audit doc committed in PR alongside any code/test deltas from Phase D | yes | pending |
| Phase D fixes (if any) all merged into umbrella before final review | yes | pending |
| Final umbrella PR rebased against latest `main` (post-owner audit-debt fixes) | yes | pending |
| Owner final review of umbrella PR | yes | pending |

When every row above is met, the umbrella PR moves from `[DO NOT MERGE]` to
ready-for-merge and the owner makes the final merge call.

## 5. Notes

- This file is owner-edited; agents touch it only to mark per-case
  pass/fail evidence after running, plus the §4 gate rows during final
  readiness.
- Live Chrome UI cases (category UI) are the substitute for SC-005's
  missing real-browser harness. If the owner provisions Chrome MCP /
  Playwright later, those tests can replace the manual UI cases in this
  file and the SC-005 row in the manager checklist §15 can be promoted to
  `[x]` from `[~]`.
- Bio-Formats cases (category BF) only run where JVM is available. If the
  owner's primary CI / dev environment does not have JVM, BF cases stay
  P2/P3 and the SC-002 row in the manager checklist §15 stays `[~]` with
  documented rationale.
