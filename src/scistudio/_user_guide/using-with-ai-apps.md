# Using SciStudio in your AI app

Open SciStudio in your AI app's built-in browser and use the app's conversation
to work on your project. You can watch the workflow change on the canvas as the
AI helps you build it, then inspect the results yourself.

## Before you start

Install the SciStudio desktop app from the
[Releases page](https://github.com/jiazhenz026/SciStudio/releases) and an AI
desktop app whose built-in browser supports **WebMCP**, such as ChatGPT or Kimi
**(Claude is not currently supported)**. WebMCP lets the AI use the tools
provided by the SciStudio page. The browser in your installed AI app must
provide this capability.

Use both apps on the same computer: the connection address points to the
SciStudio service running locally. Sign in to your AI app as usual. SciStudio
bundles Python and its required runtime dependencies; this connection does not
require installing an agent CLI or configuring an MCP server manually.

The Claude limitation above concerns its desktop app's WebMCP connection.
**Claude Code** is still supported by SciStudio's embedded assistant and AI
Agent blocks. Those use separately installed CLIs; see
[The AI assistant](ai-assistant.md).

## 1. Start SciStudio in External AI mode

Launch SciStudio. At **How do you want to use SciStudio?**, choose
**External AI**. SciStudio starts its local service and opens a connection
window. Wait until the status is **Running**, the **Address** field is filled,
and **Copy** becomes available.

You can select **Don't ask again** to remember the mode. To change it later,
use **File > Startup Mode**, the tray's **Startup Mode** menu, or the
**At launch** selector in the connection window. Choose **Ask every time** in
that selector, or **Ask at Every Launch** in the menu, to restore the startup
question.

## 2. Open the address in your AI app

Click **Copy** in the connection window. Open your AI app's **built-in browser**
and paste the copied address into its address bar.

Use the complete address shown by SciStudio. It contains the current local
port and ends in `/?ui=ai`, which selects the layout for an AI app. Copy it
again after restarting the service, since the port can change.

Keep this page open in the AI app while you work. Opening it in a separate
browser does not connect that browser's page to the AI app's conversation.

## 3. Open a project and start a conversation

Create a project or open an existing one from the SciStudio start screen. Then
use your AI app's conversation to ask for help. For example:

> Inspect the current SciStudio project and tell me what workflows and data
> are available.

> Help me build a workflow that loads a CSV file and previews the table.

> Explain why the last run failed and suggest a fix.

When the AI invokes SciStudio tools, the workspace reflects its changes. Review
the workflow, adjust parameters, and inspect results in the same page. For
guided practice, open SciStudio's **Learning Center** and its existing tutorials.

The AI browser layout puts the activity rail and resizable sidebar on the
**right**, with **Preview** in its own card. The embedded **AI Chat** tab is
hidden in this layout; continue chatting in your AI app. The toolbar's layout
switch lets you choose the workbench layout without reloading the page.

An **AI Agent block** within a workflow still needs a supported local CLI
provider. Your AI app's conversation is not automatically used to execute that
block; see [The AI Agent block](ai-assistant.md#the-ai-agent-block).

## 4. Keep the service running, or stop it

Keep SciStudio running in the background while using it from your AI app.
Closing the connection window leaves the service running. To reopen the
connection window, use **Open Connection Window** from the SciStudio tray menu,
or launch SciStudio again with External AI selected. Reopening uses the existing
service.

The connection window provides these controls:

| Control | What it does |
|---|---|
| **Open Desktop Window** | Opens the SciStudio desktop workspace using the same running service. |
| **Stop Service** | Stops the service. Open SciStudio pages lose their connection. |
| **Restart Service** | Starts the service again after it has stopped or failed. Wait for Running, then copy the current address and reopen it in your AI app. |
| **Show Logs** | Opens the logs when the service has failed or become unresponsive. |
| **Stop and Quit** | Stops the service and exits SciStudio. |

Stop the current workflow before stopping the service. If a desktop workspace
window is attached, SciStudio asks for confirmation before stopping the service
or using **Stop and Quit**.

If the service stops or crashes while every SciStudio window is closed,
SciStudio exits. Launch it again to recover. If a window remains open, it shows
the service status so you can use **Restart Service**.

### Platform notes

- **Windows:** click the SciStudio tray icon to reopen the connection window.
- **macOS:** the tray controls appear in the menu bar. Reopening SciStudio from
  the Dock or Finder brings forward an existing desktop window if one is open;
  otherwise, with External AI selected, it opens the connection window.
- **Linux:** some desktops do not display tray icons. Keep the connection
  window available, or launch SciStudio again with External AI selected to
  reopen it and access **Stop and Quit**.

## If the page or tools are unavailable

| What you see | What to check |
|---|---|
| The page will not open | Check that SciStudio is Running on the same computer. Copy the address from the connection window again. If the service stopped, restart it first. |
| The page opens, but the AI cannot find SciStudio tools | Make sure the page is open in the AI app's own browser and that this browser supports WebMCP. Reload the page after the service is ready. A normal browser can show the workspace without exposing its tools to an AI app. |
| Tools stop working after a service restart | Copy the current address and reload the page in the AI app so it reconnects to the new service session. |
| The service fails to start or becomes unresponsive | Open the connection window and use **Show Logs**. After a failure or stop, use **Restart Service**. |
| SciStudio opens directly in Desktop mode | Use **File > Startup Mode** to choose **Ask at Every Launch** or **Always Run for External AI** for the next launch. |

For canvas operations, continue with [Getting started](getting-started.md).
For the embedded CLI assistant, see [The AI assistant](ai-assistant.md).

<!-- Runtime contract: docs/specs/adr-055-local-background-runtime.md;
     docs/specs/adr-055-ai-host-presentation.md; desktop/background-mode.js;
     desktop/connection.html; desktop/menu.js; frontend/src/webmcp/register.ts.
     Source paths are relative to the SciStudio repository; issue #2290. -->
