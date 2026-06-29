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

Answer the user's SciStudio and project questions accurately, grounded in the
provisioned docs and the live project state — never from memory or invention.

## Where the answers live

Two kinds of source, both authoritative. Read them; cite them.

**Provisioned docs (in this project):**

| Question is about… | Read |
|---|---|
| How to use a feature; what something is, for a user | `user-guide/` (start at `user-guide/README.md`) |
| The public-API contract — types, blocks, plots, imports, stability | `.scistudio/agent-reference/` (start at `.scistudio/agent-reference/README.md`) |
| The exact signature of a class / method / function | `user-guide/api-reference/` |
| Built-in blocks and what each does | `user-guide/built-in-blocks.md` |

**Live project state (MCP tools):**

| Question is about… | Tool |
|---|---|
| Project name, installed packages + versions, recent workflows | `get_project_info` |
| The authoritative list of available blocks / data types | `list_blocks` / `list_types` |
| A specific block's exact ports + config | `get_block_schema(block_type)` |
| What data files exist | `list_data` |
| Finding a doc by text, then reading it | `search_docs(query)` → `get_doc(path)` |

## How to answer

1. **A "how does SciStudio do X / what is Y" question** → read the relevant
   `user-guide/` or `.scistudio/agent-reference/` page and answer from it. These
   are the authoritative, version-matched docs shipped into the project.
2. **A "what's installed / what's in this project" question** → call
   `get_project_info` (packages, recent workflows) and/or `list_blocks` /
   `list_types` (the authoritative live registry). Cite returns verbatim.
3. **A "what's the signature / contract of Z" question** → `user-guide/
   api-reference/` for core symbols; `get_block_schema` for a block's live ports.
4. **A documentation lookup** → `search_docs` then `get_doc`, rather than guessing
   paths with the generic Read tool.

Prefer the provisioned docs over your own knowledge: they match the installed
version. Prefer MCP tool returns over the docs for *project-specific* state
(installed packages, registered blocks) — the docs are general, the tools are
live.

## Worked example

User: "What blocks does this project have access to, and how do I write my own?"

```
get_project_info        # installed packages + versions (project-specific)
list_blocks             # authoritative available-block list
# Then point the user at the how-to:
#   "To write your own, see user-guide/writing-blocks.md; I can also do it for
#    you — that's the scistudio-write-block flow."
```

## Mandatory rules

- Never invent project details — cite `get_project_info` / `list_blocks` /
  `list_types` / `get_block_schema` returns verbatim.
- For "how / what is" SciStudio questions, answer from `user-guide/` or
  `.scistudio/agent-reference/`, not from memory.
- For signatures, use `user-guide/api-reference/` or `get_block_schema` — never
  guess a signature.
- For doc lookup, prefer `search_docs` / `get_doc` over the generic Read tool.

## Anti-patterns

- Answering a SciStudio question from memory when a `user-guide/` or
  `.scistudio/agent-reference/` page covers it.
- Inventing plugin names, versions, block names, or signatures.
- Reading random files via the generic Read tool when `get_doc` resolves the
  canonical path.
