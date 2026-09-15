# GUI visual debugging

## 1. Where to look

| You need | Read |
|---|---|
| Opening, navigating, and operating the running GUI | the `scistudio-use-gui` skill |
| `screenshot_gui` arguments and result | the live MCP tool schema |
| Checking a MiniApp after writing it | the `scistudio-write-miniapp` skill (step 9 and "Checking") |
| Checking a panel after writing it | the `scistudio-write-panel` skill ("Check the result") |
| Checking a plot's figure | the `scistudio-write-plot` skill ("Check the figure") |
| What the user sees in a MiniApp tab | `user-guide/miniapps.md` |

## 2. Rules

- **`screenshot_gui` shows the desktop app over local MCP only.** It captures the
  SciStudio desktop window, including MiniApp iframes, canvas, and WebGL, and
  returns a PNG the model can see. Through WebMCP or in an ordinary browser tab it
  returns an unsupported error; use your own browser or app screenshot tool there.
- **It only looks; it never acts.** It does not open or focus tabs, click, or start
  processes. Open the MiniApp with `open_miniapp` first, and operate controls with
  your own browser, side-panel, or computer-use tools.
- **Pick the target.** `target="miniapp"` (the default) captures the visible
  MiniApp, narrowed by `panel_id` or `context_id`; `target="workspace"` captures the
  whole window and takes neither. Pass `client_id` when several desktop windows show
  the project; the error lists the ids.
- **`wait_ms` is a layout delay, not readiness.** It accepts 0 to 5000 ms (default
  500). Read the returned `state` (loading, ready, or error) and look at the image
  before judging.
- **Look at the image, not only the metadata.** A `ready` state means the page
  finished the SDK handshake, nothing more. Check the picture for blank content,
  wrong data, clipping, overlap, and error messages.
- **A screenshot is not an interaction test.** It does not prove a control works,
  that Python matches the slider, or that a result is correct. Operate the main
  control, capture again, and report plainly any interaction you could not test.
- **Errors are actionable; follow them.** A disconnected GUI, a hidden MiniApp, an
  ambiguous window, a project switch, or a timeout (10 seconds per request) returns
  a named error instead of a stale image. Fix the cause the error names and capture
  again.
- **Captures are bounded to the open project.** Only the authorized project can be
  captured, and a capture that crosses a project or tab switch is discarded. Images
  are limited to 2560 × 2560 pixels, 4 million pixels in total, and 4 MiB of PNG.
