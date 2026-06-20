"""Tests for workflow validator — structural, edge, cycle, type compat, dangling ports."""

from __future__ import annotations

from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.core.types.array import Array
from scistudio.core.types.series import Series
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.validator import validate_workflow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(
    name: str,
    input_ports: list[InputPort] | None = None,
    output_ports: list[OutputPort] | None = None,
) -> BlockSpec:
    """Create a minimal BlockSpec with the given ports."""
    return BlockSpec(
        name=name,
        input_ports=list(input_ports or []),
        output_ports=list(output_ports or []),
    )


def _registry_from_specs(*specs: BlockSpec) -> BlockRegistry:
    """Build a BlockRegistry pre-populated with the given specs."""
    reg = BlockRegistry()
    for spec in specs:
        reg._registry[spec.name] = spec
    return reg


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


class TestValidatorStructural:
    """Check 1: duplicate IDs, empty workflow."""

    def test_valid_linear_workflow(self) -> None:
        """Three nodes in a linear chain — no errors."""
        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="loader"),
                NodeDef(id="B", block_type="processor"),
                NodeDef(id="C", block_type="writer"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="B:out", target="C:in"),
            ],
        )
        errors = validate_workflow(wf)
        assert errors == []

    def test_empty_workflow_valid(self) -> None:
        """An empty workflow (no nodes) is valid."""
        wf = WorkflowDefinition()
        assert validate_workflow(wf) == []

    def test_duplicate_node_ids(self) -> None:
        """Two nodes with the same ID should produce an error."""
        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="loader"),
                NodeDef(id="A", block_type="processor"),
            ],
        )
        errors = validate_workflow(wf)
        assert any("Duplicate node id: 'A'" in e for e in errors)


# ---------------------------------------------------------------------------
# Edge format validation
# ---------------------------------------------------------------------------


