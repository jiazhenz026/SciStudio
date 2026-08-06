---
spec_id: adr-034-multi-provider-agent-chat
title: "ADR-034 Multi-Provider Agent Chat Implementation Specification"
status: Planned
feature_branch: docs/1992-adr-034-multi-provider-spec
created: 2026-08-06
input: "Owner request: add Kimi Code and Qoder CLI support to AI chat, covering every feature surface including AI Block, with the provider set driven by one registry instead of scattered per-provider branches. Qoder must support both its international and China channel CLIs simultaneously."
owners:
  - "@jiazhenz026"
related_adrs:
  - 34
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
    - WITHDRAWN 2026-08-06 - Pin the SetupScreen action bar so Launch is reachable at every bottom-panel height without scrolling. See User Story 6 for the measurements that withdrew it.
    - Collapse the three duplicated frontend provider union types into one source.
    - Fix the orphaned system-prompt temp file leak on the AI Block spawn path.
    - Replace the invalid `scistudio install --target claude-code` hint emitted by AI Block validate-time errors with a message that does not suggest a command incapable of installing the provider CLI.
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
    - scistudio.ai.agent.providers_registry
    - scistudio.ai.agent.terminal
    - scistudio.api.routes.ai
    - scistudio.api.routes.ai_pty
    - scistudio.blocks.ai.ai_block
    - scistudio.engine.pty_control
  contracts:
    - scistudio.ai.agent.providers_registry.CredentialProbe
    - scistudio.ai.agent.providers_registry.McpInjection
    - scistudio.ai.agent.providers_registry.ProviderDescriptor
    - scistudio.ai.agent.providers_registry.ProviderKind
    - scistudio.ai.agent.providers_registry.ProviderRegistry
    - scistudio.ai.agent.providers_registry.REGISTRY
    - scistudio.ai.agent.providers_registry.SystemPromptInjection
    - scistudio.ai.agent.providers_registry.resolve_binary
    - scistudio.ai.agent.terminal.spawn_agent
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
    - src/scistudio/ai/agent/providers_registry.py
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
    - frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx
    - frontend/src/components/AIChat/SetupScreen.parts/PermissionModePicker.tsx
    - frontend/src/components/AIChat/SetupScreen.parts/ProviderPicker.tsx
    - frontend/src/components/AIChat/SetupScreen.parts/types.ts
    - frontend/src/components/AIChat/hooks/usePtyWebSocket.ts
    - frontend/src/components/AIChat/blockPtyHandlers.ts
    - frontend/src/hooks/useWebSocket.parts/handleBlockPty.ts
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
  files: []
  excludes: []
tests:
  - tests/ai/test_providers_registry.py
  - tests/ai/test_provider_mcp_write_atomicity.py
  - tests/ai/test_windows_executable_resolution.py
  - tests/api/test_provider_discovery.py
  - tests/api/test_provider_discovery_agreement.py
  - tests/api/test_provider_propagation_chain.py
  - tests/api/test_provider_registry_extensibility.py
  - tests/api/test_ai_pty.py
  - tests/api/test_ai_pty_engine_spawn.py
  - tests/api/routes/ai_pty/test_engine.py
  - tests/architecture/test_adr_034_provider_single_source.py
  - tests/blocks/ai/test_ai_block_skeleton.py
  - tests/cli/test_install.py
  - tests/engine/test_pty_control.py
  - frontend/src/components/AIChat/__tests__/SetupScreen.test.tsx
  - frontend/src/components/AIChat/__tests__/TerminalTab.test.tsx
  - frontend/src/components/AIChat/__tests__/ProviderExtensibility.test.tsx
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

### Corrections from the owner's live hand-test (2026-08-06, issue #1994)

The owner ran the implementation on a real workstation with `claude`, `codex`,
`kimi` and `qoderclicn` installed. Five defects surfaced, and three of them
falsify or extend facts recorded above. Live observation beats the tables, so
the tables are corrected here rather than the code being bent to match them.

**Manual Approve was never expressed on the command line.** The tables record a
bypass flag per provider and nothing for safe mode, and the implementation
matched that: safe mode appended no argv at all. Every one of these CLIs
persists a permission mode across sessions, so "no flag" does not mean "ask
me" — it means "resume whatever was saved". The owner selected Manual Approve
and got Claude Code in auto mode and Codex in YOLO mode. Manual mode is now
stated explicitly, as a descriptor field symmetric with the bypass flag:

| Fact | `claude-code` | `codex` | `kimi-code` | `qoder` / `qoder-cn` |
|---|---|---|---|---|
| Manual-approve flag | `--permission-mode manual` | `--ask-for-approval untrusted` | **none** | `--permission-mode default` |

Each value was confirmed by running the binary: a bogus value is rejected
(`claude` exits 1, `codex` exits 2, `qoderclicn` exits 1 listing its choices)
while the value above is accepted. Kimi Code exposes only the *loosening* flags
`-y/--yolo` and `--auto`, so manual mode is the absence of both; the registry
records that as an explicit reason string rather than an empty field.

**Kimi Code has no positional prompt.** The tables do not record how each CLI
receives an AI Block's task, and the implementation assumed every provider takes
one after a `--` separator. `kimi --help` at 0.33.0 shows
`Usage: kimi [options] [command]` with no `[prompt]` argument, so a positional
is parsed as a subcommand: `kimi -- "<task>"` exits 1 with
`unknown command '<task>'`. Its only prompt flag, `-p/--prompt`, runs one prompt
non-interactively and exits, which cannot seed the interactive session an AI
Block needs. Kimi Code is therefore a chat-tab provider only, and the AI Block
refuses it at config time with that explanation.

This means **Success Criterion 2 is not met for `kimi-code`**, and that is
recorded here rather than papered over. Two alternative delivery routes were
examined before accepting the limitation:

*Typing the prompt over PTY stdin.* No such route exists. `_engine_initial_stdin`
is assigned `""` in `open_engine_initiated_tab` and read by nothing, on this
branch and on `origin/main` alike — #1789 removed the consumer precisely because
a raw-mode TUI ignored the trailing carriage return and the typed prompt sat
unsubmitted for Claude Code and Codex. Rebuilding it is new mechanism, not
reuse. Whether Kimi would behave differently from the two CLIs that motivated
#1789 could **not** be determined on the owner's workstation: Kimi blocks at its
own `Trust this folder?` gate on launch and exits without an answer, and the
account needed to drive it past that point is not available. This is an open
question, not a closed one.

