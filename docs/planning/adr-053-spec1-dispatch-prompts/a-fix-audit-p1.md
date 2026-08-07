[DISPATCH-TEMPLATE-V1: fix]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs, with no deferred scope. This slice fixes the P1 and P2 findings AUDIT-A raised against the integrated Track A branch.
- Task kind: bugfix
- Persona: implementer
- Issues: #2022 (both P1s), #2021 and #2009 (the FR-062 P2)
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Tracking branch (your merge target): fix/2020-adr-053-registry-runtime-defects
- Agent branch: fix/2022-audit-p1-shadowing-and-registration
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-afix
- Gate record: create with `gate_record init --slug 2022-audit-p1-shadowing-and-registration`
- Audit report you are fixing: `docs/audit/2026-08-07-adr-053-spec1-track-a.md` (on branch `audit/adr-053-spec1-track-a`)
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§7.4)

**Read the audit report first.** It contains the reproductions; do not re-derive them from scratch, but do re-run them so you can prove your fix works.

## Required Rules

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §5 (FR-012 – FR-016), §10.3, §10.4, §11, §13 OQ-1, §14

## Scope

You own:

- `src/scistudio/core/dropins.py`
- `src/scistudio/core/types/registry.py`
- `src/scistudio/blocks/registry/_scan.py`
- `src/scistudio/blocks/registry/__init__.py`
- `src/scistudio/api/routes/blocks.py`, `src/scistudio/api/routes/projects.py`
- `src/scistudio/ai/agent/mcp/tools_authoring.py`
- `src/scistudio/api/runtime/_projects.py`
- `tests/blocks/test_dropin_type_import.py`, `tests/api/test_registry_reload_symmetry.py`
- `docs/specs/adr-053-personal-tool-library.md`
- `CHANGELOG.md`

You must not touch:

- `src/scistudio/core/types/base.py` — protected core owned by B2 in PR B
- `frontend/**`
- `docs/ai-developer/**`
- `docs/planning/**` — the manager owns the checklist

## Coordination