class TestValidatorEdgeFormat:
    """Check 2 & 3: edge format and node references."""

    def test_invalid_edge_format_no_colon(self) -> None:
        """Edge source/target without ':' separator is invalid."""
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="A", block_type="loader")],
            edges=[EdgeDef(source="Aout", target="Ain")],
        )
        errors = validate_workflow(wf)
        assert any("invalid port reference format" in e for e in errors)

    def test_invalid_edge_format_empty_parts(self) -> None:
        """Edge with empty node_id or port_name is invalid."""
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="A", block_type="loader")],
            edges=[EdgeDef(source=":port", target="A:in")],
        )
        errors = validate_workflow(wf)
        assert any("invalid port reference format" in e for e in errors)

    def test_invalid_edge_format_empty_port_name(self) -> None:
        """Edge with empty port_name part is invalid."""
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="A", block_type="loader")],
            edges=[EdgeDef(source="A:", target="A:in")],
        )
        errors = validate_workflow(wf)
        assert any("invalid port reference format" in e for e in errors)

    def test_edge_references_nonexistent_node(self) -> None:
        """Edge referencing a node not in the workflow should error."""
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="A", block_type="loader")],
            edges=[EdgeDef(source="A:out", target="Z:in")],
        )
        errors = validate_workflow(wf)
        assert any("Edge references unknown node 'Z'" in e for e in errors)

    def test_edge_references_nonexistent_source_node(self) -> None:
        """Edge with unknown source node should also error."""
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="B", block_type="loader")],
            edges=[EdgeDef(source="X:out", target="B:in")],
        )
        errors = validate_workflow(wf)
        assert any("Edge references unknown node 'X'" in e for e in errors)


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestValidatorCycleDetection:
    """Check 4: cycle detection using engine/dag.py."""

    def test_cycle_detected(self) -> None:
        """A -> B -> C -> A should be reported as a cycle."""
        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="t"),
                NodeDef(id="B", block_type="t"),
                NodeDef(id="C", block_type="t"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="B:out", target="C:in"),
                EdgeDef(source="C:out", target="A:in"),
            ],
        )
        errors = validate_workflow(wf)
        assert any("Workflow contains a cycle" in e for e in errors)

    def test_self_loop_detected(self) -> None:
        """A single node with an edge to itself is a cycle."""
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="A", block_type="t")],
            edges=[EdgeDef(source="A:out", target="A:in")],
        )
        errors = validate_workflow(wf)
        assert any("Workflow contains a cycle" in e for e in errors)

    def test_no_cycle_valid(self) -> None:
        """A diamond DAG (A -> B, A -> C, B -> D, C -> D) has no cycle."""
        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="t"),
                NodeDef(id="B", block_type="t"),
                NodeDef(id="C", block_type="t"),
                NodeDef(id="D", block_type="t"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="A:out", target="C:in"),
                EdgeDef(source="B:out", target="D:in"),
                EdgeDef(source="C:out", target="D:in"),
            ],
        )
        errors = validate_workflow(wf)
        assert not any("cycle" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Type compatibility
# ---------------------------------------------------------------------------


class TestValidatorTypeCompat:
    """Check 5: port type matching when registry is provided."""

    def test_type_mismatch_with_registry(self) -> None:
        """Array output -> Series input should report a type error."""
        spec_a = _make_spec(
            "producer",
            output_ports=[OutputPort(name="out", accepted_types=[Array])],
        )
        spec_b = _make_spec(
            "consumer",
            input_ports=[InputPort(name="in", accepted_types=[Series])],
        )
        reg = _registry_from_specs(spec_a, spec_b)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="producer"),
                NodeDef(id="B", block_type="consumer"),
            ],
            edges=[EdgeDef(source="A:out", target="B:in")],
        )
        errors = validate_workflow(wf, registry=reg)
        assert any("A:out" in e and "B:in" in e for e in errors)

    def test_compatible_types_valid(self) -> None:
        """Array subclass output -> Array input should be valid.

        Uses a locally-defined Array subclass to exercise the
        subclass-is-compatible path without depending on the
        scistudio-blocks-imaging plugin's Image type.
        """

        class _ArraySub(Array):
            """Local Array subclass for the subclass-compat test."""

        spec_a = _make_spec(
            "producer",
            output_ports=[OutputPort(name="out", accepted_types=[_ArraySub])],
        )
        spec_b = _make_spec(
            "consumer",
            input_ports=[InputPort(name="in", accepted_types=[Array])],
        )
        reg = _registry_from_specs(spec_a, spec_b)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="producer"),
                NodeDef(id="B", block_type="consumer"),
            ],
            edges=[EdgeDef(source="A:out", target="B:in")],
        )
        errors = validate_workflow(wf, registry=reg)
        # No type-compatibility errors expected
        type_errors = [e for e in errors if "A:out" in e and "B:in" in e]
        assert type_errors == []

    def test_no_registry_skips_type_check(self) -> None:
        """Without a registry, only structural + cycle checks are performed."""
        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="producer"),
                NodeDef(id="B", block_type="consumer"),
            ],
            edges=[EdgeDef(source="A:out", target="B:in")],
        )
        errors = validate_workflow(wf, registry=None)
        # No type or dangling port errors since no registry
        assert errors == []

    def test_unknown_block_type_warning(self) -> None:
        """Unregistered block type produces a warning, not a crash."""
        reg = _registry_from_specs()  # empty registry

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="unknown_producer"),
                NodeDef(id="B", block_type="unknown_consumer"),
            ],
            edges=[EdgeDef(source="A:out", target="B:in")],
        )
        errors = validate_workflow(wf, registry=reg)
        assert any("Warning: block type 'unknown_producer' not in registry" in e for e in errors)

    def test_unknown_port_name_warning(self) -> None:
        """Port name not found on the block spec produces a warning."""
        spec_a = _make_spec(
            "producer",
            output_ports=[OutputPort(name="data", accepted_types=[Array])],
        )
        spec_b = _make_spec(
            "consumer",
            input_ports=[InputPort(name="data", accepted_types=[Array])],
        )
        reg = _registry_from_specs(spec_a, spec_b)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="producer"),
                NodeDef(id="B", block_type="consumer"),
            ],
            edges=[EdgeDef(source="A:wrong_port", target="B:data")],
        )
        errors = validate_workflow(wf, registry=reg)
        assert any("Warning: port 'wrong_port' not found on block 'producer'" in e for e in errors)


