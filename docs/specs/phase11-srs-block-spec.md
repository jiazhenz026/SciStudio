---
spec_id: phase11-srs-block-spec
title: "Phase 11 SRS Plugin Block Specification"
status: Deprecated
feature_branch: legacy/phase11-srs-block-spec
created: 2026-04-07
input: "Historical Phase 11 scistudio-blocks-srs implementation specification retained for reference."
owners:
  - "@jiazhenz026"
related_adrs:
  - 27
  - 28
related_specs:
  - phase11-implementation-standards
  - phase11-imaging-block-spec
  - phase11-lcms-block-spec
scope:
  in:
    - Historical SRS plugin block contracts retained for reference.
  out:
    - Active implementation planning.
governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests: []
acceptance_source: issue
language_source: en
---
# Phase 11 SRS Plugin Block Specification

## 1. Change Summary

This deprecated spec is retained as historical reference. Its original body is preserved below, but it is not an active implementation spec under ADR-042.

## 2. Existing Historical Body

# Phase 11 — `scistudio-blocks-srs` Plugin Block Specification

**Status**: accepted
**Date**: 2026-04-07
**Issue**: #299
**Authoritative ADRs**: ADR-027 (Phase 10 type system), ADR-028 (IOBlock refactor),
ADR-028 Addendum 1 (dynamic ports + GUI)
**Companion specs**: `docs/specs/phase11-imaging-block-spec.md` (parent — supplies
`Image`, `Mask`, `Label`, `LoadImage`), `docs/specs/phase11-lcms-block-spec.md`
(sibling — independent plugin)
**Master plan**: `phase11_master_plan.md` §2.4 SRS PLUGIN (locked block list)

---

## 1. Purpose

This document is the **single source of truth** for the implementation tickets
that ship the `scistudio-blocks-srs` plugin package. It is the SRS-modality
companion to the imaging spec (`phase11-imaging-block-spec.md`) and inherits the
imaging spec's `Image` / `Mask` / `Label` types and `LoadImage` / `SaveImage` IO
blocks unchanged.

A subsequent implementation agent picking up any single T-SRS ticket should
**not need to re-read the master plan or the ADRs**. This document quotes the
locked master-plan §2.4 SRS section for traceability and reproduces the
relevant ADR-027 / ADR-028 / ADR-028 Addendum 1 contracts inline where the
implementation is load-bearing.

The spec covers:

- One **type** (`SRSImage`) that subclasses imaging's `Image` and tightens the
  axis schema to require the spectral `lambda` axis.
- **Eleven blocks** organised into three categories — preprocessing (4),
  component analysis (5), spectral extraction (2).
- One **package skeleton** ticket (entry-points, layout, smoke tests).
- One **end-to-end integration** ticket that consumes the four real test
  images at `C:\Users\jiazh\Desktop\workspace\Example\images\` and exercises
  the imaging plugin's `CellposeSegment` alongside the SRS plugin's
  `ExtractSpectrum` to produce per-cell spectra.

The spec deliberately ships **no separate `LoadSRS` / `LoadSRSImage` block**.
Per master plan §2.4 ("复用 Image 类的 io，然后套个壳加个 metadata") the SRS
ingress path is `LoadImage` → `Image` → `SRSCalibrate` → `SRSImage`. The
calibration block performs the digitizer voltage inversion **and** the type
upgrade in one step.

The spec deliberately ships **no `RamanSpectrum` / `Spectrum` class**. Per
master plan §2.4 ("spectrum 不需要抽象出来，直接用 DF 管理就行了") spectra are
returned as plain `DataFrame` instances from the core type system, with the
`region_id` / `wavenumber_cm1` / `intensity` schema documented per producing
block.

## 2. Scope

**In scope** — files that the implementation cascade is allowed to touch
through the union of all T-SRS tickets:

- `packages/scistudio-blocks-srs/pyproject.toml`
- `packages/scistudio-blocks-srs/README.md`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/__init__.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/types.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocessing/{__init__,calibrate,baseline,denoise,normalize}.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/{__init__,unmix,vca,pca,ica,kmeans}.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/spectral/{__init__,extract,band_ratio}.py`
- `packages/scistudio-blocks-srs/tests/**`

**Out of scope** — explicitly forbidden by this spec, even if the agent thinks
it would help:

- ADR text under `docs/adr/` (already merged — ADR-027, ADR-028, ADR-028
  Addendum 1).
- Other Phase 11 spec docs (`phase11-imaging-block-spec.md`,
  `phase11-lcms-block-spec.md`).
- Architecture docs (`docs/architecture/ARCHITECTURE.md`,
  `docs/architecture/PROJECT_TREE.md`).
- Anything under `src/scistudio/` (core types, engine, blocks, api, frontend).
- The imaging plugin source (`packages/scistudio-blocks-imaging/`) — this spec
  *consumes* it and *depends* on it but does not modify it.
- Reintroducing any of the explicitly removed blocks (see §2.1 below).
- Adding any class to `types.py` other than `SRSImage`.
- Adding any IO block — `LoadImage` from imaging is reused.

### 2.1 Removed blocks (DO NOT re-add)

The user explicitly rejected the following blocks during the master plan
design conversation. They MUST NOT appear in any T-SRS ticket, even as a
"placeholder for future" or "dead code". Any PR that re-introduces one of
these is a scope violation per CLAUDE.md §6.7 / §9.2.

| Removed block            | Category               | User's reason                              |
|--------------------------|------------------------|--------------------------------------------|
| `SRSDespike`             | Preprocessing          | "SRS 没有宇宙射线影响" (no cosmic rays in SRS) |
| `SRSWavenumberCalibrate` | Preprocessing          | "一般系统都是调好的" (systems are pre-calibrated)|
| `SRSMCR_ALS`             | Component analysis     | ALS rejected by user (both for baseline and unmixing) |
| `SRSNMF`                 | Component analysis     | Removed by user                            |
| `PeakFind`               | Spectral extraction    | Removed by user                            |
| `PeakFit`                | Spectral extraction    | Removed by user                            |
| `LipidDropletQuantify`   | SRS-specific measurement | "暂时不用" (not needed for now)            |
| `ProteinLipidRatio`      | SRS-specific measurement | "暂时不用"                                 |
| `WaterContentMap`        | SRS-specific measurement | "暂时不用"                                 |
| `CellDryMassMap`         | SRS-specific measurement | "暂时不用"                                 |

ALS-flavoured baseline correction is also rejected: `SRSBaseline.method` MUST
NOT include `als` as an option. The allowed methods are `polynomial`,
`rubber_band`, `rolling_ball_spectral` only.

### 2.2 Cross-plugin dependency on `scistudio-blocks-imaging`

`scistudio-blocks-srs` depends on `scistudio-blocks-imaging` because:

1. `SRSImage` subclasses `Image` (defined in
   `scistudio_blocks_imaging.types.image`).
2. `SRSCalibrate.input_ports` accepts `Image` (the raw digitizer output) and
   `SRSCalibrate.output_ports` produces `SRSImage` (the calibrated typed
   instance). The Phase 10 port-check accepts the upgrade because `SRSImage`
   is a subclass of `Image`.
3. `ExtractSpectrum.input_ports` consumes `SRSImage` plus optional `Mask` /
   `Label` from imaging.
4. The plugin's `pyproject.toml` declares `scistudio-blocks-imaging>=0.1` as a
   hard runtime dependency.

This is the **first** intentional cross-plugin import in SciStudio. The pattern
is documented here so the LC-MS spec and future plugins can follow it. The
import direction is one-way: `srs` imports from `imaging`, never the reverse.

### 2.3 Package layout

```
packages/scistudio-blocks-srs/
├── pyproject.toml
├── README.md
├── src/scistudio_blocks_srs/
│   ├── __init__.py                  (get_blocks, get_types)
│   ├── types.py                     (SRSImage)
│   ├── preprocessing/{__init__,calibrate,baseline,denoise,normalize}.py
│   ├── component_analysis/{__init__,vca,unmix,pca,ica,kmeans}.py
│   └── spectral/{__init__,extract,band_ratio}.py
└── tests/
    ├── __init__.py, test_types.py, test_package_skeleton.py, test_entry_points.py
    ├── test_preprocessing/{__init__,test_calibrate,test_baseline,test_denoise,test_normalize}.py
    ├── test_component_analysis/{__init__,test_vca,test_unmix,test_pca,test_ica,test_kmeans}.py
    ├── test_spectral/{__init__,test_extract,test_band_ratio}.py
    └── integration/{__init__,conftest,test_e2e_with_imaging}.py
```

## 3. Cross-reference table

| Ticket       | Title                                        | Source ADR / spec section                          |
|--------------|----------------------------------------------|----------------------------------------------------|
| T-SRS-000    | Package skeleton + entry-points              | ADR-025 §3, ADR-028 §D7, master plan §2.4          |
| T-SRS-001    | `SRSImage` type + `Meta` model               | ADR-027 D1, D2, D5, master plan §2.4               |
| T-SRS-002    | `SRSCalibrate` block (digitizer + type)      | ADR-027 D7, ADR-028 §D1, master plan §2.4          |
| T-SRS-003    | `SRSBaseline` block                          | ADR-027 D3, D7                                     |
| T-SRS-004    | `SRSDenoise` block                           | ADR-027 D3, D7                                     |
| T-SRS-005    | `SRSNormalize` block                         | ADR-027 D3, D7                                     |
| T-SRS-006    | `SRSVCA` block                               | ADR-027 D7                                         |
| T-SRS-007    | `SRSUnmix` block (NNLS + auto-VCA fallback)  | ADR-027 D7, master plan §2.4                       |
| T-SRS-008    | `SRSPCA` block                               | ADR-027 D7                                         |
| T-SRS-009    | `SRSICA` block                               | ADR-027 D7                                         |
| T-SRS-010    | `SRSKMeansCluster` block                     | ADR-027 D7                                         |
| T-SRS-011    | `ExtractSpectrum` block                      | ADR-027 D7, imaging spec (Mask/Label types)        |
| T-SRS-012    | `BandRatio` block                            | ADR-027 D7                                         |
| T-SRS-013    | Plugin entry-point wiring + smoke test       | ADR-025 §6, ADR-028 §D7                            |
| T-SRS-014    | E2E integration test (cross-plugin)          | master plan §1 E2E test, imaging spec §11          |

## 4. Dependency graph

```
                    T-SRS-000 (package skeleton)
                          │
                          ▼
                    T-SRS-001 (SRSImage type)
                          │
                          ▼
                    T-SRS-002 (SRSCalibrate)
                          │
        ┌─────────────────┼───────────────────┐
        ▼                 ▼                   ▼
   T-SRS-003          T-SRS-004           T-SRS-005
   (Baseline)         (Denoise)           (Normalize)
        │                 │                   │
        └────────┬────────┴────────┬──────────┘
                 ▼                 ▼
          T-SRS-006             T-SRS-008
          (VCA)                 (PCA)
                 │                 │
                 ▼                 ▼
          T-SRS-007             T-SRS-009
          (Unmix; uses VCA)     (ICA)
                 │                 │
                 └────────┬────────┘
                          ▼
                    T-SRS-010 (KMeans)
                          │
                          ▼
                    T-SRS-011 (ExtractSpectrum)
                          │
                          ▼
                    T-SRS-012 (BandRatio)
                          │
                          ▼
                    T-SRS-013 (entry-point wiring)
                          │
                          ▼
                    T-SRS-014 (E2E with imaging)
```