*Non-interactive mode.* `kimi -p "<task>"` would run the task with tools and MCP
available and print the result, which the block's completion watcher could
observe. It is rejected as an unreviewed substitution rather than as impossible:
it replaces the visible, interruptible TUI session that ADR-035 describes with an
unattended one-shot run, and it makes the block's own **Manual Approve** setting
meaningless because there is no session in which to approve anything. Adopting
it would change what an AI Block *is* for one provider, which is an owner
decision and not one to take silently inside a bug fix.

**A batch-launcher install truncates the AI Block prompt.** Codex installs from
npm as `codex.cmd` with no `codex.exe` on PATH — the real binary sits under a
hashed `node_modules` path — so `CreateProcess` runs it through `cmd.exe`, whose
command line ends at the first line feed. The composed AI Block prompt is
multi-line, so Codex received only its first line and the owner's own task never
arrived. Claude Code resolves to `claude.exe` and was unaffected, which is why
the defect looked Codex-specific. Prompts delivered to a `.cmd`/`.bat` launcher
are now collapsed to a single line; providers resolving to a real executable
keep their exact text.

**Hook provisioning has no parity, and skills were never the problem.** The
skills rows above are correct — the owner confirmed SciStudio's skills do take
effect. What did not take effect are the data-protection and tool-use *hooks*, a
separate per-CLI mechanism the tables never covered:

| Fact | `claude-code` | `codex` | `kimi-code` | `qoder` / `qoder-cn` |
|---|---|---|---|---|
| Hook config location | `<project>/.claude/settings.json` | `<project>/.codex/config.toml` | **no hook system** | `<project>/.qoder/settings.json` |
| Project-dir variable | `$CLAUDE_PROJECT_DIR` | `$(git rev-parse --show-toplevel)` | n/a | `$QODER_PROJECT_DIR` |
| Provisioned before #1994 | yes | yes | n/a | **no** |
| Extra gate | none | **trust review (answered in PTY) + POSIX-only command, now fixed** | n/a | none |

Qoder's location and format were established by running
`qoderclicn hooks migrate --from-claude` at 1.1.15 against a SciStudio-
provisioned project: it wrote `<project>/.qoder/settings.json` holding
SciStudio's seven hook entries with `$CLAUDE_PROJECT_DIR` rewritten to
`$QODER_PROJECT_DIR`. `.qoder` — not `.qoder-cn` — is the project scope for both
channels; the observation was made with the China-channel binary. A blocking
hook placed in that file was then confirmed to stop a Bash tool call and surface
the hook's stderr, so exit-code-2 blocking behaves as it does for Claude Code.

Codex's declarations were already provisioned and do load — `--strict-config`
accepts them, and a bogus key in the same file is rejected, proving the file is
read — but Codex 0.130+ gates hook *execution* behind an interactive trust
review. This is **documented Codex behaviour, not a SciStudio defect**, and it
is left in place.

The gate is real: a Codex TUI opened in a provisioned project shows a panel
reading `SessionStart 2 0 2 … Press t to trust all; enter to review hooks` —
two hooks declared, zero trusted — and fires none of them.

The panel **is reachable and answerable inside SciStudio's PTY**. Spawning
Codex through the same `winpty` path the chat tab uses renders it verbatim into
the terminal stream, as a blocking numbered menu:

```
Hooks need review
10 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.
› 1. Review hooks
  2. Trust all and continue
  3. Continue without trusting (hooks won't run)
Press enter to confirm or esc to go back
```

The WS route already forwards every keystroke to the PTY verbatim, so the user
sees this on first launch in a project and answers it once. Option 3's
parenthetical is Codex stating the consequence plainly, and it is why the
owner's hooks did not run: the gate had not been answered.

**Trust was necessary but not sufficient.** After the owner answered that menu,
Codex hooks still failed repeatedly with a nonzero exit. The second cause is in
the generated command itself, and it is older and larger than ADR-034: **no
SciStudio hook has ever run under Codex on Windows.**

Every Codex hook command SciStudio has written resolves the project root with
`$(git rev-parse --show-toplevel)` — POSIX command substitution. Running the
generated command from a provisioned project through each shell:

| Shell | Result |
|---|---|
| `cmd.exe` | substitution passed through **literally**; Python is handed `…\$(git rev-parse --show-toplevel)\.claude\hooks\…` → `can't open file`, **exit 2** |
| `powershell.exe` | fails earlier still: a command line whose first token is a quoted path parses as a string *expression*, not an invocation → `Unexpected token`, **exit 1** |
| Git Bash | **exit 0** |

Only a POSIX shell works. Claude Code and both Qoder channels run hooks through
Git Bash, which is why they were unaffected and why the failure looked
Codex-specific. It is not a Codex bug, and it is not TOML escaping — the
escaping is correct.

The fix removes the construct instead of translating it per shell: the
project's absolute hook path is baked in at provisioning, spelled with forward
slashes and left unquoted. That single string is verified to execute with exit
0 in `cmd.exe`, PowerShell **and** `sh`, so it no longer depends on knowing
which shell Codex uses — which remains undocumented and could not be
established here, because no hook could be made to execute under Codex at all
in a scratch project. Existing projects are repaired through the upgrade path,
since `write_codex_config` preserves an existing file and would otherwise leave
already-provisioned users with dead hooks indefinitely.

Qoder was re-verified with SciStudio's **genuine generated** hook rather than a
hand-written one: its writer emits `$QODER_PROJECT_DIR` and never the
substitution, and the real `deny_scistudio_cli.py` blocked a `scistudio run`
Bash call, with the agent relaying SciStudio's own hook text. Claude Code is
*conditionally* fine: its command uses the same `"exe" "$VAR/…"` shape, which
only a POSIX shell executes, so its hooks depend on Git Bash being present on
Windows. That is a latent exposure for a Windows user without Git for Windows,
recorded here rather than fixed because no such failure has been observed.

