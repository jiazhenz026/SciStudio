# The built-ins

The palette ships nine blocks, and it is worth seeing why so few.

Two do input and output:

- **Load** and **Save** — the only two IO blocks. Every file format is a
  *capability* plugged into them, not another block: **formats are
  capabilities, not blocks**. One Load speaks CSV today and, with a package
  installed, an instrument format tomorrow — same block.

Three arrange data rather than compute on it:

- **DataRouter** — interactively route items from many inputs to many
  outputs. The run pauses and waits for your decision.
- **PairEditor** — interactively reorder items so paired inputs line up.
  You used this in level 3, when the slides and the counts arrived in
  different orders.
- **MergeCollection** — merge several same-typed inputs into one, with as
  many input ports as you need.

And four are starting points rather than finished blocks — one per kind you
can build on, dropped straight onto the canvas: **AI Agent**, **Code**,
**App**, and **Subworkflow**.

Everything else you will ever need is a block someone writes — you, the AI,
or a package.
