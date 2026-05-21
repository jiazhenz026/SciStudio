# {display_name}

{description}

## Installation

```bash
pip install -e .
```

After installation, SciEasy will automatically discover the blocks in this
package via the `scieasy.blocks` entry-point.

## Usage

Verify the blocks are registered:

```bash
scieasy blocks
```

You should see **{display_name} Example** in the block list.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check . && ruff format --check .
```

## Block development guide

1. Add new block classes in `src/{module_name}/blocks.py` (or create
   sub-modules per category).
2. Register each block class in `get_blocks()` in
   `src/{module_name}/__init__.py`.
3. Add tests in `tests/`.

### Block tiers

- **Tier 1** (recommended): Override `process_item()` only. The engine
  iterates the input Collection for you.
- **Tier 2**: Override `run()` and use `map_items()` or `parallel_map()`.
- **Tier 3**: Override `run()` with full manual Collection handling.

See the [SciEasy block development docs](https://github.com/zjzcpj/SciEasy)
for more details.
