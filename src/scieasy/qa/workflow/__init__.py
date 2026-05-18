"""SciEasy QA workflow-v2 package (ADR-042 §19).

This package owns the workflow-v2 gate machinery: stage definitions,
per-stage validators, and the runtime context shared between them.

Phase 1A-b (this initial shipment) ships ONLY the gate-level pydantic
shapes (``StageContext``, ``ValidationResult``, ``Validator`` Protocol,
``StageDefinition`` dataclass) in ``gate.py``. The seven concrete
stage validators arrive in TC-1H.2 under
``scieasy.qa.workflow.validators``; the YAML stage definitions arrive
in ``.workflow/schema-v2.yaml`` (TC-1H.1).
"""
