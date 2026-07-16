"""Port, InputPort, OutputPort — typed connection endpoints on blocks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from scistudio.core.types.base import TypeSignature, same_registered_type
from scistudio.stability import stable


@dataclass(kw_only=True)
class Port:
    """Shared base for block connection endpoints.

    Internal (ADR-052 §4.3): authors declare ports with :class:`InputPort` /
    :class:`OutputPort`; ``Port`` is the shared field carrier and is not part of
    the public ``scistudio.blocks.base`` surface.
    """

    name: str
    accepted_types: list[type]
    is_collection: bool = False
    description: str = ""
    required: bool = True


@stable(since="0.3.1")
@dataclass(kw_only=True)
class InputPort(Port):
    """A typed input connection point on a block.

    Declare one per named input your block reads. The workflow editor uses the
    accepted types to decide which upstream outputs may connect here, and the
    runtime uses them (plus the optional constraint) to validate incoming data
    before the block runs.

    Set these fields when constructing a port:

    - ``name`` — the port's identifier and the key your block looks up in the
      ``inputs`` mapping passed to :meth:`Block.run`.
    - ``accepted_types`` — the data types this port accepts; an empty list means
      "accept any data object".
    - ``description`` — a short human-readable explanation shown in the editor.
    - ``required`` — whether a connection is mandatory (defaults to ``True``).
    - ``is_collection`` — whether the port expects a multi-item collection.

    Example:
        >>> from scistudio.blocks.base import InputPort
        >>> port = InputPort(name="image", accepted_types=[], required=True)
    """

    default: Any | None = None
    """Value used when nothing is connected; lets a required port stay optional."""

    constraint: Callable[[Any], bool] | None = None
    """Optional check run on the incoming value; return ``False`` to reject it."""

    constraint_description: str = ""
    """Message shown to the user when :attr:`constraint` rejects a value."""


@stable(since="0.3.1")
@dataclass(kw_only=True)
class OutputPort(Port):
    """A typed output connection point on a block.

    Declare one per named output your block produces. The key you use for each
    value in the mapping returned by :meth:`Block.run` must match an output
    port's ``name``. The workflow editor uses the accepted types to decide which
    downstream inputs this output may connect to.

    Set these fields when constructing a port:

    - ``name`` — the port's identifier and the key your block writes in the
      mapping returned by :meth:`Block.run`.
    - ``accepted_types`` — the data types this port emits; an empty list means
      "may emit any data object".
    - ``description`` — a short human-readable explanation shown in the editor.

    Example:
        >>> from scistudio.blocks.base import OutputPort
        >>> port = OutputPort(name="result", accepted_types=[])
    """


def port_accepts_type(port: Port, data_type: type | Any) -> bool:
    """Check whether *port* accepts *data_type* (isinstance-based, inheritance-aware).

    Returns ``True`` if *data_type* is a subclass of any type listed in
    ``port.accepted_types``.  An empty ``accepted_types`` list means the port
    accepts anything.

    ADR-020-Add6: If *data_type* is a Collection **instance**, checks its
    ``item_type`` against the port's accepted types.  The Collection wrapper
    is transparent to the port system.  Callers should pass the Collection
    instance directly (not ``type(collection)``).

    A by-path-imported class with a distinct identity but the same registered
    name is treated as compatible via :func:`same_registered_type`, so runtime
    validation matches what the static workflow validator accepts.
    """
    if not port.accepted_types:
        return True

    # ADR-020: Collection transparency — check item_type, not Collection class.
    from scistudio.core.types.collection import Collection

    if isinstance(data_type, Collection):
        item_type = data_type.item_type
        return any(issubclass(item_type, t) or same_registered_type(item_type, t) for t in port.accepted_types)

    return any(issubclass(data_type, t) or same_registered_type(data_type, t) for t in port.accepted_types)


def port_accepts_signature(port: Port, signature: TypeSignature) -> bool:
    """Check whether *port* accepts a :class:`TypeSignature`.

    Builds the signature for each accepted type and checks if the incoming
    signature matches (i.e. is a subtype of) at least one of them.

    Internal (ADR-052 §4.3): framework helper, not part of the public surface.

    TODO(#1817): dead code (0 call sites) — keep-or-delete tracked under #1817.
      Out of scope per ADR-052 §4.3 (demote-only this PR).
      Followup: https://github.com/jiazhenz026/SciStudio/issues/1817.
    """
    if not port.accepted_types:
        return True
    for accepted in port.accepted_types:
        accepted_sig = TypeSignature.from_type(accepted)
        if signature.matches(accepted_sig):
            return True
    return False


def validate_port_constraint(port: InputPort, value: Any) -> tuple[bool, str]:
    """Validate *value* against the input port's constraint function.

    ADR-020: *value* is a :class:`Collection` (not an individual DataObject).
    Constraint functions should iterate over the Collection if they need
    per-item checks::

        constraint=lambda col: all(
            item.axes is not None and {"y", "x"}.issubset(set(item.axes))
            for item in col
        )

    Returns ``(True, "")`` if valid or no constraint is set.
    Returns ``(False, description)`` on constraint failure.
    """
    if port.constraint is None:
        return True, ""
    try:
        result = port.constraint(value)
    except Exception as exc:
        return False, f"Constraint raised {type(exc).__name__}: {exc}"
    if not result:
        return False, port.constraint_description or "Constraint not satisfied"
    return True, ""


def ports_from_config_dicts(
    dicts: list[dict[str, Any]],
    direction: str,
) -> list[InputPort] | list[OutputPort]:
    """Convert a list of port config dicts to InputPort or OutputPort instances.

    Each dict must have the shape ``{"name": str, "types": list[str]}``.
    Type name strings are resolved against the core type registry; unknown
    names fall back to ``DataObject``.  Port names must be unique within
    *dicts* — duplicates are silently de-duplicated (last wins).

    ADR-029 D1: variadic port lists stored in block config use this format.
    """
    from scistudio.core.types.base import DataObject

    def _resolve_type(name: str) -> type:
        try:
            from scistudio.core.types.serialization import _get_type_registry

            reg = _get_type_registry()
            return reg.load_class(name)
        except Exception:
            pass
        return DataObject

    seen: dict[str, None] = {}
    result: list[Any] = []
    for item in dicts:
        port_name = str(item.get("name", "port"))
        if port_name in seen:
            continue
        seen[port_name] = None
        raw_types: list[str] = item.get("types", [])
        accepted: list[type] = [_resolve_type(t) for t in raw_types] if raw_types else [DataObject]
        if direction == "input":
            result.append(InputPort(name=port_name, accepted_types=accepted))
        else:
            result.append(OutputPort(name=port_name, accepted_types=accepted))
    return result  # type: ignore[return-value]


def validate_connection(
    source_port: OutputPort,
    target_port: InputPort,
) -> tuple[bool, str]:
    """Check whether an edge from *source_port* to *target_port* is type-compatible.

    Returns ``(True, "")`` if at least one type produced by the source is
    accepted by the target.  Returns ``(False, reason)`` otherwise.
    """
    if not source_port.accepted_types:
        # Source can produce anything — always compatible.
        return True, ""
    if not target_port.accepted_types:
        # Target accepts anything — always compatible.
        return True, ""

    for src_type in source_port.accepted_types:
        if any(
            issubclass(src_type, tgt_type) or issubclass(tgt_type, src_type) for tgt_type in target_port.accepted_types
        ):
            return True, ""

    src_names = [t.__name__ for t in source_port.accepted_types]
    tgt_names = [t.__name__ for t in target_port.accepted_types]
    return False, (
        f"Source port '{source_port.name}' produces {src_names} but "
        f"target port '{target_port.name}' accepts {tgt_names}"
    )
