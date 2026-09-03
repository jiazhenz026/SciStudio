"""ADR-054 spec 1 FR-012 — settling a producing panel's emission into a decision.

A producing panel's only outbound path is the emission of code, and ADR-054 §3.6
says the meaning of an emission is settled by the context it is mounted in. These
tests pin the interactive-block context: the snippet the host committed becomes
the ``interactive_response`` the block's ``run`` reads, and every way that can
fail names the block and the panel rather than leaving a person who clicked
Confirm with nothing.

The namespace is the other half. The snippet arrived over a WebSocket, so what it
can reach is a real boundary and not a convention: exactly one name, ``scistudio``,
whose only attribute is ``output``. The refusals below are the boundary's tests —
an import, a file open, a builtin, a dunder walk out of the namespace, and an
attribute the sink does not have.
"""

from __future__ import annotations

import pytest

from scistudio.blocks.base.interactive import (
    INTERACTIVE_EMISSION_KEY,
    InteractiveEmissionError,
    is_panel_emission,
    settle_interactive_response,
    settle_panel_emission,
)

# The two snippets the shipped built-in panel documents actually emit
# (``src/scistudio/panels/builtin/core.interactive.{data_router,pair_editor}``).
DATA_ROUTER_EMISSION = (
    'assignments = {"port_1": ["input_1:0", "input_1:1"], "port_2": []}\nscistudio.output(assignments=assignments)'
)
PAIR_EDITOR_EMISSION = 'reorder = {"input_1": [1, 0], "input_2": [0, 1]}\nscistudio.output(reorder=reorder)'


def settle(code: str) -> dict[str, object]:
    """Settle *code* as ``DataRouter``'s panel would have emitted it."""
    return settle_panel_emission(
        code,
        block_name="DataRouter",
        panel_id="core.interactive.data_router",
    )


class TestTheShippedPanelsCanBeConfirmed:
    """The regression this work exists to close: both built-ins were unconfirmable."""

    def test_data_router_emission_becomes_the_assignments_the_block_reads(self) -> None:
        # `data_router.py` reads `config["interactive_response"]["assignments"]`
        # and is not touched by this change; the translation is what meets it.
        assert settle(DATA_ROUTER_EMISSION) == {"assignments": {"port_1": ["input_1:0", "input_1:1"], "port_2": []}}

    def test_pair_editor_emission_becomes_the_reorder_the_block_reads(self) -> None:
        assert settle_panel_emission(
            PAIR_EDITOR_EMISSION,
            block_name="PairEditor",
            panel_id="core.interactive.pair_editor",
        ) == {"reorder": {"input_1": [1, 0], "input_2": [0, 1]}}

    def test_several_keyword_arguments_all_reach_the_response(self) -> None:
        assert settle('scistudio.output(a=1, b=[2], c={"d": None})') == {
            "a": 1,
            "b": [2],
            "c": {"d": None},
        }


class TestTellingAnEmissionFromADecision:
    """The boundary shape, and why it cannot be read two ways."""

    def test_a_lone_string_code_key_is_an_emission(self) -> None:
        assert is_panel_emission({INTERACTIVE_EMISSION_KEY: "scistudio.output(x=1)"})

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"assignments": {"port_1": []}}, id="a decision dict"),
            pytest.param({"reorder": {"input_1": [0]}}, id="another decision dict"),
            pytest.param({"code": "x", "extra": 1}, id="code plus another key"),
            pytest.param({"code": {"nested": True}}, id="code holding a non-string"),
            pytest.param({"code": 3}, id="code holding a number"),
            pytest.param({}, id="an empty decision"),
            pytest.param("not a mapping", id="not a mapping at all"),
            pytest.param(None, id="nothing"),
        ],
    )
    def test_everything_else_is_a_decision(self, payload: object) -> None:
        assert not is_panel_emission(payload)

    def test_a_decision_passes_through_verbatim(self) -> None:
        # A programmatic driver, a test, and a decision remembered before this
        # migration all keep working: nothing is executed, nothing is rewritten.
        decision = {"assignments": {"port_1": ["input_1:0"]}}
        assert settle_interactive_response(decision, block_name="b", panel_id="p") is decision

    def test_an_emission_is_translated(self) -> None:
        assert settle_interactive_response(
            {INTERACTIVE_EMISSION_KEY: DATA_ROUTER_EMISSION},
            block_name="DataRouter",
            panel_id="core.interactive.data_router",
        ) == {"assignments": {"port_1": ["input_1:0", "input_1:1"], "port_2": []}}