# ---------------------------------------------------------------------------
# Dangling required input ports
# ---------------------------------------------------------------------------


class TestValidatorDanglingPorts:
    """Check 6: required input ports without incoming edges."""

    def test_dangling_required_port(self) -> None:
        """Required input with no incoming edge should error."""
        spec_b = _make_spec(
            "consumer",
            input_ports=[InputPort(name="in", accepted_types=[Array], required=True)],
        )
        reg = _registry_from_specs(spec_b)

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="B", block_type="consumer")],
        )
        errors = validate_workflow(wf, registry=reg)
        assert any("Node 'B': required input port 'in' has no incoming connection" in e for e in errors)

    def test_draft_mode_skips_dangling_required_port(self) -> None:
        """bug#3: editor autosave (draft mode) must not flag an unconnected
        required input port; run start re-validates in strict mode."""
        spec_b = _make_spec(
            "consumer",
            input_ports=[InputPort(name="in", accepted_types=[Array], required=True)],
        )
        reg = _registry_from_specs(spec_b)
        wf = WorkflowDefinition(nodes=[NodeDef(id="B", block_type="consumer")])

        strict = validate_workflow(wf, registry=reg)
        draft = validate_workflow(wf, registry=reg, mode="draft")

        assert any("required input port 'in'" in e for e in strict)
        assert not any("required input port" in e for e in draft)

    def test_optional_port_no_edge_ok(self) -> None:
        """Optional input with no incoming edge should NOT error."""
        spec_b = _make_spec(
            "consumer",
            input_ports=[InputPort(name="in", accepted_types=[Array], required=False)],
        )
        reg = _registry_from_specs(spec_b)

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="B", block_type="consumer")],
        )
        errors = validate_workflow(wf, registry=reg)
        dangling_errors = [e for e in errors if "required input port" in e]
        assert dangling_errors == []

    def test_connected_required_port_no_error(self) -> None:
        """Required input that IS connected should not produce a dangling-port error."""
        spec_a = _make_spec(
            "producer",
            output_ports=[OutputPort(name="out", accepted_types=[Array])],
        )
        spec_b = _make_spec(
            "consumer",
            input_ports=[InputPort(name="in", accepted_types=[Array], required=True)],
        )
        reg = _registry_from_specs(spec_a, spec_b)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="producer"),
                NodeDef(id="B", block_type="consumer"),
            ],
            edges=[EdgeDef(source="A:out", target="B:in")],
        )
        errors = validate_workflow(wf, registry=reg)
        dangling_errors = [e for e in errors if "required input port" in e]
        assert dangling_errors == []

    def test_unknown_block_type_skips_dangling_check(self) -> None:
        """Unknown block type should skip dangling port checks (no crash)."""
        reg = _registry_from_specs()  # empty

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="X", block_type="mystery")],
        )
        errors = validate_workflow(wf, registry=reg)
        # Should not crash; no dangling-port error for unknown types
        dangling_errors = [e for e in errors if "required input port" in e]
        assert dangling_errors == []

    def test_multiple_required_ports_partial_connection(self) -> None:
        """Node with two required inputs, only one connected: one dangling error."""
        spec_a = _make_spec(
            "producer",
            output_ports=[OutputPort(name="out", accepted_types=[Array])],
        )
        spec_b = _make_spec(
            "dual_consumer",
            input_ports=[
                InputPort(name="left", accepted_types=[Array], required=True),
                InputPort(name="right", accepted_types=[Array], required=True),
            ],
        )
        reg = _registry_from_specs(spec_a, spec_b)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="producer"),
                NodeDef(id="B", block_type="dual_consumer"),
            ],
            edges=[EdgeDef(source="A:out", target="B:left")],
        )
        errors = validate_workflow(wf, registry=reg)
        dangling = [e for e in errors if "required input port" in e]
        assert len(dangling) == 1
        assert "'right'" in dangling[0]