- MUST work only on your branch, in your worktree. MUST NOT use `pip install -e .`; use `PYTHONPATH=./src`.
- MUST NOT open a PR. Push and report; the manager integrates.
- Add `--no-cov` to targeted pytest runs (the repo enforces a 70% global coverage gate a subset run cannot meet).
- Your branch is stacked, so set `SCISTUDIO_GATE_BASE=fix/2020-adr-053-registry-runtime-defects` for gate commands. That is the documented knob, not a bypass.
- `admin-approved:core-change` is required and **the owner has authorized it** (checklist §1.2). Record it with `--admin-label admin-approved:core-change`; CI verifies actor provenance.
- Windows: the `/bin/sh` post-commit hook error (#2011) is harmless; verify with `git log`. Stage everything before committing — pre-commit's unstaged stash also fails on Windows.
- Semantic-dup ratchet headroom is thin: **19 LOC** after A3. Prefer one shared implementation with thin adapters, and keep long rationale in module docstrings rather than on clustered functions.

## TODO And Deferral Rule

The owner directive is **complete delivery with no deferred scope**. Do not write a `TODO` to avoid work in this slice. If something genuinely cannot land, stop and report it as a blocker with reasoning.

## Work To Do

### P1-1 — the shadowing guard does not cover the worker (highest severity)

`_reject_shadowing_type_files` pre-binds the collided module **only inside**
`BlockRegistry._scan_tier1`. The worker never runs that path: it reconstructs a block through
`src/scistudio/blocks/registry/__init__.py:521-522`, which does
`prepended_sys_paths([Path(root) for root in spec.runtime_import_roots])` with **no
pre-binding**. AUDIT-A demonstrated with a real `python -m scistudio.engine.runners.worker`
run that a `{project}/types/sample_dep.py` shadows the installed `sample_dep` in the worker
while the parent process resolves the installed package.

This is a **new hazard introduced by Track A** — before #2022 the type directories were never
on `sys.path` — and it is exactly the scan-time-versus-run-time divergence FR-013 and FR-057
exist to prevent.

Fix it at the level the divergence lives at, not by copying the guard into a second place:

1. Move collision **detection and pre-binding** into one shared function in
   `src/scistudio/core/dropins.py`, beside the roots it protects. FR-057's principle is that
   no call site decides these semantics independently; a guard that only one of four
   processes runs is the same defect in a different shape.
2. Call it from **every** site that puts drop-in type roots on `sys.path` — at minimum
   `_scan_tier1` and the `runtime_import_roots` reconstruction path — so the installed module
   wins in the API, the agent, the worker, and IO dispatch alike.
3. Prove it: extend the worker-parity test so a `{project}/types/<name>.py` colliding with an
   installed top-level module leaves the **installed** module resolving inside the worker.
   AUDIT-A's reproduction is the model.

### P1-2 — "rejected" is announced but registration is not refused

`{project}/types/json.py` currently reports a `DropinTypeNameCollision` on the FR-015 surface
**and still registers its `DataObject` subclass in the `TypeRegistry`**, resolvable and
loadable. The user is told the file is rejected and must be renamed, while the type declared
in it silently keeps working. Nothing reconciles the two.

The owner resolved spec §13 OQ-1 as **"reject the file and report an error"**, and the
manager's recorded wording was "registration is refused". Make that true:

1. `TypeRegistry`'s drop-in filesystem pass MUST skip a type file whose stem collides,
   using the **same shared detection** as P1-1 — not a second copy of the rule.
2. The collision must still be reported, exactly as it is now.
3. Test it by constructing a `TypeRegistry` the way `ApiRuntime.refresh_type_registry` does
   and asserting the type is absent. **Not one of A3's 18 tests constructs a `TypeRegistry`**
   — that is why this survived. Close that hole.

### P2 — FR-062's event audit stopped at one method name

FR-062 is written in terms of **events that invalidate the registry**, but A2 enumerated only
`refresh_block_registry` call sites. Three more invalidation paths go through
`BlockRegistry.hot_reload()` and were never evaluated against the type and previewer
registries:

- `POST /api/blocks/reload` — `src/scistudio/api/routes/blocks.py:289`
- the file-save hook — `src/scistudio/api/routes/projects.py:491`
- MCP `reload_blocks` — `src/scistudio/ai/agent/mcp/tools_authoring.py:434`

Consequence today: **saving a file under `{project}/types/` refreshes nothing at all.** That
is the same class of defect #2021 exists to fix, on a path #2021 missed.

Fix all three so a type or previewer change is picked up the way a block change is. Reuse
`ApiRuntime.refresh_all_registries()` where a runtime is in hand; where only a registry is in
hand (the MCP tool), do the narrowest correct thing and say what you chose and why.

Also: A2's regression test asserts coverage by **grepping `api/routes/*.py` for three literal
method names**, so it structurally cannot see `hot_reload()` and its docstring overclaims what
it proves. Replace that with a test that exercises the behaviour — save a type file, assert
the type becomes resolvable — and correct the docstring.

### P2 — spec text

A3's FR-016 rewrite dropped the owner's "registration is refused" wording, and the §11
acceptance row now certifies a build that fails both P1s. Restore the owner's decision
wording, correct the §11 row so it describes what is actually tested, and correct the §14
risk paragraph, which currently claims the hazard is closed "by binding the real module before
any drop-in runs" — untrue in the worker until you fix P1-1.

### P3s — address, do not defer

1. **Directory-package collisions are undetected.** The collision scan globs `*.py` only, so a
   `{project}/types/json/` package directory is missed. Cover it or state in the code why a
   directory cannot reach `sys.path` here.
2. **The rejection eagerly imports the shadowed module on every scan.** A `numpy.py` collision
   imports numpy on each palette refresh. Bind once and cache, or import only when the module
   is not already in `sys.modules`.
3. **The sibling-`types/` inference is load-bearing but only documented.** `dropin_type_roots_for_block_dirs`
   assumes every block dir's sibling is its tier's type dir. Pin it with a test so a future tier
   layout change fails loudly rather than silently resolving nothing.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/blocks/test_dropin_type_import.py tests/api/test_registry_reload_symmetry.py tests/api/test_registry_provisioning_parity.py --no-cov -q`
- `PYTHONPATH=./src python -m pytest tests/api tests/blocks tests/core --no-cov -q`
- The repository's import-linter command — 13 contracts must stay kept.
- `SCISTUDIO_GATE_BASE=fix/2020-adr-053-registry-runtime-defects python -m scistudio.qa.governance.gate_record check --mode pre-pr --admin-label admin-approved:core-change`
- Note: 9 python tests fail on this Windows host on unmodified `origin/main` (POSIX unix sockets, POSIX shell rc, Windows path semantics, TOML escaping, the #2011 hook family). Reproduce any failure on the base before attributing it to your change. Linux CI is authoritative.

## Output Required

- Changed file paths.
- The shared collision-guard function's name and signature, and the list of every call site that now uses it.
- Your worker reproduction, before and after.
- Proof that a colliding type no longer registers, via a real `TypeRegistry`.
- What you did for the MCP `reload_blocks` path and why.
- Which P3s landed and how.
- Tests/checks run and results.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- Sharing the collision guard between `core/dropins.py` and `TypeRegistry` would violate an import-linter contract.
- Refusing registration breaks an existing type-resolution path.
- Fixing the `hot_reload()` sites requires touching files outside your write set.
- You cannot make the worker reproduction pass.