Separately, the interpreter path baked into these commands is whatever
`sys.executable` was at provisioning time. In the owner's sample that was
`.workflow/local/venv/Scripts/python.exe` — the gate's disposable parity venv —
because provisioning happened to run under it. This is a **real but narrower
exposure**: it breaks hooks whenever that interpreter moves or is deleted, and
it is not new (the MCP `command` in the same file has always been captured the
same way). It is left unfixed and unhidden here because the correct remedy —
resolving a stable interpreter, or re-resolving at hook time — is a design
decision beyond this bug fix.

`--dangerously-bypass-hook-trust` would make the hooks fire with no prompt, and
was **deliberately rejected**. It disarms the review for the whole config file —
including anything a user later adds to it — on every launch, in whichever
permission mode; Codex's own wording ("hooks can run outside the sandbox after
you trust them") shows what the review protects. Answering a security prompt on
the user's behalf, in the same change that adds `manual_argv` precisely so the
user's Manual Approve is *not* overridden, would be self-contradictory. The
expected first-run experience is therefore: the user answers the hook-trust menu
once per project, and SciStudio's hooks run from then on.

Kimi Code has no hook surface at all: `kimi --help` at 0.33.0 lists none, and
its config root contains no hook file. The owner asked specifically whether Kimi
has the same gap — it does not have the gap because it has no mechanism to
provision, which is a permanent limitation rather than a missing feature.

### Governance alignment — how the gap was closed (2026-08-06)

This spec was authored as `status: Draft` because the
`doc-drift.missing-adr-governance` rule requires every ADR listed in a `Planned`
or `Implemented` spec's `related_adrs` to cover every surface the spec governs,
and this spec's surface is wider than what ADR-034 governed. That item is now
closed and the spec is `Planned`. The resolution is recorded here because two of
its three parts are non-obvious and a future reader who re-derives them from
scratch will waste the same time.

**1. The addendum option does not work.** The Draft text offered two options:
expand ADR-034's `governs`, or author an ADR-034 addendum. The manager verified
during dispatch preflight that they are not equivalent — the second is silently
ineffective. `doc_drift._check_adr_spec_alignment` builds its ADR lookup as
`{frontmatter.adr: document}` over all `docs/adr/ADR-*.md`;
`ADRAddendumFrontmatter` subclasses `ADRFrontmatter` and carries the *parent*
ADR number; and `sorted()` orders `ADR-034-addendum1.md` before `ADR-034.md`. The
base ADR therefore overwrites the addendum in that dict and the addendum's
`governs` is never read. An addendum would have looked like governance and
provided none. That tooling defect is tracked as issue **#2004** and was
deliberately not fixed inside this dispatch.

**2. The owner authorized editing ADR-034 directly.** ADR-034 is Accepted,
`phase: legacy`, and marked `agent_editable: false`. On 2026-08-06 the owner
authorized amending it. The expansion is expressed as a fenced block whose info
string is exactly `yaml adr042-governance-amendment`, in ADR-034 section 3.4 —
the same ADR-042 mechanism ADR-041 Addendum 1 and ADR-043 Addendum 1 use — which
`scistudio.qa.audit._util._apply_governance_amendments` merges into ADR-034's
`governs` at load time. The frontmatter of ADR-034 is byte-identical to before,
so the original accepted record is intact. ADR-034 section 3 also records the
registry decision itself and the verified adapter matrix, so the amendment is a
decision record rather than a metadata edit.

**3. `related_adrs` narrowed from `[34, 35, 40]` to `[34]`.** The rule is a
strict conjunction: *each* listed ADR must independently cover *every* spec
surface. With ADR-034 amended and the other two still listed, flipping to
`Planned` yields 75 `missing-adr-governance` errors — 0 against ADR-034, 33
against ADR-035, 42 against ADR-040 — because ADR-035 does not govern
`scistudio.ai.agent.terminal` and ADR-040 does not govern
`scistudio.engine.pty_control` or `scistudio.api.routes.ai_pty`. Closing them
would have required amending three Accepted legacy ADRs to each govern the
others' surfaces, which is worse governance, not better. Every other active spec
in this repository lists exactly one ADR, which is the convention the conjunction
forces. ADR-035 (AI Block as a PTY-tab variant) and ADR-040 (agent
provisioning) remain genuinely related and are cited throughout this document;
they are simply not co-governors of this surface.

The two files declared under `planned_governs` in the Draft —
`src/scistudio/ai/agent/providers_registry.py` and
`frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx` — now
exist and have moved to `governs.files`. `planned_governs` is empty.

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
  names the provider and its expected binary and suggests no `scistudio install`
  command, because that command cannot install a provider CLI.
- Given an AI Block spawns a tab, when the frontend receives `block_pty_opened`,
  then the tab records the provider the engine actually spawned rather than a
  hardcoded `claude-code`, at every link from the WS payload through
  `blockPtyHandlers` to the store.
- Given a project already has a `.kimi-code/mcp.json` with the user's own MCP
  servers, when a Kimi tab spawns, then those servers are still present
  afterwards and only the SciStudio entry changed.

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

### User Story 6 - Reach Launch At Any Panel Height — WITHDRAWN (2026-08-06)

**Status: withdrawn by the owner on 2026-08-06 after measurement. FR-021g and
FR-021h are withdrawn with it. Task T-011c is not delivered.
`frontend/src/components/BottomPanel.tsx` and
`frontend/src/components/AIChat/TerminalTabs.tsx` are not touched by this
change and no longer appear in `governs.files` or section 4.2.**

The original story read: *As a SciStudio user, I can always see and click Launch
regardless of how tall the bottom panel is, without discovering that the panel
scrolls.* It was P1 on the strength of an owner report that Launch sat below the
fold at the default bottom-panel height.

The report was real and reproducible. The **explanation** in section 4.1 was
wrong, and the **fix** it prescribed was measurably inert. No follow-up issue is
being opened, deliberately, so this subsection is the only surviving record of
what was measured. It is written so a future reader who hits the same symptom
can pick it up without re-measuring.

#### 6.1 What was originally claimed, and what is now disproven

Section 4.1 argued that two `h-full` block wrappers — one in `BottomPanel` that
CSS-hides the inactive surface, one in `TerminalTabs` that CSS-hides inactive
tabs — lose a definite height, that `BottomPanel`'s `overflow-y-auto` wrapper
then scrolls the whole chat surface including the footer, and that the fix was
to convert both wrappers to definite-height flex containers *and* pin the action
bar with `sticky bottom-0` plus an opaque background.

