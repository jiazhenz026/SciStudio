"""Script introspection — parse run() signature, extract configure() schema."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def introspect_script(script_path: str | Path) -> dict[str, Any]:
    """Parse a user script and extract its interface metadata.

    Analyses the script's AST to discover:
    - ``run()`` function signature (parameter names, annotations, defaults).
    - ``configure()`` return value (if present) — treated as a parameter schema.
    - Top-level docstring.
    - Variadic port list derived from ``run()`` parameter annotations (ADR-029 D7).

    Returns a dictionary with keys:
        ``has_run``: bool
        ``run_params``: list of dicts with name, annotation, default
        ``has_configure``: bool
        ``configure_schema``: dict or None
        ``docstring``: str or None
        ``input_ports``: list of ``{"name": str, "types": list[str]}`` dicts
            derived from ``run()`` parameter annotations.  Unannotated
            parameters default to ``["DataObject"]``.
    """
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    result: dict[str, Any] = {
        "has_run": False,
        "run_params": [],
        "has_configure": False,
        "configure_schema": None,
        "docstring": ast.get_docstring(tree),
        "input_ports": [],
    }

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name == "run":
                result["has_run"] = True
                params = _extract_params(node)
                result["run_params"] = params
                result["input_ports"] = _params_to_port_dicts(params)
            elif node.name == "configure":
                result["has_configure"] = True
                result["configure_schema"] = _extract_configure_return(node, source)

    return result


def _extract_params(func_node: ast.FunctionDef) -> list[dict[str, Any]]:
    """Extract parameter info from a function definition."""
    params: list[dict[str, Any]] = []
    args = func_node.args

    # Combine all positional, keyword args.
    all_args = list(args.args) + list(args.kwonlyargs)
    # Defaults alignment: defaults fill from the right.
    defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
    kw_defaults = list(args.kw_defaults)

    for i, arg in enumerate(all_args):
        param: dict[str, Any] = {"name": arg.arg, "annotation": None, "default": None}
        if arg.annotation is not None:
            param["annotation"] = ast.dump(arg.annotation)
        if i < len(args.args):
            default_node = defaults[i] if i < len(defaults) else None
            if default_node is not None:
                param["default"] = ast.dump(default_node)
        else:
            kw_idx = i - len(args.args)
            kw_default_node = kw_defaults[kw_idx] if kw_idx < len(kw_defaults) else None
            if kw_default_node is not None:
                param["default"] = ast.dump(kw_default_node)
        params.append(param)

    return params


def _params_to_port_dicts(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert ``_extract_params()`` output to variadic port dict list (ADR-029 D7).

    Maps each parameter to a port dict ``{"name": str, "types": list[str]}``.
    Annotation strings are the ``ast.dump()`` representation produced by
    :func:`_extract_params`.  Only simple ``Name(id='...')`` annotations are
    resolved; all other forms fall back to ``"DataObject"`` silently.

    The ``self`` and ``config`` parameters (common in ``run()`` signatures)
    are skipped: ``self`` because it is the instance reference, ``config``
    because it represents the block configuration, not data input.

    Examples::

        run(self, image: Image, table: DataFrame) -> ...
        # → [{"name": "image", "types": ["Image"]},
        #    {"name": "table", "types": ["DataFrame"]}]

        run(self, x, y) -> ...
        # → [{"name": "x", "types": ["DataObject"]},
        #    {"name": "y", "types": ["DataObject"]}]
    """
    _skip_params = {"self", "config"}
    port_dicts: list[dict[str, Any]] = []
    for param in params:
        name: str = param.get("name", "")
        if name in _skip_params:
            continue
        annotation_dump: str | None = param.get("annotation")
        type_name = _annotation_to_type_name(annotation_dump)
        port_dicts.append({"name": name, "types": [type_name]})
    return port_dicts


def _annotation_to_type_name(annotation_dump: str | None) -> str:
    """Extract a clean type name from an ``ast.dump()`` annotation string.

    Only handles simple ``Name(id='TypeName')`` nodes.  All other forms
    (subscripts, attributes, unions) fall back to ``"DataObject"``.
    """
    if annotation_dump is None:
        return "DataObject"
    # Simple name: Name(id='Image') or Name(id='Image', ctx=Load())
    if annotation_dump.startswith("Name(id='"):
        try:
            # ast.dump format: "Name(id='Image')" or "Name(id='Image', ctx=Load())"
            start = annotation_dump.index("id='") + 4
            end = annotation_dump.index("'", start)
            return annotation_dump[start:end]
        except (ValueError, IndexError):
            pass
    return "DataObject"


def _extract_configure_return(func_node: ast.FunctionDef, source: str) -> dict[str, Any] | None:
    """Try to extract a static return value from a ``configure()`` function.

    If the function body is a single ``return {literal_dict}``, parse it.
    Otherwise return None (dynamic configure not statically analysable).
    """
    body = func_node.body
    # Skip docstring if present.
    stmts = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if len(stmts) == 1 and isinstance(stmts[0], ast.Return):
        ret_value = stmts[0].value
        if isinstance(ret_value, ast.Dict):
            try:
                result: dict[str, Any] = ast.literal_eval(ret_value)
                return result
            except (ValueError, TypeError):
                return None
    return None
