"""ADR-052 §15 public-API surface freeze + boundary tests.

This is the anti-drift enforcement layer for the public API contract
(ADR-052 + ``docs/specs/adr-052-public-api-surface.md``). Three things are
pinned here:

1. **Freeze test** (``test_public_surface_frozen``). The live public surface —
   every symbol in each canonical root's ``__all__``, with its stability tier
   and ``Since`` — is recomputed and diffed against the committed golden
   snapshot ``public_surface.snapshot.json``. Accidental drift (a refactor that
   adds, removes, renames, re-tiers, or re-dates a public symbol) makes the diff
   non-empty and fails CI. Intentional change means editing the snapshot, which
   is an owner-reviewed, human-readable diff (ADR-052 §15).

2. **No-internal-leak test** (``test_no_internal_or_undecorated_in_all``). Every
   ``__all__`` symbol must carry exactly one ``@stable`` / ``@provisional``
   marker (never ``@internal``, never undecorated) — ADR-052 §5.

3. **Signature assertions** for the spec-flagged new/changed members — the
   "signatures strictly consistent" layer that pins the concrete shapes the
   contract promises (ergonomic accessors, large-data methods, de-underscored
   reconstruction hooks, removed metadata shim, demoted/dropped symbols, and the
   re-exported interactive / AppBlock surfaces).

Derivation note: the EXPECTED surface in the snapshot is transcribed from the
spec's per-symbol tables / "Net __all__ change" notes ALONE — independent of the
#1817 implementation. Where this test fails against a tree that has not yet
landed #1817 (no ``__all__`` reconciliation, no stability decorators, accessors
not yet added, hooks still underscored, the metadata shim still present), that is
expected: the mismatch between the spec-derived contract and the live tree is the
whole point and is reconciled at integration.
"""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scistudio.stability import get_stability

# ---------------------------------------------------------------------------
# Canonical public roots (ADR-052 §3 / §3.10 / §4 / §5 / §6 / §7 / §7A / §8;
# the manager-defined shared freeze contract). Public surface = each root's
# ``__all__``.
# ---------------------------------------------------------------------------

CANONICAL_ROOTS: tuple[str, ...] = (
    "scistudio.core.types",
    "scistudio.core.meta",
    "scistudio.blocks.base",
    "scistudio.blocks.process",
    "scistudio.blocks.io",
    "scistudio.blocks.app",
    "scistudio.blocks.code",
    "scistudio.previewers.models",
    "scistudio.previewers.data_access",
)

_SNAPSHOT_PATH = Path(__file__).parent / "public_surface.snapshot.json"

# ---------------------------------------------------------------------------
# Non-markable public symbols (ADR-052 §15). These nine are ``str`` constants or
# ``Literal`` / ``Callable`` type-aliases that cannot carry a runtime
# ``@stable`` / ``@provisional`` marker, so ``get_stability()`` returns ``None``
# for them BY DESIGN — the stability module's own docstring calls this "the
# honest result". They ARE public per spec; their stability tier is carried by
# the snapshot / expected fixture, not a runtime marker (ADR-052 §15: the
# snapshot is the source of truth). The freeze diff still locks them via the
# live-``__all__`` vs snapshot membership check; only the runtime-marker read is
# exempted, and the no-internal-leak test does not flag them as undecorated.
# ---------------------------------------------------------------------------
NON_MARKABLE_PUBLIC_SYMBOLS: frozenset[tuple[str, str]] = frozenset(
    {
        ("scistudio.blocks.base", "INTERACTIVE_RESPONSE_KEY"),
        ("scistudio.blocks.base", "PANEL_API_VERSION"),
        ("scistudio.blocks.io", "CapabilityDirection"),
        ("scistudio.blocks.io", "MetadataFidelityLevel"),
        ("scistudio.blocks.code", "InterpreterFamily"),
        ("scistudio.previewers.models", "PREVIEWER_API_VERSION"),
        ("scistudio.previewers.models", "PreviewProvider"),
        ("scistudio.previewers.models", "PreviewResourceProvider"),
        ("scistudio.previewers.models", "PreviewerSpecList"),
    }
)


def _load_snapshot() -> dict[str, dict[str, dict[str, str]]]:
    raw = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    raw.pop("_meta", None)
    return raw


