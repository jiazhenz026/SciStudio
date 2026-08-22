# What does saving lose?

Every save format declares how much survives the trip, so this question has
an inspectable answer — the format's **metadata fidelity** level:

- **pixel_only** — the raw values and nothing else.
- **typed_meta** — values plus the type's own metadata fields.
- **format_specific** — also keeps the format's native metadata.
- **lossless** — a faithful round trip, guaranteed.

When it matters — instrument metadata, units, acquisition settings — check
the level before you pick the format, not after.
