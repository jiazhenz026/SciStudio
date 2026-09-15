"""Regression tests for #1063 — scaffold template port-spec API drift.

The scaffold once emitted ``type=DataObject`` / ``type=<T>`` for ``InputPort`` /
``OutputPort`` constructor calls, but the live ``Port`` dataclass takes
``accepted_types: list[type]``. Blocks scaffolded in that shape raised
``TypeError`` at registry-load time.

Since #2384 the ports are rendered by the shared starter-template renderer
(``scistudio.blocks._templates.render``), so the regression is pinned there.
"""

from __future__ import annotations

from scistudio.blocks._templates.render import PortStub, StarterSpec, render_starter


def _render(input_ports: tuple[PortStub, ...], output_ports: tuple[PortStub, ...]) -> str:
    spec = StarterSpec(
        class_name="Probe", label="Probe", description="d", input_ports=input_ports, output_ports=output_ports
    )
    return render_starter("basic", spec)


def test_rendered_ports_use_accepted_types() -> None:
    """Declared ports → accepted_types=[T] (not type=T)."""
    rendered = _render((PortStub("in1", "DataObject", "first"), PortStub("in2", "Array", "second")), ())
    assert "accepted_types=[DataObject]" in rendered
    assert "accepted_types=[Array]" in rendered
    assert "type=DataObject" not in rendered
    assert "type=Array" not in rendered


def test_rendered_empty_port_list_is_an_empty_list() -> None:
    """An explicitly empty side renders ``= []`` rather than a stale commented shape."""
    rendered = _render((PortStub("in1", "Array", "first"),), ())
    assert "output_ports: ClassVar[list[OutputPort]] = []" in rendered
    assert "type=DataObject" not in rendered


def test_rendered_port_carries_its_description() -> None:
    """A port description is rendered as the ``description=`` keyword users see in the GUI."""
    rendered = _render((PortStub("in1", "Array", "primary input"),), ())
    assert 'description="primary input"' in rendered
