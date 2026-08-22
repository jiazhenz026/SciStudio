# Files and formats

A file extension is a hint for humans. It is **not the data contract**.

When Load reads a file, what the run records is *which capability* read it —
a stable id naming exactly the reader used. Two packages might both handle
`.csv`; the capability id says which one this run actually meant, so the run
can be replayed without guessing.

The same goes for Save: you choose a format, and the choice is recorded as
the capability that wrote it. Extensions come and go; the capability id is
the fact.