class TestTheNamespaceIsABoundary:
    """What an emission may reach, and what it may not.

    Exposed: one global name, ``scistudio``, an object whose only attribute is
    ``output``. Withheld: every builtin (so no ``open``, no ``print``, no
    ``eval``, no ``getattr``, and no ``__import__`` — which is what makes an
    ``import`` statement fail), every module, every host object, and every
    identifier beginning with ``__``.
    """

    def test_an_import_statement_fails(self) -> None:
        with pytest.raises(InteractiveEmissionError, match="__import__ not found"):
            settle("import os\nscistudio.output(x=1)")

    def test_a_from_import_fails(self) -> None:
        with pytest.raises(InteractiveEmissionError, match="__import__ not found"):
            settle("from os import path\nscistudio.output(x=1)")

    def test_opening_a_file_fails(self) -> None:
        with pytest.raises(InteractiveEmissionError, match="name 'open' is not defined"):
            settle('open("/etc/passwd").read()')

    @pytest.mark.parametrize("builtin", ["print", "eval", "exec", "getattr", "compile", "input"])
    def test_no_builtin_is_reachable(self, builtin: str) -> None:
        with pytest.raises(InteractiveEmissionError, match=f"name '{builtin}' is not defined"):
            settle(f"{builtin}(1)")

    @pytest.mark.parametrize(
        "code",
        [
            pytest.param("scistudio.__class__", id="a dunder on the sink"),
            pytest.param("().__class__.__bases__[0].__subclasses__()", id="the classic escape walk"),
            pytest.param("__builtins__", id="the builtins mapping by name"),
            pytest.param("x = scistudio.output.__globals__", id="the sink's own globals"),
            pytest.param("def __f():\n    pass", id="a dunder function definition"),
            pytest.param("scistudio.output(__x=1)", id="a dunder keyword argument"),
        ],
    )
    def test_no_dunder_is_reachable(self, code: str) -> None:
        # Refused before anything executes: with no builtins, a dunder walk is
        # the documented way back to a live ``__builtins__``.
        with pytest.raises(InteractiveEmissionError, match="refused"):
            settle(code)

    @pytest.mark.parametrize(
        "code",
        [
            pytest.param(
                'scistudio.output(a="{0.__class__}".format(()))',
                id="a dunder spelled in a format string",
            ),
            pytest.param(
                'scistudio.output(a="{0.__class__.__base__.__subclasses__}".format(()))',
                id="the classic escape walk, spelled in a format string",
            ),
            pytest.param(
                'scistudio.output(a="{0.output.__globals__}".format(scistudio))',
                id="the sink's own globals, spelled in a format string",
            ),
            pytest.param(
                'scistudio.output(a="{0.output.__globals__[__name__]}".format(scistudio))',
                id="one global read out by name",
            ),
            pytest.param(
                'f = "{0.__class__}"\nscistudio.output(a=f.format(()))',
                id="the format string bound to a name first",
            ),
            pytest.param(
                'scistudio.output(a="{x.__class__}".format_map({"x": ()}))',
                id="format_map rather than format",
            ),
        ],
    )
    def test_no_dunder_is_reachable_through_a_runtime_format_string(self, code: str) -> None:
        """The AST pass walks identifiers, and ``str.format`` traverses
        attributes named by the *runtime string* — an ``ast.Constant``, which
        carries no identifier node to walk (#2229).

        It hands back text rather than a live object, so it is a read of the
        type graph and of module globals rather than an escape; but the read is
        exfiltratable through ``scistudio.output``, which is persisted into the
        workflow, and a documented mitigation with an undocumented hole is
        worth closing.
        """
        with pytest.raises(InteractiveEmissionError, match="refused"):
            settle(code)

    def test_an_ordinary_string_still_settles(self) -> None:
        """The refusal is on the traversal and on the template, not on strings."""
        assert settle('scistudio.output(a="left-right", b="{0} is a placeholder")') == {
            "a": "left-right",
            "b": "{0} is a placeholder",
        }

    def test_the_workflows_own_strings_may_carry_a_double_underscore(self) -> None:
        """The emitted decision embeds the workflow's names, so the refusal is
        on a format template that walks into a dunder — not on any string that
        happens to contain ``__``.

        Spelled as ``data_router``'s own emission, because that is the shape a
        port named with a double underscore would actually arrive in.
        """
        code = 'assignments = {"my__port": ["input_1:0"]}\nscistudio.output(assignments=assignments)'
        assert settle(code) == {"assignments": {"my__port": ["input_1:0"]}}

    @pytest.mark.parametrize(
        "code",
        [
            pytest.param('scistudio.output(a="{0}".format("x"))', id="format on a literal"),
            pytest.param('scistudio.output(a="{x}".format_map({"x": 1}))', id="format_map on a literal"),
        ],
    )
    def test_the_one_runtime_string_traversal_is_refused_outright(self, code: str) -> None:
        """``format`` is refused whatever it is asked to format.

        Refusing only the dunder payload would leave the mechanism, and the
        mechanism is what makes an attribute reachable without an identifier
        for the AST pass to see. Both halves are refused so neither has to be
        the only one that holds.
        """
        with pytest.raises(InteractiveEmissionError, match="refused"):
            settle(code)

    def test_the_sink_has_no_attribute_but_output(self) -> None:
        with pytest.raises(InteractiveEmissionError, match="has no attribute 'read'"):
            settle("scistudio.read()")

    def test_the_refusal_names_the_block_and_the_panel(self) -> None:
        with pytest.raises(InteractiveEmissionError) as caught:
            settle("import os")
        assert "DataRouter" in str(caught.value)
        assert "core.interactive.data_router" in str(caught.value)
        assert caught.value.block_name == "DataRouter"
        assert caught.value.panel_id == "core.interactive.data_router"


