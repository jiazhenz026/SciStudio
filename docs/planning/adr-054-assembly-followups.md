---
title: "ADR-054 Assembly Follow-Up Register"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Assembly Follow-Up Register

> The owner has forbidden new GitHub issues beyond `#2253` and `#2254` for the
> duration of this dispatch, so every deferral, edge case, cleanup and finding
> an agent turns up is written here instead. A `TODO(#2253)` or `TODO(#2254)`
> in the code cites this file and the agent's heading; an untracked "later" is
> a gate failure.
>
> Each agent edits only its own section.

## S4-A1

Owner: the Explore tab union member, the `exploreSlice`, the API types, the
WebSocket event routing, the layout swap, and the two context menus
(ADR-054 spec 4, T-001 to T-003).

### F-A1-001 — The packaged-notebook marker is not on the wire

`src/scistudio/explore/packaging.py` writes `notebook_filename` and
`notebook_commit` as `ClassVar`s on the generated block class, but
`scistudio.api.schemas.BlockSummary` carries neither and
`src/scistudio/api/routes/blocks.py::_summary` reads neither. Nothing the
frontend receives therefore says a block was packaged from a notebook.

Two requirements of spec 4 need that answer: FR-004 (double-clicking a
packaged block's node opens its notebook) and FR-030 (the node's notebook
badge, S4-A4's). Both are implemented against one predicate,
`isPackagedNotebookBlock` in `frontend/src/explore/packagedBlock.ts`, which
reads an optional `notebook_filename` on `BlockSummary` that the backend does
not send yet. Until it does, the predicate answers `false` for every block, the
canvas double-click keeps its pre-ADR-054 behaviour, and no speculative request
is sent.

Deliberately not worked around. Guessing "packaged" from the block's origin
tier plus a sibling `.ipynb` on disk would be a second definition of what a
packaged block is, and it would disagree with `packaging.py` the first time
somebody hand-writes a block beside a notebook.

**Fix**: add `notebook_filename` (and probably `notebook_commit`) to
`scistudio.api.schemas.BlockSummary` and read them in `_summary` with
`getattr(spec, ..., None)`, as `panel_manifest` and `ui_icon` already are. That
is a `src/scistudio/**` change, which no agent in this dispatch may make.

Cited by: `frontend/src/explore/packagedBlock.ts`,
`frontend/src/types/api.ts` (`BlockSummary.notebook_filename`).

### F-A1-002 — The spec calls the "no kernel" state `none`; the runtime calls it `not-started`

Spec 4 FR-016 lists the kernel states the shell must show as "none, starting,
idle, busy, dead, needs restart". The landed runtime's `KernelState`
(`src/scistudio/explore/kernel.py`) is
`"not-started" | "starting" | "idle" | "busy" | "dead"`, and `needs_restart` is
a separate boolean beside it rather than a sixth state.

The slice stores what the runtime sends, verbatim, and never collapses the flag
into the state — `SessionToolbar.kernelLabel` does that collapse at render
time, which is the one place a person is being told one thing. So the behaviour
matches the spec's intent; only the spec's word for the first state differs
from the wire's.

**Fix**: a one-word correction in the spec (`none` → `not-started`), which is a
`docs/specs/**` change and out of every agent's write set in this dispatch.

### F-A1-003 — A buffered event stream for an unknown session is dropped silently

`exploreSlice` buffers events whose `session_id` it has no notebook path for
yet, because `session_opened` is published inside the open call and can reach
the socket before the POST response reaches the caller. The buffer is capped at
`PENDING_EVENT_CAP` (200) per session id; past the cap, events are dropped with
no report.

A stream that never resolves is a bug elsewhere (an open that failed after the
runtime published, a session id the frontend never learns about), and the cap
keeps it from becoming a memory leak here. But dropping silently means that
bug shows up as a stale notebook rather than as itself.

**Fix**: log once per session id at the cap, and consider surfacing it on the
tab as a "this session is out of sync, reload" state.

Cited by: `frontend/src/store/exploreSlice.ts` (`PENDING_EVENT_CAP`).

### F-A1-004 — Closing an Explore tab leaves its session in the slice and its kernel alive

`closeTab` drops the tab; it does not call `forgetExploreSession`, and it does
not `DELETE /api/explore/sessions/{id}`. That is deliberate for now — reopening
the same notebook is then instant, and a kernel with a person's namespace in it
is not something to end on a tab close without asking — but it means the slice
grows for the life of the page and a kernel can outlive every tab that showed
it.

Spec 4 does not say what closing the tab should do. FR-015's kernel list is the
surface that ends a kernel deliberately, which is an argument for leaving the
close alone; the counter-argument is that a person who closes the tab has no
reason to expect a Python process to still be resident.

**Fix**: settle the intended behaviour with the owner, then either call
`forgetExploreSession` on close, or leave it and say so in the spec.

### F-A1-005 — `frontend/src/types/api.ts` was split for size, not for design

Appending the session API and event payloads to `api.ts` put it over the
repository's `max-lines` rule (750 counted lines). The shapes now live in
`frontend/src/types/explore.ts` and `api.ts` re-exports them with
`export * from "./explore"`, so every existing import path is unchanged and the
spec's affected-files table still describes where a consumer looks.

`api.ts` is close to the limit again on its own. A follow-up should split it by
domain the way `lib/api/` already is (`projects`, `blocks`, `workflows`, `git`,
…) rather than one more sibling per feature.
