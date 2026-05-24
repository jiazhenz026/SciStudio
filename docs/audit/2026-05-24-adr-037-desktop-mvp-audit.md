---
title: "ADR-037 Desktop MVP A5 Audit"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs: [37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47]
language_source: en
---

# ADR-037 Desktop MVP A5 Audit

## Findings

### P1 - Block: the current `desktop` candidate does not contain the MVP implementation.

The spec requires a runnable Electron MVP, successful desktop install/stage/start commands, and targeted CLI/package-discovery tests or recorded blockers
(`docs/planning/adr-037-desktop-mvp-spec.md:172`, `docs/planning/adr-037-desktop-mvp-spec.md:173`,
`docs/planning/adr-037-desktop-mvp-spec.md:174`, `docs/planning/adr-037-desktop-mvp-spec.md:175`,
`docs/planning/adr-037-desktop-mvp-spec.md:177`). The same checklist still shows A1-A4 and all verification evidence as pending
(`docs/planning/adr-037-desktop-mvp-checklist.md:123`, `docs/planning/adr-037-desktop-mvp-checklist.md:124`,
`docs/planning/adr-037-desktop-mvp-checklist.md:125`, `docs/planning/adr-037-desktop-mvp-checklist.md:126`,
`docs/planning/adr-037-desktop-mvp-checklist.md:166`, `docs/planning/adr-037-desktop-mvp-checklist.md:167`,
`docs/planning/adr-037-desktop-mvp-checklist.md:168`, `docs/planning/adr-037-desktop-mvp-checklist.md:169`,
`docs/planning/adr-037-desktop-mvp-checklist.md:170`).

Read-only inspection of this worktree found the expected implementation files absent:
`desktop/package.json`, `desktop/main.js`, `desktop/src/main.js`, `desktop/resources/packages/.gitkeep`,
`src/scistudio/paths.py`, and `tests/blocks/test_desktop_package_discovery.py` all returned `False` from `Test-Path`.
`src/scistudio/cli/main.py` still exposes only `--port` and `--no-browser`, with no `--bundled`, JSON ready line, or ephemeral-port handling
(`src/scistudio/cli/main.py:366`, `src/scistudio/cli/main.py:367`, `src/scistudio/cli/main.py:368`,
`src/scistudio/cli/main.py:389`, `src/scistudio/cli/main.py:396`, `src/scistudio/cli/main.py:398`).
Registry inspection found no `add_package_src_dir`, `SCISTUDIO_PLUGIN_PACKAGE_DIRS`, bundled package directory, or `desktop/packages` scan path.

Recommendation: do not treat the desktop branch as an MVP candidate until A1-A4 outputs are integrated, the specified files exist, and the acceptance checks have pass evidence or concrete blocker evidence.

### P1 - Block: gate evidence says implementation is done while committed task evidence says it is not.

The manager gate record lists planned implementation paths and required checks
(`.workflow/records/1502-adr-037-desktop-mvp-manager.json:33`, `.workflow/records/1502-adr-037-desktop-mvp-manager.json:37`,
`.workflow/records/1502-adr-037-desktop-mvp-manager.json:38`, `.workflow/records/1502-adr-037-desktop-mvp-manager.json:39`,
`.workflow/records/1502-adr-037-desktop-mvp-manager.json:40`, `.workflow/records/1502-adr-037-desktop-mvp-manager.json:44`,
`.workflow/records/1502-adr-037-desktop-mvp-manager.json:45`, `.workflow/records/1502-adr-037-desktop-mvp-manager.json:46`,
`.workflow/records/1502-adr-037-desktop-mvp-manager.json:47`, `.workflow/records/1502-adr-037-desktop-mvp-manager.json:48`),
but it has no check results, docs landing, commit, full audit, or Sentrux evidence
(`.workflow/records/1502-adr-037-desktop-mvp-manager.json:18`, `.workflow/records/1502-adr-037-desktop-mvp-manager.json:19`,
`.workflow/records/1502-adr-037-desktop-mvp-manager.json:20`, `.workflow/records/1502-adr-037-desktop-mvp-manager.json:21`,
`.workflow/records/1502-adr-037-desktop-mvp-manager.json:72`). Despite that, the `implement` stage is marked `done`
(`.workflow/records/1502-adr-037-desktop-mvp-manager.json:86`, `.workflow/records/1502-adr-037-desktop-mvp-manager.json:88`,
`.workflow/records/1502-adr-037-desktop-mvp-manager.json:89`).

That conflicts with ADR-042 expectations captured in the spec: committed gate evidence, checklist evidence, issue linkage, CI/readiness truth, and visible MVP gaps are mandatory
(`docs/planning/adr-037-desktop-mvp-spec.md:52`). It also conflicts with the checklist, which still records Sentrux, hooks, receipt, agent outputs, and final readiness as pending
(`docs/planning/adr-037-desktop-mvp-checklist.md:93`, `docs/planning/adr-037-desktop-mvp-checklist.md:103`,
`docs/planning/adr-037-desktop-mvp-checklist.md:104`, `docs/planning/adr-037-desktop-mvp-checklist.md:105`,
`docs/planning/adr-037-desktop-mvp-checklist.md:106`, `docs/planning/adr-037-desktop-mvp-checklist.md:183`,
`docs/planning/adr-037-desktop-mvp-checklist.md:185`, `docs/planning/adr-037-desktop-mvp-checklist.md:187`,
`docs/planning/adr-037-desktop-mvp-checklist.md:188`).