# ---------------------------------------------------------------------------
# Variadic port cardinality (Check 7)
# ---------------------------------------------------------------------------


class TestValidatorVariadicCardinality:
    """Check 7: variadic port count within min/max limits."""

    def test_variadic_input_below_min(self) -> None:
        """Block with min_input_ports=2 but only 1 effective input port should error."""
        spec = BlockSpec(
            name="variadic_block",
            variadic_inputs=True,
            min_input_ports=2,
            input_ports=[InputPort(name="in0", accepted_types=[Array])],
            output_ports=[OutputPort(name="out", accepted_types=[Array])],
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="V", block_type="variadic_block")],
        )
        errors = validate_workflow(wf, registry=reg)
        assert any("variadic input port count 1" in e and "below minimum 2" in e for e in errors)

    def test_variadic_input_above_max(self) -> None:
        """Block with max_input_ports=1 but 2 effective input ports should error."""
        spec = BlockSpec(
            name="variadic_block",
            variadic_inputs=True,
            max_input_ports=1,
            input_ports=[
                InputPort(name="in0", accepted_types=[Array]),
                InputPort(name="in1", accepted_types=[Array]),
            ],
            output_ports=[OutputPort(name="out", accepted_types=[Array])],
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="V", block_type="variadic_block")],
        )
        errors = validate_workflow(wf, registry=reg)
        assert any("variadic input port count 2" in e and "exceeds maximum 1" in e for e in errors)

    def test_variadic_output_below_min(self) -> None:
        """Block with min_output_ports=2 but only 1 effective output port should error."""
        spec = BlockSpec(
            name="variadic_block",
            variadic_outputs=True,
            min_output_ports=2,
            input_ports=[InputPort(name="in", accepted_types=[Array])],
            output_ports=[OutputPort(name="out0", accepted_types=[Array])],
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="V", block_type="variadic_block")],
        )
        errors = validate_workflow(wf, registry=reg)
        assert any("variadic output port count 1" in e and "below minimum 2" in e for e in errors)

    def test_variadic_output_above_max(self) -> None:
        """Block with max_output_ports=1 but 2 effective output ports should error."""
        spec = BlockSpec(
            name="variadic_block",
            variadic_outputs=True,
            max_output_ports=1,
            input_ports=[InputPort(name="in", accepted_types=[Array])],
            output_ports=[
                OutputPort(name="out0", accepted_types=[Array]),
                OutputPort(name="out1", accepted_types=[Array]),
            ],
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="V", block_type="variadic_block")],
        )
        errors = validate_workflow(wf, registry=reg)
        assert any("variadic output port count 2" in e and "exceeds maximum 1" in e for e in errors)

    def test_variadic_within_limits_no_error(self) -> None:
        """Block with port count within min/max should produce no cardinality errors."""
        spec = BlockSpec(
            name="variadic_block",
            variadic_inputs=True,
            min_input_ports=1,
            max_input_ports=3,
            input_ports=[
                InputPort(name="in0", accepted_types=[Array]),
                InputPort(name="in1", accepted_types=[Array]),
            ],
            output_ports=[OutputPort(name="out", accepted_types=[Array])],
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="V", block_type="variadic_block")],
        )
        errors = validate_workflow(wf, registry=reg)
        cardinality_errors = [e for e in errors if "variadic" in e]
        assert cardinality_errors == []

    def test_non_variadic_skips_cardinality_check(self) -> None:
        """Non-variadic blocks should never produce cardinality errors."""
        spec = BlockSpec(
            name="normal_block",
            variadic_inputs=False,
            variadic_outputs=False,
            min_input_ports=5,  # would fail if checked
            input_ports=[InputPort(name="in", accepted_types=[Array])],
            output_ports=[OutputPort(name="out", accepted_types=[Array])],
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[NodeDef(id="N", block_type="normal_block")],
        )
        errors = validate_workflow(wf, registry=reg)
        cardinality_errors = [e for e in errors if "variadic" in e]
        assert cardinality_errors == []


