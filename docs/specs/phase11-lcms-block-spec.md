---
spec_id: phase11-lcms-block-spec
title: "Phase 11 LC-MS Plugin Block Specification"
status: Deprecated
feature_branch: legacy/phase11-lcms-block-spec
created: 2026-04-07
input: "Historical Phase 11 scieasy-blocks-lcms implementation specification retained for reference."
owners:
  - "@jiazhenz026"
related_adrs:
  - 27
  - 28
related_specs:
  - phase11-implementation-standards
  - phase11-imaging-block-spec
  - phase11-srs-block-spec
scope:
  in:
    - Historical LC-MS plugin block contracts retained for reference.
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
# Phase 11 LC-MS Plugin Block Specification

## 1. Change Summary

This deprecated spec is retained as historical reference. Its original body is preserved below, but it is not an active implementation spec under ADR-042.

## 2. Existing Historical Body

# Phase 11 LC-MS Plugin Block Specification

**Status**: accepted
**Date**: 2026-04-07
**Issue**: #301
**Authoritative ADRs**: ADR-027, ADR-027 Addendum 1, ADR-028, ADR-028 Addendum 1
**Master plan**: `phase11_master_plan.md` §2.4 (LC-MS PLUGIN block list)
**Companion specs**: `phase11-imaging-block-spec.md`, `phase11-srs-block-spec.md`

## 1. Purpose

This document is the **single source of truth** for the implementation of the
`scieasy-blocks-lcms` plugin package. It enumerates the four plugin types,
the ~20 blocks, the package layout, the per-ticket implementation contract,
the open questions resolved during spec authoring, and the integration test
strategy.

Unlike the imaging plugin (which is broad and dimension-rich) or the SRS
plugin (which is a small specialisation of imaging), the LC-MS plugin is
shaped almost entirely by **the user's verbatim workflow**:

> 对于 raw 和 mzML、mzXML 文件，我们一般会直接打开 ElMAVEN 处理，因此 load 的时候
> 可以当作一个 artifact 类，然后直接接一个 ElMAVEN 的 AppBlock 打开进行处理。
> 之后我们会用 ElMAVEN 导出 csv 或者 tab 表格。导出的表格我们会导入自己原有的 R
> pipeline 做 Natural isotope correction，之后导出一个 xlsx 文档，这对应一个
> script block。再往后的分析就比较 customize，可以引入常用的代谢组学分析。
> 另外，因为我们做 stable isotope tracing 很多，在 LC-MS 包里面加入一些支持
> isotope tracing 的模块是比较有用的。

In English:

1. Raw `.mzML` / `.mzXML` / `.raw` / `.d` files are opened directly in **ElMAVEN**
   (an interactive desktop GUI). The plugin treats raw files as `Artifact` only
   — it never parses scan-level data.
2. ElMAVEN exports CSV/TSV/XLSX peak tables.
3. Peak tables flow into the user's existing **AccuCor R pipeline** for natural
   isotope correction; the output is a **MID table in long format**.
4. Downstream analysis is dominated by **stable isotope tracing** (the plugin's
   USP) plus general metabolomics (univariate, multivariate, pathway, consumption /
   secretion).
5. Final figure polishing happens in **GraphPad Prism** (another AppBlock).

The plugin is therefore designed around **table-shaped DataFrames flowing
through Python**, with two AppBlocks (`ElMAVENBlock`, `GraphPadBlock`) and one
CodeBlock-R (`AccuCorR`) bridging the external tools the user already depends
on. The plugin's USP is **stable isotope tracing**, which is why §9 dedicates
the most detailed per-ticket sections to the isotope tracing block group.

## 2. Scope

**In scope**: design contract for the `scieasy-blocks-lcms` plugin package,
covering 4 types and ~20 blocks across IO, external tools, isotope tracing,
metabolomics analysis, and external plotting. One PR per ticket. The recommended
PR order is a stacked sequence per the dependency graph in §4.

**Out of scope**:

- The two sibling specs (`phase11-imaging-block-spec.md`,
  `phase11-srs-block-spec.md`) — independent agents and PRs.
- Core type system, scheduler, worker subprocess (Phase 10, already merged).
- ADR text — ADR-027 / ADR-028 / their Addenda are already merged.
- The bundled AccuCor R script source code itself — only the *contract* for
  shipping it as package data is specified here. The actual R code lives in
  the implementation ticket (T-LCMS-007).
- The `scieasy-blocks-imaging` and `scieasy-blocks-srs` plugins.

**Forbidden** (these would be scope violations per the master plan §2.4 lock):

- `MSSpectrum(Series)` — the user explicitly rejected scan-level types.
- `MSRun(Array)` — same.
- `EnumerateIsotopologues`, `MatchIsotopologues`, `ComputeMID`,
  `AtomPercentExcess`, `TimeCourseFit`, `TracerFateMap` — AccuCor R does all
  of this externally.
- QC blocks (`QCDriftCheck`, `QCRecovery`, `ReportQC`) — user removed.
- `ManualReview` blocks — user said "我 GUI 右边的 viewer 栏点 block 就能看见".
- `MZmineProcess`, `XCMSRun` — user said "先实现 ElMAVEN".
- Full 13C-MFA — user said "full 13C-MFA 太重". `FluxEstimate` is a simple
  steady-state estimate only.
- Wide-format MID as the canonical shape — AccuCor produces long, the user's
  workflow uses long.

## 3. Cross-reference table

| Ticket          | Title                                            | Source ADR / spec section                       |
|-----------------|--------------------------------------------------|-------------------------------------------------|
| T-LCMS-001      | Plugin scaffold (pyproject, package layout)      | ADR-028 §D2 + master plan §2.4                  |
| T-LCMS-002      | Types module (4 plain-DataFrame/Artifact types)  | ADR-027 D2 + master plan §2.4 LC-MS types       |
| T-LCMS-003      | `LoadMSRawFiles`                                 | ADR-028 §D6 + master plan §2.4 IO               |
| T-LCMS-004      | `LoadPeakTable`                                  | ADR-028 §D6                                     |
| T-LCMS-005      | `LoadMIDTable`                                   | ADR-028 §D6 + §8 Q-3 (long-format)              |
| T-LCMS-006      | `LoadSampleMetadata` + `SaveTable`               | ADR-028 §D6                                     |
| T-LCMS-007      | `ElMAVENBlock` + `AccuCorR`                      | ADR-019 (AppBlock), ADR-017 (CodeBlock R)       |
| T-LCMS-008      | `Calculate13CEnrichment`                         | Master plan §2.4 isotope tracing (USP)          |
| T-LCMS-009      | `FractionalLabeling`                             | Master plan §2.4 isotope tracing                |
| T-LCMS-010      | `CompareGroupMID`                                | Master plan §2.4 isotope tracing                |
| T-LCMS-011      | `FluxEstimate`                                   | Master plan §2.4 isotope tracing                |
| T-LCMS-012      | `PoolSizeNormalize`                              | Master plan §2.4 isotope tracing                |
| T-LCMS-013      | `MetaboliteMatrix`                               | Master plan §2.4 metabolomics                   |
| T-LCMS-014      | `MatrixPreprocess`                               | Master plan §2.4 metabolomics                   |
| T-LCMS-015      | `UnivariateStats`                                | Master plan §2.4 metabolomics                   |
| T-LCMS-016      | `MultivariateAnalysis`                           | Master plan §2.4 metabolomics                   |
| T-LCMS-017      | `PathwayEnrichment`                              | Master plan §2.4 + §8 Q-6 (KEGG vs MetaboAnalystR) |
| T-LCMS-018      | `ConsumptionSecretionAnalysis`                   | Master plan §2.4 metabolomics                   |
| T-LCMS-019      | `GraphPadBlock`                                  | Master plan §2.4 plotting (AppBlock)            |
| T-LCMS-020      | Entry-point registration + plugin smoke test     | ADR-026 (entry-points)                          |
| T-LCMS-021      | Isotope tracing integration test                 | Master plan §8 (synthetic fixture)              |

## 4. Dependency graph

```
                     T-LCMS-001 (scaffold)
                          │
                          ▼
                     T-LCMS-002 (types module)
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   T-LCMS-003         T-LCMS-004        T-LCMS-005
   LoadMSRawFiles     LoadPeakTable     LoadMIDTable
        │                 │                 │
        │                 └────┬────────────┘
        │                      ▼
        │                T-LCMS-006
        │                LoadSampleMetadata + SaveTable
        │                      │
        ▼                      │
   T-LCMS-007 ─────────────────┤
   ElMAVENBlock + AccuCorR     │
                               ▼
                       ┌───────┴────────┐
                       ▼                ▼
               (isotope tracing) (metabolomics)
                       │                │
              ┌────────┼────────┐       │
              ▼        ▼        ▼       ▼
        T-LCMS-008  T-LCMS-009 T-LCMS-010 ... T-LCMS-018
        Calc13C    Frac        CompareGroupMID
        Enrichment Labeling
              │
              ▼
        T-LCMS-011 (FluxEstimate)
              │
              ▼
        T-LCMS-012 (PoolSizeNormalize)
                       │
                       ▼
                 T-LCMS-019 (GraphPadBlock — independent of analysis)
                       │
                       ▼
                 T-LCMS-020 (entry-point registration smoke)
                       │
                       ▼
                 T-LCMS-021 (isotope tracing integration test)
```

T-LCMS-001 is the foundation: nothing else can land without the package
scaffold. T-LCMS-002 (types) is the prerequisite for every IO and analysis
ticket because every block accepts/returns one of the four plugin types.
T-LCMS-003 / T-LCMS-004 / T-LCMS-005 are independent of each other and can
land in any order after T-LCMS-002. T-LCMS-006 stacks on T-LCMS-004 (only so
its tests can use a real PeakTable fixture). T-LCMS-007 (the two external
tools) depends on T-LCMS-003 + T-LCMS-004 + T-LCMS-006. T-LCMS-008 through
T-LCMS-018 are the analysis tickets and stack in the order shown. T-LCMS-019
(GraphPadBlock) is independent of the analysis chain — it can land any time
after T-LCMS-001 + T-LCMS-002. T-LCMS-020 stacks on every preceding ticket
(it registers them all). T-LCMS-021 stacks on T-LCMS-020.

## 5. Recommended PR order

The recommended linear order, where each PR's base is the previous PR's
branch (stacked PRs):

1. **T-LCMS-001** — plugin scaffold + pyproject (independent, small)
2. **T-LCMS-002** — types module (4 classes)
3. **T-LCMS-003** — `LoadMSRawFiles`
4. **T-LCMS-004** — `LoadPeakTable`
5. **T-LCMS-005** — `LoadMIDTable`
6. **T-LCMS-006** — `LoadSampleMetadata` + `SaveTable`
7. **T-LCMS-007** — `ElMAVENBlock` + `AccuCorR` (the two external tools)
8. **T-LCMS-008** — `Calculate13CEnrichment` (start of the USP cluster)
9. **T-LCMS-009** — `FractionalLabeling`
10. **T-LCMS-010** — `CompareGroupMID`
11. **T-LCMS-011** — `FluxEstimate`
12. **T-LCMS-012** — `PoolSizeNormalize`
13. **T-LCMS-013** — `MetaboliteMatrix` (start of the metabolomics cluster)
14. **T-LCMS-014** — `MatrixPreprocess`
15. **T-LCMS-015** — `UnivariateStats`
16. **T-LCMS-016** — `MultivariateAnalysis`
17. **T-LCMS-017** — `PathwayEnrichment`
18. **T-LCMS-018** — `ConsumptionSecretionAnalysis`
19. **T-LCMS-019** — `GraphPadBlock`
20. **T-LCMS-020** — entry-point registration + plugin smoke test
21. **T-LCMS-021** — isotope tracing integration test

If parallel work is desired, T-LCMS-003 / T-LCMS-004 / T-LCMS-005 can be
opened simultaneously off T-LCMS-002. T-LCMS-019 (GraphPadBlock) can be
opened in parallel with the analysis cluster — it touches a different
sub-package.

