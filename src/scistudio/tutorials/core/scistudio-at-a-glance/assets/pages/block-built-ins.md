# The built-ins

The palette ships a small set on purpose:

- **Load** and **Save** — the only two IO blocks. Every file format is a
  *capability* plugged into them, not another block: **formats are
  capabilities, not blocks**. One Load speaks CSV today and, with a package
  installed, an instrument format tomorrow — same block.
- **DataRouter** — interactively route items from many inputs to many
  outputs. The run pauses and waits for your decision.
- **PairEditor** — interactively reorder items so paired inputs line up.
- **MergeCollection** — merge several same-typed inputs into one, with as
  many input ports as you need.

Everything else you will ever need is a block someone writes — you, the AI,
or a package.