# ---------------------------------------------------------------------------
# Issue #680: AppBlock duplicate output-port extension validation (Check 8)
# ---------------------------------------------------------------------------


class TestValidatorAppBlockDuplicateExtensions:
    """Check 8: variadic-output blocks must not declare two ports with the same extension."""

    def test_duplicate_extension_emits_error(self) -> None:
        spec = BlockSpec(
            name="app_block_test",
            variadic_inputs=True,
            variadic_outputs=True,
            input_ports=[],
            output_ports=[],
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(
                    id="A",
                    block_type="app_block_test",
                    config={
                        "output_ports": [
                            {"name": "images", "types": ["DataObject"], "extension": "tif"},
                            {"name": "masks", "types": ["DataObject"], "extension": "tif"},
                        ]
                    },
                )
            ],
        )
        errors = validate_workflow(wf, registry=reg)
        dup_errors = [e for e in errors if "Duplicate extension" in e]
        assert len(dup_errors) == 1
        assert "'tif'" in dup_errors[0]
        assert "images" in dup_errors[0]
        assert "masks" in dup_errors[0]

    def test_duplicate_extension_is_case_insensitive(self) -> None:
        spec = BlockSpec(
            name="app_block_case",
            variadic_inputs=True,
            variadic_outputs=True,
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(
                    id="A",
                    block_type="app_block_case",
                    config={
                        "output_ports": [
                            {"name": "images", "types": ["DataObject"], "extension": "TIF"},
                            {"name": "masks", "types": ["DataObject"], "extension": ".tif"},
                        ]
                    },
                )
            ],
        )
        errors = validate_workflow(wf, registry=reg)
        dup_errors = [e for e in errors if "Duplicate extension" in e]
        assert len(dup_errors) == 1

    def test_distinct_extensions_pass(self) -> None:
        spec = BlockSpec(
            name="app_block_ok",
            variadic_inputs=True,
            variadic_outputs=True,
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(
                    id="A",
                    block_type="app_block_ok",
                    config={
                        "output_ports": [
                            {"name": "images", "types": ["DataObject"], "extension": "tif"},
                            {"name": "tables", "types": ["DataObject"], "extension": "csv"},
                        ]
                    },
                )
            ],
        )
        errors = validate_workflow(wf, registry=reg)
        dup_errors = [e for e in errors if "Duplicate extension" in e]
        assert dup_errors == []

    def test_duplicate_extension_under_params_envelope(self) -> None:
        """#690 audit fix: the frontend writes ``output_ports`` under
        ``config.params.output_ports`` (the :class:`BlockConfig` two-tier
        layout). Check 8 must read from that nested path so real configs
        produced by the port editor are validated, not silently skipped.
        """
        spec = BlockSpec(
            name="app_block_params",
            variadic_inputs=True,
            variadic_outputs=True,
            input_ports=[],
            output_ports=[],
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(
                    id="A",
                    block_type="app_block_params",
                    config={
                        "params": {
                            "output_ports": [
                                {"name": "images", "types": ["DataObject"], "extension": "tif"},
                                {"name": "masks", "types": ["DataObject"], "extension": "tif"},
                            ]
                        }
                    },
                )
            ],
        )
        errors = validate_workflow(wf, registry=reg)
        dup_errors = [e for e in errors if "Duplicate extension" in e]
        assert len(dup_errors) == 1
        assert "'tif'" in dup_errors[0]
        assert "images" in dup_errors[0]
        assert "masks" in dup_errors[0]

    def test_non_variadic_block_skips_extension_check(self) -> None:
        spec = BlockSpec(
            name="static_block",
            variadic_inputs=False,
            variadic_outputs=False,
        )
        reg = _registry_from_specs(spec)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(
                    id="A",
                    block_type="static_block",
                    config={
                        "output_ports": [
                            {"name": "a", "extension": "tif"},
                            {"name": "b", "extension": "tif"},
                        ]
                    },
                )
            ],
        )
        errors = validate_workflow(wf, registry=reg)
        dup_errors = [e for e in errors if "Duplicate extension" in e]
        assert dup_errors == []


