"""Auto-generate JSON Schema for MCP tool handlers (#789).

Each MCP tool in :mod:`scieasy.ai.agent.mcp._registry` is a plain Python
function with type-annotated parameters and a NumPy-style docstring.
This module inspects those at registration time to produce a JSON
Schema 2020-12 object that:

* Tells the LLM (via the MCP ``tools/list`` response) the exact parameter
  names, types, and which are required.
* Lets :class:`MCPServer.dispatch` validate incoming ``tools/call``
  arguments and emit clear ``JSON-RPC -32602`` errors instead of opaque
  Python ``TypeError``s.

Design constraints:

* Pure standard library — no ``jsonschema`` dependency required for
  generation (validation is light-touch: required-field check + type
  coercion check).
* Imported lazily by :class:`ToolEntry.input_schema` so tool modules
  importing this file is cheap.
* NumPy docstring parsing is best-effort: missing ``Parameters`` section
  yields empty descriptions, never raises.

This module does NOT modify the existing tool handlers — schemas are
synthesised by introspection only.
"""

from __future__ import annotations

import inspect
import logging
import re
import typing
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

logger = logging.getLogger(__name__)


# JSON Schema primitive types
_PRIMITIVE_TYPE_MAP: dict[type, dict[str, Any]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    Path: {"type": "string", "format": "path"},
}


def _is_optional(annotation: Any) -> bool:
    """Return ``True`` if *annotation* is ``Optional[T]`` (``T | None``)."""
    origin = get_origin(annotation)
    if origin is Union or origin is typing.Union:
        return type(None) in get_args(annotation)
    # Python 3.10+ ``X | None`` syntax goes through ``types.UnionType``.
    try:
        import types as _types

        if isinstance(annotation, _types.UnionType):
            return type(None) in get_args(annotation)
    except (ImportError, AttributeError):
        pass
    return False


def _strip_optional(annotation: Any) -> Any:
    """Return ``T`` from ``Optional[T]``; identity otherwise."""
    if not _is_optional(annotation):
        return annotation
    non_none = [a for a in get_args(annotation) if a is not type(None)]
    if len(non_none) == 1:
        return non_none[0]
    # ``Optional[Union[A, B]]`` → ``Union[A, B]``
    return Union[tuple(non_none)]  # type: ignore[return-value]  # noqa: UP007


