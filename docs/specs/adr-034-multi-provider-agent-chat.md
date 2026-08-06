---
spec_id: adr-034-multi-provider-agent-chat
title: "ADR-034 Multi-Provider Agent Chat Implementation Specification"
status: Draft
feature_branch: docs/1992-adr-034-multi-provider-spec
created: 2026-08-06
input: "Owner request: add Kimi Code and Qoder CLI support to AI chat, covering every feature surface including AI Block, with the provider set driven by one registry instead of scattered per-provider branches. Qoder must support both its international and China channel CLIs simultaneously."
owners:
  - "@jiazhenz026"
related_adrs:
  - 34
  - 35
  - 40
related_specs:
  - embedded-coding-agent-spec
scope:
  in:
    - Introduce a single provider registry that owns every per-CLI fact used by agent spawn, discovery, and status.
    - Add `kimi-code`, `qoder`, and `qoder-cn` as first-class PTY chat providers alongside `claude-code` and `codex`.
    - Treat Qoder's international and China channel CLIs as two independently selectable providers that may be installed side by side.
    - Extend provider binary discovery to per-provider well-known install directories that are absent from PATH.
    - Exclude non-chat sidecar binaries such as the Qoder security scanner's pinned CLI copy from provider discovery.
    - Add per-provider MCP injection strategies so the existing provider-agnostic MCP payload reaches every CLI.
    - Replace `AIBlock._build_spawn_argv` with an explicit `provider` field on the worker to engine PTY tab request.
    - Extend `GET /api/ai/status` and the PTY WebSocket provider whitelist to the full registry-derived provider set.
    - Extend the AI Block `provider` config enum to the full agent provider set.
    - Replace the SetupScreen provider radio list with a registry-driven dropdown that lists every supported agent and enables only the installed ones.
    - Add a zero-install guidance state that tells the user to install an agent CLI when none is detected.
    - Reword the permission-mode picker to plain user language with no CLI flag names.
    - Pin the SetupScreen action bar so Launch is reachable at every bottom-panel height without scrolling.
    - Collapse the three duplicated frontend provider union types into one source.
    - Fix the orphaned system-prompt temp file leak on the AI Block spawn path.
    - Fix the invalid `scistudio install --target claude-code` hint emitted by AI Block validate-time errors.
    - Update ADR-034, the embedded coding agent spec contract note, and the affected skill documentation.
  out:
    - Adding a non-CLI provider surface such as an IDE launcher or a hosted API backend.
    - Adding an `ANTHROPIC_BASE_URL` style model-backend axis orthogonal to the CLI provider axis.
    - Changing the PTY transport, WebSocket frame schema, resource cap, or pump architecture.
    - Changing the SciStudio MCP tool surface or SKILL.md content.
    - Changing `scistudio install` target semantics beyond adding registry-derived targets.
    - Bundling, vendoring, or auto-installing any provider CLI with SciStudio.
    - Changing AI Block completion-signal, run-dir, manifest, or output-loading behavior.
    - Redesigning the bottom panel, its resize behavior, its default height, or its existing pin-open toggle.
    - Adding in-app installation, download, or update of any provider CLI.
    - Adding per-provider install instructions to the normal Setup screen flow outside the zero-install state.