T-SRS-000 must merge first because every other ticket adds files inside the
package layout it creates. T-SRS-001 must merge before any block ticket
because every block annotates `input_ports` / `output_ports` with `SRSImage`.
T-SRS-002 must merge before any other preprocessing ticket because the test
fixtures the other blocks consume are `SRSImage` instances produced by the
calibration path. T-SRS-003 / T-SRS-004 / T-SRS-005 are mutually independent
once T-SRS-002 has merged. T-SRS-006 (VCA) must merge before T-SRS-007
(Unmix) because Unmix calls into VCA when no reference spectra are supplied.
T-SRS-013 must merge after every block ticket because the entry-point
registration imports them all in `get_blocks()`. T-SRS-014 is the capstone
and depends on the entire plugin plus the imaging plugin's `CellposeSegment`
ticket having landed.

Implementation status note (2026-04-08): T-SRS-001 merged in PR #367. The
dependency-root preprocess chain T-SRS-002..005 is implemented in PR #380.
Component analysis T-SRS-006 (`SRSVCA`), T-SRS-007 (`SRSUnmix`), T-SRS-008
(`SRSPCA`), T-SRS-009 (`SRSICA`), and T-SRS-010 (`SRSKMeansCluster`) are
implemented in PR #387 (issue #385). Spectral_extraction (T-SRS-011/012),
packaging (T-SRS-013/014), and the E2E capstone remain.

## 5. Recommended chained PR order

Each PR's base branch is the previous merged PR's branch (stacked PRs). When
the previous PR has already merged into `main`, base off `main` directly.
Mark stacked PRs with the previous PR number in the description.

1. **T-SRS-000** — Package skeleton + entry-points (independent)
2. **T-SRS-001** — `SRSImage` type
3. **T-SRS-002** — `SRSCalibrate` block
4. **T-SRS-003** — `SRSBaseline` block
5. **T-SRS-004** — `SRSDenoise` block
6. **T-SRS-005** — `SRSNormalize` block
7. **T-SRS-006** — `SRSVCA` block
8. **T-SRS-007** — `SRSUnmix` block (depends on T-SRS-006)
9. **T-SRS-008** — `SRSPCA` block
10. **T-SRS-009** — `SRSICA` block
11. **T-SRS-010** — `SRSKMeansCluster` block
12. **T-SRS-011** — `ExtractSpectrum` block
13. **T-SRS-012** — `BandRatio` block
14. **T-SRS-013** — Plugin entry-point wiring + smoke test
15. **T-SRS-014** — E2E integration test (cross-plugin)

If parallel work is desired: T-SRS-003 / T-SRS-004 / T-SRS-005 can be opened
simultaneously off T-SRS-002. T-SRS-008 / T-SRS-009 / T-SRS-010 can also
parallelise once T-SRS-002 has merged. Sequential preserves a clean stack.

## 6. Universal rules for all SRS implementation agents

These rules apply to **every** ticket in this document. Failure to follow
them is a workflow gate violation per CLAUDE.md Appendix A.

1. **Workflow gate is mandatory** — every ticket follows the full 6-stage
   workflow gate per `CLAUDE.md` Appendix A. No exceptions for "small"
   tickets. Each stage must show `[DONE]` in
   `python .workflow/gate.py status <task_id>` before the next stage begins.
2. **Branch naming**: `feat/issue-N/T-SRS-NNN-short-name`. Example:
   `feat/issue-301/T-SRS-002-srs-calibrate`.
3. **Stacked PR base** — each PR's base branch is the previous merged PR's
   branch. If the previous PR has already merged into `main`, base off `main`
   directly. The PR description MUST mention the previous PR number when
   stacked.
4. **Out-of-scope changes are forbidden** — the PR's diff must contain only
   the files listed in the ticket's "Files to be created", "Files to be
   modified", "New tests", and "Existing tests to update" sections. Any other
   modified file is a scope violation per `CLAUDE.md` §6.7. The §2.1 removed
   blocks list MUST NOT be re-introduced.
5. **Every check must be green before review**:
   - `pytest -x --no-cov` passes locally inside
     `packages/scistudio-blocks-srs/`.
   - `ruff check` clean over the package source and tests.
   - `ruff format --check` clean.
   - `mypy --ignore-missing-imports` clean.
   - The plugin imports cleanly with both `scistudio` and
     `scistudio-blocks-imaging` installed (T-SRS-013 adds an importability
     smoke test that the entry-point scan succeeds).
6. **CHANGELOG.md** must be updated under `[Unreleased]` in the appropriate
   section (`Added` / `Changed` / `Fixed`) with full attribution per
   `CLAUDE.md` Appendix A Stage 6:
   `[#N] Description (@agent, YYYY-MM-DD, branch: BRANCH, session: TASK_ID)`.
