"""Unit tests for the AST-whitelisted expression evaluator (T-TRK-012).

These tests exercise :class:`ExpressionEvaluator` directly, without
going through :class:`FilterCollection`, so the whitelist logic and
the runtime interpreter can be validated in isolation. The companion
file ``test_filter_collection_expression.py`` drives the evaluator
through the block's ``run`` path.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from scistudio.blocks.process.builtins.expression_evaluator import (
    ExpressionEvaluator,
    build_scope,
)


def _scope(**kwargs: Any) -> dict[str, Any]:
    """Build a scope dict with sensible defaults for the six slots."""
    base: dict[str, Any] = {
        "item": SimpleNamespace(),
        "index": 0,
        "meta": SimpleNamespace(),
        "framework": SimpleNamespace(),
        "user": {},
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Positive cases (>= 6)
# ---------------------------------------------------------------------------


class TestPositiveEvaluation:
    def test_simple_index_comparison(self) -> None:
        evaluator = ExpressionEvaluator("index < 5")
        assert evaluator.evaluate(_scope(index=3)) is True
        assert evaluator.evaluate(_scope(index=5)) is False

    def test_nested_attribute_on_meta(self) -> None:
        meta = SimpleNamespace(framework=SimpleNamespace(created_at=100))
        evaluator = ExpressionEvaluator("meta.framework.created_at > 50")
        assert evaluator.evaluate(_scope(meta=meta)) is True
        meta2 = SimpleNamespace(framework=SimpleNamespace(created_at=10))
        assert evaluator.evaluate(_scope(meta=meta2)) is False

    def test_user_tag_in_list(self) -> None:
        evaluator = ExpressionEvaluator("user['tag'] in ['a', 'b', 'c']")
        assert evaluator.evaluate(_scope(user={"tag": "b"})) is True
        assert evaluator.evaluate(_scope(user={"tag": "z"})) is False

    def test_boolean_and_or(self) -> None:
        evaluator = ExpressionEvaluator("index >= 2 and index <= 4")
        assert evaluator.evaluate(_scope(index=3)) is True
        assert evaluator.evaluate(_scope(index=1)) is False
        assert evaluator.evaluate(_scope(index=5)) is False

    def test_not_operator(self) -> None:
        evaluator = ExpressionEvaluator("not (index == 0)")
        assert evaluator.evaluate(_scope(index=1)) is True
        assert evaluator.evaluate(_scope(index=0)) is False

    def test_len_whitelisted(self) -> None:
        evaluator = ExpressionEvaluator("len(user['tags']) > 1")
        assert evaluator.evaluate(_scope(user={"tags": [1, 2, 3]})) is True
        assert evaluator.evaluate(_scope(user={"tags": [1]})) is False

    def test_chained_comparison(self) -> None:
        evaluator = ExpressionEvaluator("0 <= index < 10")
        assert evaluator.evaluate(_scope(index=5)) is True
        assert evaluator.evaluate(_scope(index=10)) is False
        assert evaluator.evaluate(_scope(index=-1)) is False

    def test_equality_with_constant(self) -> None:
        evaluator = ExpressionEvaluator("user['channel'] == 'DAPI'")
        assert evaluator.evaluate(_scope(user={"channel": "DAPI"})) is True
        assert evaluator.evaluate(_scope(user={"channel": "GFP"})) is False


# ---------------------------------------------------------------------------
# Rejection cases (>= 6)
# ---------------------------------------------------------------------------


class TestRejection:
    def test_reject_import_call(self) -> None:
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("__import__('os')")

    def test_reject_arbitrary_function_call(self) -> None:
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("print('hi')")

    def test_reject_dunder_attribute(self) -> None:
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("item.__class__ == str")

    def test_reject_dunder_name(self) -> None:
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("__builtins__")

    def test_reject_unknown_name(self) -> None:
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("os.path")

    def test_reject_lambda(self) -> None:
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("(lambda x: x)(1)")

    def test_reject_assignment_expression(self) -> None:
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("(x := 1)")

    def test_reject_subscript_slice(self) -> None:
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("user['k'][0:2] == []")

    def test_reject_arithmetic_binop(self) -> None:
        # BinOp is not in the allow list — arithmetic is not needed for
        # a predicate language.
        with pytest.raises(ValueError, match="forbidden construct"):
            ExpressionEvaluator("index + 1 > 2")

    def test_reject_syntax_error(self) -> None:
        with pytest.raises(ValueError, match="valid Python syntax"):
            ExpressionEvaluator("index <")


# ---------------------------------------------------------------------------
# build_scope helper + miscellaneous
# ---------------------------------------------------------------------------


class TestMisc:
    def test_source_roundtrip(self) -> None:
        evaluator = ExpressionEvaluator("index == 0")
        assert evaluator.source == "index == 0"

    def test_non_string_source_rejected(self) -> None:
        with pytest.raises(TypeError):
            ExpressionEvaluator(123)  # type: ignore[arg-type]

    def test_build_scope_from_dataobject(self) -> None:
        from scistudio.core.types.array import Array

        item = Array(axes=["y", "x"], shape=(2, 2), dtype="uint8", user={"k": "v"})
        scope = build_scope(item, 7)
        assert scope["item"] is item
        assert scope["index"] == 7
        assert scope["user"] == {"k": "v"}
        assert scope["framework"] is item.framework
        assert scope["meta"] is item.meta
