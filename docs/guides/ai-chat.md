# AI Chat in SciEasy — User Guide

> **Audience**: scientists using SciEasy to build, run, and reason about
> multimodal data workflows.
> **You need**: a SciEasy installation, a free Anthropic or OpenAI account,
> and about five minutes for the first-time setup.
> **You will learn**: how to install the embedded coding agent, log it in,
> have your first conversation with it, control what it is allowed to do, and
> tailor its behaviour to your project.

---

## 1. What the embedded coding agent is

SciEasy ships with an **AI Chat tab** in the bottom panel. Behind that chat
panel is a real, multi-turn, tool-using coding agent — Claude Code or
OpenAI Codex — running locally on your machine as a subprocess of SciEasy.
You ask the agent a question in plain English ("Why is my Raman peak
fit failing on sample 7?"); the agent reads the relevant blocks and
data in your project, reasons about them, edits files if you give it
permission, runs the workflow if you give it permission, and reports
back with the answer and the diff.

The agent is **not** a chatbot that hallucinates code: it has direct
access to SciEasy's block registry, type system, workflow validator, and
data layer through the SciEasy MCP server. So when it edits a block, it
sees the same port-type errors and lineage constraints you would see in
the GUI.

SciEasy itself does not maintain an agent loop, an OAuth flow, a prompt
cache, or model weights. Those concerns are delegated to the upstream
coding agent CLI (Claude Code or Codex). This means:

- You bring your own model subscription (Claude Pro, ChatGPT Plus, or an
  API key) and pay for it directly to Anthropic or OpenAI.
- The model never sees your data unless you let the agent read it.
- The agent never modifies your project unless you approve the change.

The architectural decision is recorded in [ADR-033][adr-033].

[adr-033]: ../adr/ADR-033-draft.md

---

## 2. Install the coding agent CLI

You only need to install **one** of the two CLIs. If you install both,
SciEasy lets you switch between them per chat session via a "Provider"
dropdown.

### 2.1 Install Claude Code (recommended)

Claude Code is Anthropic's official CLI for Claude. It supports
multi-turn sessions, MCP servers, and the `PreToolUse` hook that
SciEasy uses for permission gating.

```bash
npm install -g @anthropic-ai/claude-code
```

Verify the install:

```bash
claude --version
```

If you see a version number printed, you're done. If `npm` is not on
your `PATH`, install Node.js first from [nodejs.org][node]. SciEasy also
searches a long list of fallback locations (`~/.local/bin`, `$NVM_BIN`,
`$PNPM_HOME`, `~/.nvm/versions/node/*/bin/`, `npm root -g`, the Windows
registry user/system `Path` keys) so you usually don't have to manage
`PATH` manually.

[node]: https://nodejs.org

### 2.2 Install Codex (alternative)

The OpenAI Codex CLI is an alternative to Claude Code. Installation
varies by platform; the canonical instructions live at
<https://github.com/openai/codex>. The flag surface and event format
that SciEasy expects from Codex are documented in
[`docs/specs/eca-spike-codex-format.md`][spike].

SciEasy uses Codex through `codex exec --json` and resumes later turns
with `codex exec --json ... resume <thread_id> -`. Unlike Claude Code,
Codex is spawned once per user turn rather than held open as one
long-running stdin session.

[spike]: ../specs/eca-spike-codex-format.md

Verify the install:

```bash
codex --version
```

### 2.3 What if neither is installed?

SciEasy will still start. The AI Chat tab shows a banner reading
"No coding agent installed" with a link back to this guide. The rest of
SciEasy — workflow editing, block running, data inspection — works
unchanged.

---

## 3. Log in

Once the CLI is installed, log it in.

### 3.1 Claude Code

```bash
claude /login
```

This opens a browser to the Anthropic OAuth flow. Pick your Anthropic
account, accept the scope request, and close the browser when prompted.
Your credentials live in `~/.claude/` on POSIX or `%USERPROFILE%\.claude\`
on Windows. SciEasy never reads them directly.

To check that you're logged in:

```bash
claude config get -g installMethod
```

If the command prints a non-empty value (for example, `npm-global`),
SciEasy considers you logged in. SciEasy's `GET /api/ai/status` route
will surface `logged_in: true` and the AI Chat tab will lift its login
banner.

### 3.2 Codex

```bash
codex login
```

Codex's login flow is documented at <https://github.com/openai/codex>.
SciEasy checks login state with `codex login status`. If your version of
Codex does not implement that subcommand, SciEasy will mark you as
"not logged in" — that's a SciEasy-side heuristic, not a real failure;
you can still attempt to start a chat and Codex itself will tell you
whether the session opens.

---

## 4. Basic usage

### 4.1 Open the chat tab

1. Launch SciEasy: `scieasy serve` (or `scieasy gui` if you want it to
   open a browser window automatically).
2. Open <http://localhost:8000> in your browser.
3. Open a SciEasy project (or create a new one).
4. Click the **AI Chat** tab in the bottom panel.

The chat tab shows:

- A status row at the top: which provider is selected ("Claude Code"
  or "Codex"), whether the binary is installed, whether you're logged
  in, and which model is selected. If anything is wrong, the row turns
  amber and links you back here.
- A scrolling transcript of the current session.
- A multi-line input box at the bottom with a send button and a
  permission-mode toggle.

### 4.2 Have your first conversation

Type a question into the input box and press the send button (or
Ctrl/Cmd+Enter). For example:

> "Walk me through the workflow on canvas. What does each block do?"

The agent will read your workflow YAML, the block registry, and the
block source code, then explain the workflow step by step. You'll see:

- **Assistant text streaming**: the agent's reply appears word by word
  as it generates.
- **Tool-use cards**: small expandable cards saying "Read
  workflows/main.yaml" or "Read blocks/peak_finder.py". You can click
  them to see what the agent looked at.
- **Tool-result cards**: the agent's view of the tool output. These are
  collapsed by default — click to expand.
- **A "done" indicator** when the agent finishes its turn.

You can keep the conversation going. The agent remembers the previous
turn within the same chat session.

### 4.3 Ask the agent to do something

Try a follow-up like:

> "Add a bandpass filter block before the peak finder. Bandpass cutoff
> at 100–1000 cm⁻¹."

The agent will:

1. Search the block registry for a bandpass filter (or, if none exists,
   propose generating one).
2. Edit the workflow YAML to insert the new block.
3. Connect its ports correctly.
4. Validate the result.
5. Report what it did and what it would do next.

If you accept the proposed changes, click "Apply" on the workflow diff
card. SciEasy reloads the canvas with the new workflow.

### 4.4 Stop or cancel a turn

If the agent is taking too long or going in the wrong direction, click
the red **Stop** button next to the send button. SciEasy tree-kills the
agent subprocess and any child processes (e.g. a Bash command the agent
spawned). The transcript records the cancellation and the chat is ready
for your next message.

---

## 5. Permission policy

The agent can read anything in your project without asking, but every
**write-class** action (file edit, file create, bash command, web fetch,
or any MCP tool that mutates state) requires your approval. This is the
default and SciEasy calls it **STRICT** mode.

### 5.1 The permission prompt

When the agent wants to do something write-class, a card appears in the
transcript:

```
The agent wants to:    Edit blocks/peak_finder.py
Diff:
  -    threshold = 0.5
  +    threshold = 0.7

[ Allow once ]   [ Always allow Edit ]   [ Deny ]
```

- **Allow once** — approves this one call. The agent receives the tool
  result and continues.
- **Always allow Edit** — approves this call and silently approves any
  future `Edit` call within this chat session. Use sparingly.
- **Deny** — denies the call. The agent sees a "permission denied"
  result and typically explains what it would have done.

The card never times out by default. If you walk away, the agent waits
until you respond. (Administrators can configure a soft timeout under
`{project}/.scieasy/agent-settings.json`; the default is 5 minutes.)

### 5.2 What gets auto-approved

The following are read-only and never trigger a prompt:

- `Read`, `Glob`, `Grep`, `LS`, `WebSearch`.
- Any SciEasy MCP tool whose name starts with `inspect_`, `list_`,
  `get_`, or `search_`.

Everything else — `Edit`, `Write`, `Bash`, `WebFetch`, and any SciEasy
MCP tool that mutates state — requires explicit approval.

### 5.3 BYPASS mode

If you trust the agent and want to avoid every prompt — for example,
during a long autonomous task — flip the permission-mode toggle next to
the send button to **BYPASS**. While BYPASS is active:

- A persistent red banner shows at the top of the chat tab reading
  "BYPASS mode: all tool calls auto-approved".
- Every tool call is auto-approved without a prompt.
- The transcript still records every tool call, so you can review what
  happened after the fact.

BYPASS is a per-session setting. Closing and reopening a chat resets it
to STRICT.

### 5.4 Where the prompts come from

Technically, permission requests are surfaced through Claude Code's
`PreToolUse` hook. SciEasy ships a hook bridge — `scieasy hook-bridge`
— that the agent subprocess invokes before every tool call. The bridge
calls SciEasy's `/api/ai/permission-check` REST endpoint, which renders
the prompt in the GUI, waits for your answer, and tells the bridge to
allow or deny. The result is that you get a single, consistent
permission UX regardless of whether the underlying call is to a
Claude-native tool (`Edit`, `Bash`, …) or to a SciEasy MCP tool. The
hook protocol is documented in [`docs/specs/eca-spike-hook-protocol.md`][hook].

[hook]: ../specs/eca-spike-hook-protocol.md

---

## 6. Customising the system prompt

SciEasy composes the agent's system prompt in **three tiers**, each
overridable:

1. **Builtin** — shipped with SciEasy. Teaches the agent what SciEasy
   is, what blocks and ports are, where the data lives, and how the MCP
   tools are structured. You normally don't edit this.
2. **User-level override** — a Markdown file at
   `~/.scieasy/system-prompt.md`. Anything you put here applies to every
   SciEasy project on your machine. Use this for "always speak in
   metric units", "always cite ADR numbers", or general writing-style
   preferences.
3. **Project-level override** — a Markdown file at
   `{project}/.scieasy/system-prompt.md`. Anything you put here applies
   only to this project. Use this for project-specific block conventions,
   reference data locations, or domain glossaries.

The three tiers are concatenated in order: builtin → user → project.
Later tiers can refine but not delete earlier guidance.

### 6.1 Example: a project-level override

```markdown
# Project-specific guidance for the SRS microplastics project

- Reference samples live under `data/reference/`.
- Use Welch's t-test for between-group comparisons.
- The `MaskGenerator` block requires the cell-segmented mask be
  binary, not a label image — convert if needed.
```

Save as `{project}/.scieasy/system-prompt.md`. Restart the chat session
(close the tab and reopen) for the change to take effect.

### 6.2 Listing the active prompt

To see what the agent will actually receive on its next session, run:

```bash
scieasy ai prompt --project {project}
```

This prints the concatenated three-tier prompt to stdout so you can
audit it.

---

## 7. Project-local state

Everything the agent learns about your project — the conversation
transcript, your "always allow" decisions, custom skills, and project
memory — is stored under `{project}/.scieasy/`:

```
{project}/.scieasy/
├── sessions/                       # one JSON file per chat session
│   └── <chat_id>.json
├── transcripts/                    # full stream-json transcripts
│   └── <chat_id>.ndjson
├── system-prompt.md                # project-level prompt override
├── agent-settings.json             # per-project agent config
├── mcp.json                        # MCP server config (auto-generated)
└── memory/                         # long-term project memory
    └── *.md
```

All of this lives in the project directory, so:

- It travels with the project. You can hand the project to a colleague
  and they get the same agent context.
- It can be committed to git. Most users add `.scieasy/sessions/` and
  `.scieasy/transcripts/` to `.gitignore` (they contain conversation
  history) but commit `.scieasy/system-prompt.md`,
  `.scieasy/memory/`, and `.scieasy/agent-settings.json`.

---

## 8. Troubleshooting

### 8.1 "No coding agent installed"

SciEasy could not find a `claude` or `codex` binary on `PATH` or in any
fallback location. Reinstall per §2 above. If the binary is installed
but SciEasy still doesn't see it, run:

```bash
which claude    # POSIX
where.exe claude    # Windows
```

If the command prints a path, copy it. Then open
`{project}/.scieasy/agent-settings.json` and set:

```json
{ "binary_override": "/absolute/path/to/claude" }
```

Restart SciEasy. SciEasy will use the override directly without
searching `PATH`.

### 8.2 "Not logged in"

The binary is installed but SciEasy thinks you haven't authenticated.

- Claude Code: run `claude /login` and complete the OAuth flow.
- Codex: run `codex login`.

If you have logged in but SciEasy still shows "not logged in", the
login-state probe may be running against a stale shell that doesn't see
your credentials. Restart SciEasy. If the issue persists, file an
issue — the login probe is a heuristic and may need refinement for
your install.

### 8.3 Hook bridge fails / permission prompts never appear

The agent runs a tool call, the GUI shows nothing, and the transcript
shows "permission denied" with no explanation. This usually means the
hook bridge could not reach the SciEasy backend.

Check that:

1. `scieasy serve` is still running and listening on its configured
   port.
2. The `SCIEASY_CHAT_ID` and `SCIEASY_PROJECT_DIR` environment
   variables are being injected into the agent subprocess. SciEasy does
   this automatically (issue #723), but if you launched the agent
   yourself outside SciEasy, you have to set them by hand.
3. The hook config file at `{project}/.scieasy/hooks.json` exists and
   is valid JSON.

Logs from the hook bridge go to
`{project}/.scieasy/logs/hook-bridge.log`. Look for "could not reach
/api/ai/permission-check" or "no SCIEASY_CHAT_ID in env".

### 8.4 Session hangs

The agent stops producing output and never finishes its turn.

1. Click the red **Stop** button to cancel the session.
2. Open `{project}/.scieasy/transcripts/<chat_id>.ndjson` and look at
   the last few events.
3. If the last event is a `tool_use` with no matching `tool_result`,
   the agent was waiting on a tool call that never returned — likely a
   Bash command that itself hung. SciEasy's tree-kill on cancel should
   have released it, but if the child is still running, find it with
   `ps` or Task Manager and kill it manually.
4. If the last event is an `assistant_text_delta` and stops mid-word,
   the upstream model may have rate-limited or timed out. Wait a minute
   and try again. Check <https://status.anthropic.com> or
   <https://status.openai.com>.

### 8.5 GUI not refreshing after the agent edits files

The agent edited a workflow YAML or block file but the canvas still
shows the old version.

- Check the transcript: did the `Edit` tool call succeed? If yes, the
  file on disk is updated.
- Click the canvas refresh button (top right of the workflow editor).
- If still stale, hard-refresh the browser (Ctrl/Cmd+Shift+R) — the
  frontend caches the workflow definition.

### 8.6 "Permission denied" on every tool call

You're stuck approving the same tool over and over. Either:

- Click **Always allow X** the next time you approve, or
- Switch to BYPASS mode for the duration of the task (see §5.3),
  remembering to switch back to STRICT when you're done.

### 8.7 Getting more verbose logs

For deep debugging, set:

```bash
export SCIEASY_LOG_LEVEL=DEBUG
```

before starting `scieasy serve`. The agent subprocess's stderr is
captured to `{project}/.scieasy/logs/<chat_id>.stderr`. The SciEasy
backend's logs go to stdout / your terminal.

---

## 9. Where to go next

- **Architecture**: ADR-033 explains why we delegate to Claude Code /
  Codex instead of writing our own agent loop. See
  [`docs/adr/ADR-033-draft.md`][adr-033].
- **Spec**: the full spec for the embedded coding agent —
  including the MCP tool catalogue, the hook protocol, and the test
  acceptance criteria — lives at
  [`docs/specs/embedded-coding-agent-spec.md`][spec].
- **Codex stream format**: assumptions and follow-up questions about
  the Codex CLI live in [`docs/specs/eca-spike-codex-format.md`][spike].
- **Hook protocol**: the contract between SciEasy and Claude Code's
  `PreToolUse` hook lives in
  [`docs/specs/eca-spike-hook-protocol.md`][hook].
- **Issue tracker**: file bugs and feature requests at
  <https://github.com/zjzcpj/SciEasy/issues>. The umbrella issue for
  the embedded coding agent rollout is `#747`.

[spec]: ../specs/embedded-coding-agent-spec.md
