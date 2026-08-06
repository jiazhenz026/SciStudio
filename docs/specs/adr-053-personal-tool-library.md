---
spec_id: adr-053-personal-tool-library
title: "ADR-053 Personal Tool Library — Block And Type Tiers, Promotion, And The Data Types Tab"
status: Draft
feature_branch: guided/personal-tool-library-spec
created: 2026-08-06
input: "Owner-directed live session (guided): author the personal tool library spec for ADR-053 §3. Make the user tier a visible place in the product for both blocks and types, give it write entry points, add a Data types tab beside Blocks, add a GUI path for creating custom types, fix the drop-in import defect that currently prevents a block from referencing a project-local custom type, and consolidate the four diverging drop-in registration points so block and type lifecycles behave identically in every process."
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
  - 50
  - 52
  - 53
related_specs:
  - frontend-block-palette
scope:
  in:
    - Splitting the collapsed tier-1 block origin into distinct user and project origins, with a fallback for unresolvable paths.
    - A write path into the user-wide library (`~/.scistudio/blocks/`, `~/.scistudio/types/`) for both blocks and types, with collision prompting.
    - Five promotion entry points - source editor, canvas node menu, agent (MCP), the new-file target choice, and the palette hover popover.
    - Cascade promotion - carrying the project-level custom types a promoted block depends on.
    - Fixing the drop-in import defect that prevents a drop-in block from importing a drop-in type from `{project}/types/` or `~/.scistudio/types/`.
    - Aligning user-tier block discovery with type discovery so it no longer requires an active project.
    - Renaming the left palette tab to Blocks and adding a third Data types tab between Blocks and Project.
    - A types listing API carrying origin tier, file path, declared colours, and supported file extensions, plus a type template endpoint.
    - A GUI action for creating a new custom data type from a template, mirroring New custom block.
    - Backend-declared type colours on DataObject, completing the dead `TypeHierarchyEntry.ui_ring_color` field and mirroring the block `ui_color` / `ui_icon` precedent.
    - Per-type load/save file extensions derived from registered format capabilities.
    - Type tiles coloured with the canvas port palette (solid fill plus ring) and a type hover popover showing description, parent class, and supported extensions.
    - Extracting shared helpers between the Blocks and Types surfaces to prevent drift.
    - Consolidating the four independent drop-in registration points (API, agent, worker, IO dispatch) into one shared provisioning helper.
    - Registering project-level and user-level type directories in the agent runtime, which registers none today.
    - Reload symmetry — package install/uninstall and branch switch refresh the type registry, not only the block registry.
  out:
    - A user tier for previewers. Previewers keep core / package / project discovery only; `OwnerKind` is unchanged.
    - The palette tips strip (#1997), which moves to the Learning Center spec because it teaches features unrelated to the library.
    - Learning Center entries, the tutorial registry, progress, and first-run landing (the Learning Center system spec).
    - Codebase import, agent transcription, and differential tests (the import spec).
    - Any change to block discovery tier semantics themselves, the registry data model, or type serialization.
    - Sandboxing drop-in execution (deferred by #1531 and unchanged here).
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-053-personal-tool-library.md
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
planned_governs:
  modules:
    - scistudio.api.routes.types
  contracts: []
  entry_points: []
  files:
    - src/scistudio/api/routes/types.py
    - frontend/src/components/TypePalette.tsx
  excludes: []
tests:
  - tests/api/test_block_origin_tiers.py
  - tests/api/test_user_library_write.py
  - tests/api/test_types_routes.py
  - tests/blocks/test_dropin_type_import.py
  - tests/api/test_registry_provisioning_parity.py
  - tests/api/test_registry_reload_symmetry.py
  - frontend/src/components/BlockPalette.parts/__tests__/paletteModel.test.ts
  - frontend/src/components/__tests__/TypePalette.test.tsx
acceptance_source: adr
language_source: en
---

# ADR-053 Personal Tool Library — Block And Type Tiers, Promotion, And The Data Types Tab

## 1. Change Summary

ADR-053 §3 argues that users do not build reusable tool libraries because there
is no container to build one in: the user tier of the block library exists on
disk, works, and is invisible. This spec is the implementation contract for
making that tier a place in the product.

The work has four parts. The **backend** learns to tell the user tier apart from
the project tier and gains a write path into it — today no code in the product
can put a file there. The **palette** stops calling both tiers `Custom` and
names them, rendering both even when empty. A **promotion action** appears at
five points where a user is already looking at a block or a type. And a **Data
types tab** joins Blocks in the left panel, so custom data types get the same
visibility blocks are getting — with a hover card that answers what a type is,
what it descends from, and which file formats it can be read from and written
to.

Types also gain the ability to declare their own colour. Blocks have had this
since #1839; the equivalent field for types was declared on the API schema and
never populated, so every type colour in the product is currently decided by a
frontend hash. §7.1 connects it.

One defect is fixed along the way rather than deferred. A drop-in block cannot
currently import a drop-in type from `{project}/types/` — the import raises and
the block is silently skipped, so it never appears in the palette at all. This
was verified by direct reproduction (§2.5). It is fixed here because cascade
promotion is meaningless without it: there is no point carrying a block's type
dependencies across projects when a block cannot express such a dependency in
the first place.

Underneath all of it, the block and type lifecycles are made symmetric. The
same question — which drop-in directories does this process see — is currently
answered in four places that disagree (§2.6): the agent registers no type
directories at all, package installs refresh blocks but not types, and the two
registries scan in opposite orders. Every feature above would otherwise behave
differently depending on which process the user's action ran in, so §10.3 and
§10.4 consolidate this first and everything else is built on top.

Previewers are deliberately excluded. They keep core / package / project
discovery; `OwnerKind` is not extended. The tips strip (#1997) moves to the
Learning Center spec.

## 2. Current State

Every statement in this section was verified against the tree at `6579d9ce`.
The design in §3 onward depends on these being accurate.

### 2.1 The Three Tiers Exist And Discovery Reads Them

Blocks and types both support a user-wide drop-in directory and a project-local
one. `refresh_block_registry` and `refresh_type_registry`
(`src/scistudio/api/runtime/_projects.py`) register the scan directories; the
registries walk them and register any `Block` / `DataObject` subclass found in
a loose `.py` file.

### 2.2 The API Collapses The Two Tiers

`map_block_origin` (`src/scistudio/api/_block_source.py:23`) maps the internal
`tier1` label to a single `custom` origin:

```python
if raw == "tier1":
    return "custom"
```

Both `~/.scistudio/blocks/` and `{project}/blocks/` therefore arrive at the
frontend indistinguishable. `buildPaletteSections`
(`frontend/src/components/BlockPalette.parts/paletteModel.ts`) renders them as
one `Custom` section, ordered `Data I/O (pinned) → Built-in → Custom → plugin
packages A→Z`. There is no empty state: when the user owns no custom blocks the
section does not render, so a user who has never heard of a personal library
never sees the place it would live.

The registry spec already carries the concrete `file_path` used by
`resolve_block_source`, so separating the tiers is a path comparison and needs
no data model change.

### 2.3 There Is No Write Path

The only file-write endpoint is `PUT /api/projects/{project_id}/file`
(`src/scistudio/api/routes/projects.py:286`), and it rejects any path that
resolves outside the project root with a 403. The user library sits outside
every project root by construction, so this endpoint cannot serve it. Nothing
else in the product writes to `~/.scistudio/blocks/` or `~/.scistudio/types/`.
Reaching those directories today requires a file manager.

### 2.4 User-Tier Block Discovery Requires An Active Project; Type Discovery Does Not

The two registries treat the user tier differently. In
`refresh_type_registry` the user-wide scan directory is registered
unconditionally, while the project-local one is gated on an active project. In
`refresh_block_registry` **both** are gated:

```python
# refresh_type_registry
if self.active_project is not None:
    registry.add_scan_dir(Path(self.active_project.path) / "types")
registry.add_scan_dir(Path.home() / ".scistudio" / "types")   # unconditional

# refresh_block_registry
if self.active_project is not None:
    registry.add_scan_dir(Path(self.active_project.path) / "blocks")
    registry.add_scan_dir(Path.home() / ".scistudio" / "blocks")   # also gated
```

The difference is deliberate and appears in two places: `_scan_runtime_registry`
(`src/scistudio/blocks/io/_unified_dispatch.py`) is called with
`always_home=True` for types and `always_home=False` for blocks. The likely
original reason is that a type class may be needed without any project open —
artifact deserialization requires one, and
`scistudio/core/types/serialization.py` also adds the home types directory
unconditionally — whereas a block was only ever meaningful inside a project.

The consequence today is that with no project open, `~/.scistudio/types/` loads
and `~/.scistudio/blocks/` does not.

### 2.5 A Drop-In Block Cannot Import A Drop-In Type — Verified Defect

**This is a bug, not a design boundary.** `ARCHITECTURE.md` presents
`{project}/blocks/` and `{project}/types/` as companion project-level extension
points ("blocks and types cover code a user reuses across projects"), so a
custom type feeding a custom block is the natural expectation. It does not work.

Three facts combine to break it:

1. `accepted_types: list[type]` (`src/scistudio/blocks/base/ports.py:23`) holds
   real class objects, not names. A block declaring a port of a custom type must
   have imported that class.
2. When a drop-in block module is executed
   (`src/scistudio/blocks/registry/_scan.py:189`), the only paths prepended are
   `_desktop_user_python_import_roots()`, which resolves to
   `user_python_import_roots()` (`src/scistudio/desktop/paths.py:125`) — the
   user site directory for third-party dependencies. No types directory is ever
   on `sys.path`. The same value is stored as
   `block_spec.runtime_import_roots` for the worker, so the worker side is
   identical.
3. A drop-in type is loaded under a synthetic module name
   `_scistudio_type_dropin_{stem}_{mtime}_{path_hash}`. That name exists in
   `sys.modules` (the #1343 fix, so `TypeRegistry.load_class` can import it) but
   it is not the file's own name, so it cannot satisfy `import spectrum`.

Reproduction — `{project}/types/spectrum.py` defines `SpectrumData(DataObject)`,
`{project}/blocks/uses_spectrum.py` does `from spectrum import SpectrumData` and
declares it on both ports, scanned in the same order `ApiRuntime` uses:

```
=== TypeRegistry ===
SpectrumData registered: True
  module_path: _scistudio_type_dropin_spectrum_1786054247_c95eff17
  in sys.modules: True
=== BlockRegistry ===
registered block types: ['Load', 'Save', 'AI Agent', ...]
uses_spectrum present: False
```

```
Failed to import block from ...\blocks\uses_spectrum.py: drop-in module raised
during import; skipping (it contributes no blocks).
    from spectrum import SpectrumData
ModuleNotFoundError: No module named 'spectrum'
```

**The failure is silent.** The block does not appear, nothing surfaces in the
UI, and the only trace is a server-side warning. The user's experience is that
their block vanished.

### 2.6 Drop-In Directories Are Registered In Four Places, All Differently

The same semantic — "which drop-in directories does this process see?" — is
written out four times, and no two agree.

| Registration point | Blocks | Types |
|---|---|---|
| `src/scistudio/api/runtime/_projects.py` (API) | project and user, **both** gated on an active project | project gated, user **unconditional** |
| `src/scistudio/ai/agent/mcp/runtime.py` (agent) | project and user, user **unconditional** | **no scan directory at all** |
| `src/scistudio/core/types/serialization.py` (worker reconstruction) | — | project and user, read from `SCISTUDIO_PROJECT_DIR` |
| `src/scistudio/blocks/io/_unified_dispatch.py` (IO dispatch) | `always_home=False` | `always_home=True` |

The comment at `src/scistudio/core/types/serialization.py:106` states its intent
as registering "the same scan dirs `ApiRuntime.refresh_type_registry` wires" —
the synchronisation is maintained by a comment, which is the drift this spec
exists to remove.

Three consequences matter to the work in this spec.

**The agent sees no drop-in types.** `_build_type_registry()` constructs a
registry and calls `scan_all()` without registering any directory:

```python
def _build_type_registry() -> TypeRegistry:
    """Scan builtin + entry-point plugin types."""
    registry = TypeRegistry()
    registry.scan_all()      # no add_scan_dir
    return registry
```

So in the agent process neither `{project}/types/` nor `~/.scistudio/types/` is
registered, while blocks from both tiers are. Promotion by agent (FR-011) and
the dependency detection cascade needs (FR-022) would both resolve against an
empty view of the user's types.

**Reload refreshes blocks but not types.** `refresh_block_registry` is called on
its own from five sites — branch switch (`src/scistudio/api/routes/git.py:493`)
and package install/uninstall (`src/scistudio/api/routes/packages.py`, four
call sites). `refresh_type_registry` is called only on project switch and at
startup. Installing a package that ships custom types therefore leaves the type
registry stale until the next project switch.

**The scan order is inverted.** `BlockRegistry.scan()` runs builtins → drop-in →
entry-point → package-src; `TypeRegistry.scan_all()` runs builtins →
entry-point → package-src → drop-in. Both document "entry-point registrations
win on duplicates", but one achieves it by registering entry-points later and
the other by skipping names already present. The observable precedence matches;
the code paths are opposites.

### 2.7 Type Data Reaches The Frontend, But Only As A Passenger

There is no types endpoint: `listTypes` and `/api/types` do not exist on the
frontend. Type information reaches it as `type_hierarchy` on the **block list
response** (`src/scistudio/api/routes/blocks.py:387`,
`src/scistudio/api/schemas.py:221`), with fields
`{name, base_type, description, ui_ring_color}`.

That payload has no origin tier and no `file_path`, so it can support neither
tier grouping nor a promotion action.

### 2.8 Colour Resolution Is Frontend-Only, And The Backend Hook Is Dead

`frontend/src/config/typeColorMap.ts` provides `resolveTypeColor()` (solid fill)
and `resolveRingColor()` (ring), used by the canvas port handles
(`frontend/src/components/nodes/BlockNode.parts/PortHandles.tsx`). Core types
carry hand-assigned colours; unknown and plugin types fall back to a
deterministic `hashTypeName` lookup into a 20-hue palette, with the ring derived
as `darkenHex(base, 0.3)`. The solid-plus-ring treatment this spec requires for
type tiles is therefore already implemented.

A type cannot currently influence its own colour. `TypeHierarchyEntry` carries a
`ui_ring_color` field (`src/scistudio/api/schemas.py:162`) but **nothing ever
populates it** — the construction site (`src/scistudio/api/routes/blocks.py:387`)
passes only `name`, `base_type`, and `description`, so it is always `None` and
`resolveRingColor`'s backend branch is dead code. Every type colour in the
product is decided frontend-side.

Blocks already have the mechanism types lack. `BlockSummary.ui_color` and
`ui_icon` (#1839) let a block declare its canvas appearance, and the schema
comment at `src/scistudio/api/schemas.py:177` describes them as mirroring "the
`TypeHierarchyEntry.ui_ring_color` precedent for ports" — a precedent that was
never wired up. §7.1 completes it.

### 2.9 Format Capabilities Already Record Type-To-Extension Mapping

`FormatCapability` (`src/scistudio/blocks/io/capabilities.py:267`) records one
conversion as `{data_type, format_id, extensions, direction, label, ...}`, and
`registry.list_format_capabilities(direction=...)` enumerates them —
`io_capable_type_names` (`src/scistudio/blocks/io/_config_enrichment.py:28`)
already groups by `capability.data_type.__name__`. The extensions a given type
can be loaded from or saved to are therefore derivable today; nothing exposes
them per type.

### 2.10 The Hover Popover Is Non-Interactive

`BlockDetailPopover` is rendered with `pointer-events-none`
(`frontend/src/components/BlockDetailPopover.tsx:35`) and its visibility is
driven entirely by the tile: `handleTileEnter` opens it after
`POPOVER_OPEN_DELAY_MS` and `clearHover` closes it
(`frontend/src/components/BlockPalette.tsx`). A button placed inside it today
cannot be clicked, and the popover would close before the pointer reached it.

### 2.11 New Custom Block Is A Complete Template Flow

`createNewCustomBlock` (`frontend/src/App.parts/useProjectActions.ts:280`)
prompts for a filename, validates it as a Python identifier, probes for
collision via `probeProjectFileExistence`, fetches
`GET /api/blocks/template?kind=basic`
(`src/scistudio/api/routes/blocks.py:340`), writes through `putProjectFile`, and
opens the file. It is exposed from the toolbar
(`frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx:84`). No
equivalent exists for types.

### 2.12 Left Panel Tabs

`leftTab` is typed `"blocks" | "project"` in `frontend/src/App.tsx:214` and
`frontend/src/App.parts/ProjectWorkspace.tsx:52`.

## 3. Block And Type Origin Tiers

**FR-001.** `map_block_origin` MUST resolve a `tier1` block to `user` when its
`file_path` is under the user-wide blocks root, and to `project` when it is
under the active project's blocks directory.

**FR-002.** When the path cannot be resolved to either root — an absent
`file_path`, a symlink escaping both, a differing Windows drive — the origin
MUST fall back to `custom`. Behaviour degrades; it does not break. Existing
consumers of `custom` MUST continue to function.

**FR-003.** Origin resolution MUST be a single shared implementation used by
both the block and type surfaces (§10), not two path comparisons that can
diverge.

**FR-004.** The block list response MUST carry the resolved origin.

**FR-005.** The types listing response (§7) MUST carry the same origin
vocabulary: `core`, `user`, `project`, `package`, with `custom` as the same
fallback.

## 4. The User Library Write Path

**FR-006.** A new endpoint MUST accept writes into the user-wide library. It
MUST serve both targets — `~/.scistudio/blocks/` and `~/.scistudio/types/` —
selected explicitly by the caller, never inferred from file content.

**FR-007.** Its path constraint MUST be the inverse of the project endpoint's:
the resolved target MUST be inside the relevant user library root. Traversal
and symlink escapes MUST be rejected with 403, matching the existing endpoint's
behaviour and error shape.

**FR-008.** The endpoint MUST NOT silently overwrite. An existing file at the
target MUST be reported to the caller so the UI can prompt (§6, FR-018).
Overwrite MUST require an explicit caller opt-in.

**FR-009.** `PUT /api/projects/{project_id}/file` MUST keep rejecting paths
outside the project root. This spec adds a second door; it does not widen the
first.

**FR-010.** After a successful write the affected registry MUST be refreshed so
the new block or type is discoverable without a restart.

**FR-011.** The agent MUST be able to perform the same promotion through an MCP
tool. Without it the agent cannot act on the promotion opportunities ADR-053 §3
expects it to offer.

## 5. Drop-In Type Import Defect

**FR-012.** A drop-in block MUST be able to import a drop-in type by its file
name from the project types directory and from the user types directory. The
types directories MUST be prepended to `sys.path` for the duration of drop-in
block execution, alongside the existing user site directory.

**FR-013.** The same roots MUST be recorded in `block_spec.runtime_import_roots`
so the worker subprocess reconstructs the block identically. A block that
imports successfully during palette scanning but fails at run time is not a fix.

These roots must be identical in every process that loads drop-in blocks — the
API, the agent, the worker, and IO dispatch. A block that resolves its type
import under the API and fails under the agent is the same defect in a different
place. That obligation is stated as FR-057 in §10.3, because it is discharged by
the shared provisioning helper rather than by editing four call sites to match.

**FR-014.** Import resolution order MUST place the project types directory ahead
of the user types directory, so a project-local type shadows a user-level type
of the same file name. This matches the precedence users already expect from
block discovery.

**FR-015.** A drop-in block that fails to import MUST surface that failure to
the user. Today it is a server-side warning only and the block silently vanishes
(§2.5). At minimum the failing file, the exception type, and the message MUST
reach a surface the user can see. The mechanism is left to implementation; the
obligation is that silent disappearance ends.

**FR-016.** Because the types directories join `sys.path`, a file there can
shadow an installed third-party package of the same name — a `json.py` or
`numpy.py` under `{project}/types/` would be imported in preference to the real
package by any code loaded afterwards. The implementation MUST warn on a type
file whose stem collides with an importable top-level module. Whether this
warns or blocks is an open decision (§13, OQ-1).

## 6. Promotion

**FR-017.** Promotion MUST copy, never move. The originating project MUST keep
working exactly as before.

**FR-018.** A name collision in the destination MUST prompt the user with
overwrite and save-as-new-name options. Silent overwrite is forbidden.

**FR-019.** Promotion MUST be offered only for tier-1 blocks and types with a
resolvable `file_path`. For built-in and packaged items — which already live in
a library — the action MUST be hidden, not shown disabled.

**FR-020.** On success the UI MUST confirm inline and reveal the item in its new
section in the palette. The action exists to teach that the container exists; a
silent success wastes the teaching moment.

### 6.1 Cascade Promotion

**FR-021.** Before promoting a block, the implementation MUST determine which
project-level custom types that block depends on.

**FR-022.** Dependency detection MUST parse the block's imports statically (AST)
and resolve each imported name against the type registry, classifying each
resolved type by origin using the shared resolver (FR-003). Static parsing is
sufficient because after §5 a block expresses a type dependency as a real import
statement.

**FR-023.** When project-level type dependencies are found, the user MUST be
offered promotion of those types alongside the block, as a single confirmed
action. Declining MUST still allow the block to be promoted, with an explicit
warning that it will fail to load in other projects.

**FR-024.** Cascade MUST be one level deep in this spec. A type that itself
imports another project-level type is out of scope and MUST be reported rather
than silently missed.

### 6.2 Entry Points

Promotion is reachable from five places. All five call the same underlying
action.

| # | Entry point | Notes |
|---|---|---|
| E1 | Block source editor toolbar | Beside the existing save / view-source affordances |
| E2 | Canvas node context menu | Reuses the existing canvas menu |
| E3 | Agent (MCP tool) | FR-011; agent may also offer it after authoring a block the user ran successfully |
| E4 | New-file target choice | §8, FR-029 — creation-time, not promotion of an existing file |
| E5 | Palette hover popover button | §9, requires the popover to become interactive |

**FR-025.** E1, E2, E3, and E5 MUST share one implementation of the promotion
action, including collision prompting and cascade. Four copies of this logic is
exactly the drift this spec is written to avoid.

## 7. Types API

**FR-026.** A types listing endpoint MUST be added under a new
`src/scistudio/api/routes/types.py`. It MUST return, per registered type: name,
base type, description, origin tier (FR-005), `file_path` when resolvable, the
declared colours (§7.1), and the supported file extensions (§7.2).

**FR-027.** The endpoint MUST be independent of the block list response. The
Data types tab MUST NOT depend on a blocks request to populate or refresh.
`type_hierarchy` on the block response is unchanged and keeps serving port
colour resolution.

**FR-028.** A type template endpoint MUST be added to the same router, mirroring
`GET /api/blocks/template`. It MUST return a minimal `DataObject` subclass
skeleton with the same response shape as the block template endpoint
(`{kind, content, suggested_filename}`). The skeleton MUST include the colour
attributes (§7.1) as commented-out optional lines, so a user authoring a type
discovers that declaring a colour is possible.

### 7.1 Backend-Declared Type Colour

Today a type cannot influence its own colour (§2.8). Blocks can, through
`BlockSummary.ui_color` / `ui_icon` (#1839). This section completes the
`ui_ring_color` precedent that was declared and never wired.

**FR-049.** `DataObject` MUST gain optional class attributes letting a type
declare its own appearance: a fill colour and a ring colour, both CSS hex
strings, both defaulting to `None`. Naming MUST mirror the block precedent
(`ui_color`, `ui_ring_color`).

**FR-050.** `TypeRegistry` MUST collect the declared colours onto the type spec,
and the types listing endpoint MUST surface them. `TypeHierarchyEntry.ui_ring_color`
on the block response MUST also be populated from the same source, ending the
dead field described in §2.7.

**FR-051.** Colour resolution precedence MUST be: type-declared colour, then the
existing `typeColorMap` entry, then the `hashTypeName` fallback. A declared
colour wins; an undeclared type behaves exactly as it does today. This applies
identically to palette tiles and canvas ports, so a type looks the same in both
places.

**FR-052.** An invalid colour value MUST be ignored with a warning and MUST fall
through to the next precedence level. A malformed hex string in a user's type
file MUST NOT break the palette or the canvas.

**FR-053.** `src/scistudio/core/types/base.py` is a protected core path. The
implementing PR MUST carry `admin-approved:core-change`, verified in CI. This
spec is docs-only and does not itself require the label.

### 7.2 Supported Extensions Per Type

**FR-054.** The types listing endpoint MUST report, per type, the file
extensions it can be loaded from and saved to, derived from registered
`FormatCapability` records (§2.9) grouped by `data_type`.

**FR-055.** Load and save MUST be reported separately. A type readable from a
format it cannot be written back to is a real and useful asymmetry, and
collapsing the two directions would hide it.

**FR-056.** A type with no format capability MUST report empty lists, which the
popover renders as an explicit "no file formats registered" rather than omitting
the row. Absence of IO support is information.

## 8. Creating Blocks And Types

**FR-029.** The new-file flow MUST ask where the file goes: the user library or
the current project. This is E4 — the cheapest possible moment to teach that the
library exists, because the user is already deciding where their work lives.

**FR-030.** Choosing the library MUST route to the user library write endpoint
(§4); choosing the project MUST keep the current `putProjectFile` behaviour.

**FR-031.** Collision probing MUST run against whichever destination was chosen.
`probeProjectFileExistence` covers only the project today and MUST gain a user
library counterpart.

**FR-032.** A **New data type** action MUST be added to the toolbar, mirroring
`createNewCustomBlock` (§2.9): prompt for a filename, validate it as a Python
identifier, probe the chosen destination, fetch the type template (FR-028),
write, and open the file for editing.

**FR-033.** The new-block and new-data-type flows MUST share their prompt,
validation, collision-probe, write-dispatch, and open-file steps. Only the
target subdirectory and template kind differ.

## 9. Palette

### 9.1 Blocks Tab

**FR-034.** The left panel's first tab MUST be renamed `Blocks`.

**FR-035.** The single `Custom` section MUST separate into `My Library`
(user tier) and `This Project` (project tier).

**FR-036.** Section order MUST be: `Data I/O` (pinned) → `Built-in` →
`My Library` → `This Project` → plugin packages A→Z. The user tier is ordered
above the project tier because it is the container the product is asking users
to invest in.

**FR-037.** `My Library` and `This Project` MUST render when empty, each
carrying one line stating what the section is for. This is the only moment a
user who has never heard of a personal library is guaranteed to be looking at
the place it would live, and it is treated as load-bearing rather than as
polish. Other sections keep their current omit-when-empty behaviour.

**FR-038.** This changes the grouping dimension, not just the section list.
`buildPaletteSections` currently groups by package via `derivePackage`; it MUST
group by origin tier first and package second. The change is larger than the
"split one section in two" framing in #1995.

### 9.2 Data Types Tab

**FR-039.** A third tab, `Data types`, MUST be added between `Blocks` and
`Project`. `leftTab` widens from `"blocks" | "project"` to include `"types"`.
The label is `Data types` rather than `Types`, which is too abstract standing
alone next to `Blocks`; the internal key stays `types`.

**FR-040.** The Data types tab MUST mirror the Blocks tab: search input, filter
chips, and tier sections with core pinned at the top, then `My Library`, then
`This Project`, then packages A→Z. Empty-state behaviour follows FR-037.

**FR-041.** Each type tile MUST carry a colour swatch — solid fill plus ring —
resolved through the precedence in FR-051, so a type reads identically in the
palette and on a canvas port. No new colour table is introduced; the declared
colour simply takes priority over the existing resolution.

**FR-042.** Each type MUST have a hover popover carrying:

| Row | Content | Source |
|---|---|---|
| Name | The registered type name | listing |
| Parent | The immediate base class, and the core base type when it differs | `base_type`; `resolveCoreBaseType` already computes the core base for a chain such as `SRSImage → Image → Array` |
| Description | The type's docstring-derived description | listing |
| Extensions | Loadable-from and saveable-to extensions, reported separately (FR-055), or an explicit "no file formats registered" (FR-056) | §7.2 |
| Origin | Which tier the type came from | FR-005 |
| Action | Promote to My Library (E5) where applicable | §6.2 |

**FR-043.** The parent row MUST show the chain position rather than only the
immediate parent when the two differ. `resolveCoreBaseType`
(`frontend/src/config/typeColorMap.ts:179`) already returns the highest ancestor
below `DataObject` and returns `null` when the type is itself a core base, so no
redundant `Array (Array)` is rendered.

### 9.3 Interactive Popover

**FR-044.** The hover popover MUST become interactive: `pointer-events-none` is
removed, the popover maintains its own hover state so it stays open while the
pointer is inside it, and the gap between tile and popover
(`POPOVER_GAP`) MUST NOT close it in transit.

**FR-045.** Tile dragging MUST keep working unchanged. `handleDragStart` and the
popover's new interactivity MUST NOT interfere; this MUST be covered by a test.

**FR-046.** One popover implementation MUST serve both blocks and types.

## 10. Shared Helpers And Anti-Drift

Types are implemented independently, modelled on the block implementation, with
shared helpers extracted wherever the two genuinely share behaviour. The
boundary below is normative: what is listed as shared MUST be shared, and what
is listed as separate MUST NOT be forced into a common abstraction.

### 10.1 Shared

| Concern | Shape |
|---|---|
| Search filtering | `filterItems<T>(items, search, toHaystack)` — generalised from `filterBlocks` / `matchesSearch` |
| Section building | `buildSections<T>(items, groupOf, pinnedOrder)` — the Map-group → ordered-take → remainder-A→Z skeleton |
| Section model | `Section<T>`, generalised from `PaletteSection` |
| Tile | One tile component: colour swatch, label, hover trigger, drag hook |
| Popover | One popover (FR-046), including the interactivity change (FR-044) |
| Filter chips | Generalised from `CategoryChips` |
| Hover positioning | Anchor computation, `POPOVER_GAP`, `POPOVER_MAX_HEIGHT`, open delay |
| Origin resolution (backend) | One resolver (FR-003) |
| User library write (backend) | One endpoint serving both targets (FR-006) |
| Promotion action (frontend) | One action behind all of E1, E2, E3, E5 (FR-025) |
| New-file flow (frontend) | Shared prompt / validate / probe / write / open (FR-033) |

**FR-047.** After §9.1 both surfaces group primarily by origin tier, so
`buildSections<T>` MUST fit both without per-surface special-casing. If it
cannot, the grouping contract is wrong and MUST be revised rather than
special-cased.

### 10.2 Not Shared

`derivePackage` (depends on `package_name` and dotted `type_name` namespaces),
`isIoSource` / `isIoSink` / `isDataIoBlock`, `CATEGORY_KEYS`
(`io`/`process`/`code`/`app`/`ai`), and `portSignature` are block concepts and
MUST stay on the block side.

### 10.3 Registry Provisioning

§2.6 records the same semantic written four times, no two agreeing. The
frontend helpers above prevent future drift; this section removes the drift that
already exists. Without it the features in this spec behave differently
depending on which process the user's action happens to run in.

**FR-057.** Drop-in directory registration and import-root injection MUST be
provided by one shared helper, consumed by all four sites in §2.6 — the API
runtime, the agent runtime, worker-side type reconstruction, and IO dispatch.
Each site MAY pass its own project directory and MAY declare whether a project
context exists, but MUST NOT decide independently which directories the tier
comprises or which roots go on `sys.path`.

**FR-058.** The helper MUST resolve blocks and types through the same tier
definition. After this spec there is exactly one answer to "where does the user
tier live", used by both.

**FR-059.** The agent runtime MUST register project-level and user-level type
directories. Today `_build_type_registry()` registers none (§2.6), so agent
promotion (FR-011) and cascade dependency detection (FR-022) resolve against an
empty view of the user's types.

**FR-060.** Whether the user tier requires an active project MUST be one
decision applied to both blocks and types, not four independent ones. It is
currently unconditional for types under the API, unconditional for blocks under
the agent, and conditional for blocks under the API. See OQ-2 for which way the
single answer goes.

**FR-061.** The scan order difference (§2.6) MUST be reconciled or documented as
deliberate. Both registries claim entry-point registrations win on duplicates
and both achieve it, one by ordering and one by skip-if-present. If a shared
discovery helper is extracted, the orders MUST first be made to agree; if they
are kept separate, the reason MUST be recorded at both call sites.

### 10.4 Reload Symmetry

**FR-062.** Every event that invalidates the block registry MUST be evaluated
against the type registry. `refresh_block_registry` is called alone from five
sites — branch switch and four package install/uninstall paths (§2.6) — while
`refresh_type_registry` runs only on project switch and startup.

**FR-063.** Package install and uninstall MUST refresh the type registry. A
package can ship types; today installing one leaves them undiscovered until the
next project switch. This is a pre-existing defect, fixed here because the Data
types tab makes it visible — a user would install a package and watch its types
fail to appear.

**FR-064.** Branch switch MUST refresh the type registry. Switching branches can
change `{project}/types/` exactly as it changes `{project}/blocks/`.

**FR-065.** After a user library write (FR-010), the refresh MUST reach every
process holding a registry, not only the one that served the request. A block
promoted through the agent MUST become visible in the palette without a restart.

## 11. Test Plan

| Area | Test |
|---|---|
| Origin tiers | A block resolved from each directory returns its distinct origin; unresolvable path falls back to `custom` (FR-001, FR-002) |
| Shared resolver | Block and type origin resolution exercise the same function (FR-003) |
| Write endpoint | Writes land in the user library; traversal and symlink escapes 403; existing file is reported rather than overwritten (FR-006 – FR-008) |
| Project endpoint unchanged | Escaping paths still 403 (FR-009) |
| Registry refresh | A written block/type is discoverable without restart (FR-010) |
| MCP promotion | The agent tool promotes a block and the result is discoverable (FR-011) |
| Drop-in import | The §2.5 reproduction now registers `uses_spectrum`; project types shadow user types (FR-012, FR-014) |
| Worker parity | A block importing a drop-in type runs in the worker, not just registers (FR-013) |
| Import failure surfaced | A failing drop-in produces a user-visible report (FR-015) |
| Shadowing warning | A type file colliding with an importable top-level module warns (FR-016) |
| Promotion semantics | Copy not move; collision prompts; hidden for built-in/packaged (FR-017 – FR-019) |
| Cascade | Block with a project-level type dependency offers cascade; declining warns; second-level dependency reported (FR-021 – FR-024) |
| Type colour declaration | A type declaring a colour surfaces it through the listing and through `type_hierarchy`; the field is no longer always `None` (FR-049, FR-050) |
| Colour precedence | Declared colour beats `typeColorMap`, which beats the hash fallback; an undeclared type is unchanged from today (FR-051) |
| Invalid colour | A malformed hex value warns and falls through without breaking palette or canvas (FR-052) |
| Extensions per type | Load and save extensions reported separately from `FormatCapability`; a type with none reports empty lists (FR-054 – FR-056) |
| Palette sections | Order, both tiers rendered when empty, origin-first grouping (FR-035 – FR-038) |
| Data types tab | Mirrors blocks structure; tab label is `Data types`; tile colour follows the FR-051 precedence (FR-039 – FR-041) |
| Type popover contents | Name, parent (with core base when it differs), description, extensions, origin, promotion action (FR-042, FR-043) |
| Popover | Interactive, survives the tile→popover gap, does not break dragging (FR-044, FR-045) |

| Provisioning parity | The four registration sites resolve identical drop-in directories and import roots for a given project context (FR-057, FR-058) |
| Agent type visibility | A drop-in type in the project and in the user library is registered in the agent runtime (FR-059) |
| Agent import parity | The §2.5 reproduction registers under the agent runtime and the worker, not only under the API (FR-013, §10.3) |
| Tier condition | The active-project condition resolves the same way for blocks and types across all sites (FR-060) |
| Package reload | Installing a package that ships types makes them discoverable without a project switch (FR-063) |
| Branch switch reload | Switching to a branch with different `{project}/types/` refreshes the type registry (FR-064) |
| Cross-process refresh | A block promoted through the agent appears in the palette without restart (FR-065) |

**FR-048.** Backend tests MUST NOT rely on `pip install -e .`.

## 12. Implementation Plan

### 12.1 Affected Files

Every file below already exists and is modified by the implementing issues, so
none belongs in this spec's `planned_governs` (which carries only the two files
that do not exist yet). This table is the machine-unreadable half of that
contract and is the list an implementer works from.

| File | Action | Why |
|---|---|---|
| `src/scistudio/api/_block_source.py` | modify | Split `map_block_origin` into `user` / `project` with fallback (FR-001, FR-002) |
| `src/scistudio/api/routes/blocks.py` | modify | Carry resolved origin (FR-004); populate `ui_ring_color` (FR-050) |
| `src/scistudio/api/routes/types.py` | create | Types listing and type template (§7) |
| `src/scistudio/api/schemas.py` | modify | Type listing response, declared colours, extensions (§7) |
| `src/scistudio/core/types/base.py` | modify | Colour class attributes on `DataObject` (FR-049) — protected core, needs `admin-approved:core-change` |
| `src/scistudio/core/types/registry.py` | modify | Collect declared colours (FR-050); scan-order reconciliation (FR-061) |
| `src/scistudio/api/runtime/_projects.py` | modify | Consume the shared provisioning helper (FR-057); reload symmetry (FR-062) |
| `src/scistudio/ai/agent/mcp/runtime.py` | modify | Register type directories (FR-059); consume the helper (FR-057) |
| `src/scistudio/core/types/serialization.py` | modify | Consume the helper instead of duplicating scan dirs (FR-057) |
| `src/scistudio/blocks/io/_unified_dispatch.py` | modify | Consume the helper; single active-project decision (FR-057, FR-060) |
| `src/scistudio/blocks/registry/_scan.py` | modify | Import roots for drop-in type resolution (FR-012, FR-013) |
| `src/scistudio/api/routes/git.py` | modify | Branch switch refreshes the type registry (FR-064) |
| `src/scistudio/api/routes/packages.py` | modify | Package install/uninstall refreshes the type registry (FR-063) |
| `frontend/src/App.tsx` | modify | `leftTab` widens to include `types` (FR-039) |
| `frontend/src/App.parts/ProjectWorkspace.tsx` | modify | Third tab, renamed first tab (FR-034, FR-039) |
| `frontend/src/App.parts/useProjectActions.ts` | modify | New data type; new-file target choice (FR-029 – FR-033) |
| `frontend/src/components/BlockPalette.tsx` | modify | Tier sections, empty states, interactive popover wiring (§9.1, §9.3) |
| `frontend/src/components/BlockPalette.parts/paletteModel.ts` | modify | Origin-first grouping; extract shared helpers (FR-038, §10.1) |
| `frontend/src/components/BlockDetailPopover.tsx` | modify | Becomes interactive and serves both surfaces (FR-044, FR-046) |
| `frontend/src/components/TypePalette.tsx` | create | The Data types tab (§9.2) |
| `frontend/src/config/typeColorMap.ts` | modify | Declared-colour precedence (FR-051, FR-052) |
| `frontend/src/lib/api/code.ts` | modify | Type template and types listing clients (§7) |
| `docs/specs/frontend-block-palette.md` | modify | Amend for the renamed tab, tier sections, grouping change, interactive popover |

### 12.2 Sequence

1. Shared registry provisioning helper and its four consumers (§10.3). First,
   because §5, the write path, and cascade all depend on every process resolving
   the same directories — building them on four diverging call sites means
   fixing each feature four times.
2. Reload symmetry (§10.4).
3. Shared origin resolver and the `map_block_origin` split (FR-001 – FR-005).
4. Drop-in type import fix, worker parity, and shadowing warning (§5). Ahead of
   cascade because cascade depends on the dependency being expressible.
5. User library write endpoint plus registry refresh (FR-006 – FR-010).
6. Type colour attributes on `DataObject` and their collection through
   `TypeRegistry` (§7.1). Protected-core; needs `admin-approved:core-change`
   (FR-053), so it is sequenced early enough that the label review does not
   block the frontend work behind it.
7. Per-type extension derivation from format capabilities (§7.2).
8. `routes/types.py`: types listing and type template (§7).
9. Shared frontend helpers (§10.1) and the `buildSections` grouping change.
10. Blocks tab rename, tier sections, empty states (§9.1).
11. Interactive popover (§9.3).
12. Data types tab, tiles, and popover contents (§9.2).
13. Promotion action and entry points E1, E2, E5 (§6).
14. Cascade promotion (§6.1).
15. New data type and the new-file target choice (§8).
16. MCP promotion tool, E3 (FR-011).
17. Amend `docs/specs/frontend-block-palette.md` for the renamed tab, the tier
    sections, the grouping change, and the interactive popover.

The user-tier active-project condition (§2.4, OQ-2) is settled inside step 1
rather than as a separate step: FR-060 makes it one decision for both registries,
so it lands with the provisioning helper.

## 13. Open Questions

**OQ-1.** Does a type file whose stem shadows an importable top-level module
warn, or is it rejected outright (FR-016)? Warning preserves the user's freedom
to name files as they like; rejecting prevents a failure mode that will be very
hard for a user to diagnose.

**OQ-2.** Should the user tier require an active project? FR-060 makes this one
decision covering blocks and types in all four processes, rather than the four
independent answers in place today, but does not say which way it goes. Dropping
the condition aligns blocks with types and is required if any no-project surface
must show library contents; the Learning Center system spec owns that first-run
no-project surface, so the answer is settled there and executed here.

**OQ-3.** Issue coverage. #1995 and #1996 exist. The drop-in import defect
(§5), the Data types tab (§9.2), New data type (§8), backend-declared type
colour (§7.1), registry provisioning consolidation (§10.3), and reload symmetry
(§10.4) have no issue yet. The last two are pre-existing defects rather than new
feature surface and may warrant their own issues so they can land ahead of the
feature work that depends on them.

## 14. Risks

**The grouping dimension changes.** §9.1 rewrites how `buildPaletteSections`
groups rather than adding sections to it, so every existing palette ordering
test is in scope. Mitigated by `paletteModel` being pure and already unit-tested.

**Types directories join `sys.path`.** §5 makes a user-writable directory
participate in module resolution for any code loaded afterwards. The shadowing
warning (FR-016) reduces but does not eliminate this. The blast radius is bounded
by these directories already executing arbitrary user code in-process (#1531).

**A second write door.** The user library endpoint writes outside every project
root — the first such path in the product. Its constraint is inverted rather
than relaxed, and FR-009 keeps the project endpoint untouched, but this is the
highest-risk surface in the spec and warrants the closest review.

**Cascade can still produce a broken library block.** One level deep (FR-024)
leaves transitive type dependencies uncarried. FR-024 requires reporting them,
so the failure is visible rather than silent.

**Consolidating registry provisioning touches four load-bearing paths.** §10.3
replaces four independent registration sites with one helper, and those sites
serve the API, the agent, the worker, and IO dispatch. A mistake there does not
degrade a palette section — it makes blocks or types fail to load in one process
while working in another, which is the hardest class of bug in this codebase to
diagnose. It is sequenced first so it is exercised by everything built on top of
it, and FR-057's parity test is the primary defence.

**Fixing reload symmetry changes existing behaviour.** §10.4 makes package
install/uninstall and branch switch refresh the type registry, which they do not
do today. Any code that depends on the type registry surviving a package
operation unchanged would be affected. No such dependency was found, but this is
behaviour change to a path outside the spec's headline feature.

**Type colour touches protected core.** §7.1 adds class attributes to
`DataObject`, so the implementing PR needs `admin-approved:core-change`
(FR-053). The change itself is small and additive — two optional attributes
defaulting to `None` — but it lands on the most-reviewed path in the repository
and the frontend work depends on it. The precedence rule (FR-051) keeps every
existing type's appearance byte-identical, so the blast radius is confined to
types that opt in.

**Three places for blocks to live becomes visible.** ADR-053 §8 accepts this
cost: users currently reason about built-in and everything-else, and this makes
it three. The empty states (FR-037) are what turn the added category into
teaching rather than clutter.

## 15. Assumptions

| Assumption | Source |
|---|---|
| Previewers need no user tier; project-level is sufficient | owner |
| The drop-in import defect is fixed in this spec, not split out | owner |
| The tips strip (#1997) belongs to the Learning Center spec | owner |
| Types are implemented independently with shared helpers extracted, not folded into the block implementation | owner |
| The hover popover is preferred over a palette right-click menu | owner |
| Cascade promotion is required rather than warn-only | owner |
| The tab is labelled `Data types`, not `Types` | owner |
| Types declare their own colour in core, mirroring the block precedent, rather than remaining frontend-assigned | owner |
| The type popover shows description, parent class, and supported extensions | owner |
| Block and type lifecycle asymmetries found during investigation are fixed in this spec rather than split out | owner |
| No existing code depends on the type registry surviving a package install unchanged | existing-system |
| `file_path` on the registry spec is reliable enough to drive tier resolution | existing-system |
| Verified current-state facts in §2 hold at `6579d9ce` | existing-system |
