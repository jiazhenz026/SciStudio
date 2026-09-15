# Using SciStudio in your AI app

Use SciStudio in the built-in browser of an AI app such as ChatGPT or Kimi,
and chat with the AI alongside your workspace. The browser must support
**WebMCP** **(Claude is not currently supported)**.

## Connect

1. Install [SciStudio](https://github.com/jiazhenz026/SciStudio/releases) on the
   same computer as your AI app, then launch it and choose **External AI**.
2. Wait for **Running** in the connection window, then click **Copy**.
3. Open the copied address in your AI app's **built-in browser**. Use the full
   address, including `/?ui=ai`.
4. Create or open a project, then ask the AI something like:
   *"Inspect this project and help me build a workflow that loads a CSV file."*

Keep the page open and SciStudio running while you work. The sidebar appears
on the right, with **Preview** in a separate card. Chat in your AI app; this
layout hides SciStudio's embedded AI Chat tab. Use **Learning Center** for
workflow tutorials.

No agent CLI is needed for this conversation. **AI Agent blocks** still require
a local CLI provider, including when used from an AI app. **Claude Code**
remains supported for those blocks and the embedded chat; see
[The AI assistant](ai-assistant.md).

## Startup and service controls

- **Remember the mode:** select **Don't ask again** at startup. Change it later
  under **File > Startup Mode**, the tray's **Startup Mode** menu, or **At launch**
  in the connection window. To restore the question, choose **Ask at Every Launch**
  in the menu or **Ask every time** in the connection window.
- **Reopen the connection window:** choose **Open Connection Window** from the
  tray, or launch SciStudio again with External AI selected. Closing this window
  leaves the service running.
- **Open Desktop Window:** opens the desktop workspace on the same service.
- **Stop Service / Restart Service:** stop the service, then restart it when
  needed. After restarting, copy the current address and reopen it in your AI app.
- **Stop and Quit:** stops the service and exits SciStudio. Finish or cancel
  your workflow first. Stopping asks for confirmation if a desktop workspace
  window is attached.

If the service stops or crashes with all SciStudio windows closed, the app
exits; launch it again. With a window open, use **Restart Service** to recover.

On Windows, click the tray icon to reopen the connection window. On macOS,
reopening from the Dock or Finder brings forward an existing desktop window,
or the connection window with External AI selected. On Linux without tray
icons, keep the connection window available or reopen it by launching SciStudio.

## Troubleshooting

- **Page will not open:** check that SciStudio is Running on the same computer,
  then copy its current address again.
- **AI cannot find the tools:** use the AI app's own WebMCP-capable browser and
  reload the page. A page opened in a separate browser is not connected to that
  AI conversation.
- **Service fails or becomes unresponsive:** use **Show Logs** in the connection
  window. Use **Restart Service** after a failure or stop.

<!-- Runtime contract: docs/specs/adr-055-local-background-runtime.md;
     docs/specs/adr-055-ai-host-presentation.md; desktop/background-mode.js;
     desktop/connection.html; desktop/menu.js; frontend/src/webmcp/register.ts.
     Source paths are relative to the SciStudio repository; issue #2290. -->

## Explore with MiniApps

See [MiniApps](miniapps.md) to create an interactive result explorer, reuse it on
other data, manage its session, or convert it into a workflow block. The guide
also explains when an AI can inspect the rendered interface with a screenshot.
