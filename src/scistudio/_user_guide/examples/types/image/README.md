# Type example — an `Image` type

`Image` ([image.py](image.py)) is the smallest useful custom type: a 2-D
micrograph built on the core `Array`. Copy the folder's file into your
project's `types/` — the registry picks it up on reload, and the project has
a type called `Image`.

## What a subclass adds (and what it inherits)

The core types are the ones SciStudio knows how to **store and reload** —
`Array` keeps its data in a chunked Zarr store. A subclass inherits all of
that and adds only meaning:

- **A name.** The class name is the registered type name; it appears in the
  Data types tab, in port type lists, and in the Load block's `core_type`
  choices.
- **Rules.** `required_axes = frozenset({"y", "x"})` means an `Image`
  constructed without both spatial axes raises — a block that declares
  `Image` on a port can rely on `y` and `x` being present. (`allowed_axes`
  and `canonical_order` are the other two knobs; see the `Array` page in the
  API reference.)
- **Appearance (optional).** This example declares no colors: a subclass that
  says nothing inherits its parent's fill and gets an outline of its own, so
  an Image reads as "an Array, but a particular one" on every port. A type
  that wants its own declares `ui_color` / `ui_ring_color` as CSS hex
  strings.

Subtype flows with it: because an `Image` *is* an `Array`, every port, panel,
and plot that accepts `Array` accepts an `Image`.

## The type is half the story

A type nobody can load is unusable, so a real project pairs it with a loader:
the [IO block example](../../blocks/io-load-tiff/) teaches the Load block to
read `.tif` files into this `Image`, and the
[process example](../../blocks/process-segment-cells/) consumes it. For typed
metadata (a frozen Pydantic model on `Meta`), see the `custom-types.md` page
of this guide.
