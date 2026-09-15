"""Render a block starter template with a class name, labels, ports, and imports.

Every template in this package follows one layout, which is what lets a single
file serve the GUI verbatim and the agent's ``scaffold_block`` tool rendered:

- one top-level ``class <Name>(<Base>):`` whose next line is a one-line docstring;
- ``name`` / ``description`` declared as single-line ``ClassVar[str]`` assignments;
- ``input_ports`` / ``output_ports`` / ``config_schema`` statements that either
  fit on one line or close with a line holding only the matching bracket at
  class indentation;
- core data types imported with one ``from scistudio.core.types import (...)``;
- for IO templates, single-line ``output_type`` / ``input_type``,
  ``extensions`` and ``format_id`` assignments;
- the method holding the user's logic, when there is one, as the class's last
  member.

``tests/blocks/test_block_templates.py`` renders every registered kind and
checks the result imports and registers, so a template edit that breaks the
layout fails there.
"""
# Maintainer context (kept outside generated API documentation):
# #2384 — scaffold_block renders the same per-kind files GET /api/blocks/template
# serves. The renderer is pure text: resolving a port type name to an importable
# symbol needs the type registry, which the agent tool owns and passes in.
# Development references: #2384, ADR-036, ADR-040.

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any

from scistudio.blocks._templates import TEMPLATE_KINDS, read_template
from scistudio.core import types as core_types

_INDENT = "    "
_CLASS_RE = re.compile(r"^class (?P<name>\w+)\((?P<base>\w+)\):$")
_CORE_TYPES_IMPORT = "from scistudio.core.types import"


@dataclass(frozen=True)
class PortStub:
    """One port to render; ``type_name`` must be importable in the rendered file."""

    name: str
    type_name: str
    description: str
    required: bool = True
    note: str = ""
    """Optional trailing comment, e.g. the intended type when ``type_name`` is a stand-in."""


@dataclass(frozen=True)
class StarterSpec:
    """What to put into a template.

    ``None`` for a port side keeps the template's own ports and, when both sides
    are ``None``, the template's own worked body.
    """

    class_name: str
    label: str
    description: str
    input_ports: tuple[PortStub, ...] | None = None
    output_ports: tuple[PortStub, ...] | None = None
    core_types: frozenset[str] = frozenset()
    """Names that must be imported from ``scistudio.core.types``."""
    extra_import_lines: tuple[str, ...] = ()
    """Import (or commented import-hint) lines placed after the core types import."""
    extension: str | None = None
    """IO templates: the single file extension the block claims (with the dot)."""
    format_id: str | None = None
    """IO templates: the short format name for the synthesized capability."""
    known_types: frozenset[str] = field(default_factory=frozenset)
    """Core type names the generated IO body may construct or read directly."""


