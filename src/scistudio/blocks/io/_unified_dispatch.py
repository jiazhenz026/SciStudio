"""Runtime helpers for ADR-043 unified Load/Save dispatch.

Core ``Load`` / ``Save`` remain the user-facing blocks. When their selected
capability belongs to a package IO block, these helpers resolve and invoke the
owning block while preserving the stable core block surface in workflow YAML.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.core.types.base import DataObject


def _scan_runtime_registry(
    registry: Any, *, project_child: str, home_child: str, scan_method: str, always_home: bool
) -> Any:
    """Apply runtime project/user scan paths and execute the requested scan."""
    project_dir = os.environ.get("SCISTUDIO_PROJECT_DIR")
    if project_dir:
        registry.add_scan_dir(Path(project_dir) / project_child)
    if always_home or project_dir:
        registry.add_scan_dir(Path.home() / ".scistudio" / home_child)
    getattr(registry, scan_method)()
    return registry


def runtime_block_registry() -> Any:
    """Build a registry that mirrors API/worker project scan locations."""
    from scistudio.blocks.registry import BlockRegistry

    return _scan_runtime_registry(
        BlockRegistry(), project_child="blocks", home_child="blocks", scan_method="scan", always_home=False
    )


def runtime_type_registry() -> Any:
    """Build a type registry that includes core, package, and custom types."""
    from scistudio.core.types.registry import TypeRegistry

    return _scan_runtime_registry(
        TypeRegistry(), project_child="types", home_child="types", scan_method="scan_all", always_home=True
    )


def resolve_type_class(type_name: str) -> type[DataObject] | None:
    """Resolve a registered ``DataObject`` subclass by display name."""
    try:
        cls = runtime_type_registry().load_class(type_name)
    except Exception:
        return None
    if isinstance(cls, type) and issubclass(cls, DataObject):
        return cls
    return None


def capability_by_id(registry: Any, capability_id: str, *, direction: str) -> FormatCapability | None:
    """Return a registered capability by stable id and direction."""
    for capability in registry.list_format_capabilities(direction=direction):
        if capability.id == capability_id:
            return cast(FormatCapability, capability)
    return None


def capability_owner_class(registry: Any, capability: FormatCapability) -> type[Any]:
    """Load the block class that owns ``capability``."""
    block_cls = registry._resolve_capability_class(capability)
    if block_cls is None:
        raise LookupError(
            f"IO capability {capability.id!r} resolved but owner {capability.block_type!r} could not be imported."
        )
    return cast(type[Any], block_cls)


def _path_extension(params: dict[str, Any]) -> str | None:
    """Infer the lookup extension from the ``path`` and/or ``filename`` config.

    The core Save block exposes ``path`` as a *directory* browser, so the
    filename and its extension are entered in the separate ``filename`` field
    (see :class:`SaveData.config_schema`). Capability selection for a
    package-registered multi-format type (e.g. ``Image`` → tiff/zarr/png/jpeg)
    is driven by this extension, so a folder ``path`` plus ``filename="foo.tiff"``
    must still infer ``.tiff``. ``path`` is consulted first (a concrete file path
    wins), then ``filename`` as a fallback. Returning ``None`` here leaves the
    saver/loader lookup without a discriminator; the callers turn the resulting
    ambiguity into an actionable error rather than a misleading "no capability
    registered" message.
    """
    raw_path = params.get("path")
    paths = raw_path if isinstance(raw_path, list) else [raw_path]
    candidates = [*paths, params.get("filename")]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            suffixes = Path(candidate).suffixes
            if suffixes:
                return "".join(suffixes)
    return None


def selected_capability(
    *,
    direction: str,
    params: dict[str, Any],
    data_type: type[DataObject] | None,
) -> tuple[Any, FormatCapability | None]:
    """Resolve the selected capability from ``capability_id`` or path/type."""
    registry = runtime_block_registry()
    raw_id = params.get("capability_id")
    capability_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None
    if capability_id:
        return registry, capability_by_id(registry, capability_id, direction=direction)

    if data_type is None:
        return registry, None
    extension = _path_extension(params)
    finder = registry.find_loader_capability if direction == "load" else registry.find_saver_capability
    from scistudio.blocks.registry import AmbiguousCapabilityError

    try:
        return registry, finder(data_type, extension)
    except AmbiguousCapabilityError as exc:
        # A multi-format type with neither an explicit format/capability nor a
        # filename extension to disambiguate. For SAVE, honour the type's
        # declared default format so the user only has to type a filename and
        # accept (or change) the format shown in the Save block's Format
        # dropdown — the chosen format's extension is appended downstream. Pick
        # the FIRST ``is_default=True`` candidate to mirror the frontend dropdown
        # default (``capabilities.find(c => c.is_default)`` in
        # ``FormatCapabilityConfig``), keeping backend and UI in agreement.
        # Package types (e.g. imaging ``Image`` -> tiff) declare a default; core
        # IO types declare none (all ``is_default=False``), so they still surface
        # the actionable "choose a format" error below rather than the runtime
        # guessing a columnar/binary format on the user's behalf.
        if direction == "save":
            default = next((cap for cap in exc.candidates if getattr(cap, "is_default", False)), None)
            if default is not None:
                return registry, default
        # No single default to fall back on: propagate so the caller can render
        # an actionable "choose a format / add a file extension" error instead
        # of swallowing this into the misleading "no capability is registered"
        # fallback.
        raise
    except Exception:
        return registry, None


def _ambiguous_capability_message(*, direction: str, core_type: str, exc: Any) -> str:
    """Build an actionable error when a multi-format type selects no unique IO format.

    ``exc`` is an ``AmbiguousCapabilityError`` carrying the candidate
    capabilities. The user reached here because the type (e.g. ``Image``) has
    several registered formats and neither a file extension nor an explicit
    format was supplied. Tell them how to disambiguate instead of claiming the
    type has no save/load capability.
    """
    extensions = sorted({ext for cap in getattr(exc, "candidates", ()) for ext in (cap.extensions or ())})
    if extensions:
        detail = f"include a file extension ({', '.join(extensions)})"
    else:
        formats = sorted({cap.format_id for cap in getattr(exc, "candidates", ()) if cap.format_id})
        detail = f"select a format ({', '.join(formats)})" if formats else "select a format"
    if direction == "save":
        return (
            f"Save: cannot determine the output format for type {core_type!r}: it supports "
            f"multiple save formats and none was selected. Set the Save block's path or filename to "
            f"{detail}, or choose a save format explicitly."
        )
    return (
        f"Load: cannot determine the input format for type {core_type!r}: it supports "
        f"multiple load formats and none was selected. Set the Load block's path to "
        f"{detail}, or choose a load format explicitly."
    )


def delegate_params(params: dict[str, Any], capability: FormatCapability) -> dict[str, Any]:
    """Build config params for the package IO block behind a core proxy."""
    delegated = {key: value for key, value in params.items() if key != "core_type"}
    delegated["capability_id"] = capability.id
    delegated["format_id"] = capability.format_id
    delegated.setdefault("format", capability.format_id)
    return delegated


def _default_delegated_filename(data_type: type[DataObject], capability: FormatCapability) -> str | None:
    if not capability.extensions:
        return None
    return f"{data_type.__name__.lower()}{capability.extensions[0]}"


def _filename_with_extension(name: str, capability: FormatCapability) -> str:
    if not capability.extensions:
        return name
    path = Path(name)
    supported = {extension.lower() for extension in capability.extensions}
    if path.suffix.lower() in supported:
        return path.name
    stem = path.stem if path.suffix else path.name
    return f"{stem}{capability.extensions[0]}"


def _delegated_filename(
    params: dict[str, Any],
    *,
    obj: DataObject,
    data_type: type[DataObject],
    capability: FormatCapability,
) -> str:
    # Reuse the canonical filename helpers from the saver capability module
    # instead of maintaining near-identical private copies here (ADR-028
    # Addendum 1 §C9 "prefer existing helpers"; dedups the semantic-dup
    # clusters that copies of these two functions otherwise create).
    from scistudio.blocks.io.savers._capability import _filename_config, _source_filename

    configured = _filename_config(params)
    if configured is not None:
        return _filename_with_extension(configured, capability)
    source_name = _source_filename(obj)
    if source_name:
        return _filename_with_extension(source_name, capability)
    default = _default_delegated_filename(data_type, capability)
    if default is not None and not Path(str(params.get("path", ""))).is_dir():
        return default
    raise ValueError(
        "SaveData cannot infer an output filename because the input object has no source filename. "
        "Set the Save block filename field."
    )


def _resolve_delegated_save_path(
    params: dict[str, Any],
    *,
    obj: DataObject,
    data_type: type[DataObject],
    capability: FormatCapability,
) -> None:
    raw_path = params.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return
    path = Path(raw_path)
    original_path = path
    if path.is_dir():
        path = path / _delegated_filename(params, obj=obj, data_type=data_type, capability=capability)
    elif not path.suffix and capability.extensions:
        path = path.with_suffix(capability.extensions[0])
    if path != original_path:
        params["path"] = str(path)
    if path.exists() and not bool(params.get("overwrite", False)):
        raise ValueError(
            f"SaveData refuses to overwrite existing output {str(path)!r}. Choose an empty folder or a new output path."
        )


@contextmanager
def _activated_package_import_roots() -> Iterator[None]:
    """Activate installed package import roots around a delegated IO call.

    The engine worker that runs a *core* ``Load`` / ``Save`` block does not carry
    the delegated package's import roots: ``engine/runners/local.py`` ``_worker_env``
    strips plugin paths from ``PYTHONPATH`` and the core block's
    ``runtime_import_roots`` are empty. The package *module* is importable only
    because block discovery cached it in ``sys.modules`` under a scoped
    ``prepended_sys_paths`` that is then reverted — so any *lazy* third-party
    import inside the package loader/saver (e.g. the ``tifffile`` import in the
    imaging ``LoadImage`` loader) runs a fresh import at call time, finds the
    plugin ``site-packages`` missing from ``sys.path``, and raises
    ``ModuleNotFoundError``. Re-activate the installed package roots (each
    plugin's ``src`` + ``site-packages``) for the duration of the delegated
    call so those deferred imports resolve. Best-effort and a no-op outside the
    desktop/bundled layout, where the plugin deps are already importable.
    """
    try:
        from scistudio.desktop.paths import installed_package_import_roots, prepended_sys_paths

        roots = list(installed_package_import_roots())
    except Exception:
        yield
        return
    if not roots:
        yield
        return
    with prepended_sys_paths(roots):
        yield


def _effective_params(config: BlockConfig) -> dict[str, Any]:
    """Return the block's effective params, merging Pydantic *extra* fields.

    The engine worker constructs ``BlockConfig(**config)``
    (``engine/runners/worker.py`` ``main``), so the user/runtime config
    (``path``, ``core_type``, ``format``, ``capability_id``, …) lands in
    Pydantic *extra* fields rather than in ``params``. Reading
    ``config.params`` directly therefore sees an empty dict and breaks package
    IO capability selection: with no ``path`` there is no extension, so
    :func:`selected_capability` matches no format capability and core ``Load`` /
    ``Save`` of a package-registered type fails with "no load/save capability is
    registered for type ...". Mirror :meth:`BlockConfig.get` (#565) by merging
    the extras with explicit ``params`` (explicit ``params`` wins on conflict).
    """
    extras = getattr(config, "__pydantic_extra__", None) or {}
    merged: dict[str, Any] = dict(extras)
    merged.update(config.params or {})
    return merged


def delegate_load(
    *,
    config: BlockConfig,
    output_dir: str,
    core_type: str,
) -> DataObject:
    """Load through the package block selected by a core Load capability."""
    from scistudio.blocks.registry import AmbiguousCapabilityError

    data_type = resolve_type_class(core_type)
    effective = _effective_params(config)
    try:
        registry, capability = selected_capability(direction="load", params=effective, data_type=data_type)
    except AmbiguousCapabilityError as exc:
        raise ValueError(_ambiguous_capability_message(direction="load", core_type=core_type, exc=exc)) from exc
    if capability is None:
        raise ValueError(f"Load: no load capability is registered for type {core_type!r}.")
    if capability.block_type == "LoadData":
        raise ValueError(f"Load: selected capability {capability.id!r} did not resolve to a package loader.")
    loader_cls = capability_owner_class(registry, capability)
    params = delegate_params(effective, capability)
    loader = loader_cls(config={"params": params})
    with _activated_package_import_roots():
        return cast(DataObject, loader.load(BlockConfig(params=params), output_dir))


def delegate_save(
    *,
    obj: DataObject,
    config: BlockConfig,
    core_type: str,
) -> None:
    """Save through the package block selected by a core Save capability."""
    from scistudio.blocks.registry import AmbiguousCapabilityError

    data_type = resolve_type_class(core_type) or type(obj)
    effective = _effective_params(config)
    try:
        registry, capability = selected_capability(direction="save", params=effective, data_type=data_type)
    except AmbiguousCapabilityError as exc:
        raise ValueError(_ambiguous_capability_message(direction="save", core_type=core_type, exc=exc)) from exc
    if capability is None:
        raise ValueError(f"Save: no save capability is registered for type {core_type!r}.")
    if capability.block_type == "SaveData":
        raise ValueError(f"Save: selected capability {capability.id!r} did not resolve to a package saver.")
    saver_cls = capability_owner_class(registry, capability)
    params = delegate_params(effective, capability)
    _resolve_delegated_save_path(params, obj=obj, data_type=data_type, capability=capability)
    if params.get("path") != effective.get("path"):
        config.params["path"] = params["path"]
    saver = saver_cls(config={"params": params})
    with _activated_package_import_roots():
        saver.save(obj, BlockConfig(params=params))