Recommendation: correct the gate stage truth before integration. Either move `implement` back to pending/in-progress or add the missing committed evidence after real implementation is integrated.

### P2 - The ADR-037-to-later-ADR impact plan is directionally sound, but none of the implementation-level later-ADR contracts are verifiable yet.

The spec correctly scopes the MVP away from full ADR-037 PyPI/per-plugin-venv behavior
(`docs/planning/adr-037-desktop-mvp-spec.md:59`, `docs/planning/adr-037-desktop-mvp-spec.md:60`,
`docs/planning/adr-037-desktop-mvp-spec.md:61`, `docs/planning/adr-037-desktop-mvp-spec.md:144`,
`docs/planning/adr-037-desktop-mvp-spec.md:160`, `docs/planning/adr-037-desktop-mvp-spec.md:161`).
It also records the main later-ADR constraints: project lineage and block versions from ADR-038, bundled git from ADR-039, package-resource skills from ADR-040, registry/capability APIs from ADR-041 and ADR-043, authoring-only subworkflows from ADR-044, server-authoritative websocket/file watcher behavior from ADR-045, scheduler avoidance from ADR-046, and registry Path D placement from ADR-047
(`docs/planning/adr-037-desktop-mvp-spec.md:48`, `docs/planning/adr-037-desktop-mvp-spec.md:49`,
`docs/planning/adr-037-desktop-mvp-spec.md:50`, `docs/planning/adr-037-desktop-mvp-spec.md:51`,
`docs/planning/adr-037-desktop-mvp-spec.md:53`, `docs/planning/adr-037-desktop-mvp-spec.md:54`,
`docs/planning/adr-037-desktop-mvp-spec.md:55`, `docs/planning/adr-037-desktop-mvp-spec.md:56`,
`docs/planning/adr-037-desktop-mvp-spec.md:57`).

Because the implementation is absent from the branch under audit, A5 cannot verify the critical later-ADR properties: `lineage.db` is not relocated, bundled git is used instead of system git, `src/scistudio/_skills/**` is staged through the Python package path, registry scanning goes through `BlockRegistry.scan()` and `FormatCapability` validation, websocket/file watcher events are not swallowed, scheduler internals are untouched, and registry changes stay in the ADR-047 sub-package shape.

Recommendation: after A1-A4 integration, rerun this audit against the integrated candidate and include targeted checks for each later-ADR invariant.

### P3 - Sibling agent outputs are not committed evidence yet.

Read-only inspection of the sibling worktrees showed A1, A3, manager, and A5 clean at `7a69adca`; A2 has only an untracked `src/scistudio/paths.py`; A4 has a branch but no dedicated worktree at the requested path. Untracked work is not committed gate evidence under ADR-042, and it is not part of the desktop branch candidate under audit.

Recommendation: require each implementation agent to commit or otherwise hand off artifacts through the manager integration branch before any readiness claim.

## Commands Run

- `git fetch origin desktop`
- `git worktree add -b adr-037-mvp-a5-audit C:\Users\jiazh\Desktop\workspace\SciStudio-desktop-a5 origin/desktop`
- `Get-Content AGENTS.md`
- `Get-Content docs/ai-developer/rules.md`
- `Get-Content docs/ai-developer/personas/audit-reviewer.md`
- `Get-Content docs/ai-developer/specific_rules/gated-workflow.md`
- `Get-Content docs/ai-developer/specific_rules/agent-dispatch.md`
- `Get-Content docs/planning/adr-037-desktop-mvp-spec.md`
- `Get-Content docs/planning/adr-037-desktop-mvp-checklist.md`
- `Get-Content docs/planning/dispatch-prompts/adr-037-desktop-mvp-a5-audit.md`
- `rg --files docs | rg 'ADR-0(37|38|39|40|41|42|43|44|45|46|47)|adr-0(37|38|39|40|41|42|43|44|45|46|47)'`
- `rg --files | rg '(^desktop/|src/scistudio/paths.py|test_desktop_package_discovery|package.json$|electron|desktop)'`
- `git branch --all --list '*adr-037*' '*desktop*'`
- `git status --short --branch` in A1, A2, A3, A5, and manager worktrees
- `Test-Path C:\Users\jiazh\Desktop\workspace\SciStudio-desktop-a4`
- `git log --oneline --decorate --all --branches='*adr-037*' --max-count=20`
- `Test-Path` for expected MVP files listed in Finding P1
- `rg -n "def gui|@.*gui|bundled|port" src/scistudio/cli/main.py`
- `rg -n "add_package_src_dir|SCISTUDIO_PLUGIN_PACKAGE_DIRS|bundled_packages_dir|desktop/packages|SCISTUDIO_DESKTOP_RESOURCES|include_monorepo|def scan" src/scistudio/blocks/registry src/scistudio`

## Recommendation

Block MVP readiness. The ADR impact plan is reasonable, but the desktop branch is still a planning branch with no integrated MVP implementation and inconsistent gate-stage truth.