Both halves of that fix were isolated one variable at a time in a real browser:

- **The percentage-height chain resolves correctly.** Converting the two
  wrappers produced **byte-identical geometry**, identical scrollability, and an
  identical `Floor(visible)` of **176 px**. The conversion buys nothing. The
  hypothesis required an ancestor with an indefinite height; there is none,
  because the bottom panel is a flex item with a resolved pixel height.
- **`sticky bottom-0` is inert at every panel height.** Measured on
  `origin/main` with and without it, clipping at panel heights 150 px / 120 px /
  minimum is **20 / 9 / 46 px in both cases**. This is not a measurement
  artifact: a sticky box may not be moved outside its containing block, and
  below the floor the containing block is already shorter than the bar, so there
  is nowhere for `sticky` to move it to.

An earlier manager hypothesis — that the wrapper conversion *regressed* the
failure mode from scroll-reachable to clipped — was also falsified by the same
harness: `canScroll` is identical at every panel height on both branches, and
`afterScroll` is false below the floor on both.

#### 6.2 What the mechanism actually is

It is a **crush**, not a lost height. The chat setup surface has a fixed pixel
floor:

- **176 px** — below this the Launch button is no longer fully visible.
- **192 px** — below this something in the surface is clipped, with no
  scrollable ancestor able to reveal it.

That floor is a sum of fixed chrome, not a percentage:

| Contribution | Height |
|---|---|
| `BottomPanel` tab strip | 61 px |
| `BottomPanel` content-wrapper padding | 16 px |
| `TerminalTabs` tab strip | 37 px |
| `SetupScreen` padding | 24 px |
| Action bar | 55 px |
| **Total** | **176 px** |

Roughly 98 px of that is the two tab strips, ~17 px is padding, and ~61 px is
the action bar itself, which is irreducible. Nothing in the CSS of `SetupScreen`
or its wrappers can shrink a sum of fixed chrome.

Three further measured facts complete the picture:

- **The panel's `minSize` is a percentage while the floor is fixed pixels**, so
  no single percentage expresses it. Covering 1280x720 needs about **29 %**,
  which on a 2560x1440 display would impose a **385 px** minimum panel height.
  A correct fix is a **pixel** `minSize`, not a CSS change in the chat surface.
- **Below the floor the button is partially visible and clickable but never
  reachable by scrolling.** At 1280x520, `visible` is false while `clickable` is
  true, with **20.2 of 36 px** on screen and `elementFromPoint` hitting the
  button. The setup body genuinely scrolls, and below ~120 px the `BottomPanel`
  wrapper scrolls too — but `SetupScreen`'s `overflow-hidden` root clips the bar
  before the overflow can ever reach `BottomPanel`'s scrollable wrapper. So both
  of the owner's seemingly contradictory reports ("it is below the fold" and "I
  can find it by scrolling") are true simultaneously. What is never true is that
  scrolling brings the button *fully* into view.
- **Why History / Lineage does not show this.** `RunDetail` is rendered directly
  into `BottomPanel`'s content wrapper, skipping the 37 px `TerminalTabs` strip
  and `SetupScreen`'s 24 px padding, so its floor is about 61 px lower.
  `RunDetail`'s root also has no `overflow-hidden`. Section 4.1 originally used
  `RunDetail` as evidence that a *weaker* implementation works while a stronger
  one fails, and concluded the defect was in the host chain. The comparison was
  sound; the conclusion drawn from it was not. `RunDetail` works because it pays
  61 px less chrome, not because the wrapper chain treats it differently.

The symptom is viewport-dependent, with a crossover near **558 CSS px** of
window height. Real configurations below the crossover include a 1366x768 laptop
at 150 % scaling (512 CSS px) and 1920x1080 at 200 % (540 CSS px). An early
round that measured only at 1280x720 saw it pass; the blind spot was the
viewport, not the analysis.

#### 6.3 Why the owner withdrew it

