# The AI assistant

SciStudio has an AI assistant built in. There are two ways it shows up: the
**chat**, where you talk to an assistant about your project, and the **AI Agent
block**, where you put an AI step *inside* a workflow. Most users lean on the
chat heavily — it is the fastest way to get things done without memorizing the
API.

## Before you start: install a provider

SciStudio does not ship its own model. It drives an AI **provider** — a small
command-line tool (a "CLI") that runs on your computer and that SciStudio talks
to. Five are supported:

| Provider | Who makes it | Works in chat | Works in an AI Agent block |
|---|---|---|---|
| **Claude Code** | Anthropic | yes | yes |
| **Codex** | OpenAI | yes | yes |
| **Kimi Code** | Moonshot AI | yes | **no** — see below |
| **Qoder CLI** | Qoder (international) | yes | yes |
| **Qoder CLI (China)** | Qoder (China) | yes | yes |

Kimi Code has one further difference worth knowing before you pick it: SciStudio's
safety hooks cannot be installed into a Kimi Code chat. See
[Kimi Code chats run without SciStudio's hooks](#kimi-code-chats-run-without-scistudios-hooks).

You only need **one** to get going, but you can install several and choose per
chat or per AI Agent block. Install whichever you have an account for:

1. **Open the provider's official CLI install guide** to get its install command:
   - Claude Code — <https://code.claude.com/docs/en/quickstart#step-1-install-claude-code>
   - Codex — <https://learn.chatgpt.com/codex/cli>
   - Kimi Code — <https://www.kimi.com/code/docs/en/kimi-code-cli/guides/getting-started.html>
   - Qoder CLI — <https://docs.qoder.com/cli/installation>
   - Qoder CLI (China) — <https://docs.qoder.cn/cli/qoder-cli-cn-get-started-quickly>
2. **Copy the install command** shown there.
3. **Paste it into a terminal and run it:**
   - **macOS / Linux:** open **Terminal** and paste the command.
   - **Windows:** open **PowerShell** and paste the command.

   (SciStudio also has an **embedded terminal** you can use for this.)
4. **Sign in** the first time, following the tool's own prompts (it opens a login
   in your browser).

Once a provider's CLI is installed and signed in, SciStudio detects it and the
chat and the AI Agent block can use it.

### The two Qoder CLIs are separate products

Qoder ships an international CLI and a China CLI. They are **not** the same
install and not the same account: different download, different sign-in,
different available models. SciStudio treats them as two separate providers, so:

- Installing one does **not** make the other appear. If you install the China
  CLI, **Qoder CLI** stays greyed out as *(not installed)* — that is expected,
  not a detection bug.
- If you have both, they appear as two entries and you choose per chat. A chat
  started on one never falls back to the other.

### Kimi Code works in chat, not in an AI Agent block

Kimi Code is fully supported as a **chat** provider. It cannot be used as the
provider for an **AI Agent block**, and the block will tell you so when you try.

The reason is in the CLI itself: `kimi` accepts no task as a plain argument, so
an AI Agent block has no way to hand it the job it is supposed to do. Its one
prompt option runs a single prompt, prints an answer, and exits — which is not
the ongoing session a block needs in order to work through your inputs and write
its outputs. Use Kimi Code for chat and pick another provider for AI Agent
blocks.

### If no provider is installed

The chat's setup screen shows a notice naming every supported agent and telling
you to install one. Once you have installed and signed in to a CLI, reopen the
setup screen and the normal provider picker replaces the notice — no restart
needed.

The picker always lists **all five** providers, so you can see what is
supported. Ones you have not installed appear greyed out and marked
*(not installed)*; ones installed but not signed in are still selectable and
marked *(not logged in)*, so you can launch them and complete the sign-in inside
the terminal.

### First launch with Codex: answer the hook-trust prompt

SciStudio installs its own **hooks** into your project — small scripts that add
data protection and keep tool use in bounds. Codex asks you to approve any hook
configuration it has not seen before, so the first time you launch a Codex chat
in a project, it stops with a menu like this:

```
Hooks need review
10 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.
› 1. Review hooks
  2. Trust all and continue
  3. Continue without trusting (hooks won't run)
```

This is Codex working as designed, and it is a one-time step per project. Answer
it in the terminal with the arrow keys and Enter. Choose **Review hooks** to read
them first, or **Trust all and continue** to accept them.

Until you answer, SciStudio's hooks are inactive — that is what option 3's
"hooks won't run" means. If you picked option 3 and later wonder why the
protections seem silent, that is the cause; the prompt returns when the hook
configuration next changes.

### Kimi Code chats run without SciStudio's hooks

The hooks described just above are installed **into your project**, and every
provider except Kimi Code picks them up from there. Kimi Code reads hooks only
from its own settings file in your home directory, so there is nowhere in the
project for SciStudio to put them. A Kimi Code chat therefore runs without
them: the guard that stops accidental edits to your `data/` folder and your
workflow files is simply not active in that tab.