def _import_root(name: str) -> ModuleType:
    return importlib.import_module(name)


def _live_surface_for(root: str) -> dict[str, dict[str, Any] | None]:
    """Recompute the live public surface for one root.

    Mirrors the freeze design: import the root, read ``sorted(__all__)``, read
    ``get_stability`` off each exported object. A symbol that carries no marker
    maps to ``None`` (it is a leak the no-internal-leak test catches).
    """
    module = _import_root(root)
    all_names = getattr(module, "__all__", None)
    assert all_names is not None, f"{root} declares no __all__ (ADR-052 §2 requires one)"
    surface: dict[str, dict[str, Any] | None] = {}
    for name in sorted(all_names):
        obj = getattr(module, name)
        info = get_stability(obj)
        surface[name] = None if info is None else {"tier": info.tier, "since": info.since}
    return surface


def test_snapshot_covers_exactly_the_canonical_roots() -> None:
    """The golden snapshot must describe the 9 canonical roots and no others."""
    snapshot = _load_snapshot()
    assert set(snapshot) == set(CANONICAL_ROOTS), (
        "snapshot roots drifted from the canonical set:\n"
        f"  +in snapshot only: {sorted(set(snapshot) - set(CANONICAL_ROOTS))}\n"
        f"  -missing from snapshot: {sorted(set(CANONICAL_ROOTS) - set(snapshot))}"
    )


@pytest.mark.parametrize("root", CANONICAL_ROOTS)
def test_public_surface_frozen(root: str) -> None:
    """The live ``__all__`` + tiers + ``Since`` must equal the golden snapshot.

    A non-empty diff is a contract change. If it was intentional, update
    ``public_surface.snapshot.json`` (owner-reviewed per ADR-052 §15); if it was
    accidental, fix the code.
    """
    snapshot = _load_snapshot()
    expected = snapshot[root]
    live = _live_surface_for(root)

    expected_names = set(expected)
    live_names = set(live)

    added = sorted(live_names - expected_names)
    removed = sorted(expected_names - live_names)

    tier_changed: list[str] = []
    since_changed: list[str] = []
    undecorated: list[str] = []
    for name in sorted(expected_names & live_names):
        live_info = live[name]
        if live_info is None:
            if (root, name) in NON_MARKABLE_PUBLIC_SYMBOLS:
                # Non-markable public symbol (ADR-052 §15): no runtime marker,
                # so its tier is read from the snapshot, not get_stability. The
                # membership diff above still locks it (add/remove fails CI);
                # only the runtime tier/since read is skipped here.
                continue
            undecorated.append(name)
            continue
        if live_info["tier"] != expected[name]["tier"]:
            tier_changed.append(f"{name}: {expected[name]['tier']!r} -> {live_info['tier']!r}")
        if live_info["since"] != expected[name].get("since"):
            since_changed.append(f"{name}: {expected[name].get('since')!r} -> {live_info['since']!r}")

    problems: list[str] = []
    if added:
        problems.append(f"  +added (in live __all__, not frozen): {added}")
    if removed:
        problems.append(f"  -removed (frozen, missing from live __all__): {removed}")
    if tier_changed:
        problems.append("  ~tier-changed: " + "; ".join(tier_changed))
    if since_changed:
        problems.append("  ~since-changed: " + "; ".join(since_changed))
    if undecorated:
        problems.append(f"  !undecorated (no @stable/@provisional marker): {undecorated}")

    assert not problems, (
        f"public surface of {root} drifted from the frozen snapshot "
        f"({_SNAPSHOT_PATH.name}):\n" + "\n".join(problems)
    )


@pytest.mark.parametrize("root", CANONICAL_ROOTS)
def test_no_internal_or_undecorated_in_all(root: str) -> None:
    """No ``@internal`` and no undecorated symbol may appear in a root's ``__all__``.

    ADR-052 §5: every public symbol carries exactly one ``@stable`` /
    ``@provisional`` marker. ``@internal`` is never in a public ``__all__``.
    """
    module = _import_root(root)
    bad: list[str] = []
    for name in sorted(getattr(module, "__all__", [])):
        if (root, name) in NON_MARKABLE_PUBLIC_SYMBOLS:
            # Non-markable public symbol (ADR-052 §15): a constant / type-alias
            # that cannot carry a runtime marker — not an internal leak. Its
            # public tier is pinned by the snapshot, not get_stability().
            continue
        info = get_stability(getattr(module, name))
        if info is None:
            bad.append(f"{name} (undecorated)")
        elif info.tier == "internal":
            bad.append(f"{name} (@internal)")
    assert not bad, f"{root}.__all__ contains non-public symbols (ADR-052 §5): {bad}"


