# Previewers follow types

A previewer is registered **for a type** — tables get the table viewer,
arrays the array viewer, and your types can get viewers of their own.

When a type has no previewer, the lookup walks **up the type chain** and uses
the parent's. You have lived this: in level 2, before Image had a previewer,
your images displayed as Array's table of numbers — the parent's viewer,
doing its honest best.

When several tiers offer one, the closest wins: **project first, then your
library, then packages**, with the core viewers as the floor that always
catches.