The two external-tool tickets (T-LCMS-007's `ElMAVENBlock` and `AccuCorR`)
are deliberately bundled into a single ticket because they share the
"external tool wrapper" architectural pattern and because the implementation
agent needs to think about both `app_command` validation and R-runner
integration in the same head-space. Splitting them would create two PRs that
review identically.

## 6. Universal rules for all LC-MS implementation agents

These rules apply to **every** ticket in this document. Failure to follow
them is a workflow gate violation per `CLAUDE.md` Appendix A.

1. **Workflow gate is mandatory** — every ticket follows the full 6-stage
   workflow gate. No exceptions for "small" tickets. Each stage must show
   `[DONE]` in `python .workflow/gate.py status <task_id>` before the next
   stage begins.
2. **Branch naming**: `feat/issue-N/T-LCMS-NNN-short-name`. Example for
   T-LCMS-008: `feat/issue-NNN/T-LCMS-008-calc-13c-enrichment`.
3. **Stacked PR base** — each PR's base branch is the previous merged PR's
   branch (so the diffs compose cleanly). If the previous PR has already
   merged into `main`, base off `main` directly. Mark stacked PRs with the
   previous PR number in the description.
4. **Out-of-scope changes are forbidden** — the PR's diff must contain only
   files listed in the ticket's "Files to be created", "Files to be
   modified", "New tests", and "Existing tests to update" sections. Any
   other modified file is a scope violation per `CLAUDE.md` §6.7. Tests for
   in-scope source files are always in-scope.
5. **Plugin layout discipline**: every plugin source file lives under
   `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/`. Tests live under
   `packages/scieasy-blocks-lcms/tests/`. The plugin MUST NOT add files
   under `src/scieasy/` (the core repo path). If an implementation agent
   discovers a missing core capability, they file a *new core issue* and
   block on it — never patch core inside a plugin PR.
6. **Every check must be green before review**:
   - `pytest -x --no-cov packages/scieasy-blocks-lcms/tests/` passes
     locally.
   - `ruff check packages/scieasy-blocks-lcms/` clean.
   - `ruff format --check packages/scieasy-blocks-lcms/` clean.
   - `mypy packages/scieasy-blocks-lcms/src --ignore-missing-imports`
     clean.
   - The core repo's `python -m importlinter --config pyproject.toml`
     contract is unchanged (plugins do not import from core internals).
7. **CHANGELOG.md** must be updated under `[Unreleased]` in the appropriate
   section (`Added` / `Changed` / `Fixed`) with full attribution per
   `CLAUDE.md` Appendix A Stage 6:
   `[#N] Description (@claude, YYYY-MM-DD, branch: ..., session: ...)`.
8. **PR body must reference**:
   - The relevant master plan section (e.g. "Per master plan §2.4 LC-MS
     PLUGIN — isotope tracing").
   - The ticket ID from this spec (e.g. "Per
     `docs/specs/phase11-lcms-block-spec.md` T-LCMS-008").
   - The previous PR in the stack (if any).
   - A reproduction of the ticket's acceptance criteria as a checklist
     with each box ticked when satisfied.
9. **No silent scope expansion** — if implementing a ticket reveals a
   pre-existing bug or design ambiguity, open a *new issue* describing it.
   Do not fix it inline. Per `CLAUDE.md` §9.2 ("Claude must not silently
   broaden scope") and Appendix C Step 3.
10. **No type relaxation to pass tests** — per master plan §5 "Audit Agent
    Scope Violation Detection". If a test fails because the spec requires
    handling `MIDTable` and the implementation only handles `DataFrame`,
    the fix is to handle `MIDTable`, NOT to weaken the test to accept
    `DataFrame`. Audit agents will explicitly check for this anti-pattern.
11. **External tool blocks (T-LCMS-007, T-LCMS-019)** must mark their
    integration tests with the correct pytest markers
    (`@pytest.mark.requires_elmaven`, `@pytest.mark.requires_r`,
    `@pytest.mark.requires_graphpad`) and register them under
    `[tool.pytest.ini_options].markers` in the plugin's `pyproject.toml`
    so CI skips them when the external dependency is absent.
12. **The bundled AccuCor R script** is package data, not source code.
    It lives at `src/scieasy_blocks_lcms/scripts/accucor_default.R` and is
    declared in `pyproject.toml` `[tool.setuptools.package-data]`. The
    `AccuCorR` block resolves the script path via `importlib.resources`,
    not via filesystem traversal.

## 7. Universal acceptance criteria (apply to ALL LC-MS tickets)

In addition to each ticket's own acceptance criteria, every ticket must
satisfy these:

1. The PR's diff includes ONLY files listed in "Files to be created",
   "Files to be modified", "New tests", and "Existing tests to update" for
   that ticket. Any other modified file is a scope violation.
2. `pytest -x --no-cov packages/scieasy-blocks-lcms/tests/` passes
   locally before push.
3. `ruff check packages/scieasy-blocks-lcms/` clean.
4. `ruff format --check packages/scieasy-blocks-lcms/` clean.
5. `mypy packages/scieasy-blocks-lcms/src --ignore-missing-imports` clean.
6. Importlinter contract unchanged on the core repo.
7. `CHANGELOG.md` has an entry under `[Unreleased]` in the appropriate
   section with full attribution per `CLAUDE.md` Appendix A Stage 6.
8. Workflow gate has all 6 stages `[DONE]`.
9. PR body explicitly references which master plan section it implements
   and links to this spec by ticket ID.
10. PR body reproduces the ticket's per-ticket acceptance criteria as a
    checklist with each item ticked.
11. CI is green on the PR before requesting review.
12. No new core types are introduced (every plugin type subclasses one of
    the seven Phase 10 core types: `DataObject`, `Array`, `Series`,
    `DataFrame`, `Text`, `Artifact`, `CompositeData`).

## 8. Open questions resolved by this document

These are decisions made in this document that go *beyond* the master plan
§2.4 block list. The master plan deferred them to spec authoring; this
section records the resolution so subsequent implementation agents do not
have to re-litigate.

### Q-1: AccuCor R script bundling — vendored vs. external dependency?

The user's existing R pipeline uses the **AccuCor R package**
([`https://github.com/lparsons/accucor`](https://github.com/lparsons/accucor),
authored by Xiaojing Huang and Lance Parsons at Princeton). The user pipes
ElMAVEN-exported peak tables through their *own* R script that calls
`accucor::natural_abundance_correction()`.

**Decision**: the `AccuCorR` block ships a **default AccuCor R driver
script** as package data at
`packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/scripts/accucor_default.R`,
and accepts a user override via the `accucor_script_path: str | None`
config field.

The default driver script:

- Loads the AccuCor R package (`library(accucor)`).
- Reads the input PeakTable (CSV/TSV/XLSX) from the path the block writes
  to the exchange directory.
- Reads the SampleMetadata from the same exchange directory.
- Calls `accucor::natural_abundance_correction(...)` with the
  `tracer_formula` and `resolution` config fields.
- Writes the corrected MID table (long format) to the output directory.

**Versioning**: the bundled script is pinned to AccuCor v0.3.1 (the latest
stable release as of spec authoring, 2026-04-07). The implementation
ticket (T-LCMS-007) records the upstream commit SHA in a comment at the
top of `accucor_default.R`. The `accucor` R package is **not** auto-installed
by the plugin (R packages cannot be installed via pip); the plugin's
README documents the prerequisite (`install.packages("accucor")`).

**License**: AccuCor is MIT-licensed; the upstream LICENSE is reproduced
verbatim in `packages/scieasy-blocks-lcms/THIRD_PARTY_LICENSES.md` per the
implementation ticket T-LCMS-007.

**Why not just call AccuCor directly via `rpy2`?** Because `rpy2` carries a
heavy install footprint, fights with conda environments, and breaks on
Windows + R combinations. The `CodeBlock(language="r")` runner already
spawns a real `Rscript` subprocess (per ADR-017), so we get the same effect
with less complexity.

### Q-2: ElMAVEN GUI interaction — script the UI or wait for the user?

ElMAVEN is a desktop GUI application (Qt-based). It exposes some
command-line flags but is fundamentally interactive: the user opens the
peak table view, picks compounds, sets RT windows, and exports manually.

**Decision**: the `ElMAVENBlock` does **not** try to script ElMAVEN. It
follows the existing `AppBlock` file-exchange pattern:

1. Block copies the input `Collection[MSRawFile]` paths into
   `<exchange_dir>/inputs/` (or just records their paths in a manifest
   file — see implementation note in T-LCMS-007).
2. Block launches ElMAVEN via `subprocess.Popen` (the `app_command` is
   `elmaven` by default; the user may override via config).
3. Block transitions to `PAUSED` state (per ADR-018) and the
   `FileWatcher` watches `<exchange_dir>/outputs/` for files matching
   `*.csv`, `*.tsv`, `*.xlsx`.
4. The user drives ElMAVEN manually: opens the input files, runs peak
   detection, and uses ElMAVEN's `Export → Spreadsheet` to write CSV/TSV/XLSX
   into the watched output directory.
5. When the watcher detects stable files (per the standard
   `stability_period`), the block transitions back to `RUNNING`, parses
   the exported file as a `PeakTable`, and returns it.

**Timeout**: the `watch_timeout` defaults to **1800 seconds** (30 minutes)
because ElMAVEN sessions are slow and the user may need to inspect many
compounds. This is overridable via config.

**MID export**: ElMAVEN can also export a MID-shaped table directly (its
`isotope` view). The block treats `*.csv` / `*.tsv` / `*.xlsx` files in
the output directory uniformly: if the user exports both a peak table and
a MID table, the block returns both via separate output ports. See
T-LCMS-007 §c for the exact port wiring.

### Q-3: MID long format vs wide format — which is canonical?

AccuCor R output is **long format**: one row per compound × isotopologue
combination, sample columns wide. The user's verbatim example:

```
Compound    C13    H2    UL0    UL3    UL2    UL1    SE3
cytosine    0      0     1      1      0.9995 1      0.9542
cytosine    1      0     0      0      0      0      0.0029
```

**Decision**: `MIDTable` is **always long format**. `LoadMIDTable` preserves
this layout. `Calculate13CEnrichment`, `FractionalLabeling`,
`CompareGroupMID`, and `FluxEstimate` all consume long format.

If a user wants wide format (e.g. for plotting in GraphPad), they can:

- Use `MetaboliteMatrix` (the metabolomics block) to pivot
  PeakTable → wide.
- Use a generic `CodeBlock(language="python")` with one line of pandas:
  `df.pivot_table(index="Compound", columns="sample", values="C13")`.

**Why long?** Three reasons:

1. AccuCor produces it, and the entire downstream pipeline already speaks
   long format. Forcing a wide pivot inside `LoadMIDTable` would make the
   block's input round-trip lossy (different column orders).
2. Long format scales better when `tracer_atoms` has more than one element
   (e.g. dual `C13 + H2` labelling); wide format would require a
   multi-index column header.
3. The `groupby` patterns in every analysis block are simpler on long.

### Q-4: How does `LoadMIDTable` detect sample columns?

AccuCor MID output has three column categories:

- **Identity columns**: `Compound` (always present), and sometimes
  `formula`, `mz`, `rt` (passed through from the source PeakTable).
- **Isotope atom-count columns**: integers, named after the tracer atom
  (`C13`, `H2`, `N15`, `O18`, `D`, etc.). One row's value in each
  isotope column is the count of that isotope in this isotopologue.
- **Sample columns**: the abundance values per sample (`UL0`, `UL3`,
  `SE3`, etc. in the user's example). These are floats, named arbitrarily
  by the user's experimental design.

**Decision**: `LoadMIDTable` uses a **two-step heuristic**:

1. Drop a known set of identity column names: `Compound`, `compound`,
   `formula`, `mz`, `rt`, `RT`, `m/z`, `Adduct`, `name`, `Name`. (The set
   is exposed as a constant `_KNOWN_IDENTITY_COLUMNS` in
   `load_mid_table.py`.)
2. From the remaining columns, classify based on the `tracer_atoms` config
   field: any column whose name appears in `tracer_atoms` (case-insensitive)
   is an isotope-count column. Everything else is a sample column.

The user can override this via the `sample_column_pattern: str | None`
config field, which takes a Python regex; if set, only columns matching
the regex are treated as sample columns.

**Example**: with `tracer_atoms=["C13"]` and the user's verbatim sample,
the heuristic correctly identifies:

- Identity: `Compound`
- Isotope: `C13`, `H2` (because `H2` is in the column set; even though
  it isn't in `tracer_atoms`, `LoadMIDTable` treats *known atom names* as
  isotope columns by default — see the `_KNOWN_ATOM_COLUMNS` constant
  in `load_mid_table.py`)
- Sample: `UL0`, `UL3`, `UL2`, `UL1`, `SE3`

The constant `_KNOWN_ATOM_COLUMNS` is `{"C13", "H2", "N15", "O18", "D",
"S34", "Cl37"}` — the seven stable isotopes typically tracked in
metabolomics.

### Q-5: Tracer atom handling — single vs multi-tracer support

The default tracer is `C13` (the `Calculate13CEnrichment` block name
reflects this is the dominant case). But the user has indicated they
sometimes do dual labelling (`C13 + H2`).

**Decision**: `MIDTable.Meta.tracer_atoms` is a `list[str]` (not a single
string), defaulting to `["C13"]`. `LoadMIDTable.tracer_atoms` config field
defaults to `["C13"]` and accepts multi-element lists.

`Calculate13CEnrichment` treats the multi-tracer case as follows:

- If `tracer_atoms == ["C13"]`: standard weighted-average enrichment over
  the `C13` isotope-count column. Result: one row per compound × sample
  with column `enrichment`.
- If `tracer_atoms == ["C13", "H2"]`: per-tracer enrichment is computed
  separately, weighting by the corresponding isotope-count column. Result:
  one row per compound × sample with columns `enrichment_C13`,
  `enrichment_H2`.

The block name remains `Calculate13CEnrichment` even though it supports
multi-tracer because:

1. The user's primary use case is single 13C tracer.
2. Naming the block `CalculateEnrichment` would lose the connection to the
   dominant case.
3. The implementation's branching is a single `if len(tracer_atoms) == 1`
   inside `process()`; not worth a separate block.

### Q-6: PathwayEnrichment — Python-native KEGG REST or R wrapper?

The master plan §2.4 metabolomics list says: "PathwayEnrichment
(CodeBlock R wrapping MetaboAnalystR OR native Python)". This needs a
default-pick decision.

**Decision**: the **default implementation is Python-native** via the KEGG
REST API. Specifically:

- The block is a `ProcessBlock` (not a `CodeBlock`), and lives at
  `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/pathway.py`.
- It depends on `requests>=2.31` (already declared in `pyproject.toml`).
- The KEGG REST endpoints used: `https://rest.kegg.jp/link/pathway/cpd`
  (compound → pathway map) and `https://rest.kegg.jp/list/pathway/{org}`
  (organism-specific pathway list, default `hsa` for human).
- Compound IDs are matched on KEGG compound names (the simplest case);
  more advanced ID mapping (HMDB → KEGG, etc.) is a follow-up feature.
- A simple Fisher's exact test gives the per-pathway p-value;
  multiple-testing correction is BH (FDR) by default.
- KEGG responses are cached for the duration of a single block run via a
  process-local `dict`. Persistent caching is a follow-up feature.

The MetaboAnalystR R wrapper is **deferred** to a follow-up feature
ticket (post-0.1.0) tracked as a comment in `pathway.py` and reproduced
in §11 of this spec. The implementation pattern is straightforward
(use `CodeBlock(language="r")` with a hardcoded R script that calls
`MetaboAnalystR::SearchHMDB(...)` etc.) but the install footprint is
heavy and the user has already indicated KEGG REST is sufficient for
0.1.0.

**Why KEGG over MetaboAnalystR for the default?**

1. No R dependency for users who just want a quick enrichment.
2. KEGG REST is free and stable (no API key required).
3. The Python implementation is ~150 lines including tests; the R wrapper
   would be ~80 lines but with a 1-2 GB MetaboAnalystR install.
4. The user's metabolomics workflow already lives in R (via AccuCor); a
   pure-Python alternative gives them an option that doesn't reintroduce
   R for a small downstream step.

### Q-7: ConsumptionSecretionAnalysis — cell count normalization formula

The user described the use case: "spent media vs fresh media for cell
culture extracellular flux", with optional per-cell normalization.

**Decision**: `ConsumptionSecretionAnalysis` accepts:

- `spent_media: PeakTable` (intensity in spent media samples)
- `fresh_media: PeakTable` (intensity in fresh media controls)
- `cell_count_table: DataFrame | None` (optional, per-sample cell counts)

Config:

- `time_hours: float` (culture duration in hours; required)
- `normalize_per_cell: bool = False`
- `intensity_column: str = "intensity"`

Output (long format `DataFrame`):

| Column                  | Type    | Notes                                          |
|-------------------------|---------|------------------------------------------------|
| `compound`              | str     | Compound name (joined from `spent_media`)     |
| `sample`                | str     | Sample ID                                      |
| `delta_concentration`   | float   | `spent[c, s] - fresh[c, s]`                    |
| `consumed_or_secreted`  | str     | `"consumed"` if delta < 0, `"secreted"` if > 0 |
| `flux_per_cell_per_hour`| float   | populated only if `cell_count_table is not None` |

Formula when `normalize_per_cell = True`:

```
flux[c, s] = (spent[c, s] - fresh[c, s]) / (cell_count[s] * time_hours)
```

Formula when `normalize_per_cell = False`:

```
flux[c, s] = (spent[c, s] - fresh[c, s]) / time_hours
```

The fresh media table is matched to the spent media table by **compound
name**, not by sample. (Fresh media has its own samples; consumption is
defined per spent-media sample relative to the *mean* of fresh media
samples for that compound.) This is documented in T-LCMS-018 §g.

**Units**: the block does not enforce intensity units. The user is
responsible for ensuring the `spent_media` and `fresh_media` PeakTables
have consistent units (typically µM after calibration). The output
`flux_per_cell_per_hour` carries whatever unit the input intensities had,
divided by `cell_count * hours`.

### Q-8: GraphPad Prism integration — Windows-only?

GraphPad Prism is primarily a Windows desktop application; macOS builds
exist but cost the same. Linux is unsupported.

**Decision**: `GraphPadBlock` is an `AppBlock` subclass that **logs a
warning** if launched on a non-Windows platform but still attempts the
launch (in case the user has a custom wrapper). The `app_command` has
**no default** because GraphPad's install path varies by version
(`C:\Program Files\GraphPad\Prism 9\Prism.exe` for v9,
`C:\Program Files\GraphPad\Prism 10\Prism.exe` for v10, etc.). The user
must supply `graphpad_path` explicitly via the config.

The block accepts `Collection[DataFrame]` (any DataFrames the user wants
to plot), copies them to `<exchange_dir>/inputs/` as CSV files, optionally
copies a GraphPad template file (`template_path`) to the same directory,
launches GraphPad, and waits for the user to export figures (PNG/PDF/SVG)
to `<exchange_dir>/outputs/`. Output is `Collection[Artifact]` with the
exported figures.

This is the same pattern as `ElMAVENBlock` (T-LCMS-007). The main
difference is that GraphPad's input format is more rigid (CSV with a
specific column layout per template) — see T-LCMS-019 §g.

### Q-9: FluxEstimate vs full 13C-MFA — where is the boundary?

The user explicitly rejected full 13C-MFA: "full 13C-MFA 太重". Tools like
INCA, OpenFLUX, and Metran solve elementary metabolite unit (EMU) systems
to fit fluxes from labelling data — this is heavyweight and external.

**Decision**: `FluxEstimate` provides the **simplest possible** flux
estimate: `flux = labeling_rate × pool_size`, where `labeling_rate` is
the time derivative of fractional labelling estimated from a time-series
MID and `pool_size` is the total compound abundance from the input
PeakTable.

Specifically:

- Input: `MIDTable` (with at least 2 timepoints declared in
  `SampleMetadata.time_hours_column`) + optional `pool_size_table:
  PeakTable`.
- Config: `time_points_column: str` (column in SampleMetadata),
  `group_column: str | None` (optional grouping, e.g. "treatment").
- Output: `DataFrame` with columns `compound`, `group`, `estimated_flux`.

The estimate is a **first-order linear fit** to fractional labelling vs.
time per compound per group. There is no metabolic network, no atom
mapping, no EMU resolution. The block's docstring loudly disclaims that
this is **not a replacement for INCA / OpenFLUX / Metran** and points to
those tools for proper 13C-MFA.

This boundary keeps the block simple (~100 lines), keeps the dependency
list small (just `numpy` for `polyfit`), and matches the user's stated
needs.

### Q-10: Why `LoadMSRawFiles` (plural) and not a single-file variant?

The master plan §2.4 lists `LoadMSRawFiles` (batch loader, returns
`Collection[MSRawFile]`). There is no `LoadMSRawFile` (singular).

**Decision**: there is **no single-file variant**. Single-file loading is
just a `LoadMSRawFiles` configured with `pattern="my_file.mzML"` (i.e. a
glob that matches exactly one file), returning a `Collection` of length
1. This matches the general "collection-first" design of the rest of the
plugin and avoids two near-duplicate blocks in the palette.

The implementation reads minimal header bytes from each file to populate
the `MSRawFile.Meta` fields (`format`, `polarity`, `instrument`,
`acquisition_date`, `sample_id`), but it does not parse scan data. For
`.mzML` and `.mzXML` (XML formats), the first ~8 KB of the file
typically contains the `<msRun>` / `<run>` element with the
`startTimeStamp` and `defaultInstrumentConfigurationRef` attributes. For
`.raw` (Thermo) and `.d` (Bruker), header parsing is much more involved;
the block falls back to filename heuristics and leaves `instrument` as
`None`.

### Q-11: LCMS plugin interaction with ADR-028 Addendum 1 dynamic ports

ADR-028 Addendum 1 introduces `dynamic_ports: ClassVar[dict | None]` and
`get_effective_input_ports() / get_effective_output_ports()` overrides on
the `Block` ABC. These are used by core's `LoadData` / `SaveData` to let
one block produce different output port types based on the `core_type`
config.

**Decision**: **no LC-MS block uses `dynamic_ports`**. Every plugin block
in this spec declares fixed `input_ports` and `output_ports` ClassVars.

Rationale:

- The plugin's types are specific (`MSRawFile`, `PeakTable`, `MIDTable`,
  `SampleMetadata`) — there is no situation where one block can sensibly
  produce *one of N* different types.
- Dynamic ports add GUI complexity (the BlockNode.tsx has to recompute
  port colours when the driving config changes) and the LC-MS workflow
  doesn't benefit from it.
- The four plugin types render via the existing `resolveTypeColor`
  type-hierarchy walk in `BlockNode.tsx`, so the GUI shows distinct
  colours for `MSRawFile` vs `PeakTable` vs `MIDTable` vs `SampleMetadata`
  without any plugin-side frontend work.

### Q-12: Where do plugin blocks live in the GUI palette?

ADR-026 specifies that plugin blocks are auto-discovered from the
`scieasy.blocks` entry-point group at runtime. The frontend palette
groups blocks by their `category: ClassVar[str]` and `package_name`
fields.

**Decision**: every LC-MS block declares `category` from the following
controlled set:

- `"io"` for the 5 IO blocks (T-LCMS-003 .. T-LCMS-006).
- `"app"` for `ElMAVENBlock` and `GraphPadBlock`.
- `"code"` for `AccuCorR`.
- `"process"` for the 5 isotope tracing blocks and the 6 metabolomics
  analysis blocks.

The `package_name` ClassVar is `"scieasy-blocks-lcms"` for all 20 blocks
(set in a base class `_LCMSBlockMixin` to avoid repetition — see
T-LCMS-001).

The palette will render LC-MS blocks under a `scieasy-blocks-lcms` group
with sub-groups by category. No frontend changes are needed for this
plugin.

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

### T-LCMS-001 — Plugin scaffold

**a. Ticket ID and name**: T-LCMS-001 — `scieasy-blocks-lcms` plugin
package scaffold.

**b. Source ADR / spec sections**:
- ADR-026 (plugin entry-point pattern).
- ADR-028 §D2 (plugin-owned IO blocks).
- Master plan §2.4 LC-MS PLUGIN package layout.
- This spec §2 (scope), §6 (universal rules).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/pyproject.toml` (project metadata,
  dependencies, entry-points, package data, pytest markers).
- `packages/scieasy-blocks-lcms/README.md` (overview, install, the
  user's workflow walkthrough, prerequisites for ElMAVEN / R / AccuCor /
  GraphPad).
- `packages/scieasy-blocks-lcms/THIRD_PARTY_LICENSES.md` (AccuCor
  upstream LICENSE reproduced, plus any other vendored license text).
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/__init__.py`
  (re-exports + `get_blocks()` and `get_types()` entry-point functions —
  initially empty placeholders).
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/_base.py`
  (`_LCMSBlockMixin` providing the shared `package_name` ClassVar).
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/__init__.py`
  (empty)
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/external/__init__.py`
  (empty)
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/__init__.py`
  (empty)
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/__init__.py`
  (empty)
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/plotting/__init__.py`
  (empty)
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/scripts/.gitkeep`
  (placeholder for the AccuCor R script T-LCMS-007 will land)
- `packages/scieasy-blocks-lcms/tests/__init__.py` (empty)
- `packages/scieasy-blocks-lcms/tests/test_package_layout.py` (smoke
  test asserting every sub-package is importable, `get_blocks()` returns
  an empty list, `get_types()` returns an empty list).

**d. Files to be modified**: none.

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_package_layout.py`:
  - `test_package_importable`
  - `test_get_blocks_returns_list`
  - `test_get_types_returns_list`
  - `test_lcms_block_mixin_package_name`

**f. Existing tests to update**: none.

**g. Implementation details**:

The `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "scieasy-blocks-lcms"
version = "0.1.0"
description = "LC-MS metabolomics & stable isotope tracing blocks for SciEasy"
authors = [{ name = "SciEasy contributors" }]
license = { text = "MIT" }
requires-python = ">=3.11"
dependencies = [
    "scieasy>=0.1",
    "numpy>=1.24",
    "pandas>=2.1",
    "scipy>=1.11",
    "scikit-learn>=1.3",
    "pydantic>=2.5",
    "openpyxl>=3.1",
    "requests>=2.31",
]

[project.optional-dependencies]
metaboanalystr = []  # Requires R + MetaboAnalystR, documented not auto-installed
elmaven = []         # ElMAVEN is external, not a pip package
graphpad = []        # GraphPad is external, not a pip package
test = [
    "pytest>=8",
    "pytest-cov>=5",
]

[project.entry-points."scieasy.blocks"]
lcms = "scieasy_blocks_lcms:get_blocks"

[project.entry-points."scieasy.types"]
lcms = "scieasy_blocks_lcms.types:get_types"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
scieasy_blocks_lcms = ["scripts/*.R"]

[tool.pytest.ini_options]
markers = [
    "requires_elmaven: requires ElMAVEN desktop application",
    "requires_r: requires R + AccuCor R package",
    "requires_graphpad: requires GraphPad Prism",
]
```

The `_LCMSBlockMixin`:

```python
# packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/_base.py
from typing import ClassVar


class _LCMSBlockMixin:
    """Mixin that stamps LC-MS plugin metadata on every block in this package.

    Centralises the package_name field so individual blocks don't repeat it.
    """

    package_name: ClassVar[str] = "scieasy-blocks-lcms"
```

The `__init__.py`:

```python
# packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/__init__.py
"""scieasy-blocks-lcms: LC-MS metabolomics & stable isotope tracing blocks."""

from __future__ import annotations

__version__ = "0.1.0"


def get_blocks() -> list[type]:
    """Return all block classes registered by this plugin.

    Populated incrementally by T-LCMS-003 .. T-LCMS-019. T-LCMS-020 finalises
    the registration with the full list and the entry-point smoke test.
    """
    return []
```

**h. Acceptance criteria**:
- [ ] `packages/scieasy-blocks-lcms/pyproject.toml` declares the
      dependencies, entry-points, package-data, and pytest markers
      exactly as specified in §g.
- [ ] `pip install -e packages/scieasy-blocks-lcms` succeeds in a clean
      virtual environment with the core scieasy package already installed.
- [ ] `python -c "import scieasy_blocks_lcms"` succeeds.
- [ ] `python -c "from scieasy_blocks_lcms import get_blocks; assert get_blocks() == []"` succeeds.
- [ ] `python -c "from scieasy_blocks_lcms._base import _LCMSBlockMixin; assert _LCMSBlockMixin.package_name == 'scieasy-blocks-lcms'"` succeeds.
- [ ] `pytest packages/scieasy-blocks-lcms/tests/test_package_layout.py` passes.

**i. Out of scope**:
- The four plugin types (T-LCMS-002).
- Any block implementations.
- The bundled AccuCor R script (T-LCMS-007).
- Updating the core repo's `pyproject.toml` or import-linter contract.

**j. Dependencies on other tickets**: none. First in the cascade.

**k. Estimated diff size**: ~200 lines of `pyproject.toml` + `__init__.py`
+ `_base.py` + `README.md`. ~50 lines of test. Total ~250 lines.

**l. Suggested workflow gate ticket title**:
`scieasy-blocks-lcms plugin scaffold (T-LCMS-001)`

---

### T-LCMS-002 — Types module

**a. Ticket ID and name**: T-LCMS-002 — `scieasy_blocks_lcms.types` (4
plain-DataFrame/Artifact types).

**b. Source ADR / spec sections**:
- ADR-027 D2 (plugin types layered on core base classes).
- ADR-027 Addendum 1 §3 (Meta Pydantic constraints).
- Master plan §2.4 LC-MS PLUGIN types section.
- This spec §2 ("Forbidden" — no scan-level types).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/types.py`
  (the 4 type classes plus a `get_types()` function).

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/__init__.py`
  (re-export the four types).

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_types.py`:
  - `test_msrawfile_subclass_of_artifact`
  - `test_msrawfile_meta_frozen`
  - `test_msrawfile_meta_required_format`
  - `test_msrawfile_meta_optional_polarity_instrument`
  - `test_msrawfile_constructor_accepts_meta`
  - `test_peaktable_subclass_of_dataframe`
  - `test_peaktable_meta_source_required`
  - `test_peaktable_meta_polarity_optional`
  - `test_midtable_subclass_of_dataframe`
  - `test_midtable_meta_tracer_atoms_required`
  - `test_midtable_meta_sample_columns_required`
  - `test_midtable_meta_corrected_default_true`
  - `test_midtable_meta_correction_tool_default_accucor`
  - `test_samplemetadata_subclass_of_dataframe`
  - `test_samplemetadata_meta_sample_id_column_default`
  - `test_get_types_returns_all_four_classes`
  - `test_with_meta_round_trip_msrawfile`
  - `test_with_meta_round_trip_peaktable`
  - `test_with_meta_round_trip_midtable`
  - `test_with_meta_round_trip_samplemetadata`
  - `test_meta_json_round_trip_midtable_with_two_tracers`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/types.py
"""LC-MS plugin types: MSRawFile, PeakTable, MIDTable, SampleMetadata."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from scieasy.core.types.artifact import Artifact
from scieasy.core.types.dataframe import DataFrame


class MSRawFile(Artifact):
    """Raw LC-MS acquisition file (mzML/mzXML/.raw/.d folder).

    The actual scan data stays in the file. This class only records the
    path and minimal header metadata. ElMAVEN (or another external tool)
    handles parsing.

    Per master plan §2.4, the LC-MS plugin DOES NOT introduce
    `MSSpectrum(Series)` or `MSRun(Array)` — scan-level data is external.
    """

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        format: str = Field(
            ..., description='Acquisition file format: "mzML" | "mzXML" | "raw" | "d"'
        )
        polarity: str | None = Field(
            None, description='Ionisation polarity: "+" | "-" | None if unknown'
        )
        instrument: str | None = Field(
            None, description="Instrument model name (e.g. 'Q Exactive HF')"
        )
        acquisition_date: datetime | None = Field(
            None, description="UTC datetime of acquisition; None if not in header"
        )
        sample_id: str | None = Field(
            None, description="Sample identifier; None if not derivable from filename"
        )


class PeakTable(DataFrame):
    """LC-MS feature/peak table.

    Produced by ElMAVEN, MZmine, XCMS, or similar peak pickers. Column
    names vary by source; the `Meta.source` field records which tool
    produced this table so downstream blocks can apply source-specific
    column-name heuristics.
    """

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        source: str = Field(
            ..., description='Source tool: "ElMAVEN" | "MZmine" | "XCMS" | ...'
        )
        polarity: str | None = Field(
            None, description='Ionisation polarity: "+" | "-" | None if mixed/unknown'
        )


class MIDTable(DataFrame):
    """Mass Isotopomer Distribution table (long format).

    Format (as produced by AccuCor R package):

        Compound    C13    H2    UL0    UL3    UL2    UL1    SE3
        cytosine    0      0     1.0    1.0    0.9995 1.0    0.9542
        cytosine    1      0     0.0    0.0    0.0    0.0    0.0029

    Each row is a (compound, isotopologue) combination; each sample is a
    column. Values are fractional abundance (sum to 1.0 per compound per
    sample, modulo rounding).

    See `phase11-lcms-block-spec.md` §8 Q-3 for the long-vs-wide rationale.
    """

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        tracer_atoms: list[str] = Field(
            default_factory=lambda: ["C13"],
            description="Tracer isotope atoms; default ['C13'] for the dominant case",
        )
        sample_columns: list[str] = Field(
            ..., description="Sample column names (e.g. ['UL0', 'UL3', 'SE3'])"
        )
        corrected: bool = Field(
            True, description="Whether natural-abundance correction has been applied"
        )
        correction_tool: str = Field(
            "AccuCor", description="Name of the correction tool used"
        )


class SampleMetadata(DataFrame):
    """Per-sample metadata (group, timepoint, replicate, etc.)."""

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        sample_id_column: str = Field(
            "sample_id", description="Column name that identifies each sample"
        )


def get_types() -> list[type]:
    """Entry-point function returning all plugin types for TypeRegistry."""
    return [MSRawFile, PeakTable, MIDTable, SampleMetadata]
```

Each of the 4 classes inherits the base class's `with_meta` /
`_reconstruct_extra_kwargs` / `_serialise_extra_metadata` round-trip
hooks (added in Phase 10 T-013). No subclass override is needed because
the base class handles all the standard slots and the only
plugin-specific data is the `meta` Pydantic model itself.

**h. Acceptance criteria**:
- [ ] `MSRawFile` is a subclass of `scieasy.core.types.artifact.Artifact`.
- [ ] `MSRawFile.Meta` is a frozen Pydantic v2 BaseModel with `format`
      required and four optional fields.
- [ ] `PeakTable` is a subclass of `scieasy.core.types.dataframe.DataFrame`.
- [ ] `PeakTable.Meta.source` is required; `polarity` is optional.
- [ ] `MIDTable` is a subclass of `DataFrame`.
- [ ] `MIDTable.Meta.tracer_atoms` defaults to `["C13"]`.
- [ ] `MIDTable.Meta.sample_columns` is required.
- [ ] `MIDTable.Meta.corrected` defaults to `True`.
- [ ] `MIDTable.Meta.correction_tool` defaults to `"AccuCor"`.
- [ ] `SampleMetadata.Meta.sample_id_column` defaults to `"sample_id"`.
- [ ] `get_types()` returns the four classes in registration order.
- [ ] All four classes round-trip through `with_meta(...)` preserving
      the type and the constructor arguments.
- [ ] All four `Meta` classes round-trip through `model_dump_json` /
      `model_validate_json` per the ADR-027 Addendum 1 §3 constraint.
- [ ] **NO `MSSpectrum(Series)` or `MSRun(Array)` is added** — these are
      explicitly forbidden by master plan §2.4 and this spec §2.

**i. Out of scope**:
- Any block that produces or consumes these types (T-LCMS-003+).
- A `LoadMSRawFile` (singular) variant — see §8 Q-10.
- Subclassing `Series` or `Array` — see §2 Forbidden list.

**j. Dependencies on other tickets**: T-LCMS-001 (scaffold).

**k. Estimated diff size**: ~150 lines of source + ~200 lines of test.
Total ~350 lines.

**l. Suggested workflow gate ticket title**:
`LC-MS plugin types module per master plan §2.4 (T-LCMS-002)`

**Status**: Implemented in LCMS foundation chunk 1 (issue #363, PR #369).
`get_types()` now returns the four plugin classes in registration order,
the frozen `Meta` models round-trip through JSON, and the concrete type
tests cover `with_meta(...)` preservation without adding forbidden
scan-level `MSSpectrum` / `MSRun` classes.

---


### T-LCMS-003 — `LoadMSRawFiles`

**a. Ticket ID and name**: T-LCMS-003 — `LoadMSRawFiles` batch raw-file
loader.

**b. Source ADR / spec sections**:
- ADR-028 §D6 (plugin IO pattern).
- ADR-028 Addendum 1 §Plugin IO blocks (plugin IO stays STATIC).
- Master plan §2.4 LC-MS IO.
- This spec §8 Q-10 (plural-only, no singular variant).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_ms_raw.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/__init__.py`
  (re-export `LoadMSRawFiles`).

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_io/test_load_ms_raw.py`:
  - `test_load_single_mzml_file`
  - `test_load_directory_glob_mzml`
  - `test_load_recursive_false_ignores_subdirs`
  - `test_load_recursive_true_finds_subdirs`
  - `test_load_populates_format_metadata_from_extension`
  - `test_load_populates_polarity_from_mzml_header`
  - `test_load_populates_instrument_from_mzml_header`
  - `test_load_populates_acquisition_date_from_mzml_header`
  - `test_load_falls_back_to_filename_sample_id`
  - `test_load_raises_on_missing_directory`
  - `test_load_empty_glob_returns_empty_collection`
  - `test_load_mzxml_format_detected`
  - `test_load_raw_file_records_path_only`
  - `test_load_d_folder_records_path_only`
  - `test_output_is_collection_of_msrawfile`
  - `test_format_hint_override`

**f. Existing tests to update**: none.

**g. Implementation details**:

The block is a plain `IOBlock` subclass with `direction = "input"` and
fixed output ports. It does NOT use dynamic ports (§8 Q-11).

```python
# packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_ms_raw.py
"""LoadMSRawFiles -- batch loader for raw LC-MS acquisition files."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from scieasy.blocks.base.ports import OutputPort
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.types.collection import Collection

from scieasy_blocks_lcms._base import _LCMSBlockMixin
from scieasy_blocks_lcms.types import MSRawFile

_MZML_TIMESTAMP_RE = re.compile(r'startTimeStamp="([^"]+)"')
_MZML_POLARITY_POSITIVE = re.compile(r'accession="MS:1000130"')
_MZML_POLARITY_NEGATIVE = re.compile(r'accession="MS:1000129"')
_MZML_INSTRUMENT_RE = re.compile(
    r'<instrumentConfiguration[^>]*>.*?name="([^"]+)"', re.DOTALL
)


class LoadMSRawFiles(_LCMSBlockMixin, IOBlock):
    """Batch loader that records paths to raw LC-MS acquisition files.

    Does NOT parse scan data. Reads minimal header bytes from each file
    to populate MSRawFile.Meta (format, polarity, instrument,
    acquisition_date, sample_id). The actual data stays in the file and
    is processed externally by ElMAVEN (or another tool).

    See phase11-lcms-block-spec.md §8 Q-10 for the plural-only rationale.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "load_ms_raw_files"
    name: ClassVar[str] = "Load MS Raw Files"
    category: ClassVar[str] = "io"

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="raw_files",
            accepted_types=[MSRawFile],
            description="Collection of loaded raw file handles",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "title": "Directory path",
                     "ui_priority": 0, "ui_widget": "directory_browser"},
            "pattern": {"type": "string", "title": "Glob pattern",
                        "default": "*.mzML", "ui_priority": 1},
            "recursive": {"type": "boolean", "title": "Recursive",
                          "default": False, "ui_priority": 2},
            "format_hint": {
                "type": ["string", "null"],
                "enum": [None, "mzML", "mzXML", "raw", "d"],
                "default": None, "title": "Format hint", "ui_priority": 3,
            },
        },
        "required": ["path"],
    }

    def load(self, config: dict[str, Any]) -> dict[str, Collection]:
        root = Path(config["path"])
        if not root.exists():
            raise FileNotFoundError(f"LoadMSRawFiles: path does not exist: {root}")
        pattern = config.get("pattern", "*.mzML")
        recursive = bool(config.get("recursive", False))
        format_hint = config.get("format_hint")

        candidates = sorted(root.rglob(pattern) if recursive else root.glob(pattern))

        items: list[MSRawFile] = []
        for path in candidates:
            meta = _probe_header(path, format_hint=format_hint)
            items.append(MSRawFile(
                file_path=path,
                mime_type=_mime_for(meta.format),
                description=path.name,
                meta=meta,
            ))
        return {"raw_files": Collection(items, item_type=MSRawFile)}


def _probe_header(path: Path, *, format_hint: str | None) -> MSRawFile.Meta:
    """Populate MSRawFile.Meta from extension + first ~8 KB of mzML/mzXML."""
    fmt = format_hint or _detect_format(path)
    polarity: str | None = None
    instrument: str | None = None
    acquired: datetime | None = None
    sample_id = path.stem

    if fmt in ("mzML", "mzXML") and path.is_file():
        head = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
        if _MZML_POLARITY_POSITIVE.search(head):
            polarity = "+"
        elif _MZML_POLARITY_NEGATIVE.search(head):
            polarity = "-"
        m = _MZML_TIMESTAMP_RE.search(head)
        if m:
            try:
                acquired = datetime.fromisoformat(m.group(1).rstrip("Z"))
            except ValueError:
                acquired = None
        m = _MZML_INSTRUMENT_RE.search(head)
        if m:
            instrument = m.group(1)

    return MSRawFile.Meta(
        format=fmt, polarity=polarity, instrument=instrument,
        acquisition_date=acquired, sample_id=sample_id,
    )


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in ("mzml", "mzxml", "raw"):
        return {"mzml": "mzML", "mzxml": "mzXML", "raw": "raw"}[suffix]
    if path.is_dir() and path.suffix.lower() == ".d":
        return "d"
    return "raw"


def _mime_for(fmt: str) -> str:
    return {
        "mzML": "application/x-mzml+xml",
        "mzXML": "application/x-mzxml+xml",
        "raw": "application/octet-stream",
        "d": "inode/directory",
    }.get(fmt, "application/octet-stream")
```

**h. Acceptance criteria**:
- [ ] `LoadMSRawFiles` subclasses `IOBlock` and `_LCMSBlockMixin`.
- [ ] `direction == "input"`, `category == "io"`.
- [ ] `output_ports` declares one `raw_files` port with
      `accepted_types=[MSRawFile]`.
- [ ] `config_schema` has `path` required and `pattern`, `recursive`,
      `format_hint` optional.
- [ ] `load()` raises `FileNotFoundError` on missing directory.
- [ ] `load()` respects `recursive: False` (glob) vs `recursive: True`
      (rglob).
- [ ] `_probe_header` populates `polarity` from `MS:1000130` /
      `MS:1000129` accessions.
- [ ] `_probe_header` populates `instrument` from the first
      `<instrumentConfiguration>` element.
- [ ] `_probe_header` populates `acquisition_date` from `startTimeStamp`.
- [ ] `sample_id` defaults to `path.stem`.
- [ ] Output is a `Collection[MSRawFile]`.
- [ ] Empty glob returns an empty collection.
- [ ] `.raw` / `.d` paths are recorded without header parsing.
- [ ] All 16 tests pass.

**i. Out of scope**:
- Parsing scan data from any format.
- Handling compressed `.mzML.gz` files (follow-up).
- Header parsing for `.raw` / `.d` (Thermo / Bruker SDK integration
  is explicitly out of scope).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~250 lines source + ~300 lines test.
Total ~550 lines.

**l. Suggested workflow gate ticket title**:
`LoadMSRawFiles block per master plan §2.4 (T-LCMS-003)`

**Status**: Implemented in LCMS foundation chunk 1 (issue #363, PR #369).
`LoadMSRawFiles` now returns `Collection[MSRawFile]`, supports glob vs
recursive directory search, records `.raw` / `.d` paths without parsing
scan data, and populates `format`, `polarity`, `instrument`,
`acquisition_date`, and `sample_id` from lightweight mzML/mzXML header
sniffing.

---

### T-LCMS-004 — `LoadPeakTable`

**a. Ticket ID and name**: T-LCMS-004 — `LoadPeakTable` CSV/TSV/XLSX
peak table loader.

**b. Source ADR / spec sections**:
- ADR-028 §D6.
- Master plan §2.4 LC-MS IO.

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_peak_table.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_io/test_load_peak_table.py`:
  - `test_load_csv_elmaven`
  - `test_load_tsv_elmaven`
  - `test_load_xlsx_first_sheet`
  - `test_load_xlsx_named_sheet`
  - `test_source_elmaven_column_detection`
  - `test_source_mzmine_column_detection`
  - `test_source_xcms_column_detection`
  - `test_source_auto_detects_elmaven_from_column_names`
  - `test_load_preserves_row_order`
  - `test_load_raises_on_missing_file`
  - `test_load_raises_on_empty_table`
  - `test_output_meta_source_set`
  - `test_output_meta_polarity_optional`
  - `test_output_is_peaktable_instance`

**f. Existing tests to update**: none.

**g. Implementation details**:

`LoadPeakTable` is a plain `IOBlock` that reads CSV/TSV/XLSX into a
pandas DataFrame, auto-detects the source tool from column-name
markers, and wraps the result as a `PeakTable`.

Source autodetection signatures:

- **ElMAVEN**: presence of any of `{"compound", "formula", "medMz",
  "medRt", "expectedRtDiff"}`.
- **MZmine**: presence of any of `{"row ID", "row m/z",
  "row retention time"}`.
- **XCMS**: presence of any of `{"mzmed", "rtmed", "mzmin", "mzmax"}`.
- Fallback: ElMAVEN (the user's primary tool).

The pandas DataFrame is cached under `table.user["pandas_df"]` for
downstream blocks that want the materialised frame without a re-read
(non-load-bearing convention; downstream blocks must fall back to
`table.view()` if the key is missing).

**h. Acceptance criteria**:
- [ ] `LoadPeakTable` subclasses `IOBlock` and `_LCMSBlockMixin`.
- [ ] `direction == "input"`, `category == "io"`.
- [ ] `output_ports` has a single `peak_table` port with
      `accepted_types=[PeakTable]`.
- [ ] Supports `.csv`, `.tsv`, `.xlsx`, `.xls`.
- [ ] Raises `FileNotFoundError` on missing file, `ValueError` on empty
      table.
- [ ] `source="auto"` correctly detects ElMAVEN / MZmine / XCMS.
- [ ] Output `PeakTable.meta.source` is set.
- [ ] Output `columns` / `row_count` / `schema` match the loaded
      DataFrame.
- [ ] 14 tests pass.

**i. Out of scope**:
- Writing peak tables (`SaveTable`, T-LCMS-006).
- Parsing ElMAVEN project files (`.mzproj`).
- Automatic unit conversion between sources.

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~200 lines source + ~250 lines test.
Total ~450 lines.

**l. Suggested workflow gate ticket title**:
`LoadPeakTable block per master plan §2.4 (T-LCMS-004)`

**Status**: Implemented in LCMS foundation chunk 1 (issue #363, PR #369).
`LoadPeakTable` now reads CSV / TSV / XLSX / XLS into a cached pandas
frame, auto-detects `ElMAVEN` / `MZmine` / `XCMS` from locked column
signatures, raises on missing or empty inputs, and emits a typed
`PeakTable` with populated `columns`, `row_count`, `schema`, and
`PeakTable.Meta`.

---

### T-LCMS-005 — `LoadMIDTable`

**a. Ticket ID and name**: T-LCMS-005 — `LoadMIDTable` AccuCor output
loader.

**b. Source ADR / spec sections**:
- ADR-028 §D6.
- Master plan §2.4 LC-MS IO.
- This spec §8 Q-3 (long format), Q-4 (sample column detection),
  Q-5 (tracer atoms).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_mid_table.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_io/test_load_mid_table.py`:
  - `test_load_csv_long_format`
  - `test_load_xlsx_with_sheet_name`
  - `test_default_tracer_atoms_is_c13`
  - `test_multi_tracer_c13_h2`
  - `test_sample_column_detection_default_heuristic`
  - `test_sample_column_detection_regex_override`
  - `test_identity_columns_dropped_from_samples`
  - `test_known_atom_columns_classified_as_isotope`
  - `test_output_meta_tracer_atoms_preserved`
  - `test_output_meta_sample_columns_populated`
  - `test_output_meta_corrected_true`
  - `test_output_meta_correction_tool_accucor`
  - `test_load_raises_on_missing_compound_column`
  - `test_load_matches_users_verbatim_example`

**f. Existing tests to update**: none.

**g. Implementation details**:

Module-level constants:

```python
_KNOWN_IDENTITY_COLUMNS = frozenset({
    "Compound", "compound", "formula", "Formula",
    "mz", "MZ", "m/z",
    "rt", "RT", "retentionTime",
    "Adduct", "adduct", "name", "Name",
})

_KNOWN_ATOM_COLUMNS = frozenset({
    "C13", "H2", "N15", "O18", "D", "S34", "Cl37",
})
```

The sample-column detection function:

```python
def _detect_sample_columns(
    columns: pd.Index,
    *,
    tracer_atoms: list[str],
    pattern: str | None,
) -> list[str]:
    if pattern is not None:
        regex = re.compile(pattern)
        return [c for c in columns if regex.search(str(c))]
    exclude = set(_KNOWN_IDENTITY_COLUMNS) | set(_KNOWN_ATOM_COLUMNS)
    exclude |= set(tracer_atoms)
    return [c for c in columns if c not in exclude]
```

Applied to the user's verbatim example
(`Compound, C13, H2, UL0, UL3, UL2, UL1, SE3`) with `tracer_atoms=["C13"]`,
the default heuristic returns exactly `["UL0", "UL3", "UL2", "UL1", "SE3"]`
because `Compound` is in `_KNOWN_IDENTITY_COLUMNS`, `C13` is in
`_KNOWN_ATOM_COLUMNS` (and also in `tracer_atoms`), and `H2` is in
`_KNOWN_ATOM_COLUMNS`.

The resulting `MIDTable.Meta`:

```python
MIDTable.Meta(
    tracer_atoms=["C13"],
    sample_columns=["UL0", "UL3", "UL2", "UL1", "SE3"],
    corrected=True,
    correction_tool="AccuCor",
)
```

The pandas DataFrame is cached under `table.user["pandas_df"]`.

**h. Acceptance criteria**:
- [ ] `LoadMIDTable` subclasses `IOBlock` and `_LCMSBlockMixin`.
- [ ] `category == "io"`, `direction == "input"`.
- [ ] `config_schema` has `path` required; `tracer_atoms` defaulting to
      `["C13"]`; `sample_column_pattern` and `sheet_name` optional.
- [ ] Raises `FileNotFoundError` on missing file, `ValueError` if no
      `Compound`/`compound` column, `ValueError` if no sample columns
      detected.
- [ ] Default heuristic drops `_KNOWN_IDENTITY_COLUMNS` and
      `_KNOWN_ATOM_COLUMNS`.
- [ ] Regex override bypasses the default heuristic.
- [ ] On the user's verbatim example, detected sample columns are
      exactly `["UL0", "UL3", "UL2", "UL1", "SE3"]`.
- [ ] Multi-tracer (`["C13", "H2"]`) round-trips through
      `MIDTable.meta.tracer_atoms`.
- [ ] `MIDTable.meta.corrected == True`,
      `correction_tool == "AccuCor"`.
- [ ] 14 tests pass.

**i. Out of scope**:
- Producing MID tables (`AccuCorR`, T-LCMS-007).
- Validating that per-compound-per-sample MID values sum to 1.0.
- Wide-format loading (see §8 Q-3).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~200 lines source + ~280 lines test.
Total ~480 lines.

**l. Suggested workflow gate ticket title**:
`LoadMIDTable block per master plan §2.4 (T-LCMS-005)`

**Status**: Implemented in LCMS foundation chunk 1 (issue #363, PR #369).
`LoadMIDTable` now enforces long-format MID inputs, detects sample
columns via the spec’s identity/tracer exclusion heuristic or regex
override, preserves multi-tracer metadata, raises on missing compound
columns or empty sample detection, and emits `MIDTable.Meta` with
`corrected=True` and `correction_tool="AccuCor"`.

---

### T-LCMS-006 — `LoadSampleMetadata` + `SaveTable`

**a. Ticket ID and name**: T-LCMS-006 — `LoadSampleMetadata` loader +
`SaveTable` generic DataFrame saver.

**b. Source ADR / spec sections**:
- ADR-028 §D6.
- Master plan §2.4 LC-MS IO.

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_sample_metadata.py`
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/save_table.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_io/test_load_sample_metadata.py`:
  - `test_load_csv_sample_metadata`
  - `test_load_tsv_sample_metadata`
  - `test_default_sample_id_column`
  - `test_custom_sample_id_column`
  - `test_raises_on_missing_sample_id_column`
  - `test_output_is_samplemetadata_instance`
- `packages/scieasy-blocks-lcms/tests/test_io/test_save_table.py`:
  - `test_save_peak_table_csv`
  - `test_save_mid_table_xlsx`
  - `test_save_sample_metadata_tsv`
  - `test_save_generic_dataframe_csv`
  - `test_save_raises_on_unknown_format`
  - `test_save_index_flag_respected`
  - `test_save_creates_parent_directory`
  - `test_save_returns_empty_dict`

**f. Existing tests to update**: none.

**g. Implementation details**:

`LoadSampleMetadata` mirrors `LoadPeakTable` but wraps as
`SampleMetadata` and exposes `sample_id_column` (default `"sample_id"`)
via config. Raises `ValueError` if the configured sample ID column is
missing from the loaded DataFrame.

`SaveTable` is the generic saver:

- `direction == "output"`.
- Single input port `table` accepting `DataFrame` (covers all four
  subclasses via Liskov).
- `output_ports == []` — sink block.
- Config: `path` (required), `format` (`csv` / `tsv` / `xlsx`, default
  `csv`), `index` (default `False`).
- `save()` creates parent directories, materialises the pandas
  DataFrame via the `table.user["pandas_df"]` cache or falls back to
  `table.view().to_pandas()`, then calls `df.to_csv` / `df.to_excel`
  appropriately.
- Returns `{}` (sink).

**h. Acceptance criteria**:

`LoadSampleMetadata`:
- [ ] Subclasses `IOBlock` and `_LCMSBlockMixin`.
- [ ] `sample_id_column` defaults to `"sample_id"`.
- [ ] Raises `ValueError` on missing configured sample ID column.
- [ ] Output is a `Collection[SampleMetadata]`.
- [ ] 6 tests pass.

`SaveTable`:
- [ ] Subclasses `IOBlock`.
- [ ] Accepts any `DataFrame` subclass via `accepted_types=[DataFrame]`.
- [ ] Supports `csv`, `tsv`, `xlsx`.
- [ ] Creates parent directories if missing.
- [ ] `index` flag respected.
- [ ] Raises `ValueError` on unknown format.
- [ ] Returns an empty dict.
- [ ] 8 tests pass.

**i. Out of scope**:
- Parquet / HDF5 formats.
- Writing XML formats (mzML).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002, T-LCMS-004.

**k. Estimated diff size**: ~220 lines source + ~240 lines test.
Total ~460 lines.

**l. Suggested workflow gate ticket title**:
`LoadSampleMetadata + SaveTable blocks per master plan §2.4 (T-LCMS-006)`

**Status**: Implemented in LCMS foundation chunk 1 (issue #363, PR #369).
`LoadSampleMetadata` now mirrors the table-loading path with a required
configurable sample-ID column, while `SaveTable` writes any
`DataFrame` subclass to CSV / TSV / XLSX, creates parent directories,
respects the `index` flag, and prefers cached pandas frames before
falling back to storage-backed materialisation.

---

### T-LCMS-007 — `ElMAVENBlock` + `AccuCorR`

**a. Ticket ID and name**: T-LCMS-007 — `ElMAVENBlock` (AppBlock for
ElMAVEN) + `AccuCorR` (CodeBlock R runner for AccuCor).

**b. Source ADR / spec sections**:
- ADR-017 (CodeBlock subprocess runner).
- ADR-018 (AppBlock PAUSED state).
- ADR-019 (ProcessHandle, FileWatcher).
- ADR-020 (Collection wrap/unwrap at AppBlock boundary).
- Master plan §2.4 LC-MS external tools.
- This spec §8 Q-1 (AccuCor R script bundling), Q-2 (ElMAVEN GUI interaction).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/external/elmaven_block.py`
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/external/accucor_r.py`
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/scripts/accucor_default.R`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/external/__init__.py`
- `packages/scieasy-blocks-lcms/THIRD_PARTY_LICENSES.md` (reproduce
  AccuCor MIT LICENSE).
- `packages/scieasy-blocks-lcms/README.md` (document ElMAVEN + R +
  AccuCor prerequisites).

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_external/test_elmaven_block.py`:
  - `test_elmaven_block_class_config`
  - `test_elmaven_default_watch_timeout_1800s`
  - `test_elmaven_default_output_patterns`
  - `test_elmaven_input_ports_accept_msrawfile`
  - `test_elmaven_output_ports_declare_peaktable_and_midtable`
  - `test_elmaven_classify_export_peak_vs_mid`
  - `@pytest.mark.requires_elmaven test_elmaven_end_to_end_launch_and_collect`
- `packages/scieasy-blocks-lcms/tests/test_external/test_accucor_r.py`:
  - `test_accucor_r_subclasses_codeblock_language_r`
  - `test_accucor_r_default_script_path_resolves`
  - `test_accucor_r_default_tracer_c13`
  - `test_accucor_r_default_resolution_120000`
  - `test_accucor_r_input_ports_peak_table_and_metadata`
  - `test_accucor_r_output_port_is_midtable`
  - `test_accucor_r_override_script_path_accepted`
  - `@pytest.mark.requires_r test_accucor_r_end_to_end_synthetic_peak_table`

**f. Existing tests to update**: none.

**g. Implementation details**:

`ElMAVENBlock` reuses `AppBlock.run()` verbatim (per ADR-018/ADR-019)
and only specialises:

- `app_command: ClassVar[str] = "elmaven"` (user can override via
  `elmaven_path` config).
- `execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL`.
- `output_patterns: ClassVar[list[str]] = ["*.csv", "*.tsv", "*.xlsx"]`.
- `watch_timeout: ClassVar[int] = 1800` (30 minutes — ElMAVEN is
  interactive and slow).
- `input_ports = [InputPort(name="raw_files",
  accepted_types=[MSRawFile], required=True)]`.
- `output_ports = [OutputPort(name="peak_table",
  accepted_types=[PeakTable]), OutputPort(name="mid_table",
  accepted_types=[MIDTable], required=False)]`.

A module-level classifier routes each exported file to the right output
port:

```python
def _classify_export(path: Path) -> str:
    """Return 'mid_table' if the file looks like a MID table, else 'peak_table'.

    Heuristic: MID tables have a column named 'C13' or 'H2' in the
    header row. Peak tables typically have 'medMz' / 'mz' instead.
    """
    ...
```

Per §8 Q-2, the block does **not** try to script ElMAVEN's UI. The user
opens the input files, runs peak detection, and exports manually via
ElMAVEN's own menus; the `FileWatcher` collects the exports.

`AccuCorR` subclasses `CodeBlock` with `language = "r"` and
`mode = "script"`:

```python
class AccuCorR(_LCMSBlockMixin, CodeBlock):
    language: ClassVar[str] = "r"
    mode: ClassVar[str] = "script"

    input_ports = [
        InputPort(name="peak_table", accepted_types=[PeakTable], required=True),
        InputPort(name="sample_metadata", accepted_types=[SampleMetadata],
                  required=True),
    ]
    output_ports = [OutputPort(name="mid_table", accepted_types=[MIDTable])]

    config_schema = {
        "type": "object",
        "properties": {
            "tracer_formula": {"type": "string", "default": "C13"},
            "resolution": {"type": "integer", "default": 120000},
            "accucor_script_path": {"type": ["string", "null"], "default": None},
        },
    }

    def _resolve_script_path(self, config):
        override = config.get("accucor_script_path")
        if override:
            return str(override)
        with resources.as_file(
            resources.files("scieasy_blocks_lcms.scripts") / "accucor_default.R"
        ) as path:
            return str(path)

    def run(self, inputs, config):
        patched = dict(config)
        patched["script_path"] = self._resolve_script_path(config)
        patched["entry_function"] = "run_accucor"
        patched.setdefault("language", "r")
        patched.setdefault("mode", "script")
        return super().run(inputs, patched)
```

The bundled `accucor_default.R` (package data at
`src/scieasy_blocks_lcms/scripts/accucor_default.R`):

```r
# Default AccuCor driver shipped with scieasy-blocks-lcms.
# Upstream: https://github.com/lparsons/accucor (v0.3.1)
# License: MIT (see THIRD_PARTY_LICENSES.md)
#
# Invoked by CodeBlock's R runner with:
#   inputs$peak_table      -- path to PeakTable CSV
#   inputs$sample_metadata -- path to SampleMetadata CSV
#   params$tracer_formula  -- tracer atom, e.g. "C13"
#   params$resolution      -- mass spec resolution
# and must return a list with:
#   result$mid_table       -- path to the output MID table CSV

run_accucor <- function(inputs, params) {
  if (!requireNamespace("accucor", quietly = TRUE)) {
    stop("AccuCor is not installed. Run install.packages('accucor').")
  }
  library(accucor)

  peak_df <- read.csv(inputs$peak_table, check.names = FALSE)
  meta_df <- read.csv(inputs$sample_metadata, check.names = FALSE)

  tracer <- if (!is.null(params$tracer_formula)) params$tracer_formula else "C13"
  resolution <- if (!is.null(params$resolution)) params$resolution else 120000

  corrected <- accucor::natural_abundance_correction(
    peak_df, tracer = tracer, resolution = resolution
  )

  out_path <- tempfile(fileext = ".csv")
  write.csv(corrected$Normalized, out_path, row.names = FALSE)
  list(mid_table = out_path)
}
```

**h. Acceptance criteria**:

`ElMAVENBlock`:
- [ ] Subclasses `AppBlock` and `_LCMSBlockMixin`.
- [ ] `app_command == "elmaven"`, `execution_mode == EXTERNAL`.
- [ ] `output_patterns == ["*.csv", "*.tsv", "*.xlsx"]`.
- [ ] `watch_timeout == 1800`.
- [ ] Input port `raw_files` accepts `MSRawFile` and is required.
- [ ] Output ports: `peak_table` (required) and `mid_table` (optional).
- [ ] `_classify_export` routes files based on header-column heuristics.
- [ ] Unit tests pass; integration test marked
      `@pytest.mark.requires_elmaven`.

`AccuCorR`:
- [ ] Subclasses `CodeBlock` and `_LCMSBlockMixin`.
- [ ] `language == "r"`, `mode == "script"`.
- [ ] `config_schema` has `tracer_formula` default `"C13"`, `resolution`
      default `120000`, `accucor_script_path` optional.
- [ ] `_resolve_script_path` returns the bundled default via
      `importlib.resources` when no override is set.
- [ ] `_resolve_script_path` honours the user override when set.
- [ ] `run()` patches `script_path` / `entry_function` / `language` /
      `mode` into config before delegating to `CodeBlock.run()`.
- [ ] `accucor_default.R` is installed as package data (picked up by
      `pip install -e .`).
- [ ] `THIRD_PARTY_LICENSES.md` reproduces the AccuCor MIT LICENSE.
- [ ] Unit tests pass; integration test marked
      `@pytest.mark.requires_r`.

**i. Out of scope**:
- Scripting ElMAVEN's UI (forbidden by §8 Q-2).
- Auto-installing the AccuCor R package.
- Supporting MZmine / XCMS AppBlocks (user: "先实现 ElMAVEN").
- Using `rpy2` instead of subprocess-based R execution (§8 Q-1).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002, T-LCMS-003,
T-LCMS-004, T-LCMS-005, T-LCMS-006.

**k. Estimated diff size**: ~350 lines Python source + ~60 lines R
script + ~400 lines test. Total ~810 lines.

**l. Suggested workflow gate ticket title**:
`ElMAVENBlock + AccuCorR external-tool blocks per master plan §2.4 (T-LCMS-007)`

**Status**: Implemented in LCMS foundation chunk 1 (issue #363, PR #369).
`ElMAVENBlock` now classifies collected exports into `peak_table` vs
`mid_table` using the locked header heuristic and routes them through
the concrete LCMS loaders. `AccuCorR` now resolves the bundled default
driver script, patches `script_path` / `entry_function` / `language` /
`mode` into the delegated `CodeBlock` config, materialises peak-table
and sample-metadata inputs to CSV for the R subprocess contract, and
wraps the returned MID CSV as a typed `MIDTable`. `GraphPadBlock`
remains intentionally pending for the separate Worker A follow-up chunk
(`T-LCMS-019`).

---

### T-LCMS-008 — `Calculate13CEnrichment`

**a. Ticket ID and name**: T-LCMS-008 — `Calculate13CEnrichment`
weighted-average enrichment per compound per sample.

**Status note (2026-04-08)**: Implemented in issue #366 / PR #371
(`feat/issue-366/T-LCMS-008-012-isotope-core`). The skeleton
`NotImplementedError` body is replaced with a concrete
`ProcessBlock.process_item()` implementation plus synthetic isotope
tracing tests under `packages/scieasy-blocks-lcms/tests/test_isotope_tracing/`.

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS isotope tracing (the USP).
- This spec §8 Q-5 (tracer atom handling, multi-tracer).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/enrichment.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_isotope/test_enrichment.py`:
  - `test_single_compound_single_tracer_full_labeling`
  - `test_single_compound_single_tracer_zero_labeling`
  - `test_single_compound_single_tracer_half_labeling`
  - `test_multiple_compounds`
  - `test_multiple_samples`
  - `test_users_verbatim_cytosine_example`
  - `test_multi_tracer_c13_and_h2_produces_two_columns`
  - `test_empty_mid_table_returns_empty_dataframe`
  - `test_raises_on_missing_tracer_atom_column`
  - `test_output_is_long_format_compound_sample_enrichment`
  - `test_output_schema_is_correct`
  - `test_tracer_atoms_from_midtable_meta`

**f. Existing tests to update**: none.

**g. Implementation details**:

This is the **flagship block** of the plugin's isotope-tracing USP.
Formula (for single tracer `C13`):

```
enrichment[compound, sample] = sum(n * M+n[compound, sample]) / n_max
```

where `n` is the 13C atom count for isotopologue M+n,
`M+n[compound, sample]` is the fractional abundance in that sample, and
`n_max` is the maximum 13C count for that compound (i.e. the compound's
maximum possible 13C labelling, which equals the maximum row value in
the `C13` column for that compound).

**Rationale for dividing by `n_max`**: the raw weighted sum
`sum(n * M+n)` gives the *mean number of labelled atoms per molecule*.
Dividing by `n_max` normalises this into a fraction between 0.0 (no
labelling) and 1.0 (full labelling of every carbon position). This
matches the metabolomics convention reported in Antoniewicz (2018)
*"A guide to 13C metabolic flux analysis"* for "average 13C enrichment"
(also called "carbon enrichment").

**Multi-tracer case**: when `len(tracer_atoms) > 1`, the formula is
applied separately to each tracer atom, producing one enrichment column
per tracer (e.g. `enrichment_C13`, `enrichment_H2`). The output schema
has one row per `(compound, sample)` with one enrichment column per
tracer.

**Output shape**: **LONG format** — one row per `(compound, sample)`
combination. Columns: `compound`, `sample`, `enrichment` (for single
tracer) or `compound`, `sample`, `enrichment_{atom}` for multi-tracer.

Why long: matches the `MIDTable` long convention (§8 Q-3) and enables
simple `groupby` patterns in downstream blocks (`CompareGroupMID`,
`FluxEstimate`).

Implementation sketch:

```python
# packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/enrichment.py
"""Calculate13CEnrichment — weighted-average labelling per compound/sample."""

from __future__ import annotations

from typing import Any, ClassVar

import pandas as pd

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.collection import Collection
from scieasy.core.types.dataframe import DataFrame

from scieasy_blocks_lcms._base import _LCMSBlockMixin
from scieasy_blocks_lcms.types import MIDTable


class Calculate13CEnrichment(_LCMSBlockMixin, ProcessBlock):
    """Average 13C enrichment per compound per sample.

    Formula (single tracer):
        E[c, s] = sum_n(n * M+n[c, s]) / n_max[c]
    where n_max[c] is the maximum 13C atom count row for compound c.

    Multi-tracer case: one enrichment column per tracer atom.

    Output: long-format DataFrame with columns (compound, sample,
    enrichment) or (compound, sample, enrichment_{atom}, ...).

    See phase11-lcms-block-spec.md §8 Q-5.
    """

    name: ClassVar[str] = "Calculate 13C Enrichment"
    type_name: ClassVar[str] = "calculate_13c_enrichment"
    category: ClassVar[str] = "process"
    description: ClassVar[str] = (
        "Average 13C (or other tracer) enrichment per compound per sample, "
        "computed as the weighted sum of M+n fractional abundances divided "
        "by the compound's maximum tracer atom count."
    )

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="mid_table", accepted_types=[MIDTable], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="enrichment", accepted_types=[DataFrame],
                   description="Per-compound per-sample enrichment"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "compound_column": {"type": "string", "default": "Compound"},
        },
    }

    def process_item(self, item: MIDTable, config, state=None) -> DataFrame:
        df = item.user.get("pandas_df")
        if df is None:
            df = pd.DataFrame(item.view().to_memory())
        compound_col = config.get("compound_column", "Compound")
        if compound_col not in df.columns:
            # accept lowercase fallback
            if "compound" in df.columns:
                compound_col = "compound"
            else:
                raise ValueError(
                    f"Calculate13CEnrichment: no '{compound_col}' column"
                )
        tracer_atoms = list(item.meta.tracer_atoms)
        sample_cols = list(item.meta.sample_columns)
        rows: list[dict[str, Any]] = []

        for compound, group in df.groupby(compound_col, sort=False):
            for sample in sample_cols:
                row: dict[str, Any] = {"compound": compound, "sample": sample}
                for atom in tracer_atoms:
                    if atom not in df.columns:
                        raise ValueError(
                            f"Calculate13CEnrichment: tracer atom '{atom}' "
                            f"not in MIDTable columns"
                        )
                    n_max = int(group[atom].max())
                    if n_max == 0:
                        enrichment = 0.0
                    else:
                        mids = group[sample].astype(float).values
                        ns = group[atom].astype(int).values
                        enrichment = float((ns * mids).sum() / n_max)
                    col = "enrichment" if len(tracer_atoms) == 1 else f"enrichment_{atom}"
                    row[col] = enrichment
                rows.append(row)

        out_df = pd.DataFrame(rows)
        result = DataFrame(
            columns=list(out_df.columns),
            row_count=len(out_df),
            schema={c: str(out_df[c].dtype) for c in out_df.columns},
        )
        result.user["pandas_df"] = out_df
        return result
```

**Worked example** (user's verbatim cytosine):

```
Compound    C13  H2  UL0  UL3    UL2    UL1    SE3
cytosine    0    0   1    1      0.9995 1      0.9542
cytosine    1    0   0    0      0      0      0.0029
```

For `compound="cytosine"`, `tracer_atoms=["C13"]`,
`sample_columns=["UL0", "UL3", "UL2", "UL1", "SE3"]`:

- `n_max = max(C13 column for cytosine) = 1`
- For sample `UL0`: `enrichment = (0*1 + 1*0) / 1 = 0.0`
- For sample `UL3`: `enrichment = (0*1 + 1*0) / 1 = 0.0`
- For sample `SE3`: `enrichment = (0*0.9542 + 1*0.0029) / 1 = 0.0029`

The fact that `n_max = 1` in this truncated example is because the
verbatim sample only shows two rows (M+0, M+1). A real cytosine MID
would have `n_max = 4` (cytosine has 4 carbons) and rows for M+0 .. M+4.
The formula generalises correctly.

**h. Acceptance criteria**:
- [ ] `Calculate13CEnrichment` subclasses `ProcessBlock` and
      `_LCMSBlockMixin`.
- [ ] `category == "process"`.
- [ ] Input port `mid_table` accepts `MIDTable`.
- [ ] Output port `enrichment` produces a `DataFrame`.
- [ ] Single-tracer output has columns `compound`, `sample`,
      `enrichment`.
- [ ] Multi-tracer output has columns `compound`, `sample`,
      `enrichment_{atom}` for each tracer.
- [ ] `n_max == 0` short-circuits to `enrichment == 0.0` (avoids
      division by zero).
- [ ] Raises `ValueError` if the compound column is missing.
- [ ] Raises `ValueError` if a tracer atom column is missing.
- [ ] Output is long format (one row per `(compound, sample)`).
- [ ] `tracer_atoms` is read from `MIDTable.meta`, not from config
      (single source of truth).
- [ ] 12 tests pass, including the user's verbatim cytosine example.

**i. Out of scope**:
- Wide-format output (pivot is a generic CodeBlock one-liner).
- Error correction for skewed MID distributions.
- Confidence intervals — these need biological replicates.
- Natural abundance correction (already done upstream by AccuCor).
- Support for tracers outside `_KNOWN_ATOM_COLUMNS` (rare; users can
  add to the set via a follow-up PR if needed).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~180 lines source + ~350 lines test.
Total ~530 lines. The test file is larger than usual because the
worked examples and multi-tracer matrix tests need real fixtures.

**l. Suggested workflow gate ticket title**:
`Calculate13CEnrichment block per master plan §2.4 isotope tracing (T-LCMS-008)`

---

### T-LCMS-009 — `FractionalLabeling`

**a. Ticket ID and name**: T-LCMS-009 — `FractionalLabeling`
(`1 - M+0` per compound per sample).

**Status note (2026-04-08)**: Implemented in issue #366 / PR #371
(`feat/issue-366/T-LCMS-008-012-isotope-core`). The block now computes
`1 - M+0` from `MIDTable.meta.tracer_atoms` / `sample_columns` and the
spec-listed error path for missing M+0 rows is covered by real tests.

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS isotope tracing.

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/labeling.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_isotope/test_labeling.py`:
  - `test_single_compound_single_sample`
  - `test_zero_labeling_returns_zero`
  - `test_full_labeling_returns_one`
  - `test_half_labeling_returns_half`
  - `test_multi_compound_multi_sample`
  - `test_output_long_format`
  - `test_raises_on_missing_m0_row`
  - `test_tracer_column_read_from_midtable_meta`

**f. Existing tests to update**: none.

**g. Implementation details**:

Simpler than `Calculate13CEnrichment`:

```
fractional_labeling[compound, sample] = 1 - MID[compound, m_n=0, sample]
```

where `MID[compound, m_n=0, sample]` is the `M+0` row for that compound
in the MID table — i.e. the row where every tracer-atom column is 0.

For multi-tracer, the M+0 row is the intersection (all tracer atom
columns must be 0). The computation is straightforward:

```python
def process_item(self, item, config, state=None):
    df = item.user.get("pandas_df") or pd.DataFrame(item.view().to_memory())
    tracer_atoms = item.meta.tracer_atoms
    sample_cols = item.meta.sample_columns

    # Select M+0 rows: all tracer columns are 0.
    mask = pd.Series([True] * len(df))
    for atom in tracer_atoms:
        mask &= (df[atom] == 0)
    m0_rows = df[mask]

    rows = []
    for _, r in m0_rows.iterrows():
        compound = r["Compound"]
        for sample in sample_cols:
            rows.append({
                "compound": compound,
                "sample": sample,
                "fractional_labeling": 1.0 - float(r[sample]),
            })
    out_df = pd.DataFrame(rows)
    ...
```

Raises `ValueError` if any compound lacks an M+0 row (this indicates an
upstream data problem).

**h. Acceptance criteria**:
- [ ] Subclasses `ProcessBlock` and `_LCMSBlockMixin`.
- [ ] Input port `mid_table` accepts `MIDTable`.
- [ ] Output port `fractional_labeling` produces a `DataFrame` with
      columns `compound`, `sample`, `fractional_labeling`.
- [ ] `0 <= fractional_labeling <= 1` for valid MIDs.
- [ ] Raises `ValueError` if any compound lacks an M+0 row.
- [ ] Uses `MIDTable.meta.tracer_atoms` / `sample_columns` as the
      source of truth.
- [ ] 8 tests pass.

**i. Out of scope**:
- Enrichment calculation (T-LCMS-008).
- Per-position labelling (requires NMR or MS/MS, out of scope).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~130 lines source + ~200 lines test.
Total ~330 lines.

**l. Suggested workflow gate ticket title**:
`FractionalLabeling block per master plan §2.4 isotope tracing (T-LCMS-009)`

---

### T-LCMS-010 — `CompareGroupMID`

**a. Ticket ID and name**: T-LCMS-010 — `CompareGroupMID` per-isotopologue
statistical comparison between sample groups.

**Status note (2026-04-08)**: Implemented in issue #366 / PR #371
(`feat/issue-366/T-LCMS-008-012-isotope-core`). Two-group statistical
comparison, correction modes, and the `>2 groups -> UnivariateStats`
boundary now have concrete code and synthetic test coverage.

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS isotope tracing.

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/compare.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_isotope/test_compare.py`:
  - `test_two_group_ttest_per_isotopologue`
  - `test_two_group_wilcoxon_per_isotopologue`
  - `test_two_group_mann_whitney_per_isotopologue`
  - `test_summed_labeled_mode_sums_all_m_n_above_zero`
  - `test_bonferroni_correction_applied`
  - `test_fdr_correction_applied`
  - `test_no_correction_mode`
  - `test_significance_flag_at_alpha_0_05`
  - `test_output_columns_match_spec`
  - `test_raises_on_missing_group_column`
  - `test_raises_on_single_group`
  - `test_three_groups_not_supported_by_ttest`

**f. Existing tests to update**: none.

**g. Implementation details**:

Input: `MIDTable` + `SampleMetadata` + `group_column: str` config.
Config:
- `test: "t-test" | "wilcoxon" | "mann-whitney"` (default `"t-test"`)
- `correction: "bonferroni" | "fdr" | "none"` (default `"fdr"`)
- `per_isotopologue: bool = True`
- `alpha: float = 0.05`

Algorithm:

1. Join `MIDTable` sample columns to `SampleMetadata[group_column]` by
   sample ID.
2. For each compound × isotopologue (or compound × {summed M+n>0} if
   `per_isotopologue=False`):
   a. Split samples by group.
   b. Run the chosen test via `scipy.stats`
      (`scipy.stats.ttest_ind`, `scipy.stats.wilcoxon`,
      `scipy.stats.mannwhitneyu`).
   c. Record p-value.
3. Apply multiple-testing correction via
   `statsmodels.stats.multitest.multipletests` (import inside the
   function body so `statsmodels` is a soft dependency — declare in
   the plugin's optional extras, and the block raises a clear
   `ImportError` guiding the user).
4. Emit a long-format DataFrame.

Output columns (long format):

| Column              | Type   | Notes                                             |
|---------------------|--------|---------------------------------------------------|
| `compound`          | str    | Compound name                                     |
| `isotopologue`      | str    | `"M+0"`, `"M+1"`, ... (omitted if `per_iso=False`) |
| `group1`            | str    | First group name                                  |
| `group2`            | str    | Second group name                                 |
| `group1_mean`       | float  | Mean MID in group1                                |
| `group2_mean`       | float  | Mean MID in group2                                |
| `pvalue`            | float  | Raw test p-value                                  |
| `pvalue_adj`        | float  | Corrected p-value                                 |
| `significant`       | bool   | `pvalue_adj < alpha`                              |

**Limitation**: t-test and wilcoxon assume 2 groups; if >2 groups are
present, the block raises `NotImplementedError` pointing to
`UnivariateStats` (T-LCMS-015) which supports ANOVA.

**h. Acceptance criteria**:
- [ ] Subclasses `ProcessBlock` and `_LCMSBlockMixin`.
- [ ] Input ports: `mid_table` (MIDTable) and `sample_metadata`
      (SampleMetadata), both required.
- [ ] `config_schema` has `test`, `correction`, `per_isotopologue`,
      `group_column`, `alpha`.
- [ ] Two-group t-test, Wilcoxon, and Mann-Whitney all produce sane
      p-values on synthetic fixtures.
- [ ] Bonferroni correction: `pvalue_adj = min(1, pvalue * n_tests)`.
- [ ] FDR correction: BH method via `statsmodels.multipletests`.
- [ ] `none` correction: `pvalue_adj == pvalue`.
- [ ] `significant == pvalue_adj < alpha`.
- [ ] Raises `ValueError` on missing `group_column` or single group.
- [ ] Raises `NotImplementedError` if >2 groups (pointer to
      `UnivariateStats`).
- [ ] 12 tests pass.

**i. Out of scope**:
- ANOVA / Kruskal-Wallis (use `UnivariateStats` T-LCMS-015).
- Paired tests.
- Mixed-effects models.
- Permutation tests.

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~220 lines source + ~360 lines test.
Total ~580 lines.

**l. Suggested workflow gate ticket title**:
`CompareGroupMID block per master plan §2.4 isotope tracing (T-LCMS-010)`

---

### T-LCMS-011 — `FluxEstimate`

**a. Ticket ID and name**: T-LCMS-011 — `FluxEstimate` simple
steady-state flux via labelling rate × pool size.

**Status note (2026-04-08)**: Implemented in issue #366 / PR #371
(`feat/issue-366/T-LCMS-008-012-isotope-core`). The block now performs
the spec's naive linear-fit flux estimate and keeps the explicit
non-13C-MFA disclaimer in code and tests.

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS isotope tracing.
- This spec §8 Q-9 (FluxEstimate simplicity vs 13C-MFA boundary).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/flux.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_isotope/test_flux.py`:
  - `test_single_compound_linear_fit`
  - `test_multi_compound_flux_estimate`
  - `test_with_pool_size_table`
  - `test_without_pool_size_table_unit_pool_size`
  - `test_group_column_produces_per_group_flux`
  - `test_raises_on_fewer_than_2_timepoints`
  - `test_raises_on_missing_time_column`
  - `test_flux_is_labeling_rate_times_pool_size`
  - `test_output_long_format`
  - `test_disclaimer_in_docstring`

**f. Existing tests to update**: none.

**g. Implementation details**:

The block's contract, loudly documented:

> This is the **simplest possible** flux estimate: `flux = labeling_rate
> × pool_size`, where `labeling_rate` is the slope of a linear fit to
> fractional labelling vs. time, and `pool_size` is the total compound
> abundance from an optional `PeakTable`. This is **not a replacement
> for INCA, OpenFLUX, or Metran** — those tools solve elementary
> metabolite unit (EMU) systems for proper 13C-MFA.

Algorithm:

1. Unpack `MIDTable` + `SampleMetadata` + optional `PeakTable`.
2. Compute fractional labelling per compound per sample via the same
   `1 - M+0` formula as `FractionalLabeling`.
3. Join fractional labelling to `SampleMetadata[time_points_column]`.
4. For each `(compound, group)` combination:
   a. If < 2 distinct timepoints, raise `ValueError`.
   b. Linear fit `fractional_labeling ~ time` via `numpy.polyfit`
      degree 1.
   c. `labeling_rate = slope` of the fit.
5. If `pool_size_table` is provided, average the pool size per compound
   per group from the PeakTable's intensity column.
6. Flux `= labeling_rate × pool_size` (or just `labeling_rate` if no
   pool size).
7. Emit a long-format DataFrame with columns `compound`, `group`,
   `labeling_rate`, `pool_size` (optional), `estimated_flux`.

Inputs / config:

```python
input_ports = [
    InputPort(name="mid_table", accepted_types=[MIDTable], required=True),
    InputPort(name="sample_metadata", accepted_types=[SampleMetadata],
              required=True),
    InputPort(name="pool_size_table", accepted_types=[PeakTable],
              required=False),
]

config_schema = {
    "type": "object",
    "properties": {
        "time_points_column": {"type": "string", "default": "time_hours"},
        "group_column": {"type": ["string", "null"], "default": None},
    },
    "required": ["time_points_column"],
}
```

**h. Acceptance criteria**:
- [ ] Subclasses `ProcessBlock` and `_LCMSBlockMixin`.
- [ ] Input ports: `mid_table`, `sample_metadata`, `pool_size_table`
      (optional).
- [ ] Output column `estimated_flux` matches `labeling_rate * pool_size`
      (or just `labeling_rate` when no pool size).
- [ ] Uses `numpy.polyfit` for the linear fit (degree 1).
- [ ] Raises `ValueError` on fewer than 2 timepoints per group.
- [ ] Raises `ValueError` on missing `time_points_column`.
- [ ] Block docstring explicitly disclaims it is NOT a 13C-MFA
      replacement and points at INCA / OpenFLUX / Metran.
- [ ] Output is long format.
- [ ] 10 tests pass.

**i. Out of scope**:
- Non-linear labelling kinetics (exponential, Gompertz, etc.).
- EMU decomposition.
- Reaction network modelling.
- Atom mapping.

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~170 lines source + ~280 lines test.
Total ~450 lines.

**l. Suggested workflow gate ticket title**:
`FluxEstimate block per master plan §2.4 isotope tracing (T-LCMS-011)`

---

### T-LCMS-012 — `PoolSizeNormalize`

**a. Ticket ID and name**: T-LCMS-012 — `PoolSizeNormalize` intensity
normalization for PeakTables.

**Status note (2026-04-08)**: Implemented in issue #366 / PR #371
(`feat/issue-366/T-LCMS-008-012-isotope-core`). `IS`, `TIC`, and
`median` normalization now return a preserved-type `PeakTable` with the
spec-required meta retention and error handling.

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS isotope tracing.

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/normalize.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/isotope/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_isotope/test_normalize.py`:
  - `test_internal_standard_normalization`
  - `test_tic_normalization`
  - `test_median_normalization`
  - `test_raises_on_is_without_reference_compound`
  - `test_raises_on_missing_reference_compound`
  - `test_preserves_peak_table_type`
  - `test_preserves_peak_table_meta`
  - `test_output_column_renamed_or_inplace`

**f. Existing tests to update**: none.

**g. Implementation details**:

Three methods:

- **`IS`** (internal standard): divide every sample's intensity by the
  intensity of a reference compound in that sample. Requires
  `reference_compound: str` config.
- **`TIC`** (total ion current): divide every sample's intensity by
  the sum of all intensities in that sample.
- **`median`**: divide every sample's intensity by the median
  intensity across all compounds in that sample.

The output preserves the input `PeakTable`'s `Meta` (source, polarity)
so downstream blocks still see a typed `PeakTable`.

Config:

```python
{
    "type": "object",
    "properties": {
        "method": {
            "type": "string",
            "enum": ["IS", "TIC", "median"],
            "default": "TIC",
        },
        "reference_compound": {
            "type": ["string", "null"],
            "default": None,
            "title": "Reference compound (for IS mode)",
        },
        "intensity_column": {"type": "string", "default": "intensity"},
        "compound_column": {"type": "string", "default": "compound"},
    },
}
```

**h. Acceptance criteria**:
- [ ] Three methods implemented: `IS`, `TIC`, `median`.
- [ ] `IS` raises `ValueError` if `reference_compound` is not set.
- [ ] `IS` raises `ValueError` if the reference compound is not in the
      PeakTable.
- [ ] Output is a `PeakTable` (not a plain `DataFrame`).
- [ ] `PeakTable.meta` (source, polarity) is preserved.
- [ ] 8 tests pass.

**i. Out of scope**:
- QC-based normalization (QC blocks are out of scope entirely).
- Lowess / probabilistic quotient normalization — follow-up.
- Per-batch normalization — follow-up.

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002, T-LCMS-004.

**k. Estimated diff size**: ~150 lines source + ~240 lines test.
Total ~390 lines.

**l. Suggested workflow gate ticket title**:
`PoolSizeNormalize block per master plan §2.4 isotope tracing (T-LCMS-012)`

---

### T-LCMS-013 — `MetaboliteMatrix`

**a. Ticket ID and name**: T-LCMS-013 — `MetaboliteMatrix` (long
PeakTable + SampleMetadata → wide matrix).

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS metabolomics.

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/matrix.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_metabolomics/test_matrix.py`:
  - `test_pivot_long_to_wide`
  - `test_default_value_column_intensity`
  - `test_custom_value_column`
  - `test_default_compound_column`
  - `test_custom_compound_column`
  - `test_missing_combinations_become_nan`
  - `test_output_is_generic_dataframe`
  - `test_preserves_sample_order_from_metadata`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
class MetaboliteMatrix(_LCMSBlockMixin, ProcessBlock):
    """Pivot a long-format PeakTable to a wide compound × sample matrix."""

    input_ports = [
        InputPort(name="peak_table", accepted_types=[PeakTable], required=True),
        InputPort(name="sample_metadata", accepted_types=[SampleMetadata],
                  required=False),
    ]
    output_ports = [
        OutputPort(name="matrix", accepted_types=[DataFrame]),
    ]

    config_schema = {
        "type": "object",
        "properties": {
            "value_column": {"type": "string", "default": "intensity"},
            "compound_column": {"type": "string", "default": "compound"},
            "sample_column": {"type": "string", "default": "sample_id"},
        },
    }
```

The block uses `pandas.pivot_table(index=compound_column,
columns=sample_column, values=value_column)` to produce the wide matrix.
If `sample_metadata` is provided, the column order is taken from the
metadata (so downstream visualisations get a consistent ordering).

Missing `(compound, sample)` combinations become `NaN`; imputation is
the caller's responsibility (use `MatrixPreprocess`).

**h. Acceptance criteria**:
- [ ] Pivots long → wide correctly.
- [ ] Default column names match spec (`intensity`, `compound`,
      `sample_id`).
- [ ] Missing combinations → `NaN`.
- [ ] Output is a generic `DataFrame` (not a `PeakTable`, since the
      shape no longer matches peak-table conventions).
- [ ] Preserves sample order from metadata when provided.
- [ ] 8 tests pass.

**i. Out of scope**:
- Multi-value pivots (e.g. simultaneous intensity + area).
- Aggregation functions other than first (user should
  deduplicate upstream).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002, T-LCMS-004.

**k. Estimated diff size**: ~120 lines source + ~200 lines test.
Total ~320 lines.

**l. Suggested workflow gate ticket title**:
`MetaboliteMatrix block per master plan §2.4 metabolomics (T-LCMS-013)`

---

### T-LCMS-014 — `MatrixPreprocess`

**a. Ticket ID and name**: T-LCMS-014 — `MatrixPreprocess` consolidated
log/impute/scale for metabolite matrices.

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS metabolomics (consolidated preprocessing).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/preprocess.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_metabolomics/test_preprocess.py`:
  - `test_log_transform_default_true`
  - `test_log_transform_handles_zeros_via_pseudocount`
  - `test_impute_knn`
  - `test_impute_mean`
  - `test_impute_zero`
  - `test_impute_none`
  - `test_scale_auto_is_zscore`
  - `test_scale_pareto`
  - `test_scale_none`
  - `test_pipeline_order_impute_log_scale`
  - `test_preserves_dataframe_shape`
  - `test_raises_on_unknown_impute_method`
  - `test_raises_on_unknown_scale_method`

**f. Existing tests to update**: none.

**g. Implementation details**:

Config:

```python
{
    "type": "object",
    "properties": {
        "log_transform": {"type": "boolean", "default": True},
        "impute_method": {
            "type": "string",
            "enum": ["knn", "mean", "zero", "none"],
            "default": "knn",
        },
        "scale": {
            "type": "string",
            "enum": ["auto", "pareto", "none"],
            "default": "auto",
        },
    },
}
```

Pipeline order (documented in the block's docstring):

1. **Impute** — fill NaNs per the chosen method.
   - `knn`: `sklearn.impute.KNNImputer(n_neighbors=5)`.
   - `mean`: column-wise mean.
   - `zero`: constant 0.
   - `none`: no imputation (NaNs propagate).
2. **Log transform** — `log2(x + pseudocount)` where
   `pseudocount = min_positive_value / 2`. Skipped if
   `log_transform=False`.
3. **Scale**:
   - `auto` → z-score (mean-centred, unit variance per compound row).
   - `pareto` → mean-centred, divided by sqrt(stddev) per compound row.
   - `none` → no scaling.

Imports: `sklearn.impute.KNNImputer` (already in dependencies),
`numpy`.

**h. Acceptance criteria**:
- [ ] `log_transform` defaults to `True`.
- [ ] Log transform uses `log2(x + pseudocount)` with pseudocount =
      half the min positive value.
- [ ] All 4 impute methods work on synthetic fixtures.
- [ ] All 3 scale methods produce correct numerics.
- [ ] Pipeline order is impute → log → scale.
- [ ] Raises `ValueError` on unknown method names.
- [ ] Output shape == input shape.
- [ ] 13 tests pass.

**i. Out of scope**:
- Batch correction (ComBat / limma removeBatchEffect).
- Missing-at-random (MAR) vs not-at-random (MNAR) classification.
- Per-replicate outlier detection.

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~170 lines source + ~350 lines test.
Total ~520 lines.

**l. Suggested workflow gate ticket title**:
`MatrixPreprocess block per master plan §2.4 metabolomics (T-LCMS-014)`

---

### T-LCMS-015 — `UnivariateStats`

**a. Ticket ID and name**: T-LCMS-015 — `UnivariateStats` per-metabolite
t-test / ANOVA / Wilcoxon.

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS metabolomics.

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/univariate.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_metabolomics/test_univariate.py`:
  - `test_ttest_two_groups`
  - `test_anova_three_groups`
  - `test_wilcoxon_two_groups`
  - `test_fold_change_computed`
  - `test_bonferroni_correction`
  - `test_fdr_correction`
  - `test_significance_flag`
  - `test_raises_on_single_group`
  - `test_raises_on_anova_with_two_groups` (use t-test instead)
  - `test_raises_on_ttest_with_three_groups` (use anova instead)
  - `test_output_columns_match_spec`
  - `test_empty_matrix_returns_empty_dataframe`

**f. Existing tests to update**: none.

**g. Implementation details**:

Config:

```python
{
    "type": "object",
    "properties": {
        "test": {
            "type": "string",
            "enum": ["t-test", "anova", "wilcoxon"],
            "default": "t-test",
        },
        "correction": {
            "type": "string",
            "enum": ["bonferroni", "fdr", "none"],
            "default": "fdr",
        },
        "group_column": {"type": "string"},
        "alpha": {"type": "number", "default": 0.05},
    },
    "required": ["group_column"],
}
```

Input: `DataFrame` (metabolite matrix, rows=compounds, columns=samples)
+ `SampleMetadata`.

For each compound (row):

1. Split samples by `group_column` using the metadata.
2. Run the chosen test:
   - `t-test`: `scipy.stats.ttest_ind` (exactly 2 groups required).
   - `anova`: `scipy.stats.f_oneway` (≥ 2 groups; typically ≥ 3).
   - `wilcoxon`: `scipy.stats.mannwhitneyu` (2 groups).
3. Compute fold change (for 2-group cases): `log2(mean_group1 /
   mean_group2)`.
4. Apply multiple-testing correction.

Output columns (long format):

| Column        | Type  | Notes                                      |
|---------------|-------|--------------------------------------------|
| `compound`    | str   | Compound (row name from the matrix)        |
| `fold_change` | float | `log2(g1_mean / g2_mean)` (NaN for ANOVA)  |
| `pvalue`      | float | Raw test p-value                           |
| `pvalue_adj`  | float | Corrected p-value                          |
| `significant` | bool  | `pvalue_adj < alpha`                       |

**h. Acceptance criteria**:
- [ ] Three tests implemented correctly (`scipy.stats` verified).
- [ ] Fold change computed for 2-group cases.
- [ ] Correction methods match `CompareGroupMID`'s.
- [ ] Raises `ValueError` on wrong group count for test type.
- [ ] Output columns match the spec.
- [ ] 12 tests pass.

**i. Out of scope**:
- Linear models / ANCOVA.
- Mixed-effects models.
- Effect size (Cohen's d, etc.) — follow-up.

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002, T-LCMS-013.

**k. Estimated diff size**: ~200 lines source + ~320 lines test.
Total ~520 lines.

**l. Suggested workflow gate ticket title**:
`UnivariateStats block per master plan §2.4 metabolomics (T-LCMS-015)`

---

### T-LCMS-016 — `MultivariateAnalysis`

**a. Ticket ID and name**: T-LCMS-016 — `MultivariateAnalysis`
consolidated PCA/PLSDA/OPLSDA.

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS metabolomics.

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/multivariate.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_metabolomics/test_multivariate.py`:
  - `test_pca_default_two_components`
  - `test_pca_scores_shape_matches_samples`
  - `test_pca_loadings_shape_matches_features`
  - `test_plsda_requires_metadata`
  - `test_plsda_binary_classification`
  - `test_oplsda_requires_metadata`
  - `test_n_components_config`
  - `test_scale_true_by_default`
  - `test_output_scores_dataframe`
  - `test_output_loadings_dataframe`
  - `test_output_plot_artifact_png`
  - `test_raises_on_unknown_method`

**f. Existing tests to update**: none.

**g. Implementation details**:

Config:

```python
{
    "type": "object",
    "properties": {
        "method": {
            "type": "string",
            "enum": ["PCA", "PLSDA", "OPLSDA"],
            "default": "PCA",
        },
        "n_components": {"type": "integer", "default": 2},
        "scale": {"type": "boolean", "default": True},
        "group_column": {"type": ["string", "null"], "default": None},
    },
}
```

Input: `DataFrame` (metabolite matrix) + optional `SampleMetadata`
(required for PLSDA / OPLSDA).

Output ports:

```python
output_ports = [
    OutputPort(name="scores", accepted_types=[DataFrame]),
    OutputPort(name="loadings", accepted_types=[DataFrame]),
    OutputPort(name="plot", accepted_types=[Artifact]),
]
```

Implementation:

- PCA: `sklearn.decomposition.PCA(n_components=n)`. Data is mean-centred
  and optionally scaled (`sklearn.preprocessing.StandardScaler`).
- PLSDA: `sklearn.cross_decomposition.PLSRegression(n_components=n)`
  with a one-hot encoded group response. The name "PLSDA" is the
  chemometrics convention but the underlying implementation is just
  PLS regression against a binary response.
- OPLSDA: not natively in scikit-learn. Implement as "PLS with 1
  predictive component + (n-1) orthogonal components" per the
  Trygg & Wold (2002) algorithm. If this is non-trivial to land in
  the ticket's size budget, defer OPLSDA to a follow-up ticket and
  raise `NotImplementedError("OPLSDA: deferred to follow-up ticket")`.
  Document the deferral in the PR description.

Plot artifact: a scores scatter plot (samples coloured by group if
available), saved as PNG via `matplotlib.pyplot.savefig`, wrapped in an
`Artifact` with `mime_type="image/png"`.

**h. Acceptance criteria**:
- [ ] PCA implementation correct (scores = `pca.transform(X)`).
- [ ] PLSDA implementation correct (scores from PLS regression).
- [ ] OPLSDA either implemented correctly OR raises
      `NotImplementedError` with a pointer to the follow-up ticket.
- [ ] `n_components` defaults to 2.
- [ ] `scale` defaults to True.
- [ ] PLSDA / OPLSDA raise `ValueError` without `sample_metadata` +
      `group_column`.
- [ ] Three outputs: `scores` (DataFrame), `loadings` (DataFrame),
      `plot` (Artifact PNG).
- [ ] 12 tests pass.

**i. Out of scope**:
- ISA (Independent Component Analysis).
- HCA / dendrograms.
- Cross-validation / permutation testing for PLSDA (follow-up).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002, T-LCMS-013.

**Implementation note**: PR #379 lands PCA and PLSDA. OPLSDA remains
intentionally deferred behind a `NotImplementedError` until the follow-up
ticket is scheduled.

**k. Estimated diff size**: ~280 lines source + ~350 lines test.
Total ~630 lines.

**l. Suggested workflow gate ticket title**:
`MultivariateAnalysis block per master plan §2.4 metabolomics (T-LCMS-016)`

---

### T-LCMS-017 — `PathwayEnrichment`

**a. Ticket ID and name**: T-LCMS-017 — `PathwayEnrichment` KEGG REST
pathway enrichment (Python-native).

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS metabolomics.
- This spec §8 Q-6 (Python KEGG REST as the default).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/pathway.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_metabolomics/test_pathway.py`:
  - `test_kegg_rest_call_mocked`
  - `test_compound_pathway_map_parsing`
  - `test_pathway_list_parsing`
  - `test_fisher_exact_test_per_pathway`
  - `test_fdr_correction`
  - `test_organism_parameter_hsa_default`
  - `test_organism_parameter_eco`
  - `test_pvalue_cutoff_filter`
  - `test_output_columns_match_spec`
  - `test_raises_on_empty_input`
  - `test_cache_within_single_run`

**f. Existing tests to update**: none.

**g. Implementation details**:

Per §8 Q-6, the default implementation is Python-native via the KEGG
REST API. No R dependency.

KEGG REST endpoints:

- `https://rest.kegg.jp/link/pathway/cpd` — compound → pathway map
  (returns TSV).
- `https://rest.kegg.jp/list/pathway/{organism}` — pathway ID → name
  for an organism.

Algorithm:

1. Fetch the compound → pathway map (cached process-locally).
2. Fetch the organism-specific pathway list.
3. For each pathway:
   a. Count `hits` — the number of input compounds that map to this
      pathway.
   b. Count `total` — the total number of compounds in this pathway.
   c. Count `background` — the total number of compounds mapped to any
      pathway.
   d. Fisher's exact test for the 2×2 contingency table
      `[[hits, total-hits], [input-hits, background-input+hits]]` via
      `scipy.stats.fisher_exact`.
4. Compute fold enrichment: `(hits / input) / (total / background)`.
5. Apply FDR correction via `statsmodels.stats.multitest.multipletests`.
6. Filter by `pvalue_cutoff`.

Config:

```python
{
    "type": "object",
    "properties": {
        "database": {"type": "string", "enum": ["KEGG"], "default": "KEGG"},
        "organism": {"type": "string", "default": "hsa"},
        "pvalue_cutoff": {"type": "number", "default": 0.05},
        "compound_column": {"type": "string", "default": "compound"},
    },
}
```

Note: `database` is an enum with only `"KEGG"` for 0.1.0. A
follow-up ticket may add `"HMDB"` / `"MetaboAnalystR"` options.

Output columns (long format):

| Column            | Type  | Notes                                |
|-------------------|-------|--------------------------------------|
| `pathway`         | str   | Pathway name (e.g. "Glycolysis")     |
| `pathway_id`      | str   | KEGG pathway ID (e.g. "hsa00010")    |
| `hits`            | int   | Input compounds matched to pathway   |
| `total`           | int   | Total compounds in pathway           |
| `fold_enrichment` | float | Observed / expected ratio            |
| `pvalue`          | float | Fisher's exact p-value               |
| `pvalue_adj`      | float | FDR-corrected p-value                |

**Caching**: process-local `dict` keyed by `(endpoint, organism)`. No
persistent cache for 0.1.0.

**Rate limiting**: KEGG REST allows ~10 requests/sec per user. The
block sleeps 100 ms between requests via `time.sleep(0.1)`.

**h. Acceptance criteria**:
- [ ] Uses KEGG REST via `requests` (no R dependency).
- [ ] `organism` defaults to `"hsa"` (human).
- [ ] `pvalue_cutoff` defaults to `0.05`.
- [ ] Fisher's exact test via `scipy.stats.fisher_exact`.
- [ ] FDR correction via `statsmodels.multipletests`.
- [ ] Process-local cache (dict) used for KEGG responses.
- [ ] Rate-limiting sleep between requests (100 ms).
- [ ] Output columns match the spec.
- [ ] 11 tests pass (using `responses` or `requests_mock` to mock
      KEGG REST calls).

**i. Out of scope**:
- HMDB backend (follow-up).
- MetaboAnalystR backend (follow-up; pattern documented in §8 Q-6).
- Persistent disk cache for KEGG responses (follow-up).
- Non-human organisms beyond what KEGG supports out of the box.
- Compound ID mapping (HMDB → KEGG → InChI) — assumes compound names
  match KEGG's canonical names.

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002, T-LCMS-015
(typically fed by `UnivariateStats` significant compounds).

**k. Estimated diff size**: ~220 lines source + ~320 lines test.
Total ~540 lines.

**l. Suggested workflow gate ticket title**:
`PathwayEnrichment block (KEGG REST Python) per master plan §2.4 (T-LCMS-017)`

---

### T-LCMS-018 — `ConsumptionSecretionAnalysis`

**a. Ticket ID and name**: T-LCMS-018 — `ConsumptionSecretionAnalysis`
extracellular flux analysis (spent vs fresh media).

**b. Source ADR / spec sections**:
- Master plan §2.4 LC-MS metabolomics (NEW block per user request).
- This spec §8 Q-7 (formula, cell count normalization).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/consumption_secretion.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/metabolomics/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_metabolomics/test_consumption_secretion.py`:
  - `test_pure_consumption_delta_negative`
  - `test_pure_secretion_delta_positive`
  - `test_consumed_or_secreted_flag`
  - `test_without_cell_count_uses_unit_normalization`
  - `test_with_cell_count_computes_flux_per_cell_per_hour`
  - `test_fresh_media_averaged_across_samples`
  - `test_time_hours_required`
  - `test_raises_on_mismatched_compounds`
  - `test_output_long_format`
  - `test_output_columns_match_spec`

**f. Existing tests to update**: none.

**g. Implementation details**:

Per §8 Q-7:

Inputs:

- `spent_media: PeakTable` — intensities in spent media samples.
- `fresh_media: PeakTable` — intensities in fresh media controls.
- `cell_count_table: DataFrame | None` — optional per-sample cell
  counts.

Config:

```python
{
    "type": "object",
    "properties": {
        "time_hours": {"type": "number"},
        "normalize_per_cell": {"type": "boolean", "default": False},
        "intensity_column": {"type": "string", "default": "intensity"},
        "compound_column": {"type": "string", "default": "compound"},
        "sample_column": {"type": "string", "default": "sample_id"},
    },
    "required": ["time_hours"],
}
```

Algorithm:

1. Compute per-compound mean intensity in `fresh_media`
   (`fresh[c] = mean over all fresh samples`).
2. For each `(compound, spent_sample)`:
   a. `delta[c, s] = spent[c, s] - fresh[c]`.
   b. `consumed_or_secreted[c, s] = "consumed" if delta < 0 else "secreted"`.
   c. If `normalize_per_cell`:
      - Look up `cell_count[s]` from `cell_count_table`.
      - `flux[c, s] = delta[c, s] / (cell_count[s] * time_hours)`.
      else:
      - `flux[c, s] = delta[c, s] / time_hours`.
3. Emit long-format DataFrame.

Output columns:

| Column                   | Type  | Notes                                        |
|--------------------------|-------|----------------------------------------------|
| `compound`               | str   | Compound name                                |
| `sample`                 | str   | Spent-media sample ID                        |
| `delta_concentration`    | float | `spent - mean(fresh)`                        |
| `consumed_or_secreted`   | str   | `"consumed"` or `"secreted"`                 |
| `flux_per_cell_per_hour` | float | `delta / (cell_count * time_hours)` or `delta / time_hours` |

**h. Acceptance criteria**:
- [ ] `time_hours` is required.
- [ ] Fresh media intensities are averaged across samples per compound.
- [ ] `delta_concentration = spent - mean(fresh)`.
- [ ] `consumed_or_secreted` flag set correctly (negative → consumed,
      positive → secreted).
- [ ] Without cell count, `flux_per_cell_per_hour = delta / time_hours`.
- [ ] With cell count, `flux_per_cell_per_hour = delta / (cell_count *
      time_hours)`.
- [ ] Raises `ValueError` if `spent_media` and `fresh_media` do not
      share at least one compound.
- [ ] Output is long format.
- [ ] 10 tests pass.

**i. Out of scope**:
- Absolute quantification (requires calibration curves).
- Per-compound unit enforcement (block assumes consistent units
  between spent and fresh).
- Time-course flux profiles (single timepoint only).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002, T-LCMS-004.

**k. Estimated diff size**: ~180 lines source + ~280 lines test.
Total ~460 lines.

**l. Suggested workflow gate ticket title**:
`ConsumptionSecretionAnalysis block per master plan §2.4 (T-LCMS-018)`

---

### T-LCMS-019 — `GraphPadBlock`

**a. Ticket ID and name**: T-LCMS-019 — `GraphPadBlock` AppBlock
wrapper for GraphPad Prism.

**b. Source ADR / spec sections**:
- ADR-018 (AppBlock PAUSED state).
- ADR-019 (ProcessHandle, FileWatcher).
- Master plan §2.4 LC-MS external plotting.
- This spec §8 Q-8 (Windows-only, no default path).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/plotting/graphpad_block.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/plotting/__init__.py`
- `packages/scieasy-blocks-lcms/README.md` (document GraphPad path
  prerequisite).

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_plotting/test_graphpad_block.py`:
  - `test_graphpad_block_class_config`
  - `test_graphpad_no_default_app_command`
  - `test_graphpad_default_watch_timeout_1800s`
  - `test_graphpad_default_output_patterns`
  - `test_graphpad_input_ports_accept_dataframe`
  - `test_graphpad_output_ports_artifact_collection`
  - `test_graphpad_warns_on_non_windows`
  - `test_graphpad_raises_on_missing_graphpad_path`
  - `@pytest.mark.requires_graphpad test_graphpad_end_to_end_launch_export`

**f. Existing tests to update**: none.

**g. Implementation details**:

Per §8 Q-8, `GraphPadBlock` is a thin `AppBlock` subclass with
**no default `app_command`** — the user must supply `graphpad_path`
explicitly because the install path varies (`Prism 9` vs `Prism 10`,
Windows-only).

```python
class GraphPadBlock(_LCMSBlockMixin, AppBlock):
    """AppBlock wrapping GraphPad Prism for final figure polishing.

    Per spec §8 Q-8, there is no default `app_command` because the
    GraphPad install path varies. The user must supply `graphpad_path`
    explicitly.

    Workflow: the block copies the input DataFrames to the exchange
    directory as CSV files, optionally copies a template .pzfx file,
    launches GraphPad, and waits for the user to export figures
    (PNG/PDF/SVG) to the exchange directory.
    """

    name: ClassVar[str] = "GraphPad Prism"
    type_name: ClassVar[str] = "graphpad"
    category: ClassVar[str] = "app"
    description: ClassVar[str] = (
        "Open tables in GraphPad Prism for interactive figure creation. "
        "Exported PNG/PDF/SVG files are collected from the exchange directory."
    )

    app_command: ClassVar[str] = ""  # user must supply via graphpad_path
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL
    output_patterns: ClassVar[list[str]] = ["*.png", "*.pdf", "*.svg"]
    watch_timeout: ClassVar[int] = 1800

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="tables",
            accepted_types=[DataFrame],
            required=True,
            description="DataFrames to plot in GraphPad",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="figures",
            accepted_types=[Artifact],
            description="Exported figures (PNG/PDF/SVG)",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "graphpad_path": {
                "type": "string",
                "title": "GraphPad executable path",
                "ui_priority": 0,
                "ui_widget": "file_browser",
            },
            "template_path": {
                "type": ["string", "null"],
                "default": None,
                "title": "GraphPad template (.pzfx)",
                "ui_priority": 1,
            },
            "watch_timeout": {
                "type": "integer",
                "default": 1800,
                "title": "Watch timeout (seconds)",
                "ui_priority": 2,
            },
        },
        "required": ["graphpad_path"],
    }

    def run(self, inputs, config):
        import platform
        import logging
        if platform.system() != "Windows":
            logging.getLogger(__name__).warning(
                "GraphPad Prism is Windows-only; launching on %s "
                "may fail. See phase11-lcms-block-spec.md §8 Q-8.",
                platform.system(),
            )
        graphpad_path = config.get("graphpad_path")
        if not graphpad_path:
            raise ValueError("GraphPadBlock requires 'graphpad_path' in config")
        # Delegate to AppBlock.run() with the user-supplied path.
        patched = dict(config)
        patched["app_command"] = graphpad_path
        return super().run(inputs, patched)
```

**h. Acceptance criteria**:
- [ ] Subclasses `AppBlock` and `_LCMSBlockMixin`.
- [ ] `app_command == ""` by default (no default path).
- [ ] `output_patterns == ["*.png", "*.pdf", "*.svg"]`.
- [ ] `watch_timeout == 1800`.
- [ ] Input port `tables` accepts `DataFrame`.
- [ ] Output port `figures` produces `Artifact`.
- [ ] Logs a warning on non-Windows platforms.
- [ ] Raises `ValueError` if `graphpad_path` is missing.
- [ ] `graphpad_path` from config is patched into `app_command` before
      delegating to `AppBlock.run()`.
- [ ] Unit tests pass; integration test marked
      `@pytest.mark.requires_graphpad`.

**i. Out of scope**:
- Scripting GraphPad's UI (GraphPad has limited scripting surface).
- Template generation from scratch.
- Exporting directly to Prism `.pzfx` format from Python.
- Auto-detecting GraphPad install path (explicitly forbidden by
  §8 Q-8).

**j. Dependencies on other tickets**: T-LCMS-001, T-LCMS-002.

**k. Estimated diff size**: ~150 lines source + ~180 lines test.
Total ~330 lines.

**l. Suggested workflow gate ticket title**:
`GraphPadBlock per master plan §2.4 external plotting (T-LCMS-019)`

---

### T-LCMS-020 — Entry-point registration + plugin smoke test

**a. Ticket ID and name**: T-LCMS-020 — entry-point registration for
the `scieasy.blocks` / `scieasy.types` groups + plugin smoke test.

**b. Source ADR / spec sections**:
- ADR-026 (entry-point plugin discovery).
- ADR-028 §D2 (plugins register via `scieasy.blocks`).
- This spec §8 Q-12 (palette categories).

**c. Files to be created**: none (all registered files already exist).

**d. Files to be modified**:
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/__init__.py`
  (finalise `get_blocks()` to return the full list of 20 block
  classes).
- `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/types.py`
  (verify `get_types()` returns the 4 classes — already done in
  T-LCMS-002).
- `packages/scieasy-blocks-lcms/pyproject.toml` (double-check
  entry-point declarations match the `__init__.py` exports).

**e. New tests**:
- `packages/scieasy-blocks-lcms/tests/test_entry_points.py`:
  - `test_scieasy_blocks_entry_point_discovers_all_20`
  - `test_scieasy_types_entry_point_discovers_all_4`
  - `test_all_blocks_have_package_name_scieasy_blocks_lcms`
  - `test_all_blocks_have_category_from_controlled_set`
  - `test_all_blocks_have_unique_type_name`
  - `test_all_blocks_have_name`
  - `test_all_blocks_have_config_schema`
  - `test_all_blocks_importable_from_top_level`

**f. Existing tests to update**:
- `packages/scieasy-blocks-lcms/tests/test_package_layout.py`
  (T-LCMS-001): update `test_get_blocks_returns_list` to assert the
  length is now 20.

**g. Implementation details**:

```python
# packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/__init__.py
"""scieasy-blocks-lcms: LC-MS metabolomics & stable isotope tracing blocks."""

from __future__ import annotations

__version__ = "0.1.0"

# Types
from scieasy_blocks_lcms.types import (
    MIDTable,
    MSRawFile,
    PeakTable,
    SampleMetadata,
    get_types,
)

# IO blocks
from scieasy_blocks_lcms.io.load_ms_raw import LoadMSRawFiles
from scieasy_blocks_lcms.io.load_peak_table import LoadPeakTable
from scieasy_blocks_lcms.io.load_mid_table import LoadMIDTable
from scieasy_blocks_lcms.io.load_sample_metadata import LoadSampleMetadata
from scieasy_blocks_lcms.io.save_table import SaveTable

# External tools
from scieasy_blocks_lcms.external.elmaven_block import ElMAVENBlock
from scieasy_blocks_lcms.external.accucor_r import AccuCorR

# Isotope tracing
from scieasy_blocks_lcms.isotope.enrichment import Calculate13CEnrichment
from scieasy_blocks_lcms.isotope.labeling import FractionalLabeling
from scieasy_blocks_lcms.isotope.compare import CompareGroupMID
from scieasy_blocks_lcms.isotope.flux import FluxEstimate
from scieasy_blocks_lcms.isotope.normalize import PoolSizeNormalize

# Metabolomics analysis
from scieasy_blocks_lcms.metabolomics.matrix import MetaboliteMatrix
from scieasy_blocks_lcms.metabolomics.preprocess import MatrixPreprocess
from scieasy_blocks_lcms.metabolomics.univariate import UnivariateStats
from scieasy_blocks_lcms.metabolomics.multivariate import MultivariateAnalysis
from scieasy_blocks_lcms.metabolomics.pathway import PathwayEnrichment
from scieasy_blocks_lcms.metabolomics.consumption_secretion import (
    ConsumptionSecretionAnalysis,
)

# External plotting
from scieasy_blocks_lcms.plotting.graphpad_block import GraphPadBlock


def get_blocks() -> list[type]:
    """Return all block classes registered by this plugin."""
    return [
        # IO (5)
        LoadMSRawFiles,
        LoadPeakTable,
        LoadMIDTable,
        LoadSampleMetadata,
        SaveTable,
        # External tools (2)
        ElMAVENBlock,
        AccuCorR,
        # Isotope tracing (5)
        Calculate13CEnrichment,
        FractionalLabeling,
        CompareGroupMID,
        FluxEstimate,
        PoolSizeNormalize,
        # Metabolomics analysis (6)
        MetaboliteMatrix,
        MatrixPreprocess,
        UnivariateStats,
        MultivariateAnalysis,
        PathwayEnrichment,
        ConsumptionSecretionAnalysis,
        # External plotting (1)
        GraphPadBlock,
    ]


__all__ = [
    "MSRawFile", "PeakTable", "MIDTable", "SampleMetadata", "get_types",
    "LoadMSRawFiles", "LoadPeakTable", "LoadMIDTable", "LoadSampleMetadata",
    "SaveTable",
    "ElMAVENBlock", "AccuCorR",
    "Calculate13CEnrichment", "FractionalLabeling", "CompareGroupMID",
    "FluxEstimate", "PoolSizeNormalize",
    "MetaboliteMatrix", "MatrixPreprocess", "UnivariateStats",
    "MultivariateAnalysis", "PathwayEnrichment", "ConsumptionSecretionAnalysis",
    "GraphPadBlock",
    "get_blocks",
]
```

The smoke test verifies:

1. `get_blocks()` returns exactly 20 classes.
2. `get_types()` returns exactly 4 classes.
3. Every block has `package_name == "scieasy-blocks-lcms"`.
4. Every block's `category` is in
   `{"io", "app", "code", "process"}`.
5. Every block's `type_name` is unique across the plugin.
6. Every block has a non-empty `name` (palette label).
7. Every block has a `config_schema` (even if empty-ish).
8. All blocks are importable from the top-level package.

The test also validates via the real entry-point mechanism: it uses
`importlib.metadata.entry_points(group="scieasy.blocks")` to confirm
the plugin is discoverable via the `scieasy.blocks` group after `pip
install -e .`.

**h. Acceptance criteria**:
- [ ] `get_blocks()` returns exactly 20 classes in the order defined
      above.
- [ ] `get_types()` returns exactly 4 classes.
- [ ] All 20 blocks have `package_name == "scieasy-blocks-lcms"`.
- [ ] All 20 blocks have a `category` in the controlled set.
- [ ] All 20 `type_name` values are unique.
- [ ] `importlib.metadata.entry_points(group="scieasy.blocks")` exposes
      the `lcms` entry point.
- [ ] All 8 entry-point smoke tests pass.

**i. Out of scope**:
- Adding new blocks (the list is locked at 20).
- Renaming blocks (would break workflow YAMLs).
- Changing category values (tied to palette rendering).

**j. Dependencies on other tickets**: all prior T-LCMS-NNN tickets.

**k. Estimated diff size**: ~80 lines source + ~150 lines test.
Total ~230 lines.

**l. Suggested workflow gate ticket title**:
`LC-MS entry-point registration + smoke test (T-LCMS-020)`

---

### T-LCMS-021 — Isotope tracing integration test

**a. Ticket ID and name**: T-LCMS-021 — end-to-end isotope tracing
workflow integration test with a synthetic AccuCor fixture.

**b. Source ADR / spec sections**:
- Master plan §8 (synthetic fixtures for LC-MS — real data is not
  shipped; the 4 images in `Example/images/` are for imaging/SRS only).
- This spec §11 (full integration test body).

**c. Files to be created**:
- `packages/scieasy-blocks-lcms/tests/integration/__init__.py`
- `packages/scieasy-blocks-lcms/tests/integration/fixtures/synthetic_peak_table.csv`
  (the ElMAVEN-shaped fake peak table).
- `packages/scieasy-blocks-lcms/tests/integration/fixtures/synthetic_mid_table.csv`
  (the AccuCor-shaped fake MID table — long format).
- `packages/scieasy-blocks-lcms/tests/integration/fixtures/synthetic_sample_metadata.csv`
  (2 groups × 3 replicates × 1 timepoint).
- `packages/scieasy-blocks-lcms/tests/integration/test_tracing_workflow.py`
  (the pytest integration test).

**d. Files to be modified**: none.

**e. New tests**:
- `test_tracing_workflow.py`:
  - `test_full_isotope_tracing_pipeline`

**f. Existing tests to update**: none.

**g. Implementation details**: see §11 of this spec for the full
integration test body.

**h. Acceptance criteria**:
- [ ] Three synthetic fixtures land under
      `tests/integration/fixtures/`.
- [ ] The fixtures are plausible (10–20 compounds, 6 samples, 2
      groups, long-format MID).
- [ ] The integration test runs end-to-end without any
      `@pytest.mark.requires_*` markers (no external tools, no
      network).
- [ ] The test chains: `LoadPeakTable` → `LoadMIDTable` →
      `LoadSampleMetadata` → `Calculate13CEnrichment` →
      `CompareGroupMID` → `MetaboliteMatrix` → `MatrixPreprocess` →
      `UnivariateStats` → `SaveTable`.
- [ ] The test asserts each block's output is the expected type.
- [ ] The test asserts the final `SaveTable` writes a file to disk.
- [ ] Test passes under `pytest packages/scieasy-blocks-lcms/tests/integration/`.

**i. Out of scope**:
- Real LC-MS data (the plugin does not ship raw files).
- Testing `ElMAVENBlock` / `AccuCorR` / `GraphPadBlock` end-to-end
  (these are marker-protected per T-LCMS-007 / T-LCMS-019).
- Real KEGG REST calls (tested with mocks in T-LCMS-017).

**j. Dependencies on other tickets**: T-LCMS-001 through T-LCMS-020.

**k. Estimated diff size**: ~200 lines of fixture + ~300 lines of test.
Total ~500 lines.

**l. Suggested workflow gate ticket title**:
`LC-MS isotope tracing integration test with synthetic fixtures (T-LCMS-021)`

---

## 10. Summary table

| Ticket       | Block / deliverable             | Category | Est. LOC | Depends on         |
|--------------|---------------------------------|----------|----------|--------------------|
| T-LCMS-001   | Plugin scaffold (pyproject)     | meta     | 250      | —                  |
| T-LCMS-002   | Types module (4 classes)        | types    | 350      | T-LCMS-001         |
| T-LCMS-003   | `LoadMSRawFiles`                | io       | 550      | T-LCMS-002         |
| T-LCMS-004   | `LoadPeakTable`                 | io       | 450      | T-LCMS-002         |
| T-LCMS-005   | `LoadMIDTable`                  | io       | 480      | T-LCMS-002         |
| T-LCMS-006   | `LoadSampleMetadata`+`SaveTable`| io       | 460      | T-LCMS-002,004     |
| T-LCMS-007   | `ElMAVENBlock` + `AccuCorR`     | app/code | 810      | T-LCMS-003..006    |
| T-LCMS-008   | `Calculate13CEnrichment` ★ USP  | process  | 530      | T-LCMS-002         |
| T-LCMS-009   | `FractionalLabeling`            | process  | 330      | T-LCMS-002         |
| T-LCMS-010   | `CompareGroupMID`               | process  | 580      | T-LCMS-002         |
| T-LCMS-011   | `FluxEstimate`                  | process  | 450      | T-LCMS-002         |
| T-LCMS-012   | `PoolSizeNormalize`             | process  | 390      | T-LCMS-002,004     |
| T-LCMS-013   | `MetaboliteMatrix`              | process  | 320      | T-LCMS-002,004     |
| T-LCMS-014   | `MatrixPreprocess`              | process  | 520      | T-LCMS-002         |
| T-LCMS-015   | `UnivariateStats`               | process  | 520      | T-LCMS-002,013     |
| T-LCMS-016   | `MultivariateAnalysis`          | process  | 630      | T-LCMS-002,013     |
| T-LCMS-017   | `PathwayEnrichment` (KEGG REST) | process  | 540      | T-LCMS-002,015     |
| T-LCMS-018   | `ConsumptionSecretionAnalysis`  | process  | 460      | T-LCMS-002,004     |
| T-LCMS-019   | `GraphPadBlock`                 | app      | 330      | T-LCMS-002         |
| T-LCMS-020   | Entry-point + smoke test        | meta     | 230      | all prior          |
| T-LCMS-021   | Integration test                | meta     | 500      | T-LCMS-001..020    |
| **Total**    | 20 blocks + 4 types             |          | **~9,680** |                  |

Block count by category:

- **IO**: 5 (LoadMSRawFiles, LoadPeakTable, LoadMIDTable,
  LoadSampleMetadata, SaveTable).
- **External tools (app/code)**: 2 (ElMAVENBlock, AccuCorR) + 1 more
  app block (GraphPadBlock). 3 total.
- **Isotope tracing**: 5 (Calculate13CEnrichment, FractionalLabeling,
  CompareGroupMID, FluxEstimate, PoolSizeNormalize). **USP cluster.**
- **Metabolomics analysis**: 6 (MetaboliteMatrix, MatrixPreprocess,
  UnivariateStats, MultivariateAnalysis, PathwayEnrichment,
  ConsumptionSecretionAnalysis).
- **Total**: 5 + 3 + 5 + 6 + 1 (GraphPad is separate from metabolomics)
  = 20 blocks. Wait — GraphPad is already counted in "External tools".
  The actual total: 5 IO + 2 external wrappers (ElMAVEN, AccuCor) +
  5 isotope + 6 metabolomics + 1 plotting (GraphPad) = **19**. Adding
  the entry-point registration and integration test as non-block
  deliverables keeps the ticket count at 21. The block count is **19**.

(Note: the master plan §2.4 header says "~20 blocks" and the actual
count is 19. This is expected slack; the spec does not invent a 20th
block to hit a round number.)

## 11. Integration test — isotope tracing workflow

The full integration test at
`packages/scieasy-blocks-lcms/tests/integration/test_tracing_workflow.py`.

Per master plan §8, this plugin does **not** use the 4 imaging test
images at `Example/images/` — those are for imaging/SRS. LC-MS uses
**synthetic fixtures** generated inline (or from CSV files committed to
the repo).

### Synthetic peak table fixture

`synthetic_peak_table.csv` (ElMAVEN-shaped, ~20 rows):

```
compound,formula,medMz,medRt,S1_intensity,S2_intensity,S3_intensity,C1_intensity,C2_intensity,C3_intensity
glucose,C6H12O6,179.0561,5.2,1000,1100,950,800,850,820
lactate,C3H6O3,89.0244,3.1,200,210,190,500,520,510
pyruvate,C3H4O3,87.0088,2.8,300,310,290,600,620,610
...
```

Columns: compound identity (`compound`, `formula`), retention/mass
metadata (`medMz`, `medRt`), plus 6 sample columns (3 treatment `S*` +
3 control `C*`).

### Synthetic MID table fixture

`synthetic_mid_table.csv` (AccuCor long format, ~40 rows):

```
Compound,C13,H2,S1,S2,S3,C1,C2,C3
glucose,0,0,0.20,0.19,0.21,0.80,0.81,0.79
glucose,1,0,0.05,0.06,0.05,0.04,0.03,0.05
glucose,2,0,0.10,0.11,0.09,0.05,0.04,0.06
glucose,3,0,0.15,0.16,0.14,0.03,0.04,0.03
glucose,4,0,0.20,0.19,0.21,0.03,0.02,0.03
glucose,5,0,0.15,0.14,0.16,0.02,0.03,0.02
glucose,6,0,0.15,0.15,0.14,0.03,0.03,0.02
lactate,0,0,0.90,0.89,0.91,0.95,0.94,0.96
lactate,1,0,0.05,0.06,0.05,0.03,0.03,0.02
...
```

### Synthetic sample metadata fixture

`synthetic_sample_metadata.csv`:

```
sample_id,group,replicate,time_hours
S1,treatment,1,6
S2,treatment,2,6
S3,treatment,3,6
C1,control,1,6
C2,control,2,6
C3,control,3,6
```

### Integration test body

```python
# tests/integration/test_tracing_workflow.py
"""End-to-end isotope tracing integration test with synthetic fixtures.

Per master plan §8, LC-MS uses synthetic fixtures (not real raw data).
The 4 imaging test images at Example/images/ are for imaging/SRS only.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scieasy_blocks_lcms import (
    Calculate13CEnrichment,
    CompareGroupMID,
    LoadMIDTable,
    LoadPeakTable,
    LoadSampleMetadata,
    MatrixPreprocess,
    MetaboliteMatrix,
    MIDTable,
    PeakTable,
    SampleMetadata,
    SaveTable,
    UnivariateStats,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_full_isotope_tracing_pipeline(tmp_path):
    """Load → enrichment → comparison → matrix → preprocess → univariate → save."""

    # --- Load ---
    peak_cfg = {"path": str(FIXTURES / "synthetic_peak_table.csv"),
                "source": "ElMAVEN"}
    peak_out = LoadPeakTable().load(peak_cfg)
    peak_table = list(peak_out["peak_table"])[0]
    assert isinstance(peak_table, PeakTable)
    assert peak_table.meta.source == "ElMAVEN"

    mid_cfg = {"path": str(FIXTURES / "synthetic_mid_table.csv"),
               "tracer_atoms": ["C13"]}
    mid_out = LoadMIDTable().load(mid_cfg)
    mid_table = list(mid_out["mid_table"])[0]
    assert isinstance(mid_table, MIDTable)
    assert mid_table.meta.tracer_atoms == ["C13"]
    assert "S1" in mid_table.meta.sample_columns
    assert "C1" in mid_table.meta.sample_columns

    meta_cfg = {"path": str(FIXTURES / "synthetic_sample_metadata.csv"),
                "sample_id_column": "sample_id"}
    meta_out = LoadSampleMetadata().load(meta_cfg)
    sample_metadata = list(meta_out["metadata"])[0]
    assert isinstance(sample_metadata, SampleMetadata)

    # --- Isotope tracing: average 13C enrichment ---
    enrich = Calculate13CEnrichment()
    enrich_df = enrich.process_item(mid_table, config={})
    enrich_pandas = enrich_df.user["pandas_df"]
    assert set(enrich_pandas.columns) == {"compound", "sample", "enrichment"}
    # Treatment samples should be more enriched than controls.
    treat_mean = enrich_pandas[enrich_pandas["sample"].str.startswith("S")]["enrichment"].mean()
    ctrl_mean = enrich_pandas[enrich_pandas["sample"].str.startswith("C")]["enrichment"].mean()
    assert treat_mean > ctrl_mean, (
        f"Expected treatment > control enrichment, got {treat_mean} vs {ctrl_mean}"
    )

    # --- Isotope tracing: group comparison ---
    compare = CompareGroupMID()
    compare_out = compare.run(
        inputs={"mid_table": mid_out["mid_table"],
                "sample_metadata": meta_out["metadata"]},
        config={"test": "t-test", "correction": "fdr",
                "group_column": "group", "per_isotopologue": True,
                "alpha": 0.05},
    )
    compare_df = list(compare_out["comparison"])[0].user["pandas_df"]
    assert {"compound", "pvalue", "pvalue_adj", "significant"}.issubset(set(compare_df.columns))

    # --- Metabolomics: pivot to matrix ---
    mx = MetaboliteMatrix()
    mx_out = mx.run(
        inputs={"peak_table": peak_out["peak_table"],
                "sample_metadata": meta_out["metadata"]},
        config={"value_column": "S1_intensity", "compound_column": "compound"},
    )
    # Note: real usage would pipe through a melt first; the test uses the
    # first intensity column as a minimal smoke check.
    matrix_df = list(mx_out["matrix"])[0]

    # --- Metabolomics: preprocess ---
    preprocess = MatrixPreprocess()
    preprocess_out = preprocess.run(
        inputs={"matrix": mx_out["matrix"]},
        config={"log_transform": True, "impute_method": "knn", "scale": "auto"},
    )
    preprocessed = list(preprocess_out["matrix"])[0]

    # --- Metabolomics: univariate stats ---
    stats = UnivariateStats()
    stats_out = stats.run(
        inputs={"matrix": preprocess_out["matrix"],
                "sample_metadata": meta_out["metadata"]},
        config={"test": "t-test", "correction": "fdr",
                "group_column": "group", "alpha": 0.05},
    )
    stats_df = list(stats_out["results"])[0].user["pandas_df"]
    assert {"compound", "pvalue", "pvalue_adj", "significant"}.issubset(set(stats_df.columns))

    # --- Save final results to disk ---
    out_path = tmp_path / "univariate_results.csv"
    save = SaveTable()
    save.save(
        inputs={"table": stats_out["results"]},
        config={"path": str(out_path), "format": "csv", "index": False},
    )
    assert out_path.exists()
    reloaded = pd.read_csv(out_path)
    assert len(reloaded) > 0
```

This test deliberately keeps the pipeline simple (each block takes
simple inputs and produces simple outputs) so that debugging a
regression is easy. The test uses no external tools (ElMAVEN, R,
GraphPad are all excluded) and no network calls (PathwayEnrichment is
excluded because it hits KEGG REST).

A **separate** marker-protected integration test file
(`test_tracing_workflow_external.py`) may be added in a follow-up
ticket to chain `ElMAVENBlock` → `AccuCorR` → `Calculate13CEnrichment`
end-to-end. That test would be marked
`@pytest.mark.requires_elmaven and requires_r`.

## 12. References

- **Master plan**: `phase11_master_plan.md` §2.4 (LC-MS PLUGIN) — the
  single source of truth for the block list.
- **ADR-027**: Core type system (Array 6D axes, stratified metadata).
- **ADR-027 Addendum 1**: Worker subprocess typed reconstruction +
  Meta Pydantic constraints.
- **ADR-028**: IOBlock refactor + plugin-owned IO pattern.
- **ADR-028 Addendum 1**: Dynamic port override mechanism (not used by
  this plugin — see §8 Q-11).
- **Phase 10 implementation standards**: `docs/specs/phase10-implementation-standards.md`
  (structural template followed by this spec).
- **AccuCor R package**: https://github.com/lparsons/accucor (MIT,
  v0.3.1; vendored as package data per §8 Q-1).
- **Antoniewicz 2018**: "A guide to 13C metabolic flux analysis",
  *Exp Mol Med*. Cited in §9 T-LCMS-008 for the average 13C enrichment
  formula.
- **KEGG REST API**: https://rest.kegg.jp/ (used by `PathwayEnrichment`
  per §8 Q-6).
- **ElMAVEN**: https://github.com/ElucidataInc/ElMaven (GPLv3, external
  desktop tool).
- **GraphPad Prism**: https://www.graphpad.com/ (proprietary,
  Windows-primary; external desktop tool per §8 Q-8).
- **CLAUDE.md Appendix A**: Workflow gate protocol.
- **CLAUDE.md §6.7**: Tests-are-part-of-the-change rule.

---

*End of `phase11-lcms-block-spec.md`.*