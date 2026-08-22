# The kinds of block

A block's kind comes from what it is built on, not from a label anyone types:
the product reads the class it subclasses. Six kinds have names.

- **io** — moves data in and out of the workflow. Load and Save, and the
  loader you wrote in level 2: it subclassed an IO block, so it is one.
- **process** — takes data in, gives data out. This is where most blocks
  live, including every one you built by hand: Normalize Fluorescence,
  Segment Cells, the joint-analysis block, the QC filter the agent wrote.
- **code** — a block whose body is a script the product runs for you, rather
  than a Python class you ship.
- **app** — wraps an external program as a block.
- **ai** — a step where an AI agent does the work, like the one in level 4.
- **subworkflow** — a whole workflow folded into a single block.

Two things worth knowing about that list. A block built on the plain `Block`
base — which is what the New-custom-block template starts you with — belongs
to none of the six, and the product shows it as **unknown** until you
subclass one of them. And "process" is not a lesser kind: the blocks that
carry your science are almost all process blocks.
