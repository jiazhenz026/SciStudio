"""Materialise / reconstruct DataObjects through the IO block layer.

This module encapsulates the two operations that ``AppBlock`` and the
external-app file-exchange bridge (``blocks/app/bridge.py``) repeat
ad-hoc today:

- :func:`materialise_to_file` — write a :class:`DataObject` to a file
  using the saver class returned by
  :meth:`BlockRegistry.find_saver` (ADR-028 §D8 / #1077).
- :func:`reconstruct_from_file` — build a typed :class:`DataObject`
  from a file path by routing through
  :meth:`BlockRegistry.find_loader`.

The helpers are intentionally pure (no module-level state). Each
accepts an optional pre-built :class:`BlockRegistry` so callers in hot
paths can amortise the registry scan; if omitted, the helper builds
and scans one on demand.

ADR-028 §D8 / issue #1078: introduced as the canonical materialisation
surface so AppBlock binner and bridge prepare/restore (follow-up
issues #1079 and #1080) stop reimplementing format dispatch.

Pass-through policy
-------------------

When *obj* already has a ``storage_ref`` whose ``path`` ends in the
target extension, :func:`materialise_to_file` prefers a native link
via :func:`scieasy.utils.fs.mount_pathlike` over re-writing the bytes
through the saver. The link falls back to a byte copy (or normal saver
round-trip) if the platform refuses to create a link.

Artifact fallback
-----------------

When :func:`reconstruct_from_file` cannot find a loader for the
``(target_type, extension)`` pair, it returns an
:class:`scieasy.core.types.artifact.Artifact` when *target_type* is
``Artifact`` (or a subclass). For any other concrete target type
without a matching loader, the helper raises :class:`LookupError`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.registry import BlockRegistry
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection

__all__ = ["materialise_to_file", "reconstruct_from_file"]

_logger = logging.getLogger(__name__)


def _get_registry(registry: BlockRegistry | None) -> BlockRegistry:
    """Return *registry* if provided, else build and scan a fresh one.

    The helpers expose ``registry`` as a kwarg primarily for tests
    (which build an isolated, hand-populated registry) and for hot-path
    callers that already maintain one. The on-demand path performs a
    full scan (entry-points + drop-ins) — acceptable for the
    AppBlock once-per-session prepare/restore workflow.
    """
    if registry is not None:
        return registry
    reg = BlockRegistry()
    reg.scan()
    return reg


def _default_extension_for(obj: DataObject, registry: BlockRegistry) -> str | None:
    """Pick the first declared extension from any saver accepting *type(obj)*.

    Returns ``None`` if no saver matches *type(obj)* or every matching
    saver has an empty :attr:`supported_extensions` map. Iterates in
    registration order so the first saver registered for a given type
    wins (matches the disambiguation policy in
    :meth:`BlockRegistry.find_saver`).
    """
    savers = registry.find_io_blocks_for_type(type(obj), direction="output")
    for saver_cls in savers:
        exts: dict[str, str] = getattr(saver_cls, "supported_extensions", {}) or {}
        if exts:
            # ``dict.keys()`` is insertion-ordered in Python 3.7+; the
            # first-registered extension on the first matching saver
            # is the canonical default.
            return next(iter(exts.keys()))
    return None


def _resolve_core_type_param(obj_or_target: type | DataObject) -> str | None:
    """Return the ``core_type`` enum name for the LoadData/SaveData config.

    Both ``LoadData`` and ``SaveData`` require a ``core_type`` config
    field whose value is one of the six core-type enum strings
    (``"Array"``, ``"DataFrame"``, ``"Series"``, ``"Text"``,
    ``"Artifact"``, ``"CompositeData"``). This helper maps a
    :class:`DataObject` instance or :class:`DataObject` subclass to
    the matching enum string by walking the MRO.

    Returns ``None`` if no MRO entry matches a known core-type name,
    which is the signal to skip the ``core_type`` kwarg entirely (used
    when the resolved IO block is a plugin saver/loader that doesn't
    declare ``core_type`` in its config schema).
    """
    core_type_names = {"Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"}
    cls = obj_or_target if isinstance(obj_or_target, type) else type(obj_or_target)
    for base in cls.__mro__:
        if base.__name__ in core_type_names:
            return base.__name__
    return None


def _try_pass_through(
    obj: DataObject,
    dest: Path,
    extension: str,
) -> bool:
    """Attempt to link *dest* to ``obj.storage_ref.path``.

    Returns ``True`` when the link was created successfully (the caller
    can skip the saver round-trip), ``False`` otherwise. Failures are
    intentionally swallowed at DEBUG level — the saver round-trip is
    always a correct fallback.
    """
    ref = getattr(obj, "storage_ref", None)
    if ref is None:
        return False
    src_path_raw = getattr(ref, "path", None)
    if not src_path_raw:
        return False

    src_path = Path(str(src_path_raw))
    if not src_path.exists():
        return False

    # Only pass through when the source's trailing suffix matches the
    # requested extension (case-insensitive). This avoids handing the
    # caller a file with the wrong on-disk format (e.g. linking a .zarr
    # store under a .parquet extension).
    target_ext = extension.lower()
    src_suffix = src_path.suffix.lower()
    if src_suffix != target_ext:
        return False

    from scieasy.utils.fs import mount_pathlike

    try:
        mount_pathlike(src_path, dest)
    except (OSError, FileExistsError) as exc:
        _logger.debug(
            "materialise_to_file: pass-through link %s -> %s failed (%s); falling back to saver round-trip.",
            dest,
            src_path,
            exc,
        )
        return False
    return True


def _format_supported_savers(obj: DataObject, registry: BlockRegistry) -> str:
    """Return a human-readable list of (saver-name, supported_extensions).

    Used to build informative error messages when no saver matches the
    requested extension.
    """
    savers = registry.find_io_blocks_for_type(type(obj), direction="output")
    if not savers:
        return f"(no saver registered for {type(obj).__name__})"
    parts: list[str] = []
    for cls in savers:
        exts = sorted((getattr(cls, "supported_extensions", {}) or {}).keys())
        parts.append(f"{cls.__name__}={exts}")
    return ", ".join(parts)


def materialise_to_file(
    obj: DataObject,
    dest_dir: Path,
    extension: str | None = None,
    *,
    filename_stem: str = "data",
    registry: BlockRegistry | None = None,
) -> Path:
    """Materialise *obj* to a file under *dest_dir* and return the path.

    Resolution policy (in order):

    1. If *extension* is ``None``, pick the first extension declared by
       the first saver that accepts ``type(obj)`` (see
       :func:`_default_extension_for`). When no saver matches, a
       :class:`LookupError` is raised.
    2. Compute the destination as ``dest_dir / f"{filename_stem}{extension}"``.
    3. If ``obj.storage_ref.path`` already references a file whose
       trailing suffix matches *extension*, link the source into
       *dest* via :func:`scieasy.utils.fs.mount_pathlike`. On any link
       failure (e.g. cross-volume hardlink, junction refused), fall
       through to step 4.
    4. Resolve the saver via :meth:`BlockRegistry.find_saver`,
       instantiate it (passing ``core_type`` for the dynamic-port
       ``SaveData`` block when applicable), call ``saver.save(obj,
       config)`` directly. The saver writes to the computed path.

    Args:
        obj: The :class:`DataObject` to write.
        dest_dir: Directory that will contain the materialised file.
            Created if it does not exist.
        extension: Optional target file extension (e.g. ``".csv"``).
            When omitted the helper picks a saver-declared default.
        filename_stem: Stem of the destination filename. Default
            ``"data"``. Callers that need stable names (e.g. AppBlock
            file-exchange) should pass the port name here.
        registry: Optional pre-scanned :class:`BlockRegistry`. When
            omitted, the helper builds and scans a fresh one.

    Returns:
        The :class:`Path` of the written file.

    Raises:
        LookupError: when no saver is registered for ``(type(obj),
            extension)``.
        Exception: any exception raised by the saver itself is
            propagated to the caller (the saver contract is the source
            of truth for write failures).
    """
    reg = _get_registry(registry)

    if extension is None:
        chosen_ext = _default_extension_for(obj, reg)
        if chosen_ext is None:
            raise LookupError(
                f"materialise_to_file: no default extension available — no saver "
                f"registered for {type(obj).__name__}. Pass extension= explicitly "
                f"or register a saver."
            )
        extension = chosen_ext

    if not extension.startswith("."):
        extension = "." + extension

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{filename_stem}{extension}"

    # Pass-through optimisation: if obj already lives on disk in the
    # right format, link instead of rewrite.
    if _try_pass_through(obj, dest, extension):
        return dest

    saver_cls = reg.find_saver(type(obj), extension)
    # Dynamic-port fallback (symmetric with reconstruct_from_file): the
    # core ``SaveData`` declares ``input_ports[0].accepted_types=[DataObject]``
    # and resolves the concrete type per-instance from ``config['core_type']``.
    # ``find_saver`` uses the contravariant direction (dtype IS-A
    # accepted), so it would already return ``SaveData`` for any
    # DataObject-derived type — but plugin savers with a more specific
    # accepted-types declaration still win on specificity, which is the
    # intended behavior.
    if saver_cls is None:
        raise LookupError(
            f"materialise_to_file: no saver matches "
            f"({type(obj).__name__}, {extension!r}). "
            f"Registered savers for {type(obj).__name__}: "
            f"{_format_supported_savers(obj, reg)}."
        )

    config_params: dict[str, object] = {"path": str(dest)}
    core_type = _resolve_core_type_param(obj)
    # Only inject ``core_type`` when the saver's schema declares it
    # (LoadData / SaveData). Plugin savers without that field still
    # receive the path-only config.
    schema = getattr(saver_cls, "config_schema", {}) or {}
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if core_type is not None and "core_type" in props:
        config_params["core_type"] = core_type

    saver = saver_cls(config={"params": config_params})
    config = BlockConfig(params=config_params)
    saver.save(obj, config)
    return dest


def reconstruct_from_file(
    path: Path,
    target_type: type[DataObject],
    extension: str | None = None,
    *,
    registry: BlockRegistry | None = None,
) -> DataObject:
    """Build a *target_type* instance from *path*.

    Resolution policy (in order):

    1. If *extension* is ``None``, derive it from the path's trailing
       suffix (compound-aware, mirroring
       :meth:`IOBlock._detect_format`).
    2. Resolve the loader via :meth:`BlockRegistry.find_loader`. If a
       loader matches, instantiate and call
       ``loader.load(config, output_dir="")``. If the loader returns a
       single-item :class:`Collection` (the standard ``IOBlock.run``
       wrapper), unwrap it.
    3. If no loader matches AND *target_type* IS-A
       :class:`scieasy.core.types.artifact.Artifact`, build an
       ``Artifact(file_path=path, mime_type=None, description=path.name)``
       as a documented fallback.
    4. Otherwise, raise :class:`LookupError`.

    Args:
        path: File path to load.
        target_type: Concrete :class:`DataObject` subclass to construct.
        extension: Optional extension override (e.g. ``".ome.tif"``).
            When omitted, derived from *path*.
        registry: Optional pre-scanned :class:`BlockRegistry`.

    Returns:
        The constructed :class:`DataObject`.

    Raises:
        FileNotFoundError: if *path* does not exist.
        LookupError: if no loader matches and the Artifact fallback
            does not apply.
    """
    if not path.exists():
        raise FileNotFoundError(f"reconstruct_from_file: source not found: {path}")

    reg = _get_registry(registry)

    # Build the list of extension candidates to try, longest-first, to
    # mirror :meth:`IOBlock._detect_format` (compound-suffix-first lookup
    # with case-insensitive comparison). This matters for filenames with
    # extra dots: ``sample.v1.csv`` produces candidates ``[".v1.csv",
    # ".csv"]`` so a ``.csv`` loader is reached even when ``.v1.csv``
    # has no registered handler.
    extension_candidates: list[str]
    if extension is not None:
        if not extension.startswith("."):
            extension = "." + extension
        extension_candidates = [extension.lower()]
    else:
        suffixes = [s.lower() for s in path.suffixes]
        extension_candidates = []
        for start in range(len(suffixes)):
            candidate = "".join(suffixes[start:])
            if candidate:
                extension_candidates.append(candidate)
        if not extension_candidates:
            extension_candidates = [""]

    # Walk candidates longest-first. For each:
    #   First pass: exact type match (loader's output IS-A target_type).
    #   Second pass: dynamic-port fallback (find_loader(DataObject, ext))
    #     when the candidate loader's config_schema declares ``core_type``
    #     and ``target_type`` resolves to a known core-type enum value.
    # The first candidate that resolves a loader wins; on no match across
    # all candidates, ``loader_cls`` stays ``None`` and the Artifact /
    # LookupError branches below take over. The chosen extension is
    # captured for downstream error messages and ``config["path"]`` is
    # always the original *path*.
    loader_cls: type | None = None
    resolved_extension: str = extension_candidates[0]
    for cand in extension_candidates:
        if not cand:
            continue
        first_pass = reg.find_loader(target_type, cand)
        if first_pass is not None:
            loader_cls = first_pass
            resolved_extension = cand
            break
        if target_type is not DataObject:
            candidate_cls = reg.find_loader(DataObject, cand)
            if candidate_cls is not None:
                schema = getattr(candidate_cls, "config_schema", {}) or {}
                props = schema.get("properties", {}) if isinstance(schema, dict) else {}
                if "core_type" in props and _resolve_core_type_param(target_type) is not None:
                    loader_cls = candidate_cls
                    resolved_extension = cand
                    break
    extension = resolved_extension

    if loader_cls is not None:
        config_params: dict[str, object] = {"path": str(path)}
        core_type = _resolve_core_type_param(target_type)
        schema = getattr(loader_cls, "config_schema", {}) or {}
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if core_type is not None and "core_type" in props:
            config_params["core_type"] = core_type

        loader = loader_cls(config={"params": config_params})
        config = BlockConfig(params=config_params)
        result = loader.load(config, output_dir="")
        # Unwrap single-item Collection (IOBlock.run packs single objects
        # into a Collection for the runtime; load() can return either).
        if isinstance(result, Collection):
            if len(result) == 0:
                raise LookupError(
                    f"reconstruct_from_file: loader {loader_cls.__name__} returned an empty Collection for {path}."
                )
            if len(result) == 1:
                only = result[0]
                assert isinstance(only, DataObject)
                return only
            # Multi-item collection — caller asked for a single typed
            # object; surfacing a Collection here would silently widen
            # the contract. Raise so the caller can decide.
            raise LookupError(
                f"reconstruct_from_file: loader {loader_cls.__name__} returned a "
                f"{len(result)}-item Collection for {path}; expected a single "
                f"{target_type.__name__} instance."
            )
        assert isinstance(result, DataObject)
        return result

    # Artifact fallback: if no loader matched but the caller is OK with
    # an opaque file blob, return one.
    if issubclass(target_type, Artifact):
        return Artifact(
            file_path=path,
            mime_type=None,
            description=path.name,
        )

    raise LookupError(
        f"reconstruct_from_file: no loader matches "
        f"({target_type.__name__}, {extension!r}) and {target_type.__name__} "
        f"is not an Artifact subclass — cannot fall back to opaque-blob construction."
    )
