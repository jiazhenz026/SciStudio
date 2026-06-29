# Packaging, versioning, and releasing

Your blocks, types, and previewers become a package when you wrap them in a
Python distribution with the right entry points and a clean public surface. This
page covers `pyproject.toml`, the cross-cutting rules every package follows, and
how to version and release.

> **Alpha-stage guidance.** This page describes how package distribution works
> *today*, during the alpha: you build a wheel, attach it to a GitHub release,
> and your users install it from the SciStudio GUI. The package **structure**
> (entry points, the public-surface rules) is stable, but the **distribution
> mechanism** — a manual download-and-install — is an alpha convenience and is
> expected to change (e.g. a package browser/registry) before 1.0. The
> [Release](#release) section is the part most likely to evolve.

## `pyproject.toml`

A package is a normal distribution that depends on SciStudio core and declares
the three entry points. The minimum:

```toml
[project]
name = "scistudio-blocks-spectroscopy"
version = "0.1.2"
dependencies = ["scistudio>=0.3.1a0"]

[project.entry-points."scistudio.blocks"]
scistudio_blocks_spectroscopy = "scistudio_blocks_spectroscopy:get_block_package"

[project.entry-points."scistudio.types"]
scistudio_blocks_spectroscopy = "scistudio_blocks_spectroscopy:get_types"

[project.entry-points."scistudio.previewers"]
scistudio_blocks_spectroscopy = "scistudio_blocks_spectroscopy.previewers:get_previewers"
```

Pin the core dependency to the minimum version whose public API you rely on. The
contract guarantees `stable` symbols do not change incompatibly within a major
line, so `>=` against the version you developed on is correct.

## `PackageInfo`

The blocks entry point returns package metadata alongside the block classes:

```python
from scistudio.blocks.base import PackageInfo

def get_package_info() -> PackageInfo:
    return PackageInfo(name="scistudio-blocks-spectroscopy", version=__version__, ...)

def get_block_package() -> tuple[PackageInfo, list[type]]:
    return get_package_info(), get_blocks()
```

`PackageInfo` carries the name, version, and update channel SciStudio uses to
recognise your package and offer updates. See `scistudio.blocks.base` in the API
reference for its fields.

## The cross-cutting rules

Every package follows the same handful of rules so a consumer meets one boundary
across all packages, not a different one each time (ADR-052 §4):

- **`__all__` on everything public.** The package top level and every public
  submodule declare `__all__`; membership *is* the public surface. If it is not
  in an `__all__`, it is internal.
- **No underscore-named author-facing helper.** Anything an outside author is
  expected to call has a public home — a method on a type, or a public function.
  `_support`-style modules are for genuinely internal code only.
- **Construct on the type, with the canonical name.** A domain constructor is a
  `from_<domain>` **classmethod on the type** (e.g. `Spectrum.from_arrays(...)`),
  not a free function and not a method on a `_support` module.
- **Never shadow `to_pandas` / `to_numpy`.** The ergonomic accessors stay core's;
  redefining them per package is the exact divergence the contract forbids.
- **Blocks and previewers are not the reuse surface.** They register to core;
  authors interoperate through your **types**.
- **Stability + `Since` on every public symbol**, against your **own** version
  line.

The shared `scripts/validate_contract.py` checks the registration callables and
these package-side rules; a CI freeze test (below) catches accidental surface
drift.

## A discovery surface

So an author — or the in-app AI — can find your public types and constructors
*without reading your source*, expose a small discovery function (ADR-052 §4.4):
"what public types and constructors does this package provide." This is what
lets the assistant write a correct block against your package. Mark it
`provisional` until its shape settles.

## Start from the template

Do not hand-roll the layout. `scistudio-package-template` scaffolds a package
that is **correct by construction**:

- the MUST items (a core-subclass type stub, a typed `Meta`, a `from_<domain>`
  classmethod) ship as skeletons that `raise NotImplementedError`, so an
  unfinished contract fails loudly instead of shipping half-done;
- the SHOULD items (extra constructors/helpers) ship as empty files to fill in;
- it carries the **same** generated API reference build and the golden-snapshot
  **freeze test** core uses, run against your version line — so your public
  surface gets identical anti-drift protection.

Generate your reference the same way core does (mkdocstrings/griffe over your
declared `__all__`), version-stamped to your release.

## Versioning and deprecation

Your `Since` and stability tiers are a versioned promise to your users, on your
own version line:

- **`stable`** — no incompatible change within a major version. To remove or
  break a `stable` symbol, deprecate it for **at least one minor release** first,
  with a changelog entry and, where practical, a runtime `DeprecationWarning`
  pointing at the replacement.
- **`provisional`** — may change in a minor release, with a changelog note.
- **`internal`** — no promise; change freely.

A new public symbol ships with a `Since` equal to the release it first appears
in. The freeze test makes any surface change a reviewable diff, so changes are
deliberate and documented rather than accidental.

## Release

During the alpha, distribution is deliberately simple — no registry, no remote
package browser:

1. **Build the wheel.** Build your package as you would any Python distribution
   (e.g. `python -m build`), producing a `scistudio_blocks_*-<version>.whl`.
2. **Attach it to a GitHub release.** Cut a release on your package's GitHub
   repository and upload the `.whl` as a release asset. The release tag is your
   version line; keep it in step with the `version` in `pyproject.toml` and your
   `Since` markers.
3. **Users install it from the GUI.** A user downloads the `.whl` and installs
   it with the desktop app's **Local Package Installer** (in the toolbar):
   they pick the wheel, and SciStudio copies it into the user-scoped plugin
   directory and uses the bundled Python to install the package's runtime
   dependencies there — no system Python needed, and the app bundle is never
   modified. The backend then refreshes the block registry, so your blocks,
   types, and previewers appear in the palette without a restart.

That is the whole alpha loop: **build → GitHub release → GUI install.** Core
discovers the package through its entry points exactly as described above; the
only alpha-specific part is *how the file reaches the user* (a manual download
rather than a registry).

`PackageInfo` still carries your name, version, and update channel, which a
package may use for its own over-the-air update mechanism; that is independent of
this alpha install path.

## Recap

| Step | Where |
|---|---|
| Design types | [types.md](types.md) |
| Write blocks | [blocks.md](blocks.md) |
| Add previewers | [previewers.md](previewers.md) |
| Wire entry points, follow the rules, release | this page |

The exhaustive per-symbol interface is always the **generated API reference**;
this guide is how you design and build a package that the reference can describe
cleanly.
