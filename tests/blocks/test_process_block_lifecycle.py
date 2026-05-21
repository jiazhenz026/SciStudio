"""Tests for ProcessBlock setup/teardown lifecycle hooks (T-009, ADR-027 D7).

Coverage mirrors the acceptance criteria in
``docs/specs/phase10-implementation-standards.md`` §T-009 (h):

- ``setup`` is called once before iteration and returns opaque state.
- ``teardown`` is called once after iteration in a ``finally`` block.
- ``state`` is threaded from ``setup`` through every ``process_item`` call
  to ``teardown``.
- Defaults: ``setup`` returns ``None``; ``teardown`` is a no-op.
- Backward compatibility: pre-T-009 two-arg ``process_item(self, item, config)``
  overrides keep working via ``_process_item_takes_state`` introspection in
  ``run()``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.storage.flush_context import clear, set_output_dir
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


@pytest.fixture(autouse=True)
def _flush_context(tmp_path):
    """ADR-031 Addendum 1: auto_flush now hard-gates on output_dir."""
    set_output_dir(str(tmp_path))
    yield
    clear()


# ---------------------------------------------------------------------------
# Test fixtures — tracking ProcessBlock subclasses
# ---------------------------------------------------------------------------


class _TrackingProcessBlock(ProcessBlock):
    """ProcessBlock that records setup/teardown/process_item calls."""

    name: ClassVar[str] = "Tracking Process Block"
    algorithm: ClassVar[str] = "tracking"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="input"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="output"),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.setup_count: int = 0
        self.teardown_count: int = 0
        self.process_item_count: int = 0
        self.last_state_seen_in_teardown: Any = "<never called>"
        self.states_seen_in_process_item: list[Any] = []
        self.setup_config_seen: BlockConfig | None = None
        self.setup_was_before_process_item: bool | None = None

    def setup(self, config: BlockConfig) -> Any:
        self.setup_count += 1
        self.setup_config_seen = config
        # Record that setup ran while process_item had not yet been called.
        self.setup_was_before_process_item = self.process_item_count == 0
        return {"sentinel": "abc", "created_at": self.setup_count}

    def teardown(self, state: Any) -> None:
        self.teardown_count += 1
        self.last_state_seen_in_teardown = state

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        self.process_item_count += 1
        self.states_seen_in_process_item.append(state)
        return item


class _RaisingProcessBlock(ProcessBlock):
    """Subclass whose ``process_item`` raises, to test the ``finally`` path."""

    name: ClassVar[str] = "Raising Process Block"
    algorithm: ClassVar[str] = "raising"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="input"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="output"),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.teardown_count: int = 0
        self.teardown_state: Any = "<never called>"

    def setup(self, config: BlockConfig) -> Any:
        return {"resource": "open"}

    def teardown(self, state: Any) -> None:
        self.teardown_count += 1
        self.teardown_state = state

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        raise RuntimeError("deliberate failure in process_item")


class _LegacyTwoArgProcessBlock(ProcessBlock):
    """Pre-T-009 subclass: overrides ``process_item`` with only two args.

    Regression guard — ``ProcessBlock.run`` must detect the signature and
    call the override with 2 positional args instead of 3.
    """

    name: ClassVar[str] = "Legacy 2-arg Process Block"
    algorithm: ClassVar[str] = "legacy_two_arg"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="input"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="output"),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.calls: int = 0

    def process_item(self, item: Any, config: BlockConfig) -> Any:  # type: ignore[override]
        self.calls += 1
        return item


class _DefaultProcessBlock(ProcessBlock):
    """Subclass that does NOT override setup/teardown — exercises defaults."""

    name: ClassVar[str] = "Default Process Block"
    algorithm: ClassVar[str] = "default"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="input"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="output"),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.states_seen: list[Any] = []

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        self.states_seen.append(state)
        return item


def _make_collection(n: int) -> Collection:
    """Build a ``Collection`` of ``n`` bare DataObject instances."""
    items = [DataObject() for _ in range(n)]
    return Collection(items, item_type=DataObject)


# ---------------------------------------------------------------------------
# Default implementations (acceptance: default_setup_returns_none, default_teardown_noop)
# ---------------------------------------------------------------------------


class TestDefaultLifecycleHooks:
    """Verify the default ``setup``/``teardown`` implementations."""

    def test_default_setup_returns_none(self) -> None:
        block = _DefaultProcessBlock()
        assert block.setup(block.config) is None

    def test_default_teardown_is_noop(self) -> None:
        block = _DefaultProcessBlock()
        # Must not raise for any state value, including None.
        block.teardown(None)
        block.teardown({"anything": 1})
        block.teardown(object())

    def test_default_setup_state_is_none_in_process_item(self) -> None:
        """When ``setup`` isn't overridden, ``process_item`` receives state=None."""
        block = _DefaultProcessBlock()
        inputs = {"input": _make_collection(3)}
        block.run(inputs, block.config)
        assert block.states_seen == [None, None, None]


# ---------------------------------------------------------------------------
# setup() call-once semantics (acceptance: setup_called_once_before_iteration)
# ---------------------------------------------------------------------------


