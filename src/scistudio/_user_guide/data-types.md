# Data types

In SciStudio, every value that flows between blocks carries a **type** that says
what shape the data has, where it is stored, and what metadata travels with it.
Blocks declare which types each port accepts, so when you draw a wire the canvas
**type-checks** it: a port that expects an image accepts an image and rejects a
spectrum, and the check happens while you build the workflow.

A value is a lightweight **data object**. It points to where the data is stored
and carries the payload into memory only when a block asks for it, so large
results move between blocks as references. SciStudio manages this for you; it is
what lets a workflow move gigabyte-scale images around while loading them only
where they are used.

## The built-in types

SciStudio keeps the core data model small. These types are the common **shapes**
that domain types build on. Each one is stored in a backend chosen for how that
shape is accessed.

| Type | What it represents | Stored as | Typical use |
|---|---|---|---|
| `Array` | N-dimensional numeric data with named axes | Zarr (chunked, compressed) | Images, volumes, stacks, hyperspectral cubes |
| `Series` | One-dimensional labelled data | Arrow / Parquet | Spectra, traces, time series, calibration curves |
| `DataFrame` | Tabular rows and named columns | Arrow / Parquet | Measurements, features, peak lists, QC tables |
| `Text` | A small textual payload | In memory or filesystem | Notes, logs, prompts, small structured text |
| `Artifact` | A file whose format SciStudio does not parse | Filesystem (original file preserved) | Reports, PDFs, instrument files, archives |
| `CompositeData` | A named bundle of several data objects | One backend per slot | An omics matrix kept together with its observation and coordinate tables |

These six types are the core data model. When a block hands you the value in code
you read it as the natural Python form — an `Array` as a numpy array, a
`DataFrame` or `Series` as a table, `Text` as a string — see
[writing-blocks.md](writing-blocks.md).

## You connect blocks by type

Inside a workflow, data lives in a **canonical zone**: it is typed data objects.
File formats are handled at the **edges**: a Load block turns your instrument
files into typed data on the way in, and a Save block turns typed data into the
format you ask for on the way out. You connect blocks by *type*, and you choose
an output format with an explicit Save step.

## How values travel: collections

Every value that moves between blocks travels as a **collection**: an ordered,
same-type group of items. A single object is a length-one collection; a folder of
images is a longer one. A collection carries an item type, and ports check that
item type, so a port that accepts `Array` accepts a collection of `Array` the
same way it accepts one. Blocks that process one item at a time loop over the
collection for you (see [writing-blocks.md](writing-blocks.md)).

## Two layers: core categories and domain types

The built-in types are broad **categories**. Installed **packages** define
**domain types** that pin down scientific meaning by subclassing a category and
adding axis or slot rules and typed metadata:

- an `Image` *is an* `Array` that requires `y` and `x` axes and carries
  microscopy metadata such as pixel size;
- a `Spectrum` *is a* `Series` of intensity against wavelength, with its units
  and instrument recorded.

Domain types come from packages you install, and the app discovers them
automatically. Because a domain type is a subclass of a core category, subtypes
flow into supertype ports: an `Image` satisfies a port that wants an `Array`,
while a port that wants an `Image` requires that specific type.

If the built-in types do not capture your data's structure or metadata, you can
define your own domain type in a few lines — see
[custom-types.md](custom-types.md).

## Reading only what you need

Because a data object points to stored data, a block can read the whole thing,
read a single **slice**, or **iterate in chunks**. Named axes make that
meaningful for scientific data: a block can work over the spatial axes of an
image while stepping through time, depth, or channel. The mechanics are covered
in [writing-blocks.md](writing-blocks.md); most of the time you ask for the data
and SciStudio loads the minimum required.
