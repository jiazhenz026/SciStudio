---
name: scistudio-project-qa
description: |
  Use when the user asks a question ABOUT SciStudio or about this project —
  how a feature works, what a block/type/contract is, what blocks are
  installed, where docs/data live, project name / metadata, recent
  workflows. The Q&A skill. NOT for designing or debugging workflows
  (scistudio-build-workflow / scistudio-debug-run) or authoring code
  (scistudio-write-block / scistudio-write-plot).
---

# scistudio-project-qa

## 1. What this skill is

This skill answers the user's questions about SciStudio and about this project:
how a feature works, what something is, what the project holds, and what is
installed. Every answer comes from two sources, both shipped with or read from
this project: the provisioned docs, which match the installed SciStudio version,
and the live MCP tools, which report the current project state. Never answer from
memory.

When the question turns into a task (build this, fix that run, write that block),
answer it and load the skill for the task.

## 2. Question types and where the answers are

| Question type | For example | Where to look |
|---|---|---|
| **Using SciStudio**: what something is, how a feature works, how to do something in the GUI | "What is a MiniApp?", "How do branches work?", "How do I use this from a desktop AI app?" | `user-guide/` (start at `user-guide/README.md`) |
| **Built-in blocks**: what a core block does | "What does the Code Block do?" | `user-guide/built-in-blocks.md` |
| **Installed packages**: what a package provides and how to use it | "What does this package I installed add?" | `list_blocks` (each block names its package) and `list_types` (each type's `module_path` shows where it comes from); when the package ships docs, `.scistudio/agent-reference/package-index.md` |
| **Contracts**: what may be imported, how stable it is, the rules a block, type, or plot follows | "Can I import this class?", "What must a plot script return?" | `.scistudio/agent-reference/` (start at `README.md`) |
| **Exact signatures and file formats**: a class, method, function, or workflow YAML field | "What arguments does `Array` take?", "What fields does a node have?" | `user-guide/api-reference/` (start at `index.md`; workflow YAML in `workflow-yaml.md`) |
| **This project**: name, description, workflows, recent runs | "What's in this project?", "What did I run last?" | `get_project_info`; `get_active_workflow_context` for the open workflow; `get_workflow` for what a workflow does; `get_run_status` for one run |
| **Available blocks and types**: what is registered now, and a block's exact ports and config | "Do I have a block for normalization?", "What inputs does this block take?" | `list_blocks`, `list_types`, `get_block_schema(block_type)` |
| **Panels and MiniApps**: which MiniApps, interactive panels, and preview panels exist | "What MiniApps do I have?", "Is there a viewer for this type?" | `list_panels` (filter with `kind` and `data_type`) |
| **Data in the project**: stored results and files the user added | "What results do I have?", "Where is my raw data?" | `list_data` for stored datasets; `list_directory` or `search_files` for other files |
| **Anything else in the docs**: a topic you cannot place | "Is there a doc about hooks?" | `search_docs(query)`, then `get_doc(path)` |

## 3. Anti-patterns

- Answering a SciStudio question from memory when a `user-guide/` or
  `.scistudio/agent-reference/` page covers it.
- Inventing package names, versions, block names, types, or signatures.
- Guessing a doc path instead of finding it with `search_docs`.
- Answering a question about this project from the general docs when a tool
  reports the project's actual state.
- Quoting agent-reference rules or internal skill names at the user; answer in
  the user's terms.

## 4. Defaults, failure handling, and examples

**Defaults.**

- For how and what questions, read the relevant page and answer from it, with the
  page path so the user can read more.
- For questions about this project, call the tool and quote what it returns.
  The docs describe SciStudio in general; the tools describe this project.
- To find a page, call `search_docs(query)`, narrowed with `scope` (`user-guide`
  or `.scistudio/agent-reference`) when you know the area, then `get_doc(path)`.
- `list_data` lists only stored datasets under `data/zarr/`, `data/parquet/`, and
  `data/artifacts/`. For files the user added, such as `data/raw/counts.csv`, use
  `list_directory` or `search_files`.

**When something fails.**

- `search_docs` finds nothing: try other words, then search the file system
  yourself with `search_files` (by file name, or by `content`) and read what you
  find with `read_file`. If that finds nothing either, say the project does not
  cover it. Do not fill the gap from memory.
- A doc and a tool disagree about this project: trust the tool, and mention the
  difference.
- `get_project_info` raises `FileNotFoundError`: no `project.yaml` is open; tell
  the user to open or create a project.

**Example: "What blocks do I have, and how do I write my own?"**

```
list_blocks                         # the available blocks, each with its package
get_doc("user-guide/writing-blocks.md")
```

Answer with the blocks `list_blocks` returned, summarise how a block is written
from the page, cite `user-guide/writing-blocks.md`, and offer to write the block.

**Example: "What does my normalize workflow do?"**

```
get_project_info                    # confirm the workflow's name
get_workflow("workflows/normalize-counts.yaml")
get_block_schema("<block_type>")    # for each block whose role is unclear
```

Describe the steps in order in scientific terms, and the parameters the user can
tune.

## 5. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `search_docs` | Searches the project's `.md`, `.rst`, and `.txt` files for text. | To find the page that answers a question. |
| `get_doc` | Returns the full text of one doc file. | To read a page found by `search_docs` or named in §2. |
| `get_project_info` | Returns the project's metadata, workflows, and recent runs. | For questions about the project itself. |
| `list_blocks` | Lists available blocks with their package and I/O signature. | For which blocks exist and where they come from. |
| `get_block_schema` | Returns one block's ports and config schema. | For a block's exact inputs, outputs, and parameters. |
| `list_types` | Returns the data-type hierarchy. | For which data types exist. |
| `list_panels` | Lists existing MiniApps, interactive panels, and preview panels. | For which panels and MiniApps exist. |
| `get_active_workflow_context` | Returns the workflow open in the GUI. | When the user says "this workflow". |
| `get_workflow` | Loads a workflow file. | To explain what a workflow does. |
| `get_run_status` | Returns a run's state and errors. | For how a run went. |
| `list_data` | Lists stored datasets produced by runs. | For what results the project holds. |
| `list_directory` / `search_files` | List a folder, or find files by name or content. | For files the user added, and when `search_docs` finds nothing. |
| `read_file` | Reads a bounded part of a file. | To read a file found with `search_files`. |
