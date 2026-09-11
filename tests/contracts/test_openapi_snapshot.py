"""The committed OpenAPI snapshot matches the backend (#2297).

Frontend tests validate their backend mocks against
``tests/contracts/openapi.json``. If the backend's HTTP surface changes and the
snapshot does not, those mocks would be checked against a contract the backend
no longer honours — so this test regenerates the document and fails on any
difference, naming what moved and how to refresh the snapshot.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

_REGENERATE = "python tests/contracts/openapi_snapshot.py --write"


def _load_snapshot_module() -> ModuleType:
    path = Path(__file__).with_name("openapi_snapshot.py")
    spec = importlib.util.spec_from_file_location("scistudio_tests_openapi_snapshot", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operations(spec: dict[str, Any]) -> dict[str, Any]:
    ops: dict[str, Any] = {}
    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                ops[f"{method.upper()} {path}"] = op
    return ops


def _describe_drift(committed: dict[str, Any], current: dict[str, Any]) -> str:
    lines: list[str] = []
    old_ops, new_ops = _operations(committed), _operations(current)
    for key in sorted(new_ops.keys() - old_ops.keys()):
        lines.append(f"  + operation {key}")
    for key in sorted(old_ops.keys() - new_ops.keys()):
        lines.append(f"  - operation {key}")
    for key in sorted(old_ops.keys() & new_ops.keys()):
        if old_ops[key] != new_ops[key]:
            lines.append(f"  ~ operation {key}")
    old_schemas = committed.get("components", {}).get("schemas", {})
    new_schemas = current.get("components", {}).get("schemas", {})
    for name in sorted(new_schemas.keys() - old_schemas.keys()):
        lines.append(f"  + schema {name}")
    for name in sorted(old_schemas.keys() - new_schemas.keys()):
        lines.append(f"  - schema {name}")
    for name in sorted(old_schemas.keys() & new_schemas.keys()):
        if old_schemas[name] != new_schemas[name]:
            lines.append(f"  ~ schema {name}")
    if not lines:
        lines.append("  (top-level fields differ)")
    return "\n".join(lines[:60])


def test_committed_openapi_snapshot_matches_the_backend() -> None:
    module = _load_snapshot_module()
    current = module.build_snapshot()
    committed = json.loads(module.SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert committed == current, (
        "The backend OpenAPI surface no longer matches tests/contracts/openapi.json.\n"
        f"{_describe_drift(committed, current)}\n"
        f"If the change is intended, refresh the snapshot with: {_REGENERATE}\n"
        "and update any frontend test mocks that the refreshed contract rejects."
    )


def test_normalization_keeps_fields_named_like_metadata_keywords() -> None:
    module = _load_snapshot_module()
    spec = {
        "components": {
            "schemas": {
                "Thing": {
                    "description": "dropped",
                    "properties": {"description": {"type": "string", "description": "dropped too"}},
                    "required": ["description"],
                }
            }
        }
    }
    normalized = module._normalize(spec)
    thing = normalized["components"]["schemas"]["Thing"]
    assert "description" not in thing
    assert thing["properties"] == {"description": {"type": "string"}}
    assert thing["required"] == ["description"]
