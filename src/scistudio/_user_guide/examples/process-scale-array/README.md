# ProcessBlock example — normalize table columns

`NormalizeColumns` ([block.py](block.py)) rescales every numeric column of each
table to the 0..1 range. It is the simplest and most common kind of block: a
**per-item transform**.

## Why `ProcessBlock`

`ProcessBlock` is for blocks where:

- every item is transformed **independently**, and
- the number of items does **not** change (no filtering, merging, or splitting).

You write only `process_item(self, item, config, state=None)` — the base class
loops over the incoming batch (`Collection`) and calls it once per item, packing
the results back into a `Collection` for the output port. About 80% of blocks
need nothing more than this.

## What to notice

- **Reading the table.** `item.to_pandas()` hands you a pandas `DataFrame`. The
  data is stored as Arrow under the hood; `to_pandas()` is the *ergonomic
  accessor* that reads it out to the form most people work in. (`to_numpy()` and
  the raw `to_memory()` → `pyarrow.Table` are there too.)
- **Building the result.** A `DataFrame` is constructed from an Arrow table:
  `DataFrame(data=pa.Table.from_pandas(df))`. You always build *back* to the
  canonical Arrow form — the ergonomic accessors are read-only.
- **Parameters.** `config_schema` is JSON Schema; read values with
  `config.get("epsilon", 1e-12)`.

## When you need the whole batch instead

`ProcessBlock` hides the batch from you. If your block must **filter**, **merge**,
**split**, or otherwise change the item count, subclass `Block` and write `run()`,
which receives and returns whole `Collection`s:

```python
from scistudio.blocks.base import Block

class DropEmptyTables(Block):
    def run(self, inputs, config):
        kept = [t for t in inputs["input"] if t.row_count]
        return {"output": self.pack(kept, item_type=DataFrame)}
```

`self.pack`, `self.map_items`, `self.parallel_map`, `self.unpack`, and
`self.unpack_single` are the `Collection` helpers on every block — see `Block`
in the API reference.

## Try it

Wire any table source into `input`, run, and the `output` port carries the
normalized tables.
