# Tips

- Four output formats: **svg** (the default), **png**, **pdf**, **jpeg** —
  each plot declares which it allows.
- **Plots are preview-only.** A plot is not part of the workflow graph, is
  never scheduled, and does not appear in History. Its figure lives in a
  preview cache and is **overwritten on the next run**.
- So: **Export is the only way a figure survives.** History and git store
  the recipe, not the results — a restored project re-draws figures, it does
  not contain them.
- And a conclusion that matters belongs in a **block**, where it is recorded
  and reproducible — not only in a plot script.