7. **PR body must reference**:
   - The locked block list section in `phase11_master_plan.md` §2.4.
   - The ticket ID from this spec doc (e.g. "Per
     `docs/specs/phase11-srs-block-spec.md` T-SRS-002").
   - The previous PR in the stack (if any).
   - A reproduction of the ticket's acceptance criteria as a checklist with
     each box ticked when satisfied.
8. **No silent scope expansion** — if implementing a ticket reveals a
   pre-existing bug, ambiguity, or unspoken requirement, open a *new issue*
   describing it. Do not fix it inline. Per `CLAUDE.md` §9.2 ("Claude must
   not silently broaden scope") and the master plan §5 audit-agent rules
   ("type relaxation", "assertion removal", "test expectation rewrite",
   "scope argument shrinkage" red flags).
9. **No new types** — `SRSImage` is the only class added to `types.py`. No
   `RamanSpectrum`, no `Spectrum`, no `Spectra`, no `EndmemberMatrix`. Spectra
   are `DataFrame`. Endmember tables are `DataFrame`.
10. **No new IO blocks** — the package has zero `IOBlock` subclasses. The
    SRS ingress path reuses the imaging plugin's `LoadImage`. The egress path
    reuses imaging's `SaveImage` for `SRSImage` (subclass-compatible) and
    core's `SaveData` (post ADR-028 Addendum 1) for `DataFrame` outputs.
11. **Cross-plugin imports are one-way** — `scistudio-blocks-srs` imports from
    `scistudio_blocks_imaging` (specifically the `Image` / `Mask` / `Label`
    types). The reverse (imaging importing from srs) is forbidden and would
    be flagged by the audit agent.
12. **Lambda axis is mandatory** — `SRSImage.required_axes = frozenset({"y",
    "x", "lambda"})`. Every block in this package uses
    `has_axes("y", "x", "lambda")` from `scistudio.utils.constraints` (T-010,
    Phase 10) on its input port to enforce that the spectral dimension is
    present. Blocks that operate per-pixel along the spectral axis use
    `iterate_over_axes(operates_on={"lambda"}, ...)`; blocks that operate
    per-spectrum along the spatial axes use
    `iterate_over_axes(operates_on={"y", "x"}, ...)`; blocks that need both
    use `operates_on={"lambda", "y", "x"}` and iterate over the remaining
    axes (`t`, `z`, `c` if present).

## 7. Universal acceptance criteria (apply to ALL T-SRS tickets)

In addition to each ticket's own acceptance criteria, every ticket must
satisfy these:

1. The PR's diff includes ONLY files listed in "Files to be created", "Files
   to be modified", "New tests", and "Existing tests to update" for that
   ticket. Any other modified file is a scope violation.
2. `pytest -x --no-cov` passes locally inside the plugin package before push.
3. `ruff check src/ tests/` clean.
4. `ruff format --check src/ tests/` clean.
5. `mypy src/ --ignore-missing-imports` clean.
6. `CHANGELOG.md` has an entry under `[Unreleased]` in the appropriate
   section with full attribution per `CLAUDE.md` Appendix A Stage 6.
7. Workflow gate has all 6 stages `[DONE]`.
8. PR body explicitly references the master plan §2.4 SRS PLUGIN section and
   links to this spec doc by ticket ID.
9. PR body reproduces the ticket's per-ticket acceptance criteria as a
   checklist with each item ticked.
10. CI is green on the PR before requesting review.
11. The block class declares `name`, `description`, `version`, `category`,
    `input_ports`, `output_ports`, `config_schema`, and either
    `process_item(self, item, config, state)` or an explicit `run` override.
12. The block class is **importable** without `scistudio_blocks_imaging`
    raising — every block module that subclasses an imaging type does so via
    a top-level import that fails fast at import time with a clear message
    if the imaging plugin is missing.

## 8. Open questions resolved by this document

These are decisions made in this document that go *beyond* the locked master
plan §2.4 contract. The master plan deferred them to the implementation
phase; this section records the resolution so subsequent agents do not have
to re-litigate.

### Question 1: How does `SRSCalibrate` handle an already-calibrated `Image`?

The block produces `SRSImage` via digitizer inversion. Chaining two
`SRSCalibrate` blocks would silently corrupt data by re-inverting signal
values. **Decision: detect by Meta, backed by type check.** The block
accepts the `Image` superclass on its input port (the first call is on
a raw `Image` from `LoadImage`). Inside `process_item`, the block runs
two guards in order:

1. `isinstance(item, SRSImage)` → raise `ValueError("…chained two
   SRSCalibrate blocks?")`.
2. `item.meta is not None and getattr(item.meta, "digitizer_bit_depth",
   None) is not None` → raise `ValueError("…digitizer fields already
   populated…")`.

Together they cover the cross-pickle case where a user saved and
reloaded an SRSImage as a generic Image.

### Question 2: What happens when `c` (discrete channel) and `lambda` coexist?

`SRSImage.allowed_axes` is inherited from `Image.allowed_axes`, so an
instance with both `c` and `lambda` axes is structurally valid (rare
multi-detector SRS setups). **Decision: process per-channel**. Every
preprocessing and component-analysis block reshapes via `np.moveaxis`
to push lambda to the last dimension and flatten to `(n_pixels, n_w)`,
which transparently broadcasts over any number of leading dims (`t`,
`z`, `c`). The blocks that need explicit slice control instead call
`iterate_over_axes(item, operates_on={"lambda", "y", "x"}, func=...)`
from ADR-027 D3. Tests for each block include a 5D `(t, c, lambda, y,
x)` input case to verify the broadcast works.

### Question 3: What output format does `ExtractSpectrum` use?

**Decision: long format** with columns
`(region_id, wavenumber_cm1, intensity)`, one row per `(region,
wavenumber)` pair. Justification: long format generalises to any number
of regions without changing the schema, matches tidy-data conventions
that most plotting and statistics libraries expect, and a user who
wants wide format can call `df.pivot(index="wavenumber_cm1",
columns="region_id", values="intensity")` in a one-line CodeBlock.

The `region_id` value `0` is reserved for the "whole image, no ROI"
case (neither labels nor mask supplied). A `mask` input produces
`region_id == 1`. A `labels` input emits one row block per label value
> 0; label 0 is the background and is excluded.

### Question 4: Does `SRSUnmix` auto-detect reference spectra if none are supplied?

**Decision: yes — fall through to internal VCA.** The user's typical
workflow is "I don't have reference spectra; estimate them from the
data", and forcing them to chain `SRSVCA` → `SRSUnmix` for the common
case doubles the workflow node count. When the optional `references`
input port is empty, the block imports the module-level
`_extract_endmembers` helper from
`scistudio_blocks_srs.component_analysis.vca` directly (clean test seam,
no class instantiation), runs it with `auto_vca_n_components` from
config (default 4), and uses the returned matrix as the NNLS basis.
A runtime info log line `"SRSUnmix: no references provided, extracting
{n} endmembers via SRSVCA."` makes the fallback visible. When
references *are* provided, the `auto_vca_n_components` config field is
ignored.

### Question 5: How does `SRSKMeansCluster` shape its features?

K-means needs a 2D feature matrix. The SRS image is at minimum 3D
`(lambda, y, x)`. Two options:

- **(A) Spectral features**: each pixel contributes one row of length
  `n_wavenumbers`, the total feature matrix is `(n_pixels, n_wavenumbers)`,
  cluster IDs are reshaped back to a 2D `(y, x)` `Label` raster.
- **(B) Spatial features**: each wavenumber slice contributes one row of
  length `n_pixels` — useful for clustering wavenumbers, not pixels.

**Decision: (A).** This is what the user means by "k-means over pixel
spectra". The feature dimension is the spectral one. The block reshapes
the input via `np.moveaxis` to push lambda to the last axis, then
flattens to `(n_pixels, n_wavenumbers)`, runs `sklearn.cluster.KMeans`,
reshapes the cluster IDs back to a 2D `(y, x)` raster, and emits a
`Label` composite with that raster.

The output `Label` raster has cluster IDs starting at 0 (k-means
convention) and ranging through `n_clusters - 1`. The `centroids`
DataFrame has `cluster_id` as the index and `wavenumber_cm1` as the
columns.

### Question 6: What is the default method for `SRSBaseline`?

**Decision: `polynomial` with `order=3`.** Polynomial subtraction is
the most numerically robust on the CH-stretch region (2800–3000 cm⁻¹)
which dominates SRS biological imaging, and it is the cheapest to
compute (`numpy.polyfit` per spectrum). `rubber_band` and
`rolling_ball_spectral` remain available via the `method` config
parameter. The schema declares `method: str = "polynomial"`,
`order: int = 3` (used by polynomial), `window: int = 50` (used by
rolling_ball_spectral); rubber_band consumes neither but the fields
are accepted for config-schema simplicity.

## 9. Per-ticket sections

Each section uses the same 12 subsections:

a. Ticket ID and name
b. Source ADR / spec sections
c. Files to be created
d. Files to be modified
e. New tests
f. Existing tests to update
g. Implementation details
h. Acceptance criteria
i. Out of scope
j. Dependencies on other tickets
k. Estimated diff size
l. Suggested workflow gate ticket title

---

### T-SRS-000 — Package skeleton + entry-points

**a. Ticket ID and name**: T-SRS-000 — `scistudio-blocks-srs` package skeleton.

**b. Source ADR / spec sections**: ADR-025 §3 (plugin distribution),
ADR-028 §D7 (plugin IO blocks register via `scistudio.blocks` entry-point
group), master plan §2.4 (locked package layout).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/pyproject.toml`
- `packages/scistudio-blocks-srs/README.md`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/__init__.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/types.py` (placeholder)
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocessing/__init__.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/__init__.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/spectral/__init__.py`
- `packages/scistudio-blocks-srs/tests/__init__.py`
- `packages/scistudio-blocks-srs/tests/test_package_skeleton.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_package_skeleton.py`, 6 tests):
`test_pyproject_declares_correct_dependencies` (asserts `scistudio>=0.1`
and `scistudio-blocks-imaging>=0.1`),
`test_pyproject_declares_block_entrypoint`,
`test_pyproject_declares_type_entrypoint`,
`test_package_root_importable`,
`test_get_blocks_callable_exists` (returns `[]` in T-SRS-000),
`test_get_types_callable_exists` (returns `[]` in T-SRS-000).

**f. Existing tests to update**: none.

**g. Implementation details**:

**`pyproject.toml`** uses the `hatchling` backend and declares:

- `name = "scistudio-blocks-srs"`, `version = "0.1.0"`,
  `requires-python = ">=3.11"`.
- Runtime dependencies: `scistudio>=0.1`, `scistudio-blocks-imaging>=0.1`,
  `numpy>=1.24`, `scipy>=1.11`, `scikit-learn>=1.3`, `pydantic>=2.5`.
- Optional dependencies: `bm4d = ["bm4d>=4.0"]`,
  `pywt = ["PyWavelets>=1.5"]`,
  `dev = ["pytest>=8.0", "ruff>=0.4", "mypy>=1.10"]`.
- Entry-point group `scistudio.blocks`: `srs =
  "scistudio_blocks_srs:get_blocks"`.
- Entry-point group `scistudio.types`: `srs =
  "scistudio_blocks_srs.types:get_types"`.
- `[tool.hatch.build.targets.wheel] packages = ["src/scistudio_blocks_srs"]`.

**`src/scistudio_blocks_srs/__init__.py`** ships a docstring summarising
the package contents (one type, 4 preprocessing blocks, 5 component
analysis blocks, 2 spectral blocks, no IOBlock subclasses, no spectrum
class) and two functions:

- `get_blocks() -> list[type]` — returns `[]` in T-SRS-000, populated
  by T-SRS-013.
- `get_types() -> list[type]` — returns `[]` in T-SRS-000, populated
  by T-SRS-001 (and re-exported via `types.py`).

**`src/scistudio_blocks_srs/types.py`** is a one-function placeholder
whose `get_types()` returns `[]`. T-SRS-001 replaces it with the real
`SRSImage` definition and the populated `get_types()`.

**`README.md`** is a 30-line stub that points at this spec.

**h. Acceptance criteria**:
- [ ] `packages/scistudio-blocks-srs/` directory exists with the layout
      described in §2.3.
- [ ] `python -m pip install packages/scistudio-blocks-srs/` succeeds in a
      clean virtual environment.
- [ ] `python -c "import scistudio_blocks_srs; print(scistudio_blocks_srs.get_blocks())"`
      prints `[]`.
- [ ] `python -c "from scistudio_blocks_srs.types import get_types; print(get_types())"`
      prints `[]`.
- [ ] Both entry-point groups (`scistudio.blocks`, `scistudio.types`) appear in
      `importlib.metadata.entry_points()` after install.
- [ ] All 6 skeleton tests pass.

**i. Out of scope**:
- Implementing any block.
- Implementing the `SRSImage` type (T-SRS-001).
- Adding the package to a top-level workspace `pyproject.toml` — that is
  master-repo work tracked in a separate ticket.

**j. Dependencies**: none.

**k. Estimated diff size**: ~150 lines across pyproject + skeleton init
files + 6 tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-000 package
skeleton + entry-points`.

---

### T-SRS-001 — `SRSImage` type + `Meta` model

**a. Ticket ID and name**: T-SRS-001 — `SRSImage` type and `Meta` Pydantic
model.

**b. Source ADR / spec sections**: ADR-027 D1 (instance-level axes), D2
(domain types live in plugins), D5 (stratified Pydantic metadata), master
plan §2.4 (locked Meta field list).

**c. Files to be created**: none beyond what T-SRS-000 created.

**d. Files to be modified**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/types.py` — replace the
  placeholder with the full `SRSImage` class and the `get_types` body.
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/__init__.py` — re-export
  `SRSImage` for ergonomics.
- `packages/scistudio-blocks-srs/tests/test_types.py` — new file with the type
  tests.

**e. New tests** (`tests/test_types.py`, ~14 tests):
`test_srsimage_subclass_of_image`,
`test_srsimage_required_axes` (asserts `frozenset({"y","x","lambda"})`),
`test_srsimage_inherits_allowed_axes_from_image`,
`test_srsimage_canonical_order`,
`test_srsimage_construct_minimal` (3D `(lambda, y, x)`),
`test_srsimage_construct_5d` (`(t, c, lambda, y, x)`),
`test_srsimage_missing_lambda_raises` (validates the
`Array._validate_axes` message),
`test_srsimage_meta_default_none`,
`test_srsimage_meta_with_wavenumbers` (round-trips through
`model_dump_json`),
`test_srsimage_meta_with_digitizer_fields` (round-trips all four),
`test_srsimage_meta_laser_power_float` (mW; documents the future
`PhysicalQuantity` upgrade),
`test_srsimage_meta_with_integration_time` (uses `_TIME` units),
`test_srsimage_meta_pump_stokes_wavelengths`,
`test_srsimage_with_meta_immutable_update` (ADR-027 D5),
`test_srsimage_in_type_registry_after_scan` (resolves the full type
chain).

**f. Existing tests to update**: none (T-SRS-000 tests still pass; the new
file additions do not break them).

**g. Implementation details**:

`SRSImage` is defined in
`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/types.py` and
imports `Image` from `scistudio_blocks_imaging.types` at module top
(fail-fast if the imaging plugin is missing).

**Class declaration**:

- `class SRSImage(Image):` — single inheritance.
- `required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x",
  "lambda"})` — tightens `Image.required_axes = {y, x}` to also require
  the spectral axis.
- `allowed_axes` is **inherited** from `Image` (no override) so any
  combination of `{t, z, c, lambda, y, x}` is structurally valid as
  long as `{y, x, lambda}` is present.
- `canonical_order: ClassVar[tuple[str, ...]] = ("t", "z", "c",
  "lambda", "y", "x")` — inherits the imaging-spec convention.

**Inner `Meta` class** subclasses `Image.Meta` (which already provides
`pixel_size`, `channels`, `objective`, `acquisition_date`, ...). It
adds nine fields, all with `None` defaults, frozen via
`model_config = ConfigDict(frozen=True, extra="forbid")`:

| Field                     | Type                       | Notes |
|---------------------------|----------------------------|-------|
| `wavenumbers_cm1`         | `list[float] \| None`      | Length must match the lambda axis size when set. |
| `laser_power`             | `float \| None`            | mW. Stored as float because the Phase 10 PhysicalQuantity unit table has no power kind; a future addendum may upgrade. |
| `integration_time`        | `PhysicalQuantity \| None` | Time kind (us, ms, s). |
| `digitizer_bit_depth`     | `int \| None`              | Set by `SRSCalibrate`. |
| `digitizer_voltage_range` | `float \| None`            | Set by `SRSCalibrate`. |
| `digitizer_offset`        | `float \| None`            | Set by `SRSCalibrate`. |
| `digitizer_scale`         | `float \| None`            | Set by `SRSCalibrate`. |
| `pump_wavelength_nm`      | `float \| None`            | Optical setup. |
| `stokes_wavelength_nm`    | `float \| None`            | Optical setup. |

**Module-level `get_types()`** returns `[SRSImage]` so the entry-point
scan picks up exactly one class.

**h. Acceptance criteria**:
- [ ] `SRSImage` is defined in `types.py` and inherits from
      `scistudio_blocks_imaging.types.Image`.
- [ ] `SRSImage.required_axes == frozenset({"y", "x", "lambda"})`.
- [ ] `SRSImage.canonical_order == ("t", "z", "c", "lambda", "y", "x")`.
- [ ] `SRSImage.Meta` is a frozen Pydantic v2 BaseModel that subclasses
      `Image.Meta` and adds the nine fields locked in master plan §2.4.
- [ ] `SRSImage.Meta` round-trips through `model_dump_json` /
      `model_validate_json`.
- [ ] `get_types()` returns `[SRSImage]`.
- [ ] After `TypeRegistry.scan()`, the type chain `["DataObject", "Array",
      "Image", "SRSImage"]` resolves to `SRSImage`.
- [ ] All 14 tests in `test_types.py` pass.

**i. Out of scope**:
- Adding any other type. No `RamanSpectrum`, no `Spectrum`, no
  `EndmemberMatrix`.
- Modifying `Image.Meta` in the imaging plugin (out of plugin scope).
- Implementing any block (later tickets).

**j. Dependencies**: T-SRS-000 (skeleton), and the imaging plugin's `Image`
class (assumed merged via the imaging spec's T-IMG-001 ticket).

**k. Estimated diff size**: ~120 lines across `types.py` (~80) + tests (~40).

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-001 SRSImage
type with Meta`.

---

### T-SRS-002 — `SRSCalibrate` block

**a. Ticket ID and name**: T-SRS-002 — `SRSCalibrate` digitizer inversion +
type conversion block.

**b. Source ADR / spec sections**: ADR-027 D7 (`ProcessBlock` setup/teardown
hooks), ADR-028 §D1 (typed plugin blocks), §8 Question 1 (re-run detection),
master plan §2.4 (locked digitizer formula and parameter set).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocessing/calibrate.py`

**d. Files to be modified**: none beyond the new file.

**e. New tests** (`tests/test_preprocessing/test_calibrate.py`, ~12 tests):
`test_calibrate_smoke_minimal`,
`test_calibrate_inversion_formula` (verifies `(pixel/4096*10 - 0)/1`
element-wise on a known input),
`test_calibrate_offset_nonzero`,
`test_calibrate_scale_nonzero`,
`test_calibrate_meta_populated`,
`test_calibrate_wavenumbers_passthrough`,
`test_calibrate_rejects_srsimage_input` (Question 1 §8),
`test_calibrate_rejects_image_with_digitizer_meta`,
`test_calibrate_5d_input_with_c_axis`,
`test_calibrate_lambda_axis_required`,
`test_calibrate_collection_input`,
`test_calibrate_dtype_float32`.

**f. Existing tests to update**: none.

**g. Implementation details**:

The block subclasses `ProcessBlock` and overrides `process_item` only
(not `run`). Class-level declarations:

- `name = "SRS Calibrate"`, `category = "preprocessing"`,
  `version = "0.1.0"`.
- `input_ports = [InputPort("image", accepted_types=[Image],
  constraint=has_axes("y","x","lambda"))]` — accepts the imaging-plugin
  base class so the very first call (right after `LoadImage`) succeeds.
- `output_ports = [OutputPort("srs_image", accepted_types=[SRSImage])]`.
- `config_schema` declares `bit_depth: int = 4096`, `voltage_range:
  float = 10.0`, `offset: float = 0.0`, `scale: float = 1.0`, and
  `wavenumbers_cm1: list[float] | None = None`.

`process_item(self, item, config, state)` body:

1. **Reject double-calibration** (per §8 Question 1):
   - if `isinstance(item, SRSImage)` → `raise ValueError("…chained two
     SRSCalibrate blocks?")`.
   - elif `item.meta is not None and
     getattr(item.meta, "digitizer_bit_depth", None) is not None` →
     `raise ValueError("…digitizer fields already populated…")`.
2. Reject `scale == 0` with a clear `ValueError`.
3. `pixel = np.asarray(item).astype(np.float64)`.
4. `signal = (pixel / bit_depth * voltage_range - offset) / scale`.
5. Cast to `float32`.
6. If `wavenumbers_cm1` is supplied, assert
   `len(wavenumbers_cm1) == item.shape[item.axes.index("lambda")]`,
   else raise.
7. Construct `new_meta = SRSImage.Meta(**old_meta_dump,
   wavenumbers_cm1=…, digitizer_bit_depth=…, digitizer_voltage_range=…,
   digitizer_offset=…, digitizer_scale=…)`. The `**old_meta_dump`
   preserves any inherited Image.Meta fields (pixel_size, channels,
   acquisition_date, …).
8. Construct and return `SRSImage(axes=item.axes, shape=signal.shape,
   dtype=np.float32, framework=item.framework.derive(), meta=new_meta,
   user=dict(item.user), storage_ref=None)`. Stash `out._data = signal`
   so downstream `to_memory()` short-circuits to memory (matches the
   pattern T-006 established for `Array.sel`).

The OptEasy reference `srs_calibration.py` uses the same formula but
returns a typed `OpteasyImage`. The SciStudio version differs only in
returning `SRSImage` and populating the typed `Meta` model rather than
a free dict.

**h. Acceptance criteria**:
- [ ] Block class declares `name`, `description`, `version`, `category =
      "preprocessing"`, `input_ports`, `output_ports`, `config_schema`.
- [ ] `input_ports[0].constraint` enforces `has_axes("y", "x", "lambda")`.
- [ ] `process_item` raises `ValueError` when handed an `SRSImage`.
- [ ] `process_item` raises `ValueError` when handed an `Image` whose
      `meta.digitizer_bit_depth is not None`.
- [ ] Output dtype is always `float32`.
- [ ] Output meta carries the four digitizer parameters and optional
      `wavenumbers_cm1`.
- [ ] All 12 tests pass.
- [ ] Universal acceptance criteria §7 met.

**i. Out of scope**:
- Wavenumber calibration / fitting (`SRSWavenumberCalibrate` was removed).
- Despiking (`SRSDespike` was removed).

**j. Dependencies**: T-SRS-001 (`SRSImage` type).

**k. Estimated diff size**: ~250 lines source + ~150 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-002
SRSCalibrate digitizer + type conversion`.

---

### T-SRS-003 — `SRSBaseline` block

**a. Ticket ID and name**: T-SRS-003 — `SRSBaseline` spectral baseline
correction.

**b. Source ADR / spec sections**: ADR-027 D3 (`iterate_over_axes`), D7
(`ProcessBlock` setup/teardown), §8 Question 6 (default `polynomial`
order=3).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocessing/baseline.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_preprocessing/test_baseline.py`, ~10 tests):
`test_baseline_smoke_polynomial`,
`test_baseline_default_method_is_polynomial` (verifies
`method=polynomial`, `order=3` defaults),
`test_baseline_polynomial_order_param`,
`test_baseline_rubber_band_smoke`,
`test_baseline_rolling_ball_spectral_smoke`,
`test_baseline_rejects_als_method` (asserts `method="als"` raises with
a message naming the three accepted methods),
`test_baseline_unknown_method_raises`,
`test_baseline_5d_with_c_axis_iterates`,
`test_baseline_preserves_meta`,
`test_baseline_dtype_float32`.

**f. Existing tests to update**: none.

**g. Implementation details**:

`SRSBaseline(ProcessBlock)` declares:

- `name = "SRS Baseline Correct"`, `category = "preprocessing"`.
- `input_ports = [InputPort("image", accepted_types=[SRSImage],
  constraint=has_axes("y","x","lambda"))]`.
- `output_ports = [OutputPort("image", accepted_types=[SRSImage])]`.
- `config_schema` declares
  `method: enum["polynomial","rubber_band","rolling_ball_spectral"] =
  "polynomial"`, `order: int = 3`, `window: int = 50`.

Module-level constant `_ALLOWED_METHODS = ("polynomial", "rubber_band",
"rolling_ball_spectral")`. The block raises `ValueError` for any other
method, including `"als"`, with a message that explicitly names the
three accepted values and notes that ALS is intentionally unsupported.

Three private helper functions, each operating on an `(..., n_w)`
ndarray with `lambda` already moved to the last axis:

- `_baseline_polynomial(spec, order)` — `numpy.polyfit` per pixel of
  `flat = spec.reshape(-1, n_w)`, subtract the fitted polynomial,
  reshape back. O(n_pixels × n_w) work.
- `_baseline_rubber_band(spec)` — convex-hull lower envelope per pixel
  via `scipy.spatial.ConvexHull`; subtract the interpolated baseline.
- `_baseline_rolling_ball(spec, window)` — `scipy.ndimage.grey_opening`
  with `size=window` along the spectral axis per pixel.

`process_item` body:

1. Validate method via the `_ALLOWED_METHODS` membership check.
2. `lambda_pos = item.axes.index("lambda")`.
3. `moved = np.moveaxis(np.asarray(item), lambda_pos, -1)`.
4. Dispatch to the relevant private helper.
5. `out_data = np.moveaxis(result, -1, lambda_pos).astype(np.float32)`.
6. Construct `SRSImage(axes=item.axes, shape=out_data.shape,
   dtype=np.float32, framework=item.framework.derive(), meta=item.meta,
   user=dict(item.user), storage_ref=None)` with `out._data = out_data`.

The `np.moveaxis` reshape pattern transparently broadcasts over any
extra axes (`t`, `z`, `c`), satisfying §8 Question 2 without an explicit
`iterate_over_axes` call — the helpers see `(..., n_w)` and operate per
spectrum regardless of how many leading dims there are.

**h. Acceptance criteria**:
- [ ] `method` enum is exactly `{"polynomial", "rubber_band",
      "rolling_ball_spectral"}` — ALS not present.
- [ ] Default `method="polynomial"`, `order=3`.
- [ ] `process_item` raises `ValueError` for any other method including
      `"als"`.
- [ ] Output preserves `item.meta` and `item.user`.
- [ ] 5D inputs with extra `c` axis succeed (broadcast handled internally
      via the `np.moveaxis` reshape — the per-spectrum helpers operate on
      the leading dimensions transparently).
- [ ] All 10 tests pass.

**i. Out of scope**:
- ALS variants.
- Wavenumber-aware baseline (using wavenumbers_cm1 as the polynomial x
  axis instead of integer indices) — defer to a follow-up if needed.

**j. Dependencies**: T-SRS-001, T-SRS-002.

**k. Estimated diff size**: ~250 lines source + ~120 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-003 SRSBaseline
spectral baseline`.

---

### T-SRS-004 — `SRSDenoise` block

**a. Ticket ID and name**: T-SRS-004 — `SRSDenoise` spatio-spectral
denoising.

**b. Source ADR / spec sections**: ADR-027 D3, D7. Master plan §2.4
(method enum locked).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocessing/denoise.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_preprocessing/test_denoise.py`, ~10 tests):
`test_denoise_smoke_pca`,
`test_denoise_smoke_svd_truncation`,
`test_denoise_smoke_wavelet` (skipped via `pytest.importorskip("pywt")`),
`test_denoise_smoke_bm4d` (skipped via `pytest.importorskip("bm4d")`),
`test_denoise_unknown_method_raises`,
`test_denoise_n_components_validation` (`n_components > n_wavenumbers`
raises),
`test_denoise_meta_preserved`,
`test_denoise_dtype_float32`,
`test_denoise_5d_with_c`,
`test_denoise_pca_reduces_noise` (synthetic Gaussian noise: PCA RMS
error below input noise RMS).

**f. Existing tests to update**: none.

**g. Implementation details**:

`SRSDenoise(ProcessBlock)` declares:

- `name = "SRS Denoise"`, `category = "preprocessing"`.
- `input_ports = [InputPort("image", accepted_types=[SRSImage],
  constraint=has_axes("y","x","lambda"))]`.
- `output_ports = [OutputPort("image", accepted_types=[SRSImage])]`.
- `config_schema` declares
  `method: enum["wavelet","PCA_denoise","SVD_truncation","BM4D"] =
  "PCA_denoise"`, `n_components: int = 10`, `wavelet: str = "db4"`.

`process_item` body:

1. Validate `n_components <= item.shape[item.axes.index("lambda")]`,
   else raise.
2. Move `lambda` to the last axis, reshape to `flat = (n_pixels, n_w)`
   (float64).
3. Dispatch on `method`:
   - **PCA_denoise**: `sklearn.decomposition.PCA(n_components).fit_transform`
     then `inverse_transform`.
   - **SVD_truncation**: `numpy.linalg.svd(flat, full_matrices=False)`,
     zero singular values past `n_components`, reconstruct via
     `U @ diag(s) @ Vt`.
   - **wavelet**: `import pywt` (optional dep — wrap in `try/except
     ImportError` and re-raise as `ValueError("install pywt extra")`).
     Per spectrum: `wavedec` with `level=3`, soft threshold using the
     universal threshold `sigma * sqrt(2 ln N)` where
     `sigma = median(|cd|) / 0.6745`, then `waverec`.
   - **BM4D**: `import bm4d` (optional dep, same wrap-and-raise).
     Call `bm4d.bm4d(cube, sigma_psd=0.1)` on the 3D cube directly.
   - any other value → `ValueError`.
4. Reshape and `np.moveaxis` back, cast to float32.
5. Return new `SRSImage` with `out._data = recon` and inherited
   framework/meta/user.

The optional dependencies are declared in the package's
`[project.optional-dependencies]` section as `pywt` and `bm4d`. Tests
for these methods use `pytest.importorskip` to skip cleanly when the
extras are not installed.

**h. Acceptance criteria**:
- [ ] All four methods present in the enum.
- [ ] PCA / SVD methods always available; wavelet and BM4D guarded by
      ImportError → ValueError with a "pip install scistudio-blocks-srs[pywt|bm4d]"
      hint.
- [ ] `n_components > n_wavenumbers` raises.
- [ ] Output dtype float32; meta preserved.
- [ ] All 10 tests pass.

**i. Out of scope**:
- Anisotropic diffusion, NLM, total variation — not in master plan list.

**j. Dependencies**: T-SRS-001, T-SRS-002.

**k. Estimated diff size**: ~250 lines source + ~150 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-004 SRSDenoise
spatio-spectral denoising`.

---

### T-SRS-005 — `SRSNormalize` block

**a. Ticket ID and name**: T-SRS-005 — `SRSNormalize` intensity normalization.

**b. Source ADR / spec sections**: ADR-027 D3, D7. Master plan §2.4
(method enum locked).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocessing/normalize.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_preprocessing/test_normalize.py`, ~9 tests):
`test_normalize_snv` (asserts row mean ≈ 0, std ≈ 1),
`test_normalize_msc` (synthetic offset/slope corrected),
`test_normalize_vector` (asserts L2 norm ≈ 1 per pixel),
`test_normalize_area` (asserts row sum ≈ 1),
`test_normalize_peak_area_with_reference_peak`,
`test_normalize_peak_area_requires_wavenumbers` (raises when meta
missing wavenumbers),
`test_normalize_unknown_method_raises`,
`test_normalize_meta_preserved`,
`test_normalize_dtype_float32`.

