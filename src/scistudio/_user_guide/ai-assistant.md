# The AI assistant

SciStudio has an AI assistant built in. There are two ways it shows up: the
**chat**, where you talk to an assistant about your project, and the **AI Agent
block**, where you put an AI step *inside* a workflow. Most users lean on the
chat heavily — it is the fastest way to get things done without memorizing the
API.

## Before you start: install a provider

SciStudio does not ship its own model. It drives one of two AI **providers**, and
you pick which one to use:

- **Claude Code** (Anthropic)
- **Codex** (OpenAI)

Both run as a small command-line tool (a "CLI") on your computer that SciStudio
talks to. You only need **one** to get going, but you can install both and choose
per chat or per AI Agent block. Install whichever you have an account for:

1. **Open the provider's official CLI install guide** to get its install command:
   - Claude Code — <https://code.claude.com/docs/en/quickstart#step-1-install-claude-code>
   - Codex — <https://developers.openai.com/codex/quickstart?setup=cli>
2. **Copy the install command** shown there.
3. **Paste it into a terminal and run it:**
   - **macOS / Linux:** open **Terminal** and paste the command.
   - **Windows:** open **PowerShell** and paste the command.

   (SciStudio also has an **embedded terminal** you can use for this.)
4. **Sign in** the first time, following the tool's own prompts (it opens a login
   in your browser).

Once a provider's CLI is installed and signed in, SciStudio detects it and the
chat and the AI Agent block can use it. If the assistant says no provider is
available, it means neither CLI is installed yet — come back here and install
one.

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
- **Provider** — which assistant runs it (`claude-code` or `codex`).
- **Permission mode** — *Ask* (the agent checks with you before sensitive
  actions) or *Bypass* (full access, no prompts).
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
