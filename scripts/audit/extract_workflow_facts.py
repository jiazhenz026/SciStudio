"""Extract workflow facts from `.workflow/schema-v2.yaml` (ADR-042 §7.5.3).

The workflow extractor reads the v2 YAML schema and produces a
:class:`scieasy.qa.schemas.facts.WorkflowFacts` instance describing:

- ``stage_count``: number of declared stages (must equal the v2 ADR §19.2 set of 7).
- ``stages``: ordered list of stage IDs.
- ``blocking_validations``: per-stage list of validator IDs that block advance.

This script is invoked by :mod:`scripts.audit.generate_facts` and by the
per-namespace test in ``tests/qa/test_facts_extraction.py``.

Reads
-----
``.workflow/schema-v2.yaml`` — see ADR-042 §19 and Phase 1H sub-PR 1 (#1145).

References
----------
ADR-042 §7.5.3 — generation table (workflow namespace row).
ADR-042 §19.2 — the seven stages (canonical list).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa.schemas.facts import WorkflowFacts


def _default_schema_path() -> Path:
    """Return the repo-root-relative path to ``.workflow/schema-v2.yaml``."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".workflow" / "schema-v2.yaml").is_file():
            return parent / ".workflow" / "schema-v2.yaml"
        if (parent / "pyproject.toml").is_file():
            # Allow returning a non-existent path so the caller can surface a
            # clean error message rather than walking past the repo root.
            return parent / ".workflow" / "schema-v2.yaml"
    raise FileNotFoundError("could not locate repo root from extract_workflow_facts.py")


def extract(schema_path: Path | None = None) -> WorkflowFacts:
    """Read ``.workflow/schema-v2.yaml`` and return a :class:`WorkflowFacts` instance.

    Args:
        schema_path: Optional explicit path. Defaults to the repo-root
            ``.workflow/schema-v2.yaml`` discovered by walking up from this
            file's location.

    Raises:
        FileNotFoundError: If the schema YAML is absent.
        ValueError: If the YAML is malformed (missing ``stages`` key).
    """
    path = schema_path or _default_schema_path()
    if not path.is_file():
        raise FileNotFoundError(f"workflow schema not found: {path}")

    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    stages_raw = raw.get("stages")
    if not isinstance(stages_raw, list) or not stages_raw:
        raise ValueError(f"workflow schema has no 'stages' list: {path}")

    stages: list[str] = []
    blocking: dict[str, list[str]] = {}
    for stage in stages_raw:
        if not isinstance(stage, dict):
            raise ValueError(f"stage entry is not a mapping: {stage!r}")
        sid = stage.get("id")
        if not isinstance(sid, str):
            raise ValueError(f"stage missing 'id': {stage!r}")
        stages.append(sid)
        # Per ADR-042 §19.2/§19.5, "validations" entries are the blocking
        # validator IDs. Stages with no validations get an empty list.
        validations = stage.get("validations") or []
        if not isinstance(validations, list):
            raise ValueError(f"stage '{sid}' has non-list 'validations': {validations!r}")
        blocking[sid] = [str(v) for v in validations]

    return WorkflowFacts(
        stage_count=len(stages),
        stages=stages,
        blocking_validations=blocking,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints a JSON dump of the workflow facts to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Path to .workflow/schema-v2.yaml (defaults to repo-root discovery).",
    )
    args = parser.parse_args(argv)
    facts = extract(args.schema)
    print(json.dumps(facts.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
