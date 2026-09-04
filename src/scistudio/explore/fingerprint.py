"""Bounded content fingerprints and the namespace comparison (ADR-054, FR-024 to FR-030).

What a notebook cell *changes* cannot be read off its source: a cell that calls
``df.dropna(inplace=True)`` or ``values.append(x)`` rebinds nothing, and no list
of "mutating methods" stays right for long. ADR-054 answers that by *observing*
instead of guessing — the session fingerprints every top-level name before a cell
runs and again after, and the names whose fingerprint moved are the names the
cell changed.

This module is the whole of that answer as spec §4.2 assigns it: the fingerprint
(FR-024, FR-025), the comparison over a whole namespace (FR-026), and the
:class:`ObservedChange` record keyed to the cell's source hash (FR-027, FR-029,
FR-030). What the kernel does *around* a cell run — taking the two namespace
snapshots and calling :func:`compare_namespaces` — is the explore-session spec's
(A-007). Joining an observation to the graph, the unpredicted-change diagnostic
of FR-028, and the metadata codec of FR-031 to FR-034 belong to
:mod:`scistudio.explore.dependency_analysis`, which is where the static estimate
an observation is compared against lives.

The contract:

* :func:`fingerprint` is **pure** (FR-004). It reads the object it is given and
  nothing else — no filesystem, no execution, no global state, no caching.
* It inspects *content* for numpy arrays, pandas frames, series and indexes,
  lists, tuples, dicts, sets, strings, bytes, and numbers, so that an in-place
  mutation of any of them moves the digest (FR-024, SC-006).
* Every other type falls back to **identity** and the result is marked
  ``observable=False`` (FR-024, FR-029). A fingerprint never guesses from
  ``repr``: an object with a random or stateful representation would then look
  changed on every run, and a false observation is noise a person learns to
  ignore, which costs more than an honest "I cannot see this one".
* Its cost is bounded by :data:`FINGERPRINT_BUDGET` (FR-025). Content at or
  below the budget's whole-content limit is hashed entire; above it, the content
  is sampled at fixed strides *across its full extent* — first element to last —
  together with its shape, dtype, and length, so a large object is still cheap
  and a change at either end is still visible.

Why not :func:`scistudio.utils.hashing.content_hash`: it hashes arrays whole
with no bound, and falls back to ``repr`` for everything it does not know. Both
are exactly what this use cannot have (spec §4.1).

Import discipline (FR-035, SC-011): at module scope this file imports the
standard library and :mod:`scistudio.stability` only. numpy, pandas, and the
``xxhash`` digest that spec §4.1 names are imported lazily, inside the
fingerprint, and numpy/pandas only when they are already loaded — an object
cannot be a ``DataFrame`` if pandas was never imported, so the check is a
``sys.modules`` lookup rather than an import cost paid by every caller.

Two honest limits, stated here rather than discovered later:

* Above the budget the fingerprint is a *sample*. A change confined to bytes the
  stride skipped is not seen. The budget is chosen so that a fingerprint costs
  far less than the cell it follows; a fingerprint slower than the code it
  watches is one the first person to notice would switch off.
* The identity fallback uses :func:`id`, and CPython reuses addresses. Two
  distinct short-lived objects can therefore collide. That is why the fallback
  reports ``observable=False`` instead of pretending: FR-029 requires the name
  to be surfaced as unobservable for that run, so nobody reads the comparison as
  proof the object did not change.
"""

from __future__ import annotations

import struct
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import islice
from typing import Any

from scistudio.stability import provisional

__all__ = [
    "FINGERPRINT_BUDGET",
    "Fingerprint",
    "FingerprintBudget",
    "ObservedChange",
    "compare_namespaces",
    "fingerprint",
]