**f. Existing tests to update**: none.

**g. Implementation details**:

`SRSNormalize(ProcessBlock)` declares:

- `name = "SRS Normalize"`, `category = "preprocessing"`.
- Standard `SRSImage` in/out ports with the `has_axes("y","x","lambda")`
  constraint.
- `config_schema` declares
  `method: enum["SNV","MSC","vector","area","peak_area"] = "SNV"` and
  `reference_peak_cm1: float | None = None`.

`process_item` reshapes to `flat = (n_pixels, n_w)` (float64) the same
way `SRSBaseline` does, then dispatches:

- **SNV** (Standard Normal Variate): per row, subtract row mean,
  divide by row std (`+ 1e-12` epsilon).
- **MSC** (Multiplicative Scatter Correction): compute the column-mean
  reference spectrum once. Per row: `slope, intercept = np.polyfit(mean,
  row, 1)`; corrected row = `(row - intercept) / (slope + eps)`.
- **vector**: divide each row by its L2 norm.
- **area**: divide each row by its sum.
- **peak_area**: requires both `reference_peak_cm1` config AND
  `item.meta.wavenumbers_cm1`; both missing → `ValueError`. Find
  `idx = argmin(|wavenumbers - reference_peak_cm1|)` and divide each row
  by `flat[:, idx]`.
