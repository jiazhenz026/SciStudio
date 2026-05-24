---
title: "ADR-037 Desktop MVP Agent Dispatch Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs: [37, 38, 39, 40, 42, 43, 45, 47]
language_source: en
---

# ADR-037 Desktop MVP Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Build an MVP desktop distribution from ADR-037 on a protected
  desktop branch, after writing a full implementation spec and checking later
  ADR impact.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1502`
- Gate record:
  `.workflow/records/1502-adr-037-desktop-mvp-manager.json`
- Branch/worktree plan: manager integrates on
  `adr-037-desktop-mvp-manager` in
  `C:\Users\jiazh\Desktop\workspace\SciStudio-desktop-mvp`; agents use
  sibling worktrees off `desktop`.
- Protected branch: `main`
- Desktop integration branch: `desktop`
- Umbrella PR: `N/A per owner instruction: no PR to main tonight`
- Umbrella PR title: `N/A`
- Final PR target: `desktop`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `docs/planning/adr-037-desktop-mvp-spec.md`
  - `docs/planning/adr-037-desktop-mvp-checklist.md`
  - `docs/planning/dispatch-prompts/adr-037-desktop-mvp-*.md`
  - `desktop/**`
  - `src/scistudio/paths.py`
  - `src/scistudio/cli/main.py`
  - `src/scistudio/blocks/registry/**`
  - targeted tests under `tests/cli/`, `tests/blocks/`, `tests/packaging/`
  - `pyproject.toml` only for runtime dependency metadata
- Out of scope:
  - full PyPI plugin browser
  - per-plugin venvs
  - signing/notarization/auto-update
  - telemetry implementation
  - scheduler internals
  - frontend UX beyond build/staging smoke unless explicitly needed
- Protected paths:
  - `.agents/**`, `.claude/**`, `.codex/**`, `.github/**` unless manager
    amends the gate record
- Deferred work:
  - TODOs must cite #1502 or ADR-037 sections.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager worktree created -> `SciStudio-desktop-mvp`
- [x] Open issue created -> #1502
- [x] Gate record started -> `.workflow/records/1502-adr-037-desktop-mvp-manager.json`
- [x] Scope include/exclude recorded in the gate record -> gate record start
- [x] Desktop integration branch created -> `origin/desktop`
- [x] Umbrella PR intentionally not opened -> owner requested no PR to main
- [x] Protected branch and desktop branch recorded in this checklist
- [x] No `pip install -e .` used -> manager used `PYTHONPATH=src`
- [~] Dispatch checklist copied from the template and committed
- [~] Dispatch prompts created from the correct prompt template and linked
      below
- [ ] Sentrux baseline recorded, or N/A reason recorded

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` | `[ ]` | `pending` |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | `pending` |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | `pending` |
| Receipt | `python -m scistudio.qa.governance.gate_receipt validate --gate-record .workflow/records/1502-adr-037-desktop-mvp-manager.json --base origin/desktop --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | `pending` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `yes`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: MVP spec records the owner-authorized
  deviation from opening a `[DO NOT MERGE]` main PR tonight.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | implementer | N/A | `docs/planning/dispatch-prompts/adr-037-desktop-mvp-a1-desktop-shell.md` | Electron shell and staging scripts | `adr-037-mvp-a1-desktop-shell` | `SciStudio-desktop-a1` | `desktop/**` | `src/**`, `frontend/src/**` | #1502 | `[ ]` |
| A2 | implementer | N/A | `docs/planning/dispatch-prompts/adr-037-desktop-mvp-a2-cli-paths.md` | CLI bundled mode and paths module | `adr-037-mvp-a2-cli-paths` | `SciStudio-desktop-a2` | `src/scistudio/cli/main.py`, `src/scistudio/paths.py`, `tests/cli/test_cli.py` | `desktop/**`, registry | #1502 | `[ ]` |
| A3 | implementer | N/A | `docs/planning/dispatch-prompts/adr-037-desktop-mvp-a3-package-discovery.md` | Hard-installed packages discovery | `adr-037-mvp-a3-package-discovery` | `SciStudio-desktop-a3` | `src/scistudio/blocks/registry/**`, `tests/blocks/test_desktop_package_discovery.py` | `desktop/**`, CLI | #1502 | `[ ]` |
| A4 | test_engineer | N/A | `docs/planning/dispatch-prompts/adr-037-desktop-mvp-a4-validation.md` | Validation scripts and smoke tests | `adr-037-mvp-a4-validation` | `SciStudio-desktop-a4` | `tests/packaging/**`, `desktop/scripts/**` validation-only | production code unless explicitly blocked | #1502 | `[ ]` |
| A5 | audit_reviewer | with-context | `docs/planning/dispatch-prompts/adr-037-desktop-mvp-a5-audit.md` | ADR impact and MVP readiness audit | `adr-037-mvp-a5-audit` | `SciStudio-desktop-a5` | `docs/audit/2026-05-24-adr-037-desktop-mvp-audit.md` | production code | #1502 | `[ ]` |

## 7. Tracks

### 7.1 A1 Desktop Shell

- [ ] Electron package scaffold -> pending
- [ ] Main process port handshake -> pending
- [ ] Resource staging scripts -> pending
- [ ] `npm --prefix desktop run stage` evidence -> pending

### 7.2 A2 CLI And Paths

- [ ] `scistudio gui --bundled --port 0` -> pending
- [ ] `scistudio.paths` resolver -> pending
- [ ] CLI regression tests -> pending

### 7.3 A3 Hard-Installed Packages

- [ ] Registry package src discovery -> pending
- [ ] Tests with fake `desktop/packages/scistudio-blocks-*` source package -> pending
- [ ] No per-plugin venv/PyPI behavior introduced -> pending

### 7.4 A4 Validation

- [ ] Packaging checks -> pending
- [ ] Smoke commands recorded -> pending
- [ ] Known blockers written to checklist -> pending

### 7.5 A5 Audit

- [ ] Later ADR impact reviewed -> pending
- [ ] MVP deferrals checked for visibility -> pending
- [ ] Audit report committed -> pending

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Frontend build | `npm --prefix frontend run build` | `[ ]` | `pending` |
| Desktop install | `npm --prefix desktop install` | `[ ]` | `pending` |
| Desktop stage | `npm --prefix desktop run stage` | `[ ]` | `pending` |
| CLI tests | `$env:PYTHONPATH='src'; pytest tests/cli/test_cli.py --timeout=60` | `[ ]` | `pending` |
| Package discovery tests | `$env:PYTHONPATH='src'; pytest tests/blocks/test_desktop_package_discovery.py --timeout=60` | `[ ]` | `pending` |
| Gate pre-commit | `$env:PYTHONPATH='src'; python -m scistudio.qa.governance.gate_record pre-commit --staged` | `[ ]` | `pending` |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-24 | manager | Dispatch rule normally requires umbrella PR, but owner explicitly requested no PR to main tonight. | Use remote `desktop` branch and committed checklist/prompts as visibility evidence. | #1502 |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] Remote `desktop` branch contains the MVP.
- [ ] CI status or local blocker status is reported truthfully.
