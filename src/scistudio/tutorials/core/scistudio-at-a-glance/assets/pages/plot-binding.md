# What a plot points at

A plot binds to **one output port of one block** — any block in the
workflow.

The binding uses the node's stable identity plus the port name, never the
display label. Labels can repeat and drift; identities cannot.

Delete a block and rebuild it and the new block has a new identity — the
plot card shows **broken**, and **Relink** points it at the new target.
Nothing is guessed on your behalf.
