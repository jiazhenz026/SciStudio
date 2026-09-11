---
title: "ADR-055 Spec 4 Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
related_specs:
  - adr-055-enterprise-support
  - adr-055-identity-seam
language_source: en
---

# ADR-055 Spec 4 Dispatch Prompts

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
Checklist: `docs/planning/adr-055-spec4-checklist.md`.

## A1 — O1: Capability Extensions And Enterprise UI (#2322)

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: implement ADR-055 Spec 4 (open-source side) as the manager's
  O1 track: capability extensions in the seam plus the capability-gated
  enterprise UI (owner, 2026-09-11).
- Task kind: feature
- Persona: implementer
- Issue: #2322
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2322
- Umbrella issue: #2321 (it holds the shared capability contract; read it)
- Umbrella PR: #UMBRELLA_PR `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-055-spec4
- Agent branch: feat/2322-enterprise-ui (create it from origin/main)
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/feat-2322-enterprise-ui
- Gate record: .workflow/records/2322-feat-2322-enterprise-ui.json
- Checklist: docs/planning/adr-055-spec4-checklist.md (on track/adr-055-spec4)

## Required Rules

Read and follow:

- Issues #2322 and #2321 (the shared capability contract table) and all owner
  instructions in them.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-055-enterprise-support.md (FR-003 to FR-007, FR-014, FR-015;
  stories 3, 4, 6 and 7)
- docs/specs/adr-055-identity-seam.md (FR-014 to FR-016, section 4.5)
- ADR-052, for provisional public API rules.

## Scope

You own only:

- src/scistudio/api/seam.py
- src/scistudio/api/spa.py
- src/scistudio/api/app.py. You may touch it only if it is needed to expose
  the capabilities to route handlers, for example on `app.state`. Keep it
  minimal.