@provisional(since="0.3.4")
@dataclass(frozen=True)
class FingerprintBudget:
    """The declared cost bound of :func:`fingerprint` (FR-025).

    FR-025 requires the cost constant and the sample size to be declared in one
    place. This is that place: :data:`FINGERPRINT_BUDGET` is the only instance,
    every limit below is read from it, and no other constant in the module
    bounds anything.

    A single call to :func:`fingerprint` feeds at most :attr:`max_total_bytes`
    to the hash, visits at most :attr:`max_nodes` objects, descends at most
    :attr:`max_depth` levels, and walks at most :attr:`max_scan_items` entries of
    any one mapping or set. Everything else follows from those four.
    """

    whole_content_bytes: int = 1 << 20
    """Content this size or smaller is hashed entire (1 MiB)."""

    sample_bytes: int = 1 << 16
    """Bytes taken from content larger than :attr:`whole_content_bytes` (64 KiB).

    The sample is strided across the full extent, not a prefix, so a change at
    the end of a large array is as visible as one at the start.
    """

    container_items: int = 512
    """Elements sampled from a sequence, mapping, or set larger than this.

    Containers are bounded by element count rather than bytes: the cost of a
    list is the cost of fingerprinting its elements, which no byte count of the
    list object itself predicts.
    """

    max_scan_items: int = 1 << 20
    """Entries of one mapping or set the fingerprint will iterate over (1 Mi).

    Dicts and sets are not indexable, so a strided sample still has to *walk*
    the entries it skips. Beyond this length the walk itself is the cost, and
    the fingerprint takes a prefix of :attr:`container_items` entries instead,
    recording that it did so.
    """

    max_nodes: int = 4096
    """Objects visited by one call, across the whole recursion."""

    max_total_bytes: int = 4 << 20
    """Bytes fed to the hash by one call (4 MiB). The hard cost ceiling."""

    max_depth: int = 16
    """Levels of nesting descended before the rest is recorded as truncated."""

    max_seconds: float = 0.25
    """Wall-clock bound for one call (SC-007).

    The measured worst case over the fixtures in
    ``tests/explore/test_fingerprint.py`` is 10.4 ms — a one-million-entry dict,
    whose entries have to be *walked* even where they are not hashed, because a
    mapping cannot be indexed. An 800 MB array costs 0.03 ms and a
    one-million-row twenty-column frame 0.9 ms. The bound is set roughly
    twenty-four times above the measurement so that a loaded shared runner does
    not turn a timing test into a flake; it is not licence for a slower
    algorithm, and a change that approaches it should be read as a regression.
    The bound for a whole namespace of *n* names is *n* times this constant.
    """


#: The one declared budget (FR-025). Read it; do not shadow it with locals.
FINGERPRINT_BUDGET = FingerprintBudget()


@provisional(since="0.3.4")
@dataclass(frozen=True)
class Fingerprint:
    """What one object looked like at one moment (spec §3 Key Entities).

    Two fingerprints of the same unchanged object are equal; a fingerprint taken
    after an in-place mutation differs, within the bound of
    :data:`FINGERPRINT_BUDGET`. The comparison function of FR-026 compares these
    pairwise and reports the names whose value moved.

    ``observable`` is the part a person needs to read. ``False`` means the
    fingerprint fell back to identity because no content rule covered the type,
    so equality proves only that the name still points at the same object — not
    that the object is unchanged. FR-029 requires such names to be reported once
    per cell run.
    """

    digest: str
    """Hexadecimal digest of the content that was inspected."""

    observable: bool
    """``False`` when the value fell back to identity (FR-029)."""

    type_name: str
    """Qualified name of the type the digest was computed for."""


# ---------------------------------------------------------------------------
# Lazy third-party access (FR-035)
# ---------------------------------------------------------------------------


def _numpy() -> Any:
    """Return numpy if the caller's process already imported it, else ``None`` (FR-035).

    An object cannot be a ``numpy.ndarray`` unless numpy has been imported, so
    the ``sys.modules`` guard is a complete test and costs a dict lookup.
    Importing numpy here to find out would make every fingerprint of a plain
    ``int`` pay for it, and would pull a heavy dependency into a namespace that
    had chosen not to have one. The import statement itself stays inside the
    function, per FR-035.
    """
    if "numpy" not in sys.modules:
        return None
    # Lazy, inside the fingerprint (FR-035).
    import numpy

    return numpy


def _pandas() -> Any:
    """Return pandas if the caller's process already imported it (FR-035).

    Same guard and the same reason as :func:`_numpy`.
    """
    if "pandas" not in sys.modules:
        return None
    # Lazy, inside the fingerprint (FR-035).
    import pandas

    return pandas


def _new_hasher() -> Any:
    """Return a fresh xxh3-64 hasher (spec §4.1).

    ``xxhash`` is a dependency SciStudio already carries and is the digest §4.1
    names for this module. It is imported lazily for the same reason numpy and
    pandas are: nothing at import time of this module needs it.
    """
    # Lazy, inside the fingerprint, for the same reason numpy and pandas are.
    import xxhash

    return xxhash.xxh3_64()


# ---------------------------------------------------------------------------
# Recursion state
# ---------------------------------------------------------------------------


@dataclass
class _Context:
    """Mutable state of one :func:`fingerprint` call.

    Kept in one object so every limit in :data:`FINGERPRINT_BUDGET` is enforced
    against the *whole* call rather than per node: a list of a thousand large
    arrays must cost no more than the ceiling, not a thousand times it.
    """

    hasher: Any
    budget: FingerprintBudget
    observable: bool = True
    truncated: bool = False
    hashed_bytes: int = 0
    nodes: int = 0
    depth: int = 0
    path: set[int] = field(default_factory=set)


