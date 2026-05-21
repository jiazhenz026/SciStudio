---
spec_id: phase11-imaging-block-spec
title: "Phase 11 Imaging Plugin Block Specification"
status: Deprecated
feature_branch: legacy/phase11-imaging-block-spec
created: 2026-04-07
input: "Historical Phase 11 scieasy-blocks-imaging implementation specification retained for reference."
owners:
  - "@jiazhenz026"
related_adrs:
  - 27
  - 28
  - 29
related_specs:
  - phase11-implementation-standards
scope:
  in:
    - Historical imaging plugin block contracts retained for reference.
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
# Phase 11 Imaging Plugin Block Specification

## 1. Change Summary

This deprecated spec is retained as historical reference. Its original body is preserved below, but it is not an active implementation spec under ADR-042.

## 2. Existing Historical Body

# Phase 11 `scieasy-blocks-imaging` Implementation Specification

**Status**: accepted
**Date**: 2026-04-07
**Issue**: #298
**Authoritative ADRs**: ADR-027 (core types), ADR-027 Addendum 1 (worker
reconstruction + Pydantic Meta), ADR-028 (IOBlock refactor), ADR-028
Addendum 1 (dynamic ports + GUI consequences), ADR-029 (preliminary,
variadic ports — informational only).

---

## 1. Purpose

`scieasy-blocks-imaging` is the first SciEasy plugin package, shipping a
general-purpose set of blocks for fluorescence, brightfield, confocal,
widefield, hyperspectral, and label-free microscopy. It is the
flagship plugin used to validate ADR-028's plugin-IO contract and
ADR-027 D7's `setup` / `teardown` lifecycle hooks (via the
`CellposeSegment` block).

This document is the **single source of truth** for the ~38
implementation tickets that compose the imaging plugin from an empty
package skeleton through release 0.1.0. Each ticket below is a complete
contract specifying which files to create, which to modify, which tests
to add, the acceptance criteria, the dependencies on other tickets, and
explicit out-of-scope notes.

A subsequent implementation agent picking up any single ticket should
**not need to re-read the ADRs**. This document quotes the ADR
pseudocode where the contract is load-bearing, and cites the specific
Decision letter (D1', D2', ...) from ADR-028 / Addendum 1 and (D1, D2,
...) from ADR-027 for traceability.

**Target users**: experimental cell biologists, microscopists,
biophysicists, and computational scientists analysing image data who
do not want to write Python plumbing for every workflow. The block
list is biased toward cancer biology / immunology / metabolic imaging
because that is the primary user's domain, but every block is generic
enough to apply to any quantitative microscopy.

**Phase 10 dependencies**: this plugin requires the Phase 10 core
surface as merged on `main` at `1406b2a`:

- `scieasy.core.types.array.Array` with instance-level axes and
  `required_axes` / `allowed_axes` / `canonical_order` ClassVar schema
  (T-006).
- `scieasy.core.types.composite.CompositeData` with `expected_slots`
  ClassVar schema (T-007).
- `scieasy.core.types.dataframe.DataFrame` for tabular outputs (T-007).
- `scieasy.core.types.artifact.Artifact` for visualization outputs
  (T-007).
- `scieasy.core.types.collection.Collection` for batch transport.
- `scieasy.core.meta.FrameworkMeta` and `ChannelInfo` (T-004).
- `scieasy.core.units.PhysicalQuantity` with Pydantic v2 integration
  (T-003).
- `scieasy.utils.axis_iter.iterate_over_axes(source, operates_on, func)`
  (T-011).
- `scieasy.utils.constraints.has_axes` / `has_exact_axes` / `has_shape`
  (T-010).
- `scieasy.blocks.process.ProcessBlock` with `setup` / `teardown` hooks
  and three-arg `process_item(self, item, config, state=None)` (T-009).
- `scieasy.blocks.io.IOBlock` as abstract base class with abstract
  `load()` / `save()` (ADR-028).
- `BlockRegistry` reading `dynamic_ports` ClassVar (ADR-028 Addendum 1).
- `Block.get_effective_input_ports()` / `get_effective_output_ports()`
  override hooks (ADR-028 Addendum 1).
- Worker subprocess returning typed `DataObject` instances via
  `_reconstruct_one` / `_serialise_one` (ADR-027 Addendum 1).

---

## 2. Scope

**In scope**: contracts for tickets T-IMG-001 through T-IMG-038, the
complete `scieasy-blocks-imaging` 0.1.0 release. The package lives at
`packages/scieasy-blocks-imaging/` inside the SciEasy monorepo per
master plan Q1.

**Out of scope**:

- Tracking blocks beyond a single `TrackObjects` palette placeholder
  (Phase 12).
- Deconvolution beyond a single `Deconvolve` palette placeholder
  (Phase 12).
- StarDist segmentation (deferred — `cellpose` is the only supported
  deep-learning segmentor in 0.1.0).
- SRS-specific blocks (`SRSCalibrate`, `SRSUnmix`, `ExtractSpectrum`,
  ...) — those live in `scieasy-blocks-srs` per
  `docs/specs/phase11-srs-block-spec.md`.
- LC-MS blocks — those live in `scieasy-blocks-lcms` per
  `docs/specs/phase11-lcms-block-spec.md`.
- The cross-plugin E2E pipeline (imaging + SRS + core IO) is referenced
  here for completeness in §11 but its `ExtractSpectrum` half is
  specified by the SRS spec.
- AI-driven variadic ports on `ImageCalculator` (deferred to ADR-029).
  0.1.0 ships fixed two-input ports (A and B) plus an expression mode
  with the variables `a` and `b` only.
- Frontend (`frontend/`) changes — the imaging plugin reuses the
  existing `BlockNode.tsx` rendering via the generic
  `category === "io"` path landed in ADR-028 Addendum 1. No new React
  component or schema response field is introduced by this plugin.
- The plugin skeleton itself (the `packages/scieasy-blocks-imaging/`
  directory tree with placeholder `NotImplementedError` files) is
  produced by the **Skeleton Agent** per master plan §4.2 Step 8 — not
  by these implementation tickets, which fill in the bodies.
- ADR-029 design decisions. ADR-029 is referenced as "informational"
  for the `ImageCalculator` variadic deferral, but its content is
  preliminary.

---

## 3. Cross-reference table

| Ticket    | Title                                      | Source ADR / utility                                              |
|-----------|--------------------------------------------|-------------------------------------------------------------------|
| T-IMG-001 | Types module (Image / Mask / Label / Transform) | ADR-027 D1, D2 (Array subclassing), D5 (Meta Pydantic), D7 (subclass schema), Addendum 1 §3 (Meta JSON-round-trip) |
| T-IMG-002 | LoadImage                                  | ADR-028 §D3' (plugin IO classes), ADR-028 Addendum 1 §D6' (plugin IO stays static), ADR-027 D1 (axes propagation) |
| T-IMG-003 | SaveImage                                  | ADR-028 §D3' (plugin IO classes), ADR-028 §D7 (`direction = "output"`) |
| T-IMG-004 | Denoise                                    | ADR-027 D3 (`iterate_over_axes`), ADR-027 D4 companion (constraints) |
| T-IMG-005 | BackgroundSubtract                         | ADR-027 D3, D5 (meta propagation)                                  |
| T-IMG-006 | Normalize                                  | ADR-027 D3, D5                                                     |
| T-IMG-007 | FlatFieldCorrect                           | ADR-027 D3, ADR-027 D2 (multi-input ports)                         |
| T-IMG-008 | Geometry bundle (Rotate/Flip/Crop/Pad/Resize) | ADR-027 D5 (meta propagation under shape change)                |
| T-IMG-009 | ConvertDType                               | ADR-027 D5                                                         |
| T-IMG-010 | AxisSplit / AxisMerge                      | ADR-027 D1 (axes), D5, ADR-020 (Collection)                        |
| T-IMG-011 | Deconvolve placeholder                     | ADR-027 D9 (palette discoverability)                               |
| T-IMG-012 | MorphologyOp                               | ADR-027 D3                                                         |
| T-IMG-013 | EdgeDetect                                 | ADR-027 D3                                                         |
| T-IMG-014 | RidgeFilter                                | ADR-027 D3                                                         |
| T-IMG-015 | Sharpen                                    | ADR-027 D3                                                         |
| T-IMG-016 | FFTFilter                                  | ADR-027 D3                                                         |
| T-IMG-017 | Threshold                                  | ADR-027 D3, D2 (Mask subclass output)                              |
| T-IMG-018 | Watershed                                  | ADR-027 D3, D2 (Label output), CompositeData.expected_slots        |
| T-IMG-019 | CellposeSegment (flagship)                 | ADR-027 D7 (`setup` / `teardown`), D2 (Label), ADR-027 D10 (GPU auto-detect interaction) |
| T-IMG-020 | BlobDetect                                 | ADR-027 D3, D2                                                     |
| T-IMG-021 | ConnectedComponents                        | ADR-027 D3, D2                                                     |
| T-IMG-022 | Cleanup bundle                             | ADR-027 D3                                                         |
| T-IMG-023 | TrackObjects placeholder                   | ADR-027 D9                                                         |
| T-IMG-024 | RegionProps                                | ADR-027 D2 (DataFrame output), ADR-020 (Collection)                |
| T-IMG-025 | PairwiseDistance                           | ADR-027 D2 (DataFrame output)                                      |
| T-IMG-026 | Colocalization                             | ADR-027 D2 (DataFrame output), D3                                  |
| T-IMG-027 | ComputeRegistration                        | ADR-027 D2 (Transform output), D3                                  |
| T-IMG-028 | ApplyTransform                             | ADR-027 D3, D5                                                     |
| T-IMG-029 | RegisterSeries                             | ADR-027 D3, D5, D2 (Collection[Transform] secondary output)        |
| T-IMG-030 | AxisProjection / SelectSlice               | ADR-027 D1 (axes), D4 (`sel`), D5                                  |
| T-IMG-031 | Math scalar bundle                         | ADR-027 D3                                                         |
| T-IMG-032 | ImageCalculator                            | ADR-027 D3, ADR-029 (informational — variadic deferred)            |
| T-IMG-033 | Visualization bundle                       | ADR-027 D2 (Artifact output)                                       |
| T-IMG-034 | FijiBlock                                  | ADR-019 (AppBlock + ProcessHandle + FileWatcher), ADR-020          |
| T-IMG-035 | NapariBlock                                | ADR-019                                                            |
| T-IMG-036 | CellProfilerBlock                          | ADR-019                                                            |
| T-IMG-037 | QuPathBlock                                | ADR-019                                                            |
| T-IMG-038 | Plugin packaging                           | ADR-025 (`scieasy.blocks` / `scieasy.types` entry-point groups), ADR-028 §D8 |

---

## 4. Dependency graph

```
                     T-IMG-001 (types)
                          |
              +-----------+-----------+
              |                       |
              v                       v
        T-IMG-002 (LoadImage)   T-IMG-038 (packaging)
              |                       ^
              v                       |
        T-IMG-003 (SaveImage)         |
              |                       |
              v                       |
        +-----+----------------+      |
        |           |          |      |
        v           v          v      |
    Preprocessing  Morph    Segment   |
    cluster        cluster  cluster   |
    T-IMG-004      T-IMG-012  T-IMG-017|
    T-IMG-005      T-IMG-013  T-IMG-018|
    T-IMG-006      T-IMG-014  T-IMG-019  <-- flagship: needs T-009 setup/teardown
    T-IMG-007      T-IMG-015  T-IMG-020|
    T-IMG-008      T-IMG-016  T-IMG-021|
    T-IMG-009                 T-IMG-022|
    T-IMG-010                 T-IMG-023 (placeholder)
    T-IMG-011                          |
    (placeholder)                      |
                                       |
                  Measurement cluster  |
                  T-IMG-024 (RegionProps)
                  T-IMG-025 (PairwiseDistance)
                  T-IMG-026 (Colocalization)
                                       |
                  Registration cluster |
                  T-IMG-027 (ComputeRegistration)
                  T-IMG-028 (ApplyTransform)
                  T-IMG-029 (RegisterSeries)
                                       |
                  Axis cluster         |
                  T-IMG-030 (AxisProjection / SelectSlice)
                                       |
                  Math cluster         |
                  T-IMG-031 (scalar)   |
                  T-IMG-032 (ImageCalculator)
                                       |
                  Visualization cluster|
                  T-IMG-033            |
                                       |
                  Interactive cluster  |
                  T-IMG-034 (Fiji)     |
                  T-IMG-035 (Napari)   |
                  T-IMG-036 (CellProfiler)
                  T-IMG-037 (QuPath)   |
                                       v
                          T-IMG-038 (final packaging review)
```

**Critical path**: T-IMG-001 → T-IMG-002 → T-IMG-003 → (T-IMG-004 +
T-IMG-019) → T-IMG-038. The E2E test in §11 requires only T-IMG-001,
T-IMG-002, T-IMG-003, T-IMG-004, T-IMG-019, and T-IMG-038 to be
landed before it can run.

**Independent clusters**: morphology / measurement / registration /
math / visualization / interactive can land in any order once their
common prerequisites (T-IMG-001 types, T-IMG-002 LoadImage for end-to-end
testing) are present.

