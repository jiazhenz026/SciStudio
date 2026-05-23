"""Capability registry helpers (ADR-043) for :class:`BlockRegistry`.

Per ADR-047 §C9: this module hosts only module-level private helpers — it
must contain **zero** ``class`` definitions. The :class:`BlockRegistry`
class and its 5 error subclasses live in ``__init__.py``.

Owns:

- ``_iter_capability_specs`` — iteration helper over (capability, spec) pairs.
- ``list_format_capabilities`` — filtered enumeration of registered capabilities.
- ``find_loader_capability`` / ``find_saver_capability`` — explicit-failure
  ADR-043 lookups (raise on miss / ambiguity).
- ``_find_format_capability`` — shared core for the two finders.
- ``_capability_satisfies_query`` — capability-id verification helper.
- ``_resolve_capability_class`` / ``_resolve_first_capability_class`` —
  reach the block class behind a capability (mtime-aware re-import).
- ``_resolve_class`` — generic spec → class re-import.
- ``_validate_dynamic_ports`` — ADR-028 Addendum 1 shape check.
- ``_format_capabilities_from_class`` — ADR-043 class-level descriptor
  extraction (used by ``_spec._spec_from_class``).

Module-level utilities:

- ``_iter_compound_to_single_suffix`` — compound→single extension fallback chain.
- ``_exact_ext_in_mapping`` / ``_ext_in_mapping`` — extension membership tests.
- ``_capability_matches_type`` / ``_capability_type_specificity`` — IS-A and
  specificity helpers used in candidate ranking.
- ``_capability_error_message`` — diagnostic-string builder.
- ``_validate_capability_id`` — package-qualified id syntax check.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from scistudio.blocks.io.capabilities import CapabilityDirection, FormatCapability, normalize_extension
from scistudio.core.types.base import DataObject, TypeSignature

if TYPE_CHECKING:
    from scistudio.blocks.registry import BlockRegistry, BlockSpec

logger = logging.getLogger(__name__)


def _iter_compound_to_single_suffix(extension: str) -> list[str]:
    """Return the compound-to-single suffix chain for *extension*.

    Mirrors :meth:`IOBlock._detect_format`'s probe order so registry
    extension lookups agree with IO-block format detection. The chain
    walks from the longest compound form down to the trailing single
    suffix. Examples (case-preserving — caller is expected to lower-case
    once before calling):

    * ``".ome.tif"`` -> ``[".ome.tif", ".tif"]``
    * ``".foo.bar.baz"`` -> ``[".foo.bar.baz", ".bar.baz", ".baz"]``
    * ``".tif"`` -> ``[".tif"]``
    * ``"tif"`` -> ``[".tif"]`` (leading dot is normalized).

    Returns an empty list when *extension* is empty.
    """
    if not extension:
        return []
    normalized = extension if extension.startswith(".") else f".{extension}"
    parts = normalized.split(".")
    # ``".ome.tif"`` -> ``["", "ome", "tif"]``; skip the leading empty so
    # ``start`` indexes the first real suffix component.
    chain: list[str] = []
    for start in range(1, len(parts)):
        chain.append("." + ".".join(parts[start:]))
    return chain


def _exact_ext_in_mapping(extension_lower: str, mapping: dict[str, str]) -> bool:
    """Case-insensitive exact-match check for ``supported_extensions``.

    Accepts both forms ``".tif"`` and ``"tif"`` for *extension_lower``
    (leading dot normalized). Used by candidate-set extension matching
    inside compound-to-single suffix walks.
    """
    if not mapping:
        return False
    candidate = extension_lower if extension_lower.startswith(".") else f".{extension_lower}"
    return any(candidate == key.lower() for key in mapping)


def _ext_in_mapping(extension_lower: str, mapping: dict[str, str]) -> bool:
    """Backward-compatible membership check including compound-to-single fallback.

    Kept for callers that only need a boolean "does this extension reach
    any declared key (exact or compound-fallback)?" check. Registry-internal
    dispatch should use :func:`_exact_ext_in_mapping` inside an outer loop
    over :func:`_iter_compound_to_single_suffix` so the
    "longest declared suffix wins" tie-break stays deterministic.
    """
    if not mapping:
        return False
    return any(
        _exact_ext_in_mapping(candidate, mapping) for candidate in _iter_compound_to_single_suffix(extension_lower)
    )


def _capability_matches_type(
    capability: FormatCapability,
    data_type: type[DataObject],
    direction: CapabilityDirection,
) -> bool:
    try:
        capability_signature = TypeSignature.from_type(capability.data_type)
        query_signature = TypeSignature.from_type(data_type)
    except Exception:
        return False

    if direction == "load":
        return capability_signature.matches(query_signature)
    return query_signature.matches(capability_signature)


def _capability_type_specificity(capability: FormatCapability) -> int:
    try:
        return len(TypeSignature.from_type(capability.data_type).type_chain)
    except Exception:
        return 0


def _capability_error_message(
    prefix: str,
    *,
    direction: CapabilityDirection,
    data_type: type[DataObject],
    extension: str | None = None,
    format_id: str | None = None,
    capability_id: str | None = None,
    candidates: tuple[FormatCapability, ...] = (),
) -> str:
    candidate_ids = ", ".join(candidate.id for candidate in candidates) if candidates else "none"
    return (
        f"{prefix}: direction={direction!r}, data_type={data_type.__name__!r}, "
        f"extension={extension!r}, format_id={format_id!r}, capability_id={capability_id!r}, "
        f"candidates=[{candidate_ids}]"
    )


def _validate_capability_id(capability: FormatCapability) -> None:
    from scistudio.blocks.registry import CapabilityRegistrationError

    parts = capability.id.split(".")
    if len(parts) < 3 or any(not part for part in parts):
        raise CapabilityRegistrationError(f"Capability id {capability.id!r} must be stable and package-qualified.")
    if any(char.isspace() for char in capability.id):
        raise CapabilityRegistrationError(f"Capability id {capability.id!r} must not contain whitespace.")


def _format_capabilities_from_class(cls: type) -> list[FormatCapability]:
    from scistudio.blocks.io.io_block import IOBlock
    from scistudio.blocks.registry import CapabilityRegistrationError
    from scistudio.blocks.registry._spec import _validate_class_capability, _validate_simple_extension_declaration

    if not issubclass(cls, IOBlock):
        return []

    _validate_simple_extension_declaration(cls)
    capabilities = list(cls.get_format_capabilities())
    for capability in capabilities:
        if not isinstance(capability, FormatCapability):
            raise CapabilityRegistrationError(
                f"{cls.__name__}.get_format_capabilities() returned {type(capability).__name__}, "
                "expected FormatCapability."
            )
        _validate_class_capability(cls, capability)
    return capabilities


# ---------------------------------------------------------------------------
# Capability lookup helpers operating on a :class:`BlockRegistry` instance.
# ---------------------------------------------------------------------------


def _iter_capability_specs(registry: BlockRegistry) -> list[tuple[FormatCapability, BlockSpec]]:
    """Return capability/spec pairs in registry insertion order."""
    return [(capability, spec) for spec in registry._registry.values() for capability in spec.format_capabilities]


def _validate_dynamic_ports(cls: type) -> None:
    """Validate the shape of ``cls.dynamic_ports`` per ADR-028 Addendum 1.

    Called at scan time so malformed declarations fail loudly at import.
    Accepts ``None`` (the default) and any dict that matches::

        {
            "source_config_key": str,
            # Exactly one of the following two keys must be present.
            # ``output_port_mapping`` is used by input-direction blocks
            # (LoadData) and ``input_port_mapping`` by output-direction
            # blocks (SaveData). The shape of the value is identical.
            "output_port_mapping": {
                "<port_name>": {
                    "<enum_value>": ["<TypeName>", ...],
                    ...
                },
                ...
            },
            # OR
            "input_port_mapping": {
                "<port_name>": {
                    "<enum_value>": ["<TypeName>", ...],
                    ...
                },
                ...
            },
        }

    Raises ``ValueError`` with the offending class name and field path
    when the shape is wrong.

    T-TRK-008 (SaveData) note: the ``input_port_mapping`` variant was
    added in this ticket per ADR-028 Addendum 1 §C5/§C9. T-TRK-006
    (PR #321) only declared the ``output_port_mapping`` variant
    because LoadData (T-TRK-007) was the first consumer; SaveData is
    the symmetric output-direction consumer and uses the
    ``input_port_mapping`` key. The frontend
    ``computeEffectivePorts`` helper in T-TRK-009 must handle both
    keys.
    """
    descriptor = getattr(cls, "dynamic_ports", None)
    if descriptor is None:
        return

    cls_name = cls.__name__
    if not isinstance(descriptor, dict):
        raise ValueError(f"{cls_name}.dynamic_ports must be a dict or None, got {type(descriptor).__name__}")

    if "source_config_key" not in descriptor:
        raise ValueError(f"{cls_name}.dynamic_ports is missing required key 'source_config_key'")
    source_key = descriptor["source_config_key"]
    if not isinstance(source_key, str) or not source_key:
        raise ValueError(
            f"{cls_name}.dynamic_ports['source_config_key'] must be a non-empty string, got {type(source_key).__name__}"
        )

    # Exactly one of ``output_port_mapping`` or ``input_port_mapping``
    # must be present. Per ADR-028 Addendum 1 §C5: input-direction
    # blocks (LoadData) drive output ports from a config enum, and
    # output-direction blocks (SaveData) drive input ports from a
    # config enum. Both use the same nested-dict shape.
    has_output = "output_port_mapping" in descriptor
    has_input = "input_port_mapping" in descriptor
    if not has_output and not has_input:
        raise ValueError(
            f"{cls_name}.dynamic_ports is missing required key 'output_port_mapping' or 'input_port_mapping'"
        )
    if has_output and has_input:
        raise ValueError(
            f"{cls_name}.dynamic_ports must declare exactly one of "
            "'output_port_mapping' or 'input_port_mapping', not both"
        )
    mapping_key = "output_port_mapping" if has_output else "input_port_mapping"
    mapping = descriptor[mapping_key]
    if not isinstance(mapping, dict):
        raise ValueError(f"{cls_name}.dynamic_ports[{mapping_key!r}] must be a dict, got {type(mapping).__name__}")

    for port_name, enum_map in mapping.items():
        if not isinstance(port_name, str) or not port_name:
            raise ValueError(
                f"{cls_name}.dynamic_ports[{mapping_key!r}] keys must be non-empty strings, got {port_name!r}"
            )
        if not isinstance(enum_map, dict):
            raise ValueError(
                f"{cls_name}.dynamic_ports[{mapping_key!r}][{port_name!r}] must be a dict, "
                f"got {type(enum_map).__name__}"
            )
        for enum_value, type_names in enum_map.items():
            if not isinstance(enum_value, str) or not enum_value:
                raise ValueError(
                    f"{cls_name}.dynamic_ports[{mapping_key!r}][{port_name!r}] keys must be "
                    f"non-empty strings, got {enum_value!r}"
                )
            if not isinstance(type_names, list):
                raise ValueError(
                    f"{cls_name}.dynamic_ports[{mapping_key!r}][{port_name!r}][{enum_value!r}] "
                    f"must be a list, got {type(type_names).__name__}"
                )
            for type_name in type_names:
                if not isinstance(type_name, str) or not type_name:
                    raise ValueError(
                        f"{cls_name}.dynamic_ports[{mapping_key!r}][{port_name!r}][{enum_value!r}] "
                        f"entries must be non-empty strings, got {type_name!r}"
                    )


def _resolve_class(spec: BlockSpec) -> type | None:
    """Load the class referenced by *spec*. Returns ``None`` on import failure.

    Mirrors :meth:`BlockRegistry.instantiate`'s import path (mtime-keyed
    reload for Tier-1 drop-ins, normal ``import_module`` otherwise) but
    does **not** instantiate the class — query methods only need the
    ClassVars (``supported_extensions``, ports). On any import or
    attribute error the method returns ``None`` so a single bad
    plugin does not break dispatch for the rest.
    """
    try:
        if spec.file_path:
            path = Path(spec.file_path)
            mtime = path.stat().st_mtime
            mod_name = f"_scistudio_dropin_{path.stem}_{int(mtime)}"
            mod_spec = importlib.util.spec_from_file_location(mod_name, path)
            if mod_spec is None or mod_spec.loader is None:
                return None
            module = importlib.util.module_from_spec(mod_spec)
            mod_spec.loader.exec_module(module)
        else:
            module = importlib.import_module(spec.module_path)
        cls = getattr(module, spec.class_name, None)
        return cls if isinstance(cls, type) else None
    except Exception:
        logger.debug(
            "registry.find_*: class import failed for %s.%s",
            spec.module_path,
            spec.class_name,
            exc_info=True,
        )
        return None


def _resolve_capability_class(registry: BlockRegistry, capability: FormatCapability) -> type | None:
    for candidate, spec in _iter_capability_specs(registry):
        if candidate.id == capability.id:
            return _resolve_class(spec)
    return None


def _resolve_first_capability_class(
    registry: BlockRegistry,
    capabilities: tuple[FormatCapability, ...],
) -> type | None:
    candidate_ids = {capability.id for capability in capabilities}
    for capability, spec in _iter_capability_specs(registry):
        if capability.id not in candidate_ids:
            continue
        cls = _resolve_class(spec)
        if cls is not None:
            return cls
    return None


def list_format_capabilities(
    registry: BlockRegistry,
    *,
    direction: CapabilityDirection | None = None,
    data_type: type[DataObject] | None = None,
    extension: str | None = None,
    format_id: str | None = None,
) -> list[FormatCapability]:
    """List registered ADR-043 IO format capabilities matching filters."""
    normalized_extension = normalize_extension(extension) if extension else None
    normalized_format_id = format_id.strip().lower() if format_id else None

    # Filter by every dimension EXCEPT extension first, then handle
    # the compound-to-single fallback at the candidate-set level
    # so a compound-specific registration wins over a single-suffix
    # one when both apply (ADR-028 §D8 + ``IOBlock._detect_format``).
    non_extension_filtered: list[FormatCapability] = []
    for capability, _spec in _iter_capability_specs(registry):
        if direction is not None and capability.direction != direction:
            continue
        if normalized_format_id is not None and capability.format_id != normalized_format_id:
            continue
        if data_type is not None and not _capability_matches_type(
            capability,
            data_type,
            capability.direction,
        ):
            continue
        non_extension_filtered.append(capability)

    if normalized_extension is None:
        return non_extension_filtered
    # Walk compound→single; return the candidates whose extensions
    # contain the longest matching suffix. ``_detect_format`` returns
    # the first match; the registry's caller wants the candidate set
    # for ambiguity / specificity resolution, so we collect all
    # capabilities matching the FIRST non-empty suffix length.
    for candidate_ext in _iter_compound_to_single_suffix(normalized_extension):
        matched = [cap for cap in non_extension_filtered if candidate_ext in cap.extensions]
        if matched:
            return matched
    return []


def find_loader_capability(
    registry: BlockRegistry,
    data_type: type[DataObject],
    extension: str | None = None,
    *,
    format_id: str | None = None,
    capability_id: str | None = None,
) -> FormatCapability:
    """Resolve a load capability without falling back to registration order."""
    return _find_format_capability(
        registry,
        direction="load",
        data_type=data_type,
        extension=extension,
        format_id=format_id,
        capability_id=capability_id,
    )


def find_saver_capability(
    registry: BlockRegistry,
    data_type: type[DataObject],
    extension: str | None = None,
    *,
    format_id: str | None = None,
    capability_id: str | None = None,
) -> FormatCapability:
    """Resolve a save capability without falling back to registration order."""
    return _find_format_capability(
        registry,
        direction="save",
        data_type=data_type,
        extension=extension,
        format_id=format_id,
        capability_id=capability_id,
    )


def _find_format_capability(
    registry: BlockRegistry,
    *,
    direction: CapabilityDirection,
    data_type: type[DataObject],
    extension: str | None,
    format_id: str | None,
    capability_id: str | None,
) -> FormatCapability:
    from scistudio.blocks.registry import AmbiguousCapabilityError, MissingCapabilityError

    normalized_extension = normalize_extension(extension) if extension else None
    normalized_format_id = format_id.strip().lower() if format_id else None

    if capability_id is not None:
        for capability, _spec in _iter_capability_specs(registry):
            if capability.id != capability_id:
                continue
            if _capability_satisfies_query(
                capability,
                direction=direction,
                data_type=data_type,
                extension=normalized_extension,
                format_id=normalized_format_id,
            ):
                return capability
            raise MissingCapabilityError(
                _capability_error_message(
                    "Capability id exists but does not satisfy the requested IO contract",
                    direction=direction,
                    data_type=data_type,
                    extension=normalized_extension,
                    format_id=normalized_format_id,
                    capability_id=capability_id,
                    candidates=(capability,),
                ),
                direction=direction,
                data_type=data_type,
                extension=normalized_extension,
                format_id=normalized_format_id,
                capability_id=capability_id,
                candidates=(capability,),
            )
        raise MissingCapabilityError(
            _capability_error_message(
                "No IO format capability matches capability_id",
                direction=direction,
                data_type=data_type,
                extension=normalized_extension,
                format_id=normalized_format_id,
                capability_id=capability_id,
            ),
            direction=direction,
            data_type=data_type,
            extension=normalized_extension,
            format_id=normalized_format_id,
            capability_id=capability_id,
        )

    candidates = tuple(
        capability
        for capability in list_format_capabilities(
            registry,
            direction=direction,
            data_type=data_type,
            extension=normalized_extension,
            format_id=normalized_format_id,
        )
    )
    if not candidates:
        raise MissingCapabilityError(
            _capability_error_message(
                "No IO format capability matches the requested contract",
                direction=direction,
                data_type=data_type,
                extension=normalized_extension,
                format_id=normalized_format_id,
            ),
            direction=direction,
            data_type=data_type,
            extension=normalized_extension,
            format_id=normalized_format_id,
        )
    if len(candidates) == 1:
        return candidates[0]

    default_candidates = tuple(candidate for candidate in candidates if candidate.is_default)
    if len(default_candidates) == 1:
        return default_candidates[0]
    ranked_candidates = default_candidates or candidates

    max_specificity = max(_capability_type_specificity(candidate) for candidate in ranked_candidates)
    most_specific = tuple(
        candidate for candidate in ranked_candidates if _capability_type_specificity(candidate) == max_specificity
    )
    if len(most_specific) == 1:
        return most_specific[0]

    max_priority = max(candidate.priority for candidate in most_specific)
    highest_priority = tuple(candidate for candidate in most_specific if candidate.priority == max_priority)
    if len(highest_priority) == 1:
        return highest_priority[0]

    raise AmbiguousCapabilityError(
        _capability_error_message(
            "Ambiguous IO format capability lookup",
            direction=direction,
            data_type=data_type,
            extension=normalized_extension,
            format_id=normalized_format_id,
            candidates=highest_priority,
        ),
        direction=direction,
        data_type=data_type,
        extension=normalized_extension,
        format_id=normalized_format_id,
        candidates=highest_priority,
    )


def _capability_satisfies_query(
    capability: FormatCapability,
    *,
    direction: CapabilityDirection,
    data_type: type[DataObject],
    extension: str | None,
    format_id: str | None,
) -> bool:
    if capability.direction != direction:
        return False
    if extension is not None:
        # ADR-028 §D8: a compound query like ``.ome.tif`` satisfies a
        # capability declaring only ``.tif`` (compound-to-single
        # fallback). Used only when the caller passed an explicit
        # ``capability_id`` and we're verifying that capability — not
        # selecting among many — so a simple membership-style suffix
        # walk is the right shape here.
        capability_extensions = set(capability.extensions)
        if not any(candidate in capability_extensions for candidate in _iter_compound_to_single_suffix(extension)):
            return False
    if format_id is not None and capability.format_id != format_id:
        return False
    return _capability_matches_type(capability, data_type, direction)


__all__ = [
    "_capability_error_message",
    "_capability_matches_type",
    "_capability_satisfies_query",
    "_capability_type_specificity",
    "_exact_ext_in_mapping",
    "_ext_in_mapping",
    "_find_format_capability",
    "_format_capabilities_from_class",
    "_iter_capability_specs",
    "_iter_compound_to_single_suffix",
    "_resolve_capability_class",
    "_resolve_class",
    "_resolve_first_capability_class",
    "_validate_capability_id",
    "_validate_dynamic_ports",
    "find_loader_capability",
    "find_saver_capability",
    "list_format_capabilities",
]