class TestSetupLifecycle:
    """``setup`` runs exactly once per ``run()`` and before any iteration."""

    def test_setup_called_once_before_iteration(self) -> None:
        block = _TrackingProcessBlock()
        inputs = {"input": _make_collection(5)}
        block.run(inputs, block.config)
        assert block.setup_count == 1
        assert block.setup_was_before_process_item is True
        assert block.process_item_count == 5

    def test_setup_called_once_for_one_item(self) -> None:
        block = _TrackingProcessBlock()
        inputs = {"input": _make_collection(1)}
        block.run(inputs, block.config)
        assert block.setup_count == 1
        assert block.process_item_count == 1

    def test_setup_receives_config_only(self) -> None:
        """``setup`` must be invoked with the BlockConfig, not with ``inputs``."""
        block = _TrackingProcessBlock()
        inputs = {"input": _make_collection(2)}
        block.run(inputs, block.config)
        assert block.setup_config_seen is block.config


# ---------------------------------------------------------------------------
# state threading (acceptance: state_passed_to_process_item)
# ---------------------------------------------------------------------------


class TestStateThreading:
    """``state`` returned by setup is passed to every process_item + teardown."""

    def test_state_passed_to_every_process_item_call(self) -> None:
        block = _TrackingProcessBlock()
        inputs = {"input": _make_collection(4)}
        block.run(inputs, block.config)

        # All four calls see the identical state object (sentinel + counter).
        assert len(block.states_seen_in_process_item) == 4
        first_state = block.states_seen_in_process_item[0]
        assert first_state == {"sentinel": "abc", "created_at": 1}
        for s in block.states_seen_in_process_item:
            assert s is first_state  # identity: same object threaded through

    def test_teardown_receives_same_state(self) -> None:
        block = _TrackingProcessBlock()
        inputs = {"input": _make_collection(3)}
        block.run(inputs, block.config)
        assert block.teardown_count == 1
        assert block.last_state_seen_in_teardown is block.states_seen_in_process_item[0]


# ---------------------------------------------------------------------------
# teardown() lifecycle (acceptance: teardown_called_once_after, teardown_on_error)
# ---------------------------------------------------------------------------


class TestTeardownLifecycle:
    """``teardown`` runs exactly once, after iteration, even on error."""

    def test_teardown_called_once_after_iteration(self) -> None:
        block = _TrackingProcessBlock()
        inputs = {"input": _make_collection(3)}
        block.run(inputs, block.config)
        assert block.teardown_count == 1

    def test_teardown_called_even_on_process_item_error(self) -> None:
        block = _RaisingProcessBlock()
        inputs = {"input": _make_collection(2)}
        with pytest.raises(RuntimeError, match="deliberate failure"):
            block.run(inputs, block.config)
        # teardown ran exactly once, from the finally block, with the state
        # returned by setup().
        assert block.teardown_count == 1
        assert block.teardown_state == {"resource": "open"}

    def test_teardown_called_when_setup_returns_none(self) -> None:
        """Default ``setup`` returns ``None``; ``teardown`` still receives it."""
        seen: list[Any] = []

        class _Block(_DefaultProcessBlock):
            def teardown(self, state: Any) -> None:
                seen.append(state)

        block = _Block()
        inputs = {"input": _make_collection(2)}
        block.run(inputs, block.config)
        assert seen == [None]


# ---------------------------------------------------------------------------
# Backward compatibility (acceptance: two_arg_process_item_still_works)
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Pre-T-009 two-arg ``process_item`` overrides must continue to work."""

    def test_existing_two_arg_process_item_still_works(self) -> None:
        """``_process_item_takes_state`` detects the legacy arity."""
        block = _LegacyTwoArgProcessBlock()
        assert block._process_item_takes_state() is False
        inputs = {"input": _make_collection(3)}
        result = block.run(inputs, block.config)
        assert block.calls == 3
        assert isinstance(result["output"], Collection)
        assert len(result["output"]) == 3

    def test_new_three_arg_process_item_detected(self) -> None:
        block = _TrackingProcessBlock()
        assert block._process_item_takes_state() is True

    def test_legacy_block_does_not_receive_state(self) -> None:
        """Legacy 2-arg override must not crash even when setup returns a state."""

        class _LegacyWithSetup(_LegacyTwoArgProcessBlock):
            def setup(self, config: BlockConfig) -> Any:
                return "some-state"

        block = _LegacyWithSetup()
        inputs = {"input": _make_collection(2)}
        block.run(inputs, block.config)  # must not raise TypeError
        assert block.calls == 2


# ---------------------------------------------------------------------------
# Non-Collection input fallback path
# ---------------------------------------------------------------------------


class TestNonCollectionInput:
    """The default ``run`` must still honour the lifecycle for non-Collection input."""

    def test_setup_and_teardown_run_for_single_object(self) -> None:
        block = _TrackingProcessBlock()
        inputs = {"input": DataObject()}
        block.run(inputs, block.config)
        assert block.setup_count == 1
        assert block.teardown_count == 1
        assert block.process_item_count == 1
        # State threaded through the single call.
        assert block.states_seen_in_process_item[0] == {"sentinel": "abc", "created_at": 1}
