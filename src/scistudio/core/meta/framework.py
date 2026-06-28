"""Framework-managed, immutable metadata slot for every ``DataObject``.

This is the ``framework`` slot the framework fills in when it builds a
``DataObject``. It is read-only from a block author's point of view; the
fields trace where the object came from and give it a stable identity:

- ``created_at``  — when the object was first built (UTC)
- ``object_id``   — stable identifier used to join lineage records
- ``source``      — free-form origin description (e.g. a file path)
- ``lineage_id``  — link to the block execution that produced the object
- ``derived_from`` — the parent object's ``object_id`` when this is a slice

Block authors read these fields but never write them. Updating user metadata
goes through ``DataObject.with_meta()``; the framework regenerates this slot
when it produces a derived object.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from scistudio.stability import internal, stable


@stable(since="0.3.1")
class FrameworkMeta(BaseModel):
    """Framework-managed metadata, filled in when a ``DataObject`` is built.

    Block authors do not write these fields directly. The framework sets them
    when it constructs a new ``DataObject`` or derives one (for example when
    slicing or iterating over an array). The model is frozen, so an accidental
    write raises a ``ValidationError`` instead of silently mutating shared
    state. The fields are validated and JSON-round-tripped automatically when
    an object is sent to or from a worker subprocess.

    Example:
        >>> meta = FrameworkMeta(source="raw.tif")
        >>> meta.source
        'raw.tif'
        >>> meta.derived_from is None
        True
    """

    model_config = ConfigDict(frozen=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    """UTC timestamp of when the object was constructed."""
    object_id: str = Field(default_factory=lambda: uuid4().hex)
    """Unique identifier (UUIDv4 hex) for this ``DataObject`` instance, used to join lineage records."""
    source: str = ""
    """Free-form origin description (e.g. a file path or block name); ``""`` when no specific source is known."""
    lineage_id: str | None = None
    """Identifier of the block execution that produced this object, or ``None`` when it was built outside a run (e.g. in a test)."""
    derived_from: str | None = None
    """Parent object's ``object_id`` when this object is a slice/derivation, else ``None``."""

    @internal()
    def derive(self, **changes: Any) -> FrameworkMeta:
        """Return a new ``FrameworkMeta`` for a derived object.

        ADR-027 D5 propagation rule: derived slices get a fresh
        ``object_id``, a fresh ``created_at``, and ``derived_from`` set
        to the parent's ``object_id``. Other fields (``source``,
        ``lineage_id``) are inherited unless explicitly overridden via
        ``changes``.

        Used by ``Array.sel()``, ``Array.iter_over()``, and
        ``iterate_over_axes()`` (T-006, T-011) to keep lineage hints
        consistent across derivations.

        Args:
            **changes: Optional field overrides applied after the
                propagation defaults. Any of ``created_at``,
                ``object_id``, ``source``, ``lineage_id``, or
                ``derived_from`` may be overridden.

        Returns:
            A new ``FrameworkMeta`` instance. The original is unchanged
            (the model is frozen).

        Example:
            >>> parent = FrameworkMeta(source="raw.tif")
            >>> child = parent.derive()
            >>> child.derived_from == parent.object_id
            True
            >>> child.source == parent.source
            True
            >>> child.object_id != parent.object_id
            True
        """
        return type(self)(
            created_at=changes.pop("created_at", datetime.now(UTC)),
            object_id=changes.pop("object_id", uuid4().hex),
            source=changes.pop("source", self.source),
            lineage_id=changes.pop("lineage_id", self.lineage_id),
            derived_from=changes.pop("derived_from", self.object_id),
            **changes,
        )

    @internal()
    def with_lineage_id(self, lineage_id: str) -> FrameworkMeta:
        """Return a copy of this ``FrameworkMeta`` with ``lineage_id`` set.

        Per ADR-038 §3.2 / ADR-027 D5 the framework slot's ``lineage_id``
        field is a foreign key into the unified ``lineage.db`` —
        specifically the ``block_executions.block_execution_id`` that
        produced this DataObject.

        Block authors do NOT call this helper. It is the engine's
        post-execution stamping surface: the scheduler / lineage recorder
        invokes it when materialising ``data_objects`` rows so the
        persisted ``wire_payload`` carries the lineage join key. Because
        :class:`FrameworkMeta` is ``frozen=True`` per ADR-027 D5, all
        identity / provenance fields (``object_id``, ``derived_from``,
        ``created_at``, ``source``) are preserved verbatim on the copy.

        Phase D38-2.3 introduces this helper. The corresponding scheduler
        wiring that calls it end-to-end is tracked separately because it
        requires aligning the ``LineageRecorder.block_execution_id``
        allocation site with ADR §3.2 (today the recorder allocates the
        id at terminal-event time; per the ADR the scheduler should
        allocate it pre-dispatch and propagate). See #929 escalation
        comment for the cross-phase boundary.

        Args:
            lineage_id: The ``block_execution_id`` to stamp.

        Returns:
            A new ``FrameworkMeta`` with ``lineage_id`` set to the
            supplied value and every other field unchanged.

        Example:
            >>> fm = FrameworkMeta(source="raw.tif")
            >>> stamped = fm.with_lineage_id("be-abc123")
            >>> stamped.lineage_id
            'be-abc123'
            >>> stamped.object_id == fm.object_id
            True
        """
        # Pydantic v2 model_copy preserves immutability and re-validates
        # the supplied override. ``deep=False`` is correct: every field is
        # a scalar / datetime — no nested mutable structure to copy.
        return cast("FrameworkMeta", self.model_copy(update={"lineage_id": lineage_id}))
