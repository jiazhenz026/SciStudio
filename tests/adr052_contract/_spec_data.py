"""Independent ADR-052 contract data, hand-transcribed from the spec (#1833).

Not a test module (leading underscore -> pytest does not collect it). It holds
the constants the contract tests parametrize over: the committed expected surface
(``expected_surface.json``), the per-root demotions that must NOT appear in
``__all__``, the re-export expectations, and the signature/constructor specs.

Everything here is derived purely from ``docs/specs/adr-052-public-api-surface.md``
and ``docs/adr/ADR-052.md`` -- no implementation source was read.
"""

from __future__ import annotations

import importlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
SINCE_BASELINE = "0.3.1"


def import_root(name: str):
    """Import and return a public root module, or ``None`` if it cannot import.

    Returning ``None`` (rather than raising) lets a test assert a clear failure
    message instead of erroring during collection. Defined here (a uniquely
    named, non-``conftest`` module) so the contract test modules import it
    without depending on ``sys.modules["conftest"]`` — which, in a full-tree
    pytest run, resolves to a *different* suite's ``conftest`` and breaks the
    bare ``from conftest import import_root`` (collection-order fragility).
    """
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def module_all(module) -> set[str]:
    """The declared public surface of a module: ``set(module.__all__)``."""
    return set(getattr(module, "__all__", ()) or ())


with open(os.path.join(_HERE, "expected_surface.json"), encoding="utf-8") as _fh:
    EXPECTED_SURFACE: dict = json.load(_fh)

#: The nine canonical public roots (manager-defined freeze contract).
ROOTS: tuple[str, ...] = tuple(k for k in EXPECTED_SURFACE if not k.startswith("_"))

# --------------------------------------------------------------------------- #
# Non-markable public symbols (ADR-052 §15). These nine are ``str`` constants or
# ``Literal`` / ``Callable`` type-aliases that cannot carry a runtime
# ``@stable`` / ``@provisional`` marker, so ``get_stability()`` returns ``None``
# for them BY DESIGN (the stability module's docstring calls this "the honest
# result"). They ARE public per spec; their tier is carried by this expected
# fixture (and the snapshot), not a runtime marker. The inventory / no-leak /
# semantics tests therefore skip the get_stability read for these — the fixture
# still pins their presence and tier.
# --------------------------------------------------------------------------- #
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


def root_entry(root: str) -> dict:
    return EXPECTED_SURFACE[root]


def expected_symbols(root: str) -> dict[str, dict]:
    return EXPECTED_SURFACE[root]["symbols"]


def root_mode(root: str) -> str:
    return EXPECTED_SURFACE[root]["mode"]


# --------------------------------------------------------------------------- #
# Demotions: symbols that were public (or in __all__) and MUST be dropped from
# the root's __all__ in #1817. Spec §3.9 / §4.3-§4.6 / §4.8 / §6.3 / §6.5 / §8.1
# / §8.2. (png_data_uri and the methods are members, not module exports, but the
# contract still forbids them as top-level public exports.)
# --------------------------------------------------------------------------- #
DEMOTIONS: dict[str, tuple[str, ...]] = {
    # spec §3.9 (owner opt-B): 0 author importers -> internal.
    "scistudio.core.types": ("TypeRegistry", "TypeSpec"),
    # spec §4.3 (Port + 4 port helpers), §4.4 (BlockState), §4.6 (BlockResult),
    # §4.8 (interactive internals dropped from the re-exported set).
    "scistudio.blocks.base": (
        "Port",
        "BlockState",
        "BlockResult",
        "port_accepts_type",
        "port_accepts_signature",
        "validate_connection",
        "validate_port_constraint",
        "SupportsInteraction",
        "coerce_prompt",
        "serialise_storage_ref",
        "deserialise_storage_ref",
        "INTERACTIVE_INTERMEDIATE_KEY",
    ),
    # spec §6.3 / §6.5: normalize_* helpers + the concrete Load/Save blocks.
    "scistudio.blocks.io": (
        "LoadData",
        "SaveData",
        "normalize_extension",
        "normalize_extensions",
    ),
    # spec §8.1: the 7 runtime-owned model internals dropped from models.__all__.
    "scistudio.previewers.models": (
        "PreviewSession",
        "RoutingAmbiguityError",
        "UnknownPreviewerError",
        "UnknownTargetError",
        "MissingBundleError",
        "InvalidSpecError",
        "DuplicatePreviewerIdError",
    ),
    # spec §8.2: legacy method + runtime budget constants are not public exports.
    "scistudio.previewers.data_access": (
        "png_data_uri",
        "DEFAULT_MAX_ROWS",
        "DEFAULT_MAX_BYTES",
        "DEFAULT_MAX_ITEMS",
        "DEFAULT_MAX_TILE",
        "DEFAULT_MAX_DIM",
    ),
}

