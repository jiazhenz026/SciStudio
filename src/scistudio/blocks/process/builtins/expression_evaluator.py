"""AST-whitelisted expression evaluator for metadata predicates.

Used by :class:`scistudio.blocks.process.builtins.filter_collection.FilterCollection`
(T-TRK-012, Phase 11 master plan §2.5 sub-1d) to let users filter a
``Collection`` with a short Python-syntax predicate such as::

    meta.channel == "DAPI" and index < 10

without exposing the full power of :func:`eval`. The evaluator parses
the expression once, rejects any AST node outside an explicit allow
list, and then walks the validated tree against a per-item scope dict
to return a ``bool``.

Only the nodes, operators, names, and the single ``len`` call listed in
``_ALLOWED_NODES`` / ``_ALLOWED_NAMES`` are permitted. Any other
construct — including arbitrary function calls, imports, lambdas,
dunder attribute access, or subscripting with a non-literal key —
raises :class:`ValueError` at parse time so users see the error
immediately at workflow validation rather than mid-run.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from scistudio.core.types.base import DataObject

__all__ = ["ExpressionEvaluator", "build_scope"]


# Allow-list of AST node types. Anything not in this set is rejected at
# parse time. Keep in sync with docs/specs/phase11-implementation-standards.md
# §T-TRK-012 "Allowed AST nodes".
_ALLOWED_NODES: Final[frozenset[type[ast.AST]]] = frozenset(
    {
        ast.Expression,
        ast.Compare,
        ast.BoolOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Attribute,
        ast.Subscript,
        ast.Load,
        # Comparison / boolean / unary operators
        ast.And,
        ast.Or,
        ast.Not,
        ast.USub,
        ast.UAdd,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Is,
        ast.IsNot,
        # Literal containers (used on the right-hand side of ``in``)
        ast.List,
        ast.Tuple,
        ast.Set,
    }
)

# Names the expression is allowed to reference. ``len`` is the single
# whitelisted callable; all other ``Call`` nodes are rejected.
_ALLOWED_NAMES: Final[frozenset[str]] = frozenset(
    {"item", "index", "meta", "framework", "user", "len", "True", "False", "None"}
)


class ExpressionEvaluator:
    """Parse, validate, and evaluate a metadata predicate expression.

    The evaluator is constructed from a source string. Construction
    performs parsing plus a full AST walk to reject any forbidden
    construct, so a malformed or unsafe expression fails fast at
    workflow validation time rather than at runtime. The resulting
    instance is reusable and stateless: call :meth:`evaluate` once per
    data item.
    """

    def __init__(self, source: str) -> None:
        if not isinstance(source, str):
            raise TypeError(f"ExpressionEvaluator source must be str, got {type(source).__name__}")
        self._source: str = source
        try:
            tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Expression is not valid Python syntax: {exc.msg}") from exc
        self._validate(tree)
        self._tree: ast.Expression = tree

    @property
    def source(self) -> str:
        """Return the original expression source string."""
        return self._source

    @staticmethod
    def _validate(tree: ast.Expression) -> None:
        """Walk *tree* once and reject any forbidden construct."""
        for node in ast.walk(tree):
            # Call: only len(...) is allowed, and only as a bare Name.
            if isinstance(node, ast.Call):
                func = node.func
                if not (isinstance(func, ast.Name) and func.id == "len"):
                    raise ValueError(f"Expression contains forbidden construct: Call to {ast.dump(func)}")
                continue

            if type(node) not in _ALLOWED_NODES:
                raise ValueError(f"Expression contains forbidden construct: {type(node).__name__}")

            # Name: restrict to the whitelisted scope identifiers.
            if isinstance(node, ast.Name):
                if node.id.startswith("__"):
                    raise ValueError(f"Expression contains forbidden construct: dunder name {node.id!r}")
                if node.id not in _ALLOWED_NAMES:
                    raise ValueError(f"Expression contains forbidden construct: name {node.id!r}")

            # Attribute: reject dunder access (e.g. obj.__class__).
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise ValueError(f"Expression contains forbidden construct: dunder attribute {node.attr!r}")

            # Subscript: restrict key to a literal constant.
            if isinstance(node, ast.Subscript):
                key = node.slice
                if not isinstance(key, ast.Constant):
                    raise ValueError("Expression contains forbidden construct: Subscript with non-literal key")

    def evaluate(self, scope: dict[str, Any]) -> bool:
        """Evaluate the validated expression against *scope*.

        ``scope`` must supply the names the expression references. This
        method does **not** re-validate — construction already did —
        but it walks the tree manually rather than calling
        :func:`eval`, so there is no path to the real Python builtins.
        """
        result = self._eval_node(self._tree.body, scope)
        return bool(result)

    # ------------------------------------------------------------------
    # Internal AST interpreter
    # ------------------------------------------------------------------

    def _eval_node(self, node: ast.AST, scope: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            if node.id == "len":
                return len
            if node.id not in scope:
                raise NameError(f"Name {node.id!r} is not defined in evaluation scope")
            return scope[node.id]

        if isinstance(node, ast.Attribute):
            obj = self._eval_node(node.value, scope)
            return getattr(obj, node.attr)

        if isinstance(node, ast.Subscript):
            obj = self._eval_node(node.value, scope)
            key_node = node.slice
            if not isinstance(key_node, ast.Constant):
                raise ValueError("Subscript key must be a literal constant")
            return obj[key_node.value]

        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, scope)
            if isinstance(node.op, ast.Not):
                return not operand
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result: Any = True
                for value in node.values:
                    result = self._eval_node(value, scope)
                    if not result:
                        return result
                return result
            if isinstance(node.op, ast.Or):
                result = False
                for value in node.values:
                    result = self._eval_node(value, scope)
                    if result:
                        return result
                return result
            raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, scope)
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                right = self._eval_node(comparator, scope)
                if not self._apply_compare(op, left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.List):
            return [self._eval_node(elt, scope) for elt in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt, scope) for elt in node.elts)
        if isinstance(node, ast.Set):
            return {self._eval_node(elt, scope) for elt in node.elts}

        if isinstance(node, ast.Call):
            # Only len(...) survived validation.
            func = self._eval_node(node.func, scope)
            args = [self._eval_node(arg, scope) for arg in node.args]
            if node.keywords:
                raise ValueError("len() does not accept keyword arguments")
            return func(*args)

        raise ValueError(f"Unsupported AST node at runtime: {type(node).__name__}")

    @staticmethod
    def _apply_compare(op: ast.cmpop, left: Any, right: Any) -> bool:
        if isinstance(op, ast.Eq):
            return bool(left == right)
        if isinstance(op, ast.NotEq):
            return bool(left != right)
        if isinstance(op, ast.Lt):
            return bool(left < right)
        if isinstance(op, ast.LtE):
            return bool(left <= right)
        if isinstance(op, ast.Gt):
            return bool(left > right)
        if isinstance(op, ast.GtE):
            return bool(left >= right)
        if isinstance(op, ast.In):
            return left in right
        if isinstance(op, ast.NotIn):
            return left not in right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        raise ValueError(f"Unsupported comparison operator: {type(op).__name__}")


def build_scope(item: DataObject, index: int) -> dict[str, Any]:
    """Return the standard per-item evaluation scope.

    Exposes ``item``, ``index``, and the three metadata slot aliases
    ``meta`` / ``framework`` / ``user`` that mirror the corresponding
    attributes on :class:`scistudio.core.types.base.DataObject`. The
    attributes are accessed directly (not via ``getattr`` with a
    default) because the three-slot model from ADR-027 D5 guarantees
    every ``DataObject`` exposes them.
    """
    return {
        "item": item,
        "index": index,
        "meta": item.meta,
        "framework": item.framework,
        "user": item.user,
    }
