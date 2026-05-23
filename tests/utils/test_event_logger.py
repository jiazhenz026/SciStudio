"""Tests for :mod:`scistudio.utils.event_logger` (#827).

Validates that ``install_event_logger``:

* subscribes a single callback per event type defined in
  :mod:`scistudio.engine.events`;
* produces one ``scistudio.events`` log record per emitted event with
  the structured ``extra`` fields described in the module docstring;
* sanitises ``EngineEvent.data`` payloads — long strings are truncated
  and numpy / pyarrow / pandas objects are replaced with a type
  marker;
* is idempotent: a second install on the same bus does not double-log.
"""

from __future__ import annotations

import asyncio
import logging

from scistudio.engine import events as events_module
from scistudio.engine.events import EngineEvent, EventBus
from scistudio.utils.event_logger import (
    LOGGER_NAME,
    _all_event_types,
    install_event_logger,
)


def _emit(bus: EventBus, event: EngineEvent) -> None:
    asyncio.run(bus.emit(event))


def test_discovers_all_event_type_constants() -> None:
    """Every uppercase ``str`` constant in ``engine.events`` is enumerated."""
    discovered = set(_all_event_types())
    # Spot-check a few of the well-known constants from ADR-017/018.
    assert events_module.BLOCK_RUNNING in discovered
    assert events_module.BLOCK_DONE in discovered
    assert events_module.PROCESS_SPAWNED in discovered
    assert events_module.WORKFLOW_STARTED in discovered
    assert events_module.INTERACTIVE_PROMPT in discovered
    assert events_module.WORKFLOW_CHANGED in discovered

    # The list is de-duplicated.
    assert len(discovered) == len(_all_event_types())


def test_install_subscribes_to_every_event_type() -> None:
    """One subscriber is registered per event type defined in engine.events."""
    bus = EventBus()
    assert install_event_logger(bus) is True

    for event_type in _all_event_types():
        assert len(bus._subscribers[event_type]) == 1, event_type


def test_logs_event_with_structured_extras(caplog: logging.LogCaptureFixture) -> None:
    """Each emitted event lands as one ``scistudio.events`` record."""
    bus = EventBus()
    install_event_logger(bus)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _emit(
            bus,
            EngineEvent(
                event_type=events_module.BLOCK_RUNNING,
                block_id="load_csv_1",
                data={"workflow_id": "wf-abc", "config": {"path": "data.csv"}},
            ),
        )

    matching = [r for r in caplog.records if r.name == LOGGER_NAME]
    assert len(matching) == 1
    record = matching[0]

    assert record.levelno == logging.INFO
    # Structured extras are present and unwrapped.
    assert record.event_type == events_module.BLOCK_RUNNING
    assert record.block_id == "load_csv_1"
    assert record.workflow_id == "wf-abc"
    sanitised = record.event_data
    assert isinstance(sanitised, dict)
    assert sanitised["workflow_id"] == "wf-abc"
    assert sanitised["config"] == {"path": "data.csv"}


def test_truncates_long_string_payloads(caplog: logging.LogCaptureFixture) -> None:
    """Stringified payloads longer than the truncation limit are replaced."""
    bus = EventBus()
    install_event_logger(bus)

    long_value = "x" * 5000
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _emit(
            bus,
            EngineEvent(
                event_type=events_module.BLOCK_DONE,
                block_id="b",
                data={"big": long_value},
            ),
        )

    record = next(r for r in caplog.records if r.name == LOGGER_NAME)
    sanitised = record.event_data
    assert isinstance(sanitised["big"], str)
    assert sanitised["big"].startswith("<truncated")
    # The raw payload never appears in the formatted message either.
    assert long_value not in record.getMessage()


def test_drops_numpy_payload_with_type_marker(caplog: logging.LogCaptureFixture) -> None:
    """Numpy arrays are not serialised — only the shape marker is logged."""
    np = _try_import_numpy()
    if np is None:
        # No numpy in this environment — test still exercises the fallback
        # branch by injecting a stand-in that mimics the module name +
        # ``.shape`` attribute the sanitiser keys on.
        class _FakeNDArray:
            __module__ = "numpy"
            shape = (3, 4)

        payload: object = _FakeNDArray()
        expected_shape = (3, 4)
    else:
        payload = np.zeros((3, 4))
        expected_shape = (3, 4)

    bus = EventBus()
    install_event_logger(bus)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _emit(
            bus,
            EngineEvent(
                event_type=events_module.BLOCK_DONE,
                block_id="b",
                data={"arr": payload},
            ),
        )

    record = next(r for r in caplog.records if r.name == LOGGER_NAME)
    sanitised = record.event_data
    rendered = sanitised["arr"]
    assert isinstance(rendered, str)
    assert rendered.startswith("<")
    assert str(expected_shape) in rendered


def test_install_is_idempotent() -> None:
    """A second install on the same bus is a silent no-op."""
    bus = EventBus()
    assert install_event_logger(bus) is True
    assert install_event_logger(bus) is False

    # Subscriber count is unchanged after the second install.
    for event_type in _all_event_types():
        assert len(bus._subscribers[event_type]) == 1, event_type


def test_runtime_emits_to_audit_logger(caplog: logging.LogCaptureFixture) -> None:
    """``ApiRuntime`` wires the audit logger in via ``__init__``.

    Smoke check that the production wire-up (in ``api.runtime``) lands
    the audit subscriber on the live event bus, not just in unit
    isolation.
    """
    from scistudio.api.runtime import ApiRuntime

    runtime = ApiRuntime()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _emit(
            runtime.event_bus,
            EngineEvent(
                event_type=events_module.WORKFLOW_STARTED,
                block_id=None,
                data={"workflow_id": "wf-runtime-smoke"},
            ),
        )

    matching = [
        r for r in caplog.records if r.name == LOGGER_NAME and getattr(r, "workflow_id", None) == "wf-runtime-smoke"
    ]
    assert len(matching) == 1


def _try_import_numpy() -> object | None:
    try:
        import numpy

        return numpy
    except ImportError:
        return None
