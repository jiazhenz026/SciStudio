# Package development guide

This guide is for building a **distributable SciStudio package** — a pip-
installable bundle of blocks, data types, and previewers that other people add
to their SciStudio install, the way the imaging, LC-MS, and spectroscopy
packages work. It is the counterpart to the in-project *user guide* (which
covers writing a one-off custom block in your own project); here the audience is
a developer shipping a reusable extension.

If you only need a custom block for the project in front of you, you do **not**
need a package — see the user guide instead. Build a package when you want to:

- share blocks/types with other users or installs,
- give your data types tailored previews,
- version and release your extension independently of SciStudio core.

## What a package contributes

SciStudio core knows nothing about your science. A package teaches it three
kinds of thing, each through a published **entry point** core discovers at
startup:

| Entry point | You contribute | Audience |
|---|---|---|
| `scistudio.blocks` | block classes | the workflow engine + the palette |
| `scistudio.types` | data type classes | the type system + connection checking |
| `scistudio.previewers` | previewer specs | the preview router |

A fourth, equally important contribution has no entry point: the **reuse
surface** — the public types and helpers that *other* authors import when they
write blocks against your package. Getting that surface right is what separates
a package people can build on from one they have to reach into.

## How to read this guide

| Topic | Read |
|---|---|
| How the pieces fit together; the public/private boundary | [architecture.md](architecture.md) |
| Designing your data types | [types.md](types.md) |
| Writing your blocks | [blocks.md](blocks.md) |
| Giving your types a preview | [previewers.md](previewers.md) |
| Packaging, entry points, versioning, releasing | [publishing.md](publishing.md) |

## The running example

Throughout, we use the real **spectroscopy package**
(`scistudio-blocks-spectroscopy`) as the worked example: its `Spectrum` type,
its `BaselineCorrection` block, and its `Spectrum` previewer. You can read the
full source in the SciStudio repository under
`packages/scistudio-blocks-spectroscopy/`.

## The contract this guide follows

The public API contract (ADR-052) sets the rules a package must follow so its
surface is as stable and discoverable as core's:

- The public path is the **canonical import root**, not a deep module path.
  Authors `from scistudio_blocks_spectroscopy import Spectrum`, never
  `from ...types import Spectrum`.
- Everything public carries a stability tier (`stable` / `provisional` /
  `internal`) and a `Since` version, declared **in the code** with the
  `scistudio.stability` decorators.
- The exhaustive per-symbol interface lives in the **generated API reference**,
  not in prose. This guide explains *how to design and build*; the reference is
  the contract.

These rules are explained where they bite, in each page below.
