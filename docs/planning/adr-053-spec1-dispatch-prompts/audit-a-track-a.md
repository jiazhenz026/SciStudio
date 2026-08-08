[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issues: #2020, #2021, #2009, #2022
- Issue URLs:
  https://github.com/jiazhenz026/SciStudio/issues/2020 ,
  https://github.com/jiazhenz026/SciStudio/issues/2021 ,
  https://github.com/jiazhenz026/SciStudio/issues/2009 ,
  https://github.com/jiazhenz026/SciStudio/issues/2022
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs, with no deferred scope; this is PR A, the runtime defects.
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Audited branch: fix/2020-adr-053-registry-runtime-defects (integrated A1 + A2 + A3)
- Audit branch: audit/adr-053-spec1-track-a
- Audit worktree: C:/Users/jiazh/workspace/SciStudio-wt-audit-a
- Gate record: create with `gate_record init --slug adr-053-spec1-track-a-audit`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md
- Commits to audit: every commit on `fix/2020-adr-053-registry-runtime-defects` since `origin/main`
- Audit report path: docs/audit/2026-08-07-adr-053-spec1-track-a.md

## Required Reading

- The four GitHub issues above and all owner instructions in them.
- The manager checklist `docs/planning/adr-053-spec1-personal-tool-library-checklist.md`, especially §1.2 owner decisions, §6.2 frozen contracts, and §7.
- The three dispatch prompts under `docs/planning/adr-053-spec1-dispatch-prompts/` (a1, a2, a3) — what each agent was actually told.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/personas/audit-reviewer.md
- docs/specs/adr-053-personal-tool-library.md — §2.4, §2.5, §2.6, §5, §10.3, §10.4, §14
- docs/adr/ADR-053.md §3

## Audit Goal

Verify the claimed work against the issues, the checklist, the governing spec, the code,
the tests, gate evidence, and CI.

Report findings first, ordered by severity:

- **P1**: blocks merge or breaks contract.
- **P2**: should fix before completion.
- **P3**: improvement or follow-up.

## Scope

Audit these claims:

- **FR-057/FR-058** — one shared helper provides drop-in directory registration and
  import-root injection, consumed by **all four** sites (API runtime, agent runtime,
  worker-side type reconstruction, IO dispatch). No call site independently decides which
  directories the tier comprises or which roots go on `sys.path`. Blocks and types resolve
  through the same tier definition. **Check for leftovers**: grep for any surviving
  `Path.home() / ".scistudio"` or `add_scan_dir` call that bypasses the helper.
- **FR-059** — the agent runtime registers project-level and user-level type directories.
  It registered none before. Verify the `make_mcp_runtime` docstring no longer claims
  coverage it lacks.
- **FR-060** — user-tier discovery is unconditional at all four points, for blocks and
  types alike; project-tier discovery still requires a project.
- **FR-061** — the inverted scan order between `BlockRegistry.scan()` and
  `TypeRegistry.scan_all()` is either reconciled or documented as deliberate **at both call
  sites**. If reconciled, verify observable precedence is unchanged.
- **FR-062** — the audit of registry-invalidating call sites is complete. A2 reported a
  list; independently enumerate `refresh_block_registry` call sites yourself and compare.
  The spec says the five known sites are "not necessarily all of them".
- **FR-063/FR-064** — package install/uninstall and branch switch refresh the type registry.
- **#2009** — the same refresh fix for the previewer registry. Confirm it did **not** grow
  into a user-level previewer tier or an `OwnerKind` change; that is #2017 and explicitly
  out of scope.
- **FR-065** — after a user library write the refresh reaches every process holding a
  registry. The write endpoint is Track B; verify either that this landed here or that the
  handoff to B1 is recorded in the repository, not only in chat.
- **FR-012 – FR-014** — a drop-in block imports a drop-in type by file name from the project
  and user types directories; the same roots are in `block_spec.runtime_import_roots` so the
  **worker** reconstructs identically; the project types directory shadows the user one.
  Verify the worker parity test actually runs the block, not merely registers it.
- **FR-015** — a failing drop-in surfaces the failing file, exception type, and message to a
  surface a user can see. Silent disappearance has ended. Verify the historical
  `"Failed to import block from"` log wording is preserved and the #1531 skip-don't-crash
  hardening is intact.
- **FR-016 / spec §13 OQ-1** — the owner decided **reject the file and report an error**.
  Verify the implementation rejects rather than warns, that a type file does not report
  itself as a collision, and that spec §13 OQ-1 is marked Resolved with the owner's answer.
- **Spec §2.5 reproduction** — reproduce it yourself against the audited branch. Do not take
  the agent's transcript on faith.

Audit these files or surfaces:

- `src/scistudio/core/dropins.py`
- `src/scistudio/core/types/{serialization,registry}.py`
- `src/scistudio/api/runtime/_projects.py`
- `src/scistudio/ai/agent/mcp/runtime.py`
- `src/scistudio/blocks/io/_unified_dispatch.py`
- `src/scistudio/blocks/registry/**`
- `src/scistudio/api/routes/{git,packages,blocks}.py`
- `src/scistudio/previewers/**`
- `tests/api/test_registry_provisioning_parity.py`, `tests/api/test_registry_reload_symmetry.py`, `tests/blocks/test_dropin_type_import.py`
- The three agents' gate ledgers under `.workflow/records/`

Also check:

- **Scope drift** — each agent stayed inside its declared write set, and the gate ledger was
  amended where it did not.
- **Deferral drift** — the owner directive is complete delivery. Any `TODO(#NNN)` added by
  this track is a finding unless the manager recorded owner authorization in checklist §9.
- **Test-change requirement** — implementation-category work must add or modify test files,
  not merely run tests.
- **Import-linter** — `scistudio.core` must not have gained a dependency on
  `scistudio.blocks`.
- **Ledger sanitization** — no absolute local paths, usernames, temp dirs, virtualenv paths,
  or raw transcripts in committed ledger events.

Do not write feature code. MUST write the audit report to the repository file named above.
Only write the audit report and your assigned checklist audit rows (§7.4).

## Coordination

- MUST work only on your assigned audit branch, in your assigned audit worktree.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- MUST NOT merge any PR.
- MUST NOT fix implementation code unless the manager explicitly changes your role to fix agent.
- Edit only the §7.4 checklist audit rows.
- Windows note: a post-commit hook fails with `ExecutableNotFoundError: Executable /bin/sh not found` (known issue #2011). The commit still lands; verify with `git log`.

## Checks

Run or verify:

- `PYTHONPATH=./src python -m pytest tests/api tests/blocks tests/core tests/previewers -q`
- The three new test files individually.
- The repository's import-linter command.
- Your own reproduction of spec §2.5, before and after.
- Sentrux MCP if available; otherwise `sentrux scan .` and `sentrux check .`, or record the CLI/MCP unavailability explicitly.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md` on the audited branch, to confirm ledger reconciliation and required-check completeness.

## Output Required

- Audit report path.
- Commit that contains the audit report file.
- Findings ordered by severity, each with evidence from code, tests, or tool output.
- Your independent enumeration of registry-invalidating call sites, compared against A2's.
- Your independent §2.5 reproduction result.
- Checklist drift, if any.
- Scope drift, if any.
- Missing tests/docs/gate evidence, if any.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if:

- You need to change implementation code.
- Required evidence is unavailable.
- The audit scope conflicts with AGENTS.md, ADR-053, the spec, or a gate record.
