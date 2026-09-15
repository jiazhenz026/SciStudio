# SciStudio user guide

Welcome. This guide lives inside your project so it is always at hand. It covers
**using SciStudio** — building and running workflows, looking at your data, and
writing your own blocks and plots — for people doing the science, not software
engineers. If you can write a Python function, you can do everything here; and
for most of it, you can simply ask the [AI assistant](ai-assistant.md).

## Start here

New to SciStudio? Read **[getting-started.md](getting-started.md)** — it takes you
from choosing how to use SciStudio to your first run in five steps.

Want to work inside your AI app? Start with
**[Using SciStudio in your AI app](using-with-ai-apps.md)** to connect through
the app's built-in browser. For the assistant inside the SciStudio desktop
window, follow [Install a provider](ai-assistant.md#before-you-start-install-a-provider).

## The guide

**Using the app**

| Page | What it covers |
|---|---|
| [getting-star ted.md](getting-started.md) | The five-minute tour: project → workflow → run → preview |
| [Using SciStudio in your AI app](using-with-ai-apps.md) | Start External AI mode, connect from an AI app, and manage the background service |
| [how-scistudio-works.md](how-scistudio-works.md) | The short architecture map: data, blocks, lineage, AI agents, plots, and extensions |
| [using-the-gui.md](using-the-gui.md) | The canvas in depth: building workflows, running them, previewing data |
| [use-panels.md](use-panels.md) | The three kinds of panels: previews, interactive decisions, MiniApps |
| [miniapps.md](miniapps.md) | Using MiniApps for data exploration and interaction |
| [built-in-blocks.md](built-in-blocks.md) | Every block that ships with SciStudio and what it does |
| [history-and-branches.md](history-and-branches.md) | Go back to past work; keep pipeline variants on branches |
| [ai-assistant.md](ai-assistant.md) | External AI apps, the desktop CLI assistant, and AI Agent blocks |
| [learning-center.md](learning-center.md) | Guided tutorials and the in-app reading tab |

**Making your own**

| Page | What it covers |
|---|---|
| [data-types.md](data-types.md) | The data types that flow between blocks, and which one fits your data |
| [writing-blocks.md](writing-blocks.md) | Write a custom block from scratch |
| [custom-types.md](custom-types.md) | Make your own data type when the built-in ones do not fit |
| [writing-plots.md](writing-plots.md) | Write a quick preview-only plot of a result |
| [examples/](examples/) | Worked, runnable examples for every authoring surface: blocks, types, panels, plots, and workflows |

## How this guide works

These pages tell you **what exists and how to use it**, with worked examples.
They deliberately do **not** restate every parameter and return type. For the
exact contract of a class or method, the **[API reference](api-reference/index.md)**
(in the `api-reference/` folder beside this guide, and published online) is
generated directly from the code, so it can never be out of date. When a page
names a symbol — say `from scistudio.blocks.base import InputPort` — that import
path is the contract: import from there and your code keeps working across
releases.

## Two audiences, one boundary

If you are building a **distributable package** to share blocks with other
people (the way the imaging, LC-MS, and spectroscopy packages are built), that is
a separate guide aimed at developers — see **Package Development**
(`docs/package-development/`) in the SciStudio repository. This guide is for
using SciStudio in your own project.
