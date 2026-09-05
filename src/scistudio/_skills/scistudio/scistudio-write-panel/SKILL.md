---
name: scistudio-write-panel
description: |
  Use when the user wants a WINDOW ONTO DATA: something they look at or act in.
  A panel is a self-contained HTML document that renders one target type in the
  preview area or in an interactive block's pause ("show this spectrum as a
  chart", "let me drag a baseline region", "give me a picker for these pairs").
  A panel lives in ``<project>/panels/<panel_id>/`` and declares one of two
  capabilities: displaying, or producing.

  NOT for authoring a processing BLOCK — that is scistudio-write-block (a Python
  class under ``blocks/<name>.py`` that becomes a workflow node). NOT for a
  one-off preview figure from an output port — that is scistudio-write-plot.
  NOT for adding a node to a workflow YAML — that is scistudio-build-workflow.
  A panel never becomes a DAG node and never claims lineage.
---

# scistudio-write-panel

Author a panel: a **document**, not a module. This skill is the **task flow**;
the **contract** and the **worked patterns** live elsewhere — read them, do not
guess:

- **`.scistudio/agent-reference/panel-contract.md`** — the capability
  declaration, the message contract, the on-disk layout, the tiers and their
  shadowing order, registration per tier, and the statement whitelist a
  producing panel's emitted code must satisfy. This is the contract.
- **`.scistudio/agent-reference/data-types.md`** — what the data you are handed
  looks like for each target type.
- **Worked patterns:** call `mcp__scistudio__list_panel_examples` — pass
  `capability` to get just the kind you are writing — and read the example's
  `document_path`. The corpus carries a **displaying** panel and a
  **producing** one. `mcp__scistudio__read_panel_source` does the same for a
  *registered* panel, which is how you read a built-in before replacing it.
  Copy the shape they show; do not invent one the examples already have.

## The flow — five steps, in this order

1. **Decide the capability.** `displaying` renders the data and sends nothing
   back. `producing` also renders, and additionally emits a line of code the
   host inserts on the user's behalf (a picked region, a routing decision, a
   chosen pair). A producing panel satisfies a displaying request; a displaying
   panel cannot stand in for a producing one. Choose `displaying` unless the
   user is deciding something the panel has to send back.
2. **Choose the tier.** Author into the **project** tier
   (`<project>/panels/<panel_id>/`) unless the user asks for the panel across
   every project, which is the user tier. The core and package tiers are not
   yours to write. A project panel shadows a same-id panel in any higher tier —
   which is how a built-in panel gets replaced: copy it down, then edit.
3. **Write the document.** `mcp__scistudio__scaffold_panel` writes the
   directory: the declaration, a self-contained document with a working
   skeleton, and the harness. READ every `warnings[]` entry it returns, then
   edit the document. Everything the panel needs is inside the one file —
   no build step, no bundler, no import from the host page.
4. **Check it in the harness.** The scaffold ships a harness page that loads
   the document over representative data for the declared target types and
   stands in for the host side of the message contract. Open it in a browser:
   `harness_path` is a file you can open directly, and `harness_url` is the
   same page on the running GUI once the panel is registered (it is `null`
   when no GUI is reachable — use the path). Confirm it renders, and, for a
   producing panel, that the emission is captured and shown. Do not skip this:
   it is the only way you see your own work.
5. **Register it.** `mcp__scistudio__reload_panels` rebuilds the registry and
   returns the discovered panels with their tiers and capabilities, what it
   `added` and `removed`, what got `shadowed`, and its `diagnostics`. **Read
   the diagnostics.** A broken panel is a diagnostic there, never a failed
   reload — so a reload that "succeeded" while your panel is missing has
   already told you why.

## Mandatory rules

- Declare exactly one capability, and declare the target types you actually
  render. The registry rejects a declaration it cannot read, and the host
  refuses a panel that acts outside the capability it declared.
- One panel id per tier. A second declaration of the same id inside one tier is
  a discovery error, not a shadow.
- The document is self-contained. No cross-origin fetch, no import from the
  host page, no asset outside the panel's own directory.
- A producing panel's emitted code must satisfy the statement whitelist in
  `panel-contract.md`. Anything outside it is refused at the host, not at
  review time.
- Check in the harness before you tell the user it works.
- After `scaffold_panel`, read every `warnings[]`. After `reload_panels`, read
  the diagnostics and the `next_step`.

## Anti-patterns

- Writing an ES module against a host API. That form is retired; a panel is a
  document. If you are reaching for `export default`, you are following stale
  instructions — read `panel-contract.md`.
- Declaring `producing` for a panel that only displays, "to keep options open".
  The capability is what the host enforces, not a hint.
- Editing a core or package panel in place instead of copying it into the
  project tier and editing the copy.
- Telling the user the panel works without opening the harness.
- Skipping `reload_panels`, then wondering why the panel is not offered for the
  type.
- Reaching for a panel when the user wanted a figure (`scistudio-write-plot`) or
  a processing step (`scistudio-write-block`).
