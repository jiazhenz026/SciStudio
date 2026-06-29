# Package architecture

A SciStudio package is an ordinary Python distribution with three jobs: declare
some **types**, declare some **blocks** that produce and consume them, and
(optionally) declare **previewers** that show them. This page explains how those
pieces relate, how core finds them, and — most importantly — the boundary
between what your package exposes and what it keeps to itself.

## Two surfaces, two audiences

The single idea that keeps a package clean is that it faces **two different
audiences**, and they need different things:

1. **A registration surface — to core.** The block, type, and previewer classes
   core needs to populate the palette, the type system, and the preview router.
   This is a handshake with the runtime, wired through entry points. It is not
   something a human imports.

2. **A reuse surface — to other authors.** The symbols a user (or the in-app AI
   on their behalf) imports when writing *their own* block, plot, or script
   against your package: your types, the constructors and readers on them, and
   any helpers worth sharing.

Conflating these is what makes packages hard to build on. The registration
surface is for the engine; the reuse surface is for people. Design them
separately.

## Layout

The spectroscopy package is a good template to copy. Its shape:

```
scistudio-blocks-spectroscopy/
  pyproject.toml                     # deps + the three entry points
  src/scistudio_blocks_spectroscopy/
    __init__.py                      # the package's PUBLIC surface (__all__) + entry callables
    types.py                         # Spectrum, SpectralDataset
    _support.py                      # INTERNAL helpers — not public
    blocks/
      __init__.py                    # aggregates BLOCKS
      preprocessing.py               # BaselineCorrection, SmoothSpectrum, ...
      feature_extraction.py          # ExtractIntensity, FindPeaks, ...
      ...
    previewers/
      __init__.py                    # get_previewers() -> [PreviewerSpec, ...]
      providers.py                   # the backend provider functions
      assets/                        # viewer.js + CSS the frontend loads
  tests/
```

Two conventions carry the public/private boundary:

- **The package top level (`__init__.py`) is the public front door.** Everything
  an author may import is re-exported there and listed in `__all__`. An author
  writes `from scistudio_blocks_spectroscopy import Spectrum`, never
  `from scistudio_blocks_spectroscopy.types import Spectrum`. The deep path is an
  internal detail you must be free to move.

- **A leading underscore means internal.** `_support.py` holds genuinely
  package-internal code — Arrow plumbing, coercion helpers, ID generation — that
  no outside author should call. It is not in `__all__` and carries no stability
  promise.

## How core discovers a package

Core finds your package only through three entry-point callables declared in
`pyproject.toml`. There is no import-time magic and no scanning of your modules:

```toml
[project.entry-points."scistudio.blocks"]
scistudio_blocks_spectroscopy = "scistudio_blocks_spectroscopy:get_block_package"

[project.entry-points."scistudio.types"]
scistudio_blocks_spectroscopy = "scistudio_blocks_spectroscopy:get_types"

[project.entry-points."scistudio.previewers"]
scistudio_blocks_spectroscopy = "scistudio_blocks_spectroscopy.previewers:get_previewers"
```

Each points at a plain function:

- `get_block_package()` → `(PackageInfo, [BlockClass, ...])` — your blocks plus
  package metadata (name, version, update channel).
- `get_types()` → `[TypeClass, ...]` — your data types (here `[Spectrum,
  SpectralDataset]`).
- `get_previewers()` → `[PreviewerSpec, ...]` — your previewer specs.

That is the whole registration contract. Everything else about your package is
your own business. The shared `scripts/validate_contract.py` checks these
callables exist and return the right shapes.

## How the pieces relate at runtime

```
            ┌─────────── your package ───────────┐
            │                                     │
  types  ───┤  Spectrum (a Series subclass) ──────┼──► type system: ports that
            │     ▲                  ▲             │     accept_types=[Spectrum]
            │     │ produces/consumes│             │
  blocks ───┤  BaselineCorrection (ProcessBlock) ──┼──► palette + engine
            │     │                                │
  previewers┤  PreviewerSpec(target_type=Spectrum)─┼──► preview router shows a
            │                                      │     Spectrum on its port
            └─────────────────────────────────────┘
```

A block names your types on its ports; the type system uses those names to
type-check connections on the canvas; and a previewer registered for a type is
what the user sees when they click a port carrying it. The three contributions
are independent entry points but cohere around your **types** — which is why the
types are where you start.

## The reuse surface in practice

When another author writes a block that consumes your `Spectrum`, they need to:

- **name it on a port** — so `Spectrum` must be public (it is, via `__all__`);
- **construct it** — so your type needs a public constructor that takes
  domain-native inputs (Section [types.md](types.md));
- **read it** — solved for free by the inherited `to_memory()` / `to_pandas()` /
  `to_numpy()`; a package must **not** redefine those.

Everything they need is on the type or in a public helper. Nothing forces them
into `_support`. When you find yourself wishing an outside author could call
something private, that is the signal to give it a public home — that gap is the
exact problem this contract exists to close.

## Next

Start with [types.md](types.md): your types anchor everything else.