- src/scistudio/api/routes/ai_pty/** (the agent-kind refusal)
- frontend/src/lib/capabilities.ts and its test
- frontend/src/lib/api/data.ts (upload progress and cancel)
- frontend/src/components/Enterprise/** (new)
- frontend/src/components/BottomPanel.tsx and BottomPanel.parts/**
- frontend/src/components/Toolbar.tsx and Toolbar.parts/** (the identity
  chrome placement). PR #2319 just reworked these files; build on it.
- The one frontend file-actions or context-menu component where a "Download
  to this computer" action belongs. Name it in a `gate_record amend` before
  editing it.
- tests/api/test_enterprise_capabilities.py (new),
  tests/api/test_ai_pty_capability.py (new),
  tests/api/test_identity_seam.py, tests/api/seam_contract.py (only if the
  capability shape needs it), tests/api/test_public_surface.py,
  tests/api/public_surface.snapshot.json
- docs/specs/adr-055-enterprise-support.md,
  docs/specs/adr-055-identity-seam.md, CHANGELOG.md,
  src/scistudio/_agent_reference/public-api.md, plus the generated reference
  pages. Regenerate them with the repo's script; never hand-edit them.

You must not touch:

- src/scistudio/api/routes/webmcp.py, src/scistudio/cli/** (A2 owns these)
- src/scistudio/core/** (a stop condition)
- docs/ai-developer/**
- Anything that implements an enterprise backend route. This repository only
  consumes capability URLs.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase. A2 works in parallel on the stdio
  adapter (#2308).
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Use the shared interpreter
  C:/Users/jiazh/workspace/SciStudio/.venv/Scripts/python with
  `PYTHONPATH=src`, the same for the gate commands.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- Your final PR targets `main` (manager-assigned final PR).
- MUST NOT merge any PR.
- Edit only your checklist rows. The manager updates the checklist on the
  umbrella branch; report row evidence in your final message.
- Run long commands in the foreground. Do not wait on background monitors.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- Panel prefix registration: #2288 (ADR-054 paused). Do not implement.

## Work To Do

1. Create the worktree and branch from origin/main. Run `gate_record init`
   with task-kind feature, persona implementer, issue 2322 and your include
   set. Then run `plan`.
2. Seam, following the #2321 contract.
   - Make `identity.logout_url` optional.
   - Add `ai_chat_disabled` (true or absent).
   - Make `transfer` an object `{inline_max_bytes, download_url_template}`.
     A breaking change to the provisional API needs a CHANGELOG entry per
     ADR-052. Keep `False`/`None` meaning off.
   - Add `update` `{status_url, restart_url}`.
   - Every URL is a backend route path without the service prefix: a leading
     `/`, not `//`, no scheme, no whitespace or control characters. The
     download template must contain exactly one `{path}` placeholder.
   - Absent still means off, and nothing is injected when all are off.
   - Extend the escaped page injection (FR-015) and add a version field.
3. Frontend accessor: extend `getCapabilities()` and read each malformed field
   as off. Resolve capability URLs under the service prefix exactly as API
   calls are resolved.
4. Enterprise components.
   - Identity chrome: the user name, plus Logout when `logout_url` is given.
     Logout sends a same-origin POST, reads `{location}` from the JSON
     response, and navigates there.
   - Update notice: poll `status_url` every 60 s and on window focus. It is
     non-blocking and never steals focus. Restart needs confirmation, warns
     when `runs_active`, then POSTs `restart_url` and navigates to the
     returned location.
   - Transfer: an upload picker through the existing staged
     `POST /api/data/upload`, with progress and cancel, and a download action
     using the template with a URL-encoded project-relative path.
   - Nothing renders for an absent capability.
5. AI chat: when `ai_chat_disabled` is set, hide the AI Chat surface in
   `BottomPanel`. The backend refuses any `/api/ai` PTY session whose provider
   is agent-kind in the provider registry, with a clear error and no spawned
   process. `user-terminal`, including tutorial-replay adoption, is never
   gated.
6. Tests: cover every capability both present and absent, at the root mount
   and under `/user/alice/scistudio`. Keep the default-unchanged regression.
   Use neutral example route paths in tests.
7. Docs: amend the open-source spec for the dynamic `update` shape and the
   contract details, update seam FR-014 to FR-016, and add a CHANGELOG entry.
8. Commit with trailers (`Gate-Record:`, `Task-Kind:`, `Issue:`,
   `Assisted-by: claude-code:claude-opus-5`, and the Co-Authored-By line the
   session gives). Run the pre-PR check on the committed diff, then pre-PR
   finalize with `--commit <evidence sha>`. Open the PR with the wrapper
   (Closes #2322, Refs #2321). Then post-PR finalize with `--commit` and
   `--pr`, and push.

## Required Tests And Checks

- `PYTHONPATH=src <venv python> -m pytest tests/api/test_enterprise_capabilities.py tests/api/test_ai_pty_capability.py tests/api/test_identity_seam.py tests/api/test_public_surface.py -q`
- `npm --prefix frontend run test -- --run src/lib/capabilities.test.ts src/components/Enterprise`,
  plus frontend lint and typecheck
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` to run
  tier-selected checks and reconcile the gate ledger before PR
  creation (receipt behavior is folded into the ledger per ADR-042 Addendum 6;
  there is no separate `gate_receipt` command)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2322"` before PR creation
- `python scripts/scistudio_pr_create.py` for the final PR (do not use
  `gh pr create` directly)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after PR is created
- Sentrux: N/A (MCP not available in this runtime)

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist row evidence (§7.3).
- PR number and commit.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
```

## A2 — O2: Stdio MCP Adapter And Loopback Token File (#2308)

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: implement ADR-055 Spec 4 (open-source side) as the manager's
  O2 track: a local stdio MCP adapter over the WebMCP HTTP bridge, for AI apps
  that support local MCP servers but not WebMCP (owner option B, 2026-09-11).
- Task kind: feature
- Persona: implementer
- Issue: #2308
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2308
- Umbrella issue: #2321
- Umbrella PR: #UMBRELLA_PR `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-055-spec4
- Agent branch: feat/2308-webmcp-adapter (create it from origin/main)
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/feat-2308-webmcp-adapter
- Gate record: .workflow/records/2308-feat-2308-webmcp-adapter.json
- Checklist: docs/planning/adr-055-spec4-checklist.md (on track/adr-055-spec4)

## Required Rules

Read and follow:

- Issue #2308, umbrella #2321, and all owner instructions in them.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-055-enterprise-support.md (FR-008 to FR-011, story 5)
- docs/specs/adr-055-webmcp-bridge.md (the adapter result contract, FR-005
  project binding, FR-007 logging)
- docs/specs/adr-055-identity-seam.md (what "a replacement guard is installed"
  means)

## Scope

You own only:

- src/scistudio/cli/webmcp_adapter.py (new)
- src/scistudio/cli/main.py (register the subcommand)
- src/scistudio/api/routes/webmcp.py (the loopback token file lives with the
  default guard's token minting)
- tests/cli/test_webmcp_adapter.py (new), tests/api/test_webmcp.py
- docs/specs/adr-055-enterprise-support.md (the adapter section only; A1 edits
  other sections, so keep your hunks local), CHANGELOG.md

You must not touch:

- src/scistudio/api/seam.py, src/scistudio/api/spa.py,
  src/scistudio/api/app.py, src/scistudio/api/routes/ai_pty/**, frontend/**
  (A1 owns these). If the token file truly needs app.py, stop and report.
- src/scistudio/cli/mcp_bridge.py and the local socket audience rule from
  #2275
- src/scistudio/core/**, docs/ai-developer/**

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase. A1 works in parallel on the seam and the
  frontend.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Use the shared interpreter
  C:/Users/jiazh/workspace/SciStudio/.venv/Scripts/python with
  `PYTHONPATH=src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- Your final PR targets `main` (manager-assigned final PR).
- MUST NOT merge any PR.
- Report checklist row evidence (§8.3) in your final message.
- Run long commands in the foreground. Do not wait on background monitors.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- User-guide page for external-AI mode: #2290. Do not write it here.

## Work To Do

1. Create the worktree and branch from origin/main. Run `gate_record init`
   (feature, implementer, issue 2308) and then `plan`.
2. Loopback token file (FR-010). With the default guard only, write the
   per-launch loopback token to a file in the per-user SciStudio state
   directory.
   - Contents: token, backend PID, port, and base URL including any root
     path.
   - Permissions: readable only by the current OS user (0600 on POSIX; on
     Windows, the per-user profile ACL; document it).
   - Write it atomically and remove it on shutdown.
   - Never write it when a replacement guard is installed.
   - With several backends running, pick a documented rule, such as one file
     per port plus a "latest" pointer, and test it.
3. Adapter: a `scistudio` subcommand, for example `scistudio webmcp-adapter`.
   - It speaks MCP over stdio and forwards `tools/list` to
     `GET /api/webmcp/tools` and `tools/call` to `POST /api/webmcp/call`, on a
     configurable base URL that honors a service prefix.
   - It keeps no tool registry of its own and preserves the Spec 1 result
     contract: `isError`, structured content, and non-text content.
   - It carries the catalogue's project snapshot. On
     `409 stale_project_context` it re-fetches, emits
     `notifications/tools/list_changed`, and reports the stale call as an
     error. It never retries a mutation silently.
4. Credentials (FR-009).
   - `--token` or `SCISTUDIO_MCP_TOKEN` sends `Authorization: Bearer <token>`
     on every bridge request. An edition's guard validates it; the lab uses a
     JupyterHub API token.
   - With no token and a loopback base URL, use the token file from step 2,
     sent as the existing `x-scistudio-webmcp-token` header.
   - Refuse a missing, stale, or non-owner-only token file with a clear
     message.
   - Never print or log a credential.
5. Startup: wait a bounded time for the backend, then exit with a clear
   configuration error. On an auth error, name the base URL.
6. Logging (FR-011): operation identifiers and outcomes only, never
   arguments. Add a `--print-config {claude-desktop,claude-code,codex}`
   option that prints a ready-to-paste snippet.
7. Tests:
   - catalogue parity with the bridge, including `audience:external` tools;
   - result-contract fixtures;
   - stale-context handling;
   - bearer header;
   - token-file permission refusal;
   - a scan confirming no credential appears in logs;
   - token file lifecycle with the default guard and with a replacement guard.
8. Docs: update the adapter section of the open-source spec and add a
   CHANGELOG entry.
9. Commit with trailers. Run the pre-PR check on the committed diff, then
   pre-PR finalize with `--commit`. Open the PR with the wrapper (Closes
   #2308, Refs #2321). Then post-PR finalize and push.

## Required Tests And Checks

- `PYTHONPATH=src <venv python> -m pytest tests/cli/test_webmcp_adapter.py tests/api/test_webmcp.py -q`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` to run
  tier-selected checks and reconcile the gate ledger before PR
  creation (receipt behavior is folded into the ledger per ADR-042 Addendum 6;
  there is no separate `gate_receipt` command)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2308"` before PR creation
- `python scripts/scistudio_pr_create.py` for the final PR (do not use
  `gh pr create` directly)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after PR is created
- Sentrux: N/A (MCP not available in this runtime)

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist row evidence (§8.3).
- PR number and commit.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
```