**Hard dependency on Phase 10 core**: T-IMG-019 requires T-009 (the
`ProcessBlock.setup` / `teardown` hooks merged in PR #280) — already
on `main` at the time this spec is written. Every block that uses
`iterate_over_axes` for 3D+ broadcasting requires T-011 (also merged on
`main`).

---

## 5. Recommended chained PR order

The recommended linear order, where each PR's base is the previous
PR's branch (stacked PRs) when not yet merged, or `main` when the
predecessor has merged:

1. **T-IMG-038a** — package skeleton: `pyproject.toml`, empty
   `__init__.py` with `get_blocks()` / `get_types()` stubs returning
   empty list, directory tree per §"Package layout" below. (This is
   the half of T-IMG-038 that ships first; the second half T-IMG-038b
   adds the entry-point registrations after all blocks land.) **Owned
   by the Skeleton Agent**, not an implementation ticket; this spec
   documents the contract the Skeleton Agent must satisfy.
2. **T-IMG-001** — types (`Image` / `Mask` / `Label` / `Transform`).
3. **T-IMG-002** — `LoadImage`.
4. **T-IMG-003** — `SaveImage`.
5. **T-IMG-004** — `Denoise`.
6. **T-IMG-019** — `CellposeSegment` (flagship; can land in parallel
   with the other preprocessing blocks once T-IMG-001 / T-IMG-002 /
   T-IMG-004 are in).
7. After step 6 the **E2E test in §11 can run**. The remaining tickets
   land in any order:
8. **T-IMG-005** — `BackgroundSubtract`.
9. **T-IMG-006** — `Normalize`.
10. **T-IMG-007** — `FlatFieldCorrect`.
11. **T-IMG-008** — Geometry bundle.
12. **T-IMG-009** — `ConvertDType`.
13. **T-IMG-010** — `AxisSplit` / `AxisMerge`.
14. **T-IMG-011** — `Deconvolve` placeholder.
15. **T-IMG-012** — `MorphologyOp`.
16. **T-IMG-013** — `EdgeDetect`.
17. **T-IMG-014** — `RidgeFilter`.
18. **T-IMG-015** — `Sharpen`.
19. **T-IMG-016** — `FFTFilter`.
20. **T-IMG-017** — `Threshold`.
21. **T-IMG-018** — `Watershed`.
22. **T-IMG-020** — `BlobDetect`.
23. **T-IMG-021** — `ConnectedComponents`.
24. **T-IMG-022** — Cleanup bundle.
25. **T-IMG-023** — `TrackObjects` placeholder.
26. **T-IMG-024** — `RegionProps`.
27. **T-IMG-025** — `PairwiseDistance`.
28. **T-IMG-026** — `Colocalization`.
29. **T-IMG-027** — `ComputeRegistration`.
30. **T-IMG-028** — `ApplyTransform`.
31. **T-IMG-029** — `RegisterSeries`.
32. **T-IMG-030** — `AxisProjection` / `SelectSlice`.
33. **T-IMG-031** — Math scalar bundle.
34. **T-IMG-032** — `ImageCalculator`.
35. **T-IMG-033** — Visualization bundle.
36. **T-IMG-034** — `FijiBlock`.
37. **T-IMG-035** — `NapariBlock`.
38. **T-IMG-036** — `CellProfilerBlock`.
39. **T-IMG-037** — `QuPathBlock`.
40. **T-IMG-038b** — final packaging: register all blocks in
    `get_blocks()`, register all types in `get_types()`, finalise
    `pyproject.toml` `[project.entry-points]` table, write `README.md`,
    bump version to 0.1.0.

If parallel work is desired: most blocks are independent. The hard
serial points are: T-IMG-001 → everything (types must exist first),
T-IMG-002 → E2E test (need a loader), T-IMG-019 → E2E test (need
segmentation). Outside of those, multiple impl agents can work
simultaneously as long as their PRs do not collide on
`packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`
— which they will, because each block must be registered there. The
recommended pattern is: each impl agent appends its block to the
`get_blocks()` list and the `__init__.py` `__all__`, and the manager
resolves trivial conflicts at merge time.

---

## 6. Universal rules for all imaging implementation agents

These rules apply to **every** ticket in this document. Failure to
follow them is a workflow gate violation.

1. **Workflow gate is mandatory** — every ticket follows the full
   6-stage workflow gate per `CLAUDE.md` Appendix A. No exceptions
   for "small" tickets. Each stage must show `[DONE]` in
   `python .workflow/gate.py status <task_id>` before the next stage
   begins.
2. **Branch naming**: `feat/issue-N/T-IMG-NNN-short-name` (replace
   `feat` with `fix` for bug-fix tickets). Example for T-IMG-019:
   `feat/issue-XXX/T-IMG-019-cellpose-segment`.
3. **Stacked PR base** — each PR's base branch is the previous merged
   PR's branch (so the diffs compose cleanly). If the previous PR has
   already merged into `main`, base off `main` directly. Mark stacked
   PRs with the previous PR number in the description.
4. **Out-of-scope changes are forbidden** — the PR's diff must
   contain only the files listed in the ticket's "Files to be
   created", "Files to be modified", "New tests", and "Existing
   tests to update" sections. Any other modified file is a scope
   violation per `CLAUDE.md` §6.7.
5. **Every check must be green before review**:
   - `pytest -x --no-cov packages/scieasy-blocks-imaging/tests/`
     passes locally.
   - `ruff check packages/scieasy-blocks-imaging/` clean.
   - `ruff format --check packages/scieasy-blocks-imaging/` clean.
   - `mypy packages/scieasy-blocks-imaging/src --ignore-missing-imports`
     clean.
   - For tickets that touch core (none should), additionally
     `python -m importlinter --config pyproject.toml` clean.
6. **CHANGELOG.md** must be updated under `[Unreleased]` in the
   appropriate section (`Added` / `Changed` / `Fixed`) with full
   attribution per `CLAUDE.md` Appendix A Stage 6:
   `[#N] Description (@claude, YYYY-MM-DD, branch: ..., session: ...)`.
7. **PR body must reference**:
   - The ADR section the PR implements
     (e.g. "Implements ADR-027 D7 + ADR-028 §D3'").
   - The ticket ID from this standards doc (e.g. "Per
     `docs/specs/phase11-imaging-block-spec.md` T-IMG-019").
   - The previous PR in the stack (if any).
   - A reproduction of the ticket's acceptance criteria as a checklist
     with each box ticked when satisfied.
8. **No silent scope expansion** — if implementing a ticket reveals a
   pre-existing bug in core or design ambiguity, open a *new issue*
   describing it. Do not fix it inline. Per `CLAUDE.md` §9.2 ("Claude
   must not silently broaden scope") and Appendix C Step 3.
9. **No core modifications** — the imaging plugin must not modify any
   file under `src/scieasy/`. If a block needs a feature core does not
   provide, open a follow-up issue requesting the core change and
   either skip or stub the affected behaviour. The `importlinter`
   contract `Plugins must not write to core` is the audit gate.
10. **Optional dependencies declared in extras** — heavy dependencies
    (`cellpose`, `napari`, `aicsimageio`, `nd2reader`, `readlif`) live
    in `[project.optional-dependencies]` extras (`cellpose`, `napari`,
    `czi`, `nd2`, `lif`, `all`). Tests for blocks behind extras are
    marked with `@pytest.mark.requires_<extra>` and skipped when the
    extra is not installed. Production code must guard the import with
    a `try` / `except ImportError` and raise a friendly
    `ImportError("install scieasy-blocks-imaging[<extra>]")` when the
    block is invoked without the extra.
11. **Every block declares `category`, `type_name`, `name` ClassVars
    correctly** — `category` is one of `io`, `preprocessing`,
    `morphology`, `segmentation`, `tracking`, `measurement`,
    `registration`, `axis`, `math`, `visualization`, `interactive`.
    `type_name` is `imaging.<lowercase_underscore>` (e.g.
    `imaging.cellpose_segment`). `name` is the human-readable display
    name (e.g. `"Cellpose Segmentation"`).
12. **Metadata propagation is mandatory** — every block that produces a
    new `Image` / `Mask` / `Label` derives `framework` via
    `parent.framework.derive(...)`, shares `meta` by reference unless
    physically meaningful fields change (e.g. `Resize` updates
    `pixel_size`), and shallow-copies `user`. This is the contract
    inherited from ADR-027 D5; any block violating it is rejected.

---

## 7. Universal acceptance criteria (apply to ALL imaging tickets)

In addition to each ticket's own acceptance criteria, every ticket
must satisfy these:

1. The PR's diff includes ONLY files listed in "Files to be created",
   "Files to be modified", "New tests", and "Existing tests to update"
   for that ticket. Any other modified file is a scope violation.
2. `pytest -x --no-cov packages/scieasy-blocks-imaging/tests/` passes
   locally before push.
3. `ruff check packages/scieasy-blocks-imaging/` clean.
4. `ruff format --check packages/scieasy-blocks-imaging/` clean.
5. `mypy packages/scieasy-blocks-imaging/src --ignore-missing-imports`
   clean.
6. `CHANGELOG.md` has an entry under `[Unreleased]` in the appropriate
   section with full attribution per `CLAUDE.md` Appendix A Stage 6.
7. Workflow gate has all 6 stages `[DONE]`.
8. PR body explicitly references which ADR section it implements and
   links to this standards doc by ticket ID.
9. PR body reproduces the ticket's per-ticket acceptance criteria as a
   checklist with each item ticked.
10. CI is green on the PR before requesting review.
11. The block is appended to `get_blocks()` in
    `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`
    in the same PR. (Exception: T-IMG-001 ships only types and is
    registered via `get_types()`.)
12. The block round-trips through worker subprocess reconstruction —
    a smoke test in the ticket's test file constructs an instance,
    serialises it via `_serialise_one`, reconstructs via
    `_reconstruct_one`, and asserts type / axes / meta equality. This
    catches Meta-class JSON-round-trip violations early.

---

## 8. Open questions resolved

These are decisions made in this document that go *beyond* the ADR
text and the locked block list. The master plan deferred them to the
implementation phase; this section records the resolution so subsequent
agents do not have to re-litigate.

### Q-IMG-1: Where does the TIFF JSON-in-ImageDescription metadata protocol live?

OptEasy's `tiff_adapter.py` carries an established protocol for
embedding Pydantic-encoded metadata in the TIFF `ImageDescription` tag
as a UTF-8 JSON string with the sentinel prefix `OPTEASY:`. SciEasy
inherits this verbatim per ADR-028 §D5.

**Decision**: the JSON-in-ImageDescription helpers live as **private
module-level functions** inside
`packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/load_image.py`
and the symmetric `save_image.py`. They are NOT exposed publicly. The
function names are `_decode_metadata_json(description: str | None) ->
dict | None` and `_encode_metadata_json(meta: BaseModel) -> str`. The
sentinel is renamed `SCIEASY:` for the new project.

**Rationale**:

- Keeps the protocol close to its only consumers (the TIFF loader and
  saver).
- Module-private functions match the ADR-028 Addendum 1 §D2'
  precedent for `LoadData` / `SaveData` (private functions over
  helper classes).
- Makes the protocol unit-testable inside the same test file as
  `LoadImage`.

### Q-IMG-2: How does `CellposeSegment.setup()` handle CPU-only machines?

The user has GPU hardware (5090) but explicitly chose to ship 0.1.0
with CPU as the default per master plan §1 memo (`GPU available but
START WITH CPU per user`).

**Decision**:

- `CellposeSegment.config_schema` declares `use_gpu: bool = False`.
- `setup()` instantiates `cellpose.models.Cellpose(model_type=...,
  gpu=use_gpu)` where `use_gpu` is read from `config["use_gpu"]`.
- If `use_gpu=True` and no CUDA device is available, cellpose will
  fall back to CPU automatically and emit its own warning. The block
  does not pre-check; the warning surfaces in the worker stderr.
- If the cellpose model file is not present locally, `cellpose`
  downloads it on first call. The block does not pre-fetch.
- `teardown()` calls `torch.cuda.empty_cache()` only when
  `use_gpu=True` AND `torch` is importable AND
  `torch.cuda.is_available()`. This is wrapped in a single
  `try` / `except` so test environments without `torch` work.

### Q-IMG-3: What happens to metadata on image-transforming blocks like Rotate / Flip / Crop / Resize?

ADR-027 D5 says `framework` is derived, `meta` is shared by reference,
`user` is shallow-copied. But shape-changing transforms (Crop, Resize,
Pad) and axis-permuting transforms (Rotate at non-90° angles) violate
the implicit "the meta is still physically valid" assumption: a Resize
that halves the spatial dimensions doubles the effective `pixel_size`.

**Decision** (per master plan §2.4 implicit invariant):

- **Rotate**: shape is preserved (or padded to fit). `pixel_size` is
  unchanged. `meta` is shared by reference.
- **Flip**: shape and `pixel_size` are unchanged. `meta` is shared by
  reference.
- **Crop**: shape changes; `pixel_size` is unchanged. `meta` is shared
  by reference. (Cropping does not change pixel scale.)
- **Pad**: shape changes; `pixel_size` is unchanged. `meta` is shared
  by reference.
- **Resize**: shape changes; `pixel_size` MUST be updated to reflect
  the new physical scale. The block computes
  `new_pixel_size = old_pixel_size * (old_shape / new_shape)` along
  each spatial axis and emits a new `Image` via
  `image.with_meta(pixel_size=new_pq)`. If the source has no
  `pixel_size`, the output has no `pixel_size` and a debug log notes
  it.
- **AxisSplit / AxisMerge**: changes the `axes` list; preserves
  `pixel_size`. Channel-related fields (`channels`, `wavelengths_nm`)
  are PARTIALLY propagated when splitting on `c` or `lambda` — each
  output gets the channel info for its single channel index. AxisMerge
  re-assembles the channel info from the input collection.
- **AxisProjection**: drops one axis. Channel-related fields are set
  to `None` if the projected axis is `c` or `lambda` (collapsed
  channels are no longer separable).

### Q-IMG-4: How does `AxisSplit` name the resulting Collection items?

When AxisSplit splits an `Image` along (say) axis `c` with 4 channels,
the resulting `Collection[Image]` has 4 items. Their `meta.source_file`
must be unique to enable downstream `SaveImage` to write distinct
files.

**Decision**:

- AxisSplit appends `__<axis>=<index>` to the source's
  `meta.source_file` for each split item. Example: source
  `K562_L_2845.tif` split along `c` produces items with
  `source_file = "K562_L_2845__c=0.tif"`,
  `source_file = "K562_L_2845__c=1.tif"`, etc.
- If the source has no `meta.source_file`, the block uses
  `f"axis_split__{axis}={index}"` as the synthetic name.
- The Collection's `name` (if applicable) is derived from the
  source's display name as `f"{source_name}__split_{axis}"`.

### Q-IMG-5: How does `ImageCalculator` with 2 input ports ship in 0.1.0 when full variadic needs ADR-029?

ADR-029 is preliminary and ships with NotImplementedError placeholders
per master plan §2.3. `ImageCalculator` cannot wait for it.

**Decision**:

- 0.1.0 ships `ImageCalculator` with **fixed two input ports** named
  `a` and `b`. Both accept `Image`. Both are required.
- The expression mode accepts only the variables `a` and `b` (plus
  literal numerics, parentheses, and the four arithmetic operators).
  An expression referencing `c` or `d` raises `ValueError` at runtime
  via the AST whitelist validator.
- The fixed-operation mode (`add` / `subtract` / `multiply` / `divide`)
  hard-codes `a OP b`.
- A docstring note and a `# TODO(ADR-029)` comment in the source mark
  the variadic upgrade path. When ADR-029 lands, `ImageCalculator`
  becomes the first consumer of the variadic mechanism.

### Q-IMG-6: Does `Mask` enforce `dtype=bool` at construction time?

The `Mask` class is documented as "binary mask, dtype=bool". Strict
enforcement vs. permissive coercion is a design choice.

**Decision**: **strict enforcement** via the `_validate_extra` hook
(called after `_validate_axes` in the `Image.__init__` path). If the
dtype is not `bool`, `Mask.__init__` raises
`ValueError("Mask requires dtype=bool, got {dtype}")`. Block authors
that produce a Mask must explicitly cast their output. The
`Threshold` block, for example, ends with `result.astype(bool)`
before constructing the Mask.

**Rationale**: silent coercion masks (pun intended) bugs where a
threshold returns a float array instead of bool. Strict validation
catches the bug at the producing block, not at the consuming block.

### Q-IMG-7: Does `Label` (CompositeData) require at least one of raster / polygons to be non-None?

`Label.expected_slots = {"raster": Array, "polygons": DataFrame}`. The
master plan says either slot can exist independently.

**Decision**: **at least one must be non-None**. `Label.__init__`
calls `super().__init__(...)` and then runs a `_validate_label_slots`
hook that raises `ValueError("Label requires at least one of raster
or polygons to be non-None")` if both are missing. The slots are
otherwise independent.

**Rationale**: a Label with no data is meaningless. Catching it at
construction prevents silent garbage propagation through downstream
blocks.

### Q-IMG-8: How does `LoadImage` handle unknown file extensions?

OptEasy's loader fell back to a generic Pillow read for unknown
extensions. ADR-028 §D11 makes the explicit dispatch list authoritative.

**Decision**: `LoadImage` raises `ValueError(f"Unsupported image
format: {ext}. Supported: {sorted(_SUPPORTED_EXTS)}")` for any
extension not in the explicit list. There is NO fallback to
`LoadArtifact` and NO generic Pillow path. Users with unsupported
formats can either install the corresponding optional extra (`czi` /
`nd2` / `lif`) or use the core `LoadData(core_type='Artifact')` block
to read the file as an opaque blob.

The supported list for 0.1.0:

- Always: `.tif`, `.tiff`, `.png`, `.jpg`, `.jpeg`, `.npy`, `.zarr`
- With `[czi]`: `.czi`
- With `[nd2]`: `.nd2`
- With `[lif]`: `.lif`

OME-TIFF files are detected by inspecting the TIFF metadata for an
`OME` XML namespace inside the `ImageDescription` tag and dispatched
to the OME-TIFF reader.

### Q-IMG-9: When should a block use `iterate_over_axes` vs. direct indexing?

A 2D algorithm (e.g. `skimage.filters.gaussian`) applied to a 5D
`(t, z, c, y, x)` image needs to loop over `(t, z, c)` and apply the
algorithm to each `(y, x)` slice. There are three ways to do it:

1. Manual nested loops with explicit axis bookkeeping.
2. `numpy.apply_over_axes`.
3. `scieasy.utils.axis_iter.iterate_over_axes(source, {"y", "x"}, fn)`.

**Decision**: blocks that have a 2D core algorithm and accept N-D
input MUST use `iterate_over_axes` from `scieasy.utils.axis_iter`. The
utility:

- Handles arbitrary axis orderings.
- Handles 2D-through-6D inputs uniformly.
- Propagates metadata per ADR-027 D5.
- Returns a typed instance of `type(source)` (so a 5D `Image` input
  produces a 5D `Image` output).
- Stacks results back into the original shape so axes and shape are
  preserved.

Blocks whose core algorithm is intrinsically N-D (e.g. an FFT lowpass
that operates on any spatial dimensionality, or a 3D morphology
operation) should call the algorithm directly without
`iterate_over_axes`. The choice is documented in each block's
implementation details below.

### Q-IMG-10: How does `LoadImage` decide between eager and lazy loading?

Master plan locked: "large images use lazy `storage_ref`".

**Decision**: the threshold is **128 MiB total file size**. Files
below the threshold are read eagerly into memory and stashed on the
returned `Image` via the `_data` attribute (the same path
`Array.sel()` already uses for in-memory backed data per the
T-006 implementation). Files at or above the threshold are loaded by
constructing a `ZarrStorageReference` (or the format-appropriate
`StorageReference` subclass) and the returned `Image` carries
`storage_ref=ref` with `_data` unset. The materialisation happens
later via `to_memory()` or `view()` per ADR-027 D4 Level 1 laziness.

The threshold is a constant `_LAZY_THRESHOLD_BYTES = 128 * 1024 * 1024`
at module level inside `load_image.py`. It is NOT user-configurable
in 0.1.0; an issue can be filed in Phase 12 if users complain.

### Q-IMG-11: How does `SaveImage` handle a Collection of length 1 vs N?

The master plan locked: "len==1 → single file, len>1 → directory +
indexed names". Edge cases:

- The output path is a directory but the collection is length 1.
- The output path is a file but the collection is length > 1.
- The output path does not exist yet.

**Decision**:

- Length 1 + path looks like a file (extension matches a supported
  format) → write to that file.
- Length 1 + path is an existing directory or has no extension →
  treat as directory; write to `{path}/image_000.{ext}` where `ext`
  is taken from `config["format"]` (default `.tif`).
- Length N + path looks like a file → raise `ValueError("SaveImage
  received Collection of length N=... but path={path} appears to be a
  single file. Pass a directory path or set format=...")`.
- Length N + path is or will be a directory → create the directory if
  missing; write `image_000.{ext}`, `image_001.{ext}`, ... for N
  items. If items have `meta.source_file` set, use the basename of
  that field instead of the indexed name (so a Collection that came
  from `LoadImage` round-trips with original filenames).

### Q-IMG-12: How does the `RegionProps` block emit one DataFrame for a Collection of N images?

`RegionProps` takes `labels: Label` (or `Collection[Label]`) and
optional `intensity_image: Image` (or `Collection[Image]`).

**Decision**:

- Single `Label` input → single `DataFrame` output, one row per
  detected region.
- `Collection[Label]` input → single `DataFrame` output with an
  additional `image_index` column identifying which item each row
  came from. The block runs `skimage.measure.regionprops_table` per
  item and concatenates with `image_index` prepended. This avoids
  forcing the user to chain a downstream concat block.
- If `intensity_image` is also a Collection, lengths must match;
  otherwise raise `ValueError`.

---

## 9. Per-ticket sections

Each ticket below uses the same 12-subsection structure as the Phase
10 standards doc:

a. Ticket ID and name
b. Source ADR sections
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

The package layout referenced throughout:

```
packages/scieasy-blocks-imaging/
├── pyproject.toml
├── README.md
└── src/scieasy_blocks_imaging/
    ├── __init__.py        (exports get_blocks(), get_types())
    ├── types.py           (Image, Mask, Label, Transform)
    ├── io/                (load_image.py, save_image.py)
    ├── preprocessing/     (denoise/background/normalize/flatfield/
    │                       geometry/convert_dtype/axis_split_merge/
    │                       deconvolve)
    ├── morphology/        (ops/edges/ridges/sharpen/fft)
    ├── segmentation/      (threshold/watershed/cellpose_segment/blob/
    │                       connected_components/cleanup)
    ├── tracking/          (track_objects placeholder)
    ├── measurement/       (region_props/pairwise_distance/colocalization)
    ├── registration/      (compute_registration/apply_transform/
    │                       register_series)
    ├── axis/              (projection/select_slice)
    ├── math/              (scalar_ops/image_calculator)
    ├── visualization/     (pseudo_color/overlay/montage/movie/histogram)
    └── interactive/       (fiji_block/napari_block/cellprofiler_block/
                            qupath_block)
```


---

### T-IMG-001 — Types module (Image / Mask / Label / Transform)

**Status**: Implemented in PR #365. `Image`, `Mask`, `Label`, and
`Transform` now enforce the typed metadata and validation contract on
`main` (`PhysicalQuantity`, `ChannelInfo`, label-slot presence, and
transform-matrix shape), with worker reconstruction coverage in
`packages/scieasy-blocks-imaging/tests/test_types.py`. The same PR also
aligns `T-IMG-008` / `T-IMG-010` compatibility tests with the typed
metadata contract so downstream imaging validation stays green.

**a. Ticket ID and name**: T-IMG-001 — `scieasy_blocks_imaging.types` module.

**b. Source ADR sections**:

- ADR-027 D1 (instance-level axes on Array subclasses).
- ADR-027 D2 (subclassing pattern; Image / Mask / Label / Transform are
  the canonical plugin examples).
- ADR-027 D5 (per-subclass `Meta` Pydantic class).
- ADR-027 Addendum 1 §3 (Meta JSON-round-trip constraints: frozen,
  no PrivateAttr, JSON-serialisable).
- ADR-028 §D5 (plugin types register via `scieasy.types`
  entry-point).

**c. Files to be created**:

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/types.py`

**d. Files to be modified**:

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`
  (add `get_types()` returning the four classes; the block-shipping
  half is filled by subsequent tickets).

**e. New tests**:

- `packages/scieasy-blocks-imaging/tests/test_types.py` (new file)
  containing:
  - `test_image_required_axes_yx`
  - `test_image_allowed_axes_full_alphabet`
  - `test_image_2d_construction`
  - `test_image_3d_zyx_construction`
  - `test_image_5d_tzcyx_construction`
  - `test_image_6d_tzclambdayx_construction`
  - `test_image_meta_pixel_size_pq_round_trip`
  - `test_image_meta_channels_list_channel_info`
  - `test_image_meta_json_round_trip`
  - `test_mask_dtype_bool_required`
  - `test_mask_dtype_float_raises_value_error`
  - `test_mask_inherits_image_axes`
  - `test_label_with_raster_only`
  - `test_label_with_polygons_only`
  - `test_label_with_both_slots`
  - `test_label_neither_slot_raises_value_error`
  - `test_label_meta_round_trip`
  - `test_transform_2d_affine_shape`
  - `test_transform_3d_affine_shape`
  - `test_transform_meta_transform_type_required`
  - `test_get_types_returns_four_classes`
  - `test_image_serialise_reconstruct_round_trip` (worker subprocess
    smoke test using `_serialise_one` / `_reconstruct_one`)

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/types.py

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from scieasy.core.meta import ChannelInfo
from scieasy.core.types.array import Array
from scieasy.core.types.composite import CompositeData
from scieasy.core.types.dataframe import DataFrame
from scieasy.core.units import PhysicalQuantity


class Image(Array):
    """General-purpose microscopy image, 2D to 6D.

    The 6D axis alphabet for scientific imaging is::

        {"t", "z", "c", "lambda", "y", "x"}

    where ``t`` is time, ``z`` is depth, ``c`` is discrete channel,
    ``lambda`` is continuous spectral, ``y`` and ``x`` are the spatial
    axes. ``c`` and ``lambda`` are distinct axes and may coexist.

    Replaces OptEasy's per-modality subclasses (``FluorImage``,
    ``BrightfieldImage``, ``HyperspectralImage``) with a single class.
    Different modalities are distinguished by axis configuration and
    the Meta fields, not by subclassing.
    """

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset(
        {"t", "z", "c", "lambda", "y", "x"}
    )
    canonical_order: ClassVar[tuple[str, ...]] = (
        "t", "z", "c", "lambda", "y", "x",
    )

    class Meta(BaseModel):
        """Per-instance imaging metadata.

        ADR-027 Addendum 1 §3: frozen, no PrivateAttr,
        JSON-round-trippable through Pydantic v2.
        """
        model_config = ConfigDict(frozen=True)
        pixel_size: PhysicalQuantity | None = None
        z_spacing: PhysicalQuantity | None = None
        time_interval: PhysicalQuantity | None = None
        channels: list[ChannelInfo] | None = None
        wavelengths_nm: list[float] | None = None
        objective: str | None = None
        acquisition_date: datetime | None = None
        source_file: str | None = None
        instrument: str | None = None


class Mask(Image):
    """Binary mask. Enforces dtype=bool at construction (Q-IMG-6)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._validate_mask_dtype()

    def _validate_mask_dtype(self) -> None:
        import numpy as np
        if self.dtype is None:
            return
        if np.dtype(self.dtype) != np.dtype(bool):
            raise ValueError(f"Mask requires dtype=bool, got {self.dtype}")


class Label(CompositeData):
    """Label image with raster and/or polygon representation.

    Per Q-Image-1 = B in master plan: composite with two slots:
    - raster: integer-dtype Array
    - polygons: optional DataFrame for vector representation

    At least one slot must be non-None (Q-IMG-7).
    """

    expected_slots: ClassVar[dict[str, type]] = {
        "raster": Array,
        "polygons": DataFrame,
    }

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        source_file: str | None = None
        n_objects: int | None = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._validate_label_slots()

    def _validate_label_slots(self) -> None:
        raster = self.slots.get("raster")
        polygons = self.slots.get("polygons")
        if raster is None and polygons is None:
            raise ValueError(
                "Label requires at least one of raster or polygons "
                "to be non-None"
            )


class Transform(Array):
    """Affine transform matrix.

    Per Q-Image-2 = C in master plan: Array subclass with
    axes=["row","col"], shape (2,3) for 2D affine or (3,3) for 3D.
    """

    required_axes: ClassVar[frozenset[str]] = frozenset({"row", "col"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"row", "col"})
    canonical_order: ClassVar[tuple[str, ...]] = ("row", "col")

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        transform_type: str  # "affine" | "rigid" | "similarity"
        reference_shape: tuple[int, ...] | None = None
```

The `__init__.py` `get_types()` function:

```python
# packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py

from scieasy_blocks_imaging.types import Image, Label, Mask, Transform

def get_types() -> list[type]:
    return [Image, Mask, Label, Transform]

def get_blocks() -> list[type]:
    return []  # T-IMG-002 onwards append here

__all__ = ["Image", "Label", "Mask", "Transform", "get_blocks", "get_types"]
```

**h. Acceptance criteria**:

- [ ] `Image` is `Array` subclass with `required_axes={"y","x"}`,
      `allowed_axes={"t","z","c","lambda","y","x"}`.
- [ ] `Image.Meta` is frozen Pydantic `BaseModel` with the nine
      master-plan fields.
- [ ] `Image.Meta(pixel_size=PhysicalQuantity(0.108,"um"))` round-trips
      through `model_dump_json()` / `model_validate_json()`.
- [ ] `Image(axes=["y","x"])` constructs a 2D image.
- [ ] `Image(axes=["t","z","c","lambda","y","x"])` constructs a 6D
      image.
- [ ] `Image(axes=["q","y","x"])` raises `ValueError`.
- [ ] `Image(axes=["y"])` raises `ValueError`.
- [ ] `Mask` inherits from `Image` and `required_axes`.
- [ ] `Mask(axes=["y","x"], dtype=bool)` constructs.
- [ ] `Mask(axes=["y","x"], dtype="float32")` raises `ValueError`.
- [ ] `Label.expected_slots == {"raster": Array, "polygons": DataFrame}`.
- [ ] `Label(slots={"raster": Array(axes=["y","x"], dtype="int32")})`
      constructs.
- [ ] `Label(slots={})` raises `ValueError`.
- [ ] `Transform.required_axes == {"row","col"}`.
- [ ] `Transform(axes=["row","col"], shape=(2,3),
      meta=Transform.Meta(transform_type="affine"))` constructs.
- [ ] `get_types()` returns `[Image, Mask, Label, Transform]`.
- [ ] An `Image` instance round-trips through worker `_serialise_one`
      / `_reconstruct_one` with `type(out) is Image`,
      `out.axes == src.axes`, `out.meta == src.meta`.

**i. Out of scope**:

- No `LoadImage`/`SaveImage` (T-IMG-002/T-IMG-003).
- No domain subclasses like `FluorImage` or `SRSImage`.
- No ROI/polygon import logic.

**j. Dependencies on other tickets**: T-IMG-038a (skeleton) must
exist.

**k. Estimated diff size**: ~150 src + ~250 tests = ~400 lines.
**Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-001 Image / Mask / Label / Transform types per ADR-027 D1+D2+D5`

---

### T-IMG-002 — LoadImage

**Status**: Partially implemented (#354, pilot scope: TIFF + Zarr).
Broader format support (PNG/JPG/NPY/OME-TIFF/CZI/ND2/LIF, lazy Zarr via
`storage_ref`, directory/glob enumeration) remains deferred and is
still tracked in this ticket.

**a. Ticket ID and name**: T-IMG-002 — `LoadImage` IO block.

**b. Source ADR sections**:

- ADR-028 §D3' (plugin IO subclasses concrete `IOBlock`).
- ADR-028 §D5 (TIFF JSON-in-ImageDescription protocol moves verbatim
  from OptEasy `tiff_adapter.py`).
- ADR-028 Addendum 1 §D6' (plugin IO blocks stay STATIC).
- ADR-027 D1 (axes propagation).
- Q-IMG-1, Q-IMG-8, Q-IMG-10.

**c. Files to be created**:

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/load_image.py`

**d. Files to be modified**:

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:

- `packages/scieasy-blocks-imaging/tests/test_io/test_load_image.py`
  - `test_load_single_tif_file_returns_collection_length_one`
  - `test_load_directory_returns_collection_length_n`
  - `test_load_glob_pattern_returns_collection`
  - `test_load_tif_extracts_axes_from_shape`
  - `test_load_tif_with_imagedescription_metadata_decoded`
  - `test_load_tif_without_imagedescription_returns_default_meta`
  - `test_load_png_jpg_returns_2d_image`
  - `test_load_npy_returns_array_with_user_axes`
  - `test_load_zarr_returns_lazy_image_with_storage_ref`
  - `test_load_large_tif_uses_lazy_storage_ref`
  - `test_load_small_tif_loads_eagerly`
  - `test_load_unsupported_extension_raises_value_error`
  - `test_load_nonexistent_path_raises_file_not_found`
  - `test_load_ome_tiff_detected_via_image_description`
  - `test_load_czi_skipped_when_extra_not_installed`
  - `test_load_propagates_source_file_into_meta`
  - `test_load_image_block_round_trips_through_worker`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/load_image.py

from __future__ import annotations
import json, logging
from pathlib import Path
from typing import Any, ClassVar

from scieasy.blocks.base.ports import OutputPort
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.meta import FrameworkMeta
from scieasy.core.types.collection import Collection

from scieasy_blocks_imaging.types import Image

logger = logging.getLogger(__name__)

_SUPPORTED_EXTS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".npy", ".zarr"}
_OPTIONAL_EXTS = {".czi": "czi", ".nd2": "nd2", ".lif": "lif"}
_LAZY_THRESHOLD_BYTES = 128 * 1024 * 1024
_TIFF_METADATA_PREFIX = "SCIEASY:"


class LoadImage(IOBlock):
    """Unified image loader. Returns Collection[Image]; length 1 for
    single file, length N for directory or glob.

    Per ADR-028 Addendum 1 §D6', this block is STATIC: fixed
    output_ports, no dynamic_ports. The output type is always Image.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "imaging.load_image"
    name: ClassVar[str] = "Load Image"
    category: ClassVar[str] = "io"

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Collection[Image]]),
    ]

    config_schema = {
        "properties": {
            "path": {"type": "string", "ui_priority": 0},
            "recursive": {"type": "boolean", "default": False, "ui_priority": 1},
        },
        "required": ["path"],
    }

    def load(self, config: dict[str, Any]) -> Collection[Image]:
        path = Path(config["path"])
        recursive = bool(config.get("recursive", False))
        files = self._enumerate_files(path, recursive=recursive)
        if not files:
            raise FileNotFoundError(f"LoadImage: no files found at {path}")
        return Collection([self._load_one(f) for f in files])

    def _enumerate_files(self, path: Path, *, recursive: bool) -> list[Path]:
        if path.is_file():
            return [path]
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            return sorted(p for p in path.glob(pattern)
                          if p.is_file() and self._is_supported(p))
        # glob pattern
        return sorted(path.parent.glob(path.name))

    def _is_supported(self, p: Path) -> bool:
        ext = p.suffix.lower()
        return ext in _SUPPORTED_EXTS or ext in _OPTIONAL_EXTS

    def _load_one(self, path: Path) -> Image:
        ext = path.suffix.lower()
        if ext in {".tif", ".tiff"}:
            return _load_tif(path)
        if ext in {".png", ".jpg", ".jpeg"}:
            return _load_pillow(path)
        if ext == ".npy":
            return _load_npy(path)
        if ext == ".zarr":
            return _load_zarr(path)
        if ext in _OPTIONAL_EXTS:
            return _load_optional(path, _OPTIONAL_EXTS[ext])
        raise ValueError(
            f"Unsupported image format: {ext}. "
            f"Supported: {sorted(_SUPPORTED_EXTS | _OPTIONAL_EXTS.keys())}"
        )


# -- private dispatch helpers (Q-IMG-1) ----------------------------------

def _decode_metadata_json(description: str | None) -> dict | None:
    if not description or not description.startswith(_TIFF_METADATA_PREFIX):
        return None
    try:
        return json.loads(description[len(_TIFF_METADATA_PREFIX):])
    except json.JSONDecodeError:
        logger.warning("Malformed SCIEASY metadata JSON")
        return None


