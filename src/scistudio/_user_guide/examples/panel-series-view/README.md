# Panel example — a displaying panel

`example.series.sparkline` ([panel.json](panel.json), [index.html](index.html))
draws a `Series` as a sparkline with its range underneath. It is the simplest
kind of panel: it **displays**, and sends nothing back.

## Why `displaying`

A panel declares exactly one capability, and the host enforces it:

- **`displaying`** — renders the data. Its only outbound messages are `ready`,
  `state`, and `error`. This example.
- **`producing`** — also renders, and additionally emits a line of code the host
  inserts on the user's behalf. See [panel-region-picker/](../panel-region-picker/).

A producing panel can stand in where a displaying one is asked for; a displaying
panel cannot stand in for a producing one, because there is nothing for it to
emit. Declare `displaying` unless the user is deciding something the panel has
to send back.

## What to notice

- **One file.** Markup, styles, and script all live in `index.html`. There is no
  `<script src>`, no stylesheet link, no CDN, and no shared runtime import. The
  panel is served from its own directory and may reach nothing outside it, so
  there is no build step to run and nothing to bundle.
- **The declaration.** `panel.json` names the panel id, the target types it
  renders, the capability, and the entry document. The registry reads this file
  — a panel is registered by *existing as a directory in a tier*, not by a
  registration call.
- **The handshake.** The host sends `init` with a token; the panel answers
  `ready` and only then trusts messages carrying that token. After that it
  receives `update` when the data changes, `state_request` before it is
  unmounted, and `teardown` when it goes away.
- **`textContent`, never `innerHTML`.** The payload is a person's data, not
  markup. A panel that interpolates it into HTML lets a data file inject nodes
  into the panel that renders it.
- **Degrade, do not throw.** An empty or non-numeric payload renders a line of
  prose; a host `error` renders a card. A panel that throws renders nothing and
  tells the user nothing.

## Try it

Copy this folder into `<project>/panels/example.series.sparkline/` (the
directory name is the panel id), then call `reload_panels`. The panel is offered
for `Series` targets from that point on. Ask the assistant to scaffold one
instead and it writes the same three files plus a harness page you can open in a
browser to see the panel render over stub data.

The full contract — the capability declaration, every message type, the on-disk
layout, the four tiers and their shadowing order, and the statement whitelist a
producing panel's emitted code must satisfy — is
`.scistudio/agent-reference/panel-contract.md`.