def render_starter(kind: str, spec: StarterSpec) -> str:
    """Return the template for *kind* filled in from *spec*.

    Raises:
        KeyError: if *kind* is not a registered template kind.
        ValueError: if the template does not follow the layout this module expects.
    """
    template = TEMPLATE_KINDS[kind]
    lines = read_template(kind).splitlines()

    class_index = _single_index(lines, lambda line: _CLASS_RE.match(line) is not None, "class statement", kind)
    match = _CLASS_RE.match(lines[class_index])
    assert match is not None  # guarded by _single_index
    lines[class_index] = f"class {spec.class_name}({match.group('base')}):"
    doc_index = class_index + 1
    if not (lines[doc_index].startswith(f'{_INDENT}"""') and lines[doc_index].endswith('"""')):
        raise ValueError(f"template {kind!r}: the class docstring must be one line")
    lines[doc_index] = f"{_INDENT}{_py_docstring(spec.description)}"

    _replace_assignment(lines, "name", f"ClassVar[str] = {_py_str(spec.label)}", kind)
    _replace_assignment(lines, "description", f"ClassVar[str] = {_py_str(spec.description)}", kind)

    ports_overridden = spec.input_ports is not None or spec.output_ports is not None
    if kind == "io_load" and spec.output_ports:
        data_type = spec.output_ports[0].type_name
        _replace_assignment(lines, "output_type", f"ClassVar[type[DataObject]] = {data_type}", kind)
    if kind == "io_save" and spec.input_ports:
        data_type = spec.input_ports[0].type_name
        _replace_assignment(lines, "input_type", f"ClassVar[type[DataObject]] = {data_type}", kind)
    if spec.extension is not None:
        _replace_assignment(lines, "extensions", f"ClassVar[tuple[str, ...]] = ({_py_str(spec.extension)},)", kind)
    if spec.format_id is not None:
        _replace_assignment(lines, "format_id", f"ClassVar[str] = {_py_str(spec.format_id)}", kind)

    if spec.input_ports is not None:
        _replace_ports(lines, "input_ports", "InputPort", spec.input_ports, kind)
    if spec.output_ports is not None:
        _replace_ports(lines, "output_ports", "OutputPort", spec.output_ports, kind)

    if ports_overridden and template.body_method is not None:
        # The template's example parameters are wired into the body being
        # replaced; keeping them would leave inert controls in the GUI.
        _clear_config_schema(lines, kind)
        _replace_body(lines, template.body_method, _body_for(kind, spec), kind)
    else:
        _label_config_schema(lines, kind)

    text = "\n".join(lines).rstrip("\n") + "\n"
    return _rewrite_core_types_import(text, spec, kind)


# ---------------------------------------------------------------------------
# Statement helpers
# ---------------------------------------------------------------------------


def _single_index(lines: list[str], predicate: Any, what: str, kind: str, first: int = 0) -> int:
    found = [index for index in range(first, len(lines)) if predicate(lines[index])]
    if len(found) != 1:
        raise ValueError(f"template {kind!r}: expected exactly one {what}, found {len(found)}")
    return found[0]


def _class_start(lines: list[str]) -> int:
    """Index of the class statement; the teaching header above it is never rewritten."""
    return next((index for index, line in enumerate(lines) if _CLASS_RE.match(line)), len(lines))


def _statement_span(lines: list[str], attr: str, kind: str) -> tuple[int, int] | None:
    """Return the ``[start, end]`` line span of a class-level ``attr: ... =`` statement."""
    prefix = f"{_INDENT}{attr}:"
    starts = [index for index in range(_class_start(lines), len(lines)) if lines[index].startswith(prefix)]
    if not starts:
        return None
    if len(starts) > 1:
        raise ValueError(f"template {kind!r}: {attr} is declared more than once")
    start = starts[0]
    opener = lines[start].rstrip()[-1:]
    closer = {"[": "]", "{": "}", "(": ")"}.get(opener)
    if closer is None:
        return start, start
    for end in range(start + 1, len(lines)):
        if lines[end] == f"{_INDENT}{closer}":
            return start, end
    raise ValueError(f"template {kind!r}: {attr} has no closing {closer!r} line")


def _replace_assignment(lines: list[str], attr: str, annotation_and_value: str, kind: str) -> None:
    span = _statement_span(lines, attr, kind)
    if span is None or span[0] != span[1]:
        raise ValueError(f"template {kind!r}: {attr} must be a single-line class attribute")
    lines[span[0]] = f"{_INDENT}{attr}: {annotation_and_value}"


def _replace_ports(lines: list[str], attr: str, port_class: str, ports: tuple[PortStub, ...], kind: str) -> None:
    span = _statement_span(lines, attr, kind)
    header = f"{_INDENT}{attr}: ClassVar[list[{port_class}]] = ["
    if ports:
        body = [header]
        for port in ports:
            keywords = [f"name={_py_str(port.name)}", f"accepted_types=[{port.type_name}]"]
            if port_class == "InputPort" and not port.required:
                keywords.append("required=False")
            keywords.append(f"description={_py_str(port.description)}")
            note = f"  # {' '.join(port.note.split())}" if port.note else ""
            body.append(f"{_INDENT * 2}{port_class}({', '.join(keywords)}),{note}")
        body.append(f"{_INDENT}]")
    else:
        body = [f"{header}]"]
    if span is None:
        raise ValueError(f"template {kind!r}: {attr} is not declared, so it cannot be rendered")
    lines[span[0] : span[1] + 1] = body