def _load_tif(path: Path) -> Image:
    import tifffile
    size = path.stat().st_size
    with tifffile.TiffFile(str(path)) as tf:
        page0 = tf.pages[0]
        description = getattr(page0, "description", None)
        meta_dict = _decode_metadata_json(description) or {}
        shape = tf.series[0].shape
        dtype = tf.series[0].dtype
        axes = _normalise_axes(tf.series[0].axes)
        if size < _LAZY_THRESHOLD_BYTES:
            data = tf.asarray()
            img = Image(
                axes=axes, shape=shape, dtype=dtype,
                meta=Image.Meta(source_file=str(path),
                                **_meta_dict_to_kwargs(meta_dict)),
                framework=FrameworkMeta(source=str(path)),
            )
            img._data = data
            return img
        from scieasy.core.storage.zarr_backend import ZarrStorageReference
        ref = ZarrStorageReference.from_tiff(path)
        return Image(
            axes=axes, shape=shape, dtype=dtype, storage_ref=ref,
            meta=Image.Meta(source_file=str(path),
                            **_meta_dict_to_kwargs(meta_dict)),
            framework=FrameworkMeta(source=str(path)),
        )


def _normalise_axes(tf_axes: str) -> list[str]:
    mapping = {"T": "t", "Z": "z", "C": "c", "Y": "y", "X": "x",
               "S": "c", "Q": "lambda"}
    return [mapping[ch] for ch in tf_axes if ch in mapping]


def _meta_dict_to_kwargs(d: dict) -> dict:
    allowed = {"pixel_size", "z_spacing", "time_interval", "channels",
               "wavelengths_nm", "objective", "acquisition_date", "instrument"}
    return {k: v for k, v in d.items() if k in allowed}


def _load_pillow(path: Path) -> Image:
    from PIL import Image as PILImage
    import numpy as np
    arr = np.array(PILImage.open(path))
    axes = ["y", "x"] if arr.ndim == 2 else ["y", "x", "c"]
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype,
                meta=Image.Meta(source_file=str(path)),
                framework=FrameworkMeta(source=str(path)))
    img._data = arr
    return img


def _load_npy(path: Path) -> Image:
    import numpy as np
    arr = np.load(path)
    axes = (["y", "x"] if arr.ndim == 2
            else ["c", "y", "x"] if arr.ndim == 3
            else ["t", "c", "y", "x"] if arr.ndim == 4
            else ["t", "z", "c", "y", "x"])
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype,
                meta=Image.Meta(source_file=str(path)),
                framework=FrameworkMeta(source=str(path)))
    img._data = arr
    return img


def _load_zarr(path: Path) -> Image:
    from scieasy.core.storage.zarr_backend import ZarrStorageReference
    ref = ZarrStorageReference.from_path(path)
    return Image(axes=ref.axes or ["y", "x"], shape=ref.shape,
                 dtype=ref.dtype, storage_ref=ref,
                 meta=Image.Meta(source_file=str(path)),
                 framework=FrameworkMeta(source=str(path)))


def _load_optional(path: Path, extra: str) -> Image:
    if extra == "czi":
        try:
            from aicsimageio import AICSImage  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Loading .czi files requires the [czi] extra: "
                "pip install scieasy-blocks-imaging[czi]"
            ) from exc
    elif extra == "nd2":
        try:
            import nd2reader  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Loading .nd2 files requires the [nd2] extra: "
                "pip install scieasy-blocks-imaging[nd2]"
            ) from exc
    elif extra == "lif":
        try:
            import readlif  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Loading .lif files requires the [lif] extra: "
                "pip install scieasy-blocks-imaging[lif]"
            ) from exc
    raise NotImplementedError(f"Optional format {extra} loader not yet implemented")
```

**h. Acceptance criteria**:

- [ ] `LoadImage` is concrete `IOBlock` with `direction="input"`,
      `type_name="imaging.load_image"`, `category="io"`.
- [ ] `output_ports` is single `OutputPort("images",
      [Collection[Image]])` (STATIC, no `dynamic_ports`).
- [ ] `config_schema` declares `path` (required) and `recursive`
      (default False).
- [ ] Loading single `.tif` returns `Collection[Image]` length 1.
- [ ] Loading directory returns `Collection[Image]` length N.
- [ ] Loading glob (`*.tif`) returns matching files.
- [ ] TIFFs < 128 MiB load eagerly into `image._data`.
- [ ] TIFFs ≥ 128 MiB load lazily with `storage_ref` set.
- [ ] TIFF `ImageDescription` `SCIEASY:{...}` decoded into `Image.Meta`.
- [ ] OME-TIFF detected via `<OME ` in `ImageDescription`.
- [ ] `.png`/`.jpg` load via Pillow.
- [ ] `.npy` infers axes from `ndim`.
- [ ] `.zarr` loads lazily.
- [ ] Unknown extension raises `ValueError("Unsupported image format:
      ...")` with supported list.
- [ ] Nonexistent path raises `FileNotFoundError`.
- [ ] `meta.source_file` populated.
- [ ] `framework.source` set to file path.
- [ ] `.czi`/`.nd2`/`.lif` raise friendly `ImportError` when extra
      missing.
- [ ] Loaded image survives `_serialise_one`/`_reconstruct_one`
      round-trip.

**i. Out of scope**:

- No SaveImage (T-IMG-003).
- No CSV/Excel side-loading.
- No ROI/Fiji-format import.
- No streaming reads.

**j. Dependencies on other tickets**:

- T-IMG-001 (types).
- T-IMG-038a (skeleton).

**k. Estimated diff size**: ~350 src + ~400 tests = ~750 lines.
**Large**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-002 LoadImage with TIFF/PNG/JPG/NPY/Zarr/optional CZI/ND2/LIF`

---

### T-IMG-003 — SaveImage

**Status**: Partially implemented (#354, pilot scope: TIFF + Zarr for
length-1 inputs, format auto-detect + explicit override). Indexed
directory writes, multi-page TIFFs, lazy materialisation semantics,
and PNG/JPG/NPY backends remain deferred.

**a. Ticket ID and name**: T-IMG-003 — `SaveImage` IO block.

**b. Source ADR sections**:

- ADR-028 §D3' (plugin IO subclasses).
- ADR-028 §D7 (`direction="output"`).
- ADR-028 §D5 (round-trip via SCIEASY: JSON in TIFF).
- Q-IMG-1, Q-IMG-11.

**c. Files to be created**:

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/save_image.py`

**d. Files to be modified**:

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:

- `packages/scieasy-blocks-imaging/tests/test_io/test_save_image.py`
  - `test_save_single_image_to_file`
  - `test_save_collection_to_directory_indexed`
  - `test_save_collection_uses_meta_source_file_basename_when_present`
  - `test_save_collection_to_file_path_raises_value_error`
  - `test_save_creates_parent_directory_if_missing`
  - `test_save_writes_meta_into_tiff_image_description_round_trip`
  - `test_save_with_format_param_overrides_extension`
  - `test_save_lazy_image_materialises_first`
  - `test_save_dtype_preserved`
  - `test_save_axes_preserved_in_round_trip`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/save_image.py

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, ClassVar

from scieasy.blocks.base.ports import InputPort
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.types.collection import Collection

from scieasy_blocks_imaging.types import Image

_SCIEASY_PREFIX = "SCIEASY:"


class SaveImage(IOBlock):
    """Persist Collection[Image] to disk.

    Length 1 + file path → single file.
    Length 1 + directory → image_000.<ext>.
    Length N + directory → image_000..image_{N-1}.<ext>.
    Length N + file path → ValueError.
    """

    direction: ClassVar[str] = "output"
    type_name: ClassVar[str] = "imaging.save_image"
    name: ClassVar[str] = "Save Image"
    category: ClassVar[str] = "io"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Collection[Image]]),
    ]

    config_schema = {
        "properties": {
            "path": {"type": "string", "ui_priority": 0},
            "format": {
                "type": "string",
                "enum": ["tif", "png", "jpg", "npy", "zarr"],
                "default": "tif", "ui_priority": 1,
            },
        },
        "required": ["path"],
    }

    def save(self, inputs: dict[str, Any], config: dict[str, Any]) -> None:
        col: Collection[Image] = inputs["images"]
        out_path = Path(config["path"])
        fmt = config.get("format", "tif")
        n = len(col)
        if n == 0:
            raise ValueError("SaveImage: empty collection")
        is_file_path = out_path.suffix and out_path.suffix.lstrip(".") in {
            "tif", "tiff", "png", "jpg", "jpeg", "npy", "zarr"
        }
        if n == 1 and is_file_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_one(col[0], out_path,
                           fmt or out_path.suffix.lstrip("."))
            return
        if n > 1 and is_file_path:
            raise ValueError(
                f"SaveImage received Collection of length {n} but path "
                f"{out_path} appears to be a single file. Pass a directory."
            )
        out_path.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(col):
            base = self._derive_filename(img, i, fmt)
            self._save_one(img, out_path / base, fmt)

    def _derive_filename(self, img: Image, idx: int, fmt: str) -> str:
        src = getattr(img.meta, "source_file", None) if img.meta else None
        if src:
            return f"{Path(src).stem}.{fmt}"
        return f"image_{idx:03d}.{fmt}"

    def _save_one(self, img: Image, path: Path, fmt: str) -> None:
        if fmt in {"tif", "tiff"}:
            _save_tif(img, path)
        elif fmt in {"png", "jpg", "jpeg"}:
            _save_pillow(img, path)
        elif fmt == "npy":
            _save_npy(img, path)
        elif fmt == "zarr":
            _save_zarr(img, path)
        else:
            raise ValueError(f"Unsupported save format: {fmt}")


def _encode_metadata_json(img: Image) -> str:
    if img.meta is None:
        return ""
    return _SCIEASY_PREFIX + img.meta.model_dump_json()


def _save_tif(img: Image, path: Path) -> None:
    import tifffile
    data = img.to_memory() if img.storage_ref else img._data
    tifffile.imwrite(str(path), data,
                     description=_encode_metadata_json(img),
                     metadata={"axes": "".join(img.axes).upper()})


def _save_pillow(img: Image, path: Path) -> None:
    from PIL import Image as PILImage
    import numpy as np
    data = img.to_memory() if img.storage_ref else img._data
    PILImage.fromarray(np.asarray(data)).save(path)


def _save_npy(img: Image, path: Path) -> None:
    import numpy as np
    data = img.to_memory() if img.storage_ref else img._data
    np.save(path, data)


def _save_zarr(img: Image, path: Path) -> None:
    from scieasy.core.storage.zarr_backend import ZarrStorageReference
    data = img.to_memory() if img.storage_ref else img._data
    ZarrStorageReference.write_to(path, data, axes=img.axes)
```

**h. Acceptance criteria**:

- [ ] Concrete `IOBlock` with `direction="output"`.
- [ ] `input_ports = [InputPort("images", [Collection[Image]])]`.
- [ ] `config_schema` requires `path`, optional `format` enum.
- [ ] Length-1 + file extension → single file.
- [ ] Length-1 + directory → `image_000.<ext>`.
- [ ] Length-N + directory → indexed files.
- [ ] Length-N + file path → `ValueError`.
- [ ] `meta.source_file` basenames used when present.
- [ ] Parent dirs created.
- [ ] TIFF round-trip preserves axes/shape/dtype/meta.
- [ ] Lazy images materialise via `to_memory()` first.

**i. Out of scope**:

- No multi-page TIFF for time series.
- No image compression options in 0.1.0.

**j. Dependencies on other tickets**:

- T-IMG-001, T-IMG-002.

**k. Estimated diff size**: ~250 src + ~300 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-003 SaveImage with single-file and indexed-directory modes`

---

### T-IMG-004 — Denoise

**Status**: Partially implemented (Sprint C preprocess subset A, pilot
scope: `gaussian` + `median` via scikit-image). `bilateral` / `nlmeans` /
`wavelet` remain in the enum schema but raise `NotImplementedError` and
are deferred to a follow-on subset.

**a. Ticket ID and name**: T-IMG-004 — `Denoise` block.

**b. Source ADR sections**:

- ADR-027 D3 (`iterate_over_axes`).
- ADR-027 D5 (metadata propagation).
- Q-IMG-9.

**c. Files to be created**:

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/denoise.py`

**d. Files to be modified**:

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:

- `packages/scieasy-blocks-imaging/tests/test_preprocessing/test_denoise.py`
  - `test_denoise_gaussian_2d_basic`
  - `test_denoise_gaussian_5d_iterates_over_extra_axes`
  - `test_denoise_median_2d_basic`
  - `test_denoise_bilateral_2d`
  - `test_denoise_nlmeans_2d`
  - `test_denoise_wavelet_2d`
  - `test_denoise_invalid_method_raises_value_error`
  - `test_denoise_negative_sigma_raises_value_error`
  - `test_denoise_preserves_axes_and_shape`
  - `test_denoise_preserves_meta_by_reference`
  - `test_denoise_framework_derived_from_parent`
  - `test_denoise_collection_input_iterates`
  - `test_denoise_3d_zyx_iterates_over_z`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes

from scieasy_blocks_imaging.types import Image


class Denoise(ProcessBlock):
    """Denoise images using one of several 2D algorithms.

    Operates on 2D (y, x) slices. For N-D inputs, uses
    iterate_over_axes to broadcast across (t, z, c, lambda).
    """

    type_name: ClassVar[str] = "imaging.denoise"
    name: ClassVar[str] = "Denoise"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "denoise"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image],
                  constraint=has_axes("y", "x"),
                  constraint_description="image must carry (y, x)"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["gaussian", "median", "bilateral",
                                "nlmeans", "wavelet"],
                       "default": "gaussian"},
            "sigma": {"type": "number", "default": 1.0, "minimum": 0.0},
            "radius": {"type": "integer", "default": 3, "minimum": 1},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        method = config["method"]
        sigma = config.get("sigma", 1.0)
        radius = config.get("radius", 3)
        if sigma < 0:
            raise ValueError(f"sigma must be >= 0, got {sigma}")
        fn = _get_denoise_fn(method, sigma=sigma, radius=radius)
        return iterate_over_axes(item, {"y", "x"}, fn)


def _get_denoise_fn(method: str, *, sigma: float, radius: int):
    from skimage.filters import gaussian, median
    from skimage.morphology import disk
    from skimage.restoration import (denoise_bilateral, denoise_nl_means,
                                      denoise_wavelet)
    if method == "gaussian":
        return lambda s, c: gaussian(s, sigma=sigma, preserve_range=True)
    if method == "median":
        return lambda s, c: median(s, disk(radius))
    if method == "bilateral":
        return lambda s, c: denoise_bilateral(s, sigma_spatial=sigma)
    if method == "nlmeans":
        return lambda s, c: denoise_nl_means(s, h=sigma)
    if method == "wavelet":
        return lambda s, c: denoise_wavelet(s, sigma=sigma)
    raise ValueError(f"Unknown denoise method: {method}")
```

**h. Acceptance criteria**:

- [ ] `Denoise` is `ProcessBlock` subclass with required ClassVars.
- [ ] `input_ports` declares `Image` with `has_axes("y","x")`.
- [ ] `output_ports` declares `Image`.
- [ ] `config_schema` declares `method` enum + `sigma`/`radius`.
- [ ] `gaussian` on 2D returns smoothed 2D with same shape/axes/dtype.
- [ ] `gaussian` on 5D `(t,z,c,y,x)` broadcasts via
      `iterate_over_axes`, returns 5D same shape.
- [ ] `median`/`bilateral`/`nlmeans`/`wavelet` work on 2D inputs.
- [ ] Invalid method → `ValueError`.
- [ ] Negative sigma → `ValueError`.
- [ ] Output `framework` derived from input.
- [ ] Output `meta` shared by reference.
- [ ] Output `user` shallow-copied.

**i. Out of scope**:

- No 3D Gaussian.
- No GPU variant.
- No automatic sigma estimation.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~150 src + ~250 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-004 Denoise block (gaussian/median/bilateral/nlmeans/wavelet)`


---

### T-IMG-005 — BackgroundSubtract

**Status**: Implemented (Sprint C preprocess subset A). All four
methods (`rollingball` / `tophat` / `polynomial` / `constant`) are
functional; N-D inputs broadcast via `iterate_over_axes`.

**a. Ticket ID and name**: T-IMG-005 — `BackgroundSubtract` block.

**b. Source ADR sections**: ADR-027 D3, D5.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/background.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `packages/scieasy-blocks-imaging/tests/test_preprocessing/test_background.py`
  - `test_background_rollingball_2d_basic`
  - `test_background_tophat_2d_basic`
  - `test_background_polynomial_2d_basic`
  - `test_background_constant_subtracts_value`
  - `test_background_5d_iterates_over_extra_axes`
  - `test_background_invalid_method_raises_value_error`
  - `test_background_negative_radius_raises_value_error`
  - `test_background_preserves_meta_and_axes`
  - `test_background_constant_clipped_to_zero_floor`
  - `test_background_polynomial_degree_param_respected`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes

from scieasy_blocks_imaging.types import Image


class BackgroundSubtract(ProcessBlock):
    """Subtract estimated background from each (y, x) slice.

    Methods:
    - rollingball: skimage.restoration.rolling_ball
    - tophat: skimage.morphology.white_tophat
    - polynomial: fit a degree-N polynomial to the image and subtract
    - constant: subtract a fixed scalar value
    """

    type_name: ClassVar[str] = "imaging.background_subtract"
    name: ClassVar[str] = "Background Subtract"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "background_subtract"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image],
                  constraint=has_axes("y", "x")),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["rollingball", "tophat", "polynomial", "constant"],
                       "default": "rollingball"},
            "radius": {"type": "integer", "default": 25, "minimum": 1},
            "degree": {"type": "integer", "default": 2, "minimum": 0},
            "value": {"type": "number", "default": 0.0},
            "clip_to_zero": {"type": "boolean", "default": True},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        method = config["method"]
        radius = config.get("radius", 25)
        if radius < 1:
            raise ValueError(f"radius must be >= 1, got {radius}")
        fn = _get_background_fn(method, config)
        return iterate_over_axes(item, {"y", "x"}, fn)


def _get_background_fn(method: str, config: dict):
    if method == "rollingball":
        from skimage.restoration import rolling_ball
        radius = config.get("radius", 25)
        clip = config.get("clip_to_zero", True)
        def fn(slice_2d, coord):
            bg = rolling_ball(slice_2d, radius=radius)
            out = slice_2d - bg
            return np.clip(out, 0, None) if clip else out
        return fn
    if method == "tophat":
        from skimage.morphology import disk, white_tophat
        radius = config.get("radius", 25)
        return lambda s, c: white_tophat(s, disk(radius))
    if method == "polynomial":
        degree = config.get("degree", 2)
        return _polynomial_background_fn(degree, config.get("clip_to_zero", True))
    if method == "constant":
        value = config.get("value", 0.0)
        clip = config.get("clip_to_zero", True)
        def fn(s, c):
            out = s.astype(np.float32) - value
            return np.clip(out, 0, None) if clip else out
        return fn
    raise ValueError(f"Unknown background method: {method}")


def _polynomial_background_fn(degree: int, clip: bool):
    def fn(slice_2d, coord):
        h, w = slice_2d.shape
        yy, xx = np.mgrid[0:h, 0:w]
        # build polynomial features up to total degree
        features = []
        for i in range(degree + 1):
            for j in range(degree + 1 - i):
                features.append((xx ** i * yy ** j).ravel())
        A = np.stack(features, axis=1).astype(np.float64)
        b = slice_2d.ravel().astype(np.float64)
        coeffs, *_ = np.linalg.lstsq(A, b, rcond=None)
        bg = (A @ coeffs).reshape(h, w)
        out = slice_2d - bg
        return np.clip(out, 0, None) if clip else out
    return fn
```

**h. Acceptance criteria**:

- [ ] `BackgroundSubtract` is `ProcessBlock` with required ClassVars.
- [ ] `method` enum: `rollingball`/`tophat`/`polynomial`/`constant`.
- [ ] All four methods work on 2D inputs.
- [ ] 5D inputs broadcast via `iterate_over_axes`.
- [ ] Negative radius → `ValueError`.
- [ ] Invalid method → `ValueError`.
- [ ] `clip_to_zero=True` (default) clamps negative pixels to 0.
- [ ] `polynomial` respects `degree` param.
- [ ] Output meta shared by reference; framework derived; user shallow.

**i. Out of scope**: BaSiC corrections (T-IMG-007), spatial heterogeneity correction beyond polynomial.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~200 src + ~250 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-005 BackgroundSubtract (rollingball/tophat/polynomial/constant)`

---

### T-IMG-006 — Normalize

**Status**: Partially implemented (Sprint C preprocess subset A, pilot
scope: `minmax` / `zscore` / `percentile`). `histogram_match` remains in
the enum but raises `NotImplementedError` pending a second input port
for the reference image.

**a. Ticket ID and name**: T-IMG-006 — `Normalize` block.

**b. Source ADR sections**: ADR-027 D3, D5.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/normalize.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_preprocessing/test_normalize.py`
  - `test_normalize_minmax_2d_to_0_1`
  - `test_normalize_zscore_mean_zero_std_one`
  - `test_normalize_percentile_clips_to_low_high`
  - `test_normalize_histogram_match_to_reference`
  - `test_normalize_5d_iterates_per_slice`
  - `test_normalize_5d_per_image_when_per_slice_false`
  - `test_normalize_invalid_method_raises_value_error`
  - `test_normalize_zero_variance_returns_zero_zscore_safe`
  - `test_normalize_preserves_axes_meta_user`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes

from scieasy_blocks_imaging.types import Image


class Normalize(ProcessBlock):
    """Intensity normalization with several methods."""

    type_name: ClassVar[str] = "imaging.normalize"
    name: ClassVar[str] = "Normalize"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "normalize"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["minmax", "zscore", "percentile",
                                "histogram_match"],
                       "default": "minmax"},
            "low_pct": {"type": "number", "default": 1.0},
            "high_pct": {"type": "number", "default": 99.0},
            "per_slice": {"type": "boolean", "default": True},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        method = config["method"]
        per_slice = config.get("per_slice", True)
        if per_slice and len(item.axes) > 2:
            fn = _get_normalize_fn(method, config)
            return iterate_over_axes(item, {"y", "x"}, fn)
        # whole-image normalization
        data = item.to_memory() if item.storage_ref else item._data
        out = _normalize_array(data, method, config)
        return item.with_meta()  # placeholder; full impl uses _data swap
```

**h. Acceptance criteria**:

- [ ] `Normalize` is `ProcessBlock` with required ClassVars.
- [ ] `method` enum + `low_pct`/`high_pct`/`per_slice`.
- [ ] `minmax` rescales to [0, 1].
- [ ] `zscore` produces mean ~0, std ~1.
- [ ] `percentile` clips outside `[low_pct, high_pct]`.
- [ ] `histogram_match` matches a reference image's histogram.
- [ ] Zero-variance input → safe handling (no NaN propagation).
- [ ] 5D inputs with `per_slice=True` iterate via
      `iterate_over_axes`.
- [ ] Output preserves axes/meta/user.

**i. Out of scope**: Per-channel normalization beyond the `c` axis iteration; CLAHE (use `Sharpen` Phase 12).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~200 src + ~250 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-006 Normalize (minmax/zscore/percentile/histogram_match)`

---

### T-IMG-007 — FlatFieldCorrect

**Status**: Partially implemented (Sprint C preprocess subset A). The
`basic` literal formula is functional with optional dark-frame subtract
and N-D image broadcasting. The `BaSiC` method stays in the enum but
raises `NotImplementedError` pending the BaSiC algorithm integration.

**a. Ticket ID and name**: T-IMG-007 — `FlatFieldCorrect` block.

**b. Source ADR sections**: ADR-027 D2 (multi-input ports), D3, D5.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/flatfield.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_preprocessing/test_flatfield.py`
  - `test_flatfield_basic_correction_no_dark`
  - `test_flatfield_basic_with_dark_frame`
  - `test_flatfield_basic_formula_correctness`
  - `test_flatfield_basic_method_runs`
  - `test_flatfield_5d_iterates_per_slice`
  - `test_flatfield_shape_mismatch_raises_value_error`
  - `test_flatfield_zero_flat_handled`
  - `test_flatfield_preserves_axes_meta`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock

from scieasy_blocks_imaging.types import Image


class FlatFieldCorrect(ProcessBlock):
    """Multi-input flat-field correction.

    Formula: out = (image - dark) / (flat - dark) * mean(flat - dark)
    where dark defaults to zeros if not provided.

    Methods:
    - basic: literal formula above
    - BaSiC: BaSiC algorithm via the basicpy package (optional)
    """

    type_name: ClassVar[str] = "imaging.flatfield_correct"
    name: ClassVar[str] = "Flat Field Correct"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "flatfield_correct"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
        InputPort(name="flat_field", accepted_types=[Image]),
        InputPort(name="dark_frame", accepted_types=[Image], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string", "enum": ["basic", "BaSiC"],
                       "default": "basic"},
        },
    }

    def run(self, inputs, config):
        # Tier 2: explicit run() because we have multiple inputs
        image = inputs["image"]
        flat = inputs["flat_field"]
        dark = inputs.get("dark_frame")
        method = config.get("method", "basic")
        if method == "basic":
            return self._apply_basic(image, flat, dark)
        if method == "BaSiC":
            return self._apply_basic_algorithm(image, flat, dark)
        raise ValueError(f"Unknown flatfield method: {method}")

    def _apply_basic(self, image: Image, flat: Image, dark: Image | None) -> Image:
        # ... validate shapes match in (y, x), apply formula slice-wise
        pass

    def _apply_basic_algorithm(self, image, flat, dark):
        try:
            import basicpy  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "BaSiC method requires basicpy: pip install basicpy"
            ) from exc
        # ... BaSiC pipeline
```