# ---------------------------------------------------------------------------
# Signature assertions for the spec-flagged new / changed / removed members.
# These pin the concrete shapes the contract promises ("signatures strictly
# consistent"). Many fail until #1817 lands; that is expected (see module docs).
# ---------------------------------------------------------------------------

_ABSENT = object()


def _has_callable(obj: object, name: str) -> bool:
    member = getattr(obj, name, None)
    return callable(member)


def test_ergonomic_accessors_exist_with_correct_owners() -> None:
    """§10: the additive ergonomic accessors are added on the right core types."""
    from scistudio.core.types import Array, DataFrame, Series

    assert _has_callable(Array, "to_numpy"), "Array.to_numpy() must exist (ADR-052 §10)"
    assert _has_callable(DataFrame, "to_pandas"), "DataFrame.to_pandas() must exist (§10)"
    assert _has_callable(DataFrame, "to_numpy"), "DataFrame.to_numpy() must exist (§10)"
    assert _has_callable(Series, "to_pandas"), "Series.to_pandas() must exist (§10)"
    assert _has_callable(Series, "to_numpy"), "Series.to_numpy() must exist (§10)"


def test_text_artifact_composite_have_no_ergonomic_accessor() -> None:
    """§10: already-ergonomic types add no to_pandas/to_numpy accessor."""
    from scistudio.core.types import Artifact, CompositeData, Text

    for cls in (Text, Artifact, CompositeData):
        assert not hasattr(cls, "to_pandas"), f"{cls.__name__} must not define to_pandas (§10)"
        assert not hasattr(cls, "to_numpy"), f"{cls.__name__} must not define to_numpy (§10)"


def test_array_sel_signature_takes_named_axes() -> None:
    """§11: ``Array.sel(**axes)`` — partial read by named axes."""
    from scistudio.core.types import Array

    params = inspect.signature(Array.sel).parameters
    assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()), (
        f"Array.sel must accept **axes (ADR-052 §11); got {list(params)}"
    )


def test_dataobject_large_data_methods_present() -> None:
    """§11: ``DataObject.slice(*args)`` and ``iter_chunks(chunk_size)``."""
    from scistudio.core.types import DataObject

    assert _has_callable(DataObject, "slice"), "DataObject.slice must exist (§11)"
    assert _has_callable(DataObject, "iter_chunks"), "DataObject.iter_chunks must exist (§11)"
    iter_params = inspect.signature(DataObject.iter_chunks).parameters
    assert "chunk_size" in iter_params, f"iter_chunks must take chunk_size; got {list(iter_params)}"


def test_block_persist_signatures() -> None:
    """§11: ``Block.persist_array`` / ``persist_table`` streaming writers."""
    from scistudio.blocks.base import Block

    assert _has_callable(Block, "persist_array"), "Block.persist_array must exist (§11)"
    assert _has_callable(Block, "persist_table"), "Block.persist_table must exist (§11)"
    arr_params = inspect.signature(Block.persist_array).parameters
    for expected in ("shape", "dtype", "output_dir", "chunks"):
        assert expected in arr_params, (
            f"Block.persist_array must take {expected!r} (§11); got {list(arr_params)}"
        )
    tbl_params = inspect.signature(Block.persist_table).parameters
    assert "output_dir" in tbl_params, f"persist_table must take output_dir (§11); got {list(tbl_params)}"