def _label_config_schema(lines: list[str], kind: str) -> None:
    """Give every ``config_schema`` property a ``title`` and a ``description``.

    The GUI parameter panel shows users only these two strings, so a starter
    must never leave them out. A schema that already carries both is left
    untouched, comments included.
    """
    span = _statement_span(lines, "config_schema", kind)
    if span is None:
        return
    start, end = span
    first = lines[start]
    literal = "\n".join([first[first.index("=") + 1 :], *lines[start + 1 : end + 1]])
    try:
        schema = ast.literal_eval(literal.strip())
    except (ValueError, SyntaxError) as exc:
        raise ValueError(f"template {kind!r}: config_schema must be a plain literal") from exc
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    changed = False
    for key, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if "title" not in prop:
            prop["title"] = key.replace("_", " ").strip().title()
            changed = True
        if "description" not in prop:
            prop["description"] = "Describe what this parameter controls, its units, and when to change it."
            changed = True
    if not changed:
        return
    # Keep a stable, readable key order: type, title, description, then the rest.
    for key, prop in list(properties.items()):
        if isinstance(prop, dict):
            ordered = {name: prop[name] for name in ("type", "title", "description") if name in prop}
            ordered.update({name: value for name, value in prop.items() if name not in ordered})
            properties[key] = ordered
    rendered = _py_literal(schema, level=1).splitlines()
    rendered[0] = f"{first[: first.index('=') + 1]} {rendered[0]}"
    lines[start : end + 1] = rendered


def _clear_config_schema(lines: list[str], kind: str) -> None:
    """Replace ``config_schema`` with an empty schema that shows how to add a labelled parameter."""
    span = _statement_span(lines, "config_schema", kind)
    if span is None:
        return
    lines[span[0] : span[1] + 1] = [
        f"{_INDENT}config_schema: ClassVar[dict[str, Any]] = {{",
        f'{_INDENT * 2}"type": "object",',
        f'{_INDENT * 2}"properties": {{',
        f"{_INDENT * 3}# Add one entry per value users may change, and read it with config.get(), e.g.",
        f'{_INDENT * 3}# "threshold": {{"type": "number", "title": "Threshold",',
        f'{_INDENT * 3}#               "description": "Cut-off applied to each value.", "default": 0.5}},',
        f"{_INDENT * 2}}},",
        f"{_INDENT}}}",
    ]


def _replace_body(lines: list[str], method: str, body: list[str], kind: str) -> None:
    start = _single_index(
        lines, lambda line: line.startswith(f"{_INDENT}def {method}("), f"def {method}", kind, _class_start(lines)
    )
    lines[start:] = body


def _rewrite_core_types_import(text: str, spec: StarterSpec, kind: str) -> str:
    """Import every core type the file names, marking unused ones for the linter."""
    pattern = re.compile(
        rf"^{re.escape(_CORE_TYPES_IMPORT)} (?:\((?P<multi>[^)]*)\)|(?P<single>[^\n]+))$",
        re.MULTILINE,
    )
    found = list(pattern.finditer(text))
    if len(found) != 1:
        raise ValueError(f"template {kind!r}: expected one '{_CORE_TYPES_IMPORT}' statement, found {len(found)}")
    match = found[0]
    raw = match.group("multi") if match.group("multi") is not None else match.group("single")
    names = {re.sub(r"#.*", "", part).strip() for part in re.split(r"[,\n]", raw)}
    names.discard("")
    # Usage is judged on the code after the import, ignoring comments, so a type
    # only mentioned in the teaching text still carries its linter note.
    code = "\n".join(line.split("#", 1)[0] for line in text[match.end() :].splitlines())
    names |= set(spec.core_types)
    names |= {name for name in core_types.__all__ if re.search(rf"\b{re.escape(name)}\b", code)}
    rows = []
    for name in sorted(names):
        used = re.search(rf"\b{re.escape(name)}\b", code) is not None
        rows.append(f"{_INDENT}{name},{'' if used else '  # noqa: F401'}")
    replacement = "\n".join([f"{_CORE_TYPES_IMPORT} (", *rows, ")", *spec.extra_import_lines])
    return text[: match.start()] + replacement + text[match.end() :]