**h. Acceptance criteria**:

- [ ] `FlatFieldCorrect` declares 3 input ports
      (`image`/`flat_field`/`dark_frame`, last optional).
- [ ] `method` enum: `basic`/`BaSiC`.
- [ ] `basic` applies the literal formula correctly on 2D inputs.
- [ ] Optional `dark_frame=None` defaults to zeros.
- [ ] Shape mismatch in `(y, x)` between image and flat raises
      `ValueError`.
- [ ] 5D image broadcasts per `(y, x)` slice.
- [ ] `BaSiC` raises friendly `ImportError` when basicpy missing.
- [ ] Output preserves axes/meta.

**i. Out of scope**: Multi-image flat-field estimation (the basic method requires the user to provide the reference flat field).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~250 src + ~250 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-007 FlatFieldCorrect (basic / BaSiC)`

---

### T-IMG-008 — Geometry bundle (Rotate / Flip / Crop / Pad / Resize)

**a. Ticket ID and name**: T-IMG-008 — Geometry block bundle.

**b. Source ADR sections**: ADR-027 D5 (Q-IMG-3 metadata propagation under shape change).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/geometry.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_preprocessing/test_geometry.py`
  - `test_rotate_90_degrees_2d`
  - `test_rotate_arbitrary_angle_preserves_pixel_size`
  - `test_rotate_invalid_interpolation_raises`
  - `test_flip_y_axis_2d`
  - `test_flip_x_axis_2d`
  - `test_flip_z_axis_3d`
  - `test_crop_bbox_basic`
  - `test_crop_with_mask_input`
  - `test_crop_invalid_bbox_raises`
  - `test_pad_constant_mode`
  - `test_pad_reflect_mode`
  - `test_pad_edge_mode`
  - `test_resize_target_shape_updates_pixel_size`
  - `test_resize_factor_updates_pixel_size_isotropic`
  - `test_resize_no_pixel_size_propagates_none`
  - `test_geometry_5d_broadcasts`
  - `test_geometry_meta_propagation_per_q_img_3`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.core.units import PhysicalQuantity

from scieasy_blocks_imaging.types import Image, Mask


class Rotate(ProcessBlock):
    type_name: ClassVar[str] = "imaging.rotate"
    name: ClassVar[str] = "Rotate"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "rotate"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "angle": {"type": "number", "default": 90.0},
            "interpolation": {"type": "string",
                              "enum": ["nearest", "bilinear", "bicubic"],
                              "default": "bilinear"},
        },
        "required": ["angle"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        from skimage.transform import rotate
        angle = config["angle"]
        interp = config.get("interpolation", "bilinear")
        order = {"nearest": 0, "bilinear": 1, "bicubic": 3}[interp]
        fn = lambda s, c: rotate(s, angle, order=order, preserve_range=True)
        return iterate_over_axes(item, {"y", "x"}, fn)


class Flip(ProcessBlock):
    type_name: ClassVar[str] = "imaging.flip"
    name: ClassVar[str] = "Flip"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "flip"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "axis": {"type": "string",
                     "enum": ["t", "z", "c", "lambda", "y", "x"]},
        },
        "required": ["axis"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        axis = config["axis"]
        if axis not in item.axes:
            raise ValueError(f"axis {axis!r} not in image axes {item.axes}")
        idx = item.axes.index(axis)
        data = item.to_memory() if item.storage_ref else item._data
        flipped = np.flip(data, axis=idx)
        return _make_derived(item, flipped)


class Crop(ProcessBlock):
    type_name: ClassVar[str] = "imaging.crop"
    name: ClassVar[str] = "Crop"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "crop"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
        InputPort(name="mask", accepted_types=[Mask], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "bbox": {
                "type": "array",
                "description": "[y_start, y_end, x_start, x_end]",
            },
        },
    }


class Pad(ProcessBlock):
    type_name: ClassVar[str] = "imaging.pad"
    name: ClassVar[str] = "Pad"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "pad"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "pad": {"type": "array",
                    "description": "[top, bottom, left, right]"},
            "mode": {"type": "string",
                     "enum": ["constant", "reflect", "edge"],
                     "default": "constant"},
            "value": {"type": "number", "default": 0.0},
        },
        "required": ["pad"],
    }


class Resize(ProcessBlock):
    """Resize updates pixel_size per Q-IMG-3."""

    type_name: ClassVar[str] = "imaging.resize"
    name: ClassVar[str] = "Resize"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "resize"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "target_shape": {"type": "array"},
            "factor": {"type": "number"},
            "interpolation": {"type": "string",
                              "enum": ["nearest", "bilinear", "bicubic"],
                              "default": "bilinear"},
        },
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        from skimage.transform import resize
        target = config.get("target_shape")
        factor = config.get("factor")
        # ... compute new shape
        # update pixel_size accordingly
        new_pixel_size = self._compute_new_pixel_size(item, old_shape, new_shape)
        if new_pixel_size is not None:
            item = item.with_meta(pixel_size=new_pixel_size)
        # ... apply resize
```

**h. Acceptance criteria**:

- [ ] Five blocks: `Rotate`, `Flip`, `Crop`, `Pad`, `Resize`.
- [ ] Each block declares correct ClassVars.
- [ ] `Rotate(angle=90)` produces a 90-degree rotated 2D image.
- [ ] `Rotate` arbitrary angle preserves `pixel_size`.
- [ ] `Flip(axis="y")` flips along Y; `axis="z"` works on 3D.
- [ ] `Flip` raises `ValueError` for axis not in image axes.
- [ ] `Crop(bbox=[y0,y1,x0,x1])` returns the cropped region.
- [ ] `Crop(mask=...)` uses the mask bounding box.
- [ ] `Pad(pad=[t,b,l,r], mode="constant")` adds zero-padding.
- [ ] `Pad` modes `constant`/`reflect`/`edge` all work.
- [ ] `Resize(target_shape=...)` updates `pixel_size` per Q-IMG-3.
- [ ] `Resize(factor=0.5)` updates `pixel_size` proportionally.
- [ ] `Resize` with no source `pixel_size` leaves output `pixel_size`
      as None (debug log).
- [ ] All five blocks broadcast over 5D inputs.
- [ ] All five blocks propagate framework/meta/user per Q-IMG-3.

**i. Out of scope**: Image registration (T-IMG-027/T-IMG-028); affine transformation (T-IMG-028).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~500 src + ~500 tests. **Large**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-008 Geometry bundle (Rotate/Flip/Crop/Pad/Resize)`

**Status**: Implemented (Sprint C imaging preprocess subset B). `Rotate`,
`Flip`, `Crop`, `Pad`, and `Resize` are now concrete `ProcessBlock`
implementations with focused plugin tests. `Crop(mask=...)` support is
implemented in the block, while the current local test coverage stays
on explicit bounding-box paths because `Mask` itself remains under
T-IMG-001 skeleton status.

---

### T-IMG-009 — ConvertDType

**a. Ticket ID and name**: T-IMG-009 — `ConvertDType` block.

**b. Source ADR sections**: ADR-027 D5.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/convert_dtype.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_preprocessing/test_convert_dtype.py`
  - `test_convert_uint8_to_float32_linear`
  - `test_convert_uint16_to_uint8_linear`
  - `test_convert_float32_to_uint8_clip`
  - `test_convert_to_bool_thresholds_at_zero`
  - `test_convert_invalid_dtype_raises`
  - `test_convert_preserves_axes_and_shape`
  - `test_convert_preserves_meta`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock

from scieasy_blocks_imaging.types import Image


class ConvertDType(ProcessBlock):
    type_name: ClassVar[str] = "imaging.convert_dtype"
    name: ClassVar[str] = "Convert DType"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "convert_dtype"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "target_dtype": {"type": "string",
                             "enum": ["uint8", "uint16", "float32",
                                      "float64", "bool"],
                             "default": "float32"},
            "rescale": {"type": "string",
                        "enum": ["linear", "clip"],
                        "default": "linear"},
        },
        "required": ["target_dtype"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        target = np.dtype(config["target_dtype"])
        rescale = config.get("rescale", "linear")
        data = item.to_memory() if item.storage_ref else item._data
        out = _convert(data, target, rescale)
        new = Image(axes=list(item.axes), shape=item.shape, dtype=target,
                    framework=item.framework.derive(), meta=item.meta,
                    user=dict(item.user))
        new._data = out
        return new


def _convert(arr, target, rescale):
    if target == np.dtype(bool):
        return arr > 0
    if rescale == "linear":
        info_in = np.iinfo(arr.dtype) if np.issubdtype(arr.dtype, np.integer) else None
        info_out = np.iinfo(target) if np.issubdtype(target, np.integer) else None
        if info_in and info_out:
            return ((arr.astype(np.float64) / info_in.max) * info_out.max).astype(target)
        if info_out:
            return np.clip(arr, 0, info_out.max).astype(target)
        return arr.astype(target)
    # clip
    if np.issubdtype(target, np.integer):
        info_out = np.iinfo(target)
        return np.clip(arr, info_out.min, info_out.max).astype(target)
    return arr.astype(target)
```

**h. Acceptance criteria**:

- [ ] `ConvertDType` is `ProcessBlock` with required ClassVars.
- [ ] `target_dtype` enum includes 5 standard dtypes.
- [ ] `rescale="linear"` correctly rescales `uint8 → float32`,
      `uint16 → uint8`, etc.
- [ ] `rescale="clip"` clips values without rescaling.
- [ ] `target_dtype="bool"` thresholds at zero (positive → True).
- [ ] Invalid `target_dtype` → `ValueError`.
- [ ] Output axes/shape preserved.
- [ ] Output meta preserved.

**i. Out of scope**: HDR / 32-bit float to 16-bit conversions with custom min/max scaling.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~150 src + ~200 tests. **Small-Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-009 ConvertDType (uint8/uint16/float32/float64/bool)`

**Status**: Implemented (Sprint C imaging preprocess subset B).
`ConvertDType` now supports all five locked target dtypes plus the
`linear` and `clip` modes, preserving axes / shape / metadata across
the conversion.

---

### T-IMG-010 — AxisSplit / AxisMerge

**a. Ticket ID and name**: T-IMG-010 — `AxisSplit` and `AxisMerge`.

**b. Source ADR sections**: ADR-027 D1 (axes), D5, ADR-020 (Collection); Q-IMG-3, Q-IMG-4.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/axis_split_merge.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_preprocessing/test_axis_split_merge.py`
  - `test_axis_split_c_returns_collection_per_channel`
  - `test_axis_split_t_returns_collection_per_frame`
  - `test_axis_split_z_returns_collection_per_z_plane`
  - `test_axis_split_invalid_axis_raises`
  - `test_axis_split_meta_source_file_appended_with_axis_index`
  - `test_axis_split_meta_channel_info_partitioned`
  - `test_axis_merge_inverse_of_split`
  - `test_axis_merge_invalid_ordering_raises`
  - `test_axis_merge_inconsistent_shapes_raises`
  - `test_axis_split_merge_round_trip_5d`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.collection import Collection

from scieasy_blocks_imaging.types import Image


class AxisSplit(ProcessBlock):
    """Split an Image along one axis into a Collection of (N-1)D images."""

    type_name: ClassVar[str] = "imaging.axis_split"
    name: ClassVar[str] = "Axis Split"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "axis_split"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Collection[Image]]),
    ]

    config_schema = {
        "properties": {
            "axis": {"type": "string",
                     "enum": ["t", "z", "c", "lambda"]},
        },
        "required": ["axis"],
    }

    def run(self, inputs, config):
        item: Image = inputs["image"]
        axis = config["axis"]
        if axis not in item.axes:
            raise ValueError(f"axis {axis!r} not in image axes {item.axes}")
        idx = item.axes.index(axis)
        data = item.to_memory() if item.storage_ref else item._data
        new_axes = [a for a in item.axes if a != axis]
        items = []
        for i in range(item.shape[idx]):
            slc = [slice(None)] * data.ndim
            slc[idx] = i
            sub = data[tuple(slc)]
            new_meta = self._partition_meta(item.meta, axis, i)
            new_img = Image(
                axes=new_axes, shape=sub.shape, dtype=sub.dtype,
                framework=item.framework.derive(),
                meta=new_meta, user=dict(item.user),
            )
            new_img._data = sub
            items.append(new_img)
        return Collection(items)

    def _partition_meta(self, meta, axis: str, idx: int):
        if meta is None:
            return None
        # Q-IMG-4: derive a unique source_file
        src = meta.source_file
        if src:
            from pathlib import Path
            p = Path(src)
            new_src = f"{p.stem}__{axis}={idx}{p.suffix}"
        else:
            new_src = f"axis_split__{axis}={idx}"
        # Q-IMG-3: partition channel-related fields
        updates = {"source_file": new_src}
        if axis == "c" and meta.channels and idx < len(meta.channels):
            updates["channels"] = [meta.channels[idx]]
        if axis == "lambda" and meta.wavelengths_nm and idx < len(meta.wavelengths_nm):
            updates["wavelengths_nm"] = [meta.wavelengths_nm[idx]]
        return meta.model_copy(update=updates)


class AxisMerge(ProcessBlock):
    """Merge a Collection of (N-1)D images into one N-D image."""

    type_name: ClassVar[str] = "imaging.axis_merge"
    name: ClassVar[str] = "Axis Merge"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "axis_merge"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Collection[Image]]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "axis": {"type": "string",
                     "enum": ["t", "z", "c", "lambda"]},
            "ordering": {"type": "array",
                         "description": "indices into the input collection in output order"},
        },
        "required": ["axis"],
    }

    def run(self, inputs, config):
        col: Collection[Image] = inputs["images"]
        axis = config["axis"]
        ordering = config.get("ordering", list(range(len(col))))
        if len(ordering) != len(col):
            raise ValueError("ordering length must match collection length")
        items = [col[i] for i in ordering]
        # validate consistent shapes & axes
        ref_axes = items[0].axes
        for it in items[1:]:
            if it.axes != ref_axes:
                raise ValueError(f"AxisMerge: axes mismatch {it.axes} vs {ref_axes}")
            if it.shape != items[0].shape:
                raise ValueError(f"AxisMerge: shape mismatch")
        data = np.stack([(it.to_memory() if it.storage_ref else it._data)
                         for it in items], axis=0)
        new_axes = [axis] + ref_axes
        new_img = Image(
            axes=new_axes, shape=data.shape, dtype=data.dtype,
            framework=items[0].framework.derive(),
            meta=items[0].meta, user=dict(items[0].user),
        )
        new_img._data = data
        return new_img
```

**h. Acceptance criteria**:

- [ ] `AxisSplit` produces Collection of N items where N = `shape[axis]`.
- [ ] Each output's axes excludes the split axis.
- [ ] Splitting along `c` partitions `meta.channels` per-output.
- [ ] Splitting along `lambda` partitions `meta.wavelengths_nm`
      per-output.
- [ ] `meta.source_file` appended with `__<axis>=<index>` per Q-IMG-4.
- [ ] `AxisMerge` is the inverse of `AxisSplit` (round-trip
      preserves data).
- [ ] `AxisMerge` raises on inconsistent shapes/axes.
- [ ] `AxisMerge` `ordering` parameter respected.
- [ ] Invalid axis (not in source) raises `ValueError`.

**i. Out of scope**: Splitting along `y`/`x` (split-into-tiles is a Phase 12 feature).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~250 src + ~300 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-010 AxisSplit and AxisMerge for any axis`

**Status**: Implemented (Sprint C imaging preprocess subset B).
`AxisSplit` and `AxisMerge` now provide typed Collection-based split /
merge across `t` / `z` / `c` / `lambda`, append `meta.source_file`
suffixes per split item, and partition channel / wavelength metadata
when the driving axis is `c` or `lambda`.

---

### T-IMG-011 — Deconvolve placeholder

**a. Ticket ID and name**: T-IMG-011 — `Deconvolve` placeholder.

**b. Source ADR sections**: ADR-027 D9 (palette discoverability for future blocks).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/deconvolve.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocessing/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_preprocessing/test_deconvolve.py`
  - `test_deconvolve_class_exists_in_palette`
  - `test_deconvolve_run_raises_not_implemented_error`
  - `test_deconvolve_get_blocks_includes_class`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock

from scieasy_blocks_imaging.types import Image


class Deconvolve(ProcessBlock):
    """PLACEHOLDER for Phase 12 deconvolution.

    Ships in 0.1.0 so the palette has the entry. The block raises
    NotImplementedError when invoked.
    """

    type_name: ClassVar[str] = "imaging.deconvolve"
    name: ClassVar[str] = "Deconvolve"
    category: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "deconvolve"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["richardson_lucy", "wiener", "tikhonov"],
                       "default": "richardson_lucy"},
            "iterations": {"type": "integer", "default": 30},
        },
    }

    def process_item(self, item, config, state=None):
        raise NotImplementedError(
            "Deconvolve is planned for Phase 12. "
            "Currently a palette placeholder."
        )
```

**h. Acceptance criteria**:

- [ ] `Deconvolve` class exists with the correct ClassVars.
- [ ] Calling `process_item` raises `NotImplementedError` with the
      Phase 12 message.
- [ ] Block appears in `get_blocks()`.
- [ ] Palette can render its config schema (no validation errors).

**i. Out of scope**: All actual deconvolution algorithms.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~50 src + ~50 tests. **Small**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-011 Deconvolve placeholder for Phase 12`


---

### T-IMG-012 — MorphologyOp

**a. Ticket ID and name**: T-IMG-012 — `MorphologyOp` block.

**b. Source ADR sections**: ADR-027 D3, D5.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/ops.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_morphology/test_ops.py`
  - `test_morphology_erode_2d`
  - `test_morphology_dilate_2d`
  - `test_morphology_open_2d`
  - `test_morphology_close_2d`
  - `test_morphology_tophat_2d`
  - `test_morphology_bottomhat_2d`
  - `test_morphology_disk_selem_size_param`
  - `test_morphology_square_selem_shape`
  - `test_morphology_cross_selem_shape`
  - `test_morphology_invalid_op_raises`
  - `test_morphology_5d_iterates_per_slice`
  - `test_morphology_preserves_axes_meta`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes

from scieasy_blocks_imaging.types import Image


class MorphologyOp(ProcessBlock):
    """Morphological operations on 2D slices."""

    type_name: ClassVar[str] = "imaging.morphology_op"
    name: ClassVar[str] = "Morphology Op"
    category: ClassVar[str] = "morphology"
    algorithm: ClassVar[str] = "morphology"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image],
                  constraint=has_axes("y", "x")),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "op": {"type": "string",
                   "enum": ["erode", "dilate", "open", "close",
                            "tophat", "bottomhat"],
                   "default": "erode"},
            "selem_shape": {"type": "string",
                            "enum": ["disk", "square", "cross"],
                            "default": "disk"},
            "selem_size": {"type": "integer", "default": 3, "minimum": 1},
        },
        "required": ["op"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        from skimage import morphology as M
        op = config["op"]
        shape = config.get("selem_shape", "disk")
        size = config.get("selem_size", 3)
        selem = {"disk": M.disk, "square": M.square, "cross": M.diamond}[shape](size)
        op_fn = {
            "erode": M.erosion, "dilate": M.dilation,
            "open": M.opening, "close": M.closing,
            "tophat": M.white_tophat, "bottomhat": M.black_tophat,
        }.get(op)
        if op_fn is None:
            raise ValueError(f"Unknown morphology op: {op}")
        return iterate_over_axes(item, {"y", "x"},
                                 lambda s, c: op_fn(s, selem))
```

**h. Acceptance criteria**:

- [ ] All six ops work on 2D inputs.
- [ ] All three selem shapes work.
- [ ] `selem_size` param respected.
- [ ] Invalid op → `ValueError`.
- [ ] 5D inputs broadcast.
- [ ] Output preserves axes/meta.

**i. Out of scope**: 3D structuring elements (Phase 12); reconstruction by erosion/dilation.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~120 src + ~250 tests. **Small-Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-012 MorphologyOp (erode/dilate/open/close/tophat/bottomhat)`

**Status**: Implemented (Sprint C imaging morphology chunk). All six
locked morphology ops now run on 2D slices and broadcast across extra
axes via `iterate_over_axes`, with focused tests covering valid ops,
invalid config, and higher-rank broadcasting.

---

### T-IMG-013 — EdgeDetect

**a. Ticket ID and name**: T-IMG-013 — `EdgeDetect` block.

**b. Source ADR sections**: ADR-027 D3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/edges.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_morphology/test_edges.py`
  - `test_edge_sobel_2d`
  - `test_edge_scharr_2d`
  - `test_edge_canny_2d`
  - `test_edge_canny_thresholds_param`
  - `test_edge_prewitt_2d`
  - `test_edge_invalid_method_raises`
  - `test_edge_5d_broadcast`
  - `test_edge_preserves_axes`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes

from scieasy_blocks_imaging.types import Image


class EdgeDetect(ProcessBlock):
    type_name: ClassVar[str] = "imaging.edge_detect"
    name: ClassVar[str] = "Edge Detect"
    category: ClassVar[str] = "morphology"
    algorithm: ClassVar[str] = "edge_detect"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image],
                  constraint=has_axes("y", "x")),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["sobel", "scharr", "canny", "prewitt"],
                       "default": "sobel"},
            "sigma": {"type": "number", "default": 1.0},
            "low_threshold": {"type": "number", "default": 0.1},
            "high_threshold": {"type": "number", "default": 0.2},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        from skimage import filters, feature
        method = config["method"]
        if method == "sobel":
            fn = lambda s, c: filters.sobel(s)
        elif method == "scharr":
            fn = lambda s, c: filters.scharr(s)
        elif method == "prewitt":
            fn = lambda s, c: filters.prewitt(s)
        elif method == "canny":
            sigma = config.get("sigma", 1.0)
            lo = config.get("low_threshold", 0.1)
            hi = config.get("high_threshold", 0.2)
            fn = lambda s, c: feature.canny(s, sigma=sigma,
                                            low_threshold=lo,
                                            high_threshold=hi)
        else:
            raise ValueError(f"Unknown edge method: {method}")
        return iterate_over_axes(item, {"y", "x"}, fn)
```

**h. Acceptance criteria**:

- [ ] Four methods work on 2D inputs.
- [ ] Canny `sigma`/`low_threshold`/`high_threshold` params respected.
- [ ] Invalid method → `ValueError`.
- [ ] 5D inputs broadcast.

**i. Out of scope**: Multiscale edge detection.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~120 src + ~150 tests. **Small**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-013 EdgeDetect (sobel/scharr/canny/prewitt)`

**Status**: Implemented (Sprint C imaging morphology chunk). `sobel`,
`scharr`, `prewitt`, and `canny` are now concrete, validate threshold
ordering, and broadcast per-slice over higher-rank image inputs.

---

### T-IMG-014 — RidgeFilter

**a. Ticket ID and name**: T-IMG-014 — `RidgeFilter` block.

**b. Source ADR sections**: ADR-027 D3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/ridges.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_morphology/test_ridges.py`
  - `test_ridge_frangi_2d`
  - `test_ridge_meijering_2d`
  - `test_ridge_sato_2d`
  - `test_ridge_hessian_2d`
  - `test_ridge_sigma_range_param`
  - `test_ridge_invalid_method_raises`
  - `test_ridge_5d_broadcast`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes

from scieasy_blocks_imaging.types import Image


class RidgeFilter(ProcessBlock):
    type_name: ClassVar[str] = "imaging.ridge_filter"
    name: ClassVar[str] = "Ridge Filter"
    category: ClassVar[str] = "morphology"
    algorithm: ClassVar[str] = "ridge_filter"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image],
                  constraint=has_axes("y", "x")),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["frangi", "meijering", "sato", "hessian"],
                       "default": "frangi"},
            "sigma_min": {"type": "number", "default": 1.0},
            "sigma_max": {"type": "number", "default": 10.0},
            "num_sigma": {"type": "integer", "default": 10},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        from skimage import filters
        import numpy as np
        method = config["method"]
        s_min = config.get("sigma_min", 1.0)
        s_max = config.get("sigma_max", 10.0)
        n = config.get("num_sigma", 10)
        sigmas = np.linspace(s_min, s_max, n).tolist()
        fn_map = {
            "frangi": lambda s, c: filters.frangi(s, sigmas=sigmas),
            "meijering": lambda s, c: filters.meijering(s, sigmas=sigmas),
            "sato": lambda s, c: filters.sato(s, sigmas=sigmas),
            "hessian": lambda s, c: filters.hessian(s, sigmas=sigmas),
        }
        if method not in fn_map:
            raise ValueError(f"Unknown ridge method: {method}")
        return iterate_over_axes(item, {"y", "x"}, fn_map[method])
```

**h. Acceptance criteria**:

- [ ] Four methods work on 2D inputs.
- [ ] `sigma_min`/`sigma_max`/`num_sigma` build the sigma list.
- [ ] Invalid method → `ValueError`.
- [ ] 5D inputs broadcast.

**i. Out of scope**: Custom kernels; non-skimage filters.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~120 src + ~150 tests. **Small**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-014 RidgeFilter (frangi/meijering/sato/hessian)`

