# MiniApps: explore a result interactively

A MiniApp is a custom view with controls for exploring data from a completed
block. It opens in its own workspace tab: an image explorer, say, shows the
image beside a threshold slider and updates a mask as you move it. Your source
data stays available — exploring it never reruns the workflow.

## Create a MiniApp

1. Run the block that produces the data you want to explore.
2. Open **MiniApps** in the sidebar and choose **+ New**.
3. Under **Data source**, pick a completed output of the current project.
   Workflow, node, and output names distinguish results.
4. Under **Instructions**, describe what you want to see and which controls you
   need — “Show the image with a threshold slider. Update the mask as I adjust
   the threshold.” Choose the provider and permission mode, then submit.

SciStudio opens an AI authoring session that builds the MiniApp. The AI should
test it on the selected data and report what it verified; creation alone is
not proof that every control works.

## Answer the AI's questions

Before building, the AI usually shows a short questionnaire in the MiniApp tab:
what to show, how to colour it, which values to start from. Every question is
optional — pick a suggestion, type your own, choose **Decide for me**, or skip —
then press **Submit**. The latest submit counts.

If the AI is working in a SciStudio terminal tab, it starts building on submit.
Otherwise the page says your answers are saved: go back to your AI chat and
tell it you have submitted.

## Open and reuse

- Click a MiniApp in the sidebar once to open it. If asked **Open on which
  data?**, choose a compatible completed output. Reuse the same MiniApp on
  another output instead of rebuilding its interface.
- Switching tabs keeps the MiniApp and its controls alive. Closing its tab ends
  the session; reopening may reset controls and computed results. Saved exports
  are separate.
- **Reload** at the top of the MiniApps section rescans for added, changed, or
  removed MiniApps. Registry changes update the lists automatically.

## Restart and stop

The toolbar shows whether the MiniApp is starting, running, stopped, or has an
error. **Restart** starts its Python process again (this can reset transient
values); **Stop** ends it. On an error, share the visible message and the
action that caused it with the AI. The toolbar shows useful state, not memory
or process metrics.

## Convert to an interactive workflow block

Choose **Convert** in the MiniApp toolbar, then **Convert to interactive
block**. This creates a block that can run this interface as an interactive
workflow step and send results to subsequent blocks. The original MiniApp
stays available.

- Under **Outputs**, give each result a **Name** and choose its **Data type**. Use **Add output** for more.
- Optional **Instructions** can set behavior — “Use the current threshold as
  the default.” A slider's on-screen value does not automatically become a
  Python default, so state it here and have the block tested with it.

## What's next

- [using-the-gui.md](using-the-gui.md) — where MiniApps live in the window
- [ai-assistant.md](ai-assistant.md) — work with the AI assistant
- [learning-center.md](learning-center.md) — hands-on tutorials
