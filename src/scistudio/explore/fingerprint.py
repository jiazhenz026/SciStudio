"""Runtime observation for the notebook dependency analysis (ADR-054 §6.2).

What a cell *changes* is observed, never guessed: the kernel fingerprints every
top-level name in the module namespace before and after a cell runs, and the
comparison of the two snapshots is the cell's observed changed set
(FR-024..FR-030 of ``docs/specs/adr-054-notebook-dependency-analysis.md``).

The fingerprint is pure over the object it is given (FR-004): it inspects
content for the container and array types it knows and falls back to identity
for everything else, reporting the name as unobservable rather than guessing —
a fingerprint derived from ``repr`` would produce false observations for any
object with a stateful or random representation.

Cost is bounded by two declared constants below
(:data:`FINGERPRINT_SIZE_BOUND` and :data:`FINGERPRINT_SAMPLE_SIZE`). Below the
bound the whole content is hashed; above it a strided sample across the full
extent is hashed together with shape, dtype, and length (FR-025). A sampled
fingerprint can miss a change outside the sampled positions; the union
semantics of FR-002 mean such a miss can at worst leave the graph where the
static estimate put it.

This module imports the standard library only at module level, plus the
SciStudio stability markers; numpy and pandas are imported lazily inside the
fingerprint, only when an object's type actually comes from them (FR-035).
"""

from __future__ import annotations

import hashlib
import math
import numbers
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from scistudio.stability import provisional

__all__ = [
    "FINGERPRINT_NAMESPACE_TIME_BUDGET_SECONDS",
    "FINGERPRINT_SAMPLE_SIZE",
    "FINGERPRINT_SIZE_BOUND",
    "Fingerprint",
    "ObservedChange",
    "compare_namespaces",
    "fingerprint",
    "fingerprint_namespace",
    "unpredicted_changes",
]

#: Content-element count at or below which a value is hashed whole. Above it a
#: strided sample of :data:`FINGERPRINT_SAMPLE_SIZE` positions across the full
#: extent is hashed instead, together with shape, dtype, and length (FR-025).
#: Both constants are declared here, in one place, as FR-025 requires.
FINGERPRINT_SIZE_BOUND: int = 100_000

#: Number of content positions hashed when a value exceeds
#: :data:`FINGERPRINT_SIZE_BOUND`. The sample spans the full extent at a fixed
#: stride, so a change is missed only between sampled positions.
FINGERPRINT_SAMPLE_SIZE: int = 1024

#: Declared wall-clock budget for fingerprinting every top-level name of the
#: largest fixture namespace once (SC-007). Each individual fingerprint is
#: bounded by the constants above; most names are small or fall back to
#: identity, so the per-run total stays in milliseconds.
FINGERPRINT_NAMESPACE_TIME_BUDGET_SECONDS: float = 1.0


@provisional(since="0.3.4")
@dataclass(frozen=True)
class Fingerprint:
    """The value :func:`fingerprint` returns for one object (FR-024).

    ``digest`` is the content (or identity) digest; ``observable`` is ``False``
    when the digest fell back to identity because the type's content cannot be
    inspected; ``type_name`` records the type the fingerprint was computed for.
    Two fingerprints compare equal exactly when the comparison of FR-026 must
    treat the value as unchanged.
    """

    digest: str
    observable: bool
    type_name: str


@provisional(since="0.3.4")
@dataclass(frozen=True)
class ObservedChange:
    """What one cell was seen to change when it ran (FR-026, FR-027).

    ``changed_names`` are the names whose fingerprint differs before and after
    the run, plus names that appeared or disappeared. ``unobservable_names``
    are the names whose fingerprint fell back to identity on either side of the
    run, reported once per cell run (FR-029). ``source_hash`` keys the
    observation to the source the cell held at run time; the graph discards
    the observation when the cell's source hash changes (FR-027).
    """

    cell_id: str
    changed_names: tuple[str, ...]
    unobservable_names: tuple[str, ...]
    source_hash: str


def _digest_parts(tag: str, parts: Iterable[bytes]) -> str:
    """Hash *parts* under *tag*, length-prefixing each part to avoid ambiguity."""
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(tag.encode("utf-8"))
    for part in parts:
        hasher.update(len(part).to_bytes(8, "little"))
        hasher.update(part)
    return hasher.hexdigest()


def _sample_positions(size: int, budget: int) -> range:
    """Whole extent below the bound, else a fixed-stride sample spanning it."""
    if size <= FINGERPRINT_SIZE_BOUND or size <= budget:
        return range(size)
    stride = math.ceil(size / budget)
    return range(0, size, stride)


