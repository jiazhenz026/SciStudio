---
spec_id: adr-054-notebook-dependency-analysis
title: "ADR-054 Notebook Dependency Analysis — A Cell Table, A Graph, And A Runtime Check"
status: Draft
feature_branch: docs/adr-054-notebook-dependency-analysis-spec
created: 2026-09-02
input: "Owner-directed live session (guided): author the dependency-analysis implementation spec for ADR-054 sections 6.1 and 6.2. The owner settled the design in discussion — the unit of analysis is the cell; execution semantics are Jupyter's and the graph never rebinds or re-executes anything; what a cell reads is found statically, what a cell changes is observed when it runs by fingerprinting the whole namespace before and after, with static assignments serving only as the estimate for a cell that has not run yet; the graph marks what is stale, tells the session which cell the written order says defines a name so an out-of-order re-run can be marked, selects the slice a packaged block runs, and feeds the graph view."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 51
  - 54
related_specs:
  - adr-054-panel-contract
  - adr-054-explore-session
  - adr-054-explore-frontend
  - adr-054-documentation
  - adr-051-interactive-blocks
scope:
  in:
    - Per-cell static facts computed from source without running it - the top-level names a cell binds, the names it reads, the output and input declarations it makes, and the blocks it calls.
    - Runtime observation - a pure fingerprint function and a comparison over the whole module namespace before and after a cell runs, producing the set of names the cell changed, recorded on the cell and joined to the graph.
    - The dependency graph over enabled cells, the version nodes derived from it, and the queries the rest of ADR-054 consumes - downstream of a cell, backward slice of a set of cells, names changed by a cell, and the cell the written order says defines a name a given cell reads.
    - The record kept in notebook cell metadata, keyed to a hash of the cell source, with edges recomputed on load.
    - Handling of magic and shell lines, opaque cell magics, star imports, and cells that do not parse, all without IPython.
    - Unit coverage of every recognised binding form and of the observation per type, and a differential test that executes fixture notebooks and confirms the backward slice of the declared outputs reproduces the whole notebook's outputs.
  out:
    - The kernel, the execution queue, the stale and out-of-order marks as the session applies them, and the packaged block's run, which the explore-session spec owns. This spec defines what those consume.
    - The dependency-graph view and the control that enables or disables a cell, which the explore-frontend spec owns. This spec defines the data the view renders and reads the flag the control sets.
    - Loading and saving the notebook file, which the explore-session spec owns. This spec defines the shape of the record stored in cell metadata.
    - The panel contract and the panel-side use of changed names (adr-054-panel-contract).
    - Static recognition of in-place mutation. What a cell changes is observed when it runs; this spec deliberately carries no list of mutating methods, no alias tracking, and no analysis of helper bodies.
    - Statement-order precision inside a cell and control-flow precision, which are the model's stated limit, as ADR-054 section 6.2 states it.
    - Human documentation revision, which is specified separately in adr-054-documentation.
governs:
  modules:
    - scistudio.explore
    - scistudio.explore.dependency_analysis
    - scistudio.explore.fingerprint
  contracts:
    - scistudio.explore.dependency_analysis.CellFacts
    - scistudio.explore.dependency_analysis.DependencyGraph
    - scistudio.explore.fingerprint.Fingerprint
  entry_points: []
  files:
    - docs/specs/adr-054-notebook-dependency-analysis.md
    - src/scistudio/explore/__init__.py
    - src/scistudio/explore/dependency_analysis.py
    - src/scistudio/explore/fingerprint.py
    - tests/architecture/test_layer_deps.py
    - tests/explore/test_dependency_analysis.py
    - tests/explore/test_fingerprint.py
  excludes: []
