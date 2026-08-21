# What render receives

Your render function is handed one argument: the bound output, wrapped as a
collection. If the output is one table it holds one item; if it is five
arrays it holds five.

- `collection.types` — what is in there
- `collection.items` — the items themselves
- `collection.items.open()` — all of them, as native values
- `collection.items.open_one()` — the first, when you expect exactly one

It is **lazy**: nothing is read until you `open()` it, and it opens into the
native thing — a DataFrame, an array — ready to plot.
