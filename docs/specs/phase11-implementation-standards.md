---
spec_id: phase11-implementation-standards
title: "Phase 11 Implementation Standards Task Decomposition"
status: Deprecated
feature_branch: legacy/phase11-implementation-standards
created: 2026-04-07
input: "Historical Phase 11 task decomposition for plugin cascade work tracked by issue #306."
owners:
  - "@jiazhenz026"
related_adrs:
  - 27
  - 28
  - 29
related_specs:
  - phase11-imaging-block-spec
  - phase11-srs-block-spec
  - phase11-lcms-block-spec
scope:
  in:
    - Historical Phase 11 dispatch and dependency plan retained for reference.
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
# Phase 11 Implementation Standards Task Decomposition

## 1. Change Summary

This deprecated spec is retained as historical reference. Its original body is preserved below, but it is not an active implementation spec under ADR-042.

## 2. Existing Historical Body

---
title: Phase 11 implementation standards (task decomposition)
status: in progress
issue: 306 (closes #305)
date: 2026-04-07
---

# Phase 11 implementation standards

## 1. Purpose

This document is the **master task-decomposition standard** for the
Phase 11 plugin cascade. It is the single source of truth that:

- The **skeleton agent** reads to know which files to delete, which
  to create as placeholders, and which directory layout to scaffold.
- Each **implementation agent** reads to know exactly which files
  it owns, what its acceptance criteria are, and where its work fits
  in the dependency graph.
- Each **code-audit agent** reads to verify that an implementation PR
  did not silently broaden scope, did not weaken type contracts, and
  satisfied the per-ticket acceptance criteria.

This document does **not** replace the source design documents. It is a
*decomposition layer* that breaks the source documents into
implementation-sized work units and records the dependencies between
them. The source documents remain authoritative for the *what* of each
ticket; this document is authoritative for the *how to dispatch* of the
overall cascade.

Source documents (already merged):

- ADR-028 — IOBlock architectural refactor (merged in PR #294).
- ADR-028 Addendum 1 — dynamic port override mechanism + GUI
  consequences.
- ADR-029 (preliminary, draft) — variadic port count, no
  decisions yet, namespace reservation only.
- ``docs/specs/phase11-imaging-block-spec.md`` — 38 T-IMG-* tickets,
  full per-block implementation details.
- ``docs/specs/phase11-srs-block-spec.md`` — 15 T-SRS-* tickets.
- ``docs/specs/phase11-lcms-block-spec.md`` — 21 T-LCMS-* tickets.
- ``CLAUDE.md`` — workflow gate (Appendix A), §6.7 (tests are part of
  the change), §9.2 (no silent scope expansion).

This standards document, like the Phase 10 standards before it, is the
checkpoint between *design* and *implementation*. After this document
merges, the skeleton agent and the per-ticket implementation agents
begin work; before this document merges, no implementation agent may
spawn.

---

## 2. Scope

### In scope

- **Track 1 — core block cleanup and ADR-028 implementation.** 15
  tickets, T-TRK-001 through T-TRK-015. Covers Phase 11 master-plan
  sub-tasks 1a (delete stubs + relocate ``transform.py``), 1b
  (ADR-028 implementation, broken into stacked PRs), 1c (CLAUDE.md +
  ARCHITECTURE.md ManualReview clarification), 1d (FilterCollection
  metadata query), 1e (CodeBlock R runner audit), 1f (CodeBlock
  Python runner audit), 1g (AppBlock functional audit). The
  full per-ticket details for Track 1 live **inside this document**.

- **Track 2 — imaging plugin implementation.** 38 tickets, T-IMG-001
  through T-IMG-038. Per-ticket implementation details live in
  ``docs/specs/phase11-imaging-block-spec.md``. This standards doc
  carries the *cross-ticket* metadata: dependency edges, sprint
  bucket, coupling notes.

- **Track 3 — SRS plugin implementation.** 15 tickets, T-SRS-000
  through T-SRS-014. Per-ticket details in
  ``docs/specs/phase11-srs-block-spec.md``.

- **Track 4 — LC-MS plugin implementation.** 21 tickets, T-LCMS-001
  through T-LCMS-021. Per-ticket details in
  ``docs/specs/phase11-lcms-block-spec.md``.

- **End-to-end test plan.** Two phases — post-Sprint-C (imaging done)
  and post-Sprint-E (full plugin set). Both phases described in §11.

### Out of scope

- **ADR-029 implementation.** The variadic-port-count work is hard
  frozen until ADR-029 is promoted from ``draft — scope pending`` to
  ``proposed``. No ticket in this document touches ``AIBlock`` variadic
  behaviour, ``CodeBlock`` variadic behaviour, or "add port" / "remove
  port" GUI controls. Implementation agents reading this document
  must reject any inline scope expansion in this direction.

- **Plugin packages beyond imaging / SRS / LC-MS.** ``scistudio-blocks-
  singlecell``, ``scistudio-blocks-flow``, and any future plugin remain
  out of scope. The corresponding bundled adapters (``h5ad_adapter``
  and ``fcs_adapter``) are deleted per ADR-028 §D2 but no replacement
  plugin work is scheduled.

- **ARCHITECTURE.md updates beyond Sprint A sub-1b PR-F.** Larger
  architectural docs revisions are deliberately deferred to a follow-up
  sprint. The Sprint A docs PR (T-TRK-010) covers only the §4.2 +
  §5.1 + ``PROJECT_TREE.md`` + ``block-sdk.md`` updates that ADR-028
  requires.

- **Frontend React refactoring beyond ``BlockNode.tsx`` hardcoding
  fixes.** No new React components, no new pages, no styling overhaul.
  Sprint A T-TRK-009 changes exactly the three lines ADR-028
  Addendum 1 §C identifies and adds the ``computeEffectivePorts()``
  helper plus matching TypeScript types — nothing more.

- **Cellpose / Napari / Fiji / R / ElMAVEN / GraphPad version pinning,
  installation scripts, or CI integration.** Marker-protected tests
  (``@pytest.mark.requires_*``) skip when the optional dependency is
  absent. Local-machine integration is the user's responsibility.

---

## 3. Cross-reference table

| Track | Total tickets | Source spec / doc                                  | Sprint(s)             |
|-------|---------------|----------------------------------------------------|-----------------------|
| 1     | 15            | This document §9 (T-TRK-* full format)             | Sprint A + Sprint B  |
| 2     | 38            | ``docs/specs/phase11-imaging-block-spec.md``       | Sprint C             |
| 3     | 15            | ``docs/specs/phase11-srs-block-spec.md``           | Sprint D             |
| 4     | 21            | ``docs/specs/phase11-lcms-block-spec.md``          | Sprint E             |
| **Total** | **89**    |                                                    |                       |

ADR cross-reference:

| Source | Authoritative for                                             |
|--------|---------------------------------------------------------------|
| ADR-028 + Addendum 1 | Track 1 sub-1b (IOBlock + dynamic ports), Block ABC migration, BlockSchemaResponse, frontend BlockNode |
| ADR-028 §D2 | Track 1 sub-1a + Track 2 ``LoadImage`` adapter migration   |
| ADR-027 (Phase 10) | Block class hierarchy, type registry, port system |
| ADR-029 (preliminary) | Documents what is **out of scope** for Phase 11 |

---

## 4. Dependency graph

The cascade is divided into five sprints. Within each sprint, tickets
are grouped by parallelism level: tickets at the same level can run
concurrently; tickets at level N+1 depend on level N completing.

```
Sprint A (Track 1 sub-1a + sub-1b + sub-1c)
├── Level A0 (parallel)
│   ├── T-TRK-001  delete process/contrib/                    [parallel]
│   ├── T-TRK-002  delete process/builtins/register.py        [parallel]
│   ├── T-TRK-003  move transform.py → tests/fixtures/        [parallel]
│   └── T-TRK-011  CLAUDE.md §2.5 + ARCHITECTURE.md MR        [parallel, independent]
├── Level A1 (after A0)
│   └── T-TRK-004  delete adapters/ + adapter_registry +
│                  rewrite io_block.py as ABC                  [bundles old PR-A]
├── Level A2 (after A1)
│   └── T-TRK-006  Block ABC dynamic-port hooks +
│                  BlockSpec + BlockSchemaResponse +
│                  framework read-path migration               [bundles PR-B-1/2/3]
├── Level A3 (after A2, parallel pair)
│   ├── T-TRK-007  LoadData + 6 _load_* private functions
│   └── T-TRK-008  SaveData + 6 _save_* private functions
├── Level A4 (after A3)
│   └── T-TRK-009  Frontend BlockNode.tsx fixes +
│                  computeEffectivePorts + types/api.ts
└── Level A5 (after A4)
    └── T-TRK-010  ARCHITECTURE.md §4.2 + §5.1 +
                   PROJECT_TREE.md + block-sdk.md updates

Sprint B (Track 1 sub-1d + sub-1e + sub-1f + sub-1g, parallel)
├── T-TRK-012  FilterCollection metadata query                [imaging dep]
├── T-TRK-013  CodeBlock R runner audit                        [lcms dep]
├── T-TRK-014  CodeBlock Python runner audit                   [lcms dep]
└── T-TRK-015  AppBlock functional audit                       [imaging dep]

Sprint C (Track 2 imaging) — depends on Sprint A merged, Sprint B in progress
├── Level C0
│   └── T-IMG-001  Types module
├── Level C1 (parallel after C0)
│   ├── T-IMG-002  LoadImage
│   ├── T-IMG-003  SaveImage
│   └── T-IMG-004..T-IMG-022  preprocess/morph/seg/cleanup blocks (parallel)
├── Level C2 (parallel after C1)
│   ├── T-IMG-019  CellposeSegment (FLAGSHIP — depends on T-IMG-001 + T-TRK-015)
│   ├── T-IMG-023..T-IMG-029  tracking/measurement/registration
│   ├── T-IMG-030..T-IMG-033  projection/math/visualization
│   └── T-IMG-034..T-IMG-037  AppBlocks (Fiji/Napari/CellProfiler/QuPath, depend on T-TRK-015)
└── Level C3
    └── T-IMG-038  Plugin packaging (pyproject.toml entry points, smoke test)

Sprint D (Track 3 SRS) — depends on Sprint C T-IMG-001/002/004/019 merged
├── Level D0
│   ├── T-SRS-000  Package skeleton + entry points
│   └── T-SRS-001  SRSImage type + Meta model
├── Level D1 (parallel after D0)
│   ├── T-SRS-002..T-SRS-005  preprocess (Calibrate/Baseline/Denoise/Normalize)
│   ├── T-SRS-006..T-SRS-010  component analysis (VCA/Unmix/PCA/ICA/KMeans)
│   └── T-SRS-011..T-SRS-012  spectral extraction (ExtractSpectrum/BandRatio)
└── Level D2
    ├── T-SRS-013  Plugin entry-point wiring + smoke test
    └── T-SRS-014  E2E integration test (cross-plugin)

Sprint E (Track 4 LC-MS) — depends on Sprint A + sub-1e/1f merged
├── Level E0
│   ├── T-LCMS-001  Plugin scaffold
│   └── T-LCMS-002  Types module
├── Level E1 (parallel after E0)
│   ├── T-LCMS-003..T-LCMS-006  IO loaders (RawFiles/PeakTable/MIDTable/SampleMetadata + SaveTable)
│   └── T-LCMS-007             ElMAVENBlock + AccuCorR (depends on T-TRK-013 R audit)
├── Level E2 (parallel after E1)
│   ├── T-LCMS-008..T-LCMS-012  isotope tracing (5 blocks)
│   ├── T-LCMS-013..T-LCMS-018  metabolomics analysis (6 blocks)
│   └── T-LCMS-019             GraphPadBlock
└── Level E3
    ├── T-LCMS-020  Entry-point registration + plugin smoke test
    └── T-LCMS-021  Isotope tracing integration test
```

---

## 5. Recommended chained PR order

The literal merge order, top to bottom. Items at the same indent level
may run in parallel (separate branches and PRs); items at deeper indent
are stacked on the previous level.

1. **Sprint A — Track 1 sub-1a parallel batch** (4 PRs in parallel,
   independent)
   - T-TRK-001 (delete ``process/contrib/``)
   - T-TRK-002 (delete ``process/builtins/register.py``)
   - T-TRK-003 (move ``transform.py`` → ``tests/fixtures/noop_block.py``)
   - T-TRK-011 (CLAUDE.md §2.5 + ARCHITECTURE.md ManualReview)
2. **Sprint A — Track 1 sub-1b stacked cascade** (sequential, each PR
   stacked on the previous)
   - T-TRK-004 (delete adapters + rewrite ``io_block.py`` as ABC)
   - T-TRK-006 (Block ABC dynamic-port hooks + BlockSpec + framework
     migration)
   - T-TRK-007 + T-TRK-008 in parallel (LoadData / SaveData) — both
     stacked on T-TRK-006
   - T-TRK-009 (frontend BlockNode.tsx + types/api.ts)
   - T-TRK-010 (ARCHITECTURE + PROJECT_TREE + block-sdk docs)
3. **Sprint B — Track 1 sub-1d/1e/1f/1g** (4 PRs in parallel,
   independent of each other but dependent on Sprint A complete)
   - T-TRK-012 (FilterCollection)
   - T-TRK-013 (CodeBlock R audit)
   - T-TRK-014 (CodeBlock Python audit)
   - T-TRK-015 (AppBlock audit)
4. **Sprint C — Track 2 imaging cascade** (T-IMG-001 first, then
   ~36 mostly-parallel block PRs, then T-IMG-038 packaging last)
5. **Sprint D — Track 3 SRS cascade** (T-SRS-000 / T-SRS-001 first,
   then ~13 parallel block PRs, then T-SRS-013 / T-SRS-014 last)
6. **Sprint E — Track 4 LC-MS cascade** (T-LCMS-001 / T-LCMS-002 first,
   then ~17 mostly-parallel block PRs, then T-LCMS-020 / T-LCMS-021
   last)

**Stacked-PR rule**: when a PR is stacked on a not-yet-merged base, set
``base`` in ``gh pr create`` to the previous PR's branch name. After
the previous PR merges, the next stacked PR's base auto-retargets to
``main``. Per Phase 10 cascade lessons, **the first destructive PR is
the highest-risk point** because the full CI pipeline only runs after
retarget to ``main`` (the stacked branch's CI runs against the
unstable base). For this cascade the first destructive PR is
**T-TRK-004** (delete adapters + rewrite ``io_block.py``).

---

## 6. Universal rules for all 89 implementation agents

These rules apply to **every** ticket in this document. Failure to
follow them is a workflow gate violation per ``CLAUDE.md`` §6.7 and
§9.2.

1. **Workflow gate is mandatory.** Every ticket follows the full
   6-stage workflow gate per ``CLAUDE.md`` Appendix A. No exceptions
   for "small" tickets, including pure file-deletion PRs and
   doc-only PRs. Each stage must show ``[DONE]`` in
   ``python .workflow/gate.py status <task_id>`` before the next stage
   begins.

2. **Branch naming.**
   - Track 1: ``feat/issue-N/T-TRK-NNN-short-name`` (replace ``feat``
     with ``fix`` or ``docs`` or ``refactor`` as appropriate). Example:
     ``refactor/issue-310/T-TRK-004-delete-adapters-rewrite-ioblock``.
   - Track 2: ``feat/issue-N/T-IMG-NNN-short-name``.
   - Track 3: ``feat/issue-N/T-SRS-NNN-short-name``.
   - Track 4: ``feat/issue-N/T-LCMS-NNN-short-name``.

3. **Stacked-PR base.** Each PR's base branch is the previous merged
   PR's branch (so the diffs compose cleanly). If the previous PR has
   already merged into ``main``, base off ``main`` directly. Mark
   stacked PRs with the previous PR number in the description.

4. **Out-of-scope changes are forbidden.** The PR's diff must contain
   only the files listed in the ticket's "Files to be created", "Files
   to be modified", "New tests", and "Existing tests to update"
   sections. Any other modified file is a scope violation per
   ``CLAUDE.md`` §6.7 and §9.2.

5. **Every check must be green before review.**
   - ``pytest -x --no-cov`` passes locally.
   - ``ruff check src/ tests/ packages/`` clean.
   - ``ruff format --check src/ tests/ packages/`` clean.
   - ``mypy src/scistudio --ignore-missing-imports`` clean for core
     changes; ``mypy packages/scistudio-blocks-<plugin>/src
     --ignore-missing-imports`` clean for plugin changes.
   - ``python -m importlinter --config pyproject.toml`` clean (the
     ``Core must not depend on blocks/engine/api/ai/workflow``
     contract is load-bearing for Track 1 sub-1b).

6. **CHANGELOG.md** must be updated under ``[Unreleased]`` in the
   appropriate section (``Added`` / ``Changed`` / ``Fixed`` /
   ``Removed``) with full attribution per ``CLAUDE.md`` Appendix A
   Stage 6:
   ``[#N] Description (@claude, YYYY-MM-DD, branch: ..., session: ...)``.

7. **PR body must reference**:
   - The ADR section the PR implements
     (e.g. "Implements ADR-028 §D2").
   - The ticket ID from this standards doc
     (e.g. "Per ``docs/specs/phase11-implementation-standards.md``
     T-TRK-006").
   - For Tracks 2/3/4, the source-spec ticket ID (e.g. "Per
     ``docs/specs/phase11-imaging-block-spec.md`` T-IMG-019").
   - The previous PR in the stack (if any).
   - A reproduction of the ticket's acceptance criteria as a checklist
     with each box ticked when satisfied.

8. **No silent scope expansion.** If implementing a ticket reveals a
   pre-existing bug or design ambiguity, open a *new issue* describing
   it. Do not fix it inline. Per ``CLAUDE.md`` §9.2 and Appendix C
   Step 3.

9. **Scope-violation red flags (the audit-agent checklist).** Audit
   agents will reject any PR that exhibits any of the following
   patterns. Implementation agents must therefore avoid them:

   1. **Type relaxation** — weakening a type annotation from specific
      to general (``list[InputPort]`` → ``Any``, ``dict[str, int]`` →
      ``dict``, ``Image`` → ``DataObject``,
      ``InputPort | None`` → ``InputPort | Any``).
   2. **Assertion removal** — deleting or weakening a runtime
      assertion or validation that was in the original code.
   3. **Test expectation rewrite** — changing a test expectation
      instead of fixing the code under test.
   4. **Scope argument shrinkage** — narrowing a function's scope to
      avoid implementing the full contract (the spec says "handle
      Array, DataFrame, Series" but the PR only handles Array).
   5. **Silent exception swallowing** — adding ``except Exception:
      pass`` or ``except Exception: return None`` where the original
      raised.
   6. **Default fallback abuse** — using ``getattr(x, 'foo', None)``
      where the original did ``x.foo`` and the attribute is
      load-bearing.
   7. **Commenting out code** — commenting out a code path instead of
      fixing it.
   8. **"TODO: fix in follow-up" placeholders** for things that were
      supposed to be fixed *now*.

10. **Doc-external changes are restricted.** The user has granted
    permission for doc-external changes when tests reveal missing
    things, but only when scoped to the feature being tested. Any such
    change must be called out explicitly in the PR body and must not
    expand the ticket's diff beyond what is strictly necessary.

11. **Branch base.** Each ticket starts from ``origin/main`` (or the
    previous merged stacked branch). Never branch from ``main-local``
    once Phase 11 implementation begins; ``main-local`` is frozen per
    the master plan §10.

12. **One ticket = one PR.** The Phase 11 master plan §4.3 explicitly
    states *"default: one agent = one ticket = one PR"*. Bundling is
    only permitted when the change spans files that **only make sense
    together** (see §8 Q3 below for the documented coupling).

---

## 7. Universal acceptance criteria

In addition to each ticket's own acceptance criteria, every ticket
must satisfy these 10 items:

1. The PR's diff includes ONLY files listed in the ticket's "Files to
   be created", "Files to be modified", "New tests", and "Existing
   tests to update" sections. Any other modified file is a scope
   violation.
2. ``pytest -x --no-cov`` passes locally before push.
3. ``ruff check src/ tests/ packages/`` clean.
4. ``ruff format --check src/ tests/ packages/`` clean.
5. ``mypy`` (per scope) clean.
6. ``CHANGELOG.md`` has an entry under ``[Unreleased]`` in the
   appropriate section with full attribution per ``CLAUDE.md``
   Appendix A Stage 6.
7. Workflow gate has all 6 stages ``[DONE]``.
8. PR body explicitly references which ADR section it implements and
   links to this standards doc by ticket ID.
9. PR body reproduces the ticket's per-ticket acceptance criteria as
   a checklist with each item ticked.
10. CI is green on the PR before requesting review.

---

## 8. Open questions resolved by this document

These are decisions made in this document that go *beyond* the ADR
text and the source spec text. The ADRs and the source specs deferred
them to the implementation phase; this section records the resolution
so subsequent agents do not have to re-litigate them.

### Q1. Branch and ticket numbering scheme

**Decision**: Branch names follow ``<type>/issue-N/T-XXX-NNN-short``
where:

- ``<type>`` is one of ``feat``, ``fix``, ``refactor``, ``docs``,
  matching the conventional-commit prefix used in the commit message.
- ``N`` is the GitHub issue number for that specific ticket (a new
  issue per ticket, not the standards-doc issue #306).
- ``T-XXX-NNN`` is the ticket ID exactly as it appears in §9 / source
  spec, where ``XXX`` is one of ``TRK`` / ``IMG`` / ``SRS`` / ``LCMS``
  and ``NNN`` is zero-padded to three digits.
- ``short`` is a 2-5 word kebab-case description.

Ticket IDs are stable: T-TRK-006 always means "Block ABC dynamic-port
hooks + BlockSpec + framework read-path migration", regardless of
which agent picks it up.

### Q2. Where Sprint A sub-1c lands

**Decision**: T-TRK-011 (sub-1c) lives in **Sprint A Level A0**, in
parallel with the sub-1a deletion tickets and independent of the
sub-1b stacked cascade. It touches only ``CLAUDE.md``,
``docs/architecture/ARCHITECTURE.md`` (the ManualReview clarification
paragraph), and ``docs/guides/block-sdk.md``. None of those files are
touched by any sub-1b ticket, so there is no merge conflict.

Sub-1c does NOT depend on sub-1b being complete: the ManualReview
clarification is independent of the IOBlock refactor. Sub-1c is in
Sprint A purely for bookkeeping (it's part of the same "core cleanup"
master plan section), not because of a technical dependency.

### Q3. PR-B coupling resolution (Block ABC dynamic-port migration)

The Phase 11 master plan §4.3 lists three sub-PRs for Block ABC
dynamic-port hooks: PR-B-1 (Block ABC hooks + BlockSpec +
BlockSchemaResponse), PR-B-2 (framework read-path migration:
``Block.validate``, ``ProcessBlock.run``, ``workflow/validator.py``,
``api/routes/blocks.py``), and PR-B-3 (LoadData class).

**Decision**: PR-B-1 and PR-B-2 are **bundled into a single ticket
T-TRK-006** because splitting them would leave the codebase in a
broken intermediate state. Specifically:

- After PR-B-1 alone, the ``Block`` ABC has the new
  ``get_effective_*_ports()`` methods, and ``BlockSpec``/
  ``BlockSchemaResponse`` carry the new fields, but the framework
  callsites (``Block.validate``, ``ProcessBlock.run``, etc.) still
  read ``self.input_ports`` directly. Static blocks would still work,
  but if any block in the test suite happened to set
  ``dynamic_ports`` (even speculatively) the validator would silently
  use the wrong ports.
- After PR-B-1 alone, the BlockSchemaResponse would have a
  ``dynamic_ports`` field that the frontend cannot consume yet
  (frontend work is T-TRK-009), but no test would catch the broken
  intermediate.
- PR-B-2 alone is unimplementable: the framework callsites would call
  methods that don't exist on ``Block`` yet.

PR-B-1 + PR-B-2 must merge atomically. They are bundled into
**T-TRK-006**.

PR-B-3 (LoadData) is split off into its own ticket **T-TRK-007**
because it depends on PR-B-1+PR-B-2 but is otherwise self-contained
and is parallel-independent of T-TRK-008 (SaveData). T-TRK-007 and
T-TRK-008 are stacked on T-TRK-006 and run in parallel with each
other.

This bundling decision is the only place in the cascade where two
master-plan PRs collapse into one ticket. Every other coupling rule
was satisfiable by one-ticket-per-PR.

### Q4. Skeleton agent PR strategy

**Decision**: **One large skeleton PR covering all 4 tracks** instead
of four smaller per-track skeleton PRs. Rationale:

- The skeleton agent only creates placeholder files with
  ``raise NotImplementedError("T-XXX-NNN: ...")`` bodies. There is no
  business logic to review.
- A single PR makes it easier to verify completeness ("does the
  skeleton create a placeholder for every ticket in this standards
  doc?") via a single diff against ``main``.
- Splitting into four PRs would create cross-package dependencies
  (e.g. SRS skeleton imports from imaging skeleton) that would force
  one of the splits to merge first, defeating the parallelism
  argument for splitting.
- The skeleton PR is reviewed by the design/plan/skeleton audit agent,
  not by per-track audit agents, because completeness against this
  standards doc is the primary check.

### Q5. Test fixture pattern for cross-plugin imports

SRS tests need types from the imaging plugin (``Image``, ``Mask``,
``Label``). The imaging plugin is an optional dependency from the
core repo's perspective.

**Decision**: SRS tests that touch imaging types use
``pytest.importorskip("scistudio_blocks_imaging")`` at module top, plus
a session-scoped fixture in ``packages/scistudio-blocks-srs/tests/
conftest.py``::

    import pytest

    @pytest.fixture(scope="session")
    def imaging_types():
        imaging = pytest.importorskip("scistudio_blocks_imaging")
        return imaging  # caller does imaging_types.Image, .Mask, .Label

Tests that do not touch imaging types skip the fixture entirely. The
fixture is the **only** sanctioned way to import imaging-plugin types
from SRS tests; ad-hoc ``import scistudio_blocks_imaging`` at module
top (without ``importorskip``) breaks the SRS test suite when imaging
is not installed.

The same pattern applies to LC-MS tests that touch external tools
(ElMAVEN, AccuCor R) — see Q7 for the marker discipline.

### Q6. E2E test image access pattern

The four test images live at ``C:\Users\<user>\Desktop\workspace\
Example\images\``. Filenames contain spaces and parentheses.

**Decision**: Constants in ``tests/fixtures/test_images.py`` (a new
file owned by T-TRK-003 alongside the ``noop_block`` move):

    from pathlib import Path

    TEST_IMAGES_DIR = Path(r"C:\Users\<user>\Desktop\workspace\Example\images")

    K562_L_2845_TIF = TEST_IMAGES_DIR / "K562_L_2845 (uV).tif"
    K562_L_SPECTRA_TIF = TEST_IMAGES_DIR / "K562_L_spectra (uV).tif"
    K562_UL_2845_TIF = TEST_IMAGES_DIR / "K562_UL_2845 (uV).tif"
    K562_UL_SPECTRA_TIF = TEST_IMAGES_DIR / "K562_UL_spectra (uV).tif"

    SEGMENTATION_IMAGES = [K562_L_2845_TIF, K562_UL_2845_TIF]
    SPECTRA_IMAGES = [K562_L_SPECTRA_TIF, K562_UL_SPECTRA_TIF]

E2E tests import the constants instead of hardcoding paths. The
filename encoding (raw string for Windows backslashes; literal spaces
and parens) is centralised so a single test-image directory move only
requires one file edit.

If the ``TEST_IMAGES_DIR`` does not exist (CI environment), tests
that import from this fixture skip via
``pytest.importorskip`` style: ``pytest.skip("test images unavailable", allow_module_level=True)``
at the top of the test module after the path-existence check.

### Q7. Pytest markers introduced in Phase 11

**Decision**: The following pytest markers are introduced. Each must
be registered in the relevant ``pyproject.toml`` under
``[tool.pytest.ini_options].markers`` so that ``--strict-markers``
does not error. The registration is part of the ticket that first
uses the marker.

| Marker                   | Registered in                                | First-use ticket          |
|--------------------------|----------------------------------------------|---------------------------|
| ``requires_cellpose``    | ``packages/scistudio-blocks-imaging/pyproject.toml`` | T-IMG-019            |
| ``requires_napari``      | ``packages/scistudio-blocks-imaging/pyproject.toml`` | T-IMG-035            |
| ``requires_fiji``        | ``packages/scistudio-blocks-imaging/pyproject.toml`` | T-IMG-034 + T-TRK-015 |
| ``requires_cellprofiler``| ``packages/scistudio-blocks-imaging/pyproject.toml`` | T-IMG-036            |
| ``requires_qupath``      | ``packages/scistudio-blocks-imaging/pyproject.toml`` | T-IMG-037            |
| ``requires_r``           | ``pyproject.toml`` (root, for sub-1e) AND ``packages/scistudio-blocks-lcms/pyproject.toml`` (for AccuCor) | T-TRK-013 + T-LCMS-007 |
| ``requires_elmaven``     | ``packages/scistudio-blocks-lcms/pyproject.toml`` | T-LCMS-007             |
| ``requires_graphpad``    | ``packages/scistudio-blocks-lcms/pyproject.toml`` | T-LCMS-019             |
| ``requires_imaging``     | ``pyproject.toml`` (root, used by SRS tests) | (already registered Phase 10) |
| ``requires_lcms``        | ``pyproject.toml`` (root, used by integration tests) | T-LCMS-021         |

### Q8. Where markers register

**Decision**: Each plugin package registers its own markers in its
own ``pyproject.toml``. The root ``pyproject.toml`` only registers
markers used by tests in the core repo (``tests/`` directory).
Cross-package markers (``requires_imaging``, ``requires_lcms``) are
registered in the root because they are consumed by core integration
tests.

The first ticket in each plugin that introduces a new marker is
responsible for adding the registration line. Subsequent tickets in
the same plugin reuse the existing registration without modifying
``pyproject.toml`` (so that ticket diffs stay narrow).

### Q9. ADR-028 §D3 supersession check

ADR-028 §D3 originally specified six concrete loader/saver pairs
(``LoadArray``, ``LoadDataFrame``, ``LoadSeries``, ``LoadText``,
``LoadArtifact``, ``LoadCompositeData``) and six savers. ADR-028
Addendum 1 explicitly **supersedes** that with two dynamic blocks:
``LoadData`` + ``SaveData`` dispatching internally via private
module-level functions.

**Decision (anti-drift flag)**: Implementation agents reading
``docs/specs/phase11-imaging-block-spec.md`` may encounter references
to the original six-loader structure if the imaging spec was drafted
before the addendum landed. **The addendum overrides.** The core
repo's IO surface is ``LoadData`` / ``SaveData`` (one block each),
period. Any imaging-spec ticket that references "LoadArray" or
"LoadDataFrame" as a separate class is referring to a now-removed
design and must be reinterpreted as ``LoadData`` with the appropriate
``core_type`` config value.

This document **flags** the potential drift but does **not** fix it.
The audit agent reviewing the imaging-spec PRs must check each
implementation against this rule and reject any new code that
introduces a separate ``LoadArray`` / ``LoadDataFrame`` / etc. class
in core or in the imaging plugin.

### Q10. SRS ticket count discrepancy

The Phase 11 master plan §2.4 says the SRS plugin has ``~8 blocks``.
The actual SRS spec (``docs/specs/phase11-srs-block-spec.md``)
contains **11 blocks** (T-SRS-001 type + T-SRS-002..T-SRS-012 = 11
implementation tickets, plus T-SRS-000 scaffold + T-SRS-013
entry-point + T-SRS-014 integration test = 15 tickets total).

**Decision**: The **canonical count is 11 implementation blocks**
(documented in the SRS spec and reflected in §3 of this document as
15 tickets total). The master plan §2.4's "~8" was a rough estimate
during the doc-phase planning conversation. This standards doc and
the SRS spec are now authoritative.

### Q11. ImageCalculator port count for Phase 11

The imaging spec T-IMG-032 specifies ``ImageCalculator`` with two
fixed input ports (``A``, ``B``) plus a configurable expression. The
user-facing motivation for variadic input is to support arbitrary
N-port arithmetic.

**Decision**: ``ImageCalculator`` is **2-port-fixed in 0.1.0**. The
variadic version is deferred to ADR-029. The 2-port version satisfies
the immediate use cases (``A+B``, ``A-B``, ``A*B``, ``A/B``, plus a
restricted user-defined expression on the two named inputs); the
variadic version requires the ADR-029 mechanism that does not exist
yet. Implementation agents must not "anticipate" variadic by adding
optional ``C``, ``D``, ``E`` input ports.

### Q12. Test runner discovery for monorepo

Phase 11 introduces ``packages/scistudio-blocks-imaging/`` and
``packages/scistudio-blocks-srs/`` and ``packages/scistudio-blocks-lcms/``
each with their own ``tests/`` directory.

**Decision**: The root ``pyproject.toml`` ``[tool.pytest.ini_options]``
section gains a ``testpaths`` key that includes both the core
``tests`` directory and each plugin's ``tests`` directory::

    [tool.pytest.ini_options]
    testpaths = [
        "tests",
        "packages/scistudio-blocks-imaging/tests",
        "packages/scistudio-blocks-srs/tests",
        "packages/scistudio-blocks-lcms/tests",
    ]
    rootdir = "."

Plugin-package tests run via the same ``pytest`` invocation as core
tests. Each plugin package also has its own ``pyproject.toml`` so a
normal package install into a clean virtual environment works standalone
for downstream consumers.

This decision is implemented incrementally: T-IMG-038 / T-SRS-013 /
T-LCMS-020 each add their plugin's ``tests`` path to the root config
when the plugin first becomes installable. The first plugin
(imaging) lands the initial monorepo testpaths config; later plugins
extend it.

---

## 9. Per-ticket sections

Each Track 1 ticket uses these 13 subsections:

a. Ticket ID and name
b. Source ADR / spec sections
c. Files to be created
d. Files to be modified
e. Files to be deleted
f. New tests
g. Existing tests to update
h. Implementation details
i. Acceptance criteria
j. Out of scope
k. Dependencies on other tickets
l. Estimated diff size (XS / S / M / L / XL)
m. Coupling notes (Standalone / Bundled / Sequential)

Tracks 2 / 3 / 4 use a compact reference format because the
per-ticket implementation details live in the corresponding source
spec. Each compact entry has: title + source spec pointer + summary +
files + dependencies + estimated diff + coupling notes.

### 9.1 Track 1 — core block cleanup and ADR-028 implementation

---

### T-TRK-001 — Delete ``process/contrib/`` stub directory

**a. Ticket ID and name**: T-TRK-001 — Delete ``process/contrib/``
stub directory and its four placeholder files.

**b. Source ADR / spec sections**:
- Phase 11 master plan §2.5 sub-1a (delete-stubs list).
- ``CLAUDE.md`` §9.4 (incomplete skeletons may be intentionally
  empty; this ticket explicitly removes a set that is *not*
  intentional, per master plan).

**c. Files to be created**: none.

**d. Files to be modified**: none. (The directory is deleted in its
entirety; no surrounding ``__init__.py`` references it.)

**e. Files to be deleted**:
- ``src/scistudio/blocks/process/contrib/cellpose_segment.py`` (1-line
  stub)
- ``src/scistudio/blocks/process/contrib/spectral_pca.py`` (1-line
  stub)
- ``src/scistudio/blocks/process/contrib/baseline_correction.py``
  (1-line stub)
- ``src/scistudio/blocks/process/contrib/__init__.py`` (1-line stub)
- ``src/scistudio/blocks/process/contrib/`` directory itself

**f. New tests**: none.

**g. Existing tests to update**:
- Grep ``tests/`` for any import of ``scistudio.blocks.process.contrib``;
  remove or replace each. Expected hits: zero, because every file in
  the directory is a 1-line stub. The grep is part of the acceptance
  criteria; if it returns hits, escalate as a separate issue rather
  than expanding scope.

**h. Implementation details**:
1. ``git rm -r src/scistudio/blocks/process/contrib/``
2. ``git grep "scistudio.blocks.process.contrib"`` — must return 0 hits
   in non-deleted files.
3. ``git grep "from scistudio.blocks.process import contrib"`` — must
   return 0 hits.
4. Run ``pytest -x --no-cov tests/blocks/`` to confirm no test
   imports from the deleted directory.

**i. Acceptance criteria**:
- The four files and the directory no longer exist.
- ``git grep`` for the deleted module path returns 0 hits.
- ``pytest -x --no-cov`` is green.
- All universal AC items (§7) are satisfied.

**j. Out of scope**:
- Do **not** also delete ``process/builtins/register.py`` (separate
  ticket T-TRK-002).
- Do **not** also move ``transform.py`` (separate ticket T-TRK-003).
- Do **not** add new ``contrib`` blocks "to fill the gap" — the
  contrib pattern is being abandoned in favour of the plugin
  package pattern.

**k. Dependencies**: none. Independent of every other ticket.

**l. Estimated diff size**: XS (5 file deletions, ~5 line removals
total).

**m. Coupling notes**: Standalone. Runs in parallel with T-TRK-002,
T-TRK-003, T-TRK-011 in Sprint A Level A0.

---

### T-TRK-002 — Delete ``process/builtins/register.py``

**a. Ticket ID and name**: T-TRK-002 — Delete the
``process/builtins/register.py`` 1-line stub.

**b. Source ADR / spec sections**:
- Phase 11 master plan §2.5 sub-1a.

**c. Files to be created**: none.

**d. Files to be modified**:
- ``src/scistudio/blocks/process/builtins/__init__.py`` — remove any
  ``from .register import ...`` line if present.

**e. Files to be deleted**:
- ``src/scistudio/blocks/process/builtins/register.py`` (1-line stub)

**f. New tests**: none.

**g. Existing tests to update**: grep for
``scistudio.blocks.process.builtins.register``; remove any test imports.

**h. Implementation details**:
1. Read ``register.py`` to confirm it is a 1-line stub (verify the
   master plan claim before deleting).
2. ``git rm src/scistudio/blocks/process/builtins/register.py``
3. Edit ``__init__.py`` to remove any reference.
4. ``git grep "blocks.process.builtins.register"`` — must be 0 hits.

**i. Acceptance criteria**:
- File deleted, ``__init__.py`` updated.
- ``git grep`` returns 0 hits.
- All universal AC items satisfied.

**j. Out of scope**: do not touch ``transform.py`` (T-TRK-003) or
``filter_collection.py`` (T-TRK-012).

**k. Dependencies**: none. Independent.

**l. Estimated diff size**: XS (1 file deletion, ~1 line removed in
``__init__.py``).

**m. Coupling notes**: Standalone. Sprint A Level A0 parallel.

---

### T-TRK-003 — Move ``transform.py`` → ``tests/fixtures/noop_block.py``

**a. Ticket ID and name**: T-TRK-003 — Relocate the smoke-test
``TransformBlock`` from ``src/scistudio/blocks/process/builtins/`` to
``tests/fixtures/`` and rename to ``NoopBlock``.

**b. Source ADR / spec sections**:
- Phase 11 master plan §2.5 sub-1a (relocate ``transform.py``).
- Master plan rationale: this block is **not a placeholder** — it is
  the smoke-test fixture for CI, just miscategorised.

**c. Files to be created**:
- ``tests/fixtures/noop_block.py`` (new — body copied from old
  ``transform.py``, class renamed ``TransformBlock`` →
  ``NoopBlock``, ``type_name`` changed to ``"noop"``).
- ``tests/fixtures/test_images.py`` (new — the E2E test image
  constants per Q6 above). This file is owned by T-TRK-003 because
  it is in the same ``tests/fixtures/`` directory and the move is
  the natural place to introduce the fixtures package.

**d. Files to be modified**:
- ``src/scistudio/blocks/process/builtins/__init__.py`` — remove
  ``TransformBlock`` import / re-export.
- All test files that import ``TransformBlock`` from
  ``scistudio.blocks.process.builtins.transform``: rewrite to
  ``from tests.fixtures.noop_block import NoopBlock``.

**e. Files to be deleted**:
- ``src/scistudio/blocks/process/builtins/transform.py``

**f. New tests**:
- ``tests/fixtures/test_noop_block.py`` — minimal smoke test that
  ``NoopBlock`` instantiates and ``run({...})`` returns the input
  unchanged.

**g. Existing tests to update**:
- Every existing test that constructs ``TransformBlock(...)``: rename
  to ``NoopBlock(...)`` and update the import line.
- ``git grep "TransformBlock"`` — must hit only the new
  ``NoopBlock`` definition and possibly historical CHANGELOG entries.

**h. Implementation details**:
1. Read the current ``transform.py`` body. Confirm it is a no-op
   pass-through block (per master plan).
2. Create ``tests/fixtures/__init__.py`` if it does not exist.
3. Create ``tests/fixtures/noop_block.py`` with the relocated body,
   renamed class, and new ``type_name = "noop"``.
4. Create ``tests/fixtures/test_images.py`` per Q6.
5. ``git rm src/scistudio/blocks/process/builtins/transform.py``
6. Update ``__init__.py``.
7. ``git grep "TransformBlock"`` and rewrite each hit.
8. Run ``pytest -x --no-cov`` and confirm green.

**i. Acceptance criteria**:
- ``tests/fixtures/noop_block.py`` exists, defines ``NoopBlock``.
- ``tests/fixtures/test_images.py`` exists with the four image
  constants and the two derived lists.
- Old ``transform.py`` deleted.
- ``__init__.py`` no longer references ``TransformBlock``.
- All ``TransformBlock`` references in tests are now ``NoopBlock``.
- ``pytest -x --no-cov`` green.
- All universal AC items satisfied.

**j. Out of scope**:
- Do not change any ``NoopBlock`` behaviour (it is a literal
  pass-through; the test fixture relies on identity-out = identity-in).
- Do not introduce new test fixtures beyond the two named files.

**k. Dependencies**: none. Independent of T-TRK-001 / T-TRK-002 /
T-TRK-011.

**l. Estimated diff size**: S (~80 lines changed across ~5 test files).

**m. Coupling notes**: Standalone. Sprint A Level A0 parallel.

---

### T-TRK-004 — Delete ``adapters/`` and rewrite ``io_block.py`` as ABC

**a. Ticket ID and name**: T-TRK-004 — Delete the entire
``src/scistudio/blocks/io/adapters/`` directory and
``adapter_registry.py``, and rewrite ``src/scistudio/blocks/io/
io_block.py`` as an abstract base class with ``load()`` / ``save()``
abstract methods plus a default ``run()`` dispatch.

**b. Source ADR / spec sections**:
- ADR-028 §D1 (IOBlock becomes abstract base).
- ADR-028 §D2 (delete adapters directory + adapter_registry).
- ADR-028 §D4 (delete ``scistudio.adapters`` entry-point group).
- Phase 11 master plan §2.1 + §2.5 sub-1b PR-A and PR-A-2 (this
  ticket bundles the original PR-A + PR-A-2 because rewriting
  ``io_block.py`` is unimplementable while ``adapter_registry.py``
  still imports from the deleted ``adapters/`` package).

**c. Files to be created**: none.

**d. Files to be modified**:
- ``src/scistudio/blocks/io/io_block.py`` — full rewrite. After this
  ticket, the body is approximately::

      """IOBlock — abstract base for plugin-owned data ingress and egress."""

      from __future__ import annotations
      from abc import abstractmethod
      from pathlib import Path
      from typing import Any, ClassVar

      from scistudio.blocks.base.block import Block
      from scistudio.blocks.base.config import BlockConfig
      from scistudio.blocks.base.ports import InputPort, OutputPort
      from scistudio.core.types.base import DataObject
      from scistudio.core.types.collection import Collection


      class IOBlock(Block):
          """Abstract base for blocks that load or save data.

          Subclasses must override ``load()`` (for direction='input')
          or ``save()`` (for direction='output'). The default ``run()``
          dispatches based on ``direction``.
          """

          direction: ClassVar[str] = "input"
          category: ClassVar[str] = "io"

          input_ports: ClassVar[list[InputPort]] = [
              InputPort(name="data", accepted_types=[DataObject], required=False),
          ]
          output_ports: ClassVar[list[OutputPort]] = [
              OutputPort(name="data", accepted_types=[DataObject]),
          ]
          config_schema: ClassVar[dict[str, Any]] = {
              "type": "object",
              "properties": {"path": {"type": "string", "ui_priority": 1}},
              "required": ["path"],
          }

          @abstractmethod
          def load(self, config: BlockConfig) -> DataObject | Collection:
              """Load and return a single DataObject or Collection."""
              ...

          @abstractmethod
          def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
              """Persist *obj* to the configured path."""
              ...

          def run(self, inputs, config):
              if self.direction == "input":
                  result = self.load(config)
                  if not isinstance(result, Collection):
                      result = Collection(items=[result], item_type=type(result))
                  return {"data": result}
              else:
                  data = inputs.get("data")
                  if data is None:
                      raise ValueError("IOBlock(output) requires 'data' input")
                  self.save(data, config)
                  return {"path": str(config.get("path"))}

- ``pyproject.toml`` — remove the ``[project.entry-points."scistudio.adapters"]``
  table entirely (ADR-028 §D4 supersedes ADR-025 §6).

**e. Files to be deleted**:
- ``src/scistudio/blocks/io/adapters/__init__.py``
- ``src/scistudio/blocks/io/adapters/base.py``
- ``src/scistudio/blocks/io/adapters/csv_adapter.py``
- ``src/scistudio/blocks/io/adapters/parquet_adapter.py``
- ``src/scistudio/blocks/io/adapters/zarr_adapter.py``
- ``src/scistudio/blocks/io/adapters/generic_adapter.py``
- ``src/scistudio/blocks/io/adapters/tiff_adapter.py``
- ``src/scistudio/blocks/io/adapters/mzxml_adapter.py``
- ``src/scistudio/blocks/io/adapters/h5ad_adapter.py``
- ``src/scistudio/blocks/io/adapters/fcs_adapter.py``
- ``src/scistudio/blocks/io/adapters/`` directory itself
- ``src/scistudio/blocks/io/adapter_registry.py``
- Any ``tests/blocks/io/test_*_adapter.py`` files. (Grep first; the
  expected count is 4-8 files.)

**f. New tests**:
- ``tests/blocks/io/test_io_block_abc.py`` — verifies that
  ``IOBlock()`` cannot be instantiated directly (TypeError because
  ``load`` and ``save`` are abstract); a minimal in-memory subclass
  satisfies the contract.

**g. Existing tests to update**:
- Any test that imports from ``scistudio.blocks.io.adapters.*`` must be
  deleted or rewritten. Grep before deleting.
- Any test that constructs ``IOBlock(direction=...)`` directly will
  need to use a minimal ``InMemoryIOBlock`` test fixture instead.
  Add the fixture to ``tests/blocks/io/conftest.py``.

**h. Implementation details**:
1. ``git rm -r src/scistudio/blocks/io/adapters/``
2. ``git rm src/scistudio/blocks/io/adapter_registry.py``
3. Rewrite ``io_block.py`` per the body above.
4. Edit ``pyproject.toml`` to remove the ``scistudio.adapters``
   entry-point table.
5. Grep for ``from scistudio.blocks.io.adapter_registry`` and
   ``from scistudio.blocks.io.adapters`` — every hit must be deleted
   or refactored to the new pattern.
6. Run ``pytest -x --no-cov``. Expect failures only in tests that
   imported the deleted adapter modules; delete or rewrite those
   tests as part of this PR.
7. Run ``python -m importlinter --config pyproject.toml``. The
   ``Core must not depend on blocks/engine/api/ai/workflow``
   contract is unaffected by this ticket but verify it remains green.

**i. Acceptance criteria**:
- ``src/scistudio/blocks/io/adapters/`` and
  ``src/scistudio/blocks/io/adapter_registry.py`` no longer exist.
- ``IOBlock`` cannot be instantiated directly (the new test asserts
  ``TypeError``).
- ``pyproject.toml`` no longer has any ``scistudio.adapters``
  entry-point group.
- ``pytest -x --no-cov`` green.
- ``ruff check`` clean.
- ``mypy`` clean.
- ``importlinter`` clean.
- All universal AC items satisfied.

**j. Out of scope**:
- Do **not** add ``LoadData`` or ``SaveData`` here — those are
  T-TRK-007 and T-TRK-008.
- Do **not** add ``Block.get_effective_input_ports()`` here — that
  is T-TRK-006.
- Do **not** touch ``frontend/`` here — that is T-TRK-009.
- Do **not** touch ``ARCHITECTURE.md`` here — that is T-TRK-010.

**k. Dependencies**: T-TRK-001 / T-TRK-002 / T-TRK-003 ideally
merged first (clean repo state), but technically T-TRK-004 only
**hard-depends** on the absence of any test that imports from the
deleted adapter modules (which is unrelated to T-TRK-001..003). For
schedule simplicity treat T-TRK-004 as Sprint A Level A1, after
Level A0 is fully merged.

**l. Estimated diff size**: M-L (~12 file deletions + 1 large
rewrite + ~5 test files updated).

**m. Coupling notes**: **Bundled**. The original master plan §4.3
listed PR-A (delete adapters) and PR-A-2 (rewrite io_block.py) as
two stacked PRs. They are bundled into T-TRK-004 because rewriting
``io_block.py`` is unimplementable while ``adapter_registry.py``
still exists (the current ``IOBlock.run`` imports from
``adapter_registry`` at line 63). Deleting the adapter layer and
rewriting the consumer must happen atomically.

---

### T-TRK-005 — (intentionally absent — bundled into T-TRK-004)

T-TRK-005 was reserved during early decomposition for "rewrite
``io_block.py`` as ABC", but per the coupling rule in §8 Q3 it has
been **bundled into T-TRK-004**. The ticket ID is reserved (no
re-use) so that ticket numbering remains stable across this document
and future references in PR descriptions and CHANGELOG entries. No
agent picks up T-TRK-005.

---

### T-TRK-006 — Block ABC dynamic-port hooks + framework migration

**a. Ticket ID and name**: T-TRK-006 — Add
``get_effective_input_ports()`` / ``get_effective_output_ports()`` /
``dynamic_ports`` ClassVar to ``Block`` ABC, extend ``BlockSpec`` and
``BlockSchemaResponse`` with the new fields, and migrate every
framework callsite that reads ``input_ports`` / ``output_ports`` to
use the new effective-ports methods.

**b. Source ADR / spec sections**:
- ADR-028 Addendum 1 §C ("Decision: dynamic port override mechanism")
  decisions D1 through D7.
- ADR-028 Addendum 1 §D ("Framework read-path migration").
- Phase 11 master plan §4.3 (PR-B-1, PR-B-2, PR-B-3 — bundled per Q3).

**c. Files to be created**: none. (Tests added below.)

**d. Files to be modified**:
- ``src/scistudio/blocks/base/block.py`` — add::

      input_ports: ClassVar[list[InputPort]] = []
      output_ports: ClassVar[list[OutputPort]] = []
      dynamic_ports: ClassVar[dict[str, Any] | None] = None

      def get_effective_input_ports(self) -> list[InputPort]:
          """Return effective input ports for this instance.
          Default: return type(self).input_ports. Dynamic blocks override."""
          return list(type(self).input_ports)

      def get_effective_output_ports(self) -> list[OutputPort]:
          return list(type(self).output_ports)

  And update ``Block.validate(...)`` to read
  ``self.get_effective_input_ports()`` instead of ``self.input_ports``
  directly. The existing ``port_map = {p.name: p for p in self.input_ports}``
  becomes ``port_map = {p.name: p for p in self.get_effective_input_ports()}``.

- ``src/scistudio/blocks/process/process_block.py`` (or wherever
  ``ProcessBlock.run`` lives) — when inferring output Collection
  ``item_type``, read ``self.get_effective_output_ports()`` instead
  of the ClassVar.

- ``src/scistudio/workflow/validator.py`` — when validating connection
  compatibility, construct a temporary block instance from the
  workflow node's config and call
  ``block.get_effective_input_ports()`` /
  ``get_effective_output_ports()`` to get per-instance ports for
  type checking.

- ``src/scistudio/blocks/registry.py`` — extend ``BlockSpec`` dataclass::

      direction: str = ""
      dynamic_ports: dict[str, Any] | None = None

  And in ``BlockRegistry._build_spec`` (or equivalent), populate
  these from the class::

      direction=getattr(cls, "direction", ""),
      dynamic_ports=getattr(cls, "dynamic_ports", None),

  Add ``BlockRegistry._validate_dynamic_ports(cls)`` that validates
  the ``dynamic_ports`` dict shape at scan time and raises a
  descriptive error if malformed (missing ``source_config_key``,
  ``output_port_mapping`` not a dict, enum-value lists not lists of
  strings, etc.).

- ``src/scistudio/api/schemas.py`` — extend ``BlockSchemaResponse``::

      class BlockSchemaResponse(BlockSummary):
          config_schema: dict[str, Any] = Field(default_factory=dict)
          type_hierarchy: list[TypeHierarchyEntry] = Field(default_factory=list)
          dynamic_ports: dict[str, Any] | None = None  # ADR-028 Addendum 1 D4
          direction: str | None = None                 # ADR-028 Addendum 1 D8

- ``src/scistudio/api/routes/blocks.py`` — in ``_summary()`` and
  ``_schema_response()`` (or whatever the response builders are
  called), populate the new fields from the BlockSpec.

**e. Files to be deleted**: none.

**f. New tests**:
- ``tests/blocks/base/test_dynamic_ports.py`` — covers:
  - ``get_effective_input_ports()`` default returns the ClassVar.
  - ``get_effective_output_ports()`` default returns the ClassVar.
  - A subclass that overrides ``get_effective_output_ports`` returns
    the override.
  - ``BlockSpec.dynamic_ports`` is populated from the class.
  - ``BlockRegistry._validate_dynamic_ports`` raises on malformed
    dict (missing ``source_config_key``, etc.).
  - ``BlockSchemaResponse(dynamic_ports={...}, direction="input")``
    serialises correctly via Pydantic.
- ``tests/workflow/test_validator_dynamic_ports.py`` — covers:
  - A dynamic block in a workflow validates correctly when its
    config drives the effective output type.
  - Connection validation rejects an incompatible type via the
    effective ports.

**g. Existing tests to update**:
- Any test that asserts on ``BlockSchemaResponse`` shape: extend the
  expected dict to include the new optional fields.
- Any test that asserts on ``BlockSpec`` shape: extend similarly.

**h. Implementation details**:

This is the load-bearing structural change for ADR-028 Addendum 1.
The implementation is small (each diff is single-digit lines) but
spans many files; the audit risk is *missing* a callsite, not the
size of any individual change.

**Required audit before submitting the PR**: grep the codebase for
every read of ``.input_ports`` and ``.output_ports`` on ``self`` and
on block instances::

    git grep -n "self\.input_ports" src/
    git grep -n "self\.output_ports" src/
    git grep -n "\.input_ports" src/scistudio/workflow/
    git grep -n "\.output_ports" src/scistudio/workflow/
    git grep -n "\.input_ports" src/scistudio/api/
    git grep -n "\.output_ports" src/scistudio/api/

For each hit, decide: keep the ClassVar read (because it's a class
introspection from registry scan) or migrate to the effective-ports
method (because it's an instance read at runtime). Migrate in the
same PR; do not split.

The two pure introspection sites that *should not change* are:
- ``BlockRegistry._build_spec`` reads the class-level ClassVar to
  populate ``BlockSpec``. This is correct (the spec is class-level
  metadata, not instance-level).
- ``BlockSummary._build_for_palette`` reads the class-level ClassVar
  for the palette display. Also correct.

Every other read is a runtime read on an instance and must migrate.

**i. Acceptance criteria**:
- ``Block`` has the three new attributes / two new methods.
- Every runtime read of ``input_ports`` / ``output_ports`` on a
  block instance has migrated.
- ``BlockSpec`` has the two new fields.
- ``BlockSchemaResponse`` has the two new fields.
- ``BlockRegistry._validate_dynamic_ports`` rejects malformed dicts.
- All new tests pass.
- No existing tests regress.
- All universal AC items satisfied.

**j. Out of scope**:
- Do **not** add ``LoadData`` here — that is T-TRK-007.
- Do **not** add ``SaveData`` here — that is T-TRK-008.
- Do **not** touch ``frontend/`` here — that is T-TRK-009.
- Do **not** add variadic-port-count support — that is ADR-029 and
  is hard-frozen.

**k. Dependencies**: T-TRK-004 (the ABC must exist before the
dynamic-port hooks attach to it).

**l. Estimated diff size**: M (~6 source files modified, 2 new test
files, ~250 lines).

**m. Coupling notes**: **Bundled** (PR-B-1 + PR-B-2). Per §8 Q3,
splitting these into separate PRs would leave the codebase in a
broken intermediate state. PR-B-3 (LoadData) is split off as
T-TRK-007 because LoadData depends on but does not couple to the
ABC migration.

---

### T-TRK-007 — ``LoadData`` class + 6 private ``_load_*`` functions

**a. Ticket ID and name**: T-TRK-007 — Implement
``src/scistudio/blocks/io/loaders/load_data.py`` containing the
``LoadData`` class plus six private module-level dispatch functions.

**b. Source ADR / spec sections**:
- ADR-028 §D3 (originally six loader classes, **superseded** by
  Addendum 1 §C9 with ``LoadData`` + private functions).
- ADR-028 Addendum 1 §C5 (hardcoded ``_CORE_TYPE_MAP``).
- ADR-028 Addendum 1 §C9 (private functions, not helper classes).
- Phase 11 master plan §2.2 (``LoadData`` reference body).

**c. Files to be created**:
- ``src/scistudio/blocks/io/loaders/__init__.py`` — re-exports
  ``LoadData``.
- ``src/scistudio/blocks/io/loaders/load_data.py`` — contains the
  ``LoadData`` class and the six ``_load_*`` private functions.

  *Path-D update (issue #1459, Phase 2 of #1427)*: the module-level
  helper functions originally co-located in ``load_data.py`` were later
  extracted to private sibling modules so the file stays under the
  750-LOC god-file threshold. The sibling modules
  ``loaders/_capability.py`` (FormatCapability declarations +
  ``_LOAD_EXTENSION_MAP`` + ``_resolve_format``) and ``loaders/_helpers.py``
  (``_resolve_path``, ``_check_pickle_allowed``, ``_CORE_TYPE_MAP``,
  ``_TEXT_FORMAT_MAP``, ``_MIME_GUESS``) hold module-level private
  functions only — ADR-028 Addendum 1 §C9 ("private functions, not
  helper classes") is satisfied verbatim because no helper module
  defines a class. The reference code sketch below (lines 1411-1453) is
  illustrative; the actual layout uses these siblings to keep individual
  files focused.

**d. Files to be modified**:
- ``src/scistudio/blocks/io/__init__.py`` — re-export ``LoadData``.
- ``pyproject.toml`` — register ``LoadData`` under
  ``[project.entry-points."scistudio.blocks"]`` so it appears in the
  block palette.

**e. Files to be deleted**: none.

**f. New tests**:
- ``tests/blocks/io/test_load_data.py`` — covers:
  - ``LoadData`` instantiates with each of the six ``core_type``
    enum values.
  - ``get_effective_output_ports()`` returns the correct
    ``OutputPort.accepted_types`` for each enum value.
  - End-to-end load round-trip for each of the six core types via
    a tmp_path fixture (CSV → DataFrame, JSON → DataFrame,
    npy → Array, txt → Text, ``.bin`` → Artifact, JSON-bundle
    → CompositeData).
  - ``allow_pickle=False`` rejects ``.pkl`` / ``.pickle`` paths
    with a clear ValueError.
  - ``allow_pickle=True`` reads pickle files (with explicit
    security warning logged at WARNING level).

**g. Existing tests to update**: none directly. Some end-to-end
workflow tests may use ``IOBlock(format="csv")`` style invocations
that no longer work; rewrite to ``LoadData(config={"core_type":
"DataFrame", "path": ...})``.

**h. Implementation details**:

Implementation skeleton (canonical body — implementation agent
follows this exactly)::

    """LoadData — dynamic-port core IO loader (ADR-028 Addendum 1)."""

    from __future__ import annotations
    from pathlib import Path
    from typing import Any, ClassVar

    from scistudio.blocks.base.config import BlockConfig
    from scistudio.blocks.base.ports import OutputPort
    from scistudio.blocks.io.io_block import IOBlock
    from scistudio.core.types.array import Array
    from scistudio.core.types.artifact import Artifact
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.composite import CompositeData
    from scistudio.core.types.dataframe import DataFrame
    from scistudio.core.types.series import Series
    from scistudio.core.types.text import Text


    _CORE_TYPE_MAP: dict[str, type[DataObject]] = {
        "Array": Array,
        "DataFrame": DataFrame,
        "Series": Series,
        "Text": Text,
        "Artifact": Artifact,
        "CompositeData": CompositeData,
    }


    class LoadData(IOBlock):
        direction = "input"
        type_name = "load_data"
        name = "Load Data"
        category = "io"

        output_ports: ClassVar[list[OutputPort]] = [
            OutputPort(name="data", accepted_types=[DataObject]),
        ]

        dynamic_ports: ClassVar[dict[str, Any] | None] = {
            "source_config_key": "core_type",
            "output_port_mapping": {
                "data": {
                    "Array":         ["Array"],
                    "DataFrame":     ["DataFrame"],
                    "Series":        ["Series"],
                    "Text":          ["Text"],
                    "Artifact":      ["Artifact"],
                    "CompositeData": ["CompositeData"],
                },
            },
        }

        config_schema: ClassVar[dict[str, Any]] = {
            "type": "object",
            "properties": {
                "core_type": {
                    "type": "string",
                    "enum": list(_CORE_TYPE_MAP.keys()),
                    "default": "DataFrame",
                    "ui_priority": 0,
                },
                "path": {"type": "string", "ui_priority": 1},
                "allow_pickle": {
                    "type": "boolean",
                    "default": False,
                    "ui_priority": 2,
                },
            },
            "required": ["core_type", "path"],
        }

        def get_effective_output_ports(self) -> list[OutputPort]:
            type_name = self.config.get("core_type", "DataFrame")
            cls = _CORE_TYPE_MAP.get(type_name, DataFrame)
            return [OutputPort(name="data", accepted_types=[cls])]

        def load(self, config: BlockConfig) -> DataObject:
            type_name = config.get("core_type", "DataFrame")
            dispatch = {
                "Array": _load_array,
                "DataFrame": _load_dataframe,
                "Series": _load_series,
                "Text": _load_text,
                "Artifact": _load_artifact,
                "CompositeData": _load_composite_data,
            }
            if type_name not in dispatch:
                raise ValueError(f"Unknown core_type: {type_name}")
            return dispatch[type_name](config)

        def save(self, obj, config):
            raise NotImplementedError("LoadData is input-only; use SaveData")


    # Module-level private dispatch functions (NOT helper classes per Addendum 1).

    def _load_array(config: BlockConfig) -> Array:
        """Load Array from .npy / .npz / .zarr / .parquet (single column)."""
        ...

    def _load_dataframe(config: BlockConfig) -> DataFrame:
        """Load DataFrame from .csv / .tsv / .parquet / .json / .pkl."""
        ...

    def _load_series(config: BlockConfig) -> Series:
        """Load Series from .csv / .tsv / .parquet (single column) / .pkl."""
        ...

    def _load_text(config: BlockConfig) -> Text:
        """Load Text from .txt / .md / .html / .xml / .log / .yaml / .toml."""
        ...

    def _load_artifact(config: BlockConfig) -> Artifact:
        """Load opaque Artifact from any file (raw bytes + metadata)."""
        ...

    def _load_composite_data(config: BlockConfig) -> CompositeData:
        """Load CompositeData from a JSON manifest pointing at sidecar files."""
        ...

The six private functions absorb the logic from the deleted
``csv_adapter.py``, ``parquet_adapter.py``, ``zarr_adapter.py``, and
``generic_adapter.py``. ``allow_pickle`` gating happens inside
``_load_dataframe`` / ``_load_series`` / ``_load_array`` whenever the
file extension is ``.pkl`` or ``.pickle``.

**i. Acceptance criteria**:
- ``LoadData`` is importable from ``scistudio.blocks.io``.
- ``LoadData`` is registered in ``pyproject.toml`` entry-points.
- ``get_effective_output_ports()`` returns the correct
  ``OutputPort`` for every enum value.
- All six dispatch functions are implemented and tested.
- ``allow_pickle`` opt-in behaviour is correct (raises by default,
  loads when set).
- ``ruff`` / ``mypy`` clean.
- All universal AC items satisfied.

**j. Out of scope**:
- Do **not** add ``SaveData`` — that is T-TRK-008.
- Do **not** add format-specific tests for plugin types
  (TIFF, mzML, h5ad, fcs) — those formats live in plugin packages.
- Do **not** add a "convenience" 7th type beyond the six core types.

**k. Dependencies**: T-TRK-006 (Block ABC dynamic-port hooks must
exist before ``LoadData`` can override ``get_effective_output_ports``).

**l. Estimated diff size**: M (~400 lines: ~150 LoadData + ~150
dispatch helpers + ~100 tests).

**m. Coupling notes**: Stacked on T-TRK-006. Runs in parallel with
T-TRK-008 (SaveData).

---

### T-TRK-008 — ``SaveData`` class + 6 private ``_save_*`` functions

**a. Ticket ID and name**: T-TRK-008 — Implement
``src/scistudio/blocks/io/savers/save_data.py`` containing the
``SaveData`` class plus six private module-level dispatch functions.

**b. Source ADR / spec sections**:
- ADR-028 §D3 (originally six saver classes, **superseded** by
  Addendum 1 §C9).
- ADR-028 Addendum 1 §C5 + §C9.

**c. Files to be created**:
- ``src/scistudio/blocks/io/savers/__init__.py``
- ``src/scistudio/blocks/io/savers/save_data.py``

  *Path-D update (issue #1459, Phase 2 of #1427)*: the module-level
  helper functions originally co-located in ``save_data.py`` were later
  extracted to private sibling modules so the file stays under the
  750-LOC god-file threshold. The sibling modules
  ``savers/_capability.py`` (FormatCapability declarations +
  ``_SAVE_EXTENSION_MAP`` + ``_resolve_save_format``),
  ``savers/_helpers.py`` (``_require_path``, ``_check_pickle_gate``,
  ``_unwrap_for_save``, ``_CORE_TYPE_MAP``, per-format coercion
  helpers), and ``savers/_streaming.py`` (ADR-031 Phase 3 zero-
  materialisation export paths) hold module-level private functions
  only — ADR-028 Addendum 1 §C9 ("private functions, not helper
  classes") is satisfied verbatim because no helper module defines a
  class. The reference code sketch below is illustrative.

**d. Files to be modified**:
- ``src/scistudio/blocks/io/__init__.py`` — re-export ``SaveData``.
- ``pyproject.toml`` — register ``SaveData`` entry-point.

**e. Files to be deleted**: none.

**f. New tests**:
- ``tests/blocks/io/test_save_data.py`` — symmetric with
  ``test_load_data.py``: round-trip each of the six core types
  through SaveData → LoadData and assert equality.

**g. Existing tests to update**: none directly.

**h. Implementation details**:

The ``SaveData`` class mirrors ``LoadData`` but takes input on the
``data`` input port instead of producing output, and uses
``get_effective_input_ports()`` (not output) to update the accepted
type from the ``core_type`` enum::

    class SaveData(IOBlock):
        direction = "output"
        type_name = "save_data"
        name = "Save Data"
        category = "io"

        input_ports: ClassVar[list[InputPort]] = [
            InputPort(name="data", accepted_types=[DataObject], required=True),
        ]
        output_ports: ClassVar[list[OutputPort]] = []

        dynamic_ports: ClassVar[dict[str, Any] | None] = {
            "source_config_key": "core_type",
            "input_port_mapping": {
                "data": {
                    "Array":         ["Array"],
                    "DataFrame":     ["DataFrame"],
                    ...
                },
            },
        }

        # config_schema mirrors LoadData; load() raises NotImplementedError.

        def get_effective_input_ports(self) -> list[InputPort]:
            type_name = self.config.get("core_type", "DataFrame")
            cls = _CORE_TYPE_MAP.get(type_name, DataFrame)
            return [InputPort(name="data", accepted_types=[cls], required=True)]

        def save(self, obj, config):
            type_name = config.get("core_type", "DataFrame")
            dispatch = {"Array": _save_array, "DataFrame": _save_dataframe, ...}
            return dispatch[type_name](obj, config)

The six ``_save_*`` private functions absorb write logic from the
deleted ``csv_adapter`` / ``parquet_adapter`` / ``zarr_adapter`` /
``generic_adapter``.

The ``dynamic_ports`` schema for SaveData uses an
``input_port_mapping`` key (mirror of the ``output_port_mapping``
key in LoadData). The frontend ``computeEffectivePorts`` helper
in T-TRK-009 must handle both keys.

**i. Acceptance criteria**:
- Symmetric with T-TRK-007.
- Round-trip equality for each of the six core types via
  SaveData → LoadData → assert.
- All universal AC items satisfied.

**j. Out of scope**:
- Do not handle Collection-of-mixed-types in a single SaveData call.
  Collection of one type is fine; mixed-type Collections raise.
- Do not add a generic "save anything" path that bypasses the
  ``core_type`` dispatch.

**k. Dependencies**: T-TRK-006 (Block ABC migration).

**l. Estimated diff size**: M (~400 lines).

**m. Coupling notes**: Stacked on T-TRK-006, parallel with T-TRK-007.

---

### T-TRK-009 — Frontend ``BlockNode.tsx`` fixes + ``computeEffectivePorts``

**a. Ticket ID and name**: T-TRK-009 — Fix the three hardcoded
``blockType === "io_block"`` checks in ``BlockNode.tsx``, add a
``computeEffectivePorts()`` helper that consumes ``data.schema?.dynamic_ports``,
and update ``frontend/src/types/api.ts`` with the two new
``BlockSchemaResponse`` fields.

**b. Source ADR / spec sections**:
- ADR-028 Addendum 1 §B (the three GUI breakages enumerated).
- ADR-028 Addendum 1 §C8 (Browse button uses ``data.schema?.direction``).
- ADR-028 Addendum 1 §C11 (``data.category === "io"`` discriminator).
- Phase 11 master plan §2.2 ("Frontend changes" subsection).

**c. Files to be created**:
- ``frontend/src/utils/computeEffectivePorts.ts`` — pure-function
  helper that takes ``(dynamicPorts, configValue)`` and returns the
  effective ``InputPort[]`` / ``OutputPort[]`` lists.

**d. Files to be modified**:
- ``frontend/src/components/nodes/BlockNode.tsx`` — three changes:
  1. Browse button: replace ``blockType === "io_block" && key === "path"``
     with ``data.category === "io" && key === "path"``.
  2. Hidden ``direction`` field: replace ``blockType === "io_block"``
     filter with ``data.category === "io"``.
  3. Browse file-vs-directory: replace ``data.config?.direction``
     with ``data.schema?.direction``.
  4. (Bonus, in scope) call ``computeEffectivePorts(data.schema?.dynamic_ports,
     data.config?.[data.schema?.dynamic_ports?.source_config_key])``
     when rendering the input/output port handles, so port colours
     update live as the user changes the dropdown.

- ``frontend/src/types/api.ts`` — extend ``BlockSchemaResponse`` to
  include ``dynamic_ports?: DynamicPortsConfig | null`` and
  ``direction?: string | null``. Define the ``DynamicPortsConfig``
  interface to match the backend dict shape.

**e. Files to be deleted**: none.

**f. New tests**:
- ``frontend/src/utils/__tests__/computeEffectivePorts.test.ts`` —
  vitest unit tests covering:
  - Static block (``dynamicPorts === null``) returns the original
    ports unchanged.
  - LoadData with ``core_type="Array"`` returns
    ``[OutputPort{accepted_types: ["Array"]}]``.
  - SaveData with ``core_type="DataFrame"`` returns
    ``[InputPort{accepted_types: ["DataFrame"]}]``.
  - Unknown enum value falls back gracefully (returns the
    placeholder ClassVar ports, does not throw).

**g. Existing tests to update**:
- ``frontend/src/components/nodes/__tests__/BlockNode.test.tsx`` —
  add cases for ``data.category === "io"`` and remove cases that
  asserted on the old ``blockType === "io_block"`` paths.

**h. Implementation details**:

The exact line edits in ``BlockNode.tsx`` are spelled out in
ADR-028 Addendum 1 §B (lines 179, 241-243, 247-249 of the current
file). Implementation agent reads the addendum for the line
numbers and the surrounding context.

``computeEffectivePorts`` signature::

    interface DynamicPortsConfig {
      source_config_key: string;
      output_port_mapping?: Record<string, Record<string, string[]>>;
      input_port_mapping?: Record<string, Record<string, string[]>>;
    }

    export function computeEffectivePorts(
      dynamicPorts: DynamicPortsConfig | null | undefined,
      configValue: string | undefined,
      basePorts: PortDef[],
      kind: "input" | "output",
    ): PortDef[] {
      if (!dynamicPorts || !configValue) return basePorts;
      const mapping = kind === "input"
        ? dynamicPorts.input_port_mapping
        : dynamicPorts.output_port_mapping;
      if (!mapping) return basePorts;
      return basePorts.map(p => {
        const portRules = mapping[p.name];
        if (!portRules) return p;
        const acceptedTypes = portRules[configValue];
        if (!acceptedTypes) return p;
        return { ...p, accepted_types: acceptedTypes };
      });
    }

**i. Acceptance criteria**:
- All three hardcoded ``"io_block"`` strings are gone from
  ``BlockNode.tsx`` (verify with ``grep "io_block" frontend/src/``).
- ``computeEffectivePorts`` exists and is tested.
- ``BlockSchemaResponse`` TypeScript type includes the two new
  fields.
- ``npm test`` (vitest) green.
- ``npm run typecheck`` green.
- ``npm run lint`` green.
- All universal AC items satisfied.

**j. Out of scope**:
- Do not refactor any other React component.
- Do not add new pages or routes.
- Do not change styling beyond what is needed to render the new
  port colours.
- Do not add a backend round-trip on config change (Addendum 1
  explicitly defers that to ADR-029).

**k. Dependencies**: T-TRK-006 (the backend must populate the new
``BlockSchemaResponse`` fields before the frontend can consume them);
T-TRK-007 + T-TRK-008 (so there is at least one dynamic block in the
palette to drive the manual smoke test).

**l. Estimated diff size**: M (~250 lines: ~80 BlockNode + ~80
computeEffectivePorts + ~60 types/api.ts + ~30 tests).

**m. Coupling notes**: Stacked on T-TRK-007 + T-TRK-008. The frontend
PR is the last code-bearing PR in the Sprint A sub-1b stack; T-TRK-010
is doc-only after this.

---

### T-TRK-010 — ``ARCHITECTURE.md`` + ``PROJECT_TREE.md`` + ``block-sdk.md`` updates

**a. Ticket ID and name**: T-TRK-010 — Update the architecture docs
to reflect ADR-028 + Addendum 1.

**b. Source ADR / spec sections**:
- ADR-028 §F (Documentation impact).
- Phase 11 master plan §2.5 sub-1b PR-D (originally PR-F).

**c. Files to be created**: none.

**d. Files to be modified**:
- ``docs/architecture/ARCHITECTURE.md`` — §4.2 (block category
  hierarchy: IOBlock is now an abstract base; concrete loaders
  ship in core (LoadData / SaveData) and plugin packages) and §5.1
  (extension points: remove the ``scistudio.adapters`` entry-point
  group reference; mention the dynamic-port override mechanism).
- ``docs/architecture/PROJECT_TREE.md`` — remove the
  ``src/scistudio/blocks/io/adapters/`` subtree from the tree
  diagram; add the ``src/scistudio/blocks/io/loaders/`` and
  ``src/scistudio/blocks/io/savers/`` subtrees.
- ``docs/guides/block-sdk.md`` — add a section "Writing a dynamic-port
  block" with a worked example based on ``LoadData``; add a
  pointer to ADR-028 Addendum 1 from the IO subsection.
- ``docs/adr/ADR.md`` — add a "Superseded by ADR-028 §D4" stamp on
  ADR-025 §6 (the ``scistudio.adapters`` entry-point group section).

**e. Files to be deleted**: none.

**f. New tests**: none. (Doc-only PR, but optional ``markdownlint``
check.)

**g. Existing tests to update**: none.

**h. Implementation details**:
1. Read each of the four target files.
2. Identify the exact paragraphs that mention ``IOBlock`` /
   ``adapters`` / ``adapter_registry`` / ``scistudio.adapters``.
3. Rewrite each paragraph to reflect the post-ADR-028 architecture.
4. Add the dynamic-port worked example to ``block-sdk.md``.
5. Verify links to ADR-028 and Addendum 1 are correct.

**i. Acceptance criteria**:
- No reference to ``scistudio.blocks.io.adapters`` survives in any
  of the four files.
- No reference to ``scistudio.adapters`` entry-point survives.
- The dynamic-port worked example is present and matches the
  T-TRK-007 ``LoadData`` body.
- ADR-025 §6 has a "Superseded" stamp.
- All universal AC items satisfied.

**j. Out of scope**:
- Do not rewrite ARCHITECTURE.md beyond §4.2 + §5.1.
- Do not introduce new ARCHITECTURE.md sections.
- Do not edit any other ADR section.

**k. Dependencies**: T-TRK-009 (last code-bearing PR in the Sprint A
sub-1b stack — this docs PR rebases on top so it sees the final
file paths).

**l. Estimated diff size**: M (~200 lines of doc edits).

**m. Coupling notes**: Stacked on T-TRK-009. Last ticket in the
Sprint A sub-1b stacked cascade.

---

### T-TRK-011 — ``CLAUDE.md`` §2.5 + ``ARCHITECTURE.md`` ManualReview clarification

**a. Ticket ID and name**: T-TRK-011 — Update ``CLAUDE.md`` §2.5
("Manual steps are first-class") to reference ``AppBlock`` (Fiji
window) instead of the deprecated ``ManualReviewBlock``, remove
``ManualReviewBlock`` from the ARCHITECTURE.md "Strategy C built-in
blocks" list, and add an example to ``block-sdk.md`` showing how
to write a manual review step using ``AppBlock``.

**b. Source ADR / spec sections**:
- Phase 11 master plan §2.5 sub-1c.

**c. Files to be created**: none.

**d. Files to be modified**:
- ``CLAUDE.md`` — §2.5 example: change ``ManualReviewBlock(...)`` to
  ``AppBlock(app_command="fiji", ...)`` (or whatever the canonical
  invocation is).
- ``docs/architecture/ARCHITECTURE.md`` — "Strategy C built-in
  blocks" list: remove the ``ManualReviewBlock`` line, add a one-line
  pointer to ``AppBlock`` for the manual-review use case.
- ``docs/guides/block-sdk.md`` — new subsection "Writing a manual
  review step using AppBlock to open Fiji" with a code example.

**e. Files to be deleted**: none. (``ManualReviewBlock`` does not
currently exist as a class — it was a documentation artefact only.
If a stub class is found during implementation, file a follow-up
issue rather than deleting it inline.)

**f. New tests**: none.

**g. Existing tests to update**: none.

**h. Implementation details**:
1. Read CLAUDE.md §2.5 to confirm the current ``ManualReviewBlock``
   reference.
2. Rewrite the example with the canonical ``AppBlock`` invocation
   (refer to existing AppBlock test code for the right kwargs).
3. Read ARCHITECTURE.md "Strategy C" subsection.
4. Remove the ManualReviewBlock line, add the AppBlock pointer.
5. Add the new ``block-sdk.md`` subsection.

**i. Acceptance criteria**:
- ``git grep ManualReviewBlock`` returns 0 hits in CLAUDE.md and
  ARCHITECTURE.md.
- ``block-sdk.md`` has the new manual-review-via-AppBlock subsection.
- All universal AC items satisfied.

**j. Out of scope**:
- Do not implement a new ManualReviewBlock class. The whole point
  of this ticket is that ManualReviewBlock is being abandoned in
  favour of the AppBlock pattern.
- Do not touch any source code under ``src/scistudio/blocks/``.

**k. Dependencies**: none. Independent of every other ticket.

**l. Estimated diff size**: S (~80 lines of doc edits).

**m. Coupling notes**: Standalone. Sprint A Level A0 parallel.

---

### T-TRK-012 — ``FilterCollection`` metadata query

**a. Ticket ID and name**: T-TRK-012 — Extend
``src/scistudio/blocks/process/builtins/filter_collection.py`` to
accept an ``expression: str`` config param parsed via an AST
whitelist (NOT ``eval()``).

**b. Source ADR / spec sections**:
- Phase 11 master plan §2.5 sub-1d.

**c. Files to be created**:
- ``src/scistudio/blocks/process/builtins/expression_evaluator.py``
  — the AST whitelist evaluator (a small new module that the
  ``FilterCollection`` block depends on).

**d. Files to be modified**:
- ``src/scistudio/blocks/process/builtins/filter_collection.py`` —
  add the ``expression`` config field and the runtime evaluator
  call.

**e. Files to be deleted**: none.

**f. New tests**:
- ``tests/blocks/process/builtins/test_filter_collection_expression.py``
  — covers:
  - Filtering by ``meta.framework.created_at`` comparison.
  - Filtering by ``user.tag in [...]``.
  - Filtering by ``index < 5``.
  - Rejection of forbidden constructs: ``__import__``, function
    calls (except whitelisted ``len``), subscript ranges, exec.
  - Empty result Collection passes through cleanly.
- ``tests/blocks/process/builtins/test_expression_evaluator.py`` —
  unit tests for the AST whitelist evaluator independently of the
  ``FilterCollection`` block.

**g. Existing tests to update**: any existing FilterCollection test
that asserted on the pre-expression behaviour.

**h. Implementation details**:

**Allowed AST nodes**:
``Module``, ``Expression``, ``Compare``, ``BoolOp``, ``UnaryOp``,
``Constant``, ``Name``, ``Attribute``, ``Subscript`` (with literal
key only), ``In``, ``NotIn``, ``And``, ``Or``, ``Not``, ``Eq``,
``NotEq``, ``Lt``, ``LtE``, ``Gt``, ``GtE``.

**Allowed names** (evaluation scope):
``item`` (DataObject), ``index`` (int), ``meta`` (alias for
``item.meta``), ``framework`` (alias for ``item.framework``),
``user`` (alias for ``item.user``), and the whitelisted call
``len``.

**Forbidden**:
``Call`` (except ``len(...)``), ``Import``, ``ImportFrom``,
``Lambda``, ``FunctionDef``, ``ClassDef``, ``Global``, ``Nonlocal``,
dunder attribute access (any name starting with ``__``).

The evaluator walks the AST once at parse time to validate; if any
forbidden node is found, raises ``ValueError("Expression contains
forbidden construct: <node>")`` at workflow validation time (NOT
at runtime, so users see the error immediately).

At runtime, the evaluator walks the AST again with the per-item
scope dict and returns ``True`` / ``False``.

**i. Acceptance criteria**:
- ``FilterCollection`` accepts an ``expression`` config field.
- The evaluator validates the expression at parse time and rejects
  forbidden constructs with a clear error.
- Six positive test cases pass.
- Six rejection test cases all raise ``ValueError``.
- ``mypy`` clean.
- All universal AC items satisfied.

**j. Out of scope**:
- Do not add a "trusted mode" that bypasses the whitelist.
- Do not introduce any new keyword to the language (no
  ``filter where ...`` DSL — pure Python expression syntax only).
- Do not move ``FilterCollection`` to a plugin package. It stays in
  core because the imaging plugin depends on it.

**k. Dependencies**: T-TRK-002 (``register.py`` deletion is in the
same ``builtins`` directory; merging T-TRK-002 first prevents stray
import-removal merge conflicts).

**l. Estimated diff size**: M (~300 lines: ~150 evaluator + ~80
FilterCollection + ~150 tests).

**m. Coupling notes**: Sprint B parallel. Independent of sub-1e /
sub-1f / sub-1g.

---

### T-TRK-013 — CodeBlock R runner audit

**a. Ticket ID and name**: T-TRK-013 — Write an integration test
that runs a real R script via ``CodeBlock(language="r")``, passes
a DataFrame in, gets a DataFrame out. If the R runner does not
work end-to-end, file an issue and request a fix.

**b. Source ADR / spec sections**:
- Phase 11 master plan §2.5 sub-1e.

**c. Files to be created**:
- ``tests/blocks/code/test_codeblock_r_integration.py``
- (Optionally) ``tests/blocks/code/fixtures/sample_pipeline.R`` if
  the R script body is non-trivial.

**d. Files to be modified**:
- ``pyproject.toml`` — register ``requires_r`` marker per Q7+Q8.

**e. Files to be deleted**: none.

**f. New tests**:
- ``test_codeblock_r_dataframe_roundtrip`` — guarded by
  ``@pytest.mark.requires_r``. Loads a small DataFrame in Python,
  passes it through a CodeBlock running an R script that filters
  rows, asserts the returned DataFrame matches the expected.
- ``test_codeblock_r_error_propagates`` — R script raises an error;
  test asserts the CodeBlock surfaces it as a Python exception
  with the R error message preserved.

**g. Existing tests to update**: none.

**h. Implementation details**:

The R script is a few lines::

    # script.R
    df <- read.csv(args$input_path)
    filtered <- df[df$value > 5, ]
    write.csv(filtered, args$output_path, row.names = FALSE)

The CodeBlock invocation::

    block = CodeBlock(language="r", script=open("sample_pipeline.R").read())
    result = block.run(inputs={"data": df}, config=...)

If anything in the runner is broken (R not found, args not passed,
output not parsed), the test must produce a clear failure message
and an issue must be filed via ``gh issue create`` (separately —
not as part of this PR).

**i. Acceptance criteria**:
- Both new tests exist.
- Both tests are marker-protected and skip cleanly when R is not
  installed.
- If R is installed locally, both tests pass.
- ``requires_r`` marker is registered.
- All universal AC items satisfied.

**j. Out of scope**:
- Do not add R installation scripts.
- Do not add a CI workflow to install R (that is a follow-up).
- Do not modify any source under ``src/scistudio/blocks/code/``
  unless a verified bug requires it. If a bug is found, file a
  separate issue and reference it in this PR; the fix is a
  separate PR.

**k. Dependencies**: T-TRK-014 not strictly required (different
language) but the two CodeBlock audits are commonly merged together.

**l. Estimated diff size**: S (~150 lines).

**m. Coupling notes**: Sprint B parallel. Sequential dependency for
T-LCMS-007 (AccuCorR depends on a working R runner).

---

### T-TRK-014 — CodeBlock Python runner audit

**a. Ticket ID and name**: T-TRK-014 — Write an integration test
that runs a realistic user pipeline (e.g., a scikit-image workflow
on a test image) via ``CodeBlock(language="python")`` and verifies
that Collection auto-unpack/repack works correctly on a list of
DataObjects.

**b. Source ADR / spec sections**:
- Phase 11 master plan §2.5 sub-1f.

**c. Files to be created**:
- ``tests/blocks/code/test_codeblock_python_integration.py``

**d. Files to be modified**: none unless a bug is found.

**e. Files to be deleted**: none.

**f. New tests**:
- ``test_codeblock_python_skimage_workflow`` — uses the test
  images from ``tests/fixtures/test_images.py`` (added by T-TRK-003);
  runs a Python CodeBlock that loads, gaussian-filters, and
  thresholds the image; asserts the output Collection has the
  expected length and the expected per-item type.
- ``test_codeblock_python_collection_unpack`` — passes a Collection
  of three DataFrame items; the script processes each; the result
  is a Collection of three processed DataFrames.

**g. Existing tests to update**: none.

**h. Implementation details**: same shape as T-TRK-013. If
auto-unpack/repack has a bug, file an issue separately.

**i. Acceptance criteria**:
- Both tests exist and pass on a fresh clone with default Python
  dependencies.
- All universal AC items satisfied.

**j. Out of scope**: same as T-TRK-013 — do not modify
``src/scistudio/blocks/code/`` unless a verified bug requires it.

**k. Dependencies**: T-TRK-003 (test image fixtures must exist).

**l. Estimated diff size**: S (~150 lines).

**m. Coupling notes**: Sprint B parallel.

---

### T-TRK-015 — AppBlock functional audit

**a. Ticket ID and name**: T-TRK-015 — Write an integration test
that launches Fiji via AppBlock, optionally drives it with a
Fiji macro for automation, and collects output. Verify FileWatcher
stability, ProcessHandle cleanup on exit, and exchange directory
cleanup.

**b. Source ADR / spec sections**:
- Phase 11 master plan §2.5 sub-1g.
- Existing AppBlock tests in ``tests/blocks/app/`` (read for the
  right invocation pattern).

**c. Files to be created**:
- ``tests/blocks/app/test_appblock_fiji_integration.py``
- ``tests/blocks/app/fixtures/headless_macro.ijm`` — a small Fiji
  macro that opens a test image, applies a Gaussian blur, saves
  result to a known path.

**d. Files to be modified**:
- ``packages/scistudio-blocks-imaging/pyproject.toml`` (or root
  ``pyproject.toml`` if no plugin scaffold yet at this point) —
  register the ``requires_fiji`` marker per Q7. Note: this ticket
  runs **before** T-IMG-038 plugin packaging, so the marker
  registration may go in root ``pyproject.toml`` and migrate to
  the plugin's ``pyproject.toml`` in T-IMG-038.

**e. Files to be deleted**: none.

**f. New tests**:
- ``test_appblock_fiji_launch_and_macro`` — guarded by
  ``@pytest.mark.requires_fiji``. Launches Fiji with the headless
  macro, waits for the output file, asserts it exists and is the
  expected size.
- ``test_appblock_fiji_filewatcher_cleanup`` — confirms the
  FileWatcher thread terminates cleanly after the AppBlock exits.
- ``test_appblock_fiji_process_cleanup`` — confirms the Fiji
  process is reaped (no zombie process) after the block completes.
- ``test_appblock_exchange_dir_cleanup`` — confirms the temporary
  exchange directory is removed after the block exits successfully.

**g. Existing tests to update**: none.

**h. Implementation details**:

Fiji executable path: ``C:\Program Files\Fiji\fiji-windows-x64.exe``
(per master plan §10).

The Fiji macro invocation::

    block = FijiBlock(
        config={
            "macro_path": "tests/blocks/app/fixtures/headless_macro.ijm",
            "input_image_path": str(K562_L_2845_TIF),
            "output_image_path": str(tmp_path / "blurred.tif"),
        }
    )

If FileWatcher / ProcessHandle / exchange-dir cleanup is broken,
file an issue. Do not fix in this PR — it is an audit, not a fix.

**i. Acceptance criteria**:
- Four tests exist and skip cleanly when Fiji is not installed.
- ``requires_fiji`` marker is registered.
- If Fiji is installed locally, all four tests pass.
- All universal AC items satisfied.

**j. Out of scope**:
- Do not implement ``FijiBlock`` if it does not exist yet — this
  ticket only audits the existing AppBlock + Fiji invocation
  pattern. If ``FijiBlock`` does not exist, defer the test bodies
  to T-IMG-034 and only register the marker here.
- Do not modify ``AppBlock`` source unless a verified bug requires
  it; file a separate issue.

**k. Dependencies**: T-TRK-003 (test image constants).

**l. Estimated diff size**: M (~250 lines including the .ijm macro
fixture).

**m. Coupling notes**: Sprint B parallel. Sequential dependency for
T-IMG-034 (FijiBlock needs a working AppBlock + Fiji audit).

---

### 9.2 Track 2 — imaging plugin (compact reference format)

Each entry below is a **pointer** to the corresponding ticket in
``docs/specs/phase11-imaging-block-spec.md``. Implementation agents
read the source spec for the full implementation details (file
contents, code sketches, per-block algorithm choice, parameter
validation rules). This standards doc carries only the cross-ticket
metadata: dependency edges, sprint bucket, and coupling notes.

**Sprint C** (parallel within levels). All Track 2 tickets land in
``packages/scistudio-blocks-imaging/`` per the monorepo decision.

---

#### T-IMG-001 — Types module (Image / Mask / Label / Transform)

- **Source**: ``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-001
- **Summary**: Define ``Image(Array)``, ``Mask(Image)``,
  ``Label(CompositeData)``, ``Transform(Array)`` as the four imaging
  type classes per master plan §2.4.
- **Files**: ``packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/types.py``
  + tests
- **Dependencies**: T-TRK-006 (Block ABC migration)
- **Estimated diff size**: M
- **Coupling notes**: Standalone. **First ticket in Sprint C** —
  every other Track 2 ticket depends on it (transitively).

---

#### T-IMG-002 — LoadImage

- **Source**: imaging spec §9 T-IMG-002
- **Summary**: Unified image loader auto-detecting TIFF / OME-TIFF /
  PNG / JPG / Zarr / CZI / ND2 / LIF / npy. Absorbs the deleted
  ``tiff_adapter.py`` logic verbatim. Large images use lazy
  storage_ref. Metadata auto-extracted to ``meta``.
- **Files**: ``packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py``
  + tests
- **Dependencies**: T-IMG-001, T-TRK-004
- **Estimated diff size**: L
- **Coupling notes**: Standalone. **CRITICAL: see §8 Q9 anti-drift
  flag** — must NOT introduce a separate ``LoadArray`` /
  ``LoadDataFrame`` class in core; the addendum supersedes the
  six-loader structure.

---

#### T-IMG-003 — SaveImage

- **Source**: imaging spec §9 T-IMG-003
- **Summary**: Symmetric saver. Preserves the JSON-in-ImageDescription
  metadata round-trip from the deleted ``tiff_adapter.py``.
- **Files**: ``.../io/save_image.py`` + tests
- **Dependencies**: T-IMG-001, T-TRK-004
- **Estimated diff size**: M
- **Coupling notes**: Parallel with T-IMG-002.

---

#### T-IMG-004 — Denoise

- **Source**: imaging spec §9 T-IMG-004
- **Summary**: Method param: gaussian / median / bilateral / nlmeans /
  wavelet. The Gaussian path is the one used by the E2E test (§11).
- **Files**: ``.../preprocess/denoise.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone. Critical-path dependency for the
  Sprint C E2E test.

---

#### T-IMG-005 — BackgroundSubtract

- **Source**: imaging spec §9 T-IMG-005
- **Summary**: Method param: rollingball / tophat / polynomial /
  constant.
- **Files**: ``.../preprocess/background_subtract.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-006 — Normalize

- **Source**: imaging spec §9 T-IMG-006
- **Summary**: Method param: minmax / zscore / percentile /
  histogram_match.
- **Files**: ``.../preprocess/normalize.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-007 — FlatFieldCorrect

- **Source**: imaging spec §9 T-IMG-007
- **Summary**: Reference image + optional dark frame.
- **Files**: ``.../preprocess/flat_field_correct.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-008 — Geometry bundle (Rotate / Flip / Crop / Pad / Resize)

- **Source**: imaging spec §9 T-IMG-008
- **Summary**: Five small geometry blocks bundled into one ticket
  because they share a single test fixture and helper module.
- **Files**: ``.../preprocess/geometry.py`` (one file with five
  classes) + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: L
- **Coupling notes**: **Bundled** (5 blocks in one ticket). Per the
  source spec, the spec author concluded that the five geometry
  ops share so much fixture / parameter-validation infrastructure
  that splitting them into five PRs would create more drift than
  bundling.

---

#### T-IMG-009 — ConvertDType

- **Source**: imaging spec §9 T-IMG-009
- **Summary**: Type conversion with optional rescaling.
- **Files**: ``.../preprocess/convert_dtype.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-IMG-010 — AxisSplit / AxisMerge

- **Source**: imaging spec §9 T-IMG-010
- **Summary**: Generic axis splitting and merging (any axis, not
  just channel).
- **Files**: ``.../preprocess/axis_ops.py`` (two classes in one file)
  + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: **Bundled** (2 blocks in one ticket — symmetric
  pair).

---

#### T-IMG-011 — Deconvolve placeholder

- **Source**: imaging spec §9 T-IMG-011
- **Summary**: Class scaffold with ``raise NotImplementedError("Phase 12")``
  body. Reserved namespace.
- **Files**: ``.../preprocess/deconvolve.py`` + skeleton test
- **Dependencies**: T-IMG-001
- **Estimated diff size**: XS
- **Coupling notes**: Standalone. **Placeholder** — implementation
  deferred to Phase 12.

---

#### T-IMG-012 — MorphologyOp

- **Source**: imaging spec §9 T-IMG-012
- **Summary**: erode / dilate / open / close / tophat / bottomhat
  via method param.
- **Files**: ``.../morphology/morphology_op.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-013 — EdgeDetect

- **Source**: imaging spec §9 T-IMG-013
- **Summary**: sobel / scharr / canny / prewitt via method param.
- **Files**: ``.../morphology/edge_detect.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-014 — RidgeFilter

- **Source**: imaging spec §9 T-IMG-014
- **Summary**: frangi / meijering / sato / hessian.
- **Files**: ``.../morphology/ridge_filter.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-015 — Sharpen

- **Source**: imaging spec §9 T-IMG-015
- **Summary**: Unsharp mask + parameterised sharpen kernel.
- **Files**: ``.../morphology/sharpen.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-IMG-016 — FFTFilter

- **Source**: imaging spec §9 T-IMG-016
- **Summary**: Frequency-domain filtering (lowpass / highpass /
  bandpass).
- **Files**: ``.../morphology/fft_filter.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-017 — Threshold

- **Source**: imaging spec §9 T-IMG-017
- **Summary**: otsu / li / yen / isodata / mean / triangle /
  adaptive_otsu / manual.
- **Files**: ``.../segmentation/threshold.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-018 — Watershed

- **Source**: imaging spec §9 T-IMG-018
- **Summary**: Marker-based or distance-based watershed segmentation.
- **Files**: ``.../segmentation/watershed.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-019 — CellposeSegment (FLAGSHIP)

- **Source**: imaging spec §9 T-IMG-019
- **Summary**: Cellpose-based segmentation. Uses
  ``ProcessBlock.setup() / teardown()`` to load the cellpose model
  ONCE per run, not per item — this is the **flagship use case for
  the Phase 10 setup/teardown lifecycle hooks**.
- **Files**: ``.../segmentation/cellpose_segment.py`` + tests
- **Dependencies**: T-IMG-001, T-IMG-004 (Denoise upstream in E2E),
  T-TRK-015 (AppBlock audit not strictly needed for Cellpose, but
  the broader Sprint B audit must complete first to confirm the
  workflow infrastructure is healthy)
- **Estimated diff size**: L
- **Coupling notes**: Standalone. **Critical-path for the E2E test.**
  Test marker: ``@pytest.mark.requires_cellpose`` (per Q7).

---

#### T-IMG-020 — BlobDetect

- **Source**: imaging spec §9 T-IMG-020
- **Summary**: LoG / DoG / DoH blob detection → Label.
- **Files**: ``.../segmentation/blob_detect.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-021 — ConnectedComponents

- **Source**: imaging spec §9 T-IMG-021
- **Summary**: Connected-component labelling on a Mask → Label.
- **Files**: ``.../segmentation/connected_components.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-IMG-022 — Cleanup bundle (RemoveSmallObjects / RemoveBorderObjects / FillHoles / ExpandLabels / ShrinkLabels)

- **Source**: imaging spec §9 T-IMG-022
- **Summary**: Five small label-cleanup blocks bundled.
- **Files**: ``.../segmentation/cleanup.py`` (one file with five
  classes) + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: **Bundled** (5 blocks). Same rationale as
  T-IMG-008.

---

#### T-IMG-023 — TrackObjects placeholder

- **Source**: imaging spec §9 T-IMG-023
- **Summary**: Class scaffold with Phase 12 placeholder.
- **Files**: ``.../tracking/track_objects.py`` + skeleton test
- **Dependencies**: T-IMG-001
- **Estimated diff size**: XS
- **Coupling notes**: **Placeholder** — Phase 12.

---

#### T-IMG-024 — RegionProps

- **Source**: imaging spec §9 T-IMG-024
- **Summary**: SINGLE block with multi-select ``properties`` param
  (checkbox UI). Replaces the OptEasy multi-block approach.
- **Files**: ``.../measurement/region_props.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: L
- **Coupling notes**: Standalone.

---

#### T-IMG-025 — PairwiseDistance

- **Source**: imaging spec §9 T-IMG-025
- **Summary**: source_labels + target_labels → DataFrame of distances.
  Use case: immune cell → cancer cell distance.
- **Files**: ``.../measurement/pairwise_distance.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-026 — Colocalization

- **Source**: imaging spec §9 T-IMG-026
- **Summary**: Pearson / Manders / Costes colocalization metrics.
- **Files**: ``.../measurement/colocalization.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-027 — ComputeRegistration

- **Source**: imaging spec §9 T-IMG-027
- **Summary**: moving + fixed → Transform.
- **Files**: ``.../registration/compute_registration.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-028 — ApplyTransform

- **Source**: imaging spec §9 T-IMG-028
- **Summary**: Apply a Transform to an Image.
- **Files**: ``.../registration/apply_transform.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-IMG-029 — RegisterSeries

- **Source**: imaging spec §9 T-IMG-029
- **Summary**: Time-series or z-stack registration.
- **Files**: ``.../registration/register_series.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-IMG-030 — AxisProjection / SelectSlice

- **Source**: imaging spec §9 T-IMG-030
- **Summary**: Two related projection blocks bundled. ``SelectSlice``
  is the single replacement for the OptEasy SelectChannel /
  CropTimeRange / etc. zoo.
- **Files**: ``.../projection/projection.py`` (two classes) + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: **Bundled** (2 blocks).

---

#### T-IMG-031 — Math scalar bundle (AddScalar / SubtractScalar / MultiplyScalar / DivideScalar)

- **Source**: imaging spec §9 T-IMG-031
- **Summary**: Four trivially symmetric scalar arithmetic blocks
  bundled.
- **Files**: ``.../math/scalar_ops.py`` + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: S
- **Coupling notes**: **Bundled** (4 blocks).

---

#### T-IMG-032 — ImageCalculator

- **Source**: imaging spec §9 T-IMG-032
- **Summary**: Two-input calculator (A op B + AST-restricted user
  expression on the two named inputs).
- **Files**: ``.../math/image_calculator.py`` + tests
- **Dependencies**: T-IMG-001, T-TRK-012 (the AST whitelist
  evaluator from FilterCollection is reused here for expression
  validation)
- **Estimated diff size**: M
- **Coupling notes**: Standalone. **Per §8 Q11 — 2-port-fixed in
  0.1.0**, NOT variadic. Variadic deferred to ADR-029.

---

#### T-IMG-033 — Visualization bundle (RenderPseudoColor / RenderOverlay / RenderMontage / RenderMovie / RenderHistogram)

- **Source**: imaging spec §9 T-IMG-033
- **Summary**: Five rendering blocks producing Artifact outputs.
- **Files**: ``.../visualization/render.py`` (five classes) + tests
- **Dependencies**: T-IMG-001
- **Estimated diff size**: L
- **Coupling notes**: **Bundled** (5 blocks).

---

#### T-IMG-034 — FijiBlock

- **Source**: imaging spec §9 T-IMG-034
- **Summary**: AppBlock subclass. ``app_command = "fiji"``.
- **Files**: ``.../interactive/fiji_block.py`` + tests
- **Dependencies**: T-IMG-001, **T-TRK-015 (AppBlock + Fiji audit
  must merge first)**.
- **Estimated diff size**: M
- **Coupling notes**: Standalone. Marker:
  ``@pytest.mark.requires_fiji``.

---

#### T-IMG-035 — NapariBlock

- **Source**: imaging spec §9 T-IMG-035
- **Summary**: AppBlock subclass for Napari.
- **Files**: ``.../interactive/napari_block.py`` + tests
- **Dependencies**: T-IMG-001, T-TRK-015
- **Estimated diff size**: M
- **Coupling notes**: Standalone. Marker:
  ``@pytest.mark.requires_napari``.

---

#### T-IMG-036 — CellProfilerBlock

- **Source**: imaging spec §9 T-IMG-036
- **Summary**: AppBlock subclass for CellProfiler.
- **Files**: ``.../interactive/cell_profiler_block.py`` + tests
- **Dependencies**: T-IMG-001, T-TRK-015
- **Estimated diff size**: M
- **Coupling notes**: Standalone. Marker:
  ``@pytest.mark.requires_cellprofiler``.

---

#### T-IMG-037 — QuPathBlock

- **Source**: imaging spec §9 T-IMG-037
- **Summary**: AppBlock subclass for QuPath.
- **Files**: ``.../interactive/qupath_block.py`` + tests
- **Dependencies**: T-IMG-001, T-TRK-015
- **Estimated diff size**: M
- **Coupling notes**: Standalone. Marker:
  ``@pytest.mark.requires_qupath``.

---

#### T-IMG-038 — Plugin packaging

- **Source**: imaging spec §9 T-IMG-038
- **Summary**: ``pyproject.toml`` for the imaging package +
  entry-point registration for every block class + plugin smoke
  test that asserts every block is importable. Also adds the
  ``packages/scistudio-blocks-imaging/tests`` path to the root
  ``pyproject.toml`` ``testpaths`` list per Q12.
- **Files**: ``packages/scistudio-blocks-imaging/pyproject.toml``,
  ``packages/scistudio-blocks-imaging/tests/test_plugin_smoke.py``,
  root ``pyproject.toml`` (testpaths only)
- **Dependencies**: T-IMG-001 through T-IMG-037 ALL merged (the
  smoke test must succeed for every block).
- **Estimated diff size**: M
- **Coupling notes**: Standalone. **Last ticket in Sprint C** —
  releases the imaging plugin at version 0.1.0.

---

### 9.3 Track 3 — SRS plugin (compact reference format)

Each entry below is a pointer to ``docs/specs/phase11-srs-block-spec.md``.
SRS depends on the imaging plugin: ``SRSImage`` extends ``Image``.
Cross-plugin imports follow Q5 (``pytest.importorskip``).

Sprint D. All Track 3 tickets land in ``packages/scistudio-blocks-srs/``.

---

#### T-SRS-000 — Package skeleton + entry points

- **Source**: SRS spec §9 T-SRS-000
- **Summary**: ``packages/scistudio-blocks-srs/`` directory tree,
  ``pyproject.toml``, empty ``src/``, empty ``tests/conftest.py``
  with the ``imaging_types`` fixture per Q5.
- **Files**: ``pyproject.toml``, ``src/scistudio_blocks_srs/__init__.py``,
  ``tests/conftest.py``
- **Dependencies**: T-IMG-038 (imaging plugin must be installable
  before SRS can declare a runtime dependency on it).
- **Estimated diff size**: S
- **Coupling notes**: Standalone. **First ticket in Sprint D.**

---

#### T-SRS-001 — ``SRSImage`` type + Meta model

- **Source**: SRS spec §9 T-SRS-001
- **Summary**: ``SRSImage(Image)`` with ``required_axes={"y","x","lambda"}``
  and the SRS-specific ``Meta`` Pydantic model (wavenumbers,
  laser_power, integration_time, digitizer_*, pump/stokes wavelength).
  **NO ``RamanSpectrum``** — spectra are DataFrames per master plan
  §2.4.
- **Files**: ``src/scistudio_blocks_srs/types.py`` + tests
- **Dependencies**: T-SRS-000, T-IMG-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-002 — ``SRSCalibrate``

- **Source**: SRS spec §9 T-SRS-002
- **Summary**: Digitizer inversion + ``Image → SRSImage`` type
  conversion. **The entry point of the SRS pipeline** — converts
  the imaging-plugin output to the SRS type.
- **Files**: ``src/scistudio_blocks_srs/preprocess/srs_calibrate.py``
  + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-003 — ``SRSBaseline``

- **Source**: SRS spec §9 T-SRS-003
- **Summary**: Method param: polynomial / rubber_band /
  rolling_ball_spectral. **NO ALS** per master plan §2.4.
- **Files**: ``.../preprocess/srs_baseline.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-004 — ``SRSDenoise``

- **Source**: SRS spec §9 T-SRS-004
- **Summary**: Method param: wavelet / PCA_denoise / SVD_truncation /
  BM4D.
- **Files**: ``.../preprocess/srs_denoise.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-005 — ``SRSNormalize``

- **Source**: SRS spec §9 T-SRS-005
- **Summary**: SNV / MSC / vector / area / peak_area normalization.
- **Files**: ``.../preprocess/srs_normalize.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-006 — ``SRSVCA``

- **Source**: SRS spec §9 T-SRS-006
- **Summary**: Vertex Component Analysis for endmember extraction.
- **Files**: ``.../component_analysis/srs_vca.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-007 — ``SRSUnmix``

- **Source**: SRS spec §9 T-SRS-007
- **Summary**: NNLS unmixing with reference spectra.
- **Files**: ``.../component_analysis/srs_unmix.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-008 — ``SRSPCA``

- **Source**: SRS spec §9 T-SRS-008
- **Summary**: Principal Component Analysis on spectral axis.
- **Files**: ``.../component_analysis/srs_pca.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-009 — ``SRSICA``

- **Source**: SRS spec §9 T-SRS-009
- **Summary**: Independent Component Analysis on spectral axis.
- **Files**: ``.../component_analysis/srs_ica.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-010 — ``SRSKMeansCluster``

- **Source**: SRS spec §9 T-SRS-010
- **Summary**: K-means clustering of pixels by spectrum → Label.
- **Files**: ``.../component_analysis/srs_kmeans.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-011 — ``ExtractSpectrum``

- **Source**: SRS spec §9 T-SRS-011
- **Summary**: ROI / Label / Mask + SRSImage → DataFrame of spectra.
  **Critical-path block for the E2E test (§11)**.
- **Files**: ``.../spectral_extraction/extract_spectrum.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-SRS-012 — ``BandRatio``

- **Source**: SRS spec §9 T-SRS-012
- **Summary**: Two-band intensity ratio → Image.
- **Files**: ``.../spectral_extraction/band_ratio.py`` + tests
- **Dependencies**: T-SRS-001
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-SRS-013 — Plugin entry-point wiring + smoke test

- **Source**: SRS spec §9 T-SRS-013
- **Summary**: Update ``pyproject.toml`` entry points for all SRS
  blocks; add plugin smoke test; extend root ``pyproject.toml``
  ``testpaths`` to include ``packages/scistudio-blocks-srs/tests``.
- **Files**: ``packages/scistudio-blocks-srs/pyproject.toml``,
  ``.../tests/test_plugin_smoke.py``, root ``pyproject.toml``
- **Dependencies**: T-SRS-000 through T-SRS-012 merged.
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-SRS-014 — E2E integration test (cross-plugin)

- **Source**: SRS spec §9 T-SRS-014
- **Summary**: Integration test that exercises imaging + SRS together.
  Uses the ``imaging_types`` fixture from Q5. Marker:
  ``@pytest.mark.requires_imaging``.
- **Files**: ``packages/scistudio-blocks-srs/tests/integration/
  test_imaging_srs_pipeline.py``
- **Dependencies**: T-SRS-013, T-IMG-038
- **Estimated diff size**: M
- **Coupling notes**: Standalone. **Last ticket in Sprint D.**

---

### 9.4 Track 4 — LC-MS plugin (compact reference format)

Each entry below is a pointer to ``docs/specs/phase11-lcms-block-spec.md``.
LC-MS depends on the R runner (T-TRK-013) for AccuCorR and on the
Python runner (T-TRK-014) for some isotope tracing blocks.

Sprint E. All Track 4 tickets land in ``packages/scistudio-blocks-lcms/``.

---

#### T-LCMS-001 — Plugin scaffold

- **Source**: LC-MS spec §9 T-LCMS-001
- **Summary**: ``packages/scistudio-blocks-lcms/`` directory tree,
  ``pyproject.toml``, empty src/, conftest with marker registration
  for ``requires_r`` / ``requires_elmaven`` / ``requires_graphpad``.
- **Files**: ``pyproject.toml``, ``src/scistudio_blocks_lcms/__init__.py``,
  ``tests/conftest.py``
- **Dependencies**: T-TRK-013 + T-TRK-014 (CodeBlock audits must
  merge before LC-MS depends on the runners).
- **Estimated diff size**: S
- **Coupling notes**: Standalone. **First ticket in Sprint E.**

---

#### T-LCMS-002 — Types module

- **Source**: LC-MS spec §9 T-LCMS-002
- **Summary**: ``MSRawFile(Artifact)``, ``PeakTable(DataFrame)``,
  ``MIDTable(DataFrame)`` (long format per master plan §2.4),
  ``SampleMetadata(DataFrame)``. **NO ``MSSpectrum``, NO ``MSRun``**
  per master plan.
- **Files**: ``src/scistudio_blocks_lcms/types.py`` + tests
- **Dependencies**: T-LCMS-001
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-003 — ``LoadMSRawFiles``

- **Source**: LC-MS spec §9 T-LCMS-003
- **Summary**: Batch loader → ``Collection[MSRawFile]``. Records
  paths only (does not parse). Absorbs the deleted ``mzxml_adapter``
  metadata extraction.
- **Files**: ``.../io/load_ms_raw_files.py`` + tests
- **Dependencies**: T-LCMS-002, T-TRK-004
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-004 — ``LoadPeakTable``

- **Source**: LC-MS spec §9 T-LCMS-004
- **Summary**: CSV / TSV / XLSX auto-detect for ElMAVEN / MZmine /
  XCMS column naming.
- **Files**: ``.../io/load_peak_table.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-005 — ``LoadMIDTable``

- **Source**: LC-MS spec §9 T-LCMS-005
- **Summary**: Auto-detect AccuCor output format (Compound / C13 /
  H2 / sample_X columns).
- **Files**: ``.../io/load_mid_table.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-006 — ``LoadSampleMetadata`` + ``SaveTable``

- **Source**: LC-MS spec §9 T-LCMS-006
- **Summary**: Two small IO blocks bundled. ``SaveTable`` is the
  generic table saver — used everywhere instead of a dedicated
  ``SaveMIDTable`` per master plan §2.4.
- **Files**: ``.../io/load_sample_metadata.py``,
  ``.../io/save_table.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: **Bundled** (2 IO blocks).

---

#### T-LCMS-007 — ``ElMAVENBlock`` + ``AccuCorR``

- **Source**: LC-MS spec §9 T-LCMS-007
- **Summary**: Two external-tool blocks bundled because they share
  the conftest marker registration (``requires_elmaven``,
  ``requires_r``) and both depend on T-TRK-013 (R audit) +
  T-TRK-015 (AppBlock audit).
- **Files**: ``.../external/elmaven_block.py``,
  ``.../external/accucor_r.py``,
  ``.../external/scripts/accucor.R`` (the R script body) + tests
- **Dependencies**: T-LCMS-002, T-TRK-013, T-TRK-015
- **Estimated diff size**: L
- **Coupling notes**: **Bundled** (2 external-tool blocks). Markers:
  ``requires_elmaven`` and ``requires_r``.

---

#### T-LCMS-008 — ``Calculate13CEnrichment``

- **Source**: LC-MS spec §9 T-LCMS-008
- **Summary**: Weighted average by M+n where n is 13C count →
  DataFrame (compound × sample → enrichment fraction). NEW per user
  request.
- **Files**: ``.../isotope_tracing/calculate_13c_enrichment.py`` +
  tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-009 — ``FractionalLabeling``

- **Source**: LC-MS spec §9 T-LCMS-009
- **Summary**: ``1 - M+0`` per compound × sample → DataFrame.
- **Files**: ``.../isotope_tracing/fractional_labeling.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-LCMS-010 — ``CompareGroupMID``

- **Source**: LC-MS spec §9 T-LCMS-010
- **Summary**: Stats between groups (t-test / Wilcoxon per
  isotopologue) → DataFrame.
- **Files**: ``.../isotope_tracing/compare_group_mid.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-011 — ``FluxEstimate``

- **Source**: LC-MS spec §9 T-LCMS-011
- **Summary**: Simple steady-state flux (labeling rate × pool size).
  **NO full 13C-MFA** per master plan §2.4.
- **Files**: ``.../isotope_tracing/flux_estimate.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-012 — ``PoolSizeNormalize``

- **Source**: LC-MS spec §9 T-LCMS-012
- **Summary**: IS / TIC / median normalization.
- **Files**: ``.../isotope_tracing/pool_size_normalize.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-LCMS-013 — ``MetaboliteMatrix``

- **Source**: LC-MS spec §9 T-LCMS-013
- **Summary**: PeakTable + SampleMetadata → wide matrix.
- **Files**: ``.../analysis/metabolite_matrix.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-014 — ``MatrixPreprocess``

- **Source**: LC-MS spec §9 T-LCMS-014
- **Summary**: Consolidated log / impute / scale (method param).
- **Files**: ``.../analysis/matrix_preprocess.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-015 — ``UnivariateStats``

- **Source**: LC-MS spec §9 T-LCMS-015
- **Summary**: t-test / ANOVA / Wilcoxon (method param).
- **Files**: ``.../analysis/univariate_stats.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-016 — ``MultivariateAnalysis``

- **Source**: LC-MS spec §9 T-LCMS-016
- **Summary**: PCA / PLSDA / OPLSDA (method param) → DataFrame +
  Artifact plot.
- **Files**: ``.../analysis/multivariate_analysis.py`` + tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-017 — ``PathwayEnrichment``

- **Source**: LC-MS spec §9 T-LCMS-017
- **Summary**: CodeBlock R wrapping MetaboAnalystR OR native
  Python implementation.
- **Files**: ``.../analysis/pathway_enrichment.py`` (and possibly
  an R script in ``.../analysis/scripts/``) + tests
- **Dependencies**: T-LCMS-002, T-TRK-013 (R runner audit)
- **Estimated diff size**: M
- **Coupling notes**: Standalone. Marker: ``requires_r`` if using
  the R path.

---

#### T-LCMS-018 — ``ConsumptionSecretionAnalysis``

- **Source**: LC-MS spec §9 T-LCMS-018
- **Summary**: Spent media vs fresh media Δ-concentration analysis,
  with optional cell-count normalization for per-cell-per-hour flux.
  NEW per user.
- **Files**: ``.../analysis/consumption_secretion_analysis.py`` +
  tests
- **Dependencies**: T-LCMS-002
- **Estimated diff size**: M
- **Coupling notes**: Standalone.

---

#### T-LCMS-019 — ``GraphPadBlock``

- **Source**: LC-MS spec §9 T-LCMS-019
- **Summary**: AppBlock subclass wrapping GraphPad Prism. Path TBD;
  if path is unknown at implementation time, file an issue and
  document the placeholder behaviour.
- **Files**: ``.../external/graphpad_block.py`` + tests
- **Dependencies**: T-LCMS-002, T-TRK-015
- **Estimated diff size**: M
- **Coupling notes**: Standalone. Marker: ``requires_graphpad``.

---

#### T-LCMS-020 — Entry-point registration + plugin smoke test

- **Source**: LC-MS spec §9 T-LCMS-020
- **Summary**: Update ``pyproject.toml`` entry points for every
  LC-MS block; add plugin smoke test; extend root
  ``pyproject.toml`` ``testpaths``.
- **Files**: ``packages/scistudio-blocks-lcms/pyproject.toml``,
  ``.../tests/test_plugin_smoke.py``, root ``pyproject.toml``
- **Dependencies**: T-LCMS-001 through T-LCMS-019 merged.
- **Estimated diff size**: S
- **Coupling notes**: Standalone.

---

#### T-LCMS-021 — Isotope tracing integration test

- **Source**: LC-MS spec §9 T-LCMS-021
- **Summary**: End-to-end pipeline test: load PeakTable + MIDTable
  + SampleMetadata → MetaboliteMatrix → MatrixPreprocess →
  Calculate13CEnrichment → CompareGroupMID → SaveTable. Verifies
  the full LC-MS happy path.
- **Files**: ``packages/scistudio-blocks-lcms/tests/integration/
  test_isotope_tracing_pipeline.py``
- **Dependencies**: T-LCMS-020
- **Estimated diff size**: M
- **Coupling notes**: Standalone. **Last ticket in Sprint E.**
  Marker: ``requires_lcms`` if any external-tool dependency is on
  the path; otherwise unmarked.

---

## 10. Summary table

One row per ticket. ``Diff`` column uses XS / S / M / L / XL.
``Sprint`` column uses A0 / A1 / A2 / A3 / A4 / A5 / B / C0 / C1 /
C2 / C3 / D0 / D1 / D2 / E0 / E1 / E2 / E3 per the dependency graph
in §4. ``Coupling`` column: Standalone (S) / Bundled (B) / Sequential
(Seq).

| Ticket       | Title                                            | Track | Sprint | Diff | Deps                          | Coupling |
|--------------|--------------------------------------------------|-------|--------|------|-------------------------------|----------|
| T-TRK-001    | Delete process/contrib/                          | 1     | A0     | XS   | none                          | S        |
| T-TRK-002    | Delete process/builtins/register.py              | 1     | A0     | XS   | none                          | S        |
| T-TRK-003    | Move transform.py → tests/fixtures/noop_block    | 1     | A0     | S    | none                          | S        |
| T-TRK-004    | Delete adapters + rewrite io_block.py as ABC     | 1     | A1     | M-L  | T-TRK-001..003                | B        |
| T-TRK-005    | (reserved — bundled into T-TRK-004)              | 1     | —      | —    | —                             | —        |
| T-TRK-006    | Block ABC dynamic-port hooks + framework migration | 1   | A2     | M    | T-TRK-004                     | B        |
| T-TRK-007    | LoadData + 6 _load_* private functions           | 1     | A3     | M    | T-TRK-006                     | S        |
| T-TRK-008    | SaveData + 6 _save_* private functions           | 1     | A3     | M    | T-TRK-006                     | S        |
| T-TRK-009    | Frontend BlockNode.tsx + computeEffectivePorts   | 1     | A4     | M    | T-TRK-007, T-TRK-008          | S        |
| T-TRK-010    | ARCHITECTURE/PROJECT_TREE/block-sdk docs         | 1     | A5     | M    | T-TRK-009                     | S        |
| T-TRK-011    | CLAUDE.md §2.5 + ARCHITECTURE.md ManualReview    | 1     | A0     | S    | none                          | S        |
| T-TRK-012    | FilterCollection metadata query                  | 1     | B      | M    | T-TRK-002                     | S        |
| T-TRK-013    | CodeBlock R runner audit                         | 1     | B      | S    | none                          | S        |
| T-TRK-014    | CodeBlock Python runner audit                    | 1     | B      | S    | T-TRK-003                     | S        |
| T-TRK-015    | AppBlock + Fiji functional audit                 | 1     | B      | M    | T-TRK-003                     | S        |
| T-IMG-001    | Types module (Image/Mask/Label/Transform)        | 2     | C0     | M    | T-TRK-006                     | S        |
| T-IMG-002    | LoadImage                                        | 2     | C1     | L    | T-IMG-001, T-TRK-004          | S        |
| T-IMG-003    | SaveImage                                        | 2     | C1     | M    | T-IMG-001, T-TRK-004          | S        |
| T-IMG-004    | Denoise                                          | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-005    | BackgroundSubtract                               | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-006    | Normalize                                        | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-007    | FlatFieldCorrect                                 | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-008    | Geometry bundle (Rotate/Flip/Crop/Pad/Resize)    | 2     | C1     | L    | T-IMG-001                     | B        |
| T-IMG-009    | ConvertDType                                     | 2     | C1     | S    | T-IMG-001                     | S        |
| T-IMG-010    | AxisSplit / AxisMerge                            | 2     | C1     | M    | T-IMG-001                     | B        |
| T-IMG-011    | Deconvolve placeholder                           | 2     | C1     | XS   | T-IMG-001                     | S (placeholder) |
| T-IMG-012    | MorphologyOp                                     | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-013    | EdgeDetect                                       | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-014    | RidgeFilter                                      | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-015    | Sharpen                                          | 2     | C1     | S    | T-IMG-001                     | S        |
| T-IMG-016    | FFTFilter                                        | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-017    | Threshold                                        | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-018    | Watershed                                        | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-019    | CellposeSegment (FLAGSHIP)                       | 2     | C2     | L    | T-IMG-001/004, T-TRK-015      | S        |
| T-IMG-020    | BlobDetect                                       | 2     | C1     | M    | T-IMG-001                     | S        |
| T-IMG-021    | ConnectedComponents                              | 2     | C1     | S    | T-IMG-001                     | S        |
| T-IMG-022    | Cleanup bundle (RemoveSmall/Border/Fill/Expand)  | 2     | C1     | M    | T-IMG-001                     | B        |
| T-IMG-023    | TrackObjects placeholder                         | 2     | C2     | XS   | T-IMG-001                     | S (placeholder) |
| T-IMG-024    | RegionProps                                      | 2     | C2     | L    | T-IMG-001                     | S        |
| T-IMG-025    | PairwiseDistance                                 | 2     | C2     | M    | T-IMG-001                     | S        |
| T-IMG-026    | Colocalization                                   | 2     | C2     | M    | T-IMG-001                     | S        |
| T-IMG-027    | ComputeRegistration                              | 2     | C2     | M    | T-IMG-001                     | S        |
| T-IMG-028    | ApplyTransform                                   | 2     | C2     | S    | T-IMG-001                     | S        |
| T-IMG-029    | RegisterSeries                                   | 2     | C2     | M    | T-IMG-001                     | S        |
| T-IMG-030    | AxisProjection / SelectSlice                     | 2     | C2     | M    | T-IMG-001                     | B        |
| T-IMG-031    | Math scalar bundle                               | 2     | C2     | S    | T-IMG-001                     | B        |
| T-IMG-032    | ImageCalculator (2-port-fixed in 0.1.0)          | 2     | C2     | M    | T-IMG-001, T-TRK-012          | S        |
| T-IMG-033    | Visualization bundle                             | 2     | C2     | L    | T-IMG-001                     | B        |
| T-IMG-034    | FijiBlock                                        | 2     | C2     | M    | T-IMG-001, T-TRK-015          | S        |
| T-IMG-035    | NapariBlock                                      | 2     | C2     | M    | T-IMG-001, T-TRK-015          | S        |
| T-IMG-036    | CellProfilerBlock                                | 2     | C2     | M    | T-IMG-001, T-TRK-015          | S        |
| T-IMG-037    | QuPathBlock                                      | 2     | C2     | M    | T-IMG-001, T-TRK-015          | S        |
| T-IMG-038    | Plugin packaging                                 | 2     | C3     | M    | T-IMG-001..037                | S        |
| T-SRS-000    | Package skeleton + entry points                  | 3     | D0     | S    | T-IMG-038                     | S        |
| T-SRS-001    | SRSImage type + Meta model                       | 3     | D0     | M    | T-SRS-000, T-IMG-001          | S        |
| T-SRS-002    | SRSCalibrate                                     | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-003    | SRSBaseline                                      | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-004    | SRSDenoise                                       | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-005    | SRSNormalize                                     | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-006    | SRSVCA                                           | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-007    | SRSUnmix                                         | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-008    | SRSPCA                                           | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-009    | SRSICA                                           | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-010    | SRSKMeansCluster                                 | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-011    | ExtractSpectrum                                  | 3     | D1     | M    | T-SRS-001                     | S        |
| T-SRS-012    | BandRatio                                        | 3     | D1     | S    | T-SRS-001                     | S        |
| T-SRS-013    | Plugin entry-point wiring + smoke test           | 3     | D2     | S    | T-SRS-000..012                | S        |
| T-SRS-014    | E2E integration test (cross-plugin)              | 3     | D2     | M    | T-SRS-013, T-IMG-038          | S        |
| T-LCMS-001   | Plugin scaffold                                  | 4     | E0     | S    | T-TRK-013, T-TRK-014          | S        |
| T-LCMS-002   | Types module                                     | 4     | E0     | M    | T-LCMS-001                    | S        |
| T-LCMS-003   | LoadMSRawFiles                                   | 4     | E1     | M    | T-LCMS-002, T-TRK-004         | S        |
| T-LCMS-004   | LoadPeakTable                                    | 4     | E1     | M    | T-LCMS-002                    | S        |
| T-LCMS-005   | LoadMIDTable                                     | 4     | E1     | M    | T-LCMS-002                    | S        |
| T-LCMS-006   | LoadSampleMetadata + SaveTable                   | 4     | E1     | M    | T-LCMS-002                    | B        |
| T-LCMS-007   | ElMAVENBlock + AccuCorR                          | 4     | E1     | L    | T-LCMS-002, T-TRK-013, T-TRK-015 | B    |
| T-LCMS-008   | Calculate13CEnrichment                           | 4     | E2     | M    | T-LCMS-002                    | S        |
| T-LCMS-009   | FractionalLabeling                               | 4     | E2     | S    | T-LCMS-002                    | S        |
| T-LCMS-010   | CompareGroupMID                                  | 4     | E2     | M    | T-LCMS-002                    | S        |
| T-LCMS-011   | FluxEstimate                                     | 4     | E2     | M    | T-LCMS-002                    | S        |
| T-LCMS-012   | PoolSizeNormalize                                | 4     | E2     | S    | T-LCMS-002                    | S        |
| T-LCMS-013   | MetaboliteMatrix                                 | 4     | E2     | M    | T-LCMS-002                    | S        |
| T-LCMS-014   | MatrixPreprocess                                 | 4     | E2     | M    | T-LCMS-002                    | S        |
| T-LCMS-015   | UnivariateStats                                  | 4     | E2     | M    | T-LCMS-002                    | S        |
| T-LCMS-016   | MultivariateAnalysis                             | 4     | E2     | M    | T-LCMS-002                    | S        |
| T-LCMS-017   | PathwayEnrichment                                | 4     | E2     | M    | T-LCMS-002, T-TRK-013         | S        |
| T-LCMS-018   | ConsumptionSecretionAnalysis                     | 4     | E2     | M    | T-LCMS-002                    | S        |
| T-LCMS-019   | GraphPadBlock                                    | 4     | E2     | M    | T-LCMS-002, T-TRK-015         | S        |
| T-LCMS-020   | Entry-point registration + smoke test            | 4     | E3     | S    | T-LCMS-001..019               | S        |
| T-LCMS-021   | Isotope tracing integration test                 | 4     | E3     | M    | T-LCMS-020                    | S        |

**Total: 89 tickets** (one reserved-no-implement: T-TRK-005). 88
implementation tickets across 4 tracks.

---

## 11. End-to-end test plan

Two phases. The Python headless variant runs first; the Chrome GUI
variant runs second after the imaging plugin's GUI registration is
verified.

### 11.1 Test images

Per Phase 11 master plan §8 and Q6 (this document), the four test
images live at::

    C:\Users\<user>\Desktop\workspace\Example\images\K562_L_2845 (uV).tif       (105 KB)
    C:\Users\<user>\Desktop\workspace\Example\images\K562_L_spectra (uV).tif    (2.0 MB)
    C:\Users\<user>\Desktop\workspace\Example\images\K562_UL_2845 (uV).tif      (105 KB)
    C:\Users\<user>\Desktop\workspace\Example\images\K562_UL_spectra (uV).tif   (2.0 MB)

Filenames contain spaces and parentheses; tests import from
``tests/fixtures/test_images.py`` (T-TRK-003) which centralises the
escaped paths.

The two ``_2845`` images are used for Cellpose segmentation; the two
``_spectra`` images are used for spectrum extraction.

### 11.2 Phase 1 — post-Sprint-C E2E (imaging only)

**Trigger**: After T-IMG-038 merges to ``main``.

**Workflow graph**::

    LoadImage[segmentation]    LoadImage[spectra]
      (K562_L_2845.tif           (K562_L_spectra.tif
       K562_UL_2845.tif)           K562_UL_spectra.tif)
       |                                |
       v                                v
     Denoise[Gaussian]          Denoise[Gaussian]
       |                                |
       v                                |
     CellposeSegment                    |
       |                                |
       v                                |
     Collection[Label]                  |
       \______________                  |
                      \                 |
                       v                v
                    ExtractSpectrum
                         |
                         v
                    DataFrame (spectra)

    SaveData (Collection[Label])  SaveData (DataFrame)

**Note**: Phase 1 uses the imaging plugin's ``ExtractSpectrum`` *if
it exists at this point* — but ``ExtractSpectrum`` is actually a
**Track 3 (SRS) block** (T-SRS-011). Phase 1 must therefore either:
(a) wait until T-SRS-011 also merges (which moves Phase 1 to
post-Sprint-D), OR (b) use a Track 2 surrogate
(``RegionProps`` with ``intensity_image=spectra``) to extract
per-region intensity statistics. Phase 11 master plan §8 endorses
**option (a)**: the canonical E2E test uses ``ExtractSpectrum``
from the SRS plugin.

Updated Phase 1 trigger: **after T-SRS-011 merges** (Sprint D
Level D1, before T-SRS-013).

**Python headless variant** (file:
``tests/integration/test_phase11_e2e_imaging_srs.py``)::

    import pytest
    from tests.fixtures.test_images import (
        SEGMENTATION_IMAGES, SPECTRA_IMAGES,
    )

    pytest.importorskip("scistudio_blocks_imaging")
    pytest.importorskip("scistudio_blocks_srs")

    from scistudio_blocks_imaging import LoadImage, Denoise, CellposeSegment
    from scistudio_blocks_srs import ExtractSpectrum
    from scistudio.blocks.io.savers import SaveData

    @pytest.mark.requires_cellpose
    def test_phase11_e2e_imaging_srs_pipeline(tmp_path):
        # Build a workflow with the 8 blocks above and execute via
        # workflow.execute(). Assert:
        #   1. All blocks reach the DONE state.
        #   2. Cellpose produces non-empty Label masks (>=1 object/image).
        #   3. ExtractSpectrum returns a DataFrame with the expected columns.
        #   4. Output files exist on disk at tmp_path.
        ...

**Success criteria** (verbatim from master plan §8):
1. All blocks reach ``DONE`` state.
2. Cellpose produces non-empty ``Label`` masks (at least 1 detected
   object per image).
3. ``ExtractSpectrum`` produces a DataFrame.
4. Output files exist on disk at the configured paths.
5. No exceptions propagate out of any block.

**Failure handling**: If any block raises, file an issue titled
``E2E BLOCKER: <block name> <error>``, label ``critical``, and
spawn a fix agent. Re-run the test after the fix merges. Cellpose
model auto-download on first run is acceptable; CPU slowness is
acceptable per master plan §8.

### 11.3 Phase 2 — post-Sprint-E E2E (full plugin set)

**Trigger**: After T-LCMS-021 merges.

**Adds to Phase 1**:
- An LC-MS arm: ``LoadPeakTable`` → ``MetaboliteMatrix`` →
  ``Calculate13CEnrichment`` → ``SaveTable``. Uses synthetic
  AccuCor-format CSV fixtures (no real ElMAVEN run required).
- Full ``pytest -x --no-cov`` across the entire monorepo
  (root + 3 plugin packages) must pass.

### 11.4 Chrome GUI E2E

**Trigger**: After Phase 1 Python headless passes.

**Tooling**: ``mcp__Claude_in_Chrome__*`` MCP tools per master plan
§10. Chrome path is user-confirmed working.

**Steps**:
1. Start the FastAPI GUI server (``scistudio gui`` or
   ``uvicorn scistudio.api.main:app``).
2. ``mcp__Claude_in_Chrome__navigate`` to ``http://localhost:8000``
   (or wherever the GUI is served).
3. Drag each block from the palette to the canvas.
4. Configure each block's params (set ``path`` to the test images,
   set ``core_type`` on each ``LoadData`` to ``Image``, etc.).
5. Connect the ports per the workflow graph in §11.2.
6. Click "Run".
7. Verify each block reaches the ``DONE`` visual state.
8. Verify the saved files exist on disk at the configured paths.

If any step fails, file an issue and spawn a fix agent. The Chrome
GUI E2E is treated as a stretch goal — Phase 1 Python headless is
the **must-pass** acceptance criterion for Sprint C completion.

---

## 12. References

- Phase 11 master plan: ``C:\Users\<user>\.claude\projects\C--Users-jiazh-Desktop-workspace\memory\phase11_master_plan.md``
- ADR-028 (IOBlock refactor): ``docs/adr/ADR.md`` — search for
  ``## ADR-028:``
- ADR-028 Addendum 1 (dynamic ports + GUI): ``docs/adr/ADR.md`` —
  search for ``## ADR-028 Addendum 1:``
- ADR-029 (preliminary, variadic port count): ``docs/adr/ADR.md`` —
  search for ``## ADR-029:``
- Imaging spec: ``docs/specs/phase11-imaging-block-spec.md``
- SRS spec: ``docs/specs/phase11-srs-block-spec.md``
- LC-MS spec: ``docs/specs/phase11-lcms-block-spec.md``
- Phase 10 standards (template basis): ``docs/specs/phase10-implementation-standards.md``
- ``CLAUDE.md`` Appendix A (workflow gate), §6.7 (tests), §9.2
  (no scope expansion)
- Architecture: ``docs/architecture/ARCHITECTURE.md``,
  ``docs/architecture/PROJECT_TREE.md``
- Block SDK guide: ``docs/guides/block-sdk.md``

---

*End of Phase 11 implementation standards.*
