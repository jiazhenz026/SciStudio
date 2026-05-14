# Spec: `scieasy-blocks-metadata` (DRAFT)

**Status**: Draft (2026-05-13, rev 2)
**Owner**: TBD
**Related**: ADR-027 D5 (three-slot metadata), ADR-029 (variadic ports), ADR-031 (DataObject reference-only), ADR-032 (MetadataStore lineage)
**Scope**: New external plugin package. Zero core/engine changes.

---

## 1. Motivation

Users of SciEasy invariably bring a **sample metadata table** — an Excel/CSV
spreadsheet listing each sample, the experimental group it belongs to, treatment
condition, timepoint, etc. Today this concept only exists inside the LCMS plugin
(`scieasy_blocks_lcms.types.SampleMetadata`), which is wrong for two reasons:

1. **Not LCMS-specific.** Microscopy, sequencing, electrophysiology — all need it.
2. **Doesn't connect to anything.** The LCMS block reads the table but there is
   no machinery to ask "for this DataObject I have in hand, what group does it
   belong to?" — which is the actual user need (A vs B comparisons, plotting by
   group, splitting Collections by condition).

This spec defines a domain-agnostic plugin package, `scieasy-blocks-metadata`,
that owns the *concept* of per-sample experimental metadata and the *machinery*
to join it back to arbitrary DataObjects via the ADR-032 lineage chain.

### Non-goals

- Do **not** extend core scope. Core stays unaware of "metadata table" as a
  concept. To the engine, `Metadata` is just another DataObject subtype.
- Do **not** auto-inject sample identity into DataObject framework slots.
  Block authors decide what metadata to carry forward (per the 2026-05-13
  user decision).
- Do **not** prescribe workflow ordering. Users split when they want; if a
  late split fails because metadata was lost mid-pipeline, the workflow
  errors loudly — we don't lecture.
- Do **not** ship a `SaveMetadata` block. `Metadata <: DataFrame`, so core
  `SaveData` accepts it via inheritance.

---

## 2. Package Layout

```
scieasy-blocks-metadata/
├── pyproject.toml
└── src/scieasy_blocks_metadata/
    ├── __init__.py
    ├── types.py            # Metadata type
    ├── lookup.py           # lookup utility functions (no block deps)
    └── ops/
        ├── __init__.py
        ├── load.py         # LoadMetadata block
        ├── lookup_block.py # Lookup block
        ├── join.py         # JoinMetadata block
        └── split.py        # SplitByColumn block
```

### `pyproject.toml` entry points

```toml
[project.entry-points."scieasy.types"]
Metadata = "scieasy_blocks_metadata.types:Metadata"

[project.entry-points."scieasy.blocks"]
LoadMetadata    = "scieasy_blocks_metadata.ops.load:LoadMetadata"
Lookup          = "scieasy_blocks_metadata.ops.lookup_block:Lookup"
JoinMetadata    = "scieasy_blocks_metadata.ops.join:JoinMetadata"
SplitByColumn   = "scieasy_blocks_metadata.ops.split:SplitByColumn"

[project.dependencies]
scieasy-core = ">=X.Y.Z"   # hard pip dep
pandas       = ">=2.0"
openpyxl     = ">=3.1"     # for xlsx
```

---

## 3. Type Contract: `Metadata`

```python
from scieasy.core.types import DataFrame
from pydantic import BaseModel, ConfigDict, Field


class Metadata(DataFrame):
    """Per-sample experimental metadata.

    One row per sample. Must contain a column whose values match the
    `framework.source` of upstream loader-produced DataObjects, so that
    Lookup can resolve "given this object, what group is it in?" via
    the ADR-032 lineage chain.

    Column name configurable via Meta.sample_id_column (default: 'filename').
    All other columns are user-defined (group, condition, timepoint, etc.).
    """

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        sample_id_column: str = Field(
            "filename",
            description=(
                "Column whose values match upstream loader's framework.source. "
                "Set this when your sample identity comes from a column other "
                "than 'filename' (e.g., 'sample_id')."
            ),
        )
```

### Construction invariant

`Metadata.__init__` (or a class-level validator) MUST enforce:

- the underlying DataFrame has a column named `self.meta.sample_id_column`
- all values in that column are unique (one row per sample)
- column dtype is string-like