# --------------------------------------------------------------------------- #
# Re-exports: a public symbol whose canonical home is a root other than where it
# is defined. (root -> tuple of names expected importable from that root and, if
# in_all=True, present in that root's __all__.) Spec §3.1 / §4.7 / §4.8 / §8.5.
# --------------------------------------------------------------------------- #
# Interactive surface re-exported onto blocks.base (spec §4.8).
INTERACTIVE_REEXPORTS: tuple[str, ...] = (
    "InteractiveMixin",
    "InteractivePrompt",
    "PanelManifest",
    "load_intermediate",
    "PANEL_API_VERSION",
    "INTERACTIVE_RESPONSE_KEY",
)

REEXPORTS: dict[str, tuple[str, ...]] = {
    # spec §4.8: interactive author surface re-exported from the blocks.base root.
    "scistudio.blocks.base": (*INTERACTIVE_REEXPORTS, "PackageOtaSource"),
    # spec §4.7 / §7: AppBlock-cancellation error re-exported into blocks.app.
    "scistudio.blocks.app": ("BlockCancelledByAppError",),
    # spec §3.1 / §8.5: StorageReference public via the core.types re-export.
    "scistudio.core.types": ("StorageReference",),
}


# --------------------------------------------------------------------------- #
# Ergonomic accessors (spec §10 / ADR §3.1) -- (root, class, method, kind).
# kind: "ndarray" | "pandas.DataFrame" | "pandas.Series".
# --------------------------------------------------------------------------- #
ERGONOMIC_ACCESSORS = (
    ("scistudio.core.types", "Array", "to_numpy", "ndarray"),
    ("scistudio.core.types", "DataFrame", "to_pandas", "pandas.DataFrame"),
    ("scistudio.core.types", "DataFrame", "to_numpy", "ndarray"),
    ("scistudio.core.types", "Series", "to_pandas", "pandas.Series"),
    ("scistudio.core.types", "Series", "to_numpy", "ndarray"),
)

#: Types that MUST NOT carry an ergonomic accessor (already ergonomic; spec §10).
NO_ACCESSOR_TYPES = ("Text", "Artifact", "CompositeData")

# --------------------------------------------------------------------------- #
# Large-data surface (spec §11 / ADR §3.2) -- (root, owner, method, required
# params subset, var_kind).  var_kind: "VAR_KEYWORD" | "VAR_POSITIONAL" | None.
# --------------------------------------------------------------------------- #
LARGE_DATA_METHODS = (
    ("scistudio.core.types", "Array", "sel", (), "VAR_KEYWORD"),
    ("scistudio.core.types", "DataObject", "slice", (), "VAR_POSITIONAL"),
    ("scistudio.core.types", "DataObject", "iter_chunks", ("chunk_size",), None),
    (
        "scistudio.blocks.base",
        "Block",
        "persist_array",
        ("shape", "dtype"),
        None,
    ),
    ("scistudio.blocks.base", "Block", "persist_table", ("table",), None),
)

# --------------------------------------------------------------------------- #
# De-underscored reconstruction hooks (spec §3.1, owner opt-A): the public name
# MUST exist on DataObject and the underscore-prefixed name MUST be gone.
# --------------------------------------------------------------------------- #
DEUNDERSCORED_HOOKS = (
    ("serialise_extra_metadata", "_serialise_extra_metadata"),
    ("reconstruct_extra_kwargs", "_reconstruct_extra_kwargs"),
)

# --------------------------------------------------------------------------- #
# Keyword-only constructor payloads (spec §3.x). Each entry:
# (class, keyword_only_params, forbidden_params, positional_params).
#   - keyword_only_params: names that MUST be KEYWORD_ONLY in __init__.
#   - forbidden_params: names that MUST NOT appear in __init__ at all.
#   - positional_params: names that MUST be positional-or-keyword (NOT kw-only).
# The removed metadata shim (spec §16 cleanup) is encoded as forbidden 'metadata'
# on the DataObject base ctor.
# --------------------------------------------------------------------------- #
CONSTRUCTOR_SPECS = (
    ("DataObject", ("framework", "meta", "user", "storage_ref"), ("metadata",), ()),
    ("Array", ("axes", "data"), ("metadata",), ()),
    ("DataFrame", ("data",), ("metadata",), ()),
    ("Series", ("data",), ("metadata",), ()),
    ("Text", ("content",), ("data", "metadata"), ()),
    ("Artifact", ("file_path",), ("metadata",), ()),
    ("CompositeData", ("slots",), ("metadata",), ()),
    # spec §3.8: Collection ctor is positional (NOT kw-only); empty needs item_type.
    ("Collection", (), (), ("items", "item_type")),
)

#: spec §3.1 / §16: DataObject must expose NO 'metadata' property after the shim
#: is deleted; authors read provenance via the three-slot framework/meta/user.
REMOVED_PROPERTIES = (("DataObject", "metadata"),)

# --------------------------------------------------------------------------- #
# Deprecations (spec §6.1): IOBlock.supported_extensions stays importable but is
# marked deprecated. The exact "deprecated" marker is a #1817 convention the
# stability module does not yet encode (Tier = stable|provisional|internal), so
# the deprecation test probes several plausible conventions -- see the test's
# docstring. (root, owner_class, attr_name).
# --------------------------------------------------------------------------- #
DEPRECATED_MEMBERS = (("scistudio.blocks.io", "IOBlock", "supported_extensions"),)