def _sequence_digest(items: Iterable[Any], tag: str, seen: set[int]) -> tuple[str, bool]:
    parts: list[bytes] = []
    observable = True
    for item in items:
        digest, item_observable = _content_digest(item, seen)
        parts.append(digest.encode("ascii"))
        observable = observable and item_observable
    return _digest_parts(tag, parts), observable


def _numpy_array_digest(arr: Any, seen: set[int]) -> tuple[str, bool]:
    """Content digest of a numpy array, whole or strided-sampled (FR-025)."""
    import numpy as np

    shape = tuple(int(d) for d in arr.shape)
    dtype = str(arr.dtype)
    size = int(arr.size)
    header = [repr(shape).encode(), dtype.encode(), str(size).encode()]
    if arr.dtype == object:
        flat = arr.reshape(-1)
        positions = _sample_positions(size, FINGERPRINT_SAMPLE_SIZE)
        return _sequence_digest((flat[p] for p in positions), "ndarray-object", seen)
    contiguous = np.ascontiguousarray(arr).reshape(-1)
    positions = _sample_positions(size, FINGERPRINT_SAMPLE_SIZE)
    data = contiguous if positions.step == 1 and positions.stop == size else contiguous[positions]
    return _digest_parts("ndarray", [*header, data.tobytes()]), True


def _indexed_values_digest(values: Any, positions: range, seen: set[int]) -> tuple[str, bool]:
    """Digest a 1-D array-like at *positions* (already bounded by the caller)."""
    import numpy as np

    arr = np.asarray(values)
    header = [str(arr.dtype).encode(), str(int(arr.shape[0])).encode()]
    if arr.dtype == object:
        digest, observable = _sequence_digest((arr[p] for p in positions), "object-values", seen)
        return digest, observable
    selected = arr[list(positions)] if positions.step != 1 or positions.stop != arr.shape[0] else arr
    return _digest_parts("values", [*header, np.ascontiguousarray(selected).tobytes()]), True


def _pandas_series_digest(series: Any, seen: set[int]) -> tuple[str, bool]:
    """Content digest of a pandas Series: name, dtype, index, values."""
    size = int(series.shape[0])
    positions = _sample_positions(size, FINGERPRINT_SAMPLE_SIZE)
    index_digest, index_observable = _indexed_values_digest(series.index.to_numpy(), positions, seen)
    values_digest, values_observable = _indexed_values_digest(series.to_numpy(), positions, seen)
    digest = _digest_parts(
        "series",
        [
            repr(series.name).encode(),
            str(series.dtype).encode(),
            str(size).encode(),
            index_digest.encode(),
            values_digest.encode(),
        ],
    )
    return digest, index_observable and values_observable