def _feed(ctx: _Context, data: bytes) -> None:
    """Feed *data* to the hash, stopping at the budget's byte ceiling."""
    remaining = ctx.budget.max_total_bytes - ctx.hashed_bytes
    if remaining <= 0:
        ctx.truncated = True
        return
    if len(data) > remaining:
        data = data[:remaining]
        ctx.truncated = True
    ctx.hasher.update(data)
    ctx.hashed_bytes += len(data)


def _remaining(ctx: _Context) -> int:
    """Bytes this call may still feed to the hash."""
    return max(0, ctx.budget.max_total_bytes - ctx.hashed_bytes)


def _whole_limit(ctx: _Context) -> int:
    """Largest content this call may still hash *entire*.

    The whole-content route materialises a copy — ``tobytes()``, ``encode()`` —
    before :func:`_feed` sees it, so a call that has nearly spent its byte
    ceiling must take the sampled route even for content the standing limit
    would have allowed. Without this, a list of five hundred one-megabyte arrays
    copies five hundred megabytes to hash four.
    """
    return min(ctx.budget.whole_content_bytes, _remaining(ctx))


def _exhausted(ctx: _Context) -> bool:
    """Return ``True`` once no further node can contribute anything.

    Container loops test this and break. Without it a value with a quarter of a
    million nodes would still be *walked* a quarter of a million times after the
    budget was spent, each walk doing nothing — bounded work in the hash, but
    not bounded work, which is not what FR-025 promises.
    """
    return ctx.nodes >= ctx.budget.max_nodes or _remaining(ctx) <= 0


def _tag(ctx: _Context, text: str) -> None:
    """Feed a structural marker, so unlike shapes cannot collide.

    ``[1, 2]`` and ``(1, 2)`` and ``{1: 2}`` must not share a digest, and nor
    must ``[[1], [2]]`` and ``[1, 2]``; every node writes its type and its
    length before its content, which is what keeps them apart.
    """
    _feed(ctx, text.encode("utf-8"))
    _feed(ctx, b"\x1e")


def _type_name(obj: object) -> str:
    """Return the qualified type name recorded on the :class:`Fingerprint`."""
    cls = type(obj)
    module = getattr(cls, "__module__", "")
    name = getattr(cls, "__qualname__", cls.__name__)
    return name if module in ("builtins", "") else f"{module}.{name}"


