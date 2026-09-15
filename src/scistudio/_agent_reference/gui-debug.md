---
title: MiniApp visual debugging
status: Active
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
language_source: en
---

# MiniApp visual debugging

The installed SciStudio MCP server provides `screenshot_gui` to local AI
providers such as Claude Code and Codex. It returns an actual PNG image to the
model, together with the selected window, MiniApp, dimensions and observed
readiness. The screenshot is of the SciStudio application, including content
rendered inside MiniApp iframes and canvas surfaces.

After validating a MiniApp with `validate_panel`, open it on completed block
output with `open_miniapp`. With that tab visible, call:

```json
{"target": "miniapp", "panel_id": "my_explorer", "wait_ms": 500}
```

These are arguments for `screenshot_gui`. `panel_id` may be omitted to capture
the visible MiniApp. Supply `context_id` to select a particular mount, and
`client_id` if more than one connected desktop window shows the project. The
error names the matching client ids when that choice is needed. Use
`{"target": "workspace"}` to inspect the full current workspace. The tool never
opens or focuses tabs, starts processes, or manipulates controls.

The image metadata distinguishes loading, ready and error states, and includes
the MiniApp process state and visible error messages. A ready state means the
page called its SDK readiness handshake; inspect the actual image for blank
content, wrong data, clipping and error UI. A screenshot does not prove that a
control works, that Python defaults match current slider values, or that a
result is scientifically correct. When your AI host provides computer use, exercise important controls with that
capability and capture the result again. If computer use is unavailable, explicitly
report that interactions were not verified. SciStudio supplies screenshot_gui only;
it does not supply a separate interaction or inspection automation tool.

Capture is supported by the SciStudio desktop application through local MCP.
A browser-only GUI has no native capture capability, and the external WebMCP
host currently accepts text rather than image content. Those paths return
explicit unsupported errors. A disconnected GUI, hidden MiniApp, project
change, ambiguous window or timeout also produces an actionable error instead
of a stale image. Waits are bounded to five seconds and requests to ten seconds.

Pixels are returned only for the currently authorized project. Project and target
identity are checked before and after capture; a result captured across a project
or tab switch is discarded. Images are bounded to four million pixels and four
MiB of PNG bytes on the tool transport; this is an implementation limit, not a
metric displayed in the MiniApp interface.

## Tool arguments and result

| Argument | Contract |
|---|---|
| `target` | `"miniapp"` (default) or `"workspace"` |
| `panel_id` | Optional exact MiniApp id; only for the MiniApp target |
| `context_id` | Optional exact mounted context id; only for the MiniApp target |
| `client_id` | Optional connected workspace client id; required when several desktop windows match |
| `wait_ms` | Integer 0–5000, default 500; layout delay, not an assertion that the app is ready |

The project comes from the authorized MCP session; no arbitrary project or
filesystem screenshot path is accepted. Success returns MCP `content` containing
one `text` metadata block and one `image` block with `mimeType: "image/png"`.
The MCP client consumes the image directly; do not reinterpret a local filename
or a JSON/base64 string as visual inspection. Metadata includes `target`,
`project`, `client_id`, `width`, `height`, `state`, and for MiniApps the `panel_id`,
`context_id`, `process_state`, and visible `errors`. These observations are not
an exhaustive JavaScript console or Python traceback collector.

For a working rendering surface, use the [reusable core renderers](miniapp-renderers.md).
A user-oriented lifecycle guide is installed as `user-guide/miniapps.md`.
