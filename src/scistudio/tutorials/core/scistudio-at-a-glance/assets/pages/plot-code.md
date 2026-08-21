# The render script

Python or R — your choice per plot.

- **Python**: `def render(collection):` returns a matplotlib Figure, or the
  path of an image file it wrote. Set the size when you create the figure
  (`figsize`).
- **R**: `render <- function(collection)` returns a ggplot object or draws
  with base graphics; a top-level `figure_size(w, h)` sets the size in
  inches for either.

The scaffold each new plot starts from has working examples to paste over.
