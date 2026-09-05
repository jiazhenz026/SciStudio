# Panel example — a producing panel

Draws a `Series`, lets the user drag a region across it, and emits the picked region as one line of code.

`example.series.region_picker` is [panel.json](panel.json) plus
[index.html](index.html). That emission is the whole difference between this
panel and [panel-series-view/](../panel-series-view/), which renders the same
data and declares `displaying`.

## Why `producing`

Declare `producing` when the user is **deciding** something the panel has to
send back: a region, a routing, a pair, a threshold they picked by eye. Two
things make a panel producing, and both are required:

1. `"capability": "producing"` in `panel.json`, and
2. an `emit` message from the document.

The declaration is what the host enforces. An `emit` from a panel mounted for
display is dropped and reported — so you cannot get producing behaviour by
emitting from a panel that declared `displaying`, and you should not declare
`producing` "to keep options open" for a panel that only shows things.

## What to notice

- **What leaves is code, not a value.** The payload of `emit` is a `code`
  string, and it must satisfy the statement whitelist in
  `panel-contract.md` — here, a bare assignment of a literal tuple. Build it
  from numbers the panel computed itself. Never interpolate a string that came
  out of the data payload: that is how a data file gets to write code.
- **Emit the whole decision, every time.** Whatever confirms the pause has only
  the *last* emission to act on. A panel that emitted deltas would leave the
  host holding half a decision. Each emission rebinds the same name, so
  re-emitting the whole thing costs nothing.
- **Emit once per gesture.** This panel emits on `pointerup`, not on every
  `pointermove` — the user made one decision, not two hundred.
- **State survives a remount.** `state_request` returns the picked region, and
  `init` restores it, so reopening a pause shows what the user already chose
  rather than a blank trace.
- **The data can change underneath you.** `adopt()` drops a region that no
  longer indexes into the new series. A stale region silently emitted against
  new data is worse than no region.

## Try it

Copy this folder into `<project>/panels/example.series.region_picker/` (the
directory name is the panel id), then call `reload_panels`. To use it as an
interactive block's pause panel, name the panel id in the block's
`interactive_panel` manifest — see
`.scistudio/agent-reference/block-contract.md`.

The full contract — every message type, the tiers and their shadowing order, and
the statement whitelist in full — is
`.scistudio/agent-reference/panel-contract.md`.