- any other method → `ValueError`.

Reshape, moveaxis back, cast to float32, return a new `SRSImage` with
preserved meta.

**h. Acceptance criteria**:
- [ ] All five methods present in the enum.
- [ ] `peak_area` requires both `reference_peak_cm1` and
      `item.meta.wavenumbers_cm1`; both missing cases raise.
- [ ] Numerically: SNV per-spectrum mean ≈ 0, std ≈ 1; vector L2 norm ≈ 1.
- [ ] Output dtype float32; meta preserved.
- [ ] All 9 tests pass.

**i. Out of scope**:
- Histogram-based normalization (master plan does not list it).

**j. Dependencies**: T-SRS-001, T-SRS-002.

**k. Estimated diff size**: ~200 lines source + ~120 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-005 SRSNormalize`.

---

### T-SRS-006 — `SRSVCA` block

**a. Ticket ID and name**: T-SRS-006 — `SRSVCA` Vertex Component Analysis
endmember extraction.

**b. Source ADR / spec sections**: ADR-027 D7. Master plan §2.4 (locked).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/vca.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_component_analysis/test_vca.py`, ~7 tests):
`test_vca_smoke_3components`,
`test_vca_n_components_param`,
`test_vca_columns_match_wavenumbers`,
`test_vca_columns_default_to_index_when_no_wavenumbers`,
`test_vca_lambda_axis_required`,
`test_vca_index_named_endmember_id`,
`test_vca_internal_helper_callable_from_unmix` (asserts the
module-level `_extract_endmembers` is importable as the test seam for
SRSUnmix).

**f. Existing tests to update**: none.

**g. Implementation details**:

VCA algorithm (Nascimento & Bioucas-Dias 2005) walks the data simplex:
project the mean-centred data onto a unit vector orthogonal to the current
endmember subspace, pick the pixel with maximum projection magnitude, add
it as a new endmember, repeat for `n_components` iterations.

The implementation lives in two parts:

**Module-level helper** `_extract_endmembers(item, n_components) ->
(endmembers: np.ndarray, wavenumbers: list[float])`:

1. Reshape `item` to `pixels = (n_pixels, n_w)` via the standard
   `np.moveaxis` lambda-to-last pattern.
2. PCA pre-reduction to `n_components` dims with
   `sklearn.decomposition.PCA(n_components).fit_transform(pixels)`.
3. VCA loop on the reduced data with `random_state=42`: at iteration
   `i`, project the data onto a random unit vector orthogonal to the
   current endmember subspace, pick the pixel with maximum absolute
   projection, add to the basis. The endmember matrix `A` is built
   column-by-column.
4. The output endmembers are the **original** (full-dimension) pixel
   spectra at the chosen indices, shape `(n_components, n_w)`.
5. Wavenumbers come from `item.meta.wavenumbers_cm1` if set, else
   `list(range(n_w))`.

**Block class** `SRSVCA(ProcessBlock)`:

- `name = "SRS VCA"`, `category = "component_analysis"`.
- `input_ports = [InputPort("image", accepted_types=[SRSImage],
  constraint=has_axes("y","x","lambda"))]`.
- `output_ports = [OutputPort("endmembers", accepted_types=[DataFrame])]`.
- `config_schema` declares `n_components: int = 4` with `minimum=2`.
- `process_item` calls `_extract_endmembers`, wraps the returned matrix
  into a `pandas.DataFrame` with `columns = wavenumbers`,
  `index = pd.Index(range(n), name="endmember_id")`, and converts via
  `DataFrame.from_pandas(df)` to the SciStudio core type.

**h. Acceptance criteria**:
- [ ] `_extract_endmembers(item, n_components)` is module-level and
      importable from `vca.py` (so `SRSUnmix` can reuse it).
- [ ] Output `DataFrame` has `n_components` rows and `n_wavenumbers`
      columns.
- [ ] Index is named `endmember_id`.
- [ ] All 7 tests pass.

**i. Out of scope**:
- N-FINDR or other endmember extractors.
- Abundance maps — that is `SRSUnmix`.

**j. Dependencies**: T-SRS-001, T-SRS-002.

**k. Estimated diff size**: ~180 lines source + ~100 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-006 SRSVCA
endmember extraction`.

---

### T-SRS-007 — `SRSUnmix` block

**a. Ticket ID and name**: T-SRS-007 — `SRSUnmix` NNLS unmixing with optional
auto-VCA fallback.

**b. Source ADR / spec sections**: ADR-027 D7. §8 Question 4 (auto-VCA).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/unmix.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_component_analysis/test_unmix.py`, ~9 tests):
`test_unmix_with_explicit_references` (recovers planted abundances on a
synthetic 3-endmember mixture),
`test_unmix_no_references_falls_through_to_vca` (default
`auto_vca_n_components=4` produces 4 abundance maps),
`test_unmix_auto_vca_n_components_param`,
`test_unmix_returns_endmember_dataframe_too`,
`test_unmix_collection_item_type_is_image`,
`test_unmix_abundance_axes_are_yx`,
`test_unmix_5d_input_with_c`,
`test_unmix_lambda_axis_required`,
`test_unmix_logs_when_falling_through_to_vca` (caplog).

**f. Existing tests to update**: none.

**g. Implementation details**:

`SRSUnmix(ProcessBlock)` is a two-input / two-output block. Because the
default `ProcessBlock.run` only supports a single input port, this block
**overrides `run` directly** rather than implementing `process_item`.

Class declarations:

- `name = "SRS Unmix"`, `category = "component_analysis"`.
- `input_ports`:
  - `InputPort("image", accepted_types=[SRSImage],
    constraint=has_axes("y","x","lambda"))`
  - `InputPort("references", accepted_types=[DataFrame], required=False)`
- `output_ports`:
  - `OutputPort("abundance_maps", accepted_types=[Collection])`
  - `OutputPort("endmembers", accepted_types=[DataFrame])`
- `config_schema` declares `auto_vca_n_components: int = 4`.

