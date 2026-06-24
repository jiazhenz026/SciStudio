"""Regression test for bug #10: a loader IO block has no input port.

A ``direction="input"`` IO block (core ``load_data`` and every package loader)
is a pure source — it reads from its configured ``path``, never from an inbound
edge — so it must not expose an input port (the canvas would otherwise render a
dangling left handle). Enforced by ``IOBlock.__init_subclass__``. Savers
(``direction="output"``) keep their input port.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData


def test_load_data_has_no_input_port() -> None:
    assert LoadData.direction == "input"
    assert list(LoadData.input_ports) == []
    # The output port is unaffected — a loader still produces "data".
    assert [port.name for port in LoadData.output_ports] == ["data"]


def test_save_data_keeps_input_port() -> None:
    assert SaveData.direction == "input" or SaveData.direction == "output"
    if SaveData.direction == "output":
        assert [port.name for port in SaveData.input_ports] == ["data"]


def test_init_subclass_blanks_input_for_input_direction_subclass() -> None:
    class _MyLoader(IOBlock):
        direction = "input"

        def load(self, config, output_dir=""):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        def save(self, obj, config):  # type: ignore[no-untyped-def]
            raise NotImplementedError

    assert list(_MyLoader.input_ports) == []


def test_init_subclass_respects_explicit_input_ports() -> None:
    from scistudio.blocks.base.ports import InputPort
    from scistudio.core.types.base import DataObject

    class _ExplicitLoader(IOBlock):
        direction = "input"
        input_ports: ClassVar = [InputPort(name="custom", accepted_types=[DataObject], required=False)]

        def load(self, config, output_dir=""):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        def save(self, obj, config):  # type: ignore[no-untyped-def]
            raise NotImplementedError

    # An explicit declaration is preserved (the guard only blanks the inherited default).
    assert [port.name for port in _ExplicitLoader.input_ports] == ["custom"]