def test_reconstruction_hooks_are_de_underscored() -> None:
    """§3.1 (opt-A): the reconstruction-hook pair is published de-underscored.

    ``reconstruct_extra_kwargs`` / ``serialise_extra_metadata`` exist on the base
    type; the old underscore-prefixed names are gone.
    """
    from scistudio.core.types import DataObject

    assert _has_callable(DataObject, "reconstruct_extra_kwargs"), (
        "DataObject.reconstruct_extra_kwargs must exist (ADR-052 §3.1 opt-A, de-underscored in #1817)"
    )
    assert _has_callable(DataObject, "serialise_extra_metadata"), (
        "DataObject.serialise_extra_metadata must exist (ADR-052 §3.1 opt-A)"
    )
    assert not hasattr(DataObject, "_reconstruct_extra_kwargs"), (
        "the underscore-prefixed _reconstruct_extra_kwargs must be removed (#1817 de-underscore)"
    )
    assert not hasattr(DataObject, "_serialise_extra_metadata"), (
        "the underscore-prefixed _serialise_extra_metadata must be removed (#1817 de-underscore)"
    )


def test_dataobject_metadata_shim_removed() -> None:
    """§3.1 / §16: the deprecated ``metadata`` property + ``metadata=`` kwarg are gone."""
    from scistudio.core.types import DataObject

    # No ``metadata`` property survives on the class.
    assert inspect.getattr_static(DataObject, "metadata", _ABSENT) is _ABSENT, (
        "DataObject.metadata property must be removed (ADR-052 §3.1 / §16 Phase-11 cleanup)"
    )
    # No ``metadata=`` constructor kwarg survives.
    init_params = inspect.signature(DataObject.__init__).parameters
    assert "metadata" not in init_params, (
        f"DataObject.__init__ must not accept metadata= (§16); got {list(init_params)}"
    )


def test_type_registry_and_spec_not_public_in_core_types() -> None:
    """§3.9: ``TypeRegistry`` / ``TypeSpec`` demoted to internal (dropped from __all__)."""
    import scistudio.core.types as core_types

    assert "TypeRegistry" not in core_types.__all__, "TypeRegistry must not be in core.types.__all__ (§3.9)"
    assert "TypeSpec" not in core_types.__all__, "TypeSpec must not be in core.types.__all__ (§3.9)"
    # The internal deep path still resolves them (ADR-052 §2: deep paths keep working).
    registry = importlib.import_module("scistudio.core.types.registry")
    assert hasattr(registry, "TypeRegistry") and hasattr(registry, "TypeSpec"), (
        "the internal scistudio.core.types.registry path must keep TypeRegistry/TypeSpec (§3.9)"
    )


def test_io_internal_blocks_and_helpers_not_public() -> None:
    """§6.5 / §6.3: LoadData / SaveData / normalize_extension(s) are internal now."""
    import scistudio.blocks.io as io_root

    for name in ("LoadData", "SaveData", "normalize_extension", "normalize_extensions"):
        assert name not in io_root.__all__, f"{name} must not be in blocks.io.__all__ (ADR-052 §6.3/§6.5)"


def test_interactive_surface_reexported_from_blocks_base() -> None:
    """§4.8: the kept interactive surface is re-exported from the ``blocks.base`` root."""
    import scistudio.blocks.base as base_root

    for name in (
        "InteractiveMixin",
        "InteractivePrompt",
        "PanelManifest",
        "load_intermediate",
        "PANEL_API_VERSION",
        "INTERACTIVE_RESPONSE_KEY",
    ):
        assert name in base_root.__all__, f"{name} must be re-exported from blocks.base.__all__ (§4.8)"
        assert hasattr(base_root, name), f"{name} must be reachable from blocks.base (§4.8)"


def test_package_ota_source_in_blocks_base() -> None:
    """§4.5: ``PackageOtaSource`` is added to the ``blocks.base`` public surface."""
    import scistudio.blocks.base as base_root

    assert "PackageOtaSource" in base_root.__all__, "PackageOtaSource must be in blocks.base.__all__ (§4.5)"


def test_block_cancelled_by_app_error_reexported_from_blocks_app() -> None:
    """§4.7 / §7: ``BlockCancelledByAppError`` is re-exported from ``blocks.app``."""
    import scistudio.blocks.app as app_root

    assert "BlockCancelledByAppError" in app_root.__all__, (
        "BlockCancelledByAppError must be re-exported from blocks.app.__all__ (§4.7/§7)"
    )
    assert hasattr(app_root, "BlockCancelledByAppError")