# ---------------------------------------------------------------------------
# Port-aware bodies
# ---------------------------------------------------------------------------


def _body_for(kind: str, spec: StarterSpec) -> list[str]:
    if kind == "basic":
        return _block_run_body(spec)
    if kind == "process":
        return _process_item_body(spec)
    if kind == "io_load":
        return _load_file_body(spec)
    if kind == "io_save":
        return _save_file_body(spec)
    raise ValueError(f"template {kind!r} has no body renderer")


def _block_run_body(spec: StarterSpec) -> list[str]:
    inputs = spec.input_ports or ()
    outputs = spec.output_ports or ()
    lines = [
        f"{_INDENT}def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:",
        f"{_INDENT * 2}# >>> EDIT THIS <<<",
        f"{_INDENT * 2}# ``inputs[<port name>]`` is the Collection arriving on that input port. Return",
        f"{_INDENT * 2}# one Collection per output port, keyed by the output port name. The starter",
        f"{_INDENT * 2}# below runs as-is: it passes items straight through where an input port has",
        f"{_INDENT * 2}# the output's type and returns an empty Collection otherwise. Replace it with",
        f"{_INDENT * 2}# your logic; read a parameter with config.get(<name>, <default>). See sections",
        f"{_INDENT * 2}# 3, 5 and 6 of the header for the Collection helpers and worked examples.",
    ]
    if not outputs:
        lines.append(f"{_INDENT * 2}return {{}}")
        return lines
    lines += [
        "",
        f"{_INDENT * 2}def transform(item):",
        f"{_INDENT * 3}# Fill in: compute the new item from ``item``.",
        f"{_INDENT * 3}return item",
        "",
        f"{_INDENT * 2}return {{",
    ]
    for port in outputs:
        source = next((p for p in inputs if p.required and p.type_name == port.type_name), None)
        if source is not None:
            value = f"self.map_items(transform, inputs[{_py_str(source.name)}])"
        else:
            value = f"Collection([], item_type={port.type_name})"
        lines.append(f"{_INDENT * 3}{_py_str(port.name)}: {value},")
    lines.append(f"{_INDENT * 2}}}")
    return lines


def _process_item_body(spec: StarterSpec) -> list[str]:
    in_type = spec.input_ports[0].type_name if spec.input_ports else "DataObject"
    out_type = spec.output_ports[0].type_name if spec.output_ports else in_type
    lines = [
        f"{_INDENT}def process_item(self, item: {in_type}, config: BlockConfig, state: Any = None) -> {out_type}:",
        f"{_INDENT * 2}# >>> EDIT THIS <<<",
        f"{_INDENT * 2}# Called once per item of the first input port's Collection; return one",
        f"{_INDENT * 2}# {out_type} for the first output port. Read a parameter with",
        f"{_INDENT * 2}# config.get(<name>, <default>) and the item's value with item.to_memory().",
    ]
    if in_type == out_type:
        lines += [
            f"{_INDENT * 2}# The starter returns the item unchanged so the block runs as-is.",
            f"{_INDENT * 2}return item",
        ]
    else:
        lines.append(
            f"{_INDENT * 2}raise NotImplementedError({_py_str(f'Fill in process_item(): build a {out_type} from the {in_type} item.')})"
        )
    return lines


