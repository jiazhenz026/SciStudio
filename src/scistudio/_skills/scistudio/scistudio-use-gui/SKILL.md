---
name: scistudio-use-gui
description: >-
  Operate the running SciStudio interface using available browser automation,
  Chrome, or computer-use tools. Covers opening the current instance, finding
  workspace content, interacting with controls, and observing the result.
---

# Use the SciStudio GUI

SciStudio supplies the running GUI address. Your AI client supplies the browser
or computer-use tools that open, inspect, and operate it. Use the tools actually
available in the current session and follow their browser/app selection and
interaction instructions; do not assume a provider-specific tool name.

## Connect to the running workspace

1. Call `mcp__scistudio__open_gui`. Open its complete returned URL with your
   browser or computer-use tool on the same machine as SciStudio. Preserve
   any deployment prefix and project/workflow query parameters: `url` attaches
   to the current project view; `base_url` omits that context. `open_gui` returns
   an address; it does not open a browser or click anything.
2. Reuse a browser tab already connected to that instance and intended project
   when available.
   Computer use can also operate the existing SciStudio desktop window. Do not
   guess a port or start a second backend.
3. Read the current page or take a screenshot. Confirm the intended project
   and content before acting. A new browser tab may have different selected
   items, open tabs, and active workflow from the desktop window.

If no suitable tool is available, or it cannot reach the instance, explain the
specific limitation. Having a URL alone does not establish GUI access.

## When you run inside an AI app through WebMCP

When the user runs SciStudio in **External AI** mode, the workspace is already
open in your AI app's built-in browser, beside the conversation, and your
SciStudio tools come from that page. Operate that page with the browser or
side-panel tools and methods your own app provides for its built-in browser; they
see and act on the same view the user sees, which is smoother than any other
route.

- Work in the page that is already open. Do not open the address in a separate
  browser or tab: a page outside the AI app is not connected to this
  conversation, and the user will not see your actions there.
- The layout differs from the desktop window: the workspace sidebar is on the
  right, **Preview** sits in its own card, and the **AI Chat** tab is hidden
  because the conversation happens in your app.
- `screenshot_gui` is not available over WebMCP; use your app's own page
  screenshot or snapshot to observe the result.

## Find the right part of SciStudio

Use visible labels, tooltips, and the current page structure. The sidebar may be
on either side, so navigate by names rather than fixed screen positions.

The workspace sidebar has six sections: **Blocks**, **Workflows**, **Data
types**, **Data**, **MiniApps**, and **Project**; a **Preview** section appears
when there is something to preview. The bottom panel has the tabs **AI Chat**,
**Terminal**, **Config**, **Logs**, **Plots**, **History**, and **Git**.

| Goal | Where to look and what to do |
|---|---|
| Open a workflow | Open **Workflows**, find the intended workflow, and open its canvas tab. |
| Find a project file | Open **Project**, expand its folders, and open the file. |
| Find available blocks | Open **Blocks**. Inspect the block's name and description before selecting or dragging it onto the canvas. |
| See which data types exist | Open **Data types**. |
| Change a node's settings | Select the intended canvas node, then edit its parameters in the **Config** tab. Confirm the node identity when labels repeat. |
| Inspect data | Open **Data**, or select the relevant input/output port on the canvas to show its preview. |
| Open or manage a MiniApp | Open **MiniApps**. |
| See execution progress or errors | Check canvas node states, then the **Logs** tab. |
| See past runs and where a result came from | Open the **History** tab. |
| See or restore versions, or switch branches | Open the **Git** tab. |
| See a plot | Open the **Plots** tab. |
| Switch open content | Select the intended centre tab by its title; do not assume the most recently opened tab is still active. |

Clicking the active workspace-section icon collapses its sidebar content;
clicking it again opens it. Hover an unfamiliar icon to read its tooltip. For
more detailed feature navigation, read `user-guide/using-the-gui.md` in the
project. Prefer the observed interface if its layout differs from an example.

## Operate controls

- With browser tools, locate controls using supported page snapshots, accessible
  names, roles, or visible text. With screenshot-based computer use, derive click
  and drag positions from the current image and refresh it after layout changes.
- Focus the intended field before typing. For dropdowns, inspect the options
  after opening them. For sliders and canvas dragging, observe both the control
  and the destination/result rather than assuming the gesture succeeded.
- Handle the visible dialog or menu before trying to click behind it. Use its
  labelled actions and read validation messages when an action is unavailable.
  Native file pickers may require computer use even when the page is controlled
  through browser tools.
- Embedded content may appear inside a frame. Use frame-aware browser operations
  when supported, or the visible view through computer use; a control absent
  from a top-level page snapshot is not necessarily absent from the interface.

## Observe the result

For a screenshot of the existing SciStudio desktop workspace, local MCP may provide
`screenshot_gui(target="workspace")`. For a visible MiniApp tab it also accepts
`target="miniapp"` and an optional `panel_id`. It captures images only; use
browser or computer-use tools for actions. It does not capture ordinary browser
tabs, and the text-only WebMCP bridge does not support its image response. Use
your browser tool's screenshot capability when operating a browser tab.

After an action, inspect the resulting page state or screenshot. Check the
visible effect relevant to the task: the intended tab opened, the field changed,
the data view updated, or the dialog completed. Wait for the relevant loading
state to settle before judging it or issuing the action again.

If something fails, read the visible error and use available console or runtime
logs to understand it. Avoid repeated clicks on an unchanged failure. Continue
from the last observed state and report any unresolved limitation accurately.
An opened URL is not proof of a rendered view, and a screenshot alone is not
proof that an interaction worked.

## Available tools

The live MCP tool list is the source of truth. SciStudio supplies only the tools
below; clicking, typing, and page snapshots come from your own browser,
side-panel, or computer-use tools.

| Tool | What it does | When to use it |
|---|---|---|
| `open_gui` | Returns the address of the running GUI. | First, before opening SciStudio in a browser (not needed when you already run inside its page through WebMCP). |
| `screenshot_gui` | Captures the SciStudio desktop workspace or a visible MiniApp as an image (local MCP only). | To see the desktop window's current state. |
| `open_miniapp` | Asks the open workspace to open a MiniApp tab on a block output. | To show the user a MiniApp on their data instead of telling them where to click. |
| `get_active_workflow_context` | Returns the workflow open in the GUI. | To confirm which workflow the user is looking at. |
