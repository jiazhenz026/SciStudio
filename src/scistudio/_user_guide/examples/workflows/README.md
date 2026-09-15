# Workflow example — load and segment

A complete, minimal workflow YAML: two nodes, one edge. It is the graph the
other examples build toward — with the
[Image type](../types/image/), the
[TIFF loader](../blocks/io-load-tiff/), and the
[segmentation block](../blocks/process-segment-cells/) in a project, this file
dropped into `workflows/main.yaml` runs unchanged.

## The shape of the file

```yaml
workflow:
  id: main                 # the workflow's identity inside the project
  version: 1.0.0
  nodes:
    - id: load-cells       # the name you wire by, unique within the workflow
      block_type: load_data   # the registered block
      config:
        params: ...        # the block's config_schema values
      layout: ...          # where the node sits on the canvas
  edges:
    - source: load-cells:data    # "<node id>:<output port>"
      target: segment:image      # "<node id>:<input port>"
```

## What to notice

- **`block_type` is the registered name.** `load_data` is the built-in Load
  block; `segment_cells` is the drop-in block from the
  [process example](../blocks/process-segment-cells/) — the `type_name` its
  class declares. Custom blocks become usable the moment their file lands in
  `blocks/`.
- **Load dispatch is by (type, extension).** The Load node declares
  `core_type: Image` and a path list; the registry routes `.tif` files to the
  loader that claims `(Image, .tif)`. No capability id is written down — a
  drop-in block's id carries its source file's mtime, so naming one here would
  break on any other machine.
- **Paths are project-relative.** A run executes with the project root as its
  working directory, so `data/raw/cells_01.tif` means `<project>/data/raw/…`.
- **`layout` is cosmetic.** Positions are canvas coordinates; the graph's
  meaning is entirely in `nodes` and `edges`.

For the full schema (conditions, mappings, sub-workflows, every accepted
key), see the **Workflow YAML** page in the API reference.