SciStudio does not edit that file for you. It is your personal settings file,
shared by every project you open with Kimi Code, and changing it on your behalf
would reach far outside the project you are working in.

You can add the hooks yourself if you want them. The easiest way is to ask Kimi
in the chat itself — something like *"add the hook scripts in this project's
`.claude/hooks/` folder to my Kimi config as PreToolUse and PostToolUse hooks"* —
since it can read the scripts and edit its own configuration. The scripts work
with Kimi Code as-is; nothing needs to be rewritten. Remember that hooks added
this way apply to **every** Kimi Code session on your computer, not only this
project.

Everything else — the SciStudio tools, the skills, and the project knowledge the
assistant works from — is unaffected and works normally in a Kimi Code chat.

## The chat assistant

Open the AI chat panel and describe what you want in plain language. The
assistant works **inside your project** — it can see your workflows, your data,
your blocks, and your run results — so it acts, not just advises. What it is good
for:

- **Answering SciStudio questions.** "What block loads a CSV?" "Why did my run
  fail?" "What types can connect to this port?" It knows the app and your
  project.
- **Building workflows.** Describe a pipeline — "load these files, baseline-
  correct, find peaks, save a table" — and it assembles and wires the blocks for
  you, with valid types and parameters.
- **Writing blocks and plots.** "Write a block that normalizes each spectrum to
  its max" or "plot the peak table as a bar chart." It writes the code against
  the public API and the canonical imports, so you do not have to (see
  [writing-blocks.md](writing-blocks.md), [writing-plots.md](writing-plots.md)).
- **Checking your data.** Ask it to look at a port, sanity-check a table, find
  outliers, or confirm two batches line up — it inspects bounded previews
  without loading everything into memory.
- **Iterating for you.** "Try sigma from 1 to 5 and tell me which gives the
  cleanest baseline." It can run the workflow, read the results, adjust a
  parameter, and run again — the tuning loop you would otherwise do by hand.

You stay in control: you review what it proposes and run it. Think of it as a
collaborator who knows the tool and your project, not an autopilot.

## The AI Agent block

The chat helps you *build* a workflow. The **AI Agent** block puts AI *into* the
workflow as a step that runs every time the pipeline runs. Use it when part of
your processing is a judgment task that is hard to write as fixed code —
classifying, summarizing, extracting, or inferring something from messy inputs.

Add the **AI Agent** block from the palette like any other block. Its parameter
panel has:

- **User prompt** — the task, in plain language.
- **Provider** — which assistant runs it: `claude-code`, `codex`, `qoder`, or
  `qoder-cn`. `kimi-code` is not available here; see
  [Kimi Code works in chat, not in an AI Agent block](#kimi-code-works-in-chat-not-in-an-ai-agent-block).
- **Permission mode** — **Manual Approve** (the agent asks you before doing
  anything sensitive) or **Bypass Permission** (it runs unattended with full
  access and never asks).
- **Input / output ports** — you declare these in the port editor: name each
  port and give it a type. Inputs are handed to the agent as files; for each
  output you say where the agent should write its result and what type it is.

At run time the block spawns the agent in a terminal tab, hands it your inputs,
and waits until it has produced the declared output files — which SciStudio then
loads back as ordinary typed data for the next block. From the workflow's point
of view it is just another block with typed ports.

### Example: infer a metadata table from raw data

A common, genuinely useful job: you have a pile of raw data files and you want a
tidy **metadata table** — one row per sample, with columns like sample id,
experimental condition, and instrument — inferred from the files themselves.
That is awkward to write as fixed code (every dataset is messy in its own way)
and a perfect fit for an AI Agent block.

Set it up like this:

- **Input port** `data_files`, type `Artifact` — wire your raw files in (e.g.
  from a Load block producing file artifacts).
- **Output port** `metadata`, type `DataFrame`, with an expected path such as
  `./metadata.csv`.
- **User prompt**, something like:

  > You are given several experimental data files. Inspect each one and build a
  > metadata table with one row per sample and the columns: `sample`,
  > `condition`, `instrument`, `source_file`. Infer values from the file
  > contents and names; leave a cell blank if you cannot determine it. Write the
  > table to `./metadata.csv`.

When the workflow runs, the agent reads each input file, works out the metadata,
and writes `metadata.csv`. SciStudio loads that file back as a `DataFrame` on the
`metadata` port, ready to drive the rest of the pipeline — join it to your
measurements, filter by condition, group by sample. The AI did the messy
inference; the workflow stays typed and reproducible around it.

## Next

- [using-the-gui.md](using-the-gui.md) — where the chat and the AI Agent block fit
- [built-in-blocks.md](built-in-blocks.md) — the AI Agent block alongside the
  other built-ins