Violations raise `ValueError` at construction time, **not** lazily at Lookup.

### Why a typed wrapper

A plain `DataFrame` would technically work — Lookup could accept `DataFrame +
config[sample_id_column]`. We keep the typed wrapper because:

1. **Port type-checking surface area.** Downstream blocks declare
   `metadata: Metadata` and get compile-time-ish validation.
2. **Self-documenting workflow graphs.** Seeing `Metadata` on a wire tells
   the reader what the column carries.
3. **Inheritance preserves Save path.** `Metadata <: DataFrame`, so core
   `SaveData(core_type="DataFrame")` accepts it untouched.

---

## 4. Lookup Mechanism

### The lookup utility (`lookup.py`)

```python
def lookup_metadata(
    obj: DataObject,
    metadata: Metadata,
    *,
    keys: list[str] | None = None,
    on_missing: Literal["error", "null", "skip"] = "error",
    match_mode: Literal["exact", "basename"] = "basename",
) -> dict[str, Any] | None:
    """Resolve metadata for a single DataObject by walking its lineage.

    Algorithm:
      1. Walk `obj.framework.derived_from` chain via MetadataStore.ancestors()
         until we hit a DataObject whose framework.source is non-null.
         (This is the loader-produced root.)
      2. Match that source against metadata[sample_id_column] using match_mode.
      3. Return requested keys (or all columns) as a dict.

    match_mode semantics:
      - exact:    framework.source == metadata[sample_id_column] (full path)
      - basename: os.path.basename(framework.source) == metadata[sample_id_column]
                  (default — most user metadata tables list bare filenames)

    on_missing semantics:
      - error: raise LookupError if no match found
      - null:  return dict with None values
      - skip:  return None (caller decides)
    """
```

This is **pure Python**, no block dependency. LCMS-core / imaging-core /
anyone can import it directly.

### The `Lookup` block (`ops/lookup_block.py`)

```python
class Lookup(ProcessBlock):
    """Build a parallel Metadata table aligned to a Collection.

    For each DataObject in the input Collection, walk its lineage to find
    the originating sample's framework.source, then row-bind the matching
    Metadata row into a new Metadata table.

    Output is a Metadata table with one row per item in the Collection,
    plus an `_object_id` column carrying the input object_id for downstream
    alignment.
    """

    inputs = {
        "data":     Port[Collection],
        "metadata": Port[Metadata],
    }
    outputs = {
        "result":   Port[Metadata],
    }

    class Config(BaseModel):
        keys: list[str] | None = None                              # which columns; None = all
        on_missing: Literal["error", "null", "skip"] = "error"
        match_mode: Literal["exact", "basename"] = "basename"
```

### Output alignment: `__scieasy_object_id__` column

Lookup output is a `Metadata` table with one row per Collection item, plus a
reserved column `__scieasy_object_id__` carrying the input object's
`framework.object_id`. Downstream joins/merges align on this column.

The column name uses a deliberately ugly `__scieasy_*__` namespace (dunder
prefix + project name + dunder suffix) to minimize the chance of colliding
with a real user metadata column.

**Collision policy.** If the input `Metadata` table already contains a column
named `__scieasy_object_id__`, `Lookup` raises at validate-time with a clear
message identifying the offending column and instructing the user to rename
it. We do **not** silently rename, suffix, or shadow — that would mask bugs.
The validate-time error is the only hard restriction the package places on
user column names.

Why object_id over positional alignment:
- Robust to Collection reordering or filtering downstream
- Object IDs are the canonical identity under ADR-031 — no new concept
- Lets a single Metadata table be joined against multiple downstream
  DataFrames originating from the same Collection

---

## 5. Blocks

| Block | Inputs | Outputs | Config | Purpose |
|---|---|---|---|---|
| `LoadMetadata` | (none) | variadic `Metadata` (ADR-029) | `path`, `sheet_map`, `sample_id_column` | Read CSV/TSV/XLSX, one output port per sheet |
| `Lookup` | `data: Collection[T]`, `metadata: Metadata` | `result: Metadata` | `keys`, `on_missing`, `match_mode` | Build parallel table aligned to Collection items |
| `JoinMetadata` | `df: DataFrame`, `metadata: Metadata` | `result: DataFrame` | `left_on`, `right_on`, `how` | Row-level pandas merge for tabular data |
| `SplitByColumn` | `data: Collection[T]`, `metadata: Metadata` | variadic `Collection[T]` (ADR-029) | `column`, `output_ports` | Partition Collection by a metadata column value |