`run(self, inputs, config)` body:

1. Iterate over `inputs["image"]` (a `Collection[SRSImage]`).
2. For each item, call private `_unmix_one(item, ref_collection,
   config)`.
3. Concatenate the returned abundance Image lists into a single
   `Collection(items, item_type=Image)`.
4. Return `{"abundance_maps": collection, "endmembers": last_endmembers_df}`.

`_unmix_one(item, ref_collection, config)`:

1. **References branch**: if `ref_collection is not None and
   len(ref_collection) > 0`, take the first DataFrame, call
   `to_pandas()`, set `references = pdf.values` and
   `wavenumbers = list(pdf.columns)`.
2. **Auto-VCA branch** (per §8 Question 4): import `_extract_endmembers`
   from the sibling `vca.py` module, call it with
   `auto_vca_n_components`, log
   `"SRSUnmix: no references provided, extracting %d endmembers via
   SRSVCA."` at INFO level via `self._log` (the `ProcessBlock.setup`
   default contract gives blocks a `logging.Logger` named after the
   class).
3. Reshape `item` to `flat = (n_pixels, n_w)`.
4. Run `scipy.optimize.nnls(references.T, flat[i])` per pixel; assemble
   `abundances = (n_pixels, n_endmembers)`. Future optimisation:
   replace with a vectorised solver if profiling demands it; out of
   scope for v0.1.
5. Reshape to `ab_cube = (..., n_endmembers)`.
6. For each endmember `k`, build a 2D `Image(axes=["y","x"],
   shape=ab_cube[..., k].shape, dtype=np.float32)` with
   `img._data = ab_cube[..., k]`.
7. Build the endmember DataFrame with `endmember_id` index and
   wavenumber columns.

**h. Acceptance criteria**:
- [ ] Two output ports: `abundance_maps: Collection[Image]` and
      `endmembers: DataFrame`.
- [ ] Optional `references` input port; when omitted, block calls
      `_extract_endmembers` from `vca.py`.
- [ ] Auto-VCA fallback emits an info log message naming the component count.
- [ ] NNLS solution is non-negative (test the synthetic mixture case).
- [ ] All 9 tests pass.

**i. Out of scope**:
- MCR-ALS (explicitly removed).
- NMF (explicitly removed).

**j. Dependencies**: T-SRS-001, T-SRS-002, T-SRS-006.

**k. Estimated diff size**: ~250 lines source + ~150 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-007 SRSUnmix
NNLS + auto-VCA fallback`.

---

### T-SRS-008 — `SRSPCA` block

**a. Ticket ID and name**: T-SRS-008 — `SRSPCA` principal component analysis
along the lambda axis.

**b. Source ADR / spec sections**: ADR-027 D7. Master plan §2.4 (locked).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/pca.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_component_analysis/test_pca.py`, ~8 tests):
`test_pca_smoke_3components`,
`test_pca_n_components_param`,
`test_pca_score_maps_axes` (each score map is `axes=["y","x"]`),
`test_pca_loadings_columns_are_wavenumbers`,
`test_pca_loadings_index_is_pc_id`,
`test_pca_scale_param` (toggle on/off),
`test_pca_n_components_too_large_raises`,
`test_pca_lambda_axis_required`.

**f. Existing tests to update**: none.

**g. Implementation details**:

`SRSPCA(ProcessBlock)` overrides `run` directly (two outputs).

- `name = "SRS PCA"`, `category = "component_analysis"`.
- `input_ports`: standard `SRSImage` input with axes constraint.
- `output_ports`: `pc_maps: Collection` and `loadings: DataFrame`.
- `config_schema`: `n_components: int = 5`, `scale: bool = True`.

`run` body:

1. Validate `n_components <= n_wavenumbers`.
2. Reshape to `flat = (n_pixels, n_w)`.
3. If `scale`, apply `sklearn.preprocessing.StandardScaler().fit_transform`.
4. `PCA(n_components, random_state=42).fit_transform(flat)` → scores
   `(n_pixels, n_components)`.
5. `pca.components_` → loadings `(n_components, n_w)`.
6. Reshape scores to `(*spatial_shape, n_components)` and emit one 2D
   `Image` per component into the `pc_maps` Collection.
7. Wrap loadings in a `DataFrame` with `pc_id` index and wavenumber
   columns.

**h. Acceptance criteria**:
- [ ] Two output ports.
- [ ] Score maps are 2D `Image` instances.
- [ ] Loadings DataFrame has `pc_id` index and wavenumber columns.
- [ ] `scale` toggle honoured.
- [ ] All 8 tests pass.

**i. Out of scope**:
- Explained-variance reporting via a third output port (defer).

**j. Dependencies**: T-SRS-001, T-SRS-002.

**k. Estimated diff size**: ~180 lines source + ~120 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-008 SRSPCA`.

---

### T-SRS-009 — `SRSICA` block

**a. Ticket ID and name**: T-SRS-009 — `SRSICA` independent component
analysis (FastICA).

**b. Source ADR / spec sections**: ADR-027 D7. Master plan §2.4 (locked).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/ica.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_component_analysis/test_ica.py`, ~7 tests):
`test_ica_smoke_3components`,
`test_ica_n_components_param`,
`test_ica_method_param` (only `"fastica"` accepted),
`test_ica_lambda_axis_required`,
`test_ica_components_index_is_ic_id`,
`test_ica_components_columns_are_wavenumbers`,
`test_ica_score_maps_are_2d_images`.

**f. Existing tests to update**: none.

**g. Implementation details**:

`SRSICA(ProcessBlock)` is structurally identical to `SRSPCA` with the
following differences:

- `name = "SRS ICA"`.
- `config_schema`: `n_components: int = 4`, `method: enum["fastica"] =
  "fastica"`. The `method` enum has only one valid value; other strings
  raise `ValueError`. The single-element enum is intentional — the
  master plan locks the method but the schema reserves the field for a
  future addendum.
- `output_ports`: `ic_maps: Collection`, `components: DataFrame`
  (instead of `pc_maps` / `loadings`).
- The DataFrame index is named `ic_id` instead of `pc_id`.
- Uses `sklearn.decomposition.FastICA(n_components, random_state=42)`
  instead of `PCA`. No `scale` parameter (FastICA whitens internally).

Reuses the same lambda-to-last `np.moveaxis` reshape and the same
spatial-shape reconstruction loop.

**h. Acceptance criteria**:
- [ ] FastICA is the only supported method (other strings raise).
- [ ] Two output ports as named.
- [ ] All 7 tests pass.

**i. Out of scope**: other ICA flavours.

**j. Dependencies**: T-SRS-001, T-SRS-002.

**k. Estimated diff size**: ~150 lines source + ~110 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-009 SRSICA`.

---

### T-SRS-010 — `SRSKMeansCluster` block

**a. Ticket ID and name**: T-SRS-010 — `SRSKMeansCluster` k-means clustering
of pixel spectra.

**b. Source ADR / spec sections**: ADR-027 D7. §8 Question 5 (feature
shape).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/kmeans.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_component_analysis/test_kmeans.py`, ~8 tests):
`test_kmeans_smoke_3clusters` (Label values in `{0,1,2}`),
`test_kmeans_n_clusters_param`,
`test_kmeans_init_random`,
`test_kmeans_init_kmeanspp` (default),
`test_kmeans_n_init_param`,
`test_kmeans_label_raster_dtype_int32`,
`test_kmeans_centroids_shape` (`(n_clusters, n_wavenumbers)` with
`cluster_id` index),
`test_kmeans_lambda_axis_required`.

**f. Existing tests to update**: none.

**g. Implementation details**:

`SRSKMeansCluster(ProcessBlock)` overrides `run` directly.

- `name = "SRS K-Means Cluster"`, `category = "component_analysis"`.
- `input_ports`: standard `SRSImage` input.
- `output_ports`: `labels: Label`, `centroids: DataFrame`.
- `config_schema`: `n_clusters: int = 4`, `init: enum["k-means++",
  "random"] = "k-means++"`, `n_init: int = 10`.

`run` body:

1. Reshape the image to `features = (n_pixels, n_w)` per §8 Question 5.
2. `km = sklearn.cluster.KMeans(n_clusters, init, n_init,
   random_state=42).fit_predict(features)` returns
   `labels_flat: (n_pixels,)`.
3. `labels_2d = labels_flat.reshape(moved.shape[:-1]).astype(np.int32)`.
4. Build a 2D `Array(axes=["y","x"], shape=labels_2d.shape,
   dtype=np.int32)` with `raster._data = labels_2d`.
5. Wrap into `Label(raster=raster, polygons=None)` (the `Label`
   composite from the imaging plugin).
6. Build the centroid `DataFrame` with `cluster_id` index from
   `km.cluster_centers_`.
7. Return `{"labels": label_obj, "centroids": centroid_df}`.

**h. Acceptance criteria**:
- [ ] Two output ports: `labels: Label`, `centroids: DataFrame`.
- [ ] Label raster dtype is `int32`, values in `[0, n_clusters - 1]`.
- [ ] Centroids DataFrame has `cluster_id` index.
- [ ] All 8 tests pass.

**i. Out of scope**:
- DBSCAN, hierarchical clustering — not in master plan list.

**j. Dependencies**: T-SRS-001, T-SRS-002.

**k. Estimated diff size**: ~150 lines source + ~120 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-010
SRSKMeansCluster`.

---

### T-SRS-011 — `ExtractSpectrum` block

**a. Ticket ID and name**: T-SRS-011 — `ExtractSpectrum` extracts mean
spectra per ROI.

**b. Source ADR / spec sections**: ADR-027 D7. §8 Question 3 (long format).
Imaging spec (`Mask` and `Label` types).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/spectral/extract.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_spectral/test_extract.py`, ~12 tests):
`test_extract_no_roi_returns_single_spectrum` (`region_id == 0`),
`test_extract_with_mask` (`region_id == 1`, masked mean),
`test_extract_with_label_two_regions` (one row block per non-zero label),
`test_extract_label_value_zero_excluded`,
`test_extract_long_format_columns` (exactly `["region_id",
"wavenumber_cm1", "intensity"]`),
`test_extract_uses_meta_wavenumbers`,
`test_extract_dtype_intensity_float`,
`test_extract_lambda_axis_required`,
`test_extract_5d_with_c_axis_raises` (v0.1 limitation: extra-axis
inputs rejected with a `SelectSlice`-pointer message),
`test_extract_mask_dtype_bool_required`,
`test_extract_label_dtype_int_required`,
`test_extract_collection_input` (Collection of one input emits one
DataFrame).

**f. Existing tests to update**: none.

**g. Implementation details**:

`ExtractSpectrum(ProcessBlock)` overrides `run` directly because it has
three input ports.

- `name = "Extract Spectrum"`, `category = "spectral"`.
- `input_ports`:
  - `InputPort("image", accepted_types=[SRSImage],
    constraint=has_axes("y","x","lambda"))`
  - `InputPort("labels", accepted_types=[Label], required=False)`
  - `InputPort("mask", accepted_types=[Mask], required=False)`
- `output_ports`: `OutputPort("spectra", accepted_types=[DataFrame])`.
- `config_schema`: empty (no user-tunable params in v0.1).