# ---------------------------------------------------------------------------
# Issue #1282: _is_codeblock_spec must identify the concrete CodeBlock only
# ---------------------------------------------------------------------------


class TestIsCodeBlockSpecNarrowing:
    """Codex P1 (#1282): ``_is_codeblock_spec`` previously matched any
    spec with ``base_category == 'code'``, causing
    :func:`validate_codeblock_config` to run against non-CodeBlock
    code-category specs and emit spurious ``script_path`` / port-field
    errors. The check now requires concrete CodeBlock identity (name,
    type_name, or module+class)."""

    def test_concrete_codeblock_spec_is_identified(self) -> None:
        from scistudio.workflow.validator import _is_codeblock_spec

        # Canonical CodeBlock v2 spec — must still be identified by every
        # discriminator the validator supports.
        canonical = BlockSpec(
            name="Code Block",
            type_name="code_block",
            base_category="code",
            module_path="scistudio.blocks.code.code_block",
            class_name="CodeBlock",
        )
        assert _is_codeblock_spec(canonical) is True

    def test_codeblock_identified_by_module_and_class_path(self) -> None:
        from scistudio.workflow.validator import _is_codeblock_spec

        # Module + class path alone (e.g. a stub with non-canonical display
        # name) still identifies CodeBlock for back-compat with existing
        # registry shapes.
        by_module = BlockSpec(
            name="custom",
            type_name="custom",
            base_category="code",
            module_path="scistudio.blocks.code.code_block",
            class_name="CodeBlock",
        )
        assert _is_codeblock_spec(by_module) is True

    def test_non_codeblock_code_category_spec_is_not_identified(self) -> None:
        from scistudio.workflow.validator import _is_codeblock_spec

        # Synthetic code-category block that is NOT CodeBlock — would
        # previously have been misidentified via ``base_category == "code"``
        # and crashed CodeBlock v2 validation with spurious errors.
        synthetic = BlockSpec(
            name="my_custom_runner",
            type_name="my_custom_runner",
            base_category="code",
            module_path="my_plugin.runner",
            class_name="MyCustomRunner",
        )
        assert _is_codeblock_spec(synthetic) is False

    def test_non_codeblock_code_category_does_not_trigger_codeblock_validation(self) -> None:
        """End-to-end: a code-category spec that isn't CodeBlock must not
        surface ``script_path``-missing / port-field errors when validated.

        Before the narrowing, ``validate_codeblock_config`` would run
        against this spec and complain about a missing ``script_path``
        and unexpected ``input_ports`` / ``output_ports`` fields.
        """

        # Construct a code-category spec that is unambiguously NOT
        # CodeBlock (different name, type_name, module, class).
        synthetic = BlockSpec(
            name="custom_runner",
            type_name="custom_runner",
            base_category="code",
            module_path="my_plugin.runner",
            class_name="MyCustomRunner",
        )
        reg = _registry_from_specs(synthetic)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(
                    id="r1",
                    block_type="custom_runner",
                    # No params at all — under the old broad check, this
                    # would surface "CodeBlock script_path" errors etc.
                    config={"params": {}},
                )
            ],
        )

        errors = validate_workflow(wf, registry=reg)

        # No CodeBlock v2 diagnostics should be emitted for this non-CodeBlock spec.
        assert not any("CodeBlock" in error and "r1" in error for error in errors), (
            f"unexpected CodeBlock diagnostics on a non-CodeBlock spec: {errors}"
        )
