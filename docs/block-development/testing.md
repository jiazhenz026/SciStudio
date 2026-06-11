---
doc_type: block-development
title: "Testing"
status: living
owner: "@jiazhenz026"
last_updated: 2026-06-10
governed_by:
  - ADR-042
  - ADR-047
  - ADR-048
related_specs:
  - adr-048-developer-docs-refresh
summary: "Testing SciStudio blocks with BlockTestHarness, plus package registry, previewer-registration, template, skill-packaging, and plot validation checks."
---

# Testing

This document covers how to test SciStudio blocks using the
`BlockTestHarness` and common testing patterns, plus the extra checks an
extension package should run: entry-point, previewer-registration, template,
skill-packaging, and plot validation.

---

## Table of Contents

1. [BlockTestHarness Overview](#blocktestharness-overview)
2. [validate_block()](#validate_block)
3. [validate_entry_point_callable()](#validate_entry_point_callable)
4. [smoke_test()](#smoke_test)
5. [Test Patterns](#test-patterns)
6. [What NOT to Test](#what-not-to-test)
7. [Testing Tier 1 Drop-in Blocks vs Tier 2 Packages](#testing-tier-1-vs-tier-2)
8. [Package, previewer, template, and plot checks](#package-previewer-template-and-plot-checks)

---

## BlockTestHarness Overview

`scistudio.testing.BlockTestHarness` is the standard tool for validating
block contracts and running smoke tests.

```python
from scistudio.testing import BlockTestHarness

harness = BlockTestHarness(MyBlock)
```

Parameters:

- `block_class` -- A concrete subclass of `Block`.
- `work_dir` -- Optional working directory for smoke tests. When
  `None`, a temporary directory is used.

---

## validate_block()

Checks that a block class satisfies the block contract.

```python
def test_my_block_contract():
    harness = BlockTestHarness(MyBlock)
    errors = harness.validate_block()
    assert not errors, errors
```

### Checks performed

1. Must be a subclass of `Block`.
2. Must not be abstract (no unimplemented abstract methods).
3. Must define `input_ports` as a list of `InputPort`.
4. Must define `output_ports` as a list of `OutputPort`.
5. Must have a `run()` method.
6. Must have a non-empty `name` string (not `"Unnamed Block"`).

Returns a list of human-readable error strings. An empty list means the
block passes all checks.

---

## validate_entry_point_callable()

For Tier 2 packages, validates the return value of the `scistudio.blocks`
entry-point callable.

```python
def test_package_entry_point():
    from my_plugin import get_blocks
    harness = BlockTestHarness(Block)  # any Block subclass for init
    result = get_blocks()              # (PackageInfo, list[type])
    errors = harness.validate_entry_point_callable(result)
    assert not errors, errors
```

### Accepted return formats

Per ADR-025, the entry-point callable must return either:

- `(PackageInfo, list[type[Block]])` -- package metadata + blocks.
- `list[type[Block]]` -- plain block list (backward compatible).

### Checks performed

- Validates the tuple structure.
- If `PackageInfo` is present, validates its fields (non-empty `name`,
  non-empty `version`).
- Validates each block class in the list using `validate_block()`.

---

## smoke_test()

Instantiates the block, calls `run()`, and returns the outputs.

```python
import numpy as np
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection

def test_my_block_smoke(tmp_path):
    # Create synthetic input
    arr = Array(axes=["y", "x"], shape=(64, 64), dtype="float64", data=np.random.rand(64, 64))
    coll = Collection(items=[arr], item_type=Array)

    harness = BlockTestHarness(MyBlock, work_dir=tmp_path)
    result = harness.smoke_test(
        inputs={"image": coll},
        params={"threshold": 0.5},
    )
    assert "output" in result
```

### Parameters

- `inputs` -- Mapping of port name to input data. Values should be
  `Collection` instances.
- `params` -- Optional parameters passed to `BlockConfig`.

### Return value

The output dict returned by `block.run()`.

### Error propagation

Any exception raised by the block's `run()` method is propagated to
the caller for inspection.

---

## Test Patterns

### Contract validation test

Every block should have a contract test:

```python
from scistudio.testing import BlockTestHarness

def test_contract():
    harness = BlockTestHarness(InvertImage)
    errors = harness.validate_block()
    assert not errors, errors
```

### Smoke test with synthetic data

```python
import numpy as np
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection

def test_invert_smoke():
    data = np.array([[0, 100], [200, 255]], dtype=np.uint8)
    arr = Array(axes=["y", "x"], shape=data.shape, dtype=str(data.dtype), data=data)
    coll = Collection(items=[arr], item_type=Array)

    harness = BlockTestHarness(InvertImage)
    result = harness.smoke_test(inputs={"image": coll})

    assert "image" in result
    output_coll = result["image"]
    assert len(output_coll) == 1
```

### Testing process_item directly

For unit-testing the core logic without the full block lifecycle:

```python
def test_process_item_directly():
    block = InvertImage()
    config = BlockConfig()

    data = np.array([[10, 20], [30, 40]], dtype=np.float64)
    item = Array(axes=["y", "x"], shape=data.shape, dtype=str(data.dtype), data=data)

    result = block.process_item(item, config)
    result_data = result.to_memory()
    expected = np.array([[40, 30], [20, 10]], dtype=np.float64)
    np.testing.assert_array_equal(result_data, expected)
```

### Testing IOBlock loaders

```python
def test_loader_smoke(tmp_path):
    # Create a test file
    import numpy as np
    test_file = tmp_path / "test.npy"
    np.save(str(test_file), np.zeros((64, 64)))

    harness = BlockTestHarness(MyLoader, work_dir=tmp_path)
    result = harness.smoke_test(
        inputs={},
        params={"path": str(test_file)},
    )
    assert "data" in result
```

### Testing with fixtures

```python
import pytest
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection

@pytest.fixture
def sample_image():
    data = np.random.rand(128, 128).astype(np.float32)
    arr = Array(axes=["y", "x"], shape=data.shape, dtype=str(data.dtype), data=data)
    return arr

@pytest.fixture
def sample_collection(sample_image):
    return Collection(items=[sample_image], item_type=Array)

def test_block_with_fixture(sample_collection):
    harness = BlockTestHarness(MyBlock)
    result = harness.smoke_test(inputs={"image": sample_collection})
    assert "output" in result
```

### Asserting output types

```python
def test_output_types(sample_collection):
    harness = BlockTestHarness(MyBlock)
    result = harness.smoke_test(inputs={"image": sample_collection})
    output = result["output"]

    # Check Collection properties
    assert isinstance(output, Collection)
    assert output.item_type == Array
    assert len(output) == 1

    # Check item properties
    item = output[0]
    assert isinstance(item, Array)
    assert item.axes == ["y", "x"]
```

---

## What NOT to Test

Block-level tests should focus on your block's logic. Do NOT test:

- **Subprocess behavior**: Your block runs in-process during tests.
  Cross-process serialization is the engine's responsibility.
- **Collection serialization**: The engine handles this.
- **Port validation logic**: Tested by the framework.
- **Auto-flush internals**: Tested by the framework.

---

## Testing Tier 1 vs Tier 2

### Tier 1 (drop-in blocks)

Place test files alongside your block files or in a separate `tests/`
directory:

```
my_blocks/
  invert_image.py
  test_invert_image.py
```

### Tier 2 (installable packages)

Use a standard Python package test layout:

```
my-blocks/
  src/
    my_blocks/
      __init__.py
      blocks/
        invert.py
  tests/
    test_invert.py
    conftest.py
```

For Tier 2 packages, also test the entry-point:

```python
def test_entry_point():
    from my_blocks import get_blocks
    harness = BlockTestHarness(Block)
    info, blocks = get_blocks()
    errors = harness.validate_entry_point_callable((info, blocks))
    assert not errors, errors
```

---

## Package, previewer, template, and plot checks

An extension package should test more than its block contracts. The checks
below mirror what the SciStudio test suite itself runs.

### Package registry layout (ADR-047)

The registry is decomposed into private scan helpers (`registry/_scan.py`,
`registry/_capability.py`, `registry/_spec.py`) and exposes a capability-aware
lookup surface. Test that your `scistudio.blocks` entry-point callable returns
an accepted shape — `(PackageInfo, list[type[Block]])` (primary) — and that your
IO blocks expose `FormatCapability` records rather than the removed legacy IO
finder API.

### Previewer registration (ADR-048)

If your package ships `scistudio.previewers`, assert the factory returns a
non-empty `list[PreviewerSpec]`, each `owner_kind=OwnerKind.PACKAGE`, with a
unique `previewer_id` and a resolvable `backend_provider`:

```python
def test_previewers_register():
    from scistudio.previewers.models import OwnerKind, PreviewerSpec
    from my_blocks.previewers import get_previewers

    specs = get_previewers()
    assert specs
    ids = set()
    for spec in specs:
        assert isinstance(spec, PreviewerSpec)
        assert spec.owner_kind is OwnerKind.PACKAGE
        assert spec.previewer_id and spec.previewer_id not in ids
        assert spec.target_type
        ids.add(spec.previewer_id)
```

A backend provider must use `request.data_access` for all reads and must return
a typed error envelope rather than raising for routine failures
([Previewers and Plot Jobs](previewers-and-plots.md#the-backend-provider)).

### Scaffold / template checks

The package scaffold (`scistudio init-block-package`) is executable
documentation. Its generated blocks must use valid `InputPort` / `OutputPort`
fields (`accepted_types`, never a nonexistent `produced_type`) and a valid
`get_blocks()` entry-point shape. The SciStudio suite asserts this in
`tests/cli/test_new_block_package.py` and `tests/api/test_blocks_template.py`.

### Skill packaging / provisioning

AI skills ship in the wheel and cross-install to Claude and Codex. The suite
checks the packaged skill tree in `tests/packaging/test_wheel_skills.py` and
`tests/agent_provisioning/test_skills.py`.

### Plot job validation (ADR-048)

A plot job is preview-only; you validate and run it rather than asserting a
block contract. `validate_plot` checks the manifest schema, target reachability,
path traversal, allowed output formats, and the `render` entrypoint (R-runner
unavailability is a warning, not an error). `run_plot_job` renders to the
preview cache and reports a status. See
[Previewers and Plot Jobs](previewers-and-plots.md#validate-and-run).
