# MiniApps: explore a result interactively

A MiniApp is a custom view with controls for exploring data from a completed
block. It opens in its own workspace tab. For example, an image explorer can
show the image beside a threshold slider and update a mask as you move it.
Your source data remains available; exploring it does not rerun the workflow.

## Create a MiniApp

Run the block that produces the data you want to explore. Open **MiniApps** in
the sidebar and choose **+ New**. Under **Data source**, select an output from
a completed block in the current project. Workflow, node and output names help
distinguish results; nodes with the same display name also show their instance
identifier. A new project with no completed outputs has no data sources yet.

Under **Instructions**, describe what you want to see and which controls you
need. For example: “Show the image with a threshold slider. Update the mask as
I adjust the threshold.” Choose your provider and permission mode using the
usual AI settings, then submit. SciStudio opens an AI authoring session to build
the MiniApp. The AI should test it on the selected data and report what it has
actually verified; creation alone is not proof that every control works.

## Answer the AI's questions

Before it builds, the AI usually shows a short questionnaire in the MiniApp tab:
what to show, how to colour it, which values to start from. Every question is
optional. Pick one of the suggested answers, type your own where a box is
offered, choose **Decide for me** to leave that choice to the AI, or skip the
question. Then press **Submit**. You can change your answers and submit again;
the latest submit counts.

If the AI is working in a SciStudio terminal tab, the submit tells it directly
and it starts building. If you use SciStudio from your own AI app (External AI),
or you closed that terminal tab, the page says your answers are saved: go back
to your AI chat and tell it you have submitted.

## Open and reuse

Click a MiniApp in the sidebar once to open it. If SciStudio asks **Open on which
data?**, choose a compatible completed output in the current project. Reuse the
same MiniApp with another suitable output instead of rebuilding its interface.
Switching workspace tabs preserves the mounted MiniApp and its current controls.
Closing its tab ends the running session. Reopening may reset controls and
computed results; any export you saved is separate from that session.

Choose **Reload** at the top of the MiniApps sidebar to scan for added, changed,
or removed MiniApps. This refreshes the registered list and the compatible
MiniApp actions on blocks. New MiniApps and registry changes also update these
lists automatically.

## Restart and stop

The toolbar shows whether the MiniApp is starting, running, stopped, or has an
error. **Restart** starts its Python process again; **Stop** ends that process.
Restart can reset transient values held by the running process. If the app shows
an error, share its visible message and the action that caused it with the AI.
The toolbar intentionally shows useful state rather than memory or process metrics.

## Convert to an interactive workflow block

Choose **Convert** in the MiniApp toolbar. **Convert to interactive block**
creates a block that can use this interface as an interactive workflow step and
send results to subsequent blocks. The original MiniApp remains available.

Under **Outputs**, give each result a **Name** and choose its **Data type**.
SciStudio derives output port identifiers and checks that they are valid and
unique. The type control lists registered types; it is not a free-text field.
Use **Add output** for another result. Optional **Instructions** can specify
behavior such as “Use the current threshold as the default.” Then select the
usual provider and permission mode and choose **Convert**.

A slider's current on-screen value does not automatically become a Python
parameter default. State this requirement in Instructions and have the resulting
block tested with that default and its declared outputs.

## Keep a MiniApp in My Library

A project MiniApp appears under that project's section. Its action menu offers
**Promote to My Library** moves its directory into your user library so the same
implementation can be reused across projects. The original project copy is removed. My Library, package-provided, and built-in items have their own sections;
their availability does not grant access to another project's data. Opening a
shared MiniApp still requires a compatible output from the current project.

## Let the AI inspect the result

In the SciStudio desktop application, local AI providers can call
`screenshot_gui` to see the visible MiniApp or the current SciStudio workspace,
including canvas-rendered content. Keep the intended project and tab visible.
The tool takes a picture; it does not click controls, open tabs, or start a run.
The AI should inspect the image for missing data, blank areas, errors and clipping,
then use its own computer-use capability, when available, to try key controls
and take another picture. Without computer use it should say that interactions
were not verified.

Browser-only SciStudio and the external text-only WebMCP connection do not provide
this screenshot capability. They return an explicit unsupported message. A hidden
tab, disconnected desktop, changed project or ambiguous window also needs to be
resolved before an image can be returned. Screenshots never capture unrelated
applications or the entire desktop.

MiniApp authors can compose the same core renderers used by built-in previews:
arrays, data frames, series, text, artifacts, plots, collections, composite data,
and generic metadata. Domain-specific views such as imaging-package channel
controls remain supplied by those packages; the core numeric Array view is not
an image-domain renderer.

## Export a result or choose a built-in preview

If the MiniApp provides an **Export** or **Download** control, use it to save the
result it offers. Available formats and what is exported depend on the MiniApp.
An exported file is separate from a typed workflow output: use **Convert** and
declare the outputs when later blocks should receive the result as part of a run.

Built-in previews remain available above the preview area through **All
Previewers**, where you can browse viewers and choose one for a data type.
The left sidebar's **MiniApps** section holds reusable custom explorers; the
built-in viewer list is in the preview column.
