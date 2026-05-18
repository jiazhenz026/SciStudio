"""Round-trip tests for Workflow v2 validator registry (TC-1H.2).

These tests enforce the contract between ``.workflow/schema-v2.yaml``
and ``scieasy.qa.workflow.validators._registry.VALIDATORS``:

1. Every ``validator_id`` referenced in the YAML must resolve via
   ``get_validator``.
2. Every registered validator must satisfy the ``Validator`` runtime
   protocol (``StartAndRouteShapeValidator`` etc. all expose
   ``validator_id``, ``blocking``, and ``__call__``).
3. No orphan validators (every entry in ``VALIDATORS`` is referenced
   by at least one stage in the schema).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scieasy.qa.workflow.gate import StageContext, Validator
from scieasy.qa.workflow.validators import VALIDATORS, get_validator

SCHEMA_V2_PATH = Path(__file__).resolve().parents[2] / ".workflow" / "schema-v2.yaml"


@pytest.fixture(scope="module")
def schema_v2() -> dict:
    with open(SCHEMA_V2_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_validator_ids_in_schema(schema: dict) -> set[str]:
    out: set[str] = set()
    for stage in schema["stages"]:
        out.update(stage.get("validations", []))
    return out


class TestRegistryRoundTrip:
    def test_schema_v2_loads(self, schema_v2):
        assert schema_v2["version"].startswith("2.")
        assert isinstance(schema_v2["stages"], list)
        assert len(schema_v2["stages"]) == 7  # ADR-042 §19.2

    def test_every_schema_validator_id_resolves(self, schema_v2):
        for vid in _all_validator_ids_in_schema(schema_v2):
            v = get_validator(vid)
            assert v is not None
            assert v.validator_id == vid

    def test_no_orphan_registered_validators(self, schema_v2):
        schema_ids = _all_validator_ids_in_schema(schema_v2)
        registered_ids = set(VALIDATORS.keys())
        orphans = registered_ids - schema_ids
        assert not orphans, f"Validators in registry but not in schema-v2.yaml: {orphans}"

    def test_every_validator_satisfies_protocol(self):
        # The Protocol is @runtime_checkable so isinstance() works.
        for vid, v in VALIDATORS.items():
            assert isinstance(v, Validator), f"{vid} fails Validator Protocol"

    def test_validator_id_matches_dict_key(self):
        for vid, v in VALIDATORS.items():
            assert v.validator_id == vid, f"Registry key {vid!r} != validator.validator_id {v.validator_id!r}"

    def test_get_validator_raises_keyerror_for_unknown_id(self):
        with pytest.raises(KeyError) as excinfo:
            get_validator("nonexistent.validator")
        assert "Unknown validator_id" in str(excinfo.value)
        assert "_registry" in str(excinfo.value)

    def test_stage_ids_match_adr_042_section_19_2(self, schema_v2):
        # Authoritative seven-stage list (ADR-042 §19.2 verbatim).
        expected = [
            "start_and_route",
            "create_issue",
            "change_plan",
            "branch",
            "implement_validate",
            "complete_artifacts",
            "submit_reconcile",
        ]
        actual = [s["id"] for s in schema_v2["stages"]]
        assert actual == expected

    def test_stage_requires_form_a_dag(self, schema_v2):
        # Verify each stage's `requires` is a prefix-only DAG (each
        # stage's prerequisites are entirely declared above it).
        seen: set[str] = set()
        for stage in schema_v2["stages"]:
            for req in stage.get("requires", []):
                assert req in seen, (
                    f"stage {stage['id']!r} requires {req!r} which is not declared earlier in schema-v2.yaml"
                )
            seen.add(stage["id"])

    def test_each_stage_has_guidance_template(self, schema_v2):
        for stage in schema_v2["stages"]:
            assert stage.get("guidance_template"), f"stage {stage['id']!r} missing guidance_template"

    def test_each_stage_has_auto_advance_flag(self, schema_v2):
        for stage in schema_v2["stages"]:
            assert "auto_advance" in stage
            assert isinstance(stage["auto_advance"], bool)


class TestValidatorsAreCallableWithStageContext:
    """Smoke-check that every registered validator accepts a StageContext."""

    def _empty_ctx(self) -> StageContext:
        return StageContext(
            task_id="smoke",
            stage_name="any",
            repo_root="/tmp",
            pr_number=None,
            branch="",
            declared_data={},
        )

    def test_all_validators_return_validation_result(self):
        from scieasy.qa.workflow.gate import ValidationResult

        ctx = self._empty_ctx()
        for vid, v in VALIDATORS.items():
            result = v(ctx)
            assert isinstance(result, ValidationResult), f"{vid} returned {type(result)} instead of ValidationResult"
            assert result.status in {"pass", "fail", "skip"}
            assert result.validator_id == vid
