---
name: scieasy-project-qa
description: |
  Use when the user asks about the project itself — what blocks are
  installed, where docs live, what files are in data/, project name /
  metadata, recent workflows. NOT for designing or debugging workflows.
---

# scieasy-project-qa

Use this skill when the user asks meta-questions about the SciEasy
project workspace: which plugins are installed, where the docs are,
what's been recently modified, what files live in `data/`. These are
surfaces beyond the workflow / run scope — they map to four read-only
tools that pull from the file system, the block registry, and the
docs index. This skill teaches what each tool returns and how to
combine them for common questions.

## 1. `get_project_info`

Returns project name, root directory, installed scieasy plugins (and
their versions), recently-modified workflows (top 3-ish by mtime), and
backend / runtime version info. Call this first for any "what is this
project?" or "what's installed?" question.

Cite the returned values verbatim; do not invent plugin names or
versions.

## 2. `search_docs(query)`

Free-text search over the project's `docs/` directory and any
installed plugins' docs. Returns matching doc paths with snippets.
Use this when the user asks a documentation question and you do not
already know the canonical doc path.

Prefer `search_docs` over guessing paths with `Read` — the search
indexes the docs the way the project intends them to be discovered.

## 3. `get_doc(path)`

Returns the full text of a specific doc by path. Use this after
`search_docs` returns a candidate path, or when the user names a doc
directly (e.g. "show me the README").

## 4. `list_data`

Enumerates data assets under `data/`. Returns file paths, sizes, and
inferred types. Use this for "what data do we have?" or before
suggesting input paths for a new workflow.

## 5. Combining tools

For "what's this project about?":

```
get_project_info                       # project name, plugins, recent workflows
search_docs(query="overview")          # or get_doc(path="README.md")
```

For "what blocks does this project have access to?":

```
get_project_info                       # see installed_plugins
# If the user wants to use them, pivot to scieasy-build-workflow which
# uses list_blocks for the canonical authoritative list.
```

For "where are my outputs?":

```
list_data                              # everything under data/
get_project_info                       # confirm project_root for resolving relative paths
```

## 6. Worked example

User: "What blocks does this project have access to?"

```
get_project_info
# → {project_name: "lcms-analysis",
#    project_root: "/home/user/projects/lcms-analysis",
#    installed_plugins: [
#      {name: "scieasy-blocks-imaging", version: "0.5.2"},
#      {name: "scieasy-blocks-lcms", version: "0.3.1"}
#    ],
#    recently_modified_workflows: ["workflows/qc.yaml", ...]}

# Report: "This project has scieasy-blocks-imaging 0.5.2 and
# scieasy-blocks-lcms 0.3.1 installed. For the authoritative block
# list, I can call list_blocks — would you like me to?"
```

## Mandatory rules

- Never invent project details — cite `get_project_info` returns
  verbatim.
- For doc-lookup questions, prefer `search_docs` over guessing paths
  with the generic Read tool.
- For the authoritative block list, use `list_blocks` (covered in
  scieasy-build-workflow / scieasy-write-block) — `get_project_info`
  only surfaces the plugin metadata.

## Anti-patterns

- Inventing plugin names or versions instead of reading
  `get_project_info`.
- Reading random files via the generic Read tool when `get_doc`
  would resolve the canonical path.
- Reporting "I think this project does X" without grounding in
  `get_project_info` / `get_doc` / `list_data` outputs.