**Status**: Implemented (Sprint C imaging morphology chunk). All four
ridge filters now construct sigma ranges from
`sigma_min`/`sigma_max`/`num_sigma`, operate on 2D slices, and validate
bad method or sigma-range config explicitly.

---

### T-IMG-015 — Sharpen

**a. Ticket ID and name**: T-IMG-015 — `Sharpen` block.

**b. Source ADR sections**: ADR-027 D3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/sharpen.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_morphology/test_sharpen.py`
  - `test_sharpen_unsharp_2d`
  - `test_sharpen_laplacian_2d`
  - `test_sharpen_amount_param`
  - `test_sharpen_invalid_method_raises`
  - `test_sharpen_5d_broadcast`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes

from scieasy_blocks_imaging.types import Image


class Sharpen(ProcessBlock):
    type_name: ClassVar[str] = "imaging.sharpen"
    name: ClassVar[str] = "Sharpen"
    category: ClassVar[str] = "morphology"
    algorithm: ClassVar[str] = "sharpen"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image],
                  constraint=has_axes("y", "x")),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["unsharp", "laplacian"],
                       "default": "unsharp"},
            "amount": {"type": "number", "default": 1.0},
            "radius": {"type": "number", "default": 1.0},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        from skimage import filters
        method = config["method"]
        amount = config.get("amount", 1.0)
        radius = config.get("radius", 1.0)
        if method == "unsharp":
            fn = lambda s, c: filters.unsharp_mask(s, radius=radius, amount=amount)
        elif method == "laplacian":
            fn = lambda s, c: s + amount * filters.laplace(s)
        else:
            raise ValueError(f"Unknown sharpen method: {method}")
        return iterate_over_axes(item, {"y", "x"}, fn)
```

**h. Acceptance criteria**:

- [ ] Two methods work on 2D inputs.
- [ ] `amount`/`radius` params respected.
- [ ] Invalid method → `ValueError`.
- [ ] 5D inputs broadcast.

**i. Out of scope**: CLAHE; deep-learning sharpening.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~80 src + ~120 tests. **Small**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-015 Sharpen (unsharp / laplacian)`

**Status**: Implemented (Sprint C imaging morphology chunk). `unsharp`
and `laplacian` sharpening are now concrete `ProcessBlock`
implementations with parameter validation and focused shape-preserving
tests.

---

### T-IMG-016 — FFTFilter

**a. Ticket ID and name**: T-IMG-016 — `FFTFilter` block.

**b. Source ADR sections**: ADR-027 D3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/fft.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_morphology/test_fft.py`
  - `test_fft_lowpass_2d`
  - `test_fft_highpass_2d`
  - `test_fft_bandpass_2d`
  - `test_fft_cutoff_param`
  - `test_fft_invalid_type_raises`
  - `test_fft_5d_broadcast`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes

from scieasy_blocks_imaging.types import Image


class FFTFilter(ProcessBlock):
    """Frequency-domain filtering with circular masks."""

    type_name: ClassVar[str] = "imaging.fft_filter"
    name: ClassVar[str] = "FFT Filter"
    category: ClassVar[str] = "morphology"
    algorithm: ClassVar[str] = "fft_filter"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image],
                  constraint=has_axes("y", "x")),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "type": {"type": "string",
                     "enum": ["lowpass", "highpass", "bandpass"],
                     "default": "lowpass"},
            "cutoff_low": {"type": "number", "default": 0.1},
            "cutoff_high": {"type": "number", "default": 0.5},
        },
        "required": ["type"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        ftype = config["type"]
        lo = config.get("cutoff_low", 0.1)
        hi = config.get("cutoff_high", 0.5)
        def fn(s, c):
            f = np.fft.fftshift(np.fft.fft2(s))
            mask = _build_freq_mask(s.shape, ftype, lo, hi)
            return np.real(np.fft.ifft2(np.fft.ifftshift(f * mask)))
        return iterate_over_axes(item, {"y", "x"}, fn)


def _build_freq_mask(shape, ftype, lo, hi):
    h, w = shape
    cy, cx = h // 2, w // 2
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    r_norm = r / r.max()
    if ftype == "lowpass":
        return (r_norm < lo).astype(float)
    if ftype == "highpass":
        return (r_norm >= lo).astype(float)
    if ftype == "bandpass":
        return ((r_norm >= lo) & (r_norm < hi)).astype(float)
    raise ValueError(f"Unknown FFT filter type: {ftype}")
```

**h. Acceptance criteria**:

- [ ] Three filter types work on 2D inputs.
- [ ] `cutoff_low`/`cutoff_high` params respected.
- [ ] Invalid type → `ValueError`.
- [ ] 5D inputs broadcast.
- [ ] Output is real-valued.

**i. Out of scope**: Periodic noise removal; non-circular masks.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~150 src + ~150 tests. **Small-Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-016 FFTFilter (lowpass / highpass / bandpass)`

**Status**: Implemented (Sprint C imaging morphology chunk). FFT-based
lowpass / highpass / bandpass filtering now validates cutoff ranges and
ordering, broadcasts per 2D slice, and returns real-valued outputs.

---

### T-IMG-017 — Threshold

**Status**: Implemented in issue #372's segmentation core bundle. `Threshold`
now supports all spec-listed threshold methods, returns `Mask` outputs with
`Collection[Mask]` packaging, and broadcasts over extra imaging axes via
`iterate_over_axes`. Package tests cover manual-parameter validation, 5D
broadcasting, and plugin-surface smoke wiring.

**a. Ticket ID and name**: T-IMG-017 — `Threshold` block.

**b. Source ADR sections**: ADR-027 D3, D2 (Mask output type).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/threshold.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_segmentation/test_threshold.py`
  - `test_threshold_otsu_returns_mask`
  - `test_threshold_li_returns_mask`
  - `test_threshold_yen_returns_mask`
  - `test_threshold_isodata_returns_mask`
  - `test_threshold_mean_returns_mask`
  - `test_threshold_triangle_returns_mask`
  - `test_threshold_adaptive_otsu_local_window`
  - `test_threshold_manual_with_value`
  - `test_threshold_manual_without_value_raises`
  - `test_threshold_invalid_method_raises`
  - `test_threshold_output_dtype_is_bool`
  - `test_threshold_5d_broadcast_per_slice`
  - `test_threshold_preserves_meta`
  - `test_threshold_round_trip_serialise`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes

from scieasy_blocks_imaging.types import Image, Mask


class Threshold(ProcessBlock):
    """Single threshold block with multiple methods. Outputs Mask."""

    type_name: ClassVar[str] = "imaging.threshold"
    name: ClassVar[str] = "Threshold"
    category: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "threshold"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image],
                  constraint=has_axes("y", "x")),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="mask", accepted_types=[Mask]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["otsu", "li", "yen", "isodata", "mean",
                                "triangle", "adaptive_otsu", "manual"],
                       "default": "otsu"},
            "value": {"type": "number",
                      "description": "Manual threshold value (for method=manual)"},
            "block_size": {"type": "integer", "default": 35,
                           "description": "Window size for adaptive_otsu"},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config, state=None) -> Mask:
        from skimage import filters
        method = config["method"]
        if method == "manual":
            if "value" not in config:
                raise ValueError("Threshold method=manual requires 'value'")
            val = config["value"]
            fn = lambda s, c: (s > val).astype(bool)
        else:
            fn_map = {
                "otsu": filters.threshold_otsu,
                "li": filters.threshold_li,
                "yen": filters.threshold_yen,
                "isodata": filters.threshold_isodata,
                "mean": filters.threshold_mean,
                "triangle": filters.threshold_triangle,
            }
            if method == "adaptive_otsu":
                bs = config.get("block_size", 35)
                fn = lambda s, c: (s > filters.threshold_local(s, block_size=bs)).astype(bool)
            elif method in fn_map:
                t_fn = fn_map[method]
                fn = lambda s, c: (s > t_fn(s)).astype(bool)
            else:
                raise ValueError(f"Unknown threshold method: {method}")
        result = iterate_over_axes(item, {"y", "x"}, fn)
        # cast to Mask
        return Mask(
            axes=list(result.axes), shape=result.shape, dtype=bool,
            framework=result.framework, meta=result.meta,
            user=dict(result.user),
            **{"_data": result._data} if hasattr(result, "_data") else {},
        )
```

**h. Acceptance criteria**:

- [ ] Eight methods work on 2D inputs.
- [ ] `manual` requires `value`; otherwise raises `ValueError`.
- [ ] `adaptive_otsu` uses local windows via `block_size`.
- [ ] Output is `Mask` (not `Image`) with `dtype=bool`.
- [ ] Invalid method → `ValueError`.
- [ ] 5D inputs broadcast.
- [ ] `meta` propagated; `framework` derived.
- [ ] Output round-trips through worker subprocess.

**i. Out of scope**: Multi-class thresholding; multi-Otsu (Phase 12).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~200 src + ~300 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-017 Threshold (otsu/li/yen/isodata/mean/triangle/adaptive/manual)`

---

### T-IMG-018 — Watershed

**Status**: Implemented in issue #372's segmentation core bundle. `Watershed`
now runs the `distance`, `gradient`, and `markers` modes with optional mask and
markers inputs, emits `Collection[Label]` outputs with populated raster slots
and `n_objects`, and supports per-slice broadcasting across higher-rank imaging
inputs. Tests cover distance mode, marker-driven mode, mask usage, invalid
methods, and 5D broadcasting.

**a. Ticket ID and name**: T-IMG-018 — `Watershed` block.

**b. Source ADR sections**: ADR-027 D3, D2 (Label output, CompositeData slots).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/watershed.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_segmentation/test_watershed.py`
  - `test_watershed_distance_basic_2d`
  - `test_watershed_gradient_method`
  - `test_watershed_with_markers_input`
  - `test_watershed_with_mask_input`
  - `test_watershed_min_distance_param`
  - `test_watershed_compactness_param`
  - `test_watershed_output_is_label_with_raster`
  - `test_watershed_5d_broadcast`
  - `test_watershed_invalid_method_raises`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array

from scieasy_blocks_imaging.types import Image, Label, Mask


class Watershed(ProcessBlock):
    type_name: ClassVar[str] = "imaging.watershed"
    name: ClassVar[str] = "Watershed"
    category: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "watershed"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
        InputPort(name="mask", accepted_types=[Mask], required=False),
        InputPort(name="markers", accepted_types=[Label], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["distance", "gradient", "markers"],
                       "default": "distance"},
            "min_distance": {"type": "integer", "default": 10},
            "compactness": {"type": "number", "default": 0.0},
        },
    }

    def run(self, inputs, config):
        from scipy import ndimage as ndi
        from skimage.feature import peak_local_max
        from skimage.segmentation import watershed
        from skimage.filters import sobel

        image = inputs["image"]
        mask = inputs.get("mask")
        markers_in = inputs.get("markers")
        method = config.get("method", "distance")
        min_dist = config.get("min_distance", 10)
        comp = config.get("compactness", 0.0)

        data = image.to_memory() if image.storage_ref else image._data
        mask_data = (mask.to_memory() if mask and mask.storage_ref
                     else (mask._data if mask else None))

        if method == "distance":
            distance = ndi.distance_transform_edt(mask_data if mask_data is not None else data > 0)
            local_max = peak_local_max(distance, min_distance=min_dist)
            mk = np.zeros(distance.shape, dtype=int)
            for i, (y, x) in enumerate(local_max, start=1):
                mk[y, x] = i
            labels = watershed(-distance, mk, mask=mask_data, compactness=comp)
        elif method == "gradient":
            elevation = sobel(data)
            mk = np.zeros_like(data, dtype=int)
            mk[data < data.mean()] = 1
            mk[data > data.mean() * 1.5] = 2
            labels = watershed(elevation, mk, mask=mask_data, compactness=comp)
        elif method == "markers":
            if markers_in is None:
                raise ValueError("method=markers requires markers input")
            mk = (markers_in.slots["raster"].to_memory()
                  if markers_in.slots["raster"].storage_ref
                  else markers_in.slots["raster"]._data)
            labels = watershed(data, mk, mask=mask_data, compactness=comp)
        else:
            raise ValueError(f"Unknown watershed method: {method}")

        raster = Array(axes=list(image.axes), shape=labels.shape,
                       dtype=labels.dtype)
        raster._data = labels
        return Label(slots={"raster": raster, "polygons": None},
                     framework=image.framework.derive(),
                     meta=Label.Meta(source_file=getattr(image.meta, "source_file", None),
                                     n_objects=int(labels.max())),
                     user=dict(image.user))
```

**h. Acceptance criteria**:

- [ ] Three methods work on 2D inputs.
- [ ] Optional `mask` and `markers` inputs respected.
- [ ] `min_distance`/`compactness` params respected.
- [ ] Output is `Label` with `raster` slot populated, `polygons=None`.
- [ ] `Label.meta.n_objects` set to label count.
- [ ] `method="markers"` with no markers raises `ValueError`.
- [ ] 5D inputs broadcast.

**i. Out of scope**: 3D watershed (Phase 12); H-watershed.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~250 src + ~300 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-018 Watershed (distance / gradient / markers)`

---

### T-IMG-019 — CellposeSegment (FLAGSHIP)

**Status**: Implemented in PR #370. `CellposeSegment` now uses the
ADR-027 `setup()` / `teardown()` lifecycle to load a cellpose model once
per run, emit `Collection[Label]` outputs with populated `n_objects`
metadata, and keep the optional-dependency path friendly. The package
tests exercise the contract with test doubles, while the imaging smoke
test verifies the block is wired into the plugin surface.

**a. Ticket ID and name**: T-IMG-019 — `CellposeSegment` (FLAGSHIP block).

**b. Source ADR sections**:

- ADR-027 D7 (`setup` / `teardown` lifecycle hooks).
- ADR-027 D2 (Label output).
- ADR-027 D10 (GPU auto-detect interaction).
- Q-IMG-2 (CPU fallback).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/cellpose_segment.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_segmentation/test_cellpose.py` (marker:
  `@pytest.mark.requires_cellpose`)
  - `test_cellpose_class_exists_in_palette`
  - `test_cellpose_setup_loads_model_once`
  - `test_cellpose_process_item_uses_state_model`
  - `test_cellpose_teardown_releases_state`
  - `test_cellpose_collection_input_runs_setup_once`
  - `test_cellpose_returns_collection_of_label`
  - `test_cellpose_label_raster_dtype_int`
  - `test_cellpose_use_gpu_false_default`
  - `test_cellpose_use_gpu_true_calls_torch_empty_cache_in_teardown`
  - `test_cellpose_missing_dependency_raises_friendly_import_error`
  - `test_cellpose_diameter_param_passed_to_eval`
  - `test_cellpose_flow_threshold_param_passed_to_eval`
  - `test_cellpose_meta_n_objects_populated`
  - `test_cellpose_round_trip_serialise`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
import logging
from typing import Any, ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array
from scieasy.core.types.collection import Collection

from scieasy_blocks_imaging.types import Image, Label

logger = logging.getLogger(__name__)


class CellposeSegment(ProcessBlock):
    """Flagship segmentation block using cellpose deep learning models.

    Implements ADR-027 D7 setup/teardown to load the cellpose model
    ONCE per run, not per item. The model lives in the ``state``
    object passed through to ``process_item``.

    Per Q-IMG-2: defaults to CPU. Set ``use_gpu=True`` to use CUDA when
    available; cellpose falls back to CPU automatically if CUDA is not
    present.

    Optional dependency: install with
    ``pip install scieasy-blocks-imaging[cellpose]``.
    """

    type_name: ClassVar[str] = "imaging.cellpose_segment"
    name: ClassVar[str] = "Cellpose Segmentation"
    category: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "cellpose"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Collection[Image]]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="labels", accepted_types=[Collection[Label]]),
    ]

    config_schema = {
        "properties": {
            "model": {"type": "string",
                      "enum": ["cyto3", "cyto2", "nuclei", "custom"],
                      "default": "cyto3"},
            "diameter": {"type": "number", "default": 30.0, "minimum": 0.0},
            "flow_threshold": {"type": "number", "default": 0.4,
                               "minimum": 0.0, "maximum": 1.0},
            "cellprob_threshold": {"type": "number", "default": 0.0},
            "use_gpu": {"type": "boolean", "default": False},
            "channels": {"type": "array", "default": [0, 0]},
            "custom_model_path": {"type": "string"},
        },
    }

    def setup(self, config: BlockConfig) -> Any:
        """Load cellpose model ONCE per run (ADR-027 D7)."""
        try:
            from cellpose import models
        except ImportError as exc:
            raise ImportError(
                "CellposeSegment requires the [cellpose] extra: "
                "pip install scieasy-blocks-imaging[cellpose]"
            ) from exc
        model_name = config.get("model", "cyto3")
        use_gpu = bool(config.get("use_gpu", False))
        if model_name == "custom":
            path = config.get("custom_model_path")
            if not path:
                raise ValueError("model=custom requires custom_model_path")
            return models.CellposeModel(pretrained_model=path, gpu=use_gpu)
        return models.Cellpose(model_type=model_name, gpu=use_gpu)

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Label:
        if state is None:
            raise RuntimeError("CellposeSegment.process_item called without state")
        diameter = config.get("diameter", 30.0)
        flow = config.get("flow_threshold", 0.4)
        cellprob = config.get("cellprob_threshold", 0.0)
        chans = config.get("channels", [0, 0])

        data = item.to_memory() if item.storage_ref else item._data
        # Cellpose expects 2D or 2D+channel; if higher-dim we take the first
        # (y, x) slice. The user is expected to chain AxisProjection or
        # SelectSlice if they want to segment z-stacks differently.
        if data.ndim > 2:
            # take centre slice along all extra axes
            slc = tuple(s // 2 for s in data.shape[:-2]) + (slice(None), slice(None))
            data_2d = data[slc]
        else:
            data_2d = data

        masks, flows, styles, diams = state.eval(
            data_2d, diameter=diameter, channels=chans,
            flow_threshold=flow, cellprob_threshold=cellprob,
        )

        raster = Array(axes=["y", "x"], shape=masks.shape, dtype=masks.dtype)
        raster._data = masks
        return Label(
            slots={"raster": raster, "polygons": None},
            framework=item.framework.derive(),
            meta=Label.Meta(
                source_file=getattr(item.meta, "source_file", None),
                n_objects=int(masks.max()),
            ),
            user=dict(item.user),
        )

    def teardown(self, state: Any) -> None:
        """Release GPU memory when applicable (Q-IMG-2)."""
        if state is None:
            return
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
```

**h. Acceptance criteria**:

- [ ] `CellposeSegment` is `ProcessBlock` subclass.
- [ ] `setup()` loads cellpose model and returns it as state.
- [ ] `process_item()` uses `state.eval(...)` per image (NOT
      reloading the model per call).
- [ ] `teardown()` calls `torch.cuda.empty_cache()` when torch+CUDA
      available, no-op otherwise.
- [ ] `setup()` raises friendly `ImportError` when cellpose missing.
- [ ] `model="custom"` requires `custom_model_path`; otherwise
      `ValueError`.
- [ ] Output is `Collection[Label]` of same length as input
      collection.
- [ ] Each output `Label` has `raster` slot populated with int
      dtype.
- [ ] `Label.meta.n_objects` set.
- [ ] `use_gpu=False` is the default (Q-IMG-2).
- [ ] `diameter`/`flow_threshold`/`cellprob_threshold`/`channels`
      params respected.
- [ ] Block survives `_serialise_one`/`_reconstruct_one` round-trip.
- [ ] Tests marked `@pytest.mark.requires_cellpose` and skipped when
      cellpose not installed.

**i. Out of scope**:

- 3D cellpose (Phase 12).
- StarDist (deferred).
- Custom training pipelines.
- TrackMate-style time-series tracking.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~300 src + ~400 tests. **Large**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-019 CellposeSegment flagship block with setup/teardown lifecycle`

---

### T-IMG-020 — BlobDetect

**Status**: Implemented in issue #372's segmentation core bundle. The live
repository skeleton and tests use `segmentation/blob_detect.py` rather than the
older spec shorthand `blob.py`; implementation follows that live contract.
`BlobDetect` now supports LoG / DoG / DoH detection, paints disk labels into a
`Label` raster with unique IDs across broadcast slices, and is wired into the
imaging plugin exports and smoke coverage.

**a. Ticket ID and name**: T-IMG-020 — `BlobDetect` block.

**b. Source ADR sections**: ADR-027 D3, D2.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/blob.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_segmentation/test_blob.py`
  - `test_blob_log_basic`
  - `test_blob_dog_basic`
  - `test_blob_doh_basic`
  - `test_blob_min_max_sigma_params`
  - `test_blob_threshold_param`
  - `test_blob_invalid_method_raises`
  - `test_blob_output_is_label_with_raster`
  - `test_blob_5d_broadcast`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array

from scieasy_blocks_imaging.types import Image, Label


class BlobDetect(ProcessBlock):
    type_name: ClassVar[str] = "imaging.blob_detect"
    name: ClassVar[str] = "Blob Detect"
    category: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "blob_detect"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string", "enum": ["LoG", "DoG", "DoH"],
                       "default": "LoG"},
            "min_sigma": {"type": "number", "default": 1.0},
            "max_sigma": {"type": "number", "default": 30.0},
            "num_sigma": {"type": "integer", "default": 10},
            "threshold": {"type": "number", "default": 0.1},
        },
        "required": ["method"],
    }

    def process_item(self, item, config, state=None):
        from skimage import feature, draw
        method = config["method"]
        fns = {"LoG": feature.blob_log, "DoG": feature.blob_dog,
               "DoH": feature.blob_doh}
        if method not in fns:
            raise ValueError(f"Unknown blob method: {method}")
        data = item.to_memory() if item.storage_ref else item._data
        # take centre 2D slice if N-D
        if data.ndim > 2:
            slc = tuple(s // 2 for s in data.shape[:-2]) + (slice(None), slice(None))
            data_2d = data[slc]
        else:
            data_2d = data
        blobs = fns[method](
            data_2d, min_sigma=config.get("min_sigma", 1.0),
            max_sigma=config.get("max_sigma", 30.0),
            num_sigma=config.get("num_sigma", 10),
            threshold=config.get("threshold", 0.1),
        )
        labels = np.zeros(data_2d.shape, dtype=np.int32)
        for i, blob in enumerate(blobs, start=1):
            y, x, sigma = blob[:3]
            rr, cc = draw.disk((y, x), sigma * np.sqrt(2), shape=labels.shape)
            labels[rr, cc] = i
        raster = Array(axes=["y", "x"], shape=labels.shape, dtype=labels.dtype)
        raster._data = labels
        return Label(
            slots={"raster": raster, "polygons": None},
            framework=item.framework.derive(),
            meta=Label.Meta(n_objects=len(blobs)),
            user=dict(item.user),
        )
```

**h. Acceptance criteria**:

- [ ] Three methods work on 2D inputs.
- [ ] `min_sigma`/`max_sigma`/`num_sigma`/`threshold` params used.
- [ ] Invalid method → `ValueError`.
- [ ] Output is `Label` with `raster` slot populated.
- [ ] `Label.meta.n_objects` matches detected blob count.

**i. Out of scope**: 3D blob detection.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~150 src + ~200 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-020 BlobDetect (LoG / DoG / DoH)`

---

### T-IMG-021 — ConnectedComponents

**Status**: Implemented in issue #372's segmentation core bundle.
`ConnectedComponents` now validates 4-connectivity / 8-connectivity, produces
`Label` outputs with raster slots and `n_objects`, and returns
`Collection[Label]` from `run()`. The continuation-B skeleton tests now cover
both connectivity modes and invalid-parameter behavior.

**a. Ticket ID and name**: T-IMG-021 — `ConnectedComponents` block.

**b. Source ADR sections**: ADR-027 D3, D2.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/connected_components.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_segmentation/test_connected_components.py`
  - `test_cc_4_connectivity_2d`
  - `test_cc_8_connectivity_2d`
  - `test_cc_returns_label_with_raster`
  - `test_cc_n_objects_in_meta`
  - `test_cc_invalid_connectivity_raises`
  - `test_cc_3d_input`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array

from scieasy_blocks_imaging.types import Label, Mask


class ConnectedComponents(ProcessBlock):
    type_name: ClassVar[str] = "imaging.connected_components"
    name: ClassVar[str] = "Connected Components"
    category: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "connected_components"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="mask", accepted_types=[Mask]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label]),
    ]

    config_schema = {
        "properties": {
            "connectivity": {"type": "integer", "enum": [1, 2],
                             "default": 1,
                             "description": "1=4-conn, 2=8-conn"},
        },
    }

    def process_item(self, item: Mask, config, state=None) -> Label:
        from skimage.measure import label as cc_label
        conn = config.get("connectivity", 1)
        if conn not in (1, 2):
            raise ValueError(f"connectivity must be 1 or 2, got {conn}")
        data = item.to_memory() if item.storage_ref else item._data
        labels = cc_label(data, connectivity=conn)
        raster = Array(axes=list(item.axes), shape=labels.shape,
                       dtype=labels.dtype)
        raster._data = labels
        return Label(
            slots={"raster": raster, "polygons": None},
            framework=item.framework.derive(),
            meta=Label.Meta(n_objects=int(labels.max())),
            user=dict(item.user),
        )
```

**h. Acceptance criteria**:

- [ ] `connectivity=1` (4-conn) and `=2` (8-conn) both work.
- [ ] Output is `Label` with `raster` populated.
- [ ] `Label.meta.n_objects` set.
- [ ] Invalid connectivity → `ValueError`.

**i. Out of scope**: 3D 26-connectivity beyond skimage default.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~80 src + ~150 tests. **Small**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-021 ConnectedComponents (4-conn / 8-conn)`

---

### T-IMG-022 — Cleanup bundle (RemoveSmallObjects / RemoveBorderObjects / FillHoles / ExpandLabels / ShrinkLabels)

**Status**: Implemented in issue #372's segmentation core bundle. The cleanup
module now provides all five blocks, including `Label`/`Mask` handling for
`RemoveSmallObjects`, hole filling for `Mask`, and distance-based label expand
/ shrink operations on raster labels. Tests now cover minimum-size filtering,
hole filling, expand/shrink behavior, and metadata preservation on cleaned
labels.

**a. Ticket ID and name**: T-IMG-022 — Cleanup bundle.

**b. Source ADR sections**: ADR-027 D3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/cleanup.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_segmentation/test_cleanup.py`
  - `test_remove_small_objects_min_size`
  - `test_remove_small_objects_input_label`
  - `test_remove_small_objects_input_mask`
  - `test_remove_border_objects`
  - `test_fill_holes_basic`
  - `test_expand_labels_distance`
  - `test_shrink_labels_distance`
  - `test_cleanup_preserves_label_meta_other_than_n_objects`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock

from scieasy_blocks_imaging.types import Label, Mask


class RemoveSmallObjects(ProcessBlock):
    type_name: ClassVar[str] = "imaging.remove_small_objects"
    name: ClassVar[str] = "Remove Small Objects"
    category: ClassVar[str] = "segmentation"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label, Mask]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label, Mask]),
    ]
    config_schema = {
        "properties": {
            "min_size": {"type": "integer", "default": 64, "minimum": 1},
        },
    }
    def process_item(self, item, config, state=None):
        from skimage.morphology import remove_small_objects
        # ... extract data, apply, repackage
        pass


