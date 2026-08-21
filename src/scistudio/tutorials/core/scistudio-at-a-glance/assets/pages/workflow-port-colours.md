# Port colours

The coloured dots on a block's edges are its **ports**, and the colour names
the **data type** that passes through. Matching colours connect; a wire takes
its colour from the port it leaves.

Where a colour comes from, in order:

- A type can **declare its own** fill and ring colours — you picked one for
  your Image type in level 2, and that is why its ports were yours.
- The core types have hand-picked colours.
- Everything else gets a steady colour derived from its name — the same type
  is the same colour everywhere, every time.

One list of types supplies every surface, so a type's colour in the palette
and on the canvas can never disagree.
