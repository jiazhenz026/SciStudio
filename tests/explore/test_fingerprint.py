"""Tests for the notebook observation fingerprint (ADR-054 spec 2, T-007).

Covers:

* **SC-006** — the hard one. An in-place mutation of a numpy array, a pandas
  frame, a pandas series, a list, a dict, and a set is detected, each with its
  own test, and each with the unchanged-equality direction beside it. Every
  mutation here leaves the length and shape alone, because a fingerprint that
  only noticed ``len()`` moving would pass a weaker test and fail every real
  notebook: ``df.dropna(inplace=True)`` is the easy case, ``df.loc[2, "x"] = 0``
  is the one that matters.
* **FR-025 / SC-007** — the declared bound. Content above the limit is sampled
  rather than hashed whole, the sample spans the full extent (a change to the
  *last* element is seen), the bytes fed to the hash never exceed
  ``max_total_bytes``, and the wall-clock cost of the largest fixture stays
  inside ``max_seconds``.
* **FR-024 / FR-029** — the unobservable fallback. A type no content rule
  covers falls back to identity and is reported, and ``repr`` is never called:
  the test counts the calls, because a fingerprint that guessed from a stateful
  representation would report a change on every run.
* **FR-004 / FR-035** — purity and import discipline, asserted against the
  module's own source so a later edit that adds an eager numpy import fails
  here rather than in a cold-start profile.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from scistudio.explore import fingerprint as fingerprint_module
from scistudio.explore.fingerprint import (
    FINGERPRINT_BUDGET,
    Fingerprint,
    FingerprintBudget,
    ObservedChange,
    _fingerprint_context,
    compare_namespaces,
    fingerprint,
)
from scistudio.stability import get_stability

# ---------------------------------------------------------------------------
# SC-006: in-place mutation is detected, and an unchanged object is equal.
# One test per type, per the success criterion, plus its equality direction.
# ---------------------------------------------------------------------------


def test_sc006_numpy_array_in_place_mutation_is_detected() -> None:
    """``array[3] += 1`` moves the digest — same shape, same dtype, same object."""
    array = np.arange(64, dtype=np.float64)
    before = fingerprint(array)

    array[3] += 1.0

    assert fingerprint(array) != before
    assert before.observable is True


def test_sc006_numpy_array_unchanged_is_equal() -> None:
    """An untouched array fingerprints the same twice, and matches an equal copy."""
    array = np.arange(64, dtype=np.float64)

    assert fingerprint(array) == fingerprint(array)
    assert fingerprint(array) == fingerprint(array.copy())


def test_sc006_dataframe_in_place_mutation_is_detected() -> None:
    """``df.loc[2, "value"] = -1`` moves the digest with the shape unchanged."""
    frame = pd.DataFrame({"value": [1.0, 2.0, 3.0], "label": ["a", "b", "c"]})
    before = fingerprint(frame)

    frame.loc[2, "value"] = -1.0

    assert frame.shape == (3, 2)
    assert fingerprint(frame) != before


def test_sc006_dataframe_unchanged_is_equal() -> None:
    """An untouched frame fingerprints the same twice, and matches a copy."""
    frame = pd.DataFrame({"value": [1.0, 2.0, 3.0], "label": ["a", "b", "c"]})

    assert fingerprint(frame) == fingerprint(frame)
    assert fingerprint(frame) == fingerprint(frame.copy())


def test_sc006_series_in_place_mutation_is_detected() -> None:
    """``series.iloc[2] = -1`` moves the digest with the length unchanged."""
    series = pd.Series([1.0, 2.0, 3.0], name="signal")
    before = fingerprint(series)

    series.iloc[2] = -1.0

    assert len(series) == 3
    assert fingerprint(series) != before


def test_sc006_series_unchanged_is_equal() -> None:
    """An untouched series fingerprints the same twice, and matches a copy."""
    series = pd.Series([1.0, 2.0, 3.0], name="signal")

    assert fingerprint(series) == fingerprint(series)
    assert fingerprint(series) == fingerprint(series.copy())


def test_sc006_list_in_place_mutation_is_detected() -> None:
    """``values[2] = -1`` moves the digest without changing the length."""
    values = [1, 2, 3, 4]
    before = fingerprint(values)

    values[2] = -1

    assert len(values) == 4
    assert fingerprint(values) != before


def test_sc006_list_unchanged_is_equal() -> None:
    """An untouched list fingerprints the same twice, and matches an equal list."""
    values = [1, 2, 3, 4]

    assert fingerprint(values) == fingerprint(values)
    assert fingerprint(values) == fingerprint([1, 2, 3, 4])


def test_sc006_dict_in_place_mutation_is_detected() -> None:
    """Reassigning an existing key moves the digest without changing the length."""
    mapping = {"a": 1, "b": 2, "c": 3}
    before = fingerprint(mapping)

    mapping["b"] = -1

    assert len(mapping) == 3
    assert fingerprint(mapping) != before


def test_sc006_dict_unchanged_is_equal() -> None:
    """An untouched dict fingerprints the same twice, and matches an equal dict."""
    mapping = {"a": 1, "b": 2, "c": 3}

    assert fingerprint(mapping) == fingerprint(mapping)
    assert fingerprint(mapping) == fingerprint({"a": 1, "b": 2, "c": 3})


def test_sc006_set_in_place_mutation_is_detected() -> None:
    """Swapping one member for another moves the digest — the length does not change."""
    members = {1, 2, 3, 4}
    before = fingerprint(members)

    members.discard(3)
    members.add(-1)

    assert len(members) == 4
    assert fingerprint(members) != before


def test_sc006_set_unchanged_is_equal() -> None:
    """An untouched set fingerprints the same twice, and matches an equal set.

    Built in the reverse order, because set iteration order is an artefact of
    the hash table and the fingerprint must not depend on it.
    """
    members = {1, 2, 3, 4}

    assert fingerprint(members) == fingerprint(members)
    assert fingerprint(members) == fingerprint({4, 3, 2, 1})


# ---------------------------------------------------------------------------
# FR-024: the rest of the content-inspected types.
# ---------------------------------------------------------------------------


def test_tuple_content_is_inspected() -> None:
    """A tuple is immutable, but what it holds is not."""
    inner = [1, 2]
    pair = (inner, "text")
    before = fingerprint(pair)

    inner[0] = 99

    assert fingerprint(pair) != before
    assert fingerprint(pair).observable is True


def test_strings_and_bytes_are_inspected_by_content() -> None:
    """Equal content agrees; a one-character difference does not."""
    assert fingerprint("hello") == fingerprint("hel" + "lo")
    assert fingerprint("hello") != fingerprint("hellp")
    assert fingerprint(b"hello") == fingerprint(b"hello")
    assert fingerprint(b"hello") != fingerprint(b"hellp")
    assert fingerprint(bytearray(b"ab")) != fingerprint(bytearray(b"ac"))


def test_numbers_are_inspected_by_content() -> None:
    """Numbers of every builtin kind separate by value, including very large ints."""
    assert fingerprint(1) == fingerprint(1)
    assert fingerprint(1) != fingerprint(2)
    assert fingerprint(1.5) != fingerprint(1.6)
    assert fingerprint(1 + 2j) != fingerprint(1 + 3j)
    assert fingerprint(2**4096) != fingerprint(2**4096 + 1)
    assert fingerprint(-(2**4096)) != fingerprint(2**4096)
    assert fingerprint(None) == fingerprint(None)
    assert fingerprint(True) != fingerprint(False)


def test_unlike_types_with_like_content_do_not_collide() -> None:
    """A list, a tuple, and a set of the same elements are three different values."""
    digests = {
        fingerprint([1, 2, 3]).digest,
        fingerprint((1, 2, 3)).digest,
        fingerprint({1, 2, 3}).digest,
        fingerprint(frozenset({1, 2, 3})).digest,
    }
    assert len(digests) == 4
    assert fingerprint(1).digest != fingerprint(1.0).digest
    assert fingerprint(True).digest != fingerprint(1).digest


def test_nesting_is_structural_not_flat() -> None:
    """``[[1], [2]]`` and ``[1, 2]`` are different values, not the same bytes."""
    assert fingerprint([[1], [2]]) != fingerprint([1, 2])
    assert fingerprint({"a": {"b": 1}}) != fingerprint({"a": {"b": 2}})


def test_numpy_dtype_and_shape_are_part_of_the_value() -> None:
    """Reshaping or recasting the same numbers is a change worth reporting."""
    base = np.arange(12, dtype=np.int64)
    assert fingerprint(base) != fingerprint(base.reshape(3, 4))
    assert fingerprint(base) != fingerprint(base.astype(np.float64))
    assert fingerprint(np.array([], dtype=np.float64)) == fingerprint(np.array([], dtype=np.float64))


def test_non_contiguous_array_is_inspected_without_copying_the_whole_array() -> None:
    """A strided view is a normal value; its mutations are seen like any other."""
    view = np.arange(1000, dtype=np.float64)[::2]
    assert not view.flags["C_CONTIGUOUS"]
    before = fingerprint(view)

    view[7] = -1.0

    assert fingerprint(view) != before


def test_object_dtype_array_is_walked_element_by_element() -> None:
    """An object array holds pointers; hashing the buffer would miss the mutation."""
    inner = [1, 2]
    array = np.array([inner, {"k": 1}, "text"], dtype=object)
    before = fingerprint(array)

    inner.append(3)

    assert fingerprint(array) != before


# ---------------------------------------------------------------------------
# FR-024 / FR-029: the unobservable fallback, and what it must not do.
# ---------------------------------------------------------------------------


class _StatefulRepr:
    """A value whose representation changes every time it is asked for one.

    The shape of object a ``repr``-based fingerprint gets wrong: a connection, a
    cursor, a model with a training-step counter, anything holding an address.
    """

    repr_calls = 0

    def __repr__(self) -> str:
        type(self).repr_calls += 1
        return f"<_StatefulRepr {random.random()} {type(self).repr_calls}>"


def test_unknown_type_falls_back_to_identity_and_is_reported() -> None:
    """FR-029: the fallback is reported, not hidden."""
    value = _StatefulRepr()

    result = fingerprint(value)

    assert result.observable is False
    assert result.type_name.endswith("_StatefulRepr")


def test_fallback_never_consults_repr() -> None:
    """The digest must not come from ``repr`` — this counts the calls.

    If it did, the same untouched object would fingerprint differently on every
    call and the observation would report a change the person cannot act on.
    """
    _StatefulRepr.repr_calls = 0
    value = _StatefulRepr()

    first = fingerprint(value)
    second = fingerprint(value)

    assert _StatefulRepr.repr_calls == 0
    assert first == second


def test_fallback_separates_distinct_objects() -> None:
    """Two live objects of an unknown type do not share a fingerprint."""
    left = _StatefulRepr()
    right = _StatefulRepr()

    assert fingerprint(left) != fingerprint(right)


def test_unobservable_propagates_out_of_a_container() -> None:
    """A list holding one unknown value is not fully observable, and says so.

    The list's own content is still inspected — appending is still detected —
    but the person is told the observation does not cover everything inside it.
    """
    values = [1, 2, _StatefulRepr()]

    result = fingerprint(values)

    assert result.observable is False
    assert result.type_name == "list"

    before = fingerprint(values)
    values.append(3)
    assert fingerprint(values) != before


def test_content_inspected_values_are_observable() -> None:
    """The flag is only ``False`` where a rule was actually missing."""
    for value in ([1], (1,), {1}, {"a": 1}, "s", b"s", 1, 1.0, None, np.arange(3), pd.Series([1])):
        assert fingerprint(value).observable is True, value


def test_a_type_that_raises_on_inspection_is_unobservable_not_an_exception() -> None:
    """Observation must never turn a readable namespace into a traceback."""

    class Hostile(list):  # type: ignore[type-arg]
        def __len__(self) -> int:
            raise RuntimeError("no")

    result = fingerprint(Hostile())

    assert result.observable is False


# ---------------------------------------------------------------------------
# FR-025: the declared bound, the strided sample, and the full extent.
# ---------------------------------------------------------------------------


def test_budget_is_declared_in_one_place() -> None:
    """FR-025: one instance, and it is the one the module uses."""
    assert isinstance(FINGERPRINT_BUDGET, FingerprintBudget)
    assert FINGERPRINT_BUDGET.sample_bytes < FINGERPRINT_BUDGET.whole_content_bytes
    assert FINGERPRINT_BUDGET.whole_content_bytes < FINGERPRINT_BUDGET.max_total_bytes

    source = Path(fingerprint_module.__file__).read_text(encoding="utf-8")
    assert source.count("class FingerprintBudget") == 1
    assert source.count("FINGERPRINT_BUDGET = FingerprintBudget(") == 1


def test_content_below_the_bound_is_hashed_whole() -> None:
    """Below the limit there is no sampling to reason about."""
    array = np.zeros(FINGERPRINT_BUDGET.whole_content_bytes // 8, dtype=np.float64)
    assert array.nbytes == FINGERPRINT_BUDGET.whole_content_bytes

    context = _fingerprint_context(array)

    assert context.hashed_bytes >= array.nbytes
    assert context.truncated is False


def test_content_above_the_bound_is_sampled_not_hashed_whole() -> None:
    """A 64 MB array costs the sample, not sixty-four megabytes of hashing."""
    array = np.arange(8_000_000, dtype=np.float64)
    assert array.nbytes > FINGERPRINT_BUDGET.whole_content_bytes

    context = _fingerprint_context(array)

    assert context.hashed_bytes < FINGERPRINT_BUDGET.whole_content_bytes
    assert context.hashed_bytes <= FINGERPRINT_BUDGET.max_total_bytes


def test_the_sample_spans_the_full_extent_of_an_array() -> None:
    """FR-025 says "across its full extent" — so both ends must be covered."""
    array = np.zeros(8_000_000, dtype=np.float64)
    before = fingerprint(array)

    array[0] = 1.0
    assert fingerprint(array) != before, "a change at the start was missed"

    array[0] = 0.0
    assert fingerprint(array) == before

    array[-1] = 1.0
    assert fingerprint(array) != before, "a change at the end was missed"


def test_the_sample_spans_the_full_extent_of_a_container() -> None:
    """The same guarantee for a list far longer than ``container_items``."""
    values = [0] * 200_000
    assert len(values) > FINGERPRINT_BUDGET.container_items
    before = fingerprint(values)

    values[0] = 1
    assert fingerprint(values) != before, "a change at the start was missed"

    values[0] = 0
    values[-1] = 1
    assert fingerprint(values) != before, "a change at the end was missed"


def test_the_sample_spans_the_full_extent_of_a_frame() -> None:
    """A tall frame is sampled by row and still notices its last row."""
    frame = pd.DataFrame({"value": np.zeros(500_000)})
    before = fingerprint(frame)

    frame.iloc[-1, 0] = 1.0

    assert fingerprint(frame) != before


def test_total_hashed_bytes_never_exceed_the_declared_ceiling() -> None:
    """The whole call is bounded, not each node — a container cannot multiply it."""
    saturating = [np.zeros(FINGERPRINT_BUDGET.whole_content_bytes // 8) for _ in range(64)]

    context = _fingerprint_context(saturating)

    assert context.hashed_bytes <= FINGERPRINT_BUDGET.max_total_bytes
    assert context.truncated is True


def test_node_and_depth_ceilings_hold() -> None:
    """A wide or deep structure is truncated rather than followed forever.

    The node ceiling has to stop the *iteration*, not just the hashing: a
    structure with a quarter of a million nodes must not be walked a quarter of
    a million times to hash the first four thousand.
    """
    wide = _fingerprint_context([[index] * 512 for index in range(512)])
    assert wide.nodes <= FINGERPRINT_BUDGET.max_nodes + 1
    assert wide.truncated is True

    deep: Any = 1
    for _ in range(200):
        deep = [deep]
    assert fingerprint(deep) == fingerprint(deep)


def test_a_self_referential_value_terminates() -> None:
    """Notebook namespaces hold cycles; the fingerprint must not recurse forever."""
    cyclic: list[Any] = [1]
    cyclic.append(cyclic)

    assert fingerprint(cyclic) == fingerprint(cyclic)

    cyclic[0] = 2
    assert fingerprint(cyclic) != fingerprint([1, [1]])


def test_very_large_mapping_is_bounded_by_the_scan_limit() -> None:
    """Past ``max_scan_items`` the fingerprint records that it took a prefix."""
    budget = FingerprintBudget(max_scan_items=1000, container_items=16)
    mapping = {index: index for index in range(5000)}

    context = _fingerprint_context(mapping, budget)

    assert context.truncated is True
    assert context.nodes <= budget.max_nodes


def test_largest_fixture_costs_less_than_the_declared_time_bound() -> None:
    """SC-007: measure, do not assume. Prints the number the spec asks for.

    A fingerprint slower than the cell it follows is one the first person to
    notice would switch off, so this is the criterion the design is actually
    accountable to.
    """
    fixtures: dict[str, Any] = {
        "array_64mb": np.arange(8_000_000, dtype=np.float64),
        "array_non_contiguous": np.arange(4_000_000, dtype=np.float64)[::2],
        "frame_500k_x_8": pd.DataFrame(np.random.default_rng(0).random((500_000, 8))),
        "frame_mixed_dtypes": pd.DataFrame(
            {
                "i": np.arange(200_000),
                "f": np.random.default_rng(1).random(200_000),
                "s": [f"row-{index}" for index in range(200_000)],
                "c": pd.Categorical(["a", "b"] * 100_000),
                "t": pd.to_datetime(np.arange(200_000), unit="s"),
            }
        ),
        "list_200k": list(range(200_000)),
        "dict_200k": {index: index for index in range(200_000)},
        "set_200k": set(range(200_000)),
        "str_16mb": "x" * 16_000_000,
        "nested_containers": [{"k": [index, (index, index)]} for index in range(2000)],
    }

    measured: dict[str, float] = {}
    for name, value in fixtures.items():
        fingerprint(value)  # warm any lazy import out of the measurement
        start = time.perf_counter()
        fingerprint(value)
        measured[name] = time.perf_counter() - start

    report = "\n".join(f"  {name:24s} {seconds * 1000:8.3f} ms" for name, seconds in measured.items())
    print(f"\nfingerprint cost, bound {FINGERPRINT_BUDGET.max_seconds * 1000:.0f} ms:\n{report}")

    worst_name = max(measured, key=lambda name: measured[name])
    assert measured[worst_name] < FINGERPRINT_BUDGET.max_seconds, (
        f"{worst_name} took {measured[worst_name] * 1000:.1f} ms, "
        f"bound is {FINGERPRINT_BUDGET.max_seconds * 1000:.0f} ms"
    )

    for name, value in fixtures.items():
        assert _fingerprint_context(value).hashed_bytes <= FINGERPRINT_BUDGET.max_total_bytes, name


def test_cost_does_not_grow_with_content_above_the_bound() -> None:
    """Sampling is the point: an array a hundred times larger costs about the same."""
    small = np.zeros(FINGERPRINT_BUDGET.whole_content_bytes // 8 * 2, dtype=np.float64)
    large = np.zeros(small.size * 100, dtype=np.float64)

    assert _fingerprint_context(large).hashed_bytes <= _fingerprint_context(small).hashed_bytes * 2


# ---------------------------------------------------------------------------
# pandas dtypes that would otherwise produce a false observation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "column"),
    [
        ("tz_aware", pd.to_datetime(["2026-01-01", "2026-01-02"]).tz_localize("UTC")),
        ("naive_datetime", pd.to_datetime(["2026-01-01", "2026-01-02"])),
        ("categorical", pd.Categorical(["a", "b"])),
        ("nullable_int", pd.array([1, None], dtype="Int64")),
        ("string", ["x", "y"]),
        ("float", [1.0, 2.0]),
        ("object", [{"k": 1}, [2]]),
    ],
)
def test_column_dtypes_do_not_report_a_false_change(name: str, column: Any) -> None:
    """An untouched column must fingerprint identically twice.

    Converting an extension dtype to numpy can build a fresh Python object per
    row — a new ``Timestamp`` for every call on a timezone-aware column — whose
    identity differs every time. A fingerprint that fell for that would report
    the frame as changed on every single run.
    """
    frame = pd.DataFrame({name: column})

    assert fingerprint(frame) == fingerprint(frame)
    assert fingerprint(frame) == fingerprint(frame.copy())


def test_mutation_inside_an_object_column_is_detected() -> None:
    """The nested value is the content; the column only points at it."""
    inner = [1, 2]
    frame = pd.DataFrame({"payload": [inner, {"k": 1}]})
    before = fingerprint(frame)

    inner.append(3)

    assert fingerprint(frame) != before


def test_index_and_columns_are_part_of_a_frame_value() -> None:
    """Renaming a column or reindexing is a change the graph must see."""
    frame = pd.DataFrame({"a": [1, 2]}, index=["x", "y"])

    assert fingerprint(frame) != fingerprint(frame.rename(columns={"a": "b"}))
    assert fingerprint(frame) != fingerprint(frame.rename(index={"x": "z"}))
    assert fingerprint(frame) != fingerprint(pd.DataFrame({"a": [1, 2]}))


def test_multiindex_is_inspected_by_codes_and_levels() -> None:
    """The cheap route must still separate two different indexes."""
    left = pd.DataFrame({"v": [1, 2]}, index=pd.MultiIndex.from_tuples([("a", 1), ("b", 2)]))
    right = pd.DataFrame({"v": [1, 2]}, index=pd.MultiIndex.from_tuples([("a", 1), ("b", 3)]))

    assert fingerprint(left) == fingerprint(left.copy())
    assert fingerprint(left) != fingerprint(right)


def test_bare_index_and_series_name_are_values_too() -> None:
    """The index is fingerprintable on its own, and a series carries its name."""
    assert fingerprint(pd.Index([1, 2, 3])) != fingerprint(pd.Index([1, 2, 4]))
    assert fingerprint(pd.Series([1], name="a")) != fingerprint(pd.Series([1], name="b"))


def test_empty_pandas_values_are_stable() -> None:
    """Empty is a value, not an edge case that raises."""
    assert fingerprint(pd.DataFrame()) == fingerprint(pd.DataFrame())
    assert fingerprint(pd.Series(dtype="float64")) == fingerprint(pd.Series(dtype="float64"))
    assert fingerprint(pd.DataFrame()) != fingerprint(pd.DataFrame({"a": []}))


# ---------------------------------------------------------------------------
# FR-004 purity, FR-035 import discipline, ADR-052 stability markers.
# ---------------------------------------------------------------------------


def test_fingerprinting_does_not_change_the_value() -> None:
    """FR-004: observation reads; it does not write."""
    values = [1, [2], {"k": 3}]
    frame = pd.DataFrame({"a": [1.0, 2.0]})
    array = np.arange(4)

    before_repr = repr(values)
    for value in (values, frame, array):
        fingerprint(value)

    assert repr(values) == before_repr
    assert frame.equals(pd.DataFrame({"a": [1.0, 2.0]}))
    assert np.array_equal(array, np.arange(4))


def _module_level_imports() -> list[str]:
    """Return the modules ``fingerprint.py`` imports at module scope."""
    tree = ast.parse(Path(fingerprint_module.__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_fr035_module_scope_imports_are_stdlib_and_stability_only() -> None:
    """FR-035: nothing from SciStudio beyond the stability markers, nothing heavy."""
    imports = _module_level_imports()

    scistudio_imports = [name for name in imports if name.split(".")[0] == "scistudio"]
    assert scistudio_imports == ["scistudio.stability"]

    for forbidden in ("numpy", "pandas", "xxhash"):
        assert not any(name.split(".")[0] == forbidden for name in imports), (
            f"{forbidden} must be imported lazily inside the fingerprint (FR-035)"
        )

    for name in imports:
        root = name.split(".")[0]
        assert root == "scistudio" or root in sys.stdlib_module_names, name


def test_fr035_numpy_and_pandas_are_imported_inside_functions() -> None:
    """Lazy means lazy: the import statements live in function bodies."""
    tree = ast.parse(Path(fingerprint_module.__file__).read_text(encoding="utf-8"))
    lazy: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Import):
                    lazy.update(alias.name.split(".")[0] for alias in inner.names)

    assert {"numpy", "pandas", "xxhash"} <= lazy


def test_fingerprint_of_a_plain_value_needs_no_third_party_import() -> None:
    """A namespace that never imported pandas must not pay for pandas.

    Run in a subprocess because this process has already imported both.
    """
    script = (
        "import sys\n"
        "from scistudio.explore.fingerprint import fingerprint\n"
        "fingerprint([1, 2, 3]); fingerprint({'a': 'b'}); fingerprint(7)\n"
        "assert 'pandas' not in sys.modules, 'pandas was imported'\n"
        "assert 'numpy' not in sys.modules, 'numpy was imported'\n"
        "print('ok')\n"
    )
    src_root = Path(fingerprint_module.__file__).parents[2]
    environment = {**os.environ, "PYTHONPATH": str(src_root)}
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_public_symbols_carry_stability_markers() -> None:
    """ADR-052 §5: tier and Since on every public symbol this module adds."""
    for symbol in (fingerprint, Fingerprint, FingerprintBudget, ObservedChange, compare_namespaces):
        info = get_stability(symbol)
        assert info is not None, symbol
        assert info.tier == "provisional"
        assert info.since == "0.3.4"

    assert set(fingerprint_module.__all__) == {
        "FINGERPRINT_BUDGET",
        "Fingerprint",
        "FingerprintBudget",
        "ObservedChange",
        "compare_namespaces",
        "fingerprint",
    }


def test_fingerprint_value_type_shape() -> None:
    """The value the comparison of FR-026 will consume."""
    result = fingerprint([1])

    assert isinstance(result, Fingerprint)
    assert isinstance(result.digest, str) and result.digest
    assert result.observable is True
    assert result.type_name == "list"

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.digest = "other"  # type: ignore[misc]

    assert Fingerprint("d", True, "list") == Fingerprint("d", True, "list")
    assert Fingerprint("d", True, "list") != Fingerprint("d", False, "list")
    assert Fingerprint("d", True, "list") != Fingerprint("d", True, "tuple")


# ---------------------------------------------------------------------------
# The paths a namespace reaches less often, and the ones that must not crash.
# ---------------------------------------------------------------------------


def test_content_far_above_the_bound_is_sampled_for_bytes_and_integers() -> None:
    """Bytes and integers get the same whole-or-sampled treatment as arrays."""
    payload = bytearray(2 * FINGERPRINT_BUDGET.whole_content_bytes)
    context = _fingerprint_context(payload)
    assert context.hashed_bytes < len(payload)

    before = fingerprint(payload)
    payload[-1] = 7
    assert fingerprint(payload) != before, "a change at the end was missed"

    huge = 1 << (FINGERPRINT_BUDGET.whole_content_bytes * 8 + 8)
    assert _fingerprint_context(huge).hashed_bytes < FINGERPRINT_BUDGET.whole_content_bytes
    assert fingerprint(huge) != fingerprint(huge * 2)


def test_numpy_scalars_carry_their_dtype() -> None:
    """A 0-d numpy value is content, not an unknown type."""
    assert fingerprint(np.float32(1.0)).observable is True
    assert fingerprint(np.float32(1.0)) == fingerprint(np.float32(1.0))
    assert fingerprint(np.float32(1.0)) != fingerprint(np.float32(2.0))
    assert fingerprint(np.float32(1.0)) != fingerprint(np.float64(1.0))


def test_pandas_null_scalars_are_content_not_a_fallback() -> None:
    """``pd.NA`` and ``pd.NaT`` are permanent singletons and the values a column holds."""
    assert fingerprint(pd.NA).observable is True
    assert fingerprint(pd.NA) == fingerprint(pd.NA)
    assert fingerprint(pd.NA) != fingerprint(pd.NaT)
    assert fingerprint(pd.NA) != fingerprint(None)


def test_subclasses_of_the_known_types_are_still_inspected() -> None:
    """A ``memoryview``, an ``OrderedDict``, and a namedtuple are not unknown types."""
    import collections

    assert fingerprint(memoryview(b"ab")).observable is True
    assert fingerprint(memoryview(b"ab")) != fingerprint(memoryview(b"ac"))

    ordered = collections.OrderedDict([("a", 1)])
    assert fingerprint(ordered).observable is True
    assert fingerprint(ordered) != fingerprint(collections.OrderedDict([("a", 2)]))
    assert fingerprint(ordered) != fingerprint({"a": 1}), "a dict subclass is its own type"

    point = collections.namedtuple("point", "x y")
    assert fingerprint(point(1, 2)).observable is True
    assert fingerprint(point(1, 2)) != fingerprint((1, 2))


def test_cycles_through_a_dict_a_frame_and_an_object_array_terminate() -> None:
    """Every container the fingerprint descends into guards the same way."""
    mapping: dict[str, Any] = {"k": 1}
    mapping["self"] = mapping
    assert fingerprint(mapping) == fingerprint(mapping)

    array = np.empty(2, dtype=object)
    array[0] = 1
    array[1] = array
    assert fingerprint(array) == fingerprint(array)

    frame = pd.DataFrame({"payload": [None]})
    frame.iat[0, 0] = frame
    assert fingerprint(frame) == fingerprint(frame)


def test_a_spent_budget_stops_every_container_loop() -> None:
    """The ceilings apply to mappings, sets, and frames, not only to lists."""
    tiny = FingerprintBudget(max_total_bytes=256, max_nodes=8, container_items=8)

    for value in (
        {index: index for index in range(500)},
        set(range(500)),
        [np.zeros(1000) for _ in range(50)],
        pd.DataFrame({f"c{index}": [1.0, 2.0] for index in range(50)}),
        np.array([[1] * 50] * 50, dtype=object),
    ):
        context = _fingerprint_context(value, tiny)
        assert context.truncated is True
        assert context.hashed_bytes <= tiny.max_total_bytes
        assert context.nodes <= tiny.max_nodes + 1


def test_a_bare_array_reaching_the_column_path_is_still_inspected() -> None:
    """The defensive branch in the column path: an array is digested, not fumbled.

    ``_digest_values`` only ever hands it a pandas object today. The branch is
    what keeps a future caller from silently degrading a whole column to
    unobservable because ``to_numpy`` was missing.
    """
    context = _fingerprint_context(1)
    fingerprint_module._digest_array_like(np.arange(4), context)

    assert context.observable is True
    assert context.hashed_bytes > 0


def test_a_series_holding_itself_terminates() -> None:
    """The series path guards its own cycle, like every other container."""
    series = pd.Series([None], dtype=object)
    series.iat[0] = series

    assert fingerprint(series) == fingerprint(series)


def test_a_spent_byte_ceiling_stops_the_recursion_at_the_next_node() -> None:
    """Once the ceiling is spent, the next node is recorded rather than read."""
    context = _fingerprint_context(
        pd.Series([1.0, 2.0], name="signal"),
        FingerprintBudget(max_total_bytes=8),
    )

    assert context.truncated is True
    assert context.hashed_bytes <= 8


@pytest.mark.parametrize("library", ["numpy", "pandas"])
def test_the_sys_modules_guard_is_a_complete_test(monkeypatch: pytest.MonkeyPatch, library: str) -> None:
    """FR-035: a value of a library that was never imported cannot exist.

    So the lazy guard costs a dict lookup and never a wrong answer. With the
    library hidden, its values are simply types no rule covers — reported
    unobservable, which is the honest result, and never mistaken for content.
    """
    value = np.arange(3) if library == "numpy" else pd.Series([1])
    assert fingerprint(value).observable is True

    monkeypatch.delitem(sys.modules, library)

    assert fingerprint(value).observable is False


# ---------------------------------------------------------------------------
# FR-026 to FR-030 (T-008): the namespace comparison and the observation record.
#
# The comparison is the half of the observation that decides what a cell
# changed, so it is tested against each of the three ways a name can move
# (differ, appear, disappear), against the two ways it can *not* move, and
# against the unobservable report that tells a person when the answer is a
# guess. The FR-030 union — an observation only ever adds — is enforced by
# ``build_graph`` and tested in ``test_dependency_analysis.py``, where the
# static estimate it unions with lives.
# ---------------------------------------------------------------------------

CELL_HASH = "0" * 64
OTHER_HASH = "1" * 64


def _namespace(**values: Any) -> dict[str, Fingerprint]:
    """Fingerprint a namespace the way the kernel would (A-007)."""
    return {name: fingerprint(value) for name, value in values.items()}


def test_fr026_a_name_whose_fingerprint_differs_is_changed() -> None:
    """FR-026 / US3 scenario 1: the fingerprint moved, so the name is in the changed set."""
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    before = _namespace(df=frame, other=[1, 2])
    frame.loc[1, "x"] = 99.0
    after = _namespace(df=frame, other=[1, 2])

    observed = compare_namespaces(before, after, cell_id="c4", source_hash=CELL_HASH)

    assert observed.changed_names == frozenset({"df"})
    assert observed.cell_id == "c4"
    assert observed.source_hash == CELL_HASH


def test_fr026_a_name_that_appeared_is_changed() -> None:
    """FR-026 / US3 scenario 2: a name bound by the run is in the changed set."""
    observed = compare_namespaces(
        _namespace(df=[1]),
        _namespace(df=[1], peaks=[2, 3]),
        cell_id="c2",
        source_hash=CELL_HASH,
    )

    assert observed.changed_names == frozenset({"peaks"})


def test_fr026_a_name_that_disappeared_is_changed() -> None:
    """FR-026 / US3 scenario 2: ``del df`` is a change, so readers below depend on the cell.

    The spec's edge case says so explicitly: running them then fails with a name
    error, which is the loud failure the model relies on.
    """
    observed = compare_namespaces(
        _namespace(df=[1], keep=[2]),
        _namespace(keep=[2]),
        cell_id="c3",
        source_hash=CELL_HASH,
    )

    assert observed.changed_names == frozenset({"df"})


def test_fr026_an_untouched_namespace_reports_nothing_changed() -> None:
    """The direction that keeps the diagnostic worth reading: no mutation, no report."""
    frame = pd.DataFrame({"x": [1.0, 2.0]})
    values = [1, 2, 3]
    before = _namespace(df=frame, values=values, count=7, label="a")
    after = _namespace(df=frame, values=values, count=7, label="a")

    observed = compare_namespaces(before, after, cell_id="c1", source_hash=CELL_HASH)

    assert observed.changed_names == frozenset()
    assert observed.unobservable_names == frozenset()


def test_fr026_two_empty_namespaces_report_nothing() -> None:
    """A cell that runs against an empty namespace and binds nothing."""
    observed = compare_namespaces({}, {}, cell_id="c1", source_hash=CELL_HASH)

    assert observed.changed_names == frozenset()
    assert observed.unobservable_names == frozenset()


def test_fr026_a_rebinding_to_an_equal_value_is_not_reported() -> None:
    """Content, not identity: ``df = df.copy()`` leaves the value where it was.

    A fingerprint that keyed on ``id()`` for everything would report this as a
    change and, over a notebook, teach the person to ignore the marks. The
    static estimate still names ``df`` for such a cell, so no edge is lost —
    only the false *observation* is.
    """
    before = _namespace(df=pd.DataFrame({"x": [1.0, 2.0]}))
    after = _namespace(df=pd.DataFrame({"x": [1.0, 2.0]}))

    assert compare_namespaces(before, after, cell_id="c1", source_hash=CELL_HASH).changed_names == frozenset()


def test_fr026_a_name_that_changed_type_is_reported_even_at_an_equal_digest() -> None:
    """The type is part of the fingerprint, so a swapped container is a change."""
    before = {"values": Fingerprint(digest="abc", observable=True, type_name="list")}
    after = {"values": Fingerprint(digest="abc", observable=True, type_name="tuple")}

    observed = compare_namespaces(before, after, cell_id="c1", source_hash=CELL_HASH)

    assert observed.changed_names == frozenset({"values"})


def test_fr029_an_unobservable_name_is_reported() -> None:
    """FR-029 / US3 scenario 5: the person is told the observation does not cover it."""

    class Opaque:
        pass

    handle = Opaque()
    before = _namespace(handle=handle, df=[1])
    after = _namespace(handle=handle, df=[1])

    observed = compare_namespaces(before, after, cell_id="c5", source_hash=CELL_HASH)

    assert observed.unobservable_names == frozenset({"handle"})


def test_fr029_an_unobservable_name_is_not_reported_as_changed() -> None:
    """Unobservable is not the same claim as changed.

    Folding the two together would add an edge for every open handle in the
    namespace on every run — a stream of false diagnostics the person would
    learn to ignore, which the spec's risk section calls out by name.
    """

    class Opaque:
        pass

    handle = Opaque()
    observed = compare_namespaces(
        _namespace(handle=handle),
        _namespace(handle=handle),
        cell_id="c1",
        source_hash=CELL_HASH,
    )

    assert observed.changed_names == frozenset()
    assert observed.unobservable_names == frozenset({"handle"})


def test_fr029_an_unobservable_name_that_also_changed_is_in_both_sets() -> None:
    """A name can be changed *and* uncovered; the two reports are independent."""

    class Opaque:
        pass

    observed = compare_namespaces(
        _namespace(handle=Opaque()),
        _namespace(handle=Opaque()),
        cell_id="c1",
        source_hash=CELL_HASH,
    )

    assert observed.unobservable_names == frozenset({"handle"})
    # Two distinct objects, so the identity digests differ and the name reads as
    # changed. It is *not* proof of a change — which is exactly what the
    # unobservable report above says.
    assert observed.changed_names == frozenset({"handle"})


def test_fr029_an_unobservable_name_present_only_before_is_reported() -> None:
    """A name that was uncovered and then vanished is still reported for that run."""

    class Opaque:
        pass

    observed = compare_namespaces(
        _namespace(handle=Opaque()),
        {},
        cell_id="c1",
        source_hash=CELL_HASH,
    )

    assert observed.unobservable_names == frozenset({"handle"})
    assert observed.changed_names == frozenset({"handle"})


def test_fr027_an_observation_knows_which_source_it_describes() -> None:
    """FR-027 / US3 scenario 4: keyed to the hash of the source at the time of the run."""
    observed = compare_namespaces({}, {}, cell_id="c1", source_hash=CELL_HASH)

    assert observed.applies_to(CELL_HASH) is True
    assert observed.applies_to(OTHER_HASH) is False


def test_the_comparison_is_pure_over_its_two_mappings() -> None:
    """FR-004: it reads the two mappings and writes neither."""
    before = _namespace(df=[1, 2])
    after = _namespace(df=[1, 2, 3])
    before_copy = dict(before)
    after_copy = dict(after)

    compare_namespaces(before, after, cell_id="c1", source_hash=CELL_HASH)

    assert before == before_copy
    assert after == after_copy


def test_the_comparison_reports_on_exactly_the_names_it_is_given() -> None:
    """Filtering dunder and kernel-injected names is the caller's, per the docstring."""
    observed = compare_namespaces(
        {"__builtins__": fingerprint([1])},
        {"__builtins__": fingerprint([2])},
        cell_id="c1",
        source_hash=CELL_HASH,
    )

    assert observed.changed_names == frozenset({"__builtins__"})


