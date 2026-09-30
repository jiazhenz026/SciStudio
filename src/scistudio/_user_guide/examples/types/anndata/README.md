# Type example — an `AnnData` composite type

`AnnData` ([anndata.py](anndata.py)) is a custom type for data that is
**several data objects belonging together**: a single-cell experiment is an
expression matrix plus per-cell annotations plus per-gene annotations, and the
useful unit is the whole bundle. Where the [Image example](../image/)
subclasses `Array` because its data *is* one array, this type subclasses
`CompositeData` — the core type for a named bundle of slots.

## What `expected_slots` buys you

```python
class AnnData(CompositeData):
    expected_slots: ClassVar[dict[str, type]] = {
        "X": DataFrame,    # expression counts: one row per gene, one column per cell
        "obs": DataFrame,  # per-cell metadata: one row per cell
        "var": DataFrame,  # per-gene metadata: one row per gene
    }
```

A subclass that fills in `expected_slots` fixes the bundle's layout:

- **Construction is validated.** `set()` (and the `slots=` constructor)
  rejects a value whose type does not match its slot, so a mis-assembled
  bundle fails at the block that built it, not three steps downstream.
- **Ports can demand the whole.** A block that declares `AnnData` on an input
  port receives all three tables together and can rely on each slot's type.

```python
bundle = AnnData(slots={"X": counts, "obs": cells, "var": genes})
cells = bundle.get("obs").to_pandas()      # slots read like named attributes
```

## Composites elsewhere in the product

Composite types are also how you **plot two outputs through one port**: a
plot binds to exactly one output, so a figure that needs an embedding from
one step and cluster labels from another starts by combining them into a
composite type and a merge block (see the `writing-plots.md` page).

## Completing the type

As with every type, pair it with a `SimpleLoader` so the Load block can read
it — the [IO block example](../../blocks/io-load-tiff/) shows the pattern.