def _annotation_to_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema fragment.

    Handles primitives, ``Optional[T]``, ``Literal[...]``, ``list[T]``,
    ``dict[K, V]``, and ``tuple[T, ...]``. Unknown annotations fall back
    to a permissive ``{}`` so the schema is still well-formed.
    """
    nullable = _is_optional(annotation)
    inner = _strip_optional(annotation)

    schema: dict[str, Any]
    origin = get_origin(inner)

    # ``inspect.Parameter.empty`` / no annotation → permissive object.
    if inner is inspect.Parameter.empty or inner is Any:
        schema = {}
    # ``Literal["a", "b"]``
    elif origin is Literal:
        values = list(get_args(inner))
        # Infer a single uniform JSON type from the literal values.
        py_types = {type(v) for v in values}
        if py_types == {str}:
            schema = {"type": "string", "enum": values}
        elif py_types == {int}:
            schema = {"type": "integer", "enum": values}
        elif py_types <= {int, float}:
            schema = {"type": "number", "enum": values}
        elif py_types == {bool}:
            schema = {"type": "boolean", "enum": values}
        else:
            schema = {"enum": values}
    # ``list[T]`` / ``tuple[T, ...]``
    elif origin in (list, tuple):
        args = get_args(inner)
        schema = {"type": "array", "items": _annotation_to_schema(args[0])} if args else {"type": "array"}
    # ``dict[K, V]``
    elif origin is dict:
        args = get_args(inner)
        if len(args) == 2:
            schema = {
                "type": "object",
                "additionalProperties": _annotation_to_schema(args[1]),
            }
        else:
            schema = {"type": "object"}
    # Primitive type lookup
    elif isinstance(inner, type) and inner in _PRIMITIVE_TYPE_MAP:
        schema = dict(_PRIMITIVE_TYPE_MAP[inner])
    elif isinstance(inner, type) and issubclass(inner, Path):
        schema = {"type": "string", "format": "path"}
    else:
        schema = {}

    if nullable:
        # JSON Schema 2020-12 supports nullable via ``type`` array.
        if "type" in schema and isinstance(schema["type"], str):
            schema["type"] = [schema["type"], "null"]
        else:
            schema["nullable"] = True
    return schema


# NumPy docstring Parameters section parser. Tolerant — silently
# yields nothing if the docstring is missing or malformed.
_PARAMS_HEADER_RE = re.compile(
    r"^[ \t]*Parameters\s*\n[ \t]*-{3,}\s*$",
    re.MULTILINE,
)
_SECTION_HEADER_RE = re.compile(
    r"^[ \t]*[A-Z][A-Za-z ]+\s*\n[ \t]*-{3,}\s*$",
    re.MULTILINE,
)


def _parse_numpy_param_descriptions(docstring: str | None) -> dict[str, str]:
    """Extract one-line descriptions from a NumPy-style docstring.

    Returns ``{param_name: description}``. Multi-line param descriptions
    are flattened into one space-joined string. Missing or malformed
    sections return an empty dict.
    """
    if not docstring:
        return {}
    header_match = _PARAMS_HEADER_RE.search(docstring)
    if not header_match:
        return {}
    start = header_match.end()
    # Find the next section header (if any) to bound the Parameters block.
    rest = docstring[start:]
    next_section = _SECTION_HEADER_RE.search(rest)
    end = next_section.start() if next_section else len(rest)
    block = rest[:end]

    descriptions: dict[str, str] = {}
    # NumPy param lines look like:
    #   name : type
    #       Description text...
    #       continues on next indented line.
    # We accept ``name`` or ``name : type``.
    current_name: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        nonlocal current_name, current_lines
        if current_name is not None:
            joined = " ".join(line.strip() for line in current_lines).strip()
            if joined:
                descriptions[current_name] = joined
        current_name = None
        current_lines = []

    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # A new param header is unindented relative to descriptions (which
        # are indented). Use the simple "no leading whitespace OR exactly
        # 4 spaces" rule that NumPy convention follows; in practice the
        # param header has fewer leading spaces than its body.
        leading = len(line) - len(line.lstrip(" \t"))
        if (leading <= 4 and ":" in stripped[:80]) or (
            leading <= 4 and re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*$", stripped)
        ):
            # Heuristic: param header. Names cannot have spaces.
            name_part = stripped.split(":", 1)[0].strip()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_, ]*$", name_part):
                _flush()
                # Comma-separated names (rare): tag all with the same desc.
                current_name = name_part.split(",")[0].strip()
                continue
        current_lines.append(stripped)
    _flush()
    return descriptions


def infer_tool_schema(handler: Callable[..., Any]) -> dict[str, Any]:
    """Build a JSON Schema 2020-12 object for *handler*'s parameters.

    Parameters
    ----------
    handler
        A registered MCP tool function. Its signature is introspected to
        produce ``properties`` and ``required`` lists.

    Returns
    -------
    dict
        A JSON Schema object suitable for the MCP ``inputSchema`` field
        of a ``tools/list`` response entry.

    Notes
    -----
    * Parameters without defaults are added to ``required``.
    * Parameters annotated ``Optional[T]`` (or with a ``None`` default)
      get ``nullable: true`` in addition to their primitive type.
    * Descriptions come from the docstring's ``Parameters`` section.
    """
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError) as exc:
        logger.warning("infer_tool_schema: cannot introspect %r: %s", handler, exc)
        return {"type": "object", "additionalProperties": True}

    # ``from __future__ import annotations`` turns every annotation into
    # a string. Use :func:`typing.get_type_hints` to resolve them back
    # to real types before mapping to JSON Schema.
    try:
        hints = typing.get_type_hints(handler)
    except Exception:  # pragma: no cover - defensive; some handlers may have
        # unresolvable forward refs in 3rd-party code paths.
        hints = {}

    docstring = inspect.getdoc(handler)
    descriptions = _parse_numpy_param_descriptions(docstring)

    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for name, param in signature.parameters.items():
        # Skip *args / **kwargs — they cannot be expressed cleanly in JSON
        # Schema and none of the SciEasy MCP tools use them.
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        resolved = hints.get(name, param.annotation)
        prop = _annotation_to_schema(resolved)
        desc = descriptions.get(name)
        if desc:
            prop["description"] = desc
        if param.default is not inspect.Parameter.empty:
            # Record default for documentation purposes; validators may
            # consult it but our dispatcher does not yet.
            if param.default is not None:
                prop["default"] = param.default
        else:
            required.append(name)
        properties[name] = prop

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def validate_call_arguments(
    schema: dict[str, Any],
    arguments: dict[str, Any],
) -> str | None:
    """Light-touch validation of ``tools/call`` arguments against a schema.

    Returns ``None`` on success, or a human-readable error string on
    failure. Designed for the JSON-RPC ``-32602`` ("invalid params") path
    so the agent gets a precise hint instead of a Python ``TypeError``.

    Checks performed:

    * Every name in ``required`` is present in ``arguments``.
    * ``additionalProperties: false`` rejects unknown keys.
    * Per-property: when the schema declares a primitive ``type``, the
      argument value's Python type matches. Nullability is honoured.

    More complex validation (enum, format, nested array items) is
    deferred — the goal here is to catch the common "wrong param name"
    failure mode #789 surfaced, not to ship a full schema validator.
    """
    if not isinstance(schema, dict):
        return None
    required = schema.get("required") or []
    properties = schema.get("properties") or {}

    # Missing required.
    for name in required:
        if name not in arguments:
            return f"missing required field '{name}'"

    # Unknown keys (when additionalProperties is false).
    if schema.get("additionalProperties") is False:
        extras = sorted(set(arguments.keys()) - set(properties.keys()))
        if extras:
            allowed = ", ".join(sorted(properties.keys())) or "(none)"
            return f"unknown field(s): {', '.join(extras)}; allowed fields: {allowed}"

    # Type mismatches (primitive only).
    py_to_json = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        tuple: "array",
        dict: "object",
    }
    for name, value in arguments.items():
        prop = properties.get(name)
        if not isinstance(prop, dict):
            continue
        expected = prop.get("type")
        if expected is None:
            continue
        # ``type`` may be a list when nullable.
        allowed_types: list[str] = list(expected) if isinstance(expected, list) else [expected]
        if value is None and "null" in allowed_types:
            continue
        # Special-case: ``int`` is a valid ``number`` but ``bool`` is also
        # a Python ``int``; we treat bool strictly.
        actual: str | None = "boolean" if isinstance(value, bool) else py_to_json.get(type(value))
        if actual is None:
            continue
        if actual in allowed_types:
            continue
        if actual == "integer" and "number" in allowed_types:
            continue
        return f"field '{name}' has type {actual!r} but schema expects {'/'.join(allowed_types)!r}"

    return None
