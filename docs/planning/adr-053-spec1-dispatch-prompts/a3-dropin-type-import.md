[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs; this slice is spec §12.2 step 4, a verified defect that also blocks the parallel work-import spec.
- Task kind: bugfix
- Persona: implementer
- Issue: #2022
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2022
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Tracking branch (your merge target): fix/2020-adr-053-registry-runtime-defects
- Agent branch: fix/2022-dropin-type-import
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-a3
- Gate record: create with `gate_record init --slug 2022-dropin-type-import`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§7.3 rows A3)

Your branch starts from the tracking branch **after A1 (#2020) has landed**. The shared
drop-in provisioning helper `src/scistudio/core/dropins.py` already exists and already
exposes drop-in import roots. Consume it. You may extend it if the import-root surface is
insufficient, but you MUST NOT re-implement directory resolution locally.

## Required Rules

Read and follow:

- The GitHub issue `#2022`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §2.5, §5 (FR-012 – FR-016), §13 OQ-1, §14
- docs/adr/ADR-053.md §3

## Scope

You own only:

- `src/scistudio/blocks/registry/_scan.py`
- `src/scistudio/blocks/registry/__init__.py` and `src/scistudio/blocks/registry/_spec.py` if `runtime_import_roots` requires it
- `src/scistudio/core/dropins.py` — **import-roots surface only**, and only if A1's surface is insufficient
- `src/scistudio/api/routes/blocks.py` — **failure surfacing only** (FR-015)
- `src/scistudio/api/schemas.py` — only a response field for FR-015, if you need one
- `docs/specs/adr-053-personal-tool-library.md` — mark §13 OQ-1 resolved
- `tests/blocks/test_dropin_type_import.py` (new)
- `CHANGELOG.md` (one entry)

You must not touch:

- `src/scistudio/api/runtime/_projects.py`, `routes/git.py`, `routes/packages.py` — A2 owns them
- `src/scistudio/core/types/base.py` — protected core, owned by B2
- `src/scistudio/api/routes/{types,user_library}.py` — Track B
- Any `frontend/**` path
- `docs/ai-developer/**`

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone. A2 runs in parallel on `api/routes/{git,packages}.py` and
  `api/runtime/_projects.py`. A second manager's spec 2 track depends on your fix.
- MUST work only on your assigned branch, in your assigned worktree.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- MUST NOT open a PR. Push your branch and report; the manager integrates.
- Edit only your own checklist rows (§7.3 rows beginning `A3`).

## TODO And Deferral Rule

Deferred work must be tracked with `TODO(#NNN): <reason>` citing an issue, ADR, spec, or
follow-up ticket. The owner directive is **complete delivery with no deferred scope** —
if something must be deferred, stop and report it as a blocker.

Known deferred items: N/A. In particular, sandboxing drop-in execution (#1531) is
explicitly out of scope and unchanged; do not attempt it and do not weaken the existing
`#1531` skip-don't-crash hardening.

## Work To Do

1. **Reproduce the defect first** and record the reproduction in your report. Spec §2.5
   gives the exact case: `{project}/types/spectrum.py` defining `SpectrumData(DataObject)`,
   `{project}/blocks/uses_spectrum.py` doing `from spectrum import SpectrumData` and
   declaring it on both ports. Expected current behaviour: `ModuleNotFoundError: No module
   named 'spectrum'`, the block silently absent from the registry.

2. **FR-012** — a drop-in block MUST be able to import a drop-in type by file name from
   the project types directory and from the user types directory. Those directories join
   `sys.path` for the duration of drop-in block execution, alongside the existing user site
   directory. Today `prepended_sys_paths(_desktop_user_python_import_roots())`
   (`src/scistudio/blocks/registry/_scan.py:189`) supplies only the user site directory.

3. **FR-013 — worker parity.** The same roots MUST be recorded in
   `block_spec.runtime_import_roots` so the worker subprocess reconstructs the block
   identically. A block that imports during palette scanning and fails at run time is not
   a fix. Cover this with a test that actually runs the block in the worker path, not just
   registers it.

4. **FR-014** — the project types directory MUST resolve ahead of the user types
   directory, so a project-local type shadows a user-level type of the same file name.

5. **FR-015 — silent disappearance ends.** A drop-in block that fails to import MUST
   surface the failure to the user: at minimum the failing file, the exception type, and
   the message must reach a surface the user can see. Today it is a server-side warning
   only and the block simply vanishes.

   The mechanism is yours to choose. Constraints: keep the historical
   `"Failed to import block from"` log wording (a registry-logging contract test asserts
   it); do not let one failing drop-in prevent the rest of the scan (#1531); and prefer
   carrying the failures on an existing API response the palette already fetches over
   inventing a new polling surface.

6. **FR-016 / spec §13 OQ-1 — OWNER DECISION, ALREADY MADE.** The owner decided:
   **reject the file and report an error.** A type file whose stem collides with an
   importable top-level module (`json.py`, `numpy.py`, ...) MUST be refused registration,
   with a clear error reported through the same FR-015 surface. Do not implement the
   warn-and-load or the warn-and-exclude variants.

   Collision test: the stem resolves to an importable top-level module other than the
   drop-in file itself. Use `importlib.util.find_spec` against a `sys.path` that does not
   include the types directories, so a type file never reports itself as a collision.

   Then edit `docs/specs/adr-053-personal-tool-library.md` §13 to mark OQ-1 **Resolved**
   with the owner's answer, in the same style §13 already uses for OQ-2.

7. **FR-057 note** — the roots MUST be identical in every process that loads drop-in
   blocks: the API, the agent, the worker, and IO dispatch. That obligation is discharged
   by A1's shared helper; your job is to consume it, not to edit four call sites.

   A1 landed `src/scistudio/core/dropins.py`. The function you want is:

   ```python
   dropin_import_roots(project_dir: str | Path | None = None) -> tuple[Path, ...]
   #   == (<project>/types, ~/.scistudio/types, *user_python_import_roots())
   ```

   The ordering already satisfies FR-014 — project types ahead of user types — so do not
   re-sort it. `project_dir=None` **is** the declaration "no project context exists".
   Paths are returned whether or not they exist; `prepended_sys_paths` filters missing
   roots. Get the project dir from `project_dir_from_env()` where you have no better source.

7a. **FR-061 gap left by A1 — you own the fix.** Spec §10.3 FR-061 says that if the two
   scan orders are kept separate, "the reason MUST be recorded **at both call sites**."
   A1 kept them separate and recorded a thorough rationale on the type side
   (`scistudio/core/types/registry.py` module docstring, "Scan order versus BlockRegistry",
   pointed at from `scan_all()`). The **block side was not touched**, so a reader arriving
   at `BlockRegistry.scan()` has no record.

   You own `src/scistudio/blocks/registry/__init__.py`. Add a short back-pointer at
   `BlockRegistry.scan()` to that record — a few lines naming FR-061, stating that the pass
   order deliberately differs from `TypeRegistry.scan_all()`, and pointing at the type
   registry module docstring for the reason. Do not restate the whole rationale; a
   duplicated rationale is the drift this spec exists to remove.

8. **Write `tests/blocks/test_dropin_type_import.py`** covering: the §2.5 reproduction now
   registers `uses_spectrum` (FR-012); the worker runs it, not just registers it (FR-013);
   a project type shadows a user type of the same name (FR-014); an import failure reaches
   the user-visible surface (FR-015); a colliding filename is rejected with an error and
   the real module still imports (FR-016).

9. Update `CHANGELOG.md` with one entry.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/blocks/test_dropin_type_import.py -q`
- `PYTHONPATH=./src python -m pytest tests/blocks tests/api tests/core -q`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base fix/2020-adr-053-registry-runtime-defects --head HEAD`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2022"`
- Do NOT run `scripts/scistudio_pr_create.py`; you are not opening a PR.

You are editing a spec file (`docs/specs/adr-053-personal-tool-library.md`). That is a
product spec, not a governance surface — `docs/ai-developer/**` is untouched, so
`governance_touch` stays false. Record the spec path and `CHANGELOG.md` as docs updates in
your ledger.

## Protected-Core Label — Manager Note

`PROTECTED_CORE_PATTERNS` (`src/scistudio/qa/governance/gate_record/surfaces.py`) covers
`src/scistudio/{core,engine,blocks,workflow,utils}/**`. Your write set touches it, so
`gate_record check` will fail `guard.core_change_guard` and **block your local commit**.

Record the label as a request on your own ledger so you can commit:

```bash
gate_record amend --reason "protected-core surface: <files>; manager is obtaining owner authorization for the PR A label" --admin-label admin-approved:core-change
```

Local ledger records of requested labels are **not authoritative** — ADR-042 Addendum 6
§2.7 makes CI the sole authority on label actor provenance. The manager is obtaining owner
authorization for the integration PR. Do not claim the label was granted to you, and do
not weaken or move code out of protected paths to dodge the guard.

## Semantic-Dup Ratchet Warning

The ratchet is razor-thin on `main`: 119/120 clusters, 6970/7000 duplicate LOC. **Duplicate
LOC counts docstring lines**, so a long docstring on a function that already sits in a
cluster can break the gate on its own. A1 left roughly 26 LOC of headroom for every
remaining agent. Prefer one implementation with thin wrappers over parallel block/type
twins, and put long rationale in a module docstring rather than on a clustered function.

## Output Required

- Changed file paths.
- The reproduction transcript, before and after.
- Which FR-015 surface you chose and why.
- Tests/checks run and results.
- Checklist rows updated.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- A1's helper does not expose a usable import-root surface and extending it would change
  A1's contract.
- Making the types directories importable breaks an existing test in a way you cannot
  resolve inside your write set.
- The FR-016 rejection cannot distinguish a real collision from the type file itself.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