`run` body (per §8 Question 3 — long format):

1. Pull the first `SRSImage` from `inputs["image"]`. Reject if there
   are extra axes beyond `{y, x, lambda}` with a clear `ValueError`
   pointing at `SelectSlice` as the upstream remedy. (v0.1 limitation;
   v0.2 will iterate over `c` and add a `channel` column.)
2. Pull `wavenumbers = item.meta.wavenumbers_cm1` if set, else
   `list(range(n_w))`.
3. Move `lambda` to the last axis: `moved = (y, x, n_w)`.
4. **Label branch**: if `inputs["labels"]` is present and non-empty,
   take the first `Label`, validate `raster.dtype.kind in ("i","u")`,
   then for each `region_id in np.unique(raster)` skipping 0, compute
   `moved[raster == region_id].mean(axis=0)` and append one row per
   wavenumber to `rows`.
5. **Mask branch**: if `inputs["mask"]` is present and non-empty,
   validate `mask.dtype == bool`, compute `moved[mask].mean(axis=0)`,
   append rows with `region_id = 1`.
6. **No-ROI branch**: compute `moved.reshape(-1, n_w).mean(axis=0)`,
   append rows with `region_id = 0`.
7. Build `pd.DataFrame(rows, columns=["region_id", "wavenumber_cm1",
   "intensity"])`, wrap via `DataFrame.from_pandas`, return under
   the `spectra` output port name.

Both Label and Mask present is undefined behaviour in v0.1; the block
processes `labels` first and silently ignores `mask`. A defensive raise
would be safer; left as a v0.2 follow-up.

**h. Acceptance criteria**:
- [ ] Output DataFrame columns are exactly
      `["region_id", "wavenumber_cm1", "intensity"]`.
- [ ] Region 0 reserved for "no ROI" path.
- [ ] Mask input → `region_id == 1`.
- [ ] Label input → one block per non-zero label.
- [ ] 5D inputs raise with the documented message.
- [ ] All 12 tests pass.

**i. Out of scope**:
- Wide-format output.
- Per-channel extraction for 5D inputs (deferred to v0.2).
- Median or std spectra (only mean in v0.1).

**j. Dependencies**: T-SRS-001, T-SRS-002, plus the imaging plugin's
`Mask` and `Label` types.

**k. Estimated diff size**: ~220 lines source + ~180 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-011
ExtractSpectrum (long format, Mask/Label aware)`.

---

### T-SRS-012 — `BandRatio` block

**a. Ticket ID and name**: T-SRS-012 — `BandRatio` two-band intensity ratio
imaging.

**b. Source ADR / spec sections**: ADR-027 D7. Master plan §2.4 (locked).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/spectral/band_ratio.py`

**d. Files to be modified**: none.

**e. New tests** (`tests/test_spectral/test_band_ratio.py`, ~8 tests):
`test_band_ratio_smoke_ch2_ch3` (synthetic spectrum with known ratio),
`test_band_ratio_output_axes_yx`,
`test_band_ratio_requires_wavenumbers_meta`,
`test_band_ratio_band_outside_range_raises`,
`test_band_ratio_dtype_float32`,
`test_band_ratio_zero_division_safe` (epsilon protects denominator),
`test_band_ratio_collection_input`,
`test_band_ratio_lambda_axis_required`.

**f. Existing tests to update**: none.

**g. Implementation details**:

`BandRatio(ProcessBlock)` overrides `process_item`.

- `name = "Band Ratio"`, `category = "spectral"`.
- Standard `SRSImage` input port with axes constraint.
- `output_ports = [OutputPort("ratio", accepted_types=[Image])]`. The
  output port type is `Image`, NOT `SRSImage`, because the lambda axis
  is consumed.
- `config_schema`:
  - `numerator_band: [float, float] = [2850.0, 2855.0]` (CH₂ stretch,
    lipid).
  - `denominator_band: [float, float] = [2925.0, 2935.0]` (CH₃ stretch,
    protein).
  - both fields `required`.

`process_item` body:

1. Validate `item.meta is not None and item.meta.wavenumbers_cm1 is not
   None`, else `ValueError`.
2. Validate that both bands fall inside `[wavenumbers.min(),
   wavenumbers.max()]`; out-of-range raises with a message naming the
   offending band.
3. Convert `item.meta.wavenumbers_cm1` to a numpy array `wn`.
4. `num_idx = np.where((wn >= num_lo) & (wn <= num_hi))[0]`; same for
   `den_idx`.
5. Move `lambda` to the last axis. Compute
   `num_mean = moved[..., num_idx].mean(axis=-1)` and
   `den_mean = moved[..., den_idx].mean(axis=-1)`.
6. `ratio = (num_mean / (den_mean + 1e-12)).astype(np.float32)`.
7. Return a 2D `Image(axes=["y","x"], shape=ratio.shape,
   dtype=np.float32)` with `out._data = ratio`. The leading dims of
   `moved` are `(y, x)` for the standard 3D input; higher-D inputs are
   not supported in v0.1 (use `SelectSlice` upstream).

**h. Acceptance criteria**:
- [ ] Output port type is `Image` (not `SRSImage` — the lambda axis is
      consumed).
- [ ] Output `axes == ["y", "x"]`.
- [ ] Both bands validated against the wavenumber range.
- [ ] All 8 tests pass.

**i. Out of scope**:
- Three-band combinations.
- Wavelength (nm) instead of wavenumber (cm⁻¹) — wavenumber only.

**j. Dependencies**: T-SRS-001, T-SRS-002.

**k. Estimated diff size**: ~150 lines source + ~120 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-012 BandRatio`.

---

### T-SRS-013 — Plugin entry-point wiring + smoke test

**a. Ticket ID and name**: T-SRS-013 — wire `get_blocks()` and `get_types()`
to return all locked blocks/types and add an end-to-end importability
smoke test.

**b. Source ADR / spec sections**: ADR-025 §6 (entry-points), ADR-028 §D7
(plugin IO blocks via `scistudio.blocks`).

**c. Files to be created**:
- `packages/scistudio-blocks-srs/tests/test_entry_points.py`

**d. Files to be modified**:
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/__init__.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocessing/__init__.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/__init__.py`
- `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/spectral/__init__.py`

**e. New tests** (`tests/test_entry_points.py`, ~7 tests):
`test_get_blocks_returns_all_eleven` (`len == 11`),
`test_get_blocks_includes_calibrate`,
`test_get_blocks_includes_baseline_denoise_normalize`,
`test_get_blocks_includes_component_analysis_blocks`,
`test_get_blocks_includes_extract_and_band_ratio`,
`test_block_registry_scan_finds_srs_blocks`,
`test_type_registry_scan_finds_srsimage`.

**f. Existing tests to update**: none.

**g. Implementation details**:

`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/__init__.py`:

- Imports each block class from its sibling module
  (`preprocessing.calibrate.SRSCalibrate`,
  `preprocessing.baseline.SRSBaseline`, etc.).
- Re-exports them plus `SRSImage` via `__all__`.
- Implements `get_blocks()` to return all 11 block classes:
  `[SRSCalibrate, SRSBaseline, SRSDenoise, SRSNormalize, SRSVCA,
  SRSUnmix, SRSPCA, SRSICA, SRSKMeansCluster, ExtractSpectrum,
  BandRatio]`.
  Total: 4 preprocessing + 5 component analysis + 2 spectral = **11
  blocks**. (The "~8 blocks" / "10 blocks" phrasing in the master plan
  prompt was approximate; the locked enumerated list resolves to 11.)

`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/types.py`:

- `get_types()` returns `[SRSImage]`.

The submodule `__init__.py` files (`preprocessing/__init__.py`,
`component_analysis/__init__.py`, `spectral/__init__.py`) re-export
their classes for ergonomic `from scistudio_blocks_srs.preprocessing
import SRSCalibrate` access but do not need to declare entry-point
contributors of their own.

**h. Acceptance criteria**:
- [ ] `get_blocks()` returns 11 classes (and 11 only — no extras).
- [ ] `get_types()` returns `[SRSImage]`.
- [ ] After `BlockRegistry.scan()`, all 11 blocks are findable by their
      `type_name`.
- [ ] After `TypeRegistry.scan()`, `SRSImage` is resolvable.
- [ ] All 7 entry-point tests pass.

**i. Out of scope**:
- Adding any block not on the list (master plan §5 forbidden).

**j. Dependencies**: every prior T-SRS ticket.

