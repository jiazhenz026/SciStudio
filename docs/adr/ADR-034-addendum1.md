---
adr: 34
addendum: 1
title: "Permission Modes — Manual, Auto, Yolo/Bypass With Per-Provider Auto Flags"
status: Proposed
date_created: 2026-09-14
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [34, 53]
closes_issues: [2379]
tracking_issue: 2379

is_code_implementation: true
governs:
  modules:
    - scistudio.ai.agent.providers_registry
  contracts:
    - scistudio.ai.agent.providers_registry.ProviderDescriptor
    - scistudio.ai.agent.providers_registry.PERMISSION_MODES
    - scistudio.engine.pty_control.PtyTabSpec
  entry_points: []
  files:
    - docs/adr/ADR-034-addendum1.md
    - src/scistudio/ai/agent/providers_registry.py
    - src/scistudio/ai/agent/terminal.py
    - src/scistudio/api/routes/ai_pty/**
    - src/scistudio/api/routes/work_import.py
    - src/scistudio/blocks/ai/ai_block.py
    - src/scistudio/engine/pty_control.py
    - frontend/src/components/AIChat/SetupScreen.parts/PermissionModePicker.tsx
  excludes: []

tests:
  - tests/ai/test_permission_auto_mode.py
  - tests/api/test_ai_pty.py
  - tests/api/test_work_import_session.py
  - tests/blocks/ai/test_ai_block_skeleton.py
agent_editable: true
assisted_by:
  - "Claude:claude-opus-5"

phase: implementation
tags: [adr-034, embedded-agent, permissions, ux]
owner: "@jiazhenz026"
co_authors: ["@claude"]
language_source: en
translations: []
---

# ADR-034 Addendum 1: Permission Modes — Manual, Auto, Yolo/Bypass With Per-Provider Auto Flags

## 1. Decision Summary

A session started from AI Chat, Bring In My Work, or an AI Block now starts in
one of three permission modes — **Manual**, **Auto**, **Yolo/Bypass** — chosen
from one row of three buttons with no explanatory text. Each provider's Auto
flag lives in its registry descriptor. A provider whose CLI has no Auto mode
shows the Auto button disabled, and every launch path refuses `auto` for it.

This supersedes the two-label wording of spec FR-021e (`Manual Approve` /
`Bypass Permission`). FR-021f's guarantee is kept for the values that already
existed: `safe` and `bypass` (frontend `dangerous`) are stored, sent, and
launched exactly as before, and `safe` stays the default.

### 1.1 Problems Addressed

| Problem | Risk | ADR response | Detailed section |
|---|---|---|---|
| Every supported agent CLI now ships an Auto mode that the picker cannot reach | Users choose between approving every step and approving nothing | Add `auto` as a third mode, wired end to end | §2 |
| The picker's two options carried multi-sentence explanations | The setup screen reads as a warning page, and the copy drifts from what each CLI does | Three short labels, no descriptive copy | §3 |
| Auto flags differ per CLI, and not every CLI is guaranteed to have one | A hard-coded flag launches the wrong mode or fails to launch | Auto argv per descriptor; disabled when absent | §2 |

## 2. Decision: A Third Mode, Owned By The Registry

`PermissionMode` is `safe | auto | bypass`. `ProviderDescriptor` gains
`auto_argv` and `auto_argv_absent_reason` (exactly one must be set for an
agent, mirroring `manual_argv`), plus `supports_auto_mode` and
`permission_argv(mode)`, which is the single mode-to-argv mapping the spawn
uses. Flags verified on 2026-09-14:

| Provider | Auto argv | Source |
|---|---|---|
| `claude-code` | `--permission-mode auto` | `claude --help` 2.1.210 |
| `codex` | `--approve-for-me --ask-for-approval on-request` | `codex --help` 0.154.0 |
| `kimi-code` | `--yolo` ("Ask When Needed"; Kimi's `--auto` is Never Ask, already Yolo/Bypass) | `kimi --help` 0.42.0 |
| `qoder`, `qoder-cn` | `--permission-mode auto` | Qoder CLI permissions documentation |

The same verification found that Codex retired `--ask-for-approval untrusted`
in 0.149.0, so Codex Manual failed to launch. Codex Manual is now
`--ask-for-approval on-request --sandbox read-only`.

`auto` is accepted by the PTY WebSocket (a new `permission_mode` query
parameter that wins over the legacy `dangerous` flag), the pre-spawned tab
path, `POST /api/work-import/sessions`, `PtyTabSpec`, and the AI Block
`permission_mode` enum. Each rejects `auto` for a provider without an Auto
mode, the AI Block at config time. `GET /api/ai/status` and
`GET /api/ai/availability` carry `supports_auto_mode` so both pickers can grey
the button out.

## 3. Decision: Three Labels, No Copy

The picker is a segmented row labelled exactly `Manual`, `Auto`, `Yolo/Bypass`
under the `Permission mode` legend. It still renders no CLI flag name. When the
selected provider changes to one without Auto while Auto is selected, the
picker falls back to Manual. The AI Block's enum labels, the user guide, and
core tutorial 3 use the same three names.

## 4. Verification, Consequences, And Alternatives

Tests pin each provider's Auto argv, the exclusivity of the three fragments,
every refusal path, the picker's rendered text and disabled state, and the
request payloads for AI Chat and Bring In My Work.

Consequence: Auto flags must be re-verified when a CLI changes its permission
surface, as `manual_argv` already must. This addendum's `governs` block is
informational until issue #2004 lets audit tooling read addendum surfaces.

Alternatives rejected: keeping two modes (leaves the CLIs' reviewed-autonomy
modes unreachable); one global Auto flag (wrong for four of five CLIs); hiding
Auto for unsupported providers (the owner chose a disabled button).