planned_governs:
  modules: []
  contracts:
    - scistudio.explore.dependency_analysis.AnalysisRecord
    - scistudio.explore.fingerprint.ObservedChange
  entry_points: []
  files:
    - tests/explore/test_analysis_differential.py
    - tests/explore/fixtures/**
  excludes: []
tests:
  - tests/explore/test_dependency_analysis.py
  - tests/explore/test_fingerprint.py
  - tests/explore/test_analysis_differential.py
  - tests/architecture/test_layer_deps.py
acceptance_source: adr
language_source: en
---

# ADR-054 Notebook Dependency Analysis — A Cell Table, A Graph, And A Runtime Check

## 1. Change Summary

An explore session keeps a notebook, and ADR-054 §6.1 names the problem a
notebook brings: a person edits a cell, re-runs it, and every cell below keeps
showing a number computed from the old value, with nothing on screen saying so.
The ADR's answer is a dependency graph over the cells, with written order as the
authority so that a variable name can be reused the way these users already
write. Four things in the design consume that graph: marking what a re-run makes
stale and what a re-run read out of order, choosing the backward slice a
packaged block executes, telling the panel layer which names changed, and
drawing the dependency view.

The graph never changes how the notebook executes. Execution semantics are
Jupyter's: a cell reads whatever the kernel namespace holds at that moment, and
nothing is rebound or re-run on the graph's account. The graph describes,
marks, and selects.

This spec defines the analysis that produces the graph. It is a table with one
row per cell. **What a cell reads** is found statically, by reading the source:
the names it references at module scope. **What a cell changes** is observed:
when the cell runs, the kernel fingerprints every top-level name before and
after, and the names whose fingerprint changed, appeared, or disappeared are
the cell's changed set. That set is exact, and it needs no guessing about
in-place mutation, aliasing, or what a helper does to its argument. For a cell
that has not run yet, the names it assigns in the source stand in as the
estimate; once the cell has run, the observation is the record, and the graph
uses the union of the two so that an observation can only add.

From the table and the notebook's cell order, the graph follows by one rule: a
cell that reads a name depends on the nearest enabled cell above it that
changes that name. The **unit is the cell**, so the table makes no claim about
statement order inside a cell or about which branch of a conditional runs. The
static estimate **guarantees one direction only**: it never omits an assignment
the code shows, and it may name one that execution would not perform. Every
consumer tolerates an extra edge; a missing edge is what produces the stale
number the ADR was written to remove.

The analysis is pure Python over the standard library, with no dependency on
IPython, and reads or writes nothing except the record it defines for the
notebook's cell metadata. It is specified before the session that hosts it so
that the explore-session spec and the explore-frontend spec build against a
fixed API rather than each inventing a private version of it.

## 2. User Scenarios & Testing

### User Story 1 - A re-run marks exactly what it can affect (Priority: P1)

A person changes the filter in cell 2 and re-runs it. Cells 3, 4, and 6 below
it, which use the filtered frame, are marked stale. Cell 5, which loads an
unrelated lookup table, is untouched. Nothing runs by itself.

**Why this priority**: This is the correctness problem ADR-054 §6.1 was
written to remove, and the one the other consumers are built on. If the
downstream set is wrong, the slice and the panel refresh are wrong with it.

**Independent Test**: Analyse a fixture notebook whose cells bind and read
names in a known pattern. Ask for the downstream set of a cell. Confirm it
contains every cell that transitively reads a name the cell changes and no
cell that does not.

**Acceptance Scenarios**:

1. **Given** a notebook where cell 2 changes `df` and cells 3 and 4 read it,
   **When** the downstream set of cell 2 is requested, **Then** it contains
   cells 3 and 4 and every cell that transitively reads what they change.
2. **Given** a cell that reads a name changed by two earlier cells, **When** the
   graph is built, **Then** the cell depends on the nearer of the two and on no
   other.
3. **Given** a cell that both reads and changes `df`, **When** the graph is
   built, **Then** the cell's read of `df` resolves to the cell above it that
   changes `df` and never to the cell itself.
4. **Given** cells A, B, and C that each change `df` in written order,
   **When** the session asks which cell defines the `df` that B reads,
   **Then** the answer is A, so the session can mark B out of order if the
   namespace currently holds C's value.
5. **Given** the built graph, **When** version nodes are requested,
   **Then** there is one node for each name each cell changes, and the edges
   between version nodes agree with the edges between cells.

### User Story 2 - A packaged block executes what the outputs need, including a cell that mutates in place (Priority: P2)

A notebook is packaged into a block. It holds a load, a filter, a
`dropna(inplace=True)`, a peak finder, a `df.head()` the person left in, and an
output declaration. The packaged block's run executes the load, the filter, the
in-place drop, the peak finder, and the output declaration. It skips the
`head()` call.

**Why this priority**: This is ADR-054 §6.7, and it is where a missed edge does
the most damage: a packaged block's run that skips the in-place cell produces a
different result from the session the person approved, and nothing fails
loudly. It ranks below Story 1 because it is the slice query over the same
graph.

**Independent Test**: Run the six-cell fixture once so that every cell carries
an observation, ask for the backward slice of the output cell, and confirm the
slice is cells 1, 2, 3, 4, and 6 in written order. Repeat with the in-place
call replaced by a subscript assignment, by a call to a mutating library
function, and by a call to a helper that mutates its parameter, and confirm the
mutating cell is in the slice each time.

**Acceptance Scenarios**:

1. **Given** the six-cell fixture after one run, **When** the backward slice of
   the output cell is requested, **Then** it contains cells 1, 2, 3, 4, and 6 in
   written order and does not contain cell 5.
2. **Given** a cell containing `df.dropna(inplace=True)`, **When** it has run,
   **Then** its observed changed set contains `df` and the cell is a definer
   of `df` in the graph.
3. **Given** a cell containing `df['x'] = df.a * 2`, **When** it has run,
   **Then** its observed changed set contains `df`.
4. **Given** a cell calling `clean(df)` where `clean` mutates its argument,
   **When** it has run, **Then** its observed changed set contains `df`, and
   the cell carries a diagnostic saying it changed `df` without an assignment
   showing it.
5. **Given** a slice whose cells read a name that no enabled cell changes,
   **When** the slice is returned, **Then** the unresolved reads are listed
   with it, so packaging can refuse a notebook that would fail with a name
   error.

### User Story 3 - What a cell changes is observed, never guessed (Priority: P3)

A person calls `normalise(df)` from their own package. The function modifies
`df` in place and returns nothing. When the cell runs, the system sees that
`df` changed, tells the person that cell 4 modified `df` without the code
showing it, and from then on treats cell 4 as a cell that changes `df`.

**Why this priority**: This is the mechanism that makes Story 2 true without a
list of mutating methods that would be wrong at the margins forever. It ranks
below Story 2 because it is the means and Story 2 is the end.

**Independent Test**: Fingerprint a frame, mutate it in place, fingerprint it
again, and confirm the two differ. Fingerprint it twice without mutation and
confirm they match. Feed a before-and-after namespace pair for a cell whose
static assignments do not include the changed name into the comparison, and
confirm an observed change is produced, recorded on the cell against its
source hash, and counted as a definition in the next graph build.

**Acceptance Scenarios**:

1. **Given** a name whose fingerprint after the run differs from its
   fingerprint before, **When** the comparison runs, **Then** the name is in
   the cell's observed changed set.
2. **Given** a name that appears or disappears from the namespace during the
   run, **When** the comparison runs, **Then** the name is in the observed
   changed set.
3. **Given** an observed change to a name the cell's static assignments do not
   include, **When** the graph is rebuilt, **Then** the cell is a definer of
   that name and cells below that read the name depend on it.
4. **Given** a recorded observation, **When** the cell's source is edited,
   **Then** the observation is discarded and the static estimate alone governs
   until the cell runs again.
5. **Given** a name whose type the fingerprint cannot inspect, **When** the
   cell runs, **Then** the name is reported as unobservable once for that
   cell, so the person knows the observation does not cover it.
6. **Given** an observation, **When** the graph is rebuilt, **Then** no
   static edge has been removed; the observation only adds.

### User Story 4 - The person switches between alternatives by disabling cells (Priority: P4)

A notebook has two candidate filters in cells 2 and 3 and a peak finder in
cell 4 that reads the filtered frame. The person disables cell 3, and cell 4
now depends on cell 2. They disable cell 2 and enable cell 3, and cell 4 now
depends on cell 3. Neither filter is deleted.

**Why this priority**: A linear notebook cannot otherwise express that two
cells are alternatives rather than steps, and the owner chose enabling and
disabling as the mechanism because it needs no new concept in the graph. It
ranks below Story 3 because it is a filter over the same rule.

**Independent Test**: Analyse a fixture with two alternative definitions of a
name and one reader. Toggle the enabled flag on each definer in turn and
confirm the reader's edge follows the nearest enabled definer above it.

**Acceptance Scenarios**:

1. **Given** cells 2 and 3 both change `df` and cell 4 reads it, **When** cell 3
   is disabled, **Then** cell 4 depends on cell 2.
2. **Given** the same notebook, **When** cell 2 is disabled and cell 3 enabled,
   **Then** cell 4 depends on cell 3.
3. **Given** a disabled cell, **When** the downstream set of a cell above it is
   requested, **Then** the disabled cell is not in it and nothing depends on it.
4. **Given** a disabled cell that was the only definer of a name, **When** the
   backward slice of a reader is requested, **Then** the read is listed as
   unresolved.

### User Story 5 - The analysis never gets in the way of the notebook (Priority: P5)

A person types `%pip install scikit-image` in one cell, leaves a half-written
cell with a syntax error in another, and opens the notebook in Jupyter to show
a colleague. The analysis handles the magic line, marks the broken cell without
blocking any other, and the record it keeps in the notebook is invisible to
Jupyter.

**Why this priority**: The users this feature targets are Jupyter-fluent and
will type magics whether or not they are supported, and an analysis that
raises on a half-written cell would make the notebook unusable while it is
being written. It ranks last because it is verified by the absence of
failures rather than by a result.

**Independent Test**: Analyse cells containing a line magic, a shell line, a
cell magic, a star import, and a syntax error. Confirm none raises, each
carries the expected flag, and the remaining cells are analysed normally.
Round-trip the record through the notebook's cell metadata and confirm the
graph rebuilt from the loaded record equals the graph built from source.

**Acceptance Scenarios**:

1. **Given** a cell whose first line is `%pip install x` and whose second line
   assigns `df`, **When** it is analysed, **Then** its static estimate includes
   `df` and it carries no error flag.
2. **Given** a cell beginning with `%%time`, **When** it is analysed,
   **Then** its static estimate is empty, it reads nothing, and it carries the
   opaque-cell-magic flag.
3. **Given** a cell that does not parse, **When** the notebook is analysed,
   **Then** that cell carries the syntax-error flag with the parser's message
   and every other cell is analysed as if it were absent.
4. **Given** a cell containing `from numpy import *`, **When** a later cell
   reads a name no enabled cell changes, **Then** the read resolves to the
   star-import cell.
5. **Given** a record written to cell metadata, **When** the notebook is
   loaded and the graph rebuilt, **Then** it equals the graph built from the
   cells' source and observations, and a record whose source hash no longer
   matches its cell is discarded and recomputed.

### Edge Cases

- **A cell binds a name and reads it, with the read written first.**
  `df = df.dropna()` reads the `df` above and changes `df`. The cell-level
  rule already handles this: the read resolves to the nearest definer above,
  never to the cell itself.
- **A cell binds a name and then reads it, with the bind written first.**
  `df = load(); df.head()` is recorded as reading `df`, so if a cell above
  changes `df` an edge is drawn that execution would not need. This is the
  accepted price of not modelling statement order: dropping the read would be
  correct here and wrong for `if flag: df = load()` followed by `df.head()`,
  and the analysis cannot tell the two apart without modelling control flow.
- **A cell assigns a name only on a branch that is not taken.**
  `if flag: df = load()` with `flag` false. The static estimate says the cell
  changes `df`; the observation says it did not. The changed set is the union,
  so the edge stays. An extra edge is the safe direction.
- **A name is read that nothing changes.** Builtins, names a kernel injects,
  and names bound by code the analysis cannot see fall here. The read is
  recorded as unresolved and draws no edge, except that Python's builtins are
  not reported. The slice query lists unresolved reads so the consumer can
  decide whether they matter.
- **A cell deletes a name.** `del df` removes the name from the namespace; the
  observation records `df` as changed, so readers below depend on it. Running
  them fails with a name error, which is the loud failure the model relies on.
- **Two names are changed in one cell by one statement.** `a, b = f()`
  changes both, and each is a separate version node for the same cell.
- **A fingerprint changes without a mutation.** An object whose content
  depends on state the cell did not touch — a generator, an open handle, an
  object with a random component in its representation — would produce false
  observations. The fingerprint therefore inspects content only for the
  container and array types it knows and falls back to identity for
  everything else, reporting the name as unobservable rather than guessing.
- **A fingerprint samples above the bound and misses a change.** A single
  element changed in a large array outside the sampled positions is not seen.
  The bound is chosen so that ordinary frames are hashed whole, the sample
  spans the full extent, and the case is stated rather than hidden.
- **The notebook is large.** Analysis is one pass over the cells with a
  running map from name to latest enabled definer, so cost is linear in cells
  and names. The success criteria carry a measured bound.

## 3. Requirements

### Functional Requirements

**Granularity and the one guarantee**

- **FR-001**: The unit of analysis MUST be the cell. The graph's execution
  unit is the cell, and the analysis MUST make no claim about statement order
  inside a cell, about which branch of a conditional executes, or about the
  internals of a nested scope beyond the names that scope reads from or
  assigns to the module scope.
- **FR-002**: The static estimate of what a cell changes MUST NOT omit an
  assignment the code shows, and MAY name one that execution would not
  perform. The changed set the graph uses for a cell MUST be the union of the
  static estimate and the observation of FR-026, so that an observation can
  add a definer and never remove one. Every rule in this spec whose outcome is
  uncertain MUST resolve toward the extra edge.
- **FR-003**: The analysis MUST depend on the standard library only. It MUST
  NOT depend on IPython, on a notebook format library, or on any static
  analysis package.
- **FR-004**: The analysis MUST be pure: source, cell order, and recorded
  observations in; facts and graph out. It MUST NOT execute code, hold a
  kernel, or touch the filesystem. The fingerprint function is likewise pure
  over the object it is given.

**Per-cell static facts**

- **FR-005**: For each cell the analysis MUST record the top-level names the
  cell assigns, as the estimate of what it changes before it has run,
  recognising at least: assignment targets including tuple, star, and
  annotated forms; walrus targets at module scope; augmented assignment;
  `for`, `with ... as`, and `except ... as` targets; names introduced by
  `import` and `from ... import`; function and class definitions; and `del`
  targets. A name bound only inside a nested scope MUST NOT count as assigned
  by the cell that defines the scope.
- **FR-006**: For each cell the analysis MUST record the names the cell reads
  at module scope, including names read inside a nested scope that resolve to
  the module scope. A name the cell also assigns MUST still be recorded as
  read, because the analysis does not model whether the read precedes the
  assignment.
- **FR-007**: The static facts MUST NOT attempt to recognise in-place
  mutation, aliasing, or the effects of a called function. What a cell changes
  beyond its assignments is established by the observation of FR-024 to
  FR-030 when the cell runs. The analysis MUST carry no list of mutating
  methods or functions.
- **FR-008**: The analysis MUST record, for each cell, whether it calls
  `scistudio.output`, and the keyword names and argument names of each such
  call. A cell with such a call is an output cell.
- **FR-009**: The analysis MUST record, for each cell, each string literal
  passed as the first argument to `scistudio.input`, so the session can check
  declared inputs against the block's ports at packaging.
- **FR-010**: The analysis MUST record, for each cell, the block identifier
  passed as a string literal to a block call, and MUST flag a block call whose
  identifier is not a literal as an unknown block call.
- **FR-011**: A line whose first non-blank character is `%` or `!` MUST be
  removed before parsing and MUST NOT by itself produce an error flag. A cell
  whose first non-blank line begins with `%%` MUST be recorded as opaque:
  assigning nothing, reading nothing, and carrying the opaque-cell-magic flag.
- **FR-012**: A cell that does not parse MUST be recorded as assigning
  nothing, reading nothing, and carrying the syntax-error flag with the
  parser's message and position. It MUST NOT prevent any other cell from being
  analysed.
- **FR-013**: A cell containing a star import, or a `%run` line, MUST be
  recorded as changing an unknown set of names. A read that resolves to no
  enabled definer MUST resolve to the nearest such cell above it, if one
  exists, before being recorded as unresolved.

**The graph**

- **FR-014**: The graph MUST be built over enabled cells only. A disabled cell
  neither defines nor reads. The enabled flag is owned by the notebook and
  stored in cell metadata; the analysis reads it and never writes it.
- **FR-015**: A cell that reads a name MUST depend on the nearest enabled cell
  above it whose changed set contains that name. A cell MUST NOT depend on
  itself. A read with no enabled definer above it MUST be recorded as
  unresolved, except that a read of a name in Python's builtins namespace draws
  no edge and is not recorded as unresolved, so the list stays about names a
  run would fail on.
- **FR-016**: The graph MUST expose version nodes, one for each name in each
  enabled cell's changed set, with edges between versions derived from the
  same facts as the edges between cells. The cell-level graph is the execution
  unit; the version-level graph is what the dependency view renders.
- **FR-017**: The graph MUST be a deterministic function of the cells' source,
  their order, their enabled flags, and their recorded observations. It MUST
  NOT depend on execution history except through recorded observations.
- **FR-018**: Building the graph MUST be linear in the number of cells and the
  number of names, with a measured bound stated in §5.
- **FR-019**: Each edge MUST carry its origin: a static assignment, an
  observed change, or an unknown-binding resolution. The origin is what lets
  the view and the diagnostics say why an edge exists.

**The queries**

- **FR-020**: The graph MUST answer, for a cell, the set of enabled cells that
  transitively read a name in that cell's changed set, in written order. This
  is what the session marks stale after a re-run.
- **FR-021**: The graph MUST answer, for a set of cells, the backward slice:
  those cells and every enabled cell they transitively depend on, in written
  order, together with the unresolved reads inside the slice. This is what a
  packaged block executes and what packaging checks before it accepts a
  notebook.
- **FR-022**: The graph MUST answer, for a cell, its changed set: the union of
  its static estimate and its observation. This is what the panel layer uses
  to decide which bound names to refresh, and what the session uses to bound
  the freeze while the cell is queued.
- **FR-023**: The graph MUST answer, for a cell and a name it reads, which
  enabled cell above it the written order says defines that name, or that
  none does. This is what the session compares against the cell that last
  bound the name in the kernel, to mark a re-run that read a later version as
  out of order. The graph itself MUST NOT act on the comparison.

**Runtime observation**

- **FR-024**: A fingerprint function MUST be provided that maps an object to a
  value that is equal for an unchanged object and differs, within the stated
  bound, for an object mutated in place. It MUST inspect content for numpy
  arrays, pandas frames and series, lists, tuples, dicts, sets, strings,
  bytes, and numbers, and MUST fall back to identity for any other type with
  the result marked unobservable.
- **FR-025**: The fingerprint's cost MUST be bounded by a declared constant.
  Below the bound the whole content is hashed; above it the content is sampled
  at fixed strides across its full extent together with its shape, dtype, and
  length. The constant and the sample size MUST be declared in one place.
- **FR-026**: A comparison function MUST be provided that takes the
  fingerprints of every top-level name in the module namespace before and
  after a cell ran and reports the cell's observed changed set: names whose
  fingerprint differs, names that appeared, and names that disappeared. The
  call around execution is specified by the explore-session spec.
- **FR-027**: An observation MUST be recorded on the cell keyed to the hash of
  the cell's source at the time of the run. It MUST be discarded when the
  cell's source hash changes, so that the static estimate alone governs until
  the cell runs again.
- **FR-028**: An observed change to a name the cell's static estimate does not
  include MUST produce a diagnostic naming the cell and the name, with a
  message stating that the cell changed the name without an assignment
  showing it. The record and the message are defined here; where the message
  is shown is the explore-frontend spec's.
- **FR-029**: A name whose fingerprint fell back to identity MUST be reported
  as unobservable once per cell run, so the person knows the observation does
  not cover it.
- **FR-030**: An observation MUST only add to a cell's changed set. It MUST
  NOT remove a name the static estimate includes.

**Storage**

- **FR-031**: The per-cell record MUST be stored under the `scistudio` key of
  the cell's metadata, holding the static facts, the flags, the source hash
  they were computed from, and the observation with its own source hash. A
  notebook-level record under the same key MUST hold the analysis version.
- **FR-032**: Edges MUST NOT be stored. The graph MUST be recomputed on load
  from the records. A record whose source hash does not match its cell's
  source MUST be discarded and the cell re-analysed.
- **FR-033**: The record MUST use only JSON-serialisable primitives. Keys the
  analysis does not recognise MUST be preserved on rewrite, so that another
  tool's metadata under the same key survives.
- **FR-034**: Reading and writing the record MUST use the standard library's
  JSON handling of the notebook's cell metadata. Loading and saving the
  notebook file is the explore-session spec's; this spec defines the record
  and its codec.

**Boundaries**

- **FR-035**: The analysis and fingerprint modules MUST import from the
  standard library and, lazily and only inside the fingerprint, numpy and
  pandas. They MUST import nothing from SciStudio beyond stability markers.
  The architecture layer test MUST enumerate the new subsystem and verify the
  constraint.
- **FR-036**: Every flag the analysis can raise MUST be a member of one
  enumeration with a human-readable message, and the enumeration MUST contain
  exactly the flags named in this spec: syntax error, opaque cell magic,
  unknown bindings, unknown block call, unpredicted change, unobservable
  name, and unresolved read.

### Key Entities

- **CellFacts** — the static result for one cell. Attributes: cell id, source
  hash, assigned names (the estimate), read names, output declarations, input
  declarations, block calls, flags. Relationships: one per cell; input to
  DependencyGraph together with the cell's ObservedChange; serialised into
  AnalysisRecord.
- **DependencyGraph** — the cell-level graph over enabled cells. Attributes:
  cells in written order, edges with origins, unresolved reads, version nodes.
  Relationships: built from a sequence of CellFacts, enabled flags, and
  ObservedChanges; answers the four queries.
- **Edge** — a dependency from a reading cell to a defining cell for one name.
  Attributes: reader, definer, name, origin. Relationships: belongs to one
  DependencyGraph; origin is one of the values in FR-019.
- **VersionNode** — one name changed by one cell. Attributes: cell id, name.
  Relationships: derived from the changed set; rendered by the dependency
  view.
- **SliceResult** — the answer to a backward-slice query. Attributes: cells in
  written order, unresolved reads. Relationships: consumed by a packaged
  block's run and by the check packaging performs.
- **Fingerprint** — the value the fingerprint function returns. Attributes:
  digest, observable flag, the type it was computed for. Relationships:
  compared pairwise by the comparison function.
- **ObservedChange** — what a cell was seen to change when it ran. Attributes:
  cell id, changed names, unobservable names, source hash at the time of the
  run. Relationships: recorded in AnalysisRecord; joined to the cell's changed
  set by DependencyGraph; discarded when the source hash changes.
- **AnalysisRecord** — the JSON shape stored in cell metadata. Attributes: the
  CellFacts fields, the ObservedChange, analysis version. Relationships:
  written and read by the codec; owned by the notebook file that the
  explore-session spec loads and saves.
- **AnalysisFlag** — the closed enumeration of FR-036. Attributes: name,
  message template. Relationships: carried by CellFacts and by Edge origins.

## 4. Implementation Plan

### 4.1 Technical Approach

**Two standard-library tools, each for what it is good at.** The assigned and
read sets come from `symtable`, which reports for the module scope every name
that is assigned or imported and every name that is referenced, and for each
nested scope which names resolve to the module scope. This is exactly the
cell-level fact FR-005 and FR-006 ask for, and it handles nested functions,
comprehensions, and `global` declarations without the analysis re-deriving
Python's scoping rules. Output declarations, input declarations, and block
calls need the shape of a call rather than the fate of a name, and come from a
single walk over the `ast`. Neither tool needs a third-party dependency, and
neither executes anything.

**Why the cell and not the statement.** Statement-level versioning would let
`df = load(); df.head()` avoid a read edge. It would also require deciding what
`if flag: df = load()` assigns, which is a control-flow question the analysis
cannot answer without modelling execution. Cell granularity sidesteps the
question and its cost is a handful of extra edges in a direction every
consumer tolerates. ADR-054 §6.1 states the cell as the unit.

**Why what a cell changes is observed rather than recognised.** The first draft
of this spec carried a list of mutating methods, a list of mutating functions,
alias tracking, and an analysis of helper bodies, all to guess statically
which names a cell would mutate in place. Every one of those lists is wrong at
the margins forever, and none of them can see a helper imported from outside
the notebook. The kernel already has the answer: after the cell runs, the
namespace shows what changed. Fingerprinting every top-level name before and
after a run costs milliseconds with sampling and is exact within the
fingerprint's bound, and it covers assignment, in-place mutation, aliasing,
deletion, and mutation through any function whatsoever. The static
assignments remain as the estimate for a cell that has not run, which is the
only time an estimate is needed: a cell that has never run is neither stale
nor packageable, so a missed edge in that window has no consequence.

**Why the changed set is a union.** An observation could in principle replace
the static estimate, and for a conditional assignment on a branch not taken it
would remove an edge that execution did not need. It is kept as a union so
that an observation can only add. The one way an observation could be wrong is
a sampled fingerprint missing a change in a very large object, and a union
means that miss can at worst leave the graph where the static estimate put it.

**The graph describes; it never executes.** Execution semantics are Jupyter's:
a cell reads whatever the namespace holds when it runs. The graph's role is to
say what written order implies — which cell should have defined a name, what a
re-run makes stale, what a packaged block needs — and to hand that to the
session, which marks and never rebinds. FR-023 exists for exactly one
consumer: the session compares the graph's definer with the cell that last
bound the name in the kernel and marks the re-run out of order when they
differ. The graph does not know what the kernel holds and does not need to.

**Why the observation is keyed to the source hash.** An observation says what
a particular version of a cell did when it ran. Once the cell is edited the
statement is about code that no longer exists; keeping it would draw an edge
for a change that may have been removed. Discarding it costs nothing, because
an edited cell is stale and must run again, and the next run observes afresh.

**Why edges are not stored.** The graph is a deterministic function of the
cell sources, their order, their enabled flags, and their observations, all
of which the notebook already holds. Storing edges would create a second copy
that can disagree with the first, and the per-cell records are what
`.ipynb`'s metadata field is designed to carry. Recomputing on load is one
linear pass.

**Why no IPython.** ADR-054 §6.2 states that magics are stripped rather than
transformed. IPython's input transformer turns `%time x = f()` into a call
whose argument is the string `'x = f()'`, so the assignment is no more visible
to `ast` after the rewrite than before. The rewrite solves parseability, and
stripping the line solves parseability equally without adding a dependency to
a module that otherwise needs none. A line magic that wraps an assignment is a
missed static estimate either way; the observation records the assignment when
the cell runs.

**Fingerprints by type.** Arrays hash their bytes through the `xxhash`
dependency SciStudio already carries; frames hash their numeric blocks the
same way and sample their object columns; containers hash their elements
recursively. Everything is bounded by one declared size, above which a strided
sample across the full extent replaces the whole-content hash. Types the
fingerprint does not know fall back to identity and are reported as
unobservable, because a fingerprint that guessed from `repr` would produce
false observations for anything with a random or stateful representation, and
a false observation is noise the person would learn to ignore. The existing
`content_hash` helper in `scistudio.utils.hashing` is unsuitable for this use:
it hashes arrays whole with no bound and falls back to `repr`.

**Placement.** The two modules are the first contents of the `scistudio.explore`
package that ADR-054's `planned_governs` names. They sit in a new subsystem
because nothing existing owns notebook analysis, and they import nothing from
SciStudio beyond stability markers so that the session, the API layer, and
the kernel adapter can all import them without a layering question. The
architecture layer test enumerates subsystems and must gain this one; that is
a task in §4.3 rather than a surprise.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/specs/adr-054-notebook-dependency-analysis.md` | create | This spec. |
| `src/scistudio/explore/__init__.py` | create | The new subsystem's package; public surface for the analysis and the fingerprint. |
| `src/scistudio/explore/dependency_analysis.py` | create | Per-cell static facts, the graph, the four queries, the flag enumeration, the metadata codec (FR-005 to FR-023, FR-031 to FR-034, FR-036). |
| `src/scistudio/explore/fingerprint.py` | create | The fingerprint function, the namespace comparison, and the observation record (FR-024 to FR-030). |
| `tests/explore/test_dependency_analysis.py` | create | Every assignment form, magics, syntax errors, star imports, enabled flags, the four queries, the codec. |
| `tests/explore/test_fingerprint.py` | create | Per-type fingerprints, the size bound, the namespace comparison, unobservable fallback, source-hash invalidation. |
| `tests/explore/test_analysis_differential.py` | create | Executes fixture notebooks in a subprocess with observation, then runs the backward slice of the declared outputs on a cold namespace and compares outputs. |
| `tests/explore/fixtures/**` | create | Fixture notebooks as `.ipynb` JSON, including the six-cell notebook of Story 2 and its three mutation variants. |
| `tests/architecture/test_layer_deps.py` | modify | Subsystem enumeration gains `explore`; the import constraint of FR-035 is asserted. |

### 4.3 Implementation Sequence

| Task | Title | Story | Depends on | Verification |
|---|---|---|---|---|
| T-001 | Create the `explore` package and add it to the layer enumeration | Foundation | — | Layer test passes with the new subsystem and asserts the import constraint |
| T-002 | Compute assigned and read names per cell through `symtable` | US1 | T-001 | One test per assignment form in FR-005; nested-scope reads resolve to module scope |
| T-003 | Strip magic and shell lines; mark opaque cells, syntax errors, and unknown bindings | US5 | T-002 | No fixture raises; each carries its flag; other cells unaffected; star import resolves otherwise-unresolved reads |
| T-004 | Record output declarations, input declarations, and block calls | US2 | T-002 | Literal ids recorded; non-literal block call flagged |
| T-005 | Build the graph over enabled cells with unresolved reads, version nodes, and edge origins | US1, US4 | T-003, T-004 | Nearest-enabled-definer rule; builtins excluded from unresolved; disabled cells absent; version nodes agree with cell edges |
| T-006 | Implement the four queries | US1, US2 | T-005 | Downstream, slice, changed set, and definer tests over the fixtures |
| T-007 | Implement the fingerprint with the size bound and the unobservable fallback | US3 | T-001 | Per-type change detection; unchanged equality; bound respected; fallback reported |
| T-008 | Implement the namespace comparison and the observation record with source-hash invalidation | US3 | T-006, T-007 | Changed, appeared, and disappeared names reported; observation joins the changed set; discarded on source change; static edges never removed; unpredicted-change diagnostic produced |
| T-009 | Implement the metadata codec | US5 | T-008 | Round trip yields an identical graph; mismatched hash triggers re-analysis; unknown keys preserved |
| T-010 | Build the differential test harness and fixtures | US2, US3 | T-008 | Slice outputs equal whole-notebook outputs across fixtures |
| T-011 | Apply stability markers to the public symbols | Foundation | T-009 | Every public symbol carries a tier and a since version; the frozen surface inventory is unchanged because the package is not a canonical root |

### 4.4 Verification Plan

Unit coverage is organised by rule. Every assignment form in FR-005 has its own
test, because the static estimate is a list of forms and a form with no test is
one that silently stops matching when the `ast` shape changes across Python
versions. The enabled-flag filter, each query, and each flag in FR-036 are
tested the same way.

The observation is tested per type with a real mutation of each and with a
name that appears and a name that disappears, and its cost is measured against
the declared bound on the largest fixture, because a fingerprint that takes
longer than the cell it follows would be removed by the first person who
noticed.

The differential test is what defends the slice. It executes each fixture
notebook cell by cell in a subprocess with the observation running, records
the declared outputs, then executes only the backward slice of the output
cells on a fresh namespace and records the outputs again. The two MUST be
equal. A difference means the slice omitted a cell whose effect the outputs
depend on, which is exactly the failure Story 2 exists to prevent, and it
fails the test outright. The fixtures include the in-place, subscript, library
function, and helper variants so that each is proven to be caught by the
observation rather than assumed.

The codec is tested by round trip: analyse from source, add observations,
write the records, load them, rebuild, and compare graphs. Performance is
measured on a generated notebook of several hundred cells and recorded against
SC-010.

Lint, type, and format checks run as usual. The architecture layer test is
expected to fail until T-001, which is why it is sequenced first.

### 4.5 Risks And Rollback

**The static estimate is coarser than people will accept.** If the extra
edges pile up — every display cell depending on every definer above it — the
stale marks stop meaning anything. The edge origins of FR-019 let the view
explain an edge instead of leaving the person to guess, and the observation
replaces guesswork with fact for every cell that has run. If the estimate is
too coarse in practice the answer is a narrower rule with its own test, never
a rule that drops edges.

**The fingerprint samples above the bound and misses a change.** A single
element changed in a large array outside the sampled positions is not
detected. The bound is chosen so that ordinary frames are hashed whole, the
sample spans the full extent, and the case is stated rather than hidden. The
union of FR-002 means a miss can at worst leave the graph where the static
estimate put it.

**The fingerprint reports a change that was not one.** The mitigation is the
type allowlist: content is inspected only for types whose content is the
value, and everything else falls back to identity with an unobservable
report. A false observation adds an edge, which is the safe direction, but a
stream of them would teach people to ignore the diagnostic.

**Fingerprinting the whole namespace grows with the namespace.** A session
with hundreds of names pays hundreds of fingerprints per run. Each is bounded
and most names are small or fall back to identity, so the cost stays in
milliseconds; SC-007 measures it on the largest fixture.

**Python's `ast` and `symtable` shapes change across versions.** The bundled
runtime pins one interpreter, and the per-form tests are what surface a change
when the runtime is upgraded.

**Rollback.** Both modules are pure and have no consumers until the
explore-session spec lands, so reverting is deleting the package and its tests
and restoring the layer enumeration. Once the session consumes the graph,
rollback of the analysis means rollback of the session; that is the session
spec's concern and the reason this spec lands first.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: Every assignment form named in FR-005 has a test that fails if
  the form stops being recognised. Measured by the presence of the test per
  form.
- **SC-002**: The six-cell fixture of Story 2, after one observed run, yields a
  backward slice of cells 1, 2, 3, 4, and 6 in written order, and the same
  slice for each of its three mutation variants. Measured by test.
- **SC-003**: For every fixture notebook, running only the backward slice of
  the declared outputs on a fresh namespace produces outputs equal to running
  the whole notebook. Measured by the differential test.
- **SC-004**: Disabling a definer moves the reader's edge to the next enabled
  definer above, and disabling the only definer leaves the read unresolved.
  Measured by test.
- **SC-005**: A line magic, a shell line, a cell magic, a star import, and a
  syntax error each produce their flag and none raises. Measured by test.
- **SC-006**: The fingerprint detects an in-place mutation of a numpy array, a
  pandas frame, a pandas series, a list, a dict, and a set, and returns an
  equal value for an unchanged object of each type. Measured by test.
- **SC-007**: Fingerprinting every name in the largest fixture's namespace
  completes within the time bound declared beside the size bound. Measured by
  a timed test.
- **SC-008**: An observed change is counted in the next graph build, is
  discarded when the cell source changes, and never removes a static edge.
  Measured by test.
- **SC-009**: Writing the records to cell metadata and loading them back yields
  a graph equal to the one built from source and observations. Measured by
  round-trip test.
- **SC-010**: Analysing a generated notebook of five hundred cells, each
  assigning and reading a few names, builds the graph in under five hundred
  milliseconds on the CI runner. Measured by a timed test.
- **SC-011**: The two modules import nothing from SciStudio beyond stability
  markers and nothing third-party except numpy and pandas lazily inside the
  fingerprint. Measured by the architecture layer test.
- **SC-012**: The architecture layer test, the architecture drift audit, and
  the frozen public-symbol inventory all pass. Measured by CI.
- **SC-013**: For a cell and a name it reads, the definer query returns the
  nearest enabled cell above whose changed set contains the name, or none.
  Measured by test over the A, B, C fixture of Story 1.

## 6. Assumptions

- **A-001**: The unit of analysis is the cell, as ADR-054 §6.1 states.
  _Source: adr._
- **A-002**: Every consumer of the graph tolerates an extra edge and none
  tolerates a missing one. Stale marking, the packaged block's slice, panel
  refresh, and the dependency view are the consumers ADR-054 names, and each
  is read that way in §1. _Source: adr._
- **A-003**: What a cell changes is observed when it runs rather than
  recognised from the source. The owner chose this over a static list of
  mutating forms on 2026-09-02, on the grounds that the list would be wrong at
  the margins forever and the kernel already knows the answer. ADR-054 §6.2
  states it. _Source: owner._
- **A-004**: The changed set the graph uses is the union of the static
  estimate and the observation, so that an observation only adds.
  _Source: spec._
- **A-005**: Cells can be enabled and disabled, the flag lives in cell
  metadata, the graph is built over enabled cells only, and the control lives
  in the explore-frontend spec. ADR-054 §6.1 states it. _Source: adr._
- **A-006**: IPython's input transformer is not used. Stripping magic lines
  gives the analysis the same information the transformer would, and the
  module otherwise has no dependencies. ADR-054 §6.2 states it. _Source: adr._
- **A-007**: The kernel fingerprints every top-level name in the module
  namespace before and after each cell run and hands both to the comparison.
  The call site, and the kernel itself, are specified by the explore-session
  spec. _Source: spec._
- **A-008**: Reading and writing `.ipynb` cell metadata needs no notebook
  library. The format is JSON, the repository's only existing notebook code
  runs notebooks through `nbconvert` and never parses cells, and the standard
  library suffices for the record. _Source: existing-system._
- **A-009**: `scistudio.explore` is not added to the nine canonical public
  roots of ADR-052 by this spec, so the frozen surface inventory, the generated
  reference, and the documentation navigation are unchanged. Its public symbols
  carry stability markers so that promoting the package to a root later is a
  listing change rather than a decoration pass. Whether to promote it is the
  owner's decision. _Source: inferred._
- **A-010**: Execution semantics are Jupyter's. The graph never rebinds a name,
  never re-runs a cell, and never holds a version of an object; it describes,
  marks, and selects, and the session decides what to do with that. The owner
  rejected version retention with rebinding on 2026-09-02 as contrary to what
  Jupyter users expect. _Source: owner._