class RemoveBorderObjects(ProcessBlock):
    type_name: ClassVar[str] = "imaging.remove_border_objects"
    name: ClassVar[str] = "Remove Border Objects"
    category: ClassVar[str] = "segmentation"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label]),
    ]
    config_schema = {"properties": {}}
    def process_item(self, item, config, state=None):
        from skimage.segmentation import clear_border
        # ...


class FillHoles(ProcessBlock):
    type_name: ClassVar[str] = "imaging.fill_holes"
    name: ClassVar[str] = "Fill Holes"
    category: ClassVar[str] = "segmentation"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="mask", accepted_types=[Mask]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="mask", accepted_types=[Mask]),
    ]
    config_schema = {"properties": {}}
    def process_item(self, item, config, state=None):
        from scipy.ndimage import binary_fill_holes
        # ...


class ExpandLabels(ProcessBlock):
    type_name: ClassVar[str] = "imaging.expand_labels"
    name: ClassVar[str] = "Expand Labels"
    category: ClassVar[str] = "segmentation"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label]),
    ]
    config_schema = {
        "properties": {
            "distance_px": {"type": "integer", "default": 5, "minimum": 1},
        },
    }
    def process_item(self, item, config, state=None):
        from skimage.segmentation import expand_labels
        # ...


class ShrinkLabels(ProcessBlock):
    type_name: ClassVar[str] = "imaging.shrink_labels"
    name: ClassVar[str] = "Shrink Labels"
    category: ClassVar[str] = "segmentation"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label]),
    ]
    config_schema = {
        "properties": {
            "distance_px": {"type": "integer", "default": 1, "minimum": 1},
        },
    }
    def process_item(self, item, config, state=None):
        # erode each label by distance_px
        pass
```

**h. Acceptance criteria**:

- [ ] All five blocks present with correct ClassVars.
- [ ] `RemoveSmallObjects` accepts both `Label` and `Mask` inputs.
- [ ] `RemoveSmallObjects` `min_size` param respected.
- [ ] `RemoveBorderObjects` removes labels touching image border.
- [ ] `FillHoles` fills interior holes in `Mask`.
- [ ] `ExpandLabels` / `ShrinkLabels` use the configured distance.
- [ ] `Label.meta.n_objects` is updated after cleanup.

**i. Out of scope**: Per-label filtering by intensity (use `RegionProps` + `FilterCollection`).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~300 src + ~300 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-022 Cleanup bundle (RemoveSmallObjects/RemoveBorderObjects/FillHoles/ExpandLabels/ShrinkLabels)`

---

### T-IMG-023 — TrackObjects placeholder

**a. Ticket ID and name**: T-IMG-023 — `TrackObjects` placeholder.

**b. Source ADR sections**: ADR-027 D9 (palette discoverability for placeholders).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/tracking/track_objects.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/tracking/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_tracking/test_track_objects.py`
  - `test_track_objects_class_exists`
  - `test_track_objects_run_raises_not_implemented`
  - `test_track_objects_in_get_blocks`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock

from scieasy_blocks_imaging.types import Label


class TrackObjects(ProcessBlock):
    """PLACEHOLDER for Phase 12 tracking."""

    type_name: ClassVar[str] = "imaging.track_objects"
    name: ClassVar[str] = "Track Objects"
    category: ClassVar[str] = "tracking"
    algorithm: ClassVar[str] = "track_objects"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="labels", accepted_types=[Label]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="tracks", accepted_types=[Label]),
    ]
    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["nearest_neighbour", "trackpy", "btrack"],
                       "default": "nearest_neighbour"},
            "max_distance": {"type": "number", "default": 50.0},
        },
    }

    def process_item(self, item, config, state=None):
        raise NotImplementedError(
            "TrackObjects is planned for Phase 12. "
            "Currently a palette placeholder."
        )
```

**h. Acceptance criteria**:

- [ ] Class exists with correct ClassVars.
- [ ] `process_item` raises `NotImplementedError`.
- [ ] Block in `get_blocks()`.

**i. Out of scope**: All actual tracking algorithms.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~50 src + ~50 tests. **Small**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-023 TrackObjects placeholder for Phase 12`


---

### T-IMG-024 — RegionProps

**Status**: Implemented in issue #376's measurement bundle. The live
repository skeleton uses the singular `label` / `intensity_image`
ports and publishes a `properties` `DataFrame`; the landed
implementation follows that surface, emits `label_id` first, and
concatenates collection inputs into one table with `image_index`. The
measurement behavior is covered in
`packages/scieasy-blocks-imaging/tests/test_continuation_b_skeletons.py`
plus the top-level imaging plugin smoke.

**a. Ticket ID and name**: T-IMG-024 — `RegionProps` block.

**b. Source ADR sections**: ADR-027 D2 (DataFrame output), ADR-020 (Collection); Q-IMG-12.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/measurement/region_props.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/measurement/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_measurement/test_region_props.py`
  - `test_region_props_area_basic`
  - `test_region_props_multiple_properties_selected`
  - `test_region_props_with_intensity_image`
  - `test_region_props_collection_input_emits_image_index_column`
  - `test_region_props_collection_intensity_length_mismatch_raises`
  - `test_region_props_label_id_column_first`
  - `test_region_props_invalid_property_raises`
  - `test_region_props_eccentricity_for_non_2d_raises`
  - `test_region_props_dataframe_round_trip`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

import pandas as pd

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.collection import Collection
from scieasy.core.types.dataframe import DataFrame

from scieasy_blocks_imaging.types import Image, Label


_ALLOWED_PROPS = {
    "area", "perimeter", "eccentricity", "bbox", "centroid",
    "mean_intensity", "max_intensity", "min_intensity", "std_intensity",
    "integrated_intensity", "equivalent_diameter", "orientation",
    "major_axis_length", "minor_axis_length", "solidity",
    "convex_area", "extent",
}


class RegionProps(ProcessBlock):
    """Compute per-region statistics from a Label (or Collection[Label])."""

    type_name: ClassVar[str] = "imaging.region_props"
    name: ClassVar[str] = "Region Properties"
    category: ClassVar[str] = "measurement"
    algorithm: ClassVar[str] = "region_props"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="labels", accepted_types=[Label, Collection[Label]]),
        InputPort(name="intensity_image",
                  accepted_types=[Image, Collection[Image]],
                  required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="table", accepted_types=[DataFrame]),
    ]

    config_schema = {
        "properties": {
            "properties": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(_ALLOWED_PROPS)},
                "default": ["area", "centroid", "mean_intensity"],
                "ui_widget": "multi_select",
            },
        },
    }

    def run(self, inputs, config):
        from skimage.measure import regionprops_table

        labels = inputs["labels"]
        intensity = inputs.get("intensity_image")
        props = config.get("properties",
                           ["area", "centroid", "mean_intensity"])
        for p in props:
            if p not in _ALLOWED_PROPS:
                raise ValueError(f"Unknown property: {p}")

        if isinstance(labels, Collection):
            if intensity is not None and len(intensity) != len(labels):
                raise ValueError(
                    f"Collection length mismatch: {len(labels)} labels vs "
                    f"{len(intensity)} intensity images"
                )
            frames = []
            for i, lab in enumerate(labels):
                int_img = intensity[i] if intensity is not None else None
                df = self._props_one(lab, int_img, props)
                df.insert(0, "image_index", i)
                frames.append(df)
            df_all = pd.concat(frames, ignore_index=True)
        else:
            df_all = self._props_one(labels, intensity, props)
        return DataFrame(data=df_all)

    def _props_one(self, lab, intensity, props):
        from skimage.measure import regionprops_table
        raster = lab.slots["raster"]
        labels_arr = raster.to_memory() if raster.storage_ref else raster._data
        intensity_arr = None
        if intensity is not None:
            intensity_arr = (intensity.to_memory()
                             if intensity.storage_ref
                             else intensity._data)
        # skimage's intensity_image arg requires shape match; if 5D, take 2D
        if intensity_arr is not None and intensity_arr.ndim > labels_arr.ndim:
            intensity_arr = intensity_arr[..., :labels_arr.shape[-2], :labels_arr.shape[-1]]
        table = regionprops_table(
            labels_arr, intensity_image=intensity_arr,
            properties=("label",) + tuple(props),
        )
        df = pd.DataFrame(table)
        df.rename(columns={"label": "label_id"}, inplace=True)
        cols = ["label_id"] + [c for c in df.columns if c != "label_id"]
        return df[cols]
```

**h. Acceptance criteria**:

- [ ] `RegionProps` is `ProcessBlock` with correct ClassVars.
- [ ] `properties` config is a multi-select list of strings from
      `_ALLOWED_PROPS`.
- [ ] Single `Label` input → DataFrame with one row per label, columns
      including `label_id`.
- [ ] `Collection[Label]` input → DataFrame with `image_index`
      column prepended.
- [ ] Collection length mismatch (labels vs intensity) → `ValueError`.
- [ ] Optional `intensity_image` adds intensity columns.
- [ ] Invalid property name → `ValueError`.
- [ ] Output DataFrame round-trips.

**i. Out of scope**: 3D region props (skimage 3D path is supported but the property list is restricted to 2D-friendly subset in 0.1.0).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~250 src + ~350 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-024 RegionProps with multi-select property list`

---

### T-IMG-025 — PairwiseDistance

**Status**: Implemented in issue #376's measurement bundle. The live
repository skeleton narrows this block to a single `label` input and a
`metric` enum of `centroid` / `edge`; the landed implementation keeps
that contract, returns a long-format `DataFrame`
(`label_id_a` / `label_id_b` / `distance`), and respects the optional
`max_distance` cutoff. Coverage lives in the continuation-B imaging
tests and the imaging plugin smoke.

**a. Ticket ID and name**: T-IMG-025 — `PairwiseDistance` block.

**b. Source ADR sections**: ADR-027 D2 (DataFrame output).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/measurement/pairwise_distance.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/measurement/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_measurement/test_pairwise_distance.py`
  - `test_pairwise_euclidean_all_pairs`
  - `test_pairwise_chessboard_all_pairs`
  - `test_pairwise_manhattan_all_pairs`
  - `test_pairwise_nearest_mode`
  - `test_pairwise_dataframe_columns_source_target_distance`
  - `test_pairwise_invalid_metric_raises`
  - `test_pairwise_invalid_mode_raises`
  - `test_pairwise_empty_labels_returns_empty_dataframe`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

import numpy as np
import pandas as pd

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.dataframe import DataFrame

from scieasy_blocks_imaging.types import Label


class PairwiseDistance(ProcessBlock):
    """Pairwise distance between two label sets.

    Use case: distance from each immune cell (source labels) to the
    nearest cancer cell (target labels) for tumour-microenvironment
    analyses.
    """

    type_name: ClassVar[str] = "imaging.pairwise_distance"
    name: ClassVar[str] = "Pairwise Distance"
    category: ClassVar[str] = "measurement"
    algorithm: ClassVar[str] = "pairwise_distance"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="source_labels", accepted_types=[Label]),
        InputPort(name="target_labels", accepted_types=[Label]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="distances", accepted_types=[DataFrame]),
    ]

    config_schema = {
        "properties": {
            "metric": {"type": "string",
                       "enum": ["euclidean", "chessboard", "manhattan"],
                       "default": "euclidean"},
            "mode": {"type": "string",
                     "enum": ["all_pairs", "nearest"],
                     "default": "nearest"},
        },
    }

    def run(self, inputs, config):
        from skimage.measure import regionprops
        src = inputs["source_labels"]
        tgt = inputs["target_labels"]
        metric = config.get("metric", "euclidean")
        mode = config.get("mode", "nearest")

        src_arr = src.slots["raster"].to_memory() if src.slots["raster"].storage_ref else src.slots["raster"]._data
        tgt_arr = tgt.slots["raster"].to_memory() if tgt.slots["raster"].storage_ref else tgt.slots["raster"]._data
        src_centroids = [(p.label, p.centroid) for p in regionprops(src_arr)]
        tgt_centroids = [(p.label, p.centroid) for p in regionprops(tgt_arr)]

        rows = []
        for s_id, s_c in src_centroids:
            if mode == "all_pairs":
                for t_id, t_c in tgt_centroids:
                    rows.append({"source_id": s_id, "target_id": t_id,
                                 "distance": _dist(s_c, t_c, metric)})
            else:
                if not tgt_centroids:
                    continue
                dists = [(t_id, _dist(s_c, t_c, metric))
                         for t_id, t_c in tgt_centroids]
                t_id, d = min(dists, key=lambda x: x[1])
                rows.append({"source_id": s_id, "target_id": t_id, "distance": d})
        return DataFrame(data=pd.DataFrame(rows))


def _dist(a, b, metric):
    a, b = np.array(a), np.array(b)
    if metric == "euclidean":
        return float(np.linalg.norm(a - b))
    if metric == "chessboard":
        return float(np.max(np.abs(a - b)))
    if metric == "manhattan":
        return float(np.sum(np.abs(a - b)))
    raise ValueError(f"Unknown metric: {metric}")
```

**h. Acceptance criteria**:

- [ ] Three metrics work.
- [ ] Two modes work.
- [ ] Output DataFrame has columns `source_id`, `target_id`,
      `distance`.
- [ ] Invalid metric/mode → `ValueError`.
- [ ] Empty source or target → empty DataFrame (no error).

**i. Out of scope**: 3D distances (works because centroids are tuples but not extensively tested in 0.1.0).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~150 src + ~200 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-025 PairwiseDistance for source/target label distance analysis`

---

### T-IMG-026 — Colocalization

**Status**: Implemented in issue #376's measurement bundle. The live
repository skeleton uses `channel_a` / `channel_b` / `mask` inputs and
a `metrics` list of `pearson` / `manders` / `costes`; the landed block
keeps those names, validates collection pairing, and emits a
measurement `DataFrame` with optional `image_index` when collections
are provided. Tests now cover masked Pearson and Manders behavior, and
the imaging plugin smoke confirms export wiring on `main`.

**a. Ticket ID and name**: T-IMG-026 — `Colocalization` block.

**b. Source ADR sections**: ADR-027 D2, D3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/measurement/colocalization.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/measurement/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_measurement/test_colocalization.py`
  - `test_coloc_pearson_basic`
  - `test_coloc_manders_m1_m2`
  - `test_coloc_icq_range`
  - `test_coloc_costes_threshold`
  - `test_coloc_with_mask`
  - `test_coloc_threshold_method_mean_zero_otsu`
  - `test_coloc_invalid_method_raises`
  - `test_coloc_dataframe_round_trip`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

import numpy as np
import pandas as pd

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.dataframe import DataFrame

from scieasy_blocks_imaging.types import Image, Mask


class Colocalization(ProcessBlock):
    type_name: ClassVar[str] = "imaging.colocalization"
    name: ClassVar[str] = "Colocalization"
    category: ClassVar[str] = "measurement"
    algorithm: ClassVar[str] = "colocalization"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="ch1", accepted_types=[Image]),
        InputPort(name="ch2", accepted_types=[Image]),
        InputPort(name="mask", accepted_types=[Mask], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="stats", accepted_types=[DataFrame]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["pearson", "manders", "ICQ", "costes"],
                       "default": "pearson"},
            "threshold_method": {"type": "string",
                                 "enum": ["mean", "zero", "otsu"],
                                 "default": "mean"},
        },
    }

    def run(self, inputs, config):
        ch1 = inputs["ch1"]
        ch2 = inputs["ch2"]
        mask = inputs.get("mask")
        method = config.get("method", "pearson")
        threshold_method = config.get("threshold_method", "mean")

        a = ch1.to_memory() if ch1.storage_ref else ch1._data
        b = ch2.to_memory() if ch2.storage_ref else ch2._data
        m = (mask.to_memory() if mask and mask.storage_ref
             else (mask._data if mask else None))

        if m is not None:
            a = a[m]
            b = b[m]

        if method == "pearson":
            r = float(np.corrcoef(a.flatten(), b.flatten())[0, 1])
            df = pd.DataFrame([{"metric": "pearson_r", "value": r}])
        elif method == "manders":
            t1, t2 = _threshold(a, threshold_method), _threshold(b, threshold_method)
            m1 = float(a[(a > t1) & (b > t2)].sum() / a[a > t1].sum()) if a[a > t1].sum() else 0.0
            m2 = float(b[(b > t2) & (a > t1)].sum() / b[b > t2].sum()) if b[b > t2].sum() else 0.0
            df = pd.DataFrame([
                {"metric": "manders_M1", "value": m1},
                {"metric": "manders_M2", "value": m2},
            ])
        elif method == "ICQ":
            ma, mb = a.mean(), b.mean()
            icq = float(((a > ma) == (b > mb)).mean() - 0.5)
            df = pd.DataFrame([{"metric": "ICQ", "value": icq}])
        elif method == "costes":
            # simplified Costes thresholding
            df = pd.DataFrame([{"metric": "costes", "value": 0.0}])
        else:
            raise ValueError(f"Unknown coloc method: {method}")
        return DataFrame(data=df)


def _threshold(arr, method):
    if method == "mean":
        return arr.mean()
    if method == "zero":
        return 0.0
    if method == "otsu":
        from skimage.filters import threshold_otsu
        return threshold_otsu(arr)
    raise ValueError(f"Unknown threshold method: {method}")
```

**h. Acceptance criteria**:

- [ ] Four methods produce DataFrames.
- [ ] Optional `mask` restricts the analysis region.
- [ ] Three threshold methods work for Manders.
- [ ] Invalid method → `ValueError`.

**i. Out of scope**: Per-cell colocalization (use `Colocalization` after `RegionProps` segmentation).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~250 src + ~250 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-026 Colocalization (pearson / manders / ICQ / costes)`

---

### T-IMG-027 — ComputeRegistration

**Status**: Implemented in issue #386. `ComputeRegistration` now supports the
locked `phase_correlation` / `rigid` / `affine` skeleton methods, emits typed
`Transform` outputs, and is covered by package-local registration tests plus the
top-level imaging finish smoke test.

**a. Ticket ID and name**: T-IMG-027 — `ComputeRegistration` block.

**b. Source ADR sections**: ADR-027 D2 (Transform output), D3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/registration/compute_registration.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/registration/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_registration/test_compute_registration.py`
  - `test_phase_correlation_recovers_translation`
  - `test_orb_method`
  - `test_sift_method`
  - `test_ecc_method`
  - `test_optical_flow_method`
  - `test_multiresolution_param`
  - `test_invalid_method_raises`
  - `test_output_is_transform_with_correct_axes`
  - `test_transform_meta_transform_type_set`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock

from scieasy_blocks_imaging.types import Image, Transform


class ComputeRegistration(ProcessBlock):
    type_name: ClassVar[str] = "imaging.compute_registration"
    name: ClassVar[str] = "Compute Registration"
    category: ClassVar[str] = "registration"
    algorithm: ClassVar[str] = "compute_registration"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="moving", accepted_types=[Image]),
        InputPort(name="fixed", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="transform", accepted_types=[Transform]),
    ]

    config_schema = {
        "properties": {
            "method": {"type": "string",
                       "enum": ["phase_correlation", "ORB", "SIFT", "ECC",
                                "optical_flow"],
                       "default": "phase_correlation"},
            "multiresolution": {"type": "boolean", "default": False},
        },
    }

    def run(self, inputs, config):
        from skimage.registration import phase_cross_correlation
        moving = inputs["moving"]
        fixed = inputs["fixed"]
        method = config.get("method", "phase_correlation")

        m = moving.to_memory() if moving.storage_ref else moving._data
        f = fixed.to_memory() if fixed.storage_ref else fixed._data

        if method == "phase_correlation":
            shift, _, _ = phase_cross_correlation(f, m)
            mat = np.array([[1.0, 0.0, shift[1]],
                            [0.0, 1.0, shift[0]]], dtype=np.float64)
        else:
            # ORB / SIFT / ECC / optical_flow paths
            mat = np.eye(2, 3, dtype=np.float64)

        t = Transform(
            axes=["row", "col"], shape=mat.shape, dtype=mat.dtype,
            framework=fixed.framework.derive(),
            meta=Transform.Meta(transform_type="affine",
                                reference_shape=tuple(f.shape)),
        )
        t._data = mat
        return t
```

**h. Acceptance criteria**:

- [ ] Five methods supported.
- [ ] `phase_correlation` recovers known translations.
- [ ] Output is `Transform` with `axes=["row","col"]`, shape `(2,3)`.
- [ ] `Transform.Meta.transform_type` set.
- [ ] `Transform.Meta.reference_shape` set to fixed image shape.
- [ ] Invalid method → `ValueError`.

**i. Out of scope**: Non-rigid / deformable registration (Phase 12).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~200 src + ~250 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-027 ComputeRegistration (phase_correlation / ORB / SIFT / ECC / optical_flow)`

---

### T-IMG-028 — ApplyTransform

**Status**: Implemented in issue #386. `ApplyTransform` now applies typed
affine transforms to `Image` inputs, validates interpolation and
transform-shape constraints, and is covered by focused registration tests.

**a. Ticket ID and name**: T-IMG-028 — `ApplyTransform` block.

**b. Source ADR sections**: ADR-027 D3, D5.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/registration/apply_transform.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/registration/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_registration/test_apply_transform.py`
  - `test_apply_transform_2d_affine_translation`
  - `test_apply_transform_preserves_shape_when_preserve_range`
  - `test_apply_transform_interpolation_param`
  - `test_apply_transform_3d_input_iterates_per_z`
  - `test_apply_transform_invalid_transform_shape_raises`
  - `test_apply_transform_round_trip_with_compute_registration`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes

from scieasy_blocks_imaging.types import Image, Transform


class ApplyTransform(ProcessBlock):
    type_name: ClassVar[str] = "imaging.apply_transform"
    name: ClassVar[str] = "Apply Transform"
    category: ClassVar[str] = "registration"
    algorithm: ClassVar[str] = "apply_transform"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
        InputPort(name="transform", accepted_types=[Transform]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "interpolation": {"type": "string",
                              "enum": ["nearest", "bilinear", "bicubic"],
                              "default": "bilinear"},
            "preserve_range": {"type": "boolean", "default": True},
        },
    }

    def run(self, inputs, config):
        from skimage.transform import warp, AffineTransform
        image = inputs["image"]
        tform_obj = inputs["transform"]
        interp = config.get("interpolation", "bilinear")
        order = {"nearest": 0, "bilinear": 1, "bicubic": 3}[interp]
        preserve = config.get("preserve_range", True)

        mat = tform_obj.to_memory() if tform_obj.storage_ref else tform_obj._data
        if mat.shape not in {(2, 3), (3, 3)}:
            raise ValueError(f"Transform shape {mat.shape} unsupported; "
                             f"expected (2,3) or (3,3)")
        T = AffineTransform(matrix=mat if mat.shape == (3, 3)
                            else _to_3x3(mat))

        fn = lambda s, c: warp(s, T.inverse, order=order, preserve_range=preserve)
        return iterate_over_axes(image, {"y", "x"}, fn)