The owner tested the real application at panel heights below the floor and
judged it a non-issue: **below that threshold nothing in the panel is clickable
at all**, so a user in that state drags the tab bar up rather than hunting for a
Launch button. The remaining honest fix — converting the panel's percentage
`minSize` to pixels — is a bottom-panel resize change, which this spec's
`scope.out` explicitly excludes ("Redesigning the bottom panel, its resize
behavior, its default height, or its existing pin-open toggle").

Carrying the two inert changes anyway was rejected on the grounds that neither
is a regression but both would leave a **disproven rationale** in PTY-critical
files, inviting the next reader to believe it. The action-bar pin that A5 had
already landed was reverted for the same reason.

The one change from this area that *was* real is not part of the withdrawn work:
the entire measured delta between baseline and the pinned version came from a
`pb-1` padding change, not from `sticky` or the wrapper conversion.

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
- The project already has a `.kimi-code/mcp.json` containing the user's own MCP
  servers. Injecting the SciStudio entry must leave every other entry intact.
- That file exists but is malformed. The write must fail loudly rather than
  replace it, because replacing it destroys content the user cannot recover.
- Two SciStudio processes inject into the same provider-owned config file
  concurrently. The write must be atomic so the file is never observed
  half-written.
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
- ~~The bottom panel is at its collapsed height where even a pinned action bar
  cannot fit.~~ Withdrawn with User Story 6. Measured answer, kept because it is
  the fact the case was groping for: below a 176 px fixed chrome floor the
  action bar is clipped by `SetupScreen`'s own `overflow-hidden` root before any
  ancestor scroll can reach it, and no CSS change in the chat surface can alter
  a sum of fixed chrome.
- ~~A persisted panel height from an earlier session is smaller than the current
  default.~~ Withdrawn with User Story 6. The restored-height case behaves
  identically to the dragged case; the floor is a function of chrome, not of how
  the height was arrived at.

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
  registry and, when the failure is a missing provider binary, MUST NOT suggest
  `scistudio install`. That command wires SciStudio's MCP server and skills into
  a CLI the user already has; it cannot install the CLI itself, so running it
  would leave discovery failing. The error MUST name the provider and its
  expected binary, and otherwise omit any command SciStudio cannot make
  corrective.
- FR-015: `AIBlock.config_schema` `provider` enum MUST be derived from the
  registry's agent provider keys with `claude-code` remaining the default.
- FR-016: For providers with an explicit MCP config flag, the spawn argv MUST
  pass `<project>/.scistudio/mcp.json`.
- FR-017: For providers without an MCP config flag, spawn MUST write the
  SciStudio MCP entry into that provider's own project-scope discovery location
  before the process starts.
- FR-017a: When the write target is a config file owned by the provider rather
  than by SciStudio, the write MUST read, merge, and atomically replace the
  file, changing only the SciStudio server entry and preserving every other
  key. Whole-file replacement is forbidden for such targets.
- FR-017b: A merge write MUST refuse to proceed when the existing file is
  present but unparseable, and MUST surface an actionable error rather than
  overwriting or silently discarding the user's content.
- FR-018: MCP entry content MUST remain provider-agnostic; only the write
  location and injection mechanism may differ per provider.
- FR-019: Skill provisioning MUST remain unchanged; the spec MUST NOT add a new
  skills tree for either new provider.
- FR-020: The frontend MUST declare the provider type exactly once and every
  consumer MUST import it.
- FR-020a: Agent provider keys MUST NOT be a hand-maintained TypeScript literal
  union, because that reintroduces the duplication FR-001 removes and breaks the
  registry-only extension path. The frontend MUST treat agent provider keys as
  opaque strings validated at runtime against the status payload. The
  `user-terminal` pseudo-provider MAY remain a literal, since the frontend
  branches on it for surface routing.
- FR-020b: Provider display labels MUST come from the backend status payload
  rather than a frontend label map, so adding a provider requires no frontend
  edit. The status entry gains a `label` field; the existing fields are
  unchanged and the addition is backward compatible.
- FR-020c: The provider MUST be carried end to end on the engine-initiated tab
  path: the `block_pty_opened` payload, its WS dispatch handler, the
  `blockPtyHandlers` entry point, and the store action that creates the tab MUST
  each accept and forward it. No link may substitute a default.
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
- FR-021g: **WITHDRAWN 2026-08-06.** Previously: "The Setup screen action bar
  containing Cancel and Launch MUST remain visible at every bottom-panel height
  the panel permits, without requiring the user to scroll any ancestor
  container." Withdrawn by the owner after measurement showed the prescribed fix
  is inert and the real constraint is a fixed 176 px chrome floor against a
  percentage panel `minSize`. See User Story 6.
- FR-021h: **WITHDRAWN 2026-08-06.** Previously: "The action bar MUST render on
  an opaque background when content can pass behind it." Withdrawn with FR-021g;
  content cannot pass behind a bar that is never pinned. See User Story 6.
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
The draft allowed the old names to survive as thin registry lookups if tests
depended on them; **as delivered they are removed**, and `governs.contracts`
lists `spawn_agent` instead. Anything that looks like a transitional shim in
this area is a defect, not a plan. `resolve_windows_executable` gains an
explicit well-known-directory parameter sourced from the descriptor, replacing
`_windows_user_cli_dirs()`.

MCP injection becomes a strategy dispatch with three observed shapes: an
explicit `--mcp-config` flag (`claude-code`, `qoder`, `qoder-cn`), Codex `-c`
overrides (`codex`), and a project-scope file write (`kimi-code`, writing
`<project>/.kimi-code/mcp.json` before spawn). The payload in every case is the
existing `_mcp_entry_payload(project_dir)`.

The Kimi write must **not** reuse `_ensure_mcp_config`. That helper rewrites the
whole file every call, which is correct for `<project>/.scistudio/mcp.json`
because SciStudio owns that path, and destructive for
`<project>/.kimi-code/mcp.json` because Kimi owns it and the user may have
registered their own MCP servers there. Reusing the clobbering helper would
silently delete that configuration. The Kimi strategy therefore reads the
existing file, merges only the SciStudio server entry, and atomically replaces
the file; an existing-but-unparseable file is an error, never an overwrite. The
merge-preserving pattern already exists in `cli/install.py`, which edits
user-owned `~/.claude.json` and `.codex/config.toml` without clobbering them —
that is the precedent to follow, not `_ensure_mcp_config`.

System-prompt injection has two
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
because it is launched through a separate affordance.

Two details here decide whether the registry actually delivers the
single-file-extension promise of User Story 7. A hand-maintained TypeScript
literal union and a frontend label map would both need editing for every new
provider, which reintroduces exactly the duplication FR-001 removes. So agent
provider keys become opaque strings validated at runtime against the status
payload, and display labels are returned by the backend as a new `label` field
on each status entry. `user-terminal` stays a literal because the frontend
branches on it to route between the chat and terminal surfaces. The tradeoff is
explicit: agent provider keys lose compile-time exhaustiveness checking in
TypeScript, which is the price of not maintaining the list in two languages.

The engine-initiated tab path needs the provider threaded through four links,
not two. `open_engine_initiated_tab` already knows the provider once
`PtyTabSpec` carries it, so `block_pty_opened` gains a `provider` field; the WS
dispatch in `handleBlockPty.ts` forwards it; `blockPtyHandlers.handleBlockPtyOpened`
accepts it in its payload type; and `addAiBlockTerminalTab` stores it instead of
`terminalTabsSlice`'s hardcoded `"claude-code"`. Changing only the slice and the
WS dispatch would leave `blockPtyHandlers` unable to forward a provider it never
received, so the tab would keep recording the default.

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

**The action-bar subsection that stood here is withdrawn and its analysis is
disproven.** It argued that two `h-full` CSS-hiding wrappers lose a definite
height, that `BottomPanel`'s `overflow-y-auto` wrapper then scrolls the whole
surface including the footer, and that the fix was to convert both wrappers and
pin the bar with `sticky bottom-0` plus an opaque background. Single-variable
isolation in a real browser showed the wrapper conversion produces
byte-identical geometry and `sticky bottom-0` is inert at every panel height.
The real mechanism is a fixed 176 px chrome floor measured against a percentage
panel `minSize`. The full measurement record, including why `Lineage/RunDetail`
appears to work and why the button is clickable but never fully scrollable into
view, is in **User Story 6**, which is the surviving record. `BottomPanel.tsx`
and `TerminalTabs.tsx` are not modified by this change.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/ai/agent/providers_registry.py` | create | Descriptor dataclasses and the provider table |
| `src/scistudio/ai/agent/terminal.py` | modify | Registry-driven `spawn_agent`; parameterised Windows resolver; remove per-provider factories |
| `src/scistudio/api/routes/ai_pty/_state.py` | modify | Derive `_VALID_PROVIDERS` and `_PROVIDER_SPAWNERS` from the registry |
| `src/scistudio/api/routes/ai_pty/engine.py` | modify | Accept explicit `provider`; delete `_provider_from_argv` |
| `src/scistudio/api/routes/ai_pty/internal_routes.py` | modify | Read `provider` from the request spec |
| `src/scistudio/api/routes/ai_pty/__init__.py` | modify | Update the WS contract docstring provider list |
| `src/scistudio/api/routes/ai.py` | modify | Registry-driven status list and credential probes; add the `label` field to each status entry |
| `src/scistudio/engine/pty_control.py` | modify | Add `provider` to `PtyTabSpec`; drop `spawn_argv` |
| `src/scistudio/blocks/ai/ai_block.py` | modify | Delete `_build_spawn_argv`, `_BYPASS_FLAG`, `_discover_provider`; registry-derived enum and validation |
| `src/scistudio/cli/install.py` | modify | Accept registry-derived targets; keep existing targets working |
| `src/scistudio/_skills/scistudio/scistudio-build-workflow/SKILL.md` | modify | Update the documented AI Block provider enum |
| `frontend/src/store/types.ts` | modify | Single `TerminalProvider` union |
| `frontend/src/components/AIChat/SetupScreen.parts/types.ts` | modify | Import the shared union instead of redeclaring |
| `frontend/src/components/AIChat/hooks/usePtyWebSocket.ts` | modify | Import the shared provider type instead of an inline literal |
| `frontend/src/components/AIChat/blockPtyHandlers.ts` | modify | Accept `provider` on the `block_pty_opened` payload and forward it to the store action |
| `frontend/src/components/AIChat/SetupScreen.parts/ProviderPicker.tsx` | modify | Replace radio list with a status-driven select using backend-supplied labels; available-first ordering; `Choose provider…` placeholder |
| `frontend/src/components/AIChat/SetupScreen.parts/PermissionModePicker.tsx` | modify | Relabel to Manual Approve / Bypass Permission; strip CLI flag names |
| `frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx` | create | Zero-install guidance panel naming every supported agent |
| `frontend/src/components/AIChat/SetupScreen.tsx` | modify | Pass the status array instead of named per-provider props; branch to the zero-install notice |
| `frontend/src/store/terminalTabsSlice.ts` | modify | Record engine-reported provider on engine-initiated tabs |
| `frontend/src/hooks/useWebSocket.parts/handleBlockPty.ts` | modify | Carry `provider` from the `block_pty_opened` payload |
| `tests/ai/test_providers_registry.py` | create | Descriptor completeness and registry-derivation tests |
| `tests/api/test_provider_discovery.py` | modify | Replace the exact two-provider set assertion |
| `tests/api/test_ai_pty_engine_spawn.py` | modify | Replace the argv-sniffing test with explicit-provider tests |
| `tests/blocks/ai/test_ai_block_skeleton.py` | modify | Cover registry-derived enum and no-temp-file-leak |
| `src/scistudio/cli/install.py` | modify | Make `_atomic_write_json` concurrency-safe (see section 4.6) |
| `src/scistudio/ai/agent/mcp/tools_inspection/_preview.py` | modify | One-line import-form change that returns the cycle count to its baseline (see section 4.6); not a governed surface of this spec |
| `docs/adr/ADR-034.md` | modify | Section 3 records the provider registry decision, the verified adapter matrix and its verification date, and an `adr042-governance-amendment` block expanding `governs`. Not an addendum file — see section 1 |
| `docs/specs/embedded-coding-agent-spec.md` | modify | Update the locked-contract note's provider set |

### 4.3 Implementation Sequence

| Task | Depends on | Work | Verification |
|---|---|---|---|
| T-001 | none | Add descriptor dataclasses and the five agent descriptors plus `user-terminal` | Registry unit tests; every descriptor has a complete adapter definition; both Qoder channels present as distinct keys |
| T-002 | T-001 | Parameterise `resolve_windows_executable` with descriptor well-known dirs; exact-name matching only | Resolution tests locate `kimi.exe`, `qodercli.exe`, and `qoderclicn.exe` off-PATH; sidecar copy is rejected; one missing channel does not resolve to the other |
| T-003 | T-001, T-002 | Replace spawn factories with descriptor-driven `spawn_agent` | Argv snapshot tests per provider; no cross-provider flag leakage |
| T-004 | T-003 | Implement the three MCP injection strategies, with a merge-preserving atomic write for provider-owned config files | Kimi project MCP file written before spawn; a pre-existing `.kimi-code/mcp.json` with unrelated servers survives unchanged; an unparseable file errors instead of being overwritten; flag providers pass the SciStudio path |
| T-005 | T-001 | Derive `_VALID_PROVIDERS` / `_PROVIDER_SPAWNERS` and the status endpoint from the registry | WS rejection message enumerates five providers; status returns five entries |
| T-006 | T-005 | Descriptor-driven credential probes | Per-provider logged-in tests using fake HOME fixtures |
| T-007 | T-001 | Add `provider` to `PtyTabSpec`; accept it in the internal route and `open_engine_initiated_tab`; delete `_provider_from_argv` | Engine spawn tests assert provider passthrough, not argv inference |
| T-008 | T-007 | Delete `_build_spawn_argv`, `_BYPASS_FLAG`, `_discover_provider`; wire AI Block to the registry | AI Block run leaves no orphaned temp file; missing-binary error names the provider and its binary and suggests no non-corrective command |
| T-009 | T-005, T-008 | Registry-derived AI Block `provider` enum | Existing `claude-code` workflows load unchanged; enum lists five providers |
| T-010 | T-001 | Consolidate the frontend provider type to one source; agent keys become opaque strings; labels come from the status payload | Type check passes with no duplicate literal unions and no frontend label map |
| T-011 | T-010, T-005 | Replace the provider radio list with a status-driven select: backend-supplied labels, available-first ordering, `Choose provider…` placeholder | SetupScreen tests assert one select, disabled/annotation states, group ordering, and that Launch stays disabled until a provider is chosen |
| T-011a | T-011 | Add the zero-install guidance notice and its render branch | Tests for all-unavailable, in-flight, and status-error render paths |
| T-011b | none | Relabel the permission picker and strip CLI flag names; align AI Block `ui_enum_labels` | Rendered text contains no `--` flag; stored values unchanged |
| ~~T-011c~~ | — | **WITHDRAWN 2026-08-06 with User Story 6, FR-021g, and FR-021h.** Both prescribed changes were measured inert; see User Story 6 | Not delivered. No file under `frontend/src/components/BottomPanel.tsx` or `frontend/src/components/AIChat/TerminalTabs.tsx` is modified |
| T-012 | T-007, T-010 | Thread the provider through all four links: `block_pty_opened` payload, `handleBlockPty.ts` dispatch, `blockPtyHandlers.handleBlockPtyOpened`, and `addAiBlockTerminalTab` | Tests assert an engine-initiated Kimi or Qoder tab records that provider end to end and that no link substitutes a default |
| T-013 | T-005 | Extend `scistudio install` targets from the registry | CLI accepts existing and new targets; unknown target still errors |
| T-014 | T-001 to T-013 | Add the ADR-034 body amendment (registry decision, adapter matrix, `adr042-governance-amendment` block), flip this spec to `Planned` and reconcile its governed surface, update the embedded-agent spec note and SKILL.md | `full_audit` is error-free, including its `generate_facts`, `doc_drift`, and `closure` children; adapter matrix records the 2026-08-06 verification date. `docs/facts/generated.yaml` is gitignored, so `scripts/audit/generate_facts.py --check` is meaningful only after a local `--write`; `full_audit`'s `generate_facts` child is the authoritative equivalent |

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
- Add a validate-time test asserting the missing-binary error names the provider
  and its expected binary and contains no `scistudio install` suggestion,
  replacing the current message that emits a command the install CLI rejects and
  that could not have installed the CLI even if it parsed.
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
- Add a merge-preservation test for the Kimi MCP write: seed
  `.kimi-code/mcp.json` with an unrelated server, inject, and assert the
  unrelated entry survives byte-for-byte while only the SciStudio entry changes.
  Add a companion test asserting a malformed file raises instead of being
  overwritten.
- Add an end-to-end provider-propagation test for the engine-initiated path
  covering all four links, so a future refactor cannot reintroduce a default at
  any single hop.
- **The pinned-action-bar browser check is withdrawn with User Story 6.** The
  methodological point that produced it still stands and is worth keeping: the
  existing test `keeps Cancel and Launch outside the scrollable setup body`
  asserts the class strings `overflow-hidden`, `overflow-y-auto`, and
  `shrink-0`, passes today, and told us nothing, because jsdom performs no
  layout. Structural class assertions are not layout evidence. That test remains
  as a structural regression guard only. The real-browser measurement that this
  bullet originally demanded *was* performed, and it is what disproved the
  section 4.1 analysis and led to the withdrawal; the result is recorded in
  User Story 6 rather than encoded as an acceptance check.
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
- ~~**Touching the CSS-hiding wrappers risks unmounting live PTYs.**~~ Retired
  with T-011c. The wrappers are not touched, so the risk does not arise. The
  underlying fact remains true and is worth carrying forward for anyone who
  revisits this area: those wrappers exist so `TerminalTabs` stays mounted
  across tab and surface switches, and unmounting fires the WS cleanup hook and
  kills the agent subprocess, losing the conversation.
- ~~**The action-bar root cause is localised but not yet reproduced by the
  implementer.**~~ Retired. The risk materialised: the root cause was *not*
  correctly localised, and the belt-and-braces mitigation it proposed was
  measured inert on both belts. The lesson is recorded in User Story 6 —
  proposing two fixes because you are unsure which link is at fault is not a
  mitigation; measuring which link is at fault is.
- ~~**Changing `BottomPanel`'s content wrapper affects every bottom tab.**~~
  Retired with T-011c; `BottomPanel.tsx` is not modified.
- **Writing into a provider-owned config file is destructive if done wrong.**
  `.kimi-code/mcp.json` belongs to Kimi, not SciStudio, and a clobbering write
  destroys user configuration with no recovery path. Mitigation: FR-017a/FR-017b
  require read/merge/atomic-write with a hard failure on malformed input, and
  the merge-preservation test is a required acceptance check rather than an
  optional one.
- **Dropping the TypeScript literal union loses compile-time exhaustiveness.**
  A typo in a provider key becomes a runtime rather than a build failure.
  Mitigation: validate provider keys at runtime against the status payload and
  keep `user-terminal` a literal, so the one key the frontend branches on is
  still type-checked.
- **Rollback**: the registry is additive until T-005 switches the whitelists
  over. Reverting the frontend dropdown and the two new descriptors restores the
  previous two-provider behavior without touching the PTY transport. The GUI
  changes are independent of the registry work and can be reverted individually.

### 4.6 Verified Deviations From The Authored Plan (2026-08-06)

Three things changed between this spec as authored and this spec as
implemented. Each was measured before it was decided, and each is recorded here
rather than in a commit message so the reasoning survives.

#### 4.6.1 User Story 6, FR-021g, FR-021h, and T-011c withdrawn

Recorded in full under User Story 6. Summary: the prescribed fix was measured
inert on both of its halves, the root-cause analysis in section 4.1 was
disproven, and the owner judged the residual symptom a non-issue because below
the 176 px floor nothing in the panel is clickable anyway. No follow-up issue
was opened; User Story 6 is the record.

#### 4.6.2 `_atomic_write_json` made concurrency-safe

The spec's Edge Case list required that "two SciStudio processes inject into the
same provider-owned config file concurrently" must be atomic so the file is
never observed half-written. Implementation review found that
`scistudio.cli.install._atomic_write_json` — the helper both the install CLI and
the new Kimi project-scope MCP write go through — staged every write through a
**single shared temp path**, `path.with_suffix(path.suffix + ".tmp")`. The
`os.replace` is atomic, but the staging file is not per-writer, so overlapping
writers corrupt or destroy each other's staged bytes before either rename.

This was measured, not inferred: **227 of 240 overlapping calls failed**. The
user-visible consequence is specific and silent — a Kimi agent starts without
SciStudio tools, with no error surfaced anywhere, because the merged config it
was supposed to read never landed.

The owner approved fixing it inside this dispatch rather than deferring, on the
grounds that the spec already required the property and the helper simply did
not deliver it. The fix gives each writer a unique staging path.

**`_ensure_mcp_config` was deliberately left alone.** It writes
`<project>/.scistudio/mcp.json` with a plain `write_text` and no atomic rename
at all. That is a real and known asymmetry, and it is intentional on three
grounds: the exposure is milder because there is no shared staging file to
corrupt, only a torn read window on a file every writer writes identical bytes
to; the Edge Case is worded for **provider-owned** files, and `.scistudio/` is
SciStudio-owned, which is the same distinction FR-017a already draws when it
permits `_ensure_mcp_config` to keep clobbering that path; and widening the fix
would have pulled an unrelated write path into a dispatch already at its scope
limit. Anyone hardening this later should treat it as known, not overlooked.

#### 4.6.3 The import-cycle ratchet was not raised

FR-012's deletion of `AIBlock._build_spawn_argv` and the registry's placement as
a shared leaf split the 30-module strongly connected component that had welded
`scistudio.ai.agent` to all of `scistudio.blocks.*`. Splitting one large SCC
raises the *count* of SCCs while improving every metric that matters: the
largest SCC went **30 -> 20** and modules-in-cycles went **37 -> 30**, while the
cycle count went **3 -> 5**.

`MAX_PYTHON_CYCLES` in `tests/architecture/test_no_new_cycles.py` was
**deliberately not raised**; it is still 4, the same value as on `main`. Raising
a ratchet to accommodate an improvement teaches the ratchet to lie.

The count was brought back to 4 by a one-line import-form change in
`src/scistudio/ai/agent/mcp/tools_inspection/_preview.py`:
`from scistudio.ai.agent.mcp.tools_inspection import _helpers` became
`import scistudio.ai.agent.mcp.tools_inspection._helpers as _helpers`. The two
bind the same module object at runtime and are interchangeable for the
monkeypatch contract, but they are **not** equivalent to import-graph analysis:
`_collect_imports` records a package edge for `from pkg import sub` — it is an
attribute access on `pkg` — and records only the submodule edge for
`import pkg.sub as sub`. The `from` form was reinstating a child-to-parent
package-facade cycle. Both the module docstring and the function docstring now
say so, because the change reads as a stylistic regression and will otherwise be
"simplified" back.

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
- The frontend declares the provider type exactly once and contains no
  hand-maintained list of agent provider keys or labels.
- Injecting the SciStudio MCP entry into a provider-owned config file preserves
  every unrelated entry in that file.
- An engine-initiated tab records the provider the engine actually spawned, at
  every link from the WS payload to the store.
- Every supported agent is visible in the picker whether or not it is installed,
  only installed ones are selectable, and installed ones sort above the rest.
- The picker opens with no provider chosen and Launch stays disabled until the
  user makes an explicit choice.
- A user with no agent CLI installed sees actionable guidance instead of a
  dropdown of disabled options.
- The permission picker shows `Manual Approve` and `Bypass Permission` and no
  CLI flag names.
- ~~Launch is visible without scrolling at the default panel height, the minimum
  panel height, and a restored persisted height, confirmed in a real browser.~~
  Withdrawn 2026-08-06 with User Story 6. The real-browser measurement was
  performed and is recorded there; it disproved the prescribed fix rather than
  confirming it.
- An AI Block run creates no file that no component deletes.
- Concurrent writes to a provider-owned MCP config file never leave the file
  half-written or lose a writer's content, including when two SciStudio
  processes write the same path at the same time.
- The Python import-cycle ratchet is not raised: `MAX_PYTHON_CYCLES` is
  unchanged, the largest SCC shrinks, and modules-in-cycles falls.
- The validate-time missing-binary error names the provider and its expected
  binary and suggests no command that cannot install that binary.
- No test asserts a hardcoded two-provider set.
- Adding a sixth provider requires editing the registry module plus its
  discovery rule, and no other source file.

## 6. Assumptions

- The owner's position that MCP entries and SKILL.md content are
  provider-agnostic is treated as confirmed: the investigation found that all
  five CLIs consume the same payload and differ only in discovery mechanism.
- Kimi Code's absence of a `--mcp-config` flag is treated as stable for 0.33.x;
  the project-scope file write is chosen over mutating the user-global
  `<KIMI_CODE_HOME>/mcp.json` so SciStudio never edits shared user state. The
  project-scope file is still owned by Kimi rather than SciStudio, which is why
  FR-017a requires a merge write there even though `_ensure_mcp_config` may keep
  clobbering `<project>/.scistudio/mcp.json`, a path SciStudio does own.
- Adding a `label` field to each `/api/ai/status` entry is assumed to be
  backward compatible. The historical note calling that entry shape locked is in
  a Deprecated spec, existing consumers read fields by name, and this change adds
  rather than renames or removes.
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
- ~~The ADR governance gap described in section 1 is assumed to be resolved by
  the owner before implementation begins.~~ Resolved 2026-08-06. It was closed
  by an `adr042-governance-amendment` block in ADR-034's body, not by an
  addendum file, and `related_adrs` narrowed to `[34]`. Section 1 records why
  each of those was necessary rather than stylistic.
- ~~`src/scistudio/ai/agent/providers_registry.py` and
  `frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx` are
  declared under `planned_governs` because they do not exist yet.~~ Both exist
  and have moved to `governs.files`; `planned_governs` is empty.
- The three module-private names this spec discusses by name —
  `_VALID_PROVIDERS`, `_PROVIDER_SPAWNERS`, and `_spawn` — are deliberately not
  listed in `governs.contracts`. They are internal implementation details rather
  than public contracts, and underscore-prefixed names do not resolve in the
  generated symbol facts the closure audit checks against.
- Existing workflow YAML using `provider: claude-code` remains valid; enum
  widening is backward compatible and no migration is required.