class TestEveryFailureIsLegible:
    """A person who clicks Confirm gets an error, never silence."""

    def test_code_that_does_not_parse(self) -> None:
        with pytest.raises(InteractiveEmissionError, match="does not parse as Python"):
            settle("assignments = {")

    def test_code_that_calls_nothing(self) -> None:
        with pytest.raises(InteractiveEmissionError, match=r"never called scistudio\.output"):
            settle('assignments = {"port_1": []}')

    def test_code_that_calls_output_twice(self) -> None:
        with pytest.raises(InteractiveEmissionError, match=r"called scistudio\.output\(\) 2 times"):
            settle("scistudio.output(a=1)\nscistudio.output(b=2)")

    def test_code_that_raises(self) -> None:
        with pytest.raises(InteractiveEmissionError, match="ZeroDivisionError"):
            settle("scistudio.output(x=1 // 0)")

    def test_output_called_positionally(self) -> None:
        with pytest.raises(InteractiveEmissionError, match="positional argument"):
            settle('scistudio.output({"assignments": {}})')

    @pytest.mark.parametrize("code", ["", "   ", "\n\n"])
    def test_an_empty_emission(self, code: str) -> None:
        with pytest.raises(InteractiveEmissionError, match="emitted no code"):
            settle(code)

    def test_the_error_is_a_value_error(self) -> None:
        # The engine's ``except Exception`` around the interactive run turns this
        # into the block's ERROR exactly as it does the JSON-safety refusal,
        # which is what "surfaced the way a rejected response is" means.
        assert issubclass(InteractiveEmissionError, ValueError)


class TestStatementFormsAreNotRestrictedHere:
    """The ADR-054 §3.6 whitelist is the explore session's, not this context's.

    The spec's ``scope.out`` keeps it out of this work: it belongs where an
    emission is *queued*. Restricting the namespace is this module's job;
    restricting the statement forms is not, so a loop or a conditional in an
    emission runs.
    """

    def test_a_loop_is_admitted(self) -> None:
        assert settle("t = []\nfor i in (0, 1, 2):\n    t.append(i)\nscistudio.output(items=t)") == {"items": [0, 1, 2]}

    def test_a_conditional_and_a_subscript_assignment_are_admitted(self) -> None:
        assert settle('d = {}\nif True:\n    d["a"] = 1\nscistudio.output(d=d)') == {"d": {"a": 1}}


def test_a_non_json_safe_emission_is_left_to_the_engines_one_gate() -> None:
    """FR-004's JSON check stays where it is — this function does not duplicate it.

    ``float('nan')`` is unreachable without builtins, so the reachable way to
    produce a non-JSON value is a set literal. It settles here and is refused by
    the engine's ``json.dumps(..., allow_nan=False)``, which runs on the result.
    """
    settled = settle("scistudio.output(choice={1, 2})")
    assert settled == {"choice": {1, 2}}