def _pandas_frame_digest(frame: Any, seen: set[int]) -> tuple[str, bool]:
    """Content digest of a pandas DataFrame: columns, index, and per-column values."""
    rows, cols = (int(d) for d in frame.shape)
    total = rows * cols
    if total <= FINGERPRINT_SIZE_BOUND or rows == 0 or cols == 0:
        positions = range(rows)
    else:
        row_budget = max(1, FINGERPRINT_SAMPLE_SIZE // cols)
        stride = math.ceil(rows / row_budget)
        positions = range(0, rows, stride)
    index_digest, observable = _indexed_values_digest(frame.index.to_numpy(), positions, seen)
    column_digests: list[bytes] = []
    for column in frame.columns:
        column_digest, column_observable = _indexed_values_digest(frame[column].to_numpy(), positions, seen)
        column_digests.append(str(column).encode())
        column_digests.append(str(frame[column].dtype).encode())
        column_digests.append(column_digest.encode())
        observable = observable and column_observable
    digest = _digest_parts(
        "frame",
        [repr((rows, cols)).encode(), index_digest.encode(), *column_digests],
    )
    return digest, observable


def _content_digest(obj: Any, seen: set[int]) -> tuple[str, bool]:
    """Return ``(digest, observable)`` for *obj*.

    Content is inspected for the types FR-024 names; anything else falls back
    to identity (``observable=False``). *seen* breaks reference cycles in
    containers. A container is observable only when every inspected element is
    observable, so a partially inspectable value is reported rather than
    silently under-observed.
    """
    if obj is None:
        return _digest_parts("none", []), True
    if isinstance(obj, bool):
        return _digest_parts("bool", [repr(obj).encode()]), True
    if isinstance(obj, numbers.Number):
        return _digest_parts("number", [type(obj).__qualname__.encode(), repr(obj).encode()]), True
    if isinstance(obj, str):
        return _digest_parts("str", [obj.encode("utf-8", "surrogatepass")]), True
    if isinstance(obj, (bytes, bytearray)):
        return _digest_parts("bytes", [bytes(obj)]), True
    if isinstance(obj, (list, tuple)):
        if id(obj) in seen:
            return _digest_parts("cycle", [type(obj).__qualname__.encode()]), True
        seen.add(id(obj))
        try:
            size = len(obj)
            positions = _sample_positions(size, FINGERPRINT_SAMPLE_SIZE)
            return _sequence_digest((obj[p] for p in positions), type(obj).__qualname__, seen)
        finally:
            seen.discard(id(obj))
    if isinstance(obj, dict):
        if id(obj) in seen:
            return _digest_parts("cycle", [b"dict"]), True
        seen.add(id(obj))
        try:
            pair_digests: list[str] = []
            observable = True
            for key, value in obj.items():
                key_digest, key_observable = _content_digest(key, seen)
                value_digest, value_observable = _content_digest(value, seen)
                pair_digests.append(f"{key_digest}:{value_digest}")
                observable = observable and key_observable and value_observable
            pair_digests.sort()
            return _digest_parts("dict", [p.encode("ascii") for p in pair_digests]), observable
        finally:
            seen.discard(id(obj))
    if isinstance(obj, (set, frozenset)):
        element_digests: list[str] = []
        observable = True
        for element in obj:
            element_digest, element_observable = _content_digest(element, seen)
            element_digests.append(element_digest)
            observable = observable and element_observable
        element_digests.sort()
        return _digest_parts(type(obj).__qualname__, [d.encode("ascii") for d in element_digests]), observable
    top_module = type(obj).__module__.partition(".")[0]
    if top_module == "numpy":
        import numpy as np

        if isinstance(obj, np.ndarray):
            return _numpy_array_digest(obj, seen)
    elif top_module == "pandas":
        import pandas as pd

        if isinstance(obj, pd.DataFrame):
            return _pandas_frame_digest(obj, seen)
        if isinstance(obj, pd.Series):
            return _pandas_series_digest(obj, seen)
    return f"id:{id(obj)}", False


@provisional(since="0.3.4")
def fingerprint(obj: object) -> Fingerprint:
    """Map *obj* to a :class:`Fingerprint` (FR-024).

    Equal for an unchanged object; different, within the bound of
    :data:`FINGERPRINT_SIZE_BOUND`, for an object mutated in place. Pure over
    the object it is given (FR-004): it executes no code, touches nothing
    outside the object graph, and never raises on an unknown type — unknown
    types fall back to identity with ``observable=False``.
    """
    digest, observable = _content_digest(obj, set())
    return Fingerprint(digest=digest, observable=observable, type_name=type(obj).__qualname__)


@provisional(since="0.3.4")
def fingerprint_namespace(namespace: Mapping[str, object]) -> dict[str, Fingerprint]:
    """Fingerprint every top-level name in a module namespace (A-007).

    The kernel calls this before and after each cell run and hands both
    snapshots to :func:`compare_namespaces`.
    """
    return {name: fingerprint(value) for name, value in namespace.items()}


@provisional(since="0.3.4")
def compare_namespaces(
    cell_id: str,
    source_hash: str,
    before: Mapping[str, Fingerprint],
    after: Mapping[str, Fingerprint],
) -> ObservedChange:
    """Report what one cell changed, from the namespace fingerprints around its run (FR-026).

    The observed changed set is the names whose fingerprint differs, plus the
    names that appeared or disappeared. Names whose fingerprint fell back to
    identity on either side are reported once in ``unobservable_names``
    (FR-029). The observation is keyed to *source_hash*, the hash of the
    cell's source at the time of the run (FR-027).
    """
    changed = sorted(
        name
        for name in before.keys() | after.keys()
        if before.get(name) is None or after.get(name) is None or before[name] != after[name]
    )
    unobservable = sorted(
        {name for name, fp in before.items() if not fp.observable}
        | {name for name, fp in after.items() if not fp.observable}
    )
    return ObservedChange(
        cell_id=cell_id,
        changed_names=tuple(changed),
        unobservable_names=tuple(unobservable),
        source_hash=source_hash,
    )


@provisional(since="0.3.4")
def unpredicted_changes(change: ObservedChange, assigned_names: Iterable[str]) -> tuple[str, ...]:
    """Names a cell was observed to change that its static estimate does not include (FR-028).

    Each returned name is one the cell changed without an assignment showing
    it — the in-place mutations and helper-side effects the observation exists
    to catch. The caller turns each into a diagnostic carrying
    :attr:`AnalysisFlag.UNPREDICTED_CHANGE`.
    """
    assigned = set(assigned_names)
    return tuple(name for name in change.changed_names if name not in assigned)