### `LoadMetadata` notes

```python
class LoadMetadata(IOBlock):
    """Read a metadata file. One output port per logical metadata table.

    For .csv / .tsv: always single-sheet. The single declared output port
    receives the parsed table.

    For .xlsx: multi-sheet via ADR-029 variadic outputs. Each declared
    output port maps to one sheet, via the `sheet_map` config. Default
    when only one port is declared and `sheet_map` is empty: read the
    first sheet.
    """

    variadic_outputs: ClassVar[bool] = True
    min_output_ports = 1
    # max_output_ports unbounded — capped only by sheet count at validate time

    class Config(BaseModel):
        path: Path
        sample_id_column: str = "filename"
        # Maps output port name -> Excel sheet name. Ignored for csv/tsv.
        # If empty and exactly one output port is declared, that port
        # receives the first sheet. If empty and multiple ports declared,
        # validate-time error: user must be explicit.
        sheet_map: dict[str, str] = Field(default_factory=dict)
```

- Reads `path` based on extension: `.csv` / `.tsv` / `.xlsx`.
- `sheet_map` only honored for `.xlsx`. For csv/tsv, validate-time error if
  more than one output port is declared.
- If `sample_id_column` config differs from the typed wrapper default,
  every constructed `Metadata` instance carries that override in its Meta.
- The block emits framework.source = full path to the file (per the standard
  loader contract). For multi-sheet xlsx, source is the same path for every
  output port — sheets are distinguished by output port name, not by source.
  This lineage entry is NOT used by Lookup — Lookup walks lineages of
  *data* objects, not of the Metadata itself.

**Common patterns:**

| User scenario | Setup |
|---|---|
| One CSV file | 1 output port (any name), `sheet_map={}` |
| Single-sheet XLSX | 1 output port, `sheet_map={}` |
| XLSX with control + treated sheets | 2 output ports `["control", "treated"]`, `sheet_map={"control": "Control Samples", "treated": "Treated Samples"}` |

### `Lookup` block — when row-level metadata is needed

The motivating example from the 2026-05-13 discussion: a user loads 3 IF
images, runs cell segmentation, and ends up with a 9-row DataFrame (3 cells
per image). The 9-row DataFrame is **not a Collection**; it's a single
DataFrame. Lookup cannot help here.

For this case, the segmentation block author has two choices:

1. **Output a Collection of 3 small DataFrames** — Lookup applies cleanly.
2. **Output a single DataFrame with a `source` or `sample_id` column** that
   carries the originating filename per row. Then `JoinMetadata` (pandas
   merge) does the work.

Choice (2) is the segmentation block's responsibility. We don't enforce it;
if the author drops the column, downstream `JoinMetadata` fails loudly.
This is the self-enforcing pattern the user explicitly requested.

### `SplitByColumn` and ADR-029 variadic outputs

The block declares:

```python
class SplitByColumn(ProcessBlock):
    variadic_outputs: ClassVar[bool] = True
    min_output_ports = 2
    # max_output_ports unbounded — user-defined per instance
```

User sets `config["output_ports"] = ["control", "treatment_A", "treatment_B"]`
in the workflow. The block validates that each name maps to a unique value
of the configured column in the Metadata table; otherwise it errors at
validate-time, not run-time.

---

## 6. Engine Surface

**Zero changes to engine, scheduler, runtime API, or storage.**

The plugin gets everything it needs from the public extension API:

- `DataObject`, `DataFrame`, `Collection`, `ProcessBlock` (core base classes)
- `MetadataStore.ancestors()` (ADR-032, already exposed via `get_metadata_store()`)
- `scieasy.types` and `scieasy.blocks` entry-point groups (existing plugin contract)
- `variadic_outputs` ClassVar (ADR-029, already supported)

If during implementation it turns out a needed primitive is missing, that
becomes a separate core PR with its own ADR — **not** something we inline
into this package.