def _stride_indices(length: int, keep: int) -> list[int]:
    """Return up to *keep* + 1 indices spanning ``0 .. length - 1``.

    Fixed stride, and the last index is always included, so FR-025's "across its
    full extent" holds literally: a change to the final element of a sampled
    container is always seen.
    """
    if length <= 0:
        return []
    if length <= keep:
        return list(range(length))
    step = max(1, length // keep)
    indices = list(range(0, length, step))[:keep]
    if indices[-1] != length - 1:
        indices.append(length - 1)
    return indices


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_EXACT_SCALARS = frozenset({type(None), bool, int, float, complex, str, bytes, bytearray})
_EXACT_CONTAINERS = frozenset({list, tuple, dict, set, frozenset})


def _digest(obj: object, ctx: _Context) -> None:
    """Fold *obj* into ``ctx.hasher``, honouring every limit in the budget."""
    ctx.nodes += 1
    if ctx.nodes > ctx.budget.max_nodes or ctx.depth > ctx.budget.max_depth:
        ctx.truncated = True
        _tag(ctx, "truncated")
        return
    if _remaining(ctx) <= 0:
        # The byte ceiling is spent. Descending further would read and copy
        # content that could not be hashed anyway, which is the cost FR-025
        # exists to bound.
        ctx.truncated = True
        return

    kind = type(obj)
    try:
        if kind in _EXACT_SCALARS:
            _digest_scalar(obj, ctx)
            return
        if kind in _EXACT_CONTAINERS:
            _digest_container(obj, ctx)
            return
        if _digest_numpy(obj, ctx):
            return
        if _digest_pandas(obj, ctx):
            return
        if _digest_scalar(obj, ctx):
            return
        if _digest_container(obj, ctx):
            return
    except Exception:
        # A value's own code can fail: a subclass with a broken ``__len__``, an
        # array backed by a closed memory map, a lazy column that raises on
        # access. The fingerprint is observation, not execution — it must not
        # turn a readable namespace into an exception. Falling through to the
        # identity fallback records the honest result: content could not be
        # inspected, so the name is unobservable for this run (FR-029).
        pass
    _digest_identity(obj, ctx)


def _digest_scalar(obj: object, ctx: _Context) -> bool:
    """Digest an atomic value by content. Return ``True`` when handled."""
    if obj is None:
        _tag(ctx, "none")
        return True
    if obj is True or obj is False:
        _tag(ctx, "bool")
        _feed(ctx, b"\x01" if obj else b"\x00")
        return True
    if isinstance(obj, int):
        _tag(ctx, "int")
        _digest_big_int(int(obj), ctx)
        return True
    if isinstance(obj, float):
        _tag(ctx, "float")
        _feed(ctx, struct.pack("<d", obj))
        return True
    if isinstance(obj, complex):
        _tag(ctx, "complex")
        _feed(ctx, struct.pack("<dd", obj.real, obj.imag))
        return True
    if isinstance(obj, str):
        _digest_text(obj, ctx)
        return True
    if isinstance(obj, (bytes, bytearray, memoryview)):
        _digest_bytes(obj, ctx)
        return True
    return False


def _digest_big_int(value: int, ctx: _Context) -> None:
    """Digest an ``int`` by its two's-complement bytes, bounded like any content.

    Python integers are unbounded, so a factorial held in a notebook is content
    like any other and gets the same whole-or-sampled treatment.
    """
    width = value.bit_length() // 8 + 1
    _feed(ctx, str(width).encode("ascii"))
    if width <= _whole_limit(ctx):
        _feed(ctx, value.to_bytes(width, "little", signed=True))
        return
    raw = value.to_bytes(width, "little", signed=True)
    _digest_sampled_bytes(raw, ctx)


def _digest_text(obj: str, ctx: _Context) -> None:
    """Digest a string by its characters, sampling a long one by stride.

    The stride is applied to the *string* before encoding, so a 500 MB string is
    never materialised as 500 MB of UTF-8 to hash 64 KiB of it.
    """
    _tag(ctx, "str")
    length = len(obj)
    _feed(ctx, str(length).encode("ascii"))
    if length <= _whole_limit(ctx):
        _feed(ctx, obj.encode("utf-8", "surrogatepass"))
        return
    keep = max(1, ctx.budget.sample_bytes)
    step = max(1, length // keep)
    _feed(ctx, f"step={step}".encode("ascii"))
    _feed(ctx, obj[::step].encode("utf-8", "surrogatepass"))
    _feed(ctx, obj[-1].encode("utf-8", "surrogatepass"))


def _digest_bytes(obj: bytes | bytearray | memoryview, ctx: _Context) -> None:
    """Digest a byte buffer, whole or strided."""
    _tag(ctx, _type_name(obj))
    _feed(ctx, str(len(obj)).encode("ascii"))
    if len(obj) <= _whole_limit(ctx):
        _feed(ctx, bytes(obj))
        return
    _digest_sampled_bytes(obj, ctx)


def _digest_sampled_bytes(obj: bytes | bytearray | memoryview, ctx: _Context) -> None:
    """Feed a fixed-stride sample of a buffer larger than the whole-content limit."""
    length = len(obj)
    keep = max(1, ctx.budget.sample_bytes)
    step = max(1, length // keep)
    _feed(ctx, f"step={step}".encode("ascii"))
    _feed(ctx, bytes(obj[::step]))
    _feed(ctx, bytes(obj[-1:]))


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------


def _digest_container(obj: object, ctx: _Context) -> bool:
    """Digest a sequence, mapping, or set by its elements. Return ``True`` when handled."""
    if isinstance(obj, (list, tuple)):
        _digest_sequence(obj, ctx)
        return True
    if isinstance(obj, dict):
        _digest_mapping(obj, ctx)
        return True
    if isinstance(obj, (set, frozenset)):
        _digest_set(obj, ctx)
        return True
    return False


def _enter(obj: object, ctx: _Context) -> bool:
    """Push *obj* onto the recursion path. Return ``False`` when it is already on it.

    A notebook namespace holds cyclic values more often than one expects — a
    graph, a parent/child tree, ``a.append(a)`` by accident. Recording the cycle
    and stopping keeps the digest deterministic and the call finite.
    """
    marker = id(obj)
    if marker in ctx.path:
        _tag(ctx, "cycle")
        return False
    ctx.path.add(marker)
    ctx.depth += 1
    return True


def _leave(obj: object, ctx: _Context) -> None:
    """Pop *obj* off the recursion path."""
    ctx.path.discard(id(obj))
    ctx.depth -= 1


def _digest_sequence(obj: list[Any] | tuple[Any, ...], ctx: _Context) -> None:
    """Digest a list or tuple: type, length, then strided elements."""
    _tag(ctx, _type_name(obj))
    length = len(obj)
    _feed(ctx, str(length).encode("ascii"))
    if not _enter(obj, ctx):
        return
    try:
        for index in _stride_indices(length, ctx.budget.container_items):
            if _exhausted(ctx):
                ctx.truncated = True
                break
            _feed(ctx, str(index).encode("ascii"))
            _digest(obj[index], ctx)
    finally:
        _leave(obj, ctx)


def _digest_mapping(obj: dict[Any, Any], ctx: _Context) -> None:
    """Digest a dict: type, length, then strided key/value pairs.

    A dict is not indexable, so the stride is applied to its iterator. Past
    :attr:`FingerprintBudget.max_scan_items` even walking the skipped entries
    costs more than the budget allows, and a recorded prefix replaces the
    strided sample.
    """
    _tag(ctx, _type_name(obj))
    length = len(obj)
    _feed(ctx, str(length).encode("ascii"))
    if not _enter(obj, ctx):
        return
    try:
        for key, value in _sampled_entries(obj.items(), length, ctx):
            if _exhausted(ctx):
                ctx.truncated = True
                break
            _digest(key, ctx)
            _digest(value, ctx)
    finally:
        _leave(obj, ctx)


def _digest_set(obj: set[Any] | frozenset[Any], ctx: _Context) -> None:
    """Digest a set: type, length, then an order-independent fold of its elements.

    Set iteration order is an artefact of the hash table, not of the value, so
    the elements are combined by XOR of their own digests. Two sets holding the
    same elements therefore agree whatever order they were built in, and a
    swapped member — ``s.discard(2); s.add(99)``, which leaves the length
    untouched — still moves the result.
    """
    _tag(ctx, _type_name(obj))
    length = len(obj)
    _feed(ctx, str(length).encode("ascii"))
    if not _enter(obj, ctx):  # pragma: no cover - a set cannot contain itself
        # Kept for the depth bookkeeping and so every container reads the same;
        # the early return is unreachable because a set is not hashable.
        return
    try:
        combined = 0
        for element in _sampled_entries(iter(obj), length, ctx):
            if _exhausted(ctx):
                ctx.truncated = True
                break
            combined ^= _element_digest(element, ctx)
        _feed(ctx, combined.to_bytes(8, "little"))
    finally:
        _leave(obj, ctx)


def _sampled_entries(iterator: Any, length: int, ctx: _Context) -> list[Any]:
    """Return a bounded, full-extent sample of a non-indexable iterable."""
    keep = ctx.budget.container_items
    if length <= keep:
        return list(iterator)
    if length > ctx.budget.max_scan_items:
        ctx.truncated = True
        _tag(ctx, "prefix")
        return list(islice(iterator, keep))
    step = max(1, length // keep)
    _feed(ctx, f"step={step}".encode("ascii"))
    return list(islice(iterator, 0, None, step))


def _element_digest(obj: object, ctx: _Context) -> int:
    """Digest one element into its own hasher and return the 64-bit result.

    Used where elements must combine order-independently. The budget counters
    stay on the shared context, so a large set costs no more than any other
    value.
    """
    outer = ctx.hasher
    ctx.hasher = _new_hasher()
    try:
        _digest(obj, ctx)
        return int(ctx.hasher.intdigest())
    finally:
        ctx.hasher = outer


# ---------------------------------------------------------------------------
# numpy
# ---------------------------------------------------------------------------


def _digest_numpy(obj: object, ctx: _Context) -> bool:
    """Digest a numpy array or scalar. Return ``True`` when handled."""
    numpy = _numpy()
    if numpy is None:
        return False
    if isinstance(obj, numpy.ndarray):
        _digest_ndarray(obj, ctx)
        return True
    if isinstance(obj, numpy.generic):
        _tag(ctx, "numpy.scalar")
        _feed(ctx, obj.dtype.str.encode("ascii"))
        _feed(ctx, obj.tobytes())
        return True
    return False


def _digest_ndarray(arr: Any, ctx: _Context) -> None:
    """Digest an array by shape, dtype, and bytes — whole below the bound, strided above.

    An object-dtype array holds pointers, not content, so hashing its buffer
    would miss a mutation of anything it points at. Those are walked element by
    element instead, which is also what a frame's object columns get.
    """
    _tag(ctx, "numpy.ndarray")
    _feed(ctx, str(arr.shape).encode("ascii"))
    _feed(ctx, arr.dtype.str.encode("ascii"))
    _feed(ctx, str(arr.size).encode("ascii"))
    if arr.size == 0:
        return
    if arr.dtype.hasobject:
        _digest_object_array(arr, ctx)
        return

    itemsize = max(1, int(arr.dtype.itemsize))
    if int(arr.nbytes) <= _whole_limit(ctx):
        _feed(ctx, arr.tobytes())
        return
    keep = max(1, ctx.budget.sample_bytes // itemsize)
    step = max(1, int(arr.size) // keep)
    flat = _flat(arr)
    _feed(ctx, f"step={step}".encode("ascii"))
    _feed(ctx, flat[::step].tobytes())
    _feed(ctx, flat[-1:].tobytes())


def _flat(arr: Any) -> Any:
    """Return a 1-D handle on *arr* that a stride can be taken from cheaply.

    ``reshape(-1)`` is a view for C-contiguous data and a full copy otherwise,
    which would blow the budget on the very arrays the budget exists for; the
    ``flat`` iterator materialises only what the stride selects.
    """
    return arr.reshape(-1) if arr.flags["C_CONTIGUOUS"] else arr.flat


def _digest_object_array(arr: Any, ctx: _Context) -> None:
    """Digest an object-dtype array element by element, strided."""
    if not _enter(arr, ctx):
        return
    try:
        flat = _flat(arr)
        for index in _stride_indices(int(arr.size), ctx.budget.container_items):
            if _exhausted(ctx):
                ctx.truncated = True
                break
            _digest(flat[index], ctx)
    finally:
        _leave(arr, ctx)


# ---------------------------------------------------------------------------
# pandas
# ---------------------------------------------------------------------------


#: Sentinel for "this pandas build has no such singleton", so the identity
#: comparison below can never accidentally match a real value.
_MISSING = object()


def _digest_pandas(obj: object, ctx: _Context) -> bool:
    """Digest a pandas frame, series, index, or null scalar. Return ``True`` when handled."""
    pandas = _pandas()
    if pandas is None:
        return False
    if obj is getattr(pandas, "NA", _MISSING) or obj is getattr(pandas, "NaT", _MISSING):
        # pandas' null scalars are permanent singletons, so identity here is
        # content, not a guess: they are the values a nullable column is made of
        # and FR-024 requires such a column to be inspected by content.
        _tag(ctx, f"pandas.{obj!s}")
        return True
    if isinstance(obj, pandas.DataFrame):
        _digest_frame(obj, ctx)
        return True
    if isinstance(obj, pandas.Series):
        _digest_series(obj, ctx)
        return True
    if isinstance(obj, pandas.Index):
        _digest_index(obj, ctx)
        return True
    return False


def _digest_frame(frame: Any, ctx: _Context) -> None:
    """Digest a frame: shape, columns, index, then each column's values.

    Column by column rather than block by block, because a frame's block layout
    is an implementation detail that reshuffles on assignment while the columns
    a person sees do not.
    """
    _tag(ctx, "pandas.DataFrame")
    _feed(ctx, str(frame.shape).encode("ascii"))
    if not _enter(frame, ctx):
        return
    try:
        _digest_index(frame.columns, ctx)
        _digest_index(frame.index, ctx)
        ncols = int(frame.shape[1])
        for position in _stride_indices(ncols, ctx.budget.container_items):
            if _exhausted(ctx):
                ctx.truncated = True
                break
            _digest_values(frame.iloc[:, position], ctx)
    finally:
        _leave(frame, ctx)


def _digest_series(series: Any, ctx: _Context) -> None:
    """Digest a series: name, index, and values."""
    _tag(ctx, "pandas.Series")
    _feed(ctx, str(len(series)).encode("ascii"))
    if not _enter(series, ctx):
        return
    try:
        _digest(series.name, ctx)
        _digest_index(series.index, ctx)
        _digest_values(series, ctx)
    finally:
        _leave(series, ctx)


def _digest_index(index: Any, ctx: _Context) -> None:
    """Digest an index, taking the cheap route for the two shapes that have one.

    A ``RangeIndex`` is three integers; materialising it as an array would cost
    the length of the frame for no information. A ``MultiIndex`` is codes plus
    levels, which is both cheaper and more faithful than its tuples.
    """
    _tag(ctx, f"pandas.Index:{type(index).__name__}")
    _feed(ctx, str(len(index)).encode("ascii"))
    _feed(ctx, str(getattr(index, "dtype", "")).encode("utf-8"))
    if hasattr(index, "start") and hasattr(index, "step") and type(index).__name__ == "RangeIndex":
        _feed(ctx, f"{index.start}:{index.stop}:{index.step}".encode("ascii"))
        return
    if hasattr(index, "codes") and hasattr(index, "levels"):
        for level in index.levels:
            _digest_index(level, ctx)
        for codes in index.codes:
            _digest(_as_array(codes), ctx)
        return
    _digest_values(index, ctx)


def _digest_values(values: Any, ctx: _Context) -> None:
    """Digest the values of a series, column, or index.

    The positional sample is taken *before* conversion, so a hundred-million-row
    column is never materialised as a numpy array to hash 64 KiB of it. Whether
    the result is a numeric buffer or an object array is then the array path's
    problem, and it already knows the difference.
    """
    length = len(values)
    _feed(ctx, str(length).encode("ascii"))
    _feed(ctx, str(values.dtype).encode("utf-8"))
    if length == 0:
        return
    keep = max(1, ctx.budget.sample_bytes // 8)
    step = 1 if length <= ctx.budget.whole_content_bytes // 8 else max(1, length // keep)
    if step > 1:
        # The stride lands on ``length - length % step``, which is not the last
        # row, so the tail is taken separately. FR-025 says the sample spans the
        # full extent, and a person who edits the bottom row of a frame is
        # entitled to see that edit observed.
        _feed(ctx, f"step={step}".encode("ascii"))
        head = values[::step] if _is_index(values) else values.iloc[::step]
        tail = values[-1:] if _is_index(values) else values.iloc[-1:]
        _digest_array_like(head, ctx)
        _digest_array_like(tail, ctx)
        return
    _digest_array_like(values, ctx)


def _is_index(values: Any) -> bool:
    """Return ``True`` for a pandas index, which slices positionally on ``[]``."""
    pandas = _pandas()
    return pandas is not None and isinstance(values, pandas.Index)


def _digest_array_like(values: Any, ctx: _Context) -> None:
    """Digest the backing storage of an already-sampled series, column, or index.

    Extension dtypes are the awkward part. Converting one to numpy can build a
    fresh Python object per row — for a timezone-aware column, a new
    ``Timestamp`` each call, whose identity differs every time and would report
    the column as changed on every run. So the two shapes that would do that are
    read through their own storage instead: a categorical through codes and
    categories, a datetime-like through its integer view.
    """
    numpy = _numpy()
    if numpy is not None and isinstance(values, numpy.ndarray):
        _digest_ndarray(values, ctx)
        return
    array = values.array if hasattr(values, "array") else values
    if numpy is not None and isinstance(getattr(values, "dtype", None), numpy.dtype):
        _digest_ndarray(_as_array(values.to_numpy(copy=False)), ctx)
        return
    if hasattr(array, "codes") and hasattr(array, "categories"):
        _tag(ctx, "pandas.Categorical")
        _digest(_as_array(array.codes), ctx)
        _digest_index(array.categories, ctx)
        return
    if hasattr(array, "isna"):
        _digest(_as_array(array.isna()), ctx)
    integer_view = getattr(array, "asi8", None)
    if integer_view is not None:
        _tag(ctx, "pandas.asi8")
        _digest(_as_array(integer_view), ctx)
        return
    _digest(_as_array(array), ctx)


def _as_array(values: Any) -> Any:
    """Return *values* as a numpy array without copying when it already is one."""
    numpy = _numpy()
    if numpy is None:  # pragma: no cover - pandas cannot be loaded without numpy
        return values
    return numpy.asarray(values)


# ---------------------------------------------------------------------------
# The fallback
# ---------------------------------------------------------------------------


def _digest_identity(obj: object, ctx: _Context) -> None:
    """Record a value no content rule covers, and mark the result unobservable.

    ``repr`` is deliberately not consulted. A value whose representation carries
    an address, a timestamp, or a counter would look different on every call and
    produce a change the person cannot act on; a value whose representation
    elides its contents would look identical after a real mutation. Identity is
    at least true, and FR-029 makes sure the person is told it is all we have.
    """
    _tag(ctx, "identity")
    _feed(ctx, _type_name(obj).encode("utf-8"))
    _feed(ctx, id(obj).to_bytes(8, "little", signed=False))
    ctx.observable = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _fingerprint_context(obj: object, budget: FingerprintBudget = FINGERPRINT_BUDGET) -> _Context:
    """Run the digest and return the whole context, counters included.

    Separated from :func:`fingerprint` so the budget itself can be asserted on:
    the tests read ``hashed_bytes`` and ``nodes`` back to prove FR-025 holds,
    which no public return value should have to carry.
    """
    ctx = _Context(hasher=_new_hasher(), budget=budget)
    _digest(obj, ctx)
    return ctx


@provisional(since="0.3.4")
def fingerprint(obj: object) -> Fingerprint:
    """Return a bounded content fingerprint of *obj* (FR-024, FR-025, FR-029).

    Pure: it reads *obj* and nothing else, executes nothing, and touches no
    file. Equal for an object that has not changed; different, within the bound
    of :data:`FINGERPRINT_BUDGET`, for one mutated in place.

    Content is inspected for numpy arrays, pandas frames, series and indexes,
    lists, tuples, dicts, sets, strings, bytes, and numbers. Any other type
    falls back to identity and comes back with ``observable=False``, which the
    namespace comparison reports so the person knows the observation does not
    cover that name.

    Example:
        >>> values = [1, 2, 3]
        >>> before = fingerprint(values)
        >>> before == fingerprint(values)
        True
        >>> values[0] = 99
        >>> before == fingerprint(values)
        False
        >>> fingerprint(values).observable
        True
    """
    ctx = _fingerprint_context(obj)
    return Fingerprint(
        digest=ctx.hasher.hexdigest(),
        observable=ctx.observable,
        type_name=_type_name(obj),
    )


# ---------------------------------------------------------------------------
# The namespace comparison and the observation record (FR-026 to FR-030)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class ObservedChange:
    """What a cell was seen to change when it ran (spec §3 Key Entities).

    The record :func:`compare_namespaces` produces and the notebook stores. It is
    a statement about *one version of one cell*: :attr:`source_hash` is the hash
    of the cell's source at the moment of the run, and FR-027 requires the
    observation to be discarded once that hash no longer matches the cell, so a
    change an edit removed cannot keep drawing an edge. Use
    :meth:`applies_to` rather than comparing the hashes by hand.

    :attr:`changed_names` is the observed changed set of FR-026 — names whose
    fingerprint differs, names that appeared, and names that disappeared, in one
    set, because the graph treats all three the same way: the cell is a definer
    of the name. :attr:`unobservable_names` is the FR-029 report, and is
    deliberately *not* folded into the changed set: a name is unobservable
    because the comparison could not see whether it changed, which is not the
    same claim as "it changed", and a set that conflated them would add an edge
    for every open file handle in the namespace on every run.

    An observation only ever **adds** to a cell's changed set (FR-030). The join
    is :func:`scistudio.explore.dependency_analysis.build_graph`, which unions
    this record with the cell's static estimate and never subtracts from it.
    """

    cell_id: str
    changed_names: frozenset[str]
    unobservable_names: frozenset[str]
    source_hash: str

    def __post_init__(self) -> None:
        # Normalise so a record decoded from JSON lists compares equal to one
        # built by the comparison. Without this, a round trip through cell
        # metadata would produce a record that is equal in content and unequal
        # in ``==``, and the FR-032 round-trip check would be testing the
        # container type rather than the observation.
        object.__setattr__(self, "changed_names", frozenset(self.changed_names))
        object.__setattr__(self, "unobservable_names", frozenset(self.unobservable_names))

    def applies_to(self, source_hash: str) -> bool:
        """Return ``True`` when this observation still describes *source_hash* (FR-027).

        ``False`` means the cell has been edited since the run and the
        observation must be discarded, leaving the static estimate alone to
        govern until the cell runs again.
        """
        return self.source_hash == source_hash


@provisional(since="0.3.4")
def compare_namespaces(
    before: Mapping[str, Fingerprint],
    after: Mapping[str, Fingerprint],
    *,
    cell_id: str,
    source_hash: str,
) -> ObservedChange:
    """Report what a cell changed, from the namespace fingerprints either side of its run (FR-026).

    *before* and *after* map every top-level name in the module namespace to its
    :class:`Fingerprint`, taken before the cell ran and after it finished. Taking
    those two snapshots is the kernel's job and the explore-session spec's to
    specify (A-007); this function is pure over the two mappings and executes
    nothing.

    A name is in the observed changed set when it

    * appeared — it is in *after* and not in *before*, or
    * disappeared — it is in *before* and not in *after*, which is what ``del df``
      looks like from here, or
    * differs — it is in both and the two fingerprints are unequal.

    A name whose fingerprint fell back to identity on either side is reported in
    :attr:`ObservedChange.unobservable_names` (FR-029), whether or not it is also
    reported as changed. Equality of two identity fingerprints proves only that
    the name still points at the same address, so the honest report is that the
    observation does not cover it — and CPython reuses addresses, so it does not
    even prove that for two short-lived objects.

    The name sets are read from both mappings, so a caller that filters dunder
    names or kernel-injected names does so before calling; this function reports
    on exactly what it is given.

    Example:
        >>> before = {"df": fingerprint([1, 2]), "gone": fingerprint(1)}
        >>> after = {"df": fingerprint([1, 99]), "new": fingerprint(2)}
        >>> observed = compare_namespaces(before, after, cell_id="c2", source_hash="ab")
        >>> sorted(observed.changed_names)
        ['df', 'gone', 'new']
        >>> observed.applies_to("ab")
        True
    """
    changed: set[str] = set()
    unobservable: set[str] = set()

    for name, value in before.items():
        if not value.observable:
            unobservable.add(name)
        if name not in after:
            changed.add(name)
    for name, value in after.items():
        if not value.observable:
            unobservable.add(name)
        previous = before.get(name)
        if previous is None or previous != value:
            changed.add(name)

    return ObservedChange(
        cell_id=cell_id,
        changed_names=frozenset(changed),
        unobservable_names=frozenset(unobservable),
        source_hash=source_hash,
    )
