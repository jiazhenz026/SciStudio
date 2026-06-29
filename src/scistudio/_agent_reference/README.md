# SciStudio agent reference

Authoritative, fact-dense reference for the SciStudio embedded agent. The task
**skills** tell you *when* and *the workflow*; these pages are the *contract* you
build against. Consult the relevant page before authoring; cite it instead of
guessing.

| Page | Read it before… |
|---|---|
| [public-api.md](public-api.md) | importing anything from `scistudio` — the public/private boundary |
| [data-types.md](data-types.md) | reading or constructing a `DataObject` in block code |
| [block-contract.md](block-contract.md) | writing a block class |
| [workflow-schema.md](workflow-schema.md) | writing or editing a workflow YAML |
| [plot-contract.md](plot-contract.md) | writing a `render(collection)` plot |
| [package-discovery.md](package-discovery.md) | using types/blocks from an installed package |

For exact symbol signatures, see the generated **API reference** under the
project's `user-guide/api-reference/` (path `../../user-guide/api-reference/` from
here). These pages state the rules and shapes; the API reference states the
signatures. Neither is guesswork — read them.
