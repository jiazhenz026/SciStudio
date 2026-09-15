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
   browser or computer-use tool, including any deployment prefix. `open_gui`
   returns an address; it does not open a browser or click anything.
2. Reuse a browser tab already connected to that instance when available.
   Computer use can also operate the existing SciStudio desktop window. Do not
   guess a port or start a second backend.
3. Read the current page or take a screenshot. Confirm the intended project
   and content before acting. A new browser tab may have different selected
   items, open tabs, and active workflow from the desktop window.

If no suitable tool is available, or it cannot reach the instance, explain the
specific limitation. Having a URL alone does not establish GUI access.

## Find the right part of SciStudio

Use visible labels, tooltips, and the current page structure. The sidebar may be
on either side, so navigate by names rather than fixed screen positions.

| Goal | Where to look and what to do |
|---|---|
| Open a workflow | Open **Workflows** in the workspace sidebar, find the intended workflow, and open its canvas tab. |
| Find a project file | Open **Project**, expand its folders, and open the file. |
| Find available blocks | Open **Blocks**. Inspect the block's name and description before selecting or dragging it onto the canvas. |
| Change a node's settings | Select the intended canvas node, then use its parameter fields. Confirm the node identity when labels repeat. |
| Inspect data | Open **Data**, or select the relevant input/output port on the canvas to show its preview. |
| See execution progress or errors | Check canvas node states and the bottom area's logs/run history. |
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