def _to_3x3(mat):
    import numpy as np
    out = np.eye(3, dtype=mat.dtype)
    out[:2, :] = mat
    return out
```

**h. Acceptance criteria**:

- [ ] `ApplyTransform` is `ProcessBlock`.
- [ ] 2D affine (2,3) and 3D affine (3,3) both supported.
- [ ] Three interpolation modes work.
- [ ] N-D inputs iterate per `(y, x)` slice.
- [ ] Invalid transform shape → `ValueError`.

**i. Out of scope**: Non-affine warps (Phase 12).

**j. Dependencies on other tickets**: T-IMG-001, T-IMG-027.

**k. Estimated diff size**: ~150 src + ~200 tests. **Small-Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-028 ApplyTransform with interpolation and preserve_range`

---

### T-IMG-029 — RegisterSeries

**Status**: Implemented in issue #386. `RegisterSeries` now registers
collection or stack inputs against a selected reference frame along the locked
axis contract and returns registered images plus transform collections.

**a. Ticket ID and name**: T-IMG-029 — `RegisterSeries` block.

**b. Source ADR sections**: ADR-027 D3, D5, D2 (multi-output).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/registration/register_series.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/registration/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_registration/test_register_series.py`
  - `test_register_series_first_reference`
  - `test_register_series_middle_reference`
  - `test_register_series_mean_reference`
  - `test_register_series_returns_two_outputs`
  - `test_register_series_transforms_collection_length_matches`
  - `test_register_series_invalid_reference_raises`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.collection import Collection

from scieasy_blocks_imaging.types import Image, Transform


class RegisterSeries(ProcessBlock):
    """Register a time-series (or z-stack) to a reference frame.

    Returns the registered series + a Collection[Transform] of length
    equal to the number of frames.
    """

    type_name: ClassVar[str] = "imaging.register_series"
    name: ClassVar[str] = "Register Series"
    category: ClassVar[str] = "registration"
    algorithm: ClassVar[str] = "register_series"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="registered", accepted_types=[Image]),
        OutputPort(name="transforms", accepted_types=[Collection[Transform]]),
    ]

    config_schema = {
        "properties": {
            "reference_frame": {"type": "string",
                                "enum": ["first", "middle", "mean"],
                                "default": "first"},
            "method": {"type": "string",
                       "enum": ["phase_correlation", "ORB", "SIFT", "ECC"],
                       "default": "phase_correlation"},
            "axis": {"type": "string", "enum": ["t", "z"], "default": "t"},
        },
    }

    def run(self, inputs, config):
        # ... iterate per frame, register against reference, build
        # registered series + transforms collection
        pass
```

**h. Acceptance criteria**:

- [ ] Three reference modes work.
- [ ] Two outputs returned (registered series + transforms collection).
- [ ] Transforms collection length matches frame count.
- [ ] Invalid reference → `ValueError`.

**i. Out of scope**: Block-wise feature tracking; non-rigid series registration.

**j. Dependencies on other tickets**: T-IMG-001, T-IMG-027, T-IMG-028.

**k. Estimated diff size**: ~250 src + ~250 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-029 RegisterSeries with first/middle/mean reference`

---

### T-IMG-030 — AxisProjection / SelectSlice

**Status**: Implemented in issue #386. `AxisProjection` and `SelectSlice` now
support the locked axis operations from the skeleton, including metadata cleanup
when projecting channel or wavelength axes.

**a. Ticket ID and name**: T-IMG-030 — `AxisProjection` and `SelectSlice`.

**b. Source ADR sections**: ADR-027 D1 (axes), D4 (`sel`), D5; Q-IMG-3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/axis/projection.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/axis/select_slice.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/axis/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_axis/test_projection.py`
  - `test_projection_max_along_z`
  - `test_projection_mean_along_t`
  - `test_projection_sum_along_c`
  - `test_projection_std_min_median`
  - `test_projection_drops_projected_axis`
  - `test_projection_invalid_axis_raises`
  - `test_projection_meta_channels_cleared_when_c_projected`
- `tests/test_axis/test_select_slice.py`
  - `test_select_slice_int_index_drops_axis`
  - `test_select_slice_slice_object_keeps_axis`
  - `test_select_slice_invalid_axis_raises`
  - `test_select_slice_out_of_bounds_raises`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# axis/projection.py
from __future__ import annotations
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock

from scieasy_blocks_imaging.types import Image


class AxisProjection(ProcessBlock):
    type_name: ClassVar[str] = "imaging.axis_projection"
    name: ClassVar[str] = "Axis Projection"
    category: ClassVar[str] = "axis"
    algorithm: ClassVar[str] = "axis_projection"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "axis": {"type": "string",
                     "enum": ["t", "z", "c", "lambda", "y", "x"]},
            "method": {"type": "string",
                       "enum": ["max", "mean", "sum", "std", "min", "median"],
                       "default": "max"},
        },
        "required": ["axis", "method"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        axis = config["axis"]
        method = config["method"]
        if axis not in item.axes:
            raise ValueError(f"axis {axis!r} not in image axes {item.axes}")
        idx = item.axes.index(axis)
        data = item.to_memory() if item.storage_ref else item._data
        fn = {"max": np.max, "mean": np.mean, "sum": np.sum,
              "std": np.std, "min": np.min, "median": np.median}[method]
        out = fn(data, axis=idx)
        new_axes = [a for a in item.axes if a != axis]
        # Q-IMG-3: clear channel-related fields if projecting c or lambda
        new_meta = item.meta
        if axis in ("c", "lambda") and item.meta:
            update = {}
            if axis == "c":
                update["channels"] = None
            if axis == "lambda":
                update["wavelengths_nm"] = None
            new_meta = item.meta.model_copy(update=update)
        new_img = Image(
            axes=new_axes, shape=out.shape, dtype=out.dtype,
            framework=item.framework.derive(),
            meta=new_meta, user=dict(item.user),
        )
        new_img._data = out
        return new_img


# axis/select_slice.py

class SelectSlice(ProcessBlock):
    """Slice an image along one axis with int (drops axis) or slice (keeps)."""

    type_name: ClassVar[str] = "imaging.select_slice"
    name: ClassVar[str] = "Select Slice"
    category: ClassVar[str] = "axis"
    algorithm: ClassVar[str] = "select_slice"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "axis": {"type": "string"},
            "index": {"type": ["integer", "string"],
                      "description": "int or slice spec like '5:10'"},
        },
        "required": ["axis", "index"],
    }

    def process_item(self, item: Image, config, state=None) -> Image:
        axis = config["axis"]
        index = config["index"]
        # parse slice strings like "5:10" into slice objects
        if isinstance(index, str) and ":" in index:
            parts = [int(x) if x else None for x in index.split(":")]
            sel_arg = slice(*parts)
        else:
            sel_arg = int(index)
        return item.sel(**{axis: sel_arg})
```

**h. Acceptance criteria**:

- [ ] `AxisProjection`: six methods work.
- [ ] Projecting an axis drops it from output `axes`.
- [ ] Projecting `c`/`lambda` clears the corresponding meta field
      (Q-IMG-3).
- [ ] Invalid axis → `ValueError`.
- [ ] `SelectSlice` int index drops the axis.
- [ ] `SelectSlice` slice spec keeps the axis.
- [ ] `SelectSlice` invalid axis → `ValueError`.
- [ ] `SelectSlice` out-of-bounds → `IndexError` (from `Array.sel`).

**i. Out of scope**: Multi-axis projection in one call (chain two blocks).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~250 src + ~300 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-030 AxisProjection and SelectSlice`

---

### T-IMG-031 — Math scalar bundle (AddScalar / SubtractScalar / MultiplyScalar / DivideScalar)

**Status**: Implemented in issue #386. The scalar bundle now performs concrete
NumPy arithmetic with dtype preservation and explicit divide-by-zero handling.

**a. Ticket ID and name**: T-IMG-031 — Math scalar bundle.

**b. Source ADR sections**: ADR-027 D3.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/math/scalar_ops.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/math/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_math/test_scalar_ops.py`
  - `test_add_scalar`
  - `test_subtract_scalar`
  - `test_multiply_scalar`
  - `test_divide_scalar`
  - `test_divide_scalar_by_zero_raises`
  - `test_divide_scalar_with_epsilon_safe`
  - `test_scalar_ops_preserve_axes_meta`
  - `test_scalar_ops_5d_broadcast`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes

from scieasy_blocks_imaging.types import Image


def _make_scalar_block(name_str, type_name_str, op_fn):
    class ScalarBlock(ProcessBlock):
        type_name: ClassVar[str] = type_name_str
        name: ClassVar[str] = name_str
        category: ClassVar[str] = "math"
        algorithm: ClassVar[str] = type_name_str.split(".")[-1]

        input_ports: ClassVar[list[InputPort]] = [
            InputPort(name="image", accepted_types=[Image]),
        ]
        output_ports: ClassVar[list[OutputPort]] = [
            OutputPort(name="image", accepted_types=[Image]),
        ]

        config_schema = {
            "properties": {
                "value": {"type": "number"},
            },
            "required": ["value"],
        }

        def process_item(self, item, config, state=None):
            value = config["value"]
            return iterate_over_axes(item, {"y", "x"},
                                     lambda s, c: op_fn(s, value))
    return ScalarBlock


AddScalar = _make_scalar_block("Add Scalar", "imaging.add_scalar",
                                lambda s, v: s + v)
SubtractScalar = _make_scalar_block("Subtract Scalar", "imaging.subtract_scalar",
                                     lambda s, v: s - v)
MultiplyScalar = _make_scalar_block("Multiply Scalar", "imaging.multiply_scalar",
                                     lambda s, v: s * v)


class DivideScalar(ProcessBlock):
    type_name: ClassVar[str] = "imaging.divide_scalar"
    name: ClassVar[str] = "Divide Scalar"
    category: ClassVar[str] = "math"
    algorithm: ClassVar[str] = "divide_scalar"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "value": {"type": "number"},
            "epsilon": {"type": "number", "default": 1e-9},
        },
        "required": ["value"],
    }

    def process_item(self, item, config, state=None):
        value = config["value"]
        eps = config.get("epsilon", 1e-9)
        if value == 0 and eps == 0:
            raise ValueError("DivideScalar: value=0 and epsilon=0")
        return iterate_over_axes(item, {"y", "x"},
                                 lambda s, c: s / (value + eps))
```

**h. Acceptance criteria**:

- [ ] Four blocks: `AddScalar`, `SubtractScalar`, `MultiplyScalar`,
      `DivideScalar`.
- [ ] Each works on 2D inputs.
- [ ] `DivideScalar` `epsilon` param prevents div-by-zero.
- [ ] `DivideScalar` with `value=0` and `epsilon=0` raises.
- [ ] All four broadcast over 5D inputs.
- [ ] All four preserve axes/meta.

**i. Out of scope**: Per-channel scalar with a vector value (use `ImageCalculator`).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~150 src + ~200 tests. **Small-Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-031 Math scalar bundle (AddScalar/SubtractScalar/MultiplyScalar/DivideScalar)`

---

### T-IMG-032 — ImageCalculator

**Status**: Implemented in issue #386. `ImageCalculator` now evaluates the
locked two-port expression contract with AST validation, shape and axes checks,
and collection broadcasting support.

**a. Ticket ID and name**: T-IMG-032 — `ImageCalculator` block.

**b. Source ADR sections**: ADR-027 D3, ADR-029 (informational, variadic deferred); Q-IMG-5.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/math/image_calculator.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/math/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_math/test_image_calculator.py`
  - `test_image_calculator_add_two_images`
  - `test_image_calculator_subtract`
  - `test_image_calculator_multiply`
  - `test_image_calculator_divide_with_epsilon`
  - `test_image_calculator_expression_a_minus_b`
  - `test_image_calculator_expression_fret_ratio`
  - `test_image_calculator_expression_invalid_variable_raises`
  - `test_image_calculator_expression_with_function_call_raises`
  - `test_image_calculator_expression_with_import_raises`
  - `test_image_calculator_shape_mismatch_raises`
  - `test_image_calculator_5d_inputs_iterate`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
import ast
from typing import ClassVar
import numpy as np

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock

from scieasy_blocks_imaging.types import Image