governs:
  modules:
    - scistudio.ai.agent.terminal
    - scistudio.api.routes.ai
    - scistudio.api.routes.ai_pty
    - scistudio.blocks.ai.ai_block
    - scistudio.engine.pty_control
  contracts:
    - scistudio.ai.agent.terminal.spawn_claude
    - scistudio.ai.agent.terminal.spawn_codex
    - scistudio.ai.agent.terminal.resolve_windows_executable
    - scistudio.api.routes.ai_pty.engine.open_engine_initiated_tab
    - scistudio.api.routes.ai.provider_status
    - scistudio.engine.pty_control.PtyTabSpec
    - scistudio.blocks.ai.ai_block.AIBlock.config_schema
  entry_points:
    - scistudio.blocks
  files:
    - docs/adr/ADR-034.md
    - docs/specs/adr-034-multi-provider-agent-chat.md
    - docs/specs/embedded-coding-agent-spec.md
    - src/scistudio/ai/agent/terminal.py
    - src/scistudio/api/routes/ai.py
    - src/scistudio/api/routes/ai_pty/__init__.py
    - src/scistudio/api/routes/ai_pty/_state.py
    - src/scistudio/api/routes/ai_pty/engine.py
    - src/scistudio/api/routes/ai_pty/internal_routes.py
    - src/scistudio/blocks/ai/ai_block.py
    - src/scistudio/cli/install.py
    - src/scistudio/engine/pty_control.py
    - src/scistudio/_skills/scistudio/scistudio-build-workflow/SKILL.md
    - frontend/src/components/AIChat/SetupScreen.tsx
    - frontend/src/components/AIChat/SetupScreen.parts/PermissionModePicker.tsx
    - frontend/src/components/AIChat/SetupScreen.parts/ProviderPicker.tsx
    - frontend/src/components/AIChat/SetupScreen.parts/types.ts
    - frontend/src/components/AIChat/hooks/usePtyWebSocket.ts
    - frontend/src/store/types.ts
    - frontend/src/store/terminalTabsSlice.ts
  excludes:
    - build/**
    - desktop/dist/**
    - desktop/resources/backend/**
    - src/scistudio/api/static/**
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - src/scistudio/ai/agent/providers_registry.py
    - frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx
  excludes: []
tests:
  - tests/ai/test_providers_registry.py
  - tests/ai/test_windows_executable_resolution.py
  - tests/api/test_provider_discovery.py
  - tests/api/test_ai_pty.py
  - tests/api/test_ai_pty_engine_spawn.py
  - tests/api/routes/ai_pty/test_engine.py
  - tests/blocks/ai/test_ai_block_skeleton.py
  - tests/engine/test_pty_control.py
  - frontend/src/components/AIChat/__tests__/SetupScreen.test.tsx
  - frontend/src/components/AIChat/__tests__/TerminalTab.test.tsx
acceptance_source: adr
language_source: en
---

# ADR-034 Multi-Provider Agent Chat Implementation Specification

## 1. Change Summary

ADR-034 established that SciStudio's AI chat is a PTY-hosted third-party agent
CLI rendered through xterm.js, and that adding a provider "changes only the
spawned executable plus a few argv differences". The implementation did not hold
that shape. Per-provider knowledge is currently spread across fifteen backend
locations, three duplicated frontend union types, and two independent argv
builders, one of which is dead code that leaks a file on every run.

This spec adds three providers — **Kimi Code** (`kimi`), **Qoder CLI
international** (`qodercli`), and **Qoder CLI China** (`qoderclicn`) — and makes
ADR-034's original claim true by introducing a single **provider registry**.
After this change, every per-CLI fact (binary candidates, well-known install
directories, permission-bypass flag spelling, MCP injection strategy,
system-prompt injection strategy, credential probe) lives in exactly one
descriptor table. Adding a sixth provider becomes a data change plus a discovery
rule, not a sweep across fifteen call sites.

Qoder ships as two channel-specific CLIs that a user may install side by side,
with separate binaries, separate config roots, and separate credentials. They
are modelled as two provider keys (`qoder`, `qoder-cn`) rather than two binary
candidates of one key, because a user with both installed must be able to choose
which account and model catalog a chat tab uses. Their adapter strategies are
byte-for-byte identical, which makes them the clearest demonstration of why the
registry is a descriptor table rather than a branch chain: the pair differs only
in identity fields and shares every strategy field.

The change covers **both** consumers of the provider concept: the user-launched
chat tab (ADR-034) and the engine-initiated AI Block tab (ADR-035). AI Block is
not deferred. Reaching full AI Block coverage requires deleting
`AIBlock._build_spawn_argv`, whose output is already discarded by the receiving
end, which simultaneously resolves two existing defects.

This is a replacement of the per-provider branch pattern, not an additive layer.
The `if provider == "claude-code" / elif provider == "codex"` chains must be
removed rather than extended.

### Verified provider facts

All facts below were observed against the binaries installed on the owner
workstation on 2026-08-06. They are the authoritative input to the registry
table and must be re-verified when a provider CLI major version changes.

**Identity fields** — unique per provider, and the reason `qoder` and `qoder-cn`
cannot collapse into one descriptor:

| Fact | `claude-code` | `codex` | `kimi-code` | `qoder` | `qoder-cn` |
|---|---|---|---|---|---|
| Binary | `claude` | `codex` | `kimi` | `qodercli` | `qoderclicn` |
| Observed version | 2.x | 0.139.0 | 0.33.0 | 1.1.15 | 1.1.15 |
| On PATH by default | yes | yes | **no** | **no** | **no** |
| Well-known install dir | `~/.local/bin` | `~/AppData/Roaming/npm` | `~/.kimi-code/bin` | `~/.qoder/bin/qodercli` | `~/.qoder-cn/bin/qoderclicn` |
| Config root | `~/.claude` | `~/.codex` | `~/.kimi-code` (override: `KIMI_CODE_HOME`) | `~/.qoder` (override: `--config-dir`) | `~/.qoder-cn` (override: `--config-dir`) |
| Credential path | `~/.claude/.credentials.json` | `~/.codex/auth.json` | `~/.kimi-code/credentials/kimi-code.json` | `~/.qoder/.auth` | `~/.qoder-cn/.auth` |
| Auth status command | `claude auth status --json` | `codex login status` | `kimi doctor` | none observed | none observed |

**Adapter strategy fields** — `qoder` and `qoder-cn` are identical on every row:

| Fact | `claude-code` | `codex` | `kimi-code` | `qoder` / `qoder-cn` |
|---|---|---|---|---|
| `--mcp-config` flag | yes | no | **no** | **yes** |
| MCP fallback discovery | `<project>/.mcp.json` | `~/.codex/config.toml`, `<project>/.codex/config.toml` | `<KIMI_CODE_HOME>/mcp.json`, `<project>/.mcp.json`, `<cwd>/.kimi-code/mcp.json` | `<project>/.mcp.json` |
| System-prompt flag | `--append-system-prompt @<file>` | none | none (`--agent-file <path>`) | `--append-system-prompt <text>` (literal, no `@` indirection) |
| Skills discovery | `.claude/skills` | `.agents/skills` | `.claude/skills`, `.codex/skills`, `.agents/skills`, `.kimi-code/skills` | `.agents/skills` |
| Bypass-permission flag | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `--auto` | `--dangerously-skip-permissions` |

Verification note: the `qoder` international CLI was probed directly at version
1.1.15 before the owner workstation switched to the China channel installer;
`~/.qoder` is absent as of the verification date, so its identity paths are
recorded from the earlier direct observation rather than a live install. The
`qoder-cn` row is live-verified.

Three consequences shape the whole design:

1. **None of the new CLIs is on PATH.** `shutil.which` and the current
   `resolve_windows_executable` both fail to find them, because
   `_windows_user_cli_dirs()` only scans `~/.local/bin` and
   `~/AppData/Roaming/npm`. Discovery must become registry-driven.
2. **Skills need no new work.** Kimi Code reads `.claude/skills` and
   `.agents/skills`; both Qoder channels read `.agents/skills`. ADR-040
   provisioning already writes both trees. The owner's position that MCP and
   skill content are provider-agnostic is confirmed by the binaries: only the
   *discovery mechanism* is per-CLI, never the payload.
3. **Discovery must reject sidecar copies.** The Qoder security-scan plugin
   ships its own pinned CLI at `~/.qodersec/bin/qodercli.exe`, observed at
   version 1.1.12 with `{"channel": "global"}`. It is an internal dependency of
   the scanner, not a user-facing chat CLI, and it is stale relative to the real
   install. Discovery must match exact binary names in registered well-known
   directories rather than globbing for `qodercli*.exe` anywhere under the home
   directory, or SciStudio will offer a stale, unauthenticated agent.

### Governance alignment — open item blocking `Planned` status

This spec is `status: Draft`, not `Planned`, for one specific reason that the
owner must resolve before implementation starts.

The `doc-drift.missing-adr-governance` rule requires that every ADR listed in a
`Planned` or `Implemented` spec's `related_adrs` covers every surface the spec
governs, as a strict conjunction across all listed ADRs. This spec's surface is
wider than what ADR-034 currently governs. ADR-034 governs
`scistudio.api.routes.ai_pty`, `scistudio.engine.pty_control`,
`src/scistudio/ai/agent/terminal.py`, and `frontend/src/components/AIChat/**`.
It does not govern `src/scistudio/api/routes/ai.py`,
`src/scistudio/blocks/ai/ai_block.py`, `src/scistudio/cli/install.py`,
`frontend/src/store/**`, or `frontend/src/components/BottomPanel.tsx`, all of
which this change must touch. ADR-035 and ADR-040 cover parts of that remainder,
but the rule is a conjunction, so listing them does not close the gap.

This is a real architectural finding rather than a paperwork obstacle: the
provider registry widens what the embedded-agent decision governs, and ADR-034
is an Accepted document in `phase: legacy` marked `agent_editable: false`. The
resolution is an owner decision between two options:

1. Expand ADR-034's `governs` to cover the registry, status endpoint, AI Block
   integration, and the frontend store surfaces this spec touches.
2. Author an ADR-034 addendum that records the multi-provider registry decision
   and governs the new surfaces, leaving the original ADR untouched.

Until one of those lands, this spec stays `Draft` and declares the two
not-yet-existing files under `planned_governs`. Moving it to `Planned` without
the ADR alignment would either fail the audit or require under-declaring the
spec's real surface, and neither is acceptable.

## 2. User Scenarios & Testing

### User Story 1 - Launch A Chat With Any Installed Agent (Priority: P1)

As a SciStudio user, I can open an AI chat tab backed by Claude Code, Codex,
Kimi Code, Qoder CLI international, or Qoder CLI China, and the agent starts
with SciStudio's MCP tools and skills available regardless of which CLI I
picked.

Why this priority: this is the feature the owner requested; every other story
supports it.

Independent Test: with each provider selected in turn, launch a chat tab and
assert the PTY spawns the correct binary with the provider's own MCP injection
applied, and that the agent can call a SciStudio MCP tool.

Acceptance Scenarios:

- Given Kimi Code is installed at `~/.kimi-code/bin/kimi.exe` and is not on
  PATH, when the user opens the Setup screen, then Kimi Code appears as
  available with its version string.
- Given the user selects either Qoder channel and launches, when the PTY spawns,
  then argv contains `--mcp-config <project>/.scistudio/mcp.json`.
- Given the user selects Kimi Code and launches, when the PTY spawns, then
  `<project>/.kimi-code/mcp.json` contains the SciStudio MCP entry and argv
  contains no `--mcp-config` flag.
- Given both Qoder channels are installed, when the Setup screen renders, then
  both appear as separately selectable entries with distinct labels, and
  launching one spawns only that channel's binary.
- Given only one Qoder channel is installed, when the Setup screen renders, then
  the other channel is shown as not installed rather than silently resolving to
  the installed channel's binary.
- Given the Qoder security-scan sidecar CLI is present at `~/.qodersec/bin/`,
  when provider discovery runs, then neither Qoder provider resolves to it.
- Given any provider is selected with Bypass permission mode, when the PTY
  spawns, then that provider's own bypass flag spelling is used and no other
  provider's spelling appears in argv.

### User Story 2 - Run An AI Block With Any Installed Agent (Priority: P1)

As a workflow author, I can set an AI Block's provider to any installed agent
CLI and the engine-initiated PTY tab spawns that agent identically to a
hand-launched chat tab.

Why this priority: the owner rejected deferring AI Block; provider support that
covers only the chat surface is incomplete.

Independent Test: for each provider, run an AI Block and assert the engine
spawns via the same registry-driven factory the chat path uses, with the
provider carried explicitly rather than inferred from argv.

Acceptance Scenarios:

- Given an AI Block configured with `provider: kimi-code`, when the block runs,
  then the engine receives `provider="kimi-code"` on the tab request and spawns
  the Kimi factory.
- Given an AI Block run completes, when the run directory is inspected, then
  `<project>/.scistudio/.tmp/` contains no orphaned system-prompt file.
- Given a provider binary is absent, when `validate_config` runs, then the error
  names the provider and any install command it suggests is a command the
  `scistudio install` CLI actually accepts.
- Given an AI Block spawns a tab, when the frontend receives `block_pty_opened`,
  then the tab records the provider the engine actually spawned rather than a
  hardcoded `claude-code`.

### User Story 3 - Pick A Provider Without A Growing Radio List (Priority: P2)

As a SciStudio user, I choose the provider from a compact dropdown that shows
availability and login state, instead of a radio list that grows one row per
provider.

Why this priority: the owner explicitly requested a dropdown; five providers
plus the user terminal make the radio list the dominant element of the Setup
screen.

Independent Test: render SetupScreen with a stubbed status payload and assert a
single select control lists every agent provider with correct disabled state.

Acceptance Scenarios:

- Given five agent providers, when the Setup screen renders, then one select
  control lists them and no per-provider radio input exists.
- Given a provider reports `available: false`, when the dropdown renders, then
  the option still appears so the user learns the agent is supported, but it is
  disabled and annotated `(not installed)`.
- Given a provider reports `available: true, logged_in: false`, when the
  dropdown renders, then the option is selectable and annotated
  `(not logged in)`.
- Given a mix of installed and not-installed providers, when the dropdown opens,
  then all installed providers appear above all not-installed ones.
- Given the Setup screen renders, when the user has not chosen yet, then the
  select shows a non-selectable `Choose provider…` placeholder and Launch is
  disabled.
- Given the user picks a provider, when the selection changes, then the
  placeholder is no longer selectable and Launch becomes enabled once a
  permission mode is also chosen.

### User Story 4 - Understand What To Install When Nothing Is Installed (Priority: P1)

As a first-time SciStudio user with no agent CLI on my machine, I am told
plainly that I need to install one and which agents are supported, instead of
facing a dropdown where every option is disabled.

Why this priority: this is the first-run dead end. A user in this state cannot
use AI chat at all and the current UI gives them no path forward.

Independent Test: render SetupScreen with a status payload where every provider
reports `available: false` and assert a guidance panel replaces the picker and
the Launch control communicates why it cannot proceed.

Acceptance Scenarios:

- Given no provider is installed, when the Setup screen renders, then a guidance
  notice states that an agent CLI must be installed and names every supported
  agent.
- Given no provider is installed, when the Setup screen renders, then the
  provider dropdown and permission picker are not presented as the primary
  affordance, so the user is not left clicking disabled controls.
- Given no provider is installed, when the user reads the notice, then it
  identifies each supported agent by its user-facing product name rather than
  its internal provider key.
- Given the status endpoint is unreachable, when the Setup screen renders, then
  the existing status-error banner is shown instead of the zero-install notice,
  because unknown availability is not the same as confirmed absence.
- Given the user installs a CLI and reopens the Setup screen, when status is
  refetched, then the normal picker replaces the guidance notice without an app
  restart.

### User Story 5 - Read The Permission Choice Without Knowing CLI Flags (Priority: P2)

As a SciStudio user, I choose between approving tool calls myself and letting
the agent run unattended, described in plain language, without reading CLI flag
names I did not type.

Why this priority: the owner reports the current wording is noisy. The flag
names are implementation detail that the registry now owns per provider, and
they are no longer even accurate across five CLIs.

Independent Test: render the permission picker and assert the two visible labels
and that no CLI flag string appears in the rendered output.

Acceptance Scenarios:

- Given the permission picker renders, when the user reads it, then the two
  options are labelled `Manual Approve` and `Bypass Permission`.
- Given the permission picker renders, when the rendered text is inspected, then
  it contains no `--` flag name.
- Given the permission picker renders, when the user reads the Bypass option,
  then a short plain-language caution remains, without flag names.
- Given a tab is launched, when the stored permission value is inspected, then
  it is unchanged from the existing `safe` / `dangerous` frontend values, so
  this is a presentation change only.

### User Story 6 - Reach Launch At Any Panel Height (Priority: P1)

As a SciStudio user, I can always see and click Launch regardless of how tall
the bottom panel is, without discovering that the panel scrolls.

Why this priority: the owner reports that at the default bottom-panel height the
Launch button is below the fold. A user who does not think to scroll can never
start a chat, which makes the whole feature unreachable.

Independent Test: drive a real browser at several bottom-panel heights,
including the smallest the panel allows, and assert the Launch control is within
the visible viewport of the panel without scrolling.

Acceptance Scenarios:

- Given the bottom panel is at its default height, when the Setup screen
  renders, then Launch and Cancel are visible without scrolling.
- Given the bottom panel is dragged to its minimum height, when the Setup screen
  renders, then Launch remains visible and clickable.
- Given the setup body has more content than fits, when the user scrolls the
  body, then the action bar stays fixed and does not scroll away.
- Given the action bar overlays scrolled content, when content passes behind it,
  then the action bar is fully opaque so the buttons stay legible.

### User Story 7 - Add A Sixth Provider Cheaply (Priority: P2)

As a SciStudio maintainer, I add a new agent CLI by adding one registry entry
and one discovery rule, without editing spawn, status, WebSocket validation, AI
Block, or frontend type files.

Why this priority: the current cost of adding a provider is the defect this
spec exists to remove; without it the same sweep recurs on the next CLI.

Independent Test: add a fixture provider descriptor in a test and assert it
appears in `_VALID_PROVIDERS`, `/api/ai/status`, the AI Block config enum, and
the frontend provider list without any other source edit.

Acceptance Scenarios:

- Given a new descriptor is appended to the registry, when the backend starts,
  then the WebSocket provider whitelist and the status endpoint both include it.
- Given a new descriptor is appended, when `AIBlock.config_schema` is read,
  then its `provider` enum includes the new key.
- Given the registry is the only edited file, when the full test suite runs,
  then no test asserts a hardcoded two-provider set.
- Given a provider ships channel variants, when descriptors are added for each
  channel, then no strategy logic is duplicated because the variants differ only
  in identity fields.

### Edge Cases

- A provider binary exists but `--version` hangs. The status probe must time out
  at 2 s and report `available: false` without blocking the endpoint.
- A provider is installed only in its well-known directory and PATH lacks that
  directory. Discovery must still find it, and the chat path and AI Block path
  must agree on the result.
- Both Qoder channels are installed at once. Each must resolve to its own
  binary, read its own config root, and report its own login state; neither may
  fall back to the other when its own binary is missing.
- Only one Qoder channel is installed. The other must report `available: false`
  rather than resolving to the installed sibling.
- A stale sidecar copy of a provider binary exists outside the registered
  well-known directories. Discovery must not select it.
- A saved workflow or persisted chat tab names a Qoder channel that is no longer
  installed. Status must report it unavailable without breaking the dropdown or
  the AI Block config load.
- Kimi Code project-scope MCP loads only in a trusted workspace. When the
  project is untrusted, the agent starts without SciStudio tools; the spec must
  not claim tool availability it cannot guarantee.
- `KIMI_CODE_HOME` is set to a non-default path. Kimi's own documentation string
  instructs callers to never assume `~/.kimi-code`; discovery and MCP writes
  must honour the environment variable.
- Qoder's `--append-system-prompt` takes literal text with no `@<file>`
  indirection, so a long composed prompt would land on the command line.
- A workflow saved before this change carries `provider: claude-code`. Enum
  widening is backward compatible and such workflows must load unchanged.
- Two providers are launched concurrently. The existing 16-PTY cap and per-tab
  registry are provider-agnostic and must remain so.
- Every provider is installed but none is logged in. This is not the
  zero-install state; the picker must render normally so the user can launch and
  complete the CLI's own login flow inside the PTY.
- The status fetch is still in flight. The zero-install notice must not flash
  before availability is known.
- The bottom panel is at its collapsed height where even a pinned action bar
  cannot fit. The action bar must degrade predictably rather than being clipped
  with no way to reach it.
- A persisted panel height from an earlier session is smaller than the current
  default. The pinned action bar must hold at that height too, because the
  panel size is restored from the store rather than reset.

## 3. Requirements

### Functional Requirements

- FR-001: A provider registry module MUST be the single source of truth for
  every per-CLI fact consumed by spawn, discovery, status, and validation.
- FR-002: Each registry descriptor MUST declare provider key, display label,
  binary candidate names, well-known install directories, config-root resolution
  including environment-variable overrides, credential probe, optional auth
  status command, MCP injection strategy, system-prompt injection strategy, and
  bypass-permission argv.
- FR-003: The registry MUST distinguish agent providers from the non-agent
  `user-terminal` pseudo-provider so status and the Setup dropdown list only
  agent providers.
- FR-004: `resolve_windows_executable` MUST accept per-provider well-known
  directories from the registry instead of a module-level constant list.
- FR-005: Provider binary discovery MUST return the same result for the chat
  path and the AI Block path, and both MUST use the registry resolver rather
  than bare `shutil.which`.
- FR-006: `_VALID_PROVIDERS` and `_PROVIDER_SPAWNERS` MUST be derived from the
  registry rather than hand-maintained literals.
- FR-007: A single generic spawn function MUST build argv from a descriptor;
  per-provider spawn functions MUST NOT contain provider branching.
- FR-008: `GET /api/ai/status` MUST return one entry per agent provider derived
  from the registry, preserving the existing
  `{name, available, version, logged_in}` entry shape.
- FR-009: The provider credential probe MUST be descriptor-driven: a credential
  file path check followed by an optional provider-owned auth status command.
- FR-010: `PtyTabSpec` MUST carry an explicit `provider` field, and
  `open_engine_initiated_tab` MUST use it instead of inferring the provider from
  `spawn_argv`.
- FR-011: `_provider_from_argv` MUST be deleted; no code path may infer a
  provider from an argv basename.
- FR-012: `AIBlock._build_spawn_argv` MUST be deleted; the AI Block worker MUST
  NOT compose provider argv, write system-prompt files, or write MCP config.
- FR-013: The AI Block spawn path MUST NOT create files that no component
  deletes.
- FR-014: `AIBlock.validate_config` MUST reject unknown providers against the
  registry and MUST emit an install hint that the `scistudio install` CLI
  accepts, or omit the hint when no valid target exists.
- FR-015: `AIBlock.config_schema` `provider` enum MUST be derived from the
  registry's agent provider keys with `claude-code` remaining the default.
- FR-016: For providers with an explicit MCP config flag, the spawn argv MUST
  pass `<project>/.scistudio/mcp.json`.
- FR-017: For providers without an MCP config flag, spawn MUST write the
  SciStudio MCP entry into that provider's own project-scope discovery location
  before the process starts.
- FR-018: MCP entry content MUST remain provider-agnostic; only the write
  location and injection mechanism may differ per provider.
- FR-019: Skill provisioning MUST remain unchanged; the spec MUST NOT add a new
  skills tree for either new provider.
- FR-020: The frontend MUST declare the provider union type exactly once and
  every consumer MUST import it.
- FR-021: The Setup screen MUST render provider choice as a single select
  control driven by the status payload.
- FR-021a: The select MUST list every supported agent provider, including those
  that are not installed, so the supported set is discoverable; unavailable
  options MUST be disabled and annotated.
- FR-021b: The select MUST order available providers before unavailable ones, so
  the user never scans past disabled entries to reach a selectable one. Order
  within each group MUST be the registry order so it is stable across renders.
- FR-021i: The select MUST NOT preselect a provider. Its initial value MUST be a
  non-selectable `Choose provider…` placeholder, and Launch MUST stay disabled
  until the user picks one.
- FR-021c: When no agent provider reports `available: true`, the Setup screen
  MUST replace the picker with a guidance notice that states an agent CLI is
  required and names every supported agent by its product name.
- FR-021d: The zero-install notice MUST NOT render while provider status is
  unknown, whether in flight or failed; those states keep their existing
  loading and error treatments.
- FR-021e: The permission-mode options MUST be labelled `Manual Approve` and
  `Bypass Permission`, and the picker MUST NOT display any CLI flag name.
- FR-021f: The permission-mode change MUST be presentational; the stored values
  and the launch payload MUST be unchanged.
- FR-021g: The Setup screen action bar containing Cancel and Launch MUST remain
  visible at every bottom-panel height the panel permits, without requiring the
  user to scroll any ancestor container.
- FR-021h: The action bar MUST render on an opaque background when content can
  pass behind it.
- FR-022: The engine-initiated terminal tab MUST record the provider reported by
  the engine rather than a hardcoded value.
- FR-023: The WebSocket query contract MUST accept every registry provider key,
  and the rejection message MUST enumerate the accepted set.
- FR-024: Documentation MUST record the verified per-provider adapter matrix and
  the date it was verified against installed CLI versions.
- FR-025: A provider that ships channel-specific CLIs MUST be modelled as one
  descriptor per channel with distinct provider keys, so both channels can be
  installed and selected independently.
- FR-026: Channel variants MUST NOT be modelled as alternative binary candidates
  of a single descriptor, and a missing channel binary MUST NOT resolve to a
  sibling channel's binary.
- FR-027: Binary discovery MUST match exact binary names within registered
  well-known directories and MUST NOT select provider-named binaries found
  elsewhere, so vendor sidecar copies are never offered as chat providers.

### Key Entities

| Entity | Description | Required attributes |
|---|---|---|
| `ProviderKind` | Distinguishes agent CLIs from the shell pseudo-provider | `agent`, `terminal` |
| `McpInjection` | How a provider learns about the SciStudio MCP server | strategy tag, flag name, project-scope file path template |
| `SystemPromptInjection` | How a provider receives the composed system prompt | strategy tag, flag name, file-indirection support, ambient-only marker |
| `CredentialProbe` | How login state is detected | credential file path template, optional auth status argv |
| `ProviderDescriptor` | One agent CLI channel's complete adapter definition | key, label, kind, binary candidates, well-known dirs, config-root env override, MCP injection, system-prompt injection, credential probe, bypass argv |
| `ProviderRegistry` | Ordered descriptor collection | lookup by key, agent-only view, key tuple for whitelists and enums |

## 4. Implementation Plan

### 4.1 Technical Approach

Create `src/scistudio/ai/agent/providers_registry.py` holding the descriptor
dataclasses and the five agent descriptors plus the `user-terminal` entry. The
module must not import from `scistudio.api` or `scistudio.blocks` so both the
API layer and the block layer can depend on it without a cycle, mirroring the
constraint that makes `ai_pty/_state.py` a safe leaf.

The `qoder` and `qoder-cn` descriptors share every strategy field and differ
only in key, label, binary candidates, well-known directory, config root, and
credential path. They may be constructed through a small factory that takes the
identity fields and fills the shared strategy fields, but the registry must
still hold two independent descriptor instances so each resolves, probes, and
spawns on its own. Discovery matches an exact binary name inside a registered
well-known directory; it never searches the home directory broadly, which is
what keeps the security-scan sidecar copy out of the provider list.

`terminal.py` keeps `PtyProcess` unchanged and replaces `spawn_claude` /
`spawn_codex` with a single descriptor-driven `spawn_agent(descriptor, ...)`.
The existing names may remain as thin registry lookups only if tests depend on
them; otherwise they are removed. `resolve_windows_executable` gains an explicit
well-known-directory parameter sourced from the descriptor, replacing
`_windows_user_cli_dirs()`.

MCP injection becomes a strategy dispatch with three observed shapes: an
explicit `--mcp-config` flag (`claude-code`, `qoder`, `qoder-cn`), Codex `-c`
overrides (`codex`), and a project-scope file write (`kimi-code`, writing
`<project>/.kimi-code/mcp.json` before spawn). The payload in every case is the
existing `_mcp_entry_payload(project_dir)`. System-prompt injection has two
observed shapes: a flag that accepts file indirection (`claude-code`), and
ambient discovery through the already-provisioned skills trees (`codex`,
`kimi-code`, `qoder`, `qoder-cn`). The Qoder channels' literal-text
`--append-system-prompt` is deliberately not used, because the composed prompt
is unbounded and would land on the command line; both channels receive the
prompt through `.agents/skills` like Codex does. This decision is recorded as an
assumption to revisit if Qoder gains `@<file>` support.

On the AI Block side, `_build_spawn_argv` is deleted. `PtyTabSpec` gains
`provider: str` and keeps `spawn_argv` only if a consumer still needs it; the
investigation found no such consumer, so the field should be removed in the same
change. `open_engine_initiated_tab` takes `provider` directly. This removes the
worker's duplicated prompt-file write, which is the source of the orphaned-file
leak, and removes the last place where a provider is guessed from a string.

The frontend consolidates on `store/types.ts` as the single `TerminalProvider`
source; `SetupScreen.parts/types.ts` and the inline union in
`usePtyWebSocket.ts` re-export or import it. `ProviderPicker` becomes a `select`
driven by the `/api/ai/status` payload, with the `user-terminal` entry excluded
because it is launched through a separate affordance. Provider display names
come from a frontend label map keyed by provider key; the backend status payload
is not widened to carry labels, because its entry shape is a locked contract and
the label is presentation.

The zero-install state is a distinct render branch, not a disabled-everything
picker. `SetupScreen` already distinguishes loading, error, and loaded status;
the notice renders only in the loaded-and-all-unavailable case, which keeps
FR-021d satisfied without new state. The notice names the supported agents and
states that one must be installed. It deliberately does not carry per-provider
install commands: the owner's position is that users of these CLIs know how to
install them, and the gap being closed here is the first-run dead end, not
per-provider onboarding.

The permission picker change is text only. The `safe` / `dangerous` frontend
values and the `safe` / `bypass` backend values are untouched, so no contract
moves. For consistency the AI Block config schema's `ui_enum_labels` is updated
to the same two phrases, since it is the same choice presented on the canvas.

The pinned action bar is the one change whose root cause was located by
comparison rather than by reading `SetupScreen` alone. `SetupScreen` already
implements the textbook pinned-footer layout — root
`flex h-full min-h-0 flex-col overflow-hidden`, body
`min-h-0 flex-1 overflow-y-auto`, actions `shrink-0` — and a test in
`SetupScreen.test.tsx` asserts exactly that structure and passes, yet the button
is below the fold in the real app.

The working precedent is `Lineage/RunDetail.tsx`, the run-history detail pane.
It has the same shape — root `flex h-full flex-col`, body
`min-h-0 flex-1 overflow-y-auto`, bottom `footer` with a `border-t` — and its
Restore / Export methods bar stays pinned. Notably `RunDetail` is *less*
defensive than `SetupScreen`: its root has neither `min-h-0` nor
`overflow-hidden`, and its footer has no `shrink-0`. A weaker implementation
working while a stronger one fails localises the defect outside both components.

The difference is the host chain. `BottomPanel` renders `LineageTab` directly
into its content wrapper, so `RunDetail` sits two levels below a flex item with
a definite height. The chat surface inserts two additional `h-full` block
wrappers — one in `BottomPanel` to CSS-hide the inactive surface, one in
`TerminalTabs` to CSS-hide inactive tabs — both of which exist because
`TerminalTabs` must stay mounted so PTY subprocesses survive a tab switch. The
result is a percentage-height chain threaded through several non-flex block
wrappers, which is where a definite height is most easily lost; once it is, the
`BottomPanel` wrapper's `overflow-y-auto` scrolls the entire surface including
the footer.

The implementation therefore converts those two wrappers from percentage-height
blocks into flex containers that pass a definite height down
(`flex min-h-0 flex-1 flex-col` on the visible wrapper), preserving the
CSS-hiding behavior that keeps PTYs alive, and additionally makes the action bar
`sticky bottom-0` with an opaque background so it survives if a future ancestor
reintroduces a scroll context. Keeping both is deliberate: the structural repair
is the real fix, and the sticky rule is the guard that stops this from silently
regressing a fourth time. The opaque background contradicts the existing
assertion that the action bar has no `bg-white`; that assertion is updated, and
FR-021h records why an opaque background is now required.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/ai/agent/providers_registry.py` | create | Descriptor dataclasses and the provider table |
| `src/scistudio/ai/agent/terminal.py` | modify | Registry-driven `spawn_agent`; parameterised Windows resolver; remove per-provider factories |
| `src/scistudio/api/routes/ai_pty/_state.py` | modify | Derive `_VALID_PROVIDERS` and `_PROVIDER_SPAWNERS` from the registry |
| `src/scistudio/api/routes/ai_pty/engine.py` | modify | Accept explicit `provider`; delete `_provider_from_argv` |
| `src/scistudio/api/routes/ai_pty/internal_routes.py` | modify | Read `provider` from the request spec |
| `src/scistudio/api/routes/ai_pty/__init__.py` | modify | Update the WS contract docstring provider list |
| `src/scistudio/api/routes/ai.py` | modify | Registry-driven status list and credential probes |
| `src/scistudio/engine/pty_control.py` | modify | Add `provider` to `PtyTabSpec`; drop `spawn_argv` |
| `src/scistudio/blocks/ai/ai_block.py` | modify | Delete `_build_spawn_argv`, `_BYPASS_FLAG`, `_discover_provider`; registry-derived enum and validation |
| `src/scistudio/cli/install.py` | modify | Accept registry-derived targets; keep existing targets working |
| `src/scistudio/_skills/scistudio/scistudio-build-workflow/SKILL.md` | modify | Update the documented AI Block provider enum |
| `frontend/src/store/types.ts` | modify | Single `TerminalProvider` union |
| `frontend/src/components/AIChat/SetupScreen.parts/types.ts` | modify | Import the shared union instead of redeclaring |
| `frontend/src/components/AIChat/hooks/usePtyWebSocket.ts` | modify | Import the shared union instead of an inline literal |
| `frontend/src/components/AIChat/SetupScreen.parts/ProviderPicker.tsx` | modify | Replace radio list with a status-driven select; label map; available-first ordering; `Choose provider…` placeholder |
| `frontend/src/components/AIChat/SetupScreen.parts/PermissionModePicker.tsx` | modify | Relabel to Manual Approve / Bypass Permission; strip CLI flag names |
| `frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx` | create | Zero-install guidance panel naming every supported agent |
| `frontend/src/components/AIChat/SetupScreen.tsx` | modify | Pass the status array instead of named per-provider props; branch to the zero-install notice; sticky opaque action bar |
| `frontend/src/components/BottomPanel.tsx` | modify | Convert the surface-hiding wrapper from a percentage-height block to a flex container that passes a definite height down |
| `frontend/src/components/AIChat/TerminalTabs.tsx` | modify | Same conversion for the per-tab hiding wrapper, preserving CSS-hiding so PTYs stay mounted |
| `frontend/src/store/terminalTabsSlice.ts` | modify | Record engine-reported provider on engine-initiated tabs |
| `frontend/src/hooks/useWebSocket.parts/handleBlockPty.ts` | modify | Carry `provider` from the `block_pty_opened` payload |
| `tests/ai/test_providers_registry.py` | create | Descriptor completeness and registry-derivation tests |
| `tests/api/test_provider_discovery.py` | modify | Replace the exact two-provider set assertion |
| `tests/api/test_ai_pty_engine_spawn.py` | modify | Replace the argv-sniffing test with explicit-provider tests |
| `tests/blocks/ai/test_ai_block_skeleton.py` | modify | Cover registry-derived enum and no-temp-file-leak |
| `docs/adr/ADR-034.md` | modify | Addendum recording the provider registry and adapter matrix |
| `docs/specs/embedded-coding-agent-spec.md` | modify | Update the locked-contract note's provider set |

### 4.3 Implementation Sequence

| Task | Depends on | Work | Verification |
|---|---|---|---|
| T-001 | none | Add descriptor dataclasses and the five agent descriptors plus `user-terminal` | Registry unit tests; every descriptor has a complete adapter definition; both Qoder channels present as distinct keys |
| T-002 | T-001 | Parameterise `resolve_windows_executable` with descriptor well-known dirs; exact-name matching only | Resolution tests locate `kimi.exe`, `qodercli.exe`, and `qoderclicn.exe` off-PATH; sidecar copy is rejected; one missing channel does not resolve to the other |
| T-003 | T-001, T-002 | Replace spawn factories with descriptor-driven `spawn_agent` | Argv snapshot tests per provider; no cross-provider flag leakage |
| T-004 | T-003 | Implement the three MCP injection strategies | Kimi project MCP file written before spawn; flag providers pass the SciStudio path |
| T-005 | T-001 | Derive `_VALID_PROVIDERS` / `_PROVIDER_SPAWNERS` and the status endpoint from the registry | WS rejection message enumerates five providers; status returns five entries |
| T-006 | T-005 | Descriptor-driven credential probes | Per-provider logged-in tests using fake HOME fixtures |
| T-007 | T-001 | Add `provider` to `PtyTabSpec`; accept it in the internal route and `open_engine_initiated_tab`; delete `_provider_from_argv` | Engine spawn tests assert provider passthrough, not argv inference |
| T-008 | T-007 | Delete `_build_spawn_argv`, `_BYPASS_FLAG`, `_discover_provider`; wire AI Block to the registry | AI Block run leaves no orphaned temp file; validate hint is an accepted CLI command |
| T-009 | T-005, T-008 | Registry-derived AI Block `provider` enum | Existing `claude-code` workflows load unchanged; enum lists five providers |
| T-010 | T-001 | Consolidate the frontend provider union to one source | Type check passes with no duplicate literal unions |
| T-011 | T-010, T-005 | Replace the provider radio list with a status-driven select: label map, available-first ordering, `Choose provider…` placeholder | SetupScreen tests assert one select, disabled/annotation states, group ordering, and that Launch stays disabled until a provider is chosen |
| T-011a | T-011 | Add the zero-install guidance notice and its render branch | Tests for all-unavailable, in-flight, and status-error render paths |
| T-011b | none | Relabel the permission picker and strip CLI flag names; align AI Block `ui_enum_labels` | Rendered text contains no `--` flag; stored values unchanged |
| T-011c | none | Convert the two CSS-hiding wrappers to definite-height flex containers and pin the action bar with `sticky bottom-0` plus opaque background | Real-browser check at default, minimum, and restored-persisted panel heights; PTY survives a tab switch and a surface switch |
| T-012 | T-007, T-010 | Carry engine-reported provider onto engine-initiated tabs | Block PTY handler tests assert the provider is not hardcoded |
| T-013 | T-005 | Extend `scistudio install` targets from the registry | CLI accepts existing and new targets; unknown target still errors |
| T-014 | T-001 to T-013 | Update ADR-034 addendum, the embedded-agent spec note, and SKILL.md | Docs checks pass; adapter matrix records the verification date |

### 4.4 Verification Plan

- Add registry unit tests asserting every agent descriptor declares a complete
  adapter definition, so an incomplete future provider fails at test time rather
  than at spawn time.
- Add argv snapshot tests per provider asserting no provider's flag spelling
  appears in another provider's argv.
- Add an off-PATH discovery test using a fake home containing `.kimi-code/bin/`,
  `.qoder/bin/qodercli/`, and `.qoder-cn/bin/qoderclicn/` layouts, proving
  FR-004 and FR-005 without depending on the developer's installed CLIs.
- Add a channel-isolation test: a fake home with only one Qoder channel present
  must report the other unavailable and must not resolve it to the installed
  sibling, proving FR-026.
- Add a sidecar-rejection test: a fake home containing `.qodersec/bin/
  qodercli.exe` and no real Qoder install must report both Qoder channels
  unavailable, proving FR-027.
- Add an AI Block temp-file regression test asserting
  `<project>/.scistudio/.tmp/` contains no files attributable to the worker
  after a run.
- Add a validate-time test asserting the install hint string is accepted by the
  `scistudio install` target parser, closing the loop that currently emits an
  invalid command.
- Update `tests/api/test_provider_discovery.py` to assert the status set equals
  the registry's agent keys rather than a frozen literal set.
- Replace `test_open_engine_tab_picks_codex_provider_from_argv` with a test
  asserting the engine uses the explicitly supplied provider and ignores argv.
- Run frontend tests for SetupScreen, TerminalTab, and TerminalTabs after the
  dropdown change.
- Add SetupScreen tests for the three status branches: in-flight, error, and
  loaded-with-none-available, asserting the zero-install notice appears only in
  the third.
- Add a permission-picker test asserting the rendered text contains no `--`
  substring, so a future edit cannot reintroduce flag names.
- **Verify the pinned action bar in a real browser, not in jsdom.** The existing
  test `keeps Cancel and Launch outside the scrollable setup body` asserts the
  class strings `overflow-hidden`, `overflow-y-auto`, and `shrink-0` and passes
  today, while the button is demonstrably below the fold in the running app.
  jsdom performs no layout, so every assertion of this kind is structural only
  and gives false confidence. The acceptance evidence for User Story 6 must be a
  browser check at the default panel height, the minimum panel height, and a
  restored persisted height, confirming the Launch control is inside the visible
  panel viewport. Keep the structural test as a regression guard, but do not
  treat it as proof.
- Perform a manual smoke launch of each of the five providers against a scratch
  project, confirming the agent can call one SciStudio MCP tool. This is the
  only check that validates the MCP injection strategies end to end; unit tests
  cannot substitute because they mock the spawn. The two Qoder channels must
  both be launched even though their strategies are identical, because their
  credentials and model catalogs are not.
- Run gate-selected repository checks through `gate_record check`.

### 4.5 Risks And Rollback

- **Kimi workspace trust gates project MCP.** Kimi Code loads project-scope MCP
  servers only in trusted folders. A user whose project is untrusted will see an
  agent without SciStudio tools and no obvious cause. Mitigation: detect the
  trust state where observable and surface an actionable message; document the
  behavior. This risk cannot be removed from SciStudio's side.
- **Provider CLIs move fast.** Every fact in §1 is version-pinned to the
  binaries observed on 2026-08-06. A provider release can rename a flag or a
  config path. Mitigation: keep all such facts in one descriptor table, record
  the verification date, and add the manual five-provider smoke launch to the
  release checklist rather than trusting mocked tests.
- **Qoder channel install paths are inferred from two observed installs.** The
  `~/.qoder` / `~/.qoder-cn` split and the `qodercli` / `qoderclicn` binary
  names were observed on one workstation. A different installer build could
  place the China channel elsewhere. Mitigation: the descriptor accepts a list
  of well-known directories, so an additional path is a data change; the
  channel-isolation test guards against a wrong path silently resolving to the
  other channel.
- **Deleting `_build_spawn_argv` touches the AI Block run path.** Although its
  output is discarded downstream, it is currently executed on every run and its
  removal changes when the MCP config file is written. Mitigation: sequence
  T-007 before T-008 so the explicit-provider path is proven before the argv
  builder is removed, and keep AI Block run tests green at each step.
- **Qoder's system prompt arrives only through skills.** If ambient skill
  discovery proves insufficient in the smoke launch, the fallback is literal
  `--append-system-prompt`, which risks command-line length limits on Windows.
  Mitigation: measure the composed prompt length during the smoke launch before
  committing to either mechanism.
- **Touching the CSS-hiding wrappers risks unmounting live PTYs.** Those
  wrappers exist so `TerminalTabs` stays mounted across tab and surface
  switches; unmounting fires the WS cleanup hook and kills the agent
  subprocess, losing the conversation. Mitigation: the change must alter only
  layout classes, never the mount structure or the `hidden` toggle, and the
  browser check must include switching surfaces and tabs with a live agent
  running.
- **The action-bar root cause is localised but not yet reproduced by the
  implementer.** The `RunDetail` comparison isolates the defect to the chat
  surface's extra wrappers, but the exact failing link was not confirmed at a
  breakpoint. Mitigation: the fix is deliberately belt-and-braces — convert the
  wrappers *and* pin with `sticky bottom-0` — so it holds whichever link is at
  fault. The browser check, not the unit test, is the acceptance gate.
- **Changing `BottomPanel`'s content wrapper affects every bottom tab.** Config,
  Logs, Plots, Lineage, and Git all render inside the same wrapper. Mitigation:
  scope the change to restoring a definite height rather than removing the
  scroll affordance, and visually check each tab at default and minimum panel
  heights before merge. `Lineage` is the reference that currently works, so any
  regression there is the clearest signal the change went too far.
- **Rollback**: the registry is additive until T-005 switches the whitelists
  over. Reverting the frontend dropdown and the two new descriptors restores the
  previous two-provider behavior without touching the PTY transport. The three
  GUI changes are independent of the registry work and can be reverted
  individually.

## 5. Success Criteria

### Measurable Outcomes

- All five agent providers launch a chat tab and reach a working SciStudio MCP
  tool call in the manual smoke launch.
- All five agent providers are selectable as an AI Block provider and complete a
  block run.
- Kimi Code and both Qoder channels are discovered when installed only in their
  well-known directories and absent from PATH.
- Both Qoder channels are independently selectable when both are installed, and
  each reports unavailable when only the other is installed.
- The Qoder security-scan sidecar CLI is never offered as a provider.
- Per-provider knowledge exists in exactly one backend module; a repository
  search for a provider key outside the registry, tests, and documentation
  returns no spawn, status, or validation logic.
- The frontend declares the provider union exactly once.
- Every supported agent is visible in the picker whether or not it is installed,
  only installed ones are selectable, and installed ones sort above the rest.
- The picker opens with no provider chosen and Launch stays disabled until the
  user makes an explicit choice.
- A user with no agent CLI installed sees actionable guidance instead of a
  dropdown of disabled options.
- The permission picker shows `Manual Approve` and `Bypass Permission` and no
  CLI flag names.
- Launch is visible without scrolling at the default panel height, the minimum
  panel height, and a restored persisted height, confirmed in a real browser.
- An AI Block run creates no file that no component deletes.
- The validate-time install hint is a command the `scistudio install` CLI
  accepts.
- No test asserts a hardcoded two-provider set.
- Adding a sixth provider requires editing the registry module plus its
  discovery rule, and no other source file.

## 6. Assumptions

- The owner's position that MCP entries and SKILL.md content are
  provider-agnostic is treated as confirmed: the investigation found that all
  five CLIs consume the same payload and differ only in discovery mechanism.
- Kimi Code's absence of a `--mcp-config` flag is treated as stable for 0.33.x;
  the project-scope file write is chosen over mutating the user-global
  `<KIMI_CODE_HOME>/mcp.json` so SciStudio never edits shared user state.
- Qoder CLI's `--append-system-prompt` is assumed to accept literal text only,
  based on its argument handling reading the value directly with no file
  indirection. The design therefore does not depend on that flag.
- `KIMI_CODE_HOME` is assumed to be the only environment override for Kimi's
  config root, per the CLI's own instruction never to assume `~/.kimi-code`.
- Both Qoder channels are assumed to expose no machine-readable auth status
  command; login state is inferred from the presence of `.auth` under each
  channel's own config root. If a status command is added later, it becomes a
  descriptor field with no structural change.
- The two Qoder channels are assumed to remain flag-compatible. Their `--help`
  surfaces were compared at version 1.1.15 and differ only in the program name
  and description line. If a future release diverges, the shared strategy fields
  split per channel with no structural change, because each channel already
  owns its own descriptor.
- Qoder channel selection is assumed to be an explicit user choice rather than
  something SciStudio infers from locale or network region. SciStudio offers
  whichever channels are installed and never picks one on the user's behalf.
- `~/.qodersec` is assumed to be an internal dependency of the Qoder
  security-scan plugin rather than a user-facing CLI install, based on its
  pinned older version, its `channel` marker, and its colocation with
  `qodersec.exe`. It is excluded from discovery on that basis.
- The `user-terminal` pseudo-provider stays outside the agent provider set and
  is not affected by this change beyond sharing the registry's shape.
- Provider CLIs are user-installed. SciStudio does not bundle, vendor, or
  auto-install them. Per-provider install instructions stay out of the normal
  Setup flow because the owner confirmed their users know how to install these
  CLIs. The zero-install notice is not a contradiction of that decision: it
  addresses the first-run dead end where no choice exists at all, and it names
  the supported agents rather than reciting install commands.
- Listing not-installed providers as disabled options is assumed to be the right
  reading of the owner's two requirements — list what is installed, and let
  users know what is supported. A dropdown that hid unavailable agents would
  satisfy the first and defeat the second.
- `user-terminal` is assumed to stay out of the provider dropdown because it is
  launched from its own bottom-panel surface, not from the chat Setup screen.
- The permission relabel is assumed to need no migration because it changes only
  displayed text; persisted tab state and the launch payload keep their existing
  values.
- No principled default provider exists, so none is offered. Registry order is
  arbitrary and would silently bias users toward whichever descriptor happens to
  be listed first. A last-used-provider default would be principled but requires
  new persisted state, still needs a placeholder on first run, and can point at
  a since-uninstalled CLI. The `Choose provider…` placeholder is chosen instead;
  last-used is a possible later enhancement and is out of scope here.
- Available-first ordering is assumed not to need a visible group separator. If
  the supported set grows enough that a flat ordered list becomes hard to scan,
  option groups are a presentation-only follow-up.
- The ADR governance gap described in section 1 is assumed to be resolved by the
  owner before implementation begins. This spec does not assume which of the two
  options is chosen, and its content is unaffected by that choice; only its
  `status` and `related_adrs` change once the ADR side lands.
- `src/scistudio/ai/agent/providers_registry.py` and
  `frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx` are
  declared under `planned_governs` because they do not exist yet. They move to
  `governs` when the implementation creates them.
- The three module-private names this spec discusses by name —
  `_VALID_PROVIDERS`, `_PROVIDER_SPAWNERS`, and `_spawn` — are deliberately not
  listed in `governs.contracts`. They are internal implementation details rather
  than public contracts, and underscore-prefixed names do not resolve in the
  generated symbol facts the closure audit checks against.
- Existing workflow YAML using `provider: claude-code` remains valid; enum
  widening is backward compatible and no migration is required.
