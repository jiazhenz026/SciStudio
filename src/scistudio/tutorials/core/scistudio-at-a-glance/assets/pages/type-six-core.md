# The six core types

Each core type is paired with a storage backend that fits its access
pattern — that pairing is *why* there are exactly these six:

- **Array** — n-dimensional numbers; stored chunked and compressed (Zarr),
  built for data too big to read in one piece.
- **Series** and **DataFrame** — columns and tables; stored columnar
  (Arrow/Parquet), built for fast column reads.
- **Text** — plain text, stored as plain files.
- **Artifact** — any file, kept exactly as it is.
- **CompositeData** — the one you have *not* used: a record with named
  slots, each slot stored by its own type's backend, for data that is
  really several things travelling together.

Six types is not a list to memorise — it is one design decision seen from
six angles.

The Data types tab shows a seventh name, **DataObject**. It is not a
seventh kind of data: it is the root all six descend from, which is why a
block that accepts a DataObject accepts any of them — and why your Image,
built on Array, was accepted everywhere an Array was.