_LOAD_SNIPPETS: dict[str, tuple[str, ...]] = {
    "Text": ('return Text(content=path.read_text(encoding="utf-8"), format="plain")',),
    "Artifact": ("return Artifact(file_path=path)",),
    "Array": (
        "import numpy as np",
        "",
        "arr = np.load(path)",
        'return Array(axes=[f"axis_{i}" for i in range(arr.ndim)], data=arr)',
    ),
    "DataFrame": ("import pyarrow.csv as pa_csv", "", "return DataFrame(data=pa_csv.read_csv(path))"),
}

_SAVE_SNIPPETS: dict[str, tuple[str, ...]] = {
    "Text": ('path.write_text(obj.to_memory(), encoding="utf-8")',),
    "Artifact": ("path.write_bytes(obj.to_memory())",),
    # Write through a handle: np.save(path, ...) appends ".npy" to any other extension.
    "Array": ("import numpy as np", "", 'with path.open("wb") as handle:', "    np.save(handle, obj.to_memory())"),
    "DataFrame": ("import pyarrow.csv as pa_csv", "", "pa_csv.write_csv(obj.to_memory(), path)"),
}


def _load_file_body(spec: StarterSpec) -> list[str]:
    data_type = spec.output_ports[0].type_name if spec.output_ports else "DataObject"
    lines = [
        f"{_INDENT}def load_file(self, path: Path, config: dict[str, Any]) -> {data_type}:",
        f"{_INDENT * 2}# >>> EDIT THIS <<<",
        f"{_INDENT * 2}# Read the ONE file at ``path`` and return one {data_type}.",
    ]
    return lines + _snippet_or_fill_in(
        _LOAD_SNIPPETS.get(data_type) if data_type in spec.known_types else None,
        f"Fill in load_file(): read the file into a {data_type}.",
    )


def _save_file_body(spec: StarterSpec) -> list[str]:
    data_type = spec.input_ports[0].type_name if spec.input_ports else "DataObject"
    lines = [
        f"{_INDENT}def save_file(self, obj: DataObject, path: Path, config: dict[str, Any]) -> None:",
        f"{_INDENT * 2}# >>> EDIT THIS <<<",
        f"{_INDENT * 2}# Write the ONE object ``obj`` (a {data_type}, checked by the base class) to ``path``.",
    ]
    return lines + _snippet_or_fill_in(
        _SAVE_SNIPPETS.get(data_type) if data_type in spec.known_types else None,
        f"Fill in save_file(): write the {data_type} to the file.",
    )


def _snippet_or_fill_in(snippet: tuple[str, ...] | None, message: str) -> list[str]:
    if snippet is None:
        return [f"{_INDENT * 2}raise NotImplementedError({_py_str(message)})"]
    return [f"{_INDENT * 2}{line}" if line else "" for line in snippet]


# ---------------------------------------------------------------------------
# Literal formatting
# ---------------------------------------------------------------------------


def _py_str(value: str) -> str:
    """Return a double-quoted Python string literal for *value*."""
    return json.dumps(value, ensure_ascii=False)


def _py_docstring(value: str) -> str:
    cleaned = " ".join(value.split()).replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if cleaned.endswith('"'):
        cleaned += " "
    return f'"""{cleaned}"""'


def _py_literal(value: Any, *, level: int) -> str:
    """Format a JSON-like literal as indented Python source (first line unindented)."""
    pad = _INDENT * (level + 1)
    close = _INDENT * level
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{pad}{_py_str(str(k))}: {_py_literal(v, level=level + 1)}," for k, v in value.items()]
        return "{\n" + "\n".join(items) + f"\n{close}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [f"{pad}{_py_literal(v, level=level + 1)}," for v in value]
        return "[\n" + "\n".join(items) + f"\n{close}]"
    if isinstance(value, str):
        return _py_str(value)
    return repr(value)


__all__ = ["PortStub", "StarterSpec", "render_starter"]