def test_an_observed_change_normalises_its_name_collections() -> None:
    """A record rebuilt from JSON arrays compares equal to one the comparison made.

    Without the normalisation the round trip of FR-032 would be comparing the
    container type rather than the observation.
    """
    from_lists = ObservedChange(
        cell_id="c1",
        changed_names=["b", "a"],  # type: ignore[arg-type]
        unobservable_names=["h"],  # type: ignore[arg-type]
        source_hash=CELL_HASH,
    )
    from_sets = ObservedChange(
        cell_id="c1",
        changed_names=frozenset({"a", "b"}),
        unobservable_names=frozenset({"h"}),
        source_hash=CELL_HASH,
    )

    assert from_lists == from_sets
    assert isinstance(from_lists.changed_names, frozenset)


def test_an_observed_change_is_frozen() -> None:
    """It is a record of a run that happened; nothing may edit it afterwards."""
    observed = compare_namespaces({}, {}, cell_id="c1", source_hash=CELL_HASH)

    with pytest.raises(dataclasses.FrozenInstanceError):
        observed.cell_id = "c2"  # type: ignore[misc]


def test_the_comparison_scales_to_a_namespace_of_names() -> None:
    """SC-007's shape at the comparison level: the join is linear in the names.

    The fingerprints themselves carry the cost bound; the comparison must not
    add one of its own on top of it.
    """
    before = {f"name{index}": fingerprint(index) for index in range(5000)}
    after = {f"name{index}": fingerprint(index + 1) for index in range(5000)}

    start = time.perf_counter()
    observed = compare_namespaces(before, after, cell_id="c1", source_hash=CELL_HASH)
    elapsed = time.perf_counter() - start

    assert len(observed.changed_names) == 5000
    assert elapsed < FINGERPRINT_BUDGET.max_seconds, f"comparison took {elapsed:.3f}s"