**k. Estimated diff size**: ~80 lines source + ~80 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-013 entry-point
wiring + smoke test`.

---

### T-SRS-014 — E2E integration test (cross-plugin)

**a. Ticket ID and name**: T-SRS-014 — End-to-end integration test
exercising imaging plugin's `LoadImage` / `Denoise` / `CellposeSegment`
together with this plugin's `SRSCalibrate` / `ExtractSpectrum`.

**b. Source ADR / spec sections**: master plan §1 ("E2E test spec
(CRITICAL — this IS success criteria)"), this spec §11 below.

**c. Files to be created**:
- `packages/scistudio-blocks-srs/tests/integration/test_e2e_with_imaging.py`
- `packages/scistudio-blocks-srs/tests/integration/conftest.py` (fixture
  for the test image paths)

**d. Files to be modified**: none.

**e. New tests** (`tests/integration/test_e2e_with_imaging.py`, ~3 tests):
- `test_e2e_python_headless_workflow` — full pipeline:
  1. `LoadImage` of `K562_L_2845 (uV).tif` and `K562_UL_2845 (uV).tif`
  2. `LoadImage` of `K562_L_spectra (uV).tif` and `K562_UL_spectra (uV).tif`
  3. `Denoise(method="gaussian", sigma=1.0)` over all four images
  4. `CellposeSegment` over the two 2845 images → 2 `Label` masks
  5. `SRSCalibrate` over the two spectra images (using default digitizer
     params) → 2 `SRSImage` instances
  6. `ExtractSpectrum` consuming each (`SRSImage`, `Label`) pair → 2
     long-format DataFrames of per-cell spectra
  7. Assert: every block exits cleanly, the resulting DataFrames have the
     three expected columns, the `region_id` set is non-empty, and the
     row count equals `n_regions * n_wavenumbers`.
- `test_e2e_block_registry_resolution` — assert that
  `BlockRegistry.scan()` finds every block this test consumes (sanity
  check that the plugin install path works for both packages).
- `test_e2e_with_save_data` — second test variant that calls
  `SaveData(core_type="DataFrame", path=tmp_path/"spectra.csv")` on the
  produced DataFrame and asserts the CSV is on disk.

**f. Existing tests to update**: none.

**g. Implementation details**:

`tests/integration/conftest.py` declares two pytest fixtures
(`segmentation_image_paths` and `spectra_image_paths`) that point at
the four test images via an `EXAMPLE_DIR =
Path(r"C:\Users\jiazh\Desktop\workspace\Example\images")` constant.

`tests/integration/test_e2e_with_imaging.py` is gated by
`pytestmark = pytest.mark.requires_imaging` and starts with
`imaging = pytest.importorskip("scistudio_blocks_imaging")` so the test
skips cleanly when the sister plugin is not installed.

The main test function `test_e2e_python_headless_workflow` performs
seven steps in sequence:

1. **Load segmentation images** — instantiate `LoadImage` once per
   path and call `loader.run({}, {"path": str(path)})`. Extend a
   `seg_imgs` list with the returned `data` Collection.
2. **Load spectra images** — same pattern, into `spec_imgs`.
3. **Denoise** — instantiate `Denoise()` from the imaging plugin and
   run it once on each Collection with `{"method": "gaussian",
   "sigma": 1.0}`. Two output Collections: `seg_denoised`,
   `spec_denoised`.
4. **CellposeSegment** — instantiate, call `run({"image":
   seg_denoised}, {"diameter": 30.0, "model_type": "cyto"})`. Pull
   `masks = out["labels"]`. Assert `len(masks) == 2`.
5. **SRSCalibrate** — instantiate, call `run({"image":
   spec_denoised}, {"bit_depth": 4096, "voltage_range": 10.0,
   "offset": 0.0, "scale": 1.0})`. Pull `srs_imgs = out["srs_image"]`.
   Assert `len(srs_imgs) == 2`.
6. **ExtractSpectrum** — instantiate. Loop over `zip(srs_imgs, masks)`
   and call `extract.run({"image": Collection([srs]), "labels":
   Collection([mask])}, {})`. Append each `out["spectra"]` DataFrame
   to a `spectra_dfs` list.
7. **Assertions**:
   - `len(spectra_dfs) == 2`.
   - For each DataFrame: columns are `["region_id", "wavenumber_cm1",
     "intensity"]`, `region_id.nunique() >= 1`, and
     `len(pdf) == n_regions * n_wavenumbers`.

The second test function (`test_e2e_with_save_data`) wraps step 7 by
calling `SaveData(core_type="DataFrame", path=str(tmp_path /
f"spectra_{i}.csv"))` on each DataFrame and asserting the CSV file
exists and round-trips back through `pd.read_csv`.

The third test function (`test_e2e_block_registry_resolution`) does
not run the workflow — it just calls `BlockRegistry.scan()` and asserts
that every block this test consumes (`LoadImage`, `Denoise`,
`CellposeSegment`, `SRSCalibrate`, `ExtractSpectrum`) appears in
`registry.list_specs()`. This is a sanity check that the cross-plugin
install path produces a working registry.

**h. Acceptance criteria**:
- [ ] Test marked with `@pytest.mark.requires_imaging` so CI without the
      imaging plugin installed skips it cleanly.
- [ ] Test reads the four real test images at the locked path.
- [ ] All seven workflow steps complete without exception when both
      plugins are installed.
- [ ] The produced DataFrames have the three expected columns.
- [ ] Test variant with `SaveData` writes a CSV to `tmp_path` and asserts
      the file exists.

**i. Out of scope**:
- The Chrome GUI E2E test — that is a separate manager-tracked task per
  master plan §4.4 step 14.
- Generating new test images.

**j. Dependencies**: every prior T-SRS ticket plus the imaging plugin's
T-IMG-CellposeSegment ticket.

**k. Estimated diff size**: ~250 lines tests.

**l. Suggested workflow gate ticket title**: `feat(srs): T-SRS-014 E2E
integration test with imaging plugin`.

---

## 10. Summary table

| Ticket    | Block / Component       | Source                | Output                                 | Tests  | Diff (src/test) |
|-----------|-------------------------|-----------------------|----------------------------------------|--------|-----------------|
| T-SRS-000 | Package skeleton        | master plan §2.4      | pyproject + entry-points               | 6      | 80 / 70         |
| T-SRS-001 | `SRSImage` type         | ADR-027 D1/D5         | typed class + Meta                     | 14     | 80 / 40         |
| T-SRS-002 | `SRSCalibrate`          | master plan §2.4      | `Image → SRSImage`                     | 12     | 250 / 150       |
| T-SRS-003 | `SRSBaseline`           | master plan §2.4      | `SRSImage → SRSImage`                  | 10     | 250 / 120       |
| T-SRS-004 | `SRSDenoise`            | master plan §2.4      | `SRSImage → SRSImage`                  | 10     | 250 / 150       |
| T-SRS-005 | `SRSNormalize`          | master plan §2.4      | `SRSImage → SRSImage`                  | 9      | 200 / 120       |
| T-SRS-006 | `SRSVCA`                | master plan §2.4      | `SRSImage → DataFrame` (endmembers)    | 7      | 180 / 100       |
| T-SRS-007 | `SRSUnmix`              | master plan §2.4      | `SRSImage(+refs) → Collection + DF`    | 9      | 250 / 150       |
| T-SRS-008 | `SRSPCA`                | master plan §2.4      | `SRSImage → Collection + DF`           | 8      | 180 / 120       |
| T-SRS-009 | `SRSICA`                | master plan §2.4      | `SRSImage → Collection + DF`           | 7      | 150 / 110       |
| T-SRS-010 | `SRSKMeansCluster`      | master plan §2.4      | `SRSImage → Label + DF`                | 8      | 150 / 120       |
| T-SRS-011 | `ExtractSpectrum`       | master plan §2.4      | `SRSImage(+ROI) → DataFrame (long)`    | 12     | 220 / 180       |
| T-SRS-012 | `BandRatio`             | master plan §2.4      | `SRSImage → Image (2D)`                | 8      | 150 / 120       |
| T-SRS-013 | Entry-point wiring      | ADR-025 §6            | get_blocks/get_types complete          | 7      | 80 / 80         |
| T-SRS-014 | E2E with imaging        | master plan §1        | full workflow on real images           | 3      | 0 / 250         |
| **Total** | **15 tickets**          |                       |                                        | **130**| **2470 / 1880** |

Total diff budget: ~4350 lines across the entire SRS plugin (source +
tests). Fits comfortably inside a single sprint.

## 11. End-to-end integration test (T-SRS-014 detail)

This section reproduces the master plan §1 E2E test specification with the
SRS-specific block names plugged in. It is the success criterion for the
SRS plugin and is referenced by both this spec and the imaging spec
(`docs/specs/phase11-imaging-block-spec.md` §11).

### Test images

The four test images live at `C:\Users\jiazh\Desktop\workspace\Example\images\`
with the following filenames:

| Filename                       | Purpose                   |
|--------------------------------|---------------------------|
| `K562_L_2845 (uV).tif`         | Segmentation source (cell |
|                                | morphology image, K562    |
|                                | leukaemia "L" condition)  |
| `K562_UL_2845 (uV).tif`        | Segmentation source       |
|                                | (K562 "UL" condition)     |
| `K562_L_spectra (uV).tif`      | Spectral source           |
|                                | (hyperspectral SRS, "L")  |
| `K562_UL_spectra (uV).tif`     | Spectral source ("UL")    |

The two `*_2845` images are single-wavenumber bright-field-like images
suitable for Cellpose segmentation. The two `*_spectra` images are 3D
`(lambda, y, x)` hyperspectral SRS cubes that the SRS plugin's calibration
and extraction blocks consume.

### Workflow shape

```
LoadImage(K562_L_2845.tif)   ─┐
                              ├─► Denoise(gaussian) ─► CellposeSegment ─┐
LoadImage(K562_UL_2845.tif)  ─┘                                          │
                                                                         ▼
                                                                  Collection[Label]
                                                                         │
LoadImage(K562_L_spectra.tif) ─┐                                         │
                               ├─► Denoise(gaussian) ─► SRSCalibrate ────┤
LoadImage(K562_UL_spectra.tif)─┘                                         │
                                                                         ▼
                                                              ┌─► ExtractSpectrum ─► DataFrame
                                                              │
                                                              └─► (per (SRSImage, Label) pair)
                                                                         │
                                                                         ▼
                                                              SaveData(spectra.csv)
                                                              SaveImage(masks.tif)
```

### What this exercises

- Imaging plugin's `LoadImage` (TIFF format auto-detection).
- Imaging plugin's `Denoise` (Gaussian method) operating on 2D and 3D
  inputs.
- Imaging plugin's `CellposeSegment` flagship block (with `setup()`
  loading the model once per Collection, then GPU-batched eval).
- Imaging plugin's `Mask` / `Label` types (output of segmentation).
- SRS plugin's `SRSCalibrate` performing digitizer inversion + type
  conversion to `SRSImage`.
- SRS plugin's `ExtractSpectrum` consuming the cross-plugin `Label`
  alongside its own `SRSImage`.
- Core's post-ADR-028 `SaveData` block (auto-detects DataFrame and writes
  CSV).
- Cross-plugin port-check: the `Label` produced by imaging is accepted
  by SRS's `ExtractSpectrum` because both plugins share the same
  `TypeRegistry`.

### Pass criteria

1. All blocks reach `BlockState.DONE` (no `ERROR`, no `SKIPPED`,
   no `CANCELLED`).
2. The two output `Label` instances are non-empty (Cellpose found at
   least one cell in each image).
3. Each output `DataFrame` has columns
   `["region_id", "wavenumber_cm1", "intensity"]` and at least
   `n_cells * n_wavenumbers` rows.
4. The on-disk CSV files exist after `SaveData` and round-trip back into
   DataFrames with the same schema.

If any block fails, master plan §4.4 step 13 says: "file issue, spawn fix
agent, re-run". Test failures here are not a reason to weaken acceptance
criteria — they are a reason to fix the underlying block.

## 12. References

- **`phase11_master_plan.md`** — single source of truth for the overnight
  cascade. §2.4 SRS PLUGIN section is the locked block list this spec
  implements verbatim.
- **`docs/adr/ADR.md`** — ADR-027 (Phase 10 type system, 6D axes,
  setup/teardown, stratified Pydantic Meta), ADR-028 (IOBlock refactor,
  plugin-owned IO), ADR-028 Addendum 1 (dynamic ports + GUI consequences).
- **`docs/architecture/ARCHITECTURE.md`** — §4.1 (base type hierarchy),
  §4.2 (storage backends), §5.1 (Block ABC), §5.2 (port system).
- **`docs/specs/phase10-implementation-standards.md`** — structural
  template for the 12-subsection per-ticket pattern.
- **`docs/specs/phase11-imaging-block-spec.md`** — sister spec for the
  imaging plugin; supplies `Image`, `Mask`, `Label`, `LoadImage`,
  `Denoise`, `CellposeSegment`.
- **`CLAUDE.md`** — Appendix A (workflow gate), §6.7 (scope discipline),
  §9.2 (no silent scope expansion).
- **`src/scistudio/core/types/array.py`** — `Array` base class with
  instance-level axes and class-level schema.
- **`src/scistudio/core/meta/framework.py`** — `FrameworkMeta` and
  `with_meta_changes` helper used by every typed `Meta` model.
- **`src/scistudio/core/units.py`** — `PhysicalQuantity` for the
  `integration_time` field on `SRSImage.Meta`.
- **OptEasy reference**:
  `OptEasy/opteasy-blocks/src/opteasy_blocks/preprocessing/srs_calibration.py`
  for the digitizer inversion formula and parameter names.
- **OptEasy spectral reference**:
  `OptEasy/opteasy-blocks/src/opteasy_blocks/spectral/{extract_spectrum,
  unmixing, pca}.py` for the analytic kernel choices.