class ImageCalculator(ProcessBlock):
    """Two-input image arithmetic.

    For 0.1.0, fixed two ports A and B (Q-IMG-5). When ADR-029 lands,
    this block will be the first variadic-port consumer.
    """

    type_name: ClassVar[str] = "imaging.image_calculator"
    name: ClassVar[str] = "Image Calculator"
    category: ClassVar[str] = "math"
    algorithm: ClassVar[str] = "image_calculator"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="a", accepted_types=[Image]),
        InputPort(name="b", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema = {
        "properties": {
            "operation": {"type": "string",
                          "enum": ["add", "subtract", "multiply", "divide",
                                   "expression"],
                          "default": "add"},
            "expression": {"type": "string",
                           "description": "e.g. '(a - b) / (a + b)' for FRET ratio"},
            "epsilon": {"type": "number", "default": 1e-9},
        },
        "required": ["operation"],
    }

    def run(self, inputs, config):
        a = inputs["a"]
        b = inputs["b"]
        op = config["operation"]
        eps = config.get("epsilon", 1e-9)

        a_data = a.to_memory() if a.storage_ref else a._data
        b_data = b.to_memory() if b.storage_ref else b._data
        if a_data.shape != b_data.shape:
            raise ValueError(
                f"ImageCalculator: shape mismatch {a_data.shape} vs {b_data.shape}"
            )
        if op == "add":
            out = a_data + b_data
        elif op == "subtract":
            out = a_data - b_data
        elif op == "multiply":
            out = a_data * b_data
        elif op == "divide":
            out = a_data / (b_data + eps)
        elif op == "expression":
            expr = config.get("expression")
            if not expr:
                raise ValueError("operation=expression requires 'expression'")
            tree = ast.parse(expr, mode="eval")
            _validate_expression_ast(tree)
            out = eval(  # nosec - validated by AST whitelist
                compile(tree, "<expr>", "eval"),
                {"__builtins__": {}},
                {"a": a_data, "b": b_data},
            )
        else:
            raise ValueError(f"Unknown operation: {op}")

        new_img = Image(
            axes=list(a.axes), shape=out.shape, dtype=out.dtype,
            framework=a.framework.derive(),
            meta=a.meta, user=dict(a.user),
        )
        new_img._data = out
        return new_img


_ALLOWED_VARS = {"a", "b"}


def _validate_expression_ast(tree: ast.AST) -> None:
    """AST whitelist: arithmetic ops + a/b vars + numeric literals only."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Num, ast.Constant,
                             ast.BinOp, ast.UnaryOp, ast.UAdd, ast.USub,
                             ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
                             ast.Load)):
            continue
        if isinstance(node, ast.Name):
            if node.id not in _ALLOWED_VARS:
                raise ValueError(
                    f"ImageCalculator expression: unknown variable {node.id!r}, "
                    f"allowed: {sorted(_ALLOWED_VARS)}"
                )
            continue
        raise ValueError(
            f"ImageCalculator expression: forbidden node "
            f"{type(node).__name__} (only +, -, *, /, **, parens, "
            f"variables a/b, and numeric literals allowed)"
        )
```

**h. Acceptance criteria**:

- [ ] Two fixed input ports `a` and `b` (Q-IMG-5).
- [ ] Five operations supported.
- [ ] `expression` mode requires `expression` config field.
- [ ] AST whitelist rejects function calls, imports, attribute
      access.
- [ ] AST whitelist rejects unknown variables (only `a` and `b`).
- [ ] Shape mismatch → `ValueError`.
- [ ] FRET ratio expression `(a - b) / (a + b)` works.
- [ ] Divide-by-zero protected by `epsilon`.

**i. Out of scope**: Variadic ports (deferred to ADR-029 / Phase 12).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~250 src + ~300 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-032 ImageCalculator with expression-mode AST whitelist`

---

### T-IMG-033 — Visualization bundle (RenderPseudoColor / RenderOverlay / RenderMontage / RenderMovie / RenderHistogram)

**Status**: Implemented in issue #386. The visualization bundle now renders
static and movie artifacts through the locked block surface, with optional
dependency gating in tests where `matplotlib` is required.

**a. Ticket ID and name**: T-IMG-033 — Visualization bundle.

**b. Source ADR sections**: ADR-027 D2 (Artifact output).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/visualization/pseudo_color.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/visualization/overlay.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/visualization/montage.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/visualization/movie.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/visualization/histogram.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/visualization/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_visualization/test_pseudo_color.py`
  - `test_pseudocolor_viridis_returns_artifact`
  - `test_pseudocolor_with_vmin_vmax`
  - `test_pseudocolor_percentile_clip`
  - `test_pseudocolor_invalid_cmap_raises`
- `tests/test_visualization/test_overlay.py`
  - `test_overlay_label_basic`
  - `test_overlay_mask_basic`
  - `test_overlay_contour_only_param`
  - `test_overlay_alpha_param`
- `tests/test_visualization/test_montage.py`
  - `test_montage_collection_to_artifact`
  - `test_montage_rows_cols_layout`
  - `test_montage_with_labels`
- `tests/test_visualization/test_movie.py`
  - `test_movie_t_axis_to_mp4`
  - `test_movie_fps_param`
  - `test_movie_z_axis_to_gif`
- `tests/test_visualization/test_histogram.py`
  - `test_histogram_returns_artifact`
  - `test_histogram_bins_param`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# visualization/pseudo_color.py
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from typing import ClassVar

from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.artifact import Artifact

from scieasy_blocks_imaging.types import Image


_VALID_CMAPS = {"viridis", "plasma", "magma", "inferno", "gray", "hot"}


class RenderPseudoColor(ProcessBlock):
    type_name: ClassVar[str] = "imaging.render_pseudo_color"
    name: ClassVar[str] = "Render Pseudo Color"
    category: ClassVar[str] = "visualization"
    algorithm: ClassVar[str] = "render_pseudo_color"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="artifact", accepted_types=[Artifact]),
    ]

    config_schema = {
        "properties": {
            "cmap": {"type": "string",
                     "enum": sorted(_VALID_CMAPS), "default": "viridis"},
            "vmin": {"type": "number"},
            "vmax": {"type": "number"},
            "percentile_clip": {"type": "number", "default": 0.0},
        },
    }

    def process_item(self, item: Image, config, state=None) -> Artifact:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        cmap = config.get("cmap", "viridis")
        if cmap not in _VALID_CMAPS:
            raise ValueError(f"Unknown cmap: {cmap}")
        data = item.to_memory() if item.storage_ref else item._data
        if data.ndim > 2:
            slc = tuple(s // 2 for s in data.shape[:-2]) + (slice(None), slice(None))
            data = data[slc]
        vmin = config.get("vmin")
        vmax = config.get("vmax")
        pct = config.get("percentile_clip", 0.0)
        if pct > 0 and (vmin is None or vmax is None):
            vmin = float(np.percentile(data, pct))
            vmax = float(np.percentile(data, 100 - pct))
        fig, ax = plt.subplots()
        ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax)
        ax.axis("off")
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        out = Path("rendered.png")  # framework will redirect via storage backend
        out.write_bytes(buf.getvalue())
        return Artifact(file_path=out, mime_type="image/png")


# Similar simplified pseudocode for overlay/montage/movie/histogram
```

**h. Acceptance criteria**:

- [ ] All five blocks present.
- [ ] Each returns `Artifact` with appropriate mime type.
- [ ] `RenderPseudoColor` six cmaps, `vmin`/`vmax`/`percentile_clip`.
- [ ] `RenderOverlay` accepts `Image` + `Mask`/`Label`, alpha and
      `contour_only` params.
- [ ] `RenderMontage` arranges `Collection[Image]` in rows × cols.
- [ ] `RenderMovie` produces MP4 (default) or GIF (when path ends
      `.gif`).
- [ ] `RenderHistogram` produces a histogram PNG with `bins` param.

**i. Out of scope**: 3D volume rendering; interactive plots.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~600 src + ~500 tests. **Large**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-033 Visualization bundle (PseudoColor/Overlay/Montage/Movie/Histogram)`


---

### T-IMG-034 — FijiBlock

**Status**: Implemented in issue #386. `FijiBlock` now uses the AppBlock
file-exchange protocol, supports the locked Fiji executable override, and is
covered by fake-binary exchange tests.

**a. Ticket ID and name**: T-IMG-034 — `FijiBlock` AppBlock subclass.

**b. Source ADR sections**: ADR-019 (AppBlock + ProcessHandle + FileWatcher), ADR-020 (Collection).

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/interactive/fiji_block.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/interactive/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_interactive/test_fiji_block.py` (marker:
  `@pytest.mark.requires_fiji`)
  - `test_fiji_class_exists_in_palette`
  - `test_fiji_app_command_default_path`
  - `test_fiji_app_command_configurable`
  - `test_fiji_macro_path_required_when_present`
  - `test_fiji_input_collection_image`
  - `test_fiji_output_collection_image`
  - `test_fiji_run_creates_exchange_dir`
  - `test_fiji_filewatcher_protocol`
  - `test_fiji_process_handle_cleanup_on_error`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.app.app_block import AppBlock
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.core.types.collection import Collection

from scieasy_blocks_imaging.types import Image


class FijiBlock(AppBlock):
    """Launch Fiji to process a collection of images.

    Per master plan §10 memo, the default Fiji path is the user's
    Windows install. Override via the ``app_command`` config.

    Per ADR-019, this is an AppBlock subclass: it spawns a subprocess,
    monitors an exchange directory via FileWatcher, and collects the
    output files when the user closes Fiji.
    """

    type_name: ClassVar[str] = "imaging.fiji"
    name: ClassVar[str] = "Fiji"
    category: ClassVar[str] = "interactive"

    app_command: ClassVar[str] = r"C:\Program Files\Fiji\fiji-windows-x64.exe"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Collection[Image]]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Collection[Image]]),
    ]

    config_schema = {
        "properties": {
            "app_command": {"type": "string", "default": app_command},
            "macro_path": {"type": "string",
                           "description": "Optional Fiji macro to run headless"},
            "exchange_dir": {"type": "string"},
        },
    }

    def build_command(self, config: dict) -> list[str]:
        cmd = [config.get("app_command", self.app_command)]
        macro = config.get("macro_path")
        if macro:
            cmd.extend(["--headless", "-macro", macro])
        return cmd

    def output_patterns(self, config: dict) -> list[str]:
        return ["*.tif", "*.tiff", "*.png"]
```

**h. Acceptance criteria**:

- [ ] `FijiBlock` is `AppBlock` subclass.
- [ ] Default `app_command` matches user's Windows path.
- [ ] `app_command` configurable via config.
- [ ] Optional `macro_path` for headless mode.
- [ ] Input is `Collection[Image]`, output is `Collection[Image]`.
- [ ] Tests marked `@pytest.mark.requires_fiji`.

**i. Out of scope**: Live Fiji communication beyond file-exchange; specific Fiji plugins.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~150 src + ~200 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-034 FijiBlock AppBlock for interactive image processing`

---

### T-IMG-035 — NapariBlock

**Status**: Implemented in issue #386. `NapariBlock` now uses the shared
interactive file-exchange helper flow with fake-binary test coverage.

**a. Ticket ID and name**: T-IMG-035 — `NapariBlock` AppBlock subclass.

**b. Source ADR sections**: ADR-019.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/interactive/napari_block.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/interactive/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_interactive/test_napari_block.py` (marker:
  `@pytest.mark.requires_napari`)
  - `test_napari_class_exists_in_palette`
  - `test_napari_optional_label_input`
  - `test_napari_friendly_import_error_when_napari_missing`
  - `test_napari_run_in_subprocess`
  - `test_napari_save_modified_back_to_exchange_dir`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.app.app_block import AppBlock
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.core.types.collection import Collection

from scieasy_blocks_imaging.types import Image, Label


class NapariBlock(AppBlock):
    """Launch napari for interactive viewing/editing.

    Optional dependency: pip install scieasy-blocks-imaging[napari]
    """

    type_name: ClassVar[str] = "imaging.napari"
    name: ClassVar[str] = "Napari"
    category: ClassVar[str] = "interactive"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Collection[Image]]),
        InputPort(name="labels", accepted_types=[Collection[Label]],
                  required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Collection[Image]]),
        OutputPort(name="labels", accepted_types=[Collection[Label]]),
    ]

    config_schema = {
        "properties": {
            "exchange_dir": {"type": "string"},
        },
    }

    def build_command(self, config: dict) -> list[str]:
        try:
            import napari  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "NapariBlock requires the [napari] extra: "
                "pip install scieasy-blocks-imaging[napari]"
            ) from exc
        # napari runs as a Python subprocess that loads our exchange dir
        return ["python", "-m", "scieasy_blocks_imaging.interactive._napari_runner",
                "--exchange-dir", config.get("exchange_dir", "")]
```

**h. Acceptance criteria**:

- [ ] `NapariBlock` is `AppBlock`.
- [ ] Optional `labels` input.
- [ ] Two output ports.
- [ ] Friendly `ImportError` when napari missing.
- [ ] Subprocess launch.
- [ ] Modified images saved back to exchange dir.

**i. Out of scope**: Embedded napari widget in the SciEasy GUI (Phase 12+).

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~200 src + ~200 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-035 NapariBlock AppBlock for interactive viewing/editing`

---

### T-IMG-036 — CellProfilerBlock

**Status**: Implemented in issue #386. `CellProfilerBlock` now runs pipeline
file exchanges through the shared AppBlock helper path and routes label plus
measurement outputs with synthetic tool tests.

**a. Ticket ID and name**: T-IMG-036 — `CellProfilerBlock` AppBlock subclass.

**b. Source ADR sections**: ADR-019.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/interactive/cellprofiler_block.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/interactive/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_interactive/test_cellprofiler_block.py` (marker:
  `@pytest.mark.requires_cellprofiler`)
  - `test_cellprofiler_class_exists`
  - `test_cellprofiler_pipeline_path_required`
  - `test_cellprofiler_input_collection_image`
  - `test_cellprofiler_output_collection_label_and_dataframe`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.app.app_block import AppBlock
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.core.types.collection import Collection
from scieasy.core.types.dataframe import DataFrame

from scieasy_blocks_imaging.types import Image, Label


class CellProfilerBlock(AppBlock):
    """Run a CellProfiler .cppipe pipeline on a collection of images."""

    type_name: ClassVar[str] = "imaging.cellprofiler"
    name: ClassVar[str] = "CellProfiler"
    category: ClassVar[str] = "interactive"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Collection[Image]]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="labels", accepted_types=[Collection[Label]]),
        OutputPort(name="measurements", accepted_types=[DataFrame]),
    ]

    config_schema = {
        "properties": {
            "pipeline_path": {"type": "string"},
            "app_command": {"type": "string", "default": "cellprofiler"},
        },
        "required": ["pipeline_path"],
    }

    def build_command(self, config: dict) -> list[str]:
        return [config.get("app_command", "cellprofiler"),
                "-c", "-r", "-p", config["pipeline_path"]]
```

**h. Acceptance criteria**:

- [ ] Class exists with correct ClassVars.
- [ ] `pipeline_path` required.
- [ ] Two output ports.
- [ ] Tests marked `@pytest.mark.requires_cellprofiler`.

**i. Out of scope**: Pipeline editing inside SciEasy.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~120 src + ~150 tests. **Small-Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-036 CellProfilerBlock AppBlock`

---

### T-IMG-037 — QuPathBlock

**Status**: Implemented in issue #386. `QuPathBlock` now runs script-based
file exchanges through the shared AppBlock helper path with fake-tool coverage.

**a. Ticket ID and name**: T-IMG-037 — `QuPathBlock` AppBlock subclass.

**b. Source ADR sections**: ADR-019.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/interactive/qupath_block.py`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/interactive/__init__.py`
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`

**e. New tests**:
- `tests/test_interactive/test_qupath_block.py` (marker:
  `@pytest.mark.requires_qupath`)
  - `test_qupath_class_exists`
  - `test_qupath_groovy_script_required`
  - `test_qupath_input_output_collection_image`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
from __future__ import annotations
from typing import ClassVar

from scieasy.blocks.app.app_block import AppBlock
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.core.types.collection import Collection

from scieasy_blocks_imaging.types import Image


class QuPathBlock(AppBlock):
    """Run a QuPath Groovy script on a collection of images."""

    type_name: ClassVar[str] = "imaging.qupath"
    name: ClassVar[str] = "QuPath"
    category: ClassVar[str] = "interactive"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Collection[Image]]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Collection[Image]]),
    ]

    config_schema = {
        "properties": {
            "script_path": {"type": "string"},
            "app_command": {"type": "string", "default": "qupath"},
        },
        "required": ["script_path"],
    }

    def build_command(self, config: dict) -> list[str]:
        return [config.get("app_command", "qupath"),
                "script", config["script_path"]]
```

**h. Acceptance criteria**:

- [ ] Class exists with correct ClassVars.
- [ ] `script_path` required.
- [ ] Input/output `Collection[Image]`.
- [ ] Tests marked `@pytest.mark.requires_qupath`.

**i. Out of scope**: Whole-slide image specific features.

**j. Dependencies on other tickets**: T-IMG-001.

**k. Estimated diff size**: ~100 src + ~120 tests. **Small**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-037 QuPathBlock AppBlock`

---

### T-IMG-038 — Plugin packaging (`pyproject.toml` + entry-point registration)

**Status**: Implemented in issue #386. The package now ships as
`scieasy-blocks-imaging` 0.1.0 with hatchling metadata, `scieasy.blocks` /
`scieasy.types` entry points, package-level packaging tests, README updates, and
the required top-level workflow smoke coverage.

**a. Ticket ID and name**: T-IMG-038 — Plugin packaging and final wiring.

**b. Source ADR sections**: ADR-025 (`scieasy.blocks` / `scieasy.types` entry-point groups), ADR-028 §D8.

**c. Files to be created**:
- `packages/scieasy-blocks-imaging/pyproject.toml`
- `packages/scieasy-blocks-imaging/README.md`

**d. Files to be modified**:
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py`
  (final `get_blocks()` returning all 38 block classes; final
  `__all__`)

**e. New tests**:
- `tests/test_packaging.py`
  - `test_get_blocks_returns_all_38_blocks`
  - `test_get_types_returns_four_types`
  - `test_entry_point_imaging_blocks_resolves`
  - `test_entry_point_imaging_types_resolves`
  - `test_each_block_has_unique_type_name`
  - `test_each_block_has_required_classvars`
  - `test_each_block_round_trips_serialise`
  - `test_pyproject_toml_extras_listed`
  - `test_optional_extras_skip_when_missing`
  - `test_version_is_0_1_0`

**f. Existing tests to update**: none.

**g. Implementation details**:

```toml
# packages/scieasy-blocks-imaging/pyproject.toml

[project]
name = "scieasy-blocks-imaging"
version = "0.1.0"
description = "General-purpose microscopy block library for SciEasy"
authors = [{name = "SciEasy Contributors"}]
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "scieasy>=0.1",
    "numpy>=1.24",
    "tifffile>=2024.1",
    "imageio>=2.33",
    "scikit-image>=0.22",
    "scipy>=1.11",
    "pydantic>=2.5",
    "pillow>=10.0",
    "pandas>=2.0",
    "matplotlib>=3.7",
]

[project.optional-dependencies]
cellpose = ["cellpose>=3.0"]
napari = ["napari>=0.5"]
czi = ["aicsimageio>=4.14"]
nd2 = ["nd2reader>=3.3"]
lif = ["readlif>=0.6"]
all = ["scieasy-blocks-imaging[cellpose,napari,czi,nd2,lif]"]

[project.entry-points."scieasy.blocks"]
imaging = "scieasy_blocks_imaging:get_blocks"

[project.entry-points."scieasy.types"]
imaging = "scieasy_blocks_imaging:get_types"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/scieasy_blocks_imaging"]

[tool.pytest.ini_options]
markers = [
    "requires_cellpose: needs the [cellpose] extra",
    "requires_napari: needs the [napari] extra",
    "requires_fiji: needs Fiji installed locally",
    "requires_cellprofiler: needs CellProfiler installed locally",
    "requires_qupath: needs QuPath installed locally",
    "requires_czi: needs the [czi] extra",
    "requires_nd2: needs the [nd2] extra",
    "requires_lif: needs the [lif] extra",
]
```

```python
# packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/__init__.py
"""scieasy-blocks-imaging — general-purpose microscopy plugin for SciEasy.

Public API:
- get_blocks() — returns all block classes for scieasy.blocks entry-point
- get_types() — returns the four imaging types for scieasy.types entry-point
"""
from __future__ import annotations

from scieasy_blocks_imaging.types import Image, Label, Mask, Transform

# IO
from scieasy_blocks_imaging.io.load_image import LoadImage
from scieasy_blocks_imaging.io.save_image import SaveImage
# Preprocessing
from scieasy_blocks_imaging.preprocessing.denoise import Denoise
from scieasy_blocks_imaging.preprocessing.background import BackgroundSubtract
from scieasy_blocks_imaging.preprocessing.normalize import Normalize
from scieasy_blocks_imaging.preprocessing.flatfield import FlatFieldCorrect
from scieasy_blocks_imaging.preprocessing.geometry import (
    Rotate, Flip, Crop, Pad, Resize,
)
from scieasy_blocks_imaging.preprocessing.convert_dtype import ConvertDType
from scieasy_blocks_imaging.preprocessing.axis_split_merge import (
    AxisSplit, AxisMerge,
)
from scieasy_blocks_imaging.preprocessing.deconvolve import Deconvolve
# Morphology
from scieasy_blocks_imaging.morphology.ops import MorphologyOp
from scieasy_blocks_imaging.morphology.edges import EdgeDetect
from scieasy_blocks_imaging.morphology.ridges import RidgeFilter
from scieasy_blocks_imaging.morphology.sharpen import Sharpen
from scieasy_blocks_imaging.morphology.fft import FFTFilter
# Segmentation
from scieasy_blocks_imaging.segmentation.threshold import Threshold
from scieasy_blocks_imaging.segmentation.watershed import Watershed
from scieasy_blocks_imaging.segmentation.cellpose_segment import CellposeSegment
from scieasy_blocks_imaging.segmentation.blob import BlobDetect
from scieasy_blocks_imaging.segmentation.connected_components import (
    ConnectedComponents,
)
from scieasy_blocks_imaging.segmentation.cleanup import (
    RemoveSmallObjects, RemoveBorderObjects, FillHoles,
    ExpandLabels, ShrinkLabels,
)
# Tracking
from scieasy_blocks_imaging.tracking.track_objects import TrackObjects
# Measurement
from scieasy_blocks_imaging.measurement.region_props import RegionProps
from scieasy_blocks_imaging.measurement.pairwise_distance import PairwiseDistance
from scieasy_blocks_imaging.measurement.colocalization import Colocalization
# Registration
from scieasy_blocks_imaging.registration.compute_registration import (
    ComputeRegistration,
)
from scieasy_blocks_imaging.registration.apply_transform import ApplyTransform
from scieasy_blocks_imaging.registration.register_series import RegisterSeries
# Axis
from scieasy_blocks_imaging.axis.projection import AxisProjection
from scieasy_blocks_imaging.axis.select_slice import SelectSlice
# Math
from scieasy_blocks_imaging.math.scalar_ops import (
    AddScalar, SubtractScalar, MultiplyScalar, DivideScalar,
)
from scieasy_blocks_imaging.math.image_calculator import ImageCalculator
# Visualization
from scieasy_blocks_imaging.visualization.pseudo_color import RenderPseudoColor
from scieasy_blocks_imaging.visualization.overlay import RenderOverlay
from scieasy_blocks_imaging.visualization.montage import RenderMontage
from scieasy_blocks_imaging.visualization.movie import RenderMovie
from scieasy_blocks_imaging.visualization.histogram import RenderHistogram
# Interactive
from scieasy_blocks_imaging.interactive.fiji_block import FijiBlock
from scieasy_blocks_imaging.interactive.napari_block import NapariBlock
from scieasy_blocks_imaging.interactive.cellprofiler_block import (
    CellProfilerBlock,
)
from scieasy_blocks_imaging.interactive.qupath_block import QuPathBlock


def get_blocks() -> list[type]:
    """Plugin entry point for scieasy.blocks."""
    return [
        # IO
        LoadImage, SaveImage,
        # Preprocessing
        Denoise, BackgroundSubtract, Normalize, FlatFieldCorrect,
        Rotate, Flip, Crop, Pad, Resize,
        ConvertDType, AxisSplit, AxisMerge, Deconvolve,
        # Morphology
        MorphologyOp, EdgeDetect, RidgeFilter, Sharpen, FFTFilter,
        # Segmentation
        Threshold, Watershed, CellposeSegment, BlobDetect,
        ConnectedComponents, RemoveSmallObjects, RemoveBorderObjects,
        FillHoles, ExpandLabels, ShrinkLabels,
        # Tracking
        TrackObjects,
        # Measurement
        RegionProps, PairwiseDistance, Colocalization,
        # Registration
        ComputeRegistration, ApplyTransform, RegisterSeries,
        # Axis
        AxisProjection, SelectSlice,
        # Math
        AddScalar, SubtractScalar, MultiplyScalar, DivideScalar,
        ImageCalculator,
        # Visualization
        RenderPseudoColor, RenderOverlay, RenderMontage, RenderMovie,
        RenderHistogram,
        # Interactive
        FijiBlock, NapariBlock, CellProfilerBlock, QuPathBlock,
    ]


def get_types() -> list[type]:
    """Plugin entry point for scieasy.types."""
    return [Image, Mask, Label, Transform]


__version__ = "0.1.0"
__all__ = [
    "Image", "Mask", "Label", "Transform",
    "get_blocks", "get_types",
    # all the block classes...
]
```

**h. Acceptance criteria**:

- [ ] `pyproject.toml` declares `scieasy-blocks-imaging` 0.1.0.
- [ ] Required dependencies listed.
- [ ] Five optional extras (`cellpose`, `napari`, `czi`, `nd2`,
      `lif`) plus `all`.
- [ ] `[project.entry-points."scieasy.blocks"]` and
      `[project.entry-points."scieasy.types"]` declared.
- [ ] `pytest` markers registered for all `requires_*` tags.
- [ ] `get_blocks()` returns ~50 block classes covering all listed
      tickets (counting bundle members like `Rotate`/`Flip`/`Crop`
      individually).
- [ ] `get_types()` returns the four types.
- [ ] Each block has a unique `type_name`.
- [ ] Each block has the required ClassVars.
- [ ] Each block survives a smoke `_serialise_one` round-trip.
- [ ] `README.md` documents installation, extras, and entry-point
      registration.
- [ ] `__version__ == "0.1.0"`.

**i. Out of scope**: PyPI publishing; conda-forge recipe; Windows
installer.

**j. Dependencies on other tickets**: ALL other T-IMG tickets.

**k. Estimated diff size**: ~250 src + ~300 tests. **Medium**.

**l. Suggested workflow gate ticket title**:
`feat(imaging): T-IMG-038 Plugin packaging and entry-point registration for 0.1.0`

---

## 10. Summary table

| Ticket    | Title                                                  | Files                                                                          | Diff size | Deps                       |
|-----------|--------------------------------------------------------|--------------------------------------------------------------------------------|-----------|----------------------------|
| T-IMG-001 | Types module                                           | `types.py` + tests                                                              | Medium    | T-IMG-038a (skeleton)      |
| T-IMG-002 | LoadImage                                              | `io/load_image.py` + tests                                                      | Large     | T-IMG-001                  |
| T-IMG-003 | SaveImage                                              | `io/save_image.py` + tests                                                      | Medium    | T-IMG-001, T-IMG-002       |
| T-IMG-004 | Denoise                                                | `preprocessing/denoise.py` + tests                                              | Medium    | T-IMG-001                  |
| T-IMG-005 | BackgroundSubtract                                     | `preprocessing/background.py` + tests                                           | Medium    | T-IMG-001                  |
| T-IMG-006 | Normalize                                              | `preprocessing/normalize.py` + tests                                            | Medium    | T-IMG-001                  |
| T-IMG-007 | FlatFieldCorrect                                       | `preprocessing/flatfield.py` + tests                                            | Medium    | T-IMG-001                  |
| T-IMG-008 | Geometry bundle                                        | `preprocessing/geometry.py` + tests                                             | Large     | T-IMG-001                  |
| T-IMG-009 | ConvertDType                                           | `preprocessing/convert_dtype.py` + tests                                        | Small-Med | T-IMG-001                  |
| T-IMG-010 | AxisSplit / AxisMerge                                  | `preprocessing/axis_split_merge.py` + tests                                     | Medium    | T-IMG-001                  |
| T-IMG-011 | Deconvolve placeholder                                 | `preprocessing/deconvolve.py` + tests                                           | Small     | T-IMG-001                  |
| T-IMG-012 | MorphologyOp                                           | `morphology/ops.py` + tests                                                     | Small-Med | T-IMG-001                  |
| T-IMG-013 | EdgeDetect                                             | `morphology/edges.py` + tests                                                   | Small     | T-IMG-001                  |
| T-IMG-014 | RidgeFilter                                            | `morphology/ridges.py` + tests                                                  | Small     | T-IMG-001                  |
| T-IMG-015 | Sharpen                                                | `morphology/sharpen.py` + tests                                                 | Small     | T-IMG-001                  |
| T-IMG-016 | FFTFilter                                              | `morphology/fft.py` + tests                                                     | Small-Med | T-IMG-001                  |
| T-IMG-017 | Threshold                                              | `segmentation/threshold.py` + tests                                             | Medium    | T-IMG-001                  |
| T-IMG-018 | Watershed                                              | `segmentation/watershed.py` + tests                                             | Medium    | T-IMG-001                  |
| T-IMG-019 | CellposeSegment (FLAGSHIP)                             | `segmentation/cellpose_segment.py` + tests                                      | Large     | T-IMG-001                  |
| T-IMG-020 | BlobDetect                                             | `segmentation/blob.py` + tests                                                  | Medium    | T-IMG-001                  |
| T-IMG-021 | ConnectedComponents                                    | `segmentation/connected_components.py` + tests                                  | Small     | T-IMG-001                  |
| T-IMG-022 | Cleanup bundle                                         | `segmentation/cleanup.py` + tests                                               | Medium    | T-IMG-001                  |
| T-IMG-023 | TrackObjects placeholder                               | `tracking/track_objects.py` + tests                                             | Small     | T-IMG-001                  |
| T-IMG-024 | RegionProps                                            | `measurement/region_props.py` + tests                                           | Medium    | T-IMG-001                  |
| T-IMG-025 | PairwiseDistance                                       | `measurement/pairwise_distance.py` + tests                                      | Medium    | T-IMG-001                  |
| T-IMG-026 | Colocalization                                         | `measurement/colocalization.py` + tests                                         | Medium    | T-IMG-001                  |
| T-IMG-027 | ComputeRegistration                                    | `registration/compute_registration.py` + tests                                  | Medium    | T-IMG-001                  |
| T-IMG-028 | ApplyTransform                                         | `registration/apply_transform.py` + tests                                       | Small-Med | T-IMG-001, T-IMG-027       |
| T-IMG-029 | RegisterSeries                                         | `registration/register_series.py` + tests                                       | Medium    | T-IMG-001, T-IMG-027/028   |
| T-IMG-030 | AxisProjection / SelectSlice                           | `axis/projection.py`, `axis/select_slice.py` + tests                            | Medium    | T-IMG-001                  |
| T-IMG-031 | Math scalar bundle                                     | `math/scalar_ops.py` + tests                                                    | Small-Med | T-IMG-001                  |
| T-IMG-032 | ImageCalculator                                        | `math/image_calculator.py` + tests                                              | Medium    | T-IMG-001                  |
| T-IMG-033 | Visualization bundle                                   | `visualization/{pseudo_color,overlay,montage,movie,histogram}.py` + tests       | Large     | T-IMG-001                  |
| T-IMG-034 | FijiBlock                                              | `interactive/fiji_block.py` + tests                                             | Medium    | T-IMG-001                  |
| T-IMG-035 | NapariBlock                                            | `interactive/napari_block.py` + tests                                           | Medium    | T-IMG-001                  |
| T-IMG-036 | CellProfilerBlock                                      | `interactive/cellprofiler_block.py` + tests                                     | Small-Med | T-IMG-001                  |
| T-IMG-037 | QuPathBlock                                            | `interactive/qupath_block.py` + tests                                           | Small     | T-IMG-001                  |
| T-IMG-038 | Plugin packaging                                       | `pyproject.toml`, `README.md`, `__init__.py` final wiring + tests               | Medium    | All other T-IMG tickets    |

---

## 11. Integration test (E2E workflow)

The end-to-end test validates the full imaging plugin against the four
test images at `C:\Users\jiazh\Desktop\workspace\Example\images\` per
master plan §8:

- `K562_L_2845 (uV).tif` — segmentation image 1
- `K562_L_spectra (uV).tif` — spectra image 1
- `K562_UL_2845 (uV).tif` — segmentation image 2
- `K562_UL_spectra (uV).tif` — spectra image 2

Note the parens and spaces in filenames — quote carefully.

### Imaging-only sub-workflow (the half this spec covers)

```python
# packages/scieasy-blocks-imaging/tests/integration/test_e2e_workflow.py

from pathlib import Path

import pytest

from scieasy.workflow.builder import WorkflowBuilder

from scieasy_blocks_imaging import (
    LoadImage, Denoise, CellposeSegment, SaveImage,
)

IMAGES_DIR = Path(r"C:\Users\jiazh\Desktop\workspace\Example\images")
SEG_GLOB = "K562_*_2845 (uV).tif"
SPECTRA_GLOB = "K562_*_spectra (uV).tif"


@pytest.mark.requires_cellpose
def test_e2e_imaging_pipeline(tmp_path):
    """E2E: load -> denoise -> cellpose -> save (imaging side only)."""
    # 1. Load segmentation images
    loader = LoadImage()
    seg_collection = loader.load({"path": str(IMAGES_DIR / SEG_GLOB)})
    assert len(seg_collection) == 2

    # 2. Denoise (Gaussian)
    denoise = Denoise()
    denoised = []
    for img in seg_collection:
        denoised.append(denoise.process_item(
            img, {"method": "gaussian", "sigma": 1.0}, state=None,
        ))

    from scieasy.core.types.collection import Collection
    denoised_col = Collection(denoised)

    # 3. Cellpose segment
    seg_block = CellposeSegment()
    state = seg_block.setup({"model": "cyto3", "diameter": 30.0,
                             "use_gpu": False})
    try:
        labels = []
        for img in denoised_col:
            labels.append(seg_block.process_item(
                img, {"diameter": 30.0, "flow_threshold": 0.4}, state,
            ))
    finally:
        seg_block.teardown(state)

    label_col = Collection(labels)
    assert len(label_col) == 2
    for lab in label_col:
        assert lab.slots["raster"] is not None
        assert lab.meta.n_objects > 0

    # 4. Save labels
    saver = SaveImage()
    out_dir = tmp_path / "labels"
    # Save the raster slot of each label as an image
    label_imgs = [
        lab.slots["raster"] for lab in label_col
    ]
    saver.save({"images": Collection(label_imgs)},
               {"path": str(out_dir), "format": "tif"})
    assert (out_dir / "K562_L_2845 (uV).tif").exists() or \
           (out_dir / "image_000.tif").exists()
```

### Cross-plugin (imaging + SRS) — covered by SRS spec

The full master plan §8 workflow extends this with the spectra
branch and `ExtractSpectrum`:

```
LoadImage[seg]                  LoadImage[spectra]
       |                                |
   Denoise[gaussian]               Denoise[gaussian]
       |                                |
   CellposeSegment                      |
       |                                |
   Collection[Label] ---------- ExtractSpectrum (SRS plugin)
                                        |
                                  DataFrame (spectra)

   SaveImage(labels)            SaveData(spectra)
```

The `ExtractSpectrum` block is specified in
`docs/specs/phase11-srs-block-spec.md`, not here. The cross-plugin
integration test lives in `packages/scieasy-blocks-srs/tests/integration/`
and depends on both plugins being installed.

### Failure handling

Per master plan §8: any block failure during the E2E run files an
issue titled `E2E BLOCKER: <block name> <error>`, tags `critical`,
spawns a fix agent, and re-runs.

---

## 12. References

- `docs/adr/ADR.md` — ADR-027 (Phase 10 core type system, lines
  3961-4644), ADR-027 Addendum 1 (worker reconstruction, lines
  4645-5170), ADR-028 (IOBlock refactor, lines 5171-5922), ADR-028
  Addendum 1 (dynamic ports + GUI, lines 5923-6513).
- `docs/architecture/ARCHITECTURE.md` §4 (types) and §5 (blocks).
- `docs/specs/phase10-implementation-standards.md` — structural
  template for this spec; also defines T-009 (`ProcessBlock.setup` /
  `teardown`) which `CellposeSegment` depends on.
- `docs/guides/block-sdk.md` — block authoring patterns and the
  Tier 1 / Tier 2 / Tier 3 distinction.
- `CLAUDE.md` Appendix A — workflow gate stages, branch naming, scope
  discipline.
- `CLAUDE.md` §6.7 — scope discipline.
- `CLAUDE.md` §9.2 — no silent scope broadening.
- Phase 11 master plan (`memory/phase11_master_plan.md`) — locked
  architectural decisions, block list, E2E test images.
- `src/scieasy/utils/axis_iter.py` — `iterate_over_axes(source, operates_on, fn)`.
- `src/scieasy/utils/constraints.py` — `has_axes`, `has_exact_axes`,
  `has_shape`.
- `src/scieasy/blocks/process/process_block.py` — `setup` /
  `teardown` lifecycle hooks.
- `src/scieasy/core/types/array.py` — `Array` instance-level axes,
  `required_axes` / `allowed_axes` / `canonical_order` ClassVars.
- `src/scieasy/core/meta/framework.py` — `FrameworkMeta`.
- `src/scieasy/core/meta/channel.py` — `ChannelInfo`.
- `src/scieasy/core/units.py` — `PhysicalQuantity`.