---

## 7. Hard Dependency Implications

Per the 2026-05-13 user decision: **packages that need metadata semantics
declare hard pip deps on `scieasy-blocks-metadata`.**

Examples:

- `scieasy-blocks-lcms` analysis blocks that compare groups → hard dep
- A future `scieasy-blocks-microscopy` plot-by-group block → hard dep
- A user's private analysis package → hard dep

This means installing `scieasy-blocks-lcms` transitively pulls in
`scieasy-blocks-metadata`. There is no "soft import" or "optional
extension" mode. The trade-off: every downstream user gets the same
4 blocks visible in their palette, even if they don't personally use them.
We accept that.

---

## 8. Resolved Decisions (2026-05-13)

1. **Lookup output alignment** — RESOLVED: `__scieasy_object_id__` column.
   Collision with a user column of the same name = validate-time hard error.
   See §4.
2. **`framework.source` format** — RESOLVED: loaders continue to record full
   absolute path (no change to existing contract). `lookup_metadata` accepts
   a `match_mode` config (`exact` | `basename`, default `basename`) so user
   metadata tables can list bare filenames.
3. **LCMS migration** — RESOLVED: keep `SampleMetadata = Metadata` alias in
   LCMS for backward compat; open a tracking issue for the eventual hard
   rename. Alias gets a `DeprecationWarning` on import.
4. **User column name restrictions** — RESOLVED: package places **no**
   restriction on user column names. The only reserved name is
   `__scieasy_object_id__`, and collision is detected/errored at Lookup
   validate-time (not at LoadMetadata) — because LoadMetadata has no way to
   know whether the table will eventually be used as Lookup input.

---

## 9. Test Plan

Unit (in-package):

- `Metadata` constructor: missing sample_id_column → ValueError
- `Metadata` constructor: duplicate sample_ids → ValueError
- `lookup_metadata` utility: happy path, missing-error, missing-null, missing-skip
- `lookup_metadata` utility: deep lineage chain (data → derive → derive → loader)
- Each block's `validate()`: required ports wired, config sane

Integration (cross-package, in test repo):

- LoadMetadata → image loader → process → Lookup roundtrip
- LoadMetadata → SplitByColumn → variadic Collections fan-out
- Metadata → core `SaveData` → reload → equality (covers inheritance Save path)

CI: ship the package in the monorepo or as a sibling repo, hook into the
existing matrix.

---

## 10. Phased Migration

**Phase 1** — Scaffold + core type + Load + Lookup
- Package skeleton, `Metadata` type, `lookup_metadata` utility,
  `LoadMetadata` block (incl. multi-sheet variadic xlsx), `Lookup` block.
- Ship 0.1.0. Verify LCMS *can* import it (no migration yet).

**Phase 2** — Join + Split
- `JoinMetadata` (pandas merge passthrough).
- `SplitByColumn` (variadic ADR-029 fan-out).
- Ship 0.2.0.

**Phase 3** — LCMS migration (soft)
- Add `scieasy-blocks-metadata` as hard pip dep in `scieasy-blocks-lcms`.
- Replace LCMS's local `SampleMetadata` class body with
  `SampleMetadata = Metadata` alias + `DeprecationWarning` on import.
- Update LCMS analysis blocks that compare groups to use `Lookup`.
- Open tracking issue: "Remove LCMS `SampleMetadata` alias — hard rename".
- Ship LCMS bump.

**Phase 4** — LCMS migration (hard, deferred)
- Per the tracking issue from Phase 3, after one minor version cycle, delete
  the `SampleMetadata` alias entirely. Workflow YAMLs referencing
  `SampleMetadata` start failing with a clear "renamed to Metadata" error.

Each phase = own PR, own gate, own CI green.

---

## 11. What This Spec Does NOT Cover

- AI-assisted metadata inference (user explicitly removed scope 2026-05-13).
- A `FilterByMetadata` block (user removed scope; `SplitByColumn` + drop
  unwanted outputs covers it).
- Per-row provenance for non-Collection DataFrame outputs — that's the
  upstream block author's responsibility (see §5 segmentation example).
- Cross-project / global metadata stores — Metadata is per-workflow,
  loaded from disk like any other data.
