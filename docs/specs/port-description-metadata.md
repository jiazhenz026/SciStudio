---
spec_id: port-description-metadata
title: "Port Description Rendering In Right-Side Preview Pane"
status: Implemented
feature_branch: feat/ai-context-and-port-ux
created: 2026-05-23
input: "Issue #1326 — UX/spec: port behavior annotations in right-side preview pane (bundled with #1325 + #1488 in a single PR per owner direction 2026-05-23)."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs: []
scope:
  in:
    - Right-side preview pane gains a port-info sub-panel that renders descriptions for the selected block.
    - Per-row layout rules for author-defined, undefined, and user-added variadic ports.
    - Block-authoring guidance to populate `port.description` on new ports.
  out:
    - Schema or contract changes (none — `BlockPortResponse.description` already exists end-to-end).
    - Cursor / text-selection awareness in the AI chat.
    - Markdown or rich text in port descriptions (plain text only v1).
    - Validation logic driven by description content.
    - User-editable descriptions on author-defined ports (variadic ports only, per §5).
    - Hover-triggered display on the canvas.
governs:
  modules: []
  contracts:
    - scistudio.api.schemas.BlockPortResponse
  entry_points: []
  files:
    - docs/specs/port-description-metadata.md
  excludes: []
tests:
  - tests/api/test_block_schema_serialization.py
acceptance_source: issue
language_source: en
---

# Port Description Rendering In Right-Side Preview Pane

## 1. Change Summary

Closes the GUI gap surfaced in issue #1326: when a block has multiple
ports of the same data type (e.g. three `Image` inputs, two `Image`
outputs), users cannot tell from the canvas what each port's semantic
role is — the type pill alone is insufficient. This spec defines a new
port-info sub-panel under the right-side preview pane that renders the
per-port description text already carried by `BlockPortResponse`.

The companion issue #1325 (canvas "+" add-port button + variadic ports)
ships in the same PR; this spec defines how user-entered port names
from #1325 are rendered in the new sub-panel.

## 2. Schema — No Changes Needed

`scistudio.api.schemas.BlockPortResponse` already carries
`description: str = ""` (default empty). The backend route
`src/scistudio/api/routes/blocks.py` already populates it from the
block declaration via `getattr(port, "description", "")`. Multiple
built-in blocks already use this field
(`subworkflow_block.py`, `code_block.py`, `app_block.py`, etc.).

The schema field is therefore the **canonical port description
source** — authoritative, single-string, plain text — and no
schema or contract change is required to ship this feature.

## 3. Render Rules

The right-side preview pane is split horizontally:

- **Top half** — existing preview (unchanged).
- **Bottom half** — new port-info sub-panel, rendered when exactly one
  node is selected. Layout sketch (owner direction 2026-05-21 +
  2026-05-23):

```
Input Port:
  [icon] TypeName [— descriptive_text]
  [icon] TypeName [— descriptive_text]
Output Port:
  [icon] TypeName [— descriptive_text]
  [icon] TypeName [— descriptive_text]
```

Each row applies exactly one of three formats:

| Case | Row format |
|---|---|
| Author-defined port, `description` non-empty | `[icon] TypeName — description` |
| Author-defined port, `description` empty | `[icon] TypeName` |
| User-added variadic port (#1325) | `[icon] TypeName — <user-typed port name>` |

Field semantics:

- **`[icon]`** — type-color glyph matching the canvas / PortEditorTable
  convention. Reuse the existing per-type styling; do not invent a new
  visual.
- **`TypeName`** — the port's accepted-type display name (e.g.
  `Image`, `Data`). When `accepted_types` carries multiple entries,
  render the first type only in this row; the full type list is
  already exposed in the type pill, which remains unchanged.
- **`descriptive_text`** — plain text, ~140 character soft cap (no
  enforced limit; long strings wrap naturally).
- **Em-dash separator** — render ` — ` only when `descriptive_text`
  is non-empty.

## 4. Ordering And Trigger

- **Ordering**: declared order. The order in which `input_ports` /
  `output_ports` arrive in `BlockSchemaResponse` is preserved. Do not
  sort alphabetically.
- **Trigger**: visible whenever exactly one node is selected. No hover
  trigger.
- **Empty state — no node selected or multiple nodes selected**:
  sub-panel hidden.
- **Empty state — block has no input or no output ports**: the
  affected header (`Input Port:` / `Output Port:`) is hidden along
  with its empty row list.

## 5. Variadic Ports — Interaction With #1325

#1325 adds canvas "+" buttons that let users add ports at runtime on
variadic blocks (e.g. Code Block). For each user-added port the user
enters a port name in the add-port dialog (and may later edit it via
PortEditorTable). This spec treats that user-entered name as the
descriptive text in the preview-pane port row.

There is no per-port `description` field on user-added ports in v1;
the user-entered name **is** the description text for rendering
purposes. The PortEditorTable does not gain a separate description
column in this PR.

## 6. Block-Authoring Guidance

Authors of new and updated blocks should populate `description=` on
each `InputPort` / `OutputPort` declaration. Several built-in blocks
already follow this pattern; the rest gain descriptions
opportunistically as authors revisit them.

Recommended phrasing: one short sentence describing the port's
semantic role (e.g. `"Input to child workflow"`,
`"Output artifacts from the app"`). Do not duplicate the type
information already shown via the icon and type name.

## 7. Out Of Scope

- Schema or contract changes (none required).
- Markdown, rich text, or hyperlinks in description content.
- Validation hints driven by description content.
- User-editable descriptions on author-defined ports.
- Hover behaviour or tooltip rendering on the canvas itself.
- Sorting / filtering controls in the sub-panel.
- Inline editing of descriptions in the preview pane.
- Multi-port selection across blocks.

## 8. Test Plan

**Frontend unit tests** (new):
- Render row with non-empty `description` → expected `[icon] TypeName — description` markup.
- Render row with empty `description` → expected `[icon] TypeName` markup, no em-dash.
- Render row for user-added variadic port → user-typed name substitutes description.
- Empty-state behaviour: panel hidden when no node selected; headers hidden when port list empty.

**Backend regression** (existing path, ensure no drift):
- `BlockPortResponse` serialization preserves the `description` field
  for blocks that set it (covered by current API schema tests; verify
  the path stays green).

**Manual smoke** (recorded in PR description):
- Open a workflow containing `code_block` and `subworkflow_block`.
- Select each node in turn; confirm the panel shows the descriptions
  authored in `code_block.py` / `subworkflow_block.py`.
- For a variadic Code Block, use #1325's "+" button to add a new port
  named `my_image`; confirm the panel renders
  `[icon] Image — my_image`.
