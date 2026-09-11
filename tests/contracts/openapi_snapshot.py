"""Normalized snapshot of the backend OpenAPI document (#2297).

The frontend contract tests validate every mocked request and response against
this snapshot (``frontend/src/__tests__/contract/``), so a backend change that
renames, removes, or retypes a field fails the frontend mocks that still use the
old shape. ``test_openapi_snapshot.py`` keeps the committed file honest by
regenerating it and failing when the backend surface has moved.

Normalization keeps the contract and drops what churns without changing it:
free-text metadata (``description``, ``summary``, ``examples``, ``example``) and
generated labels (``operationId``, ``title``) are removed wherever they are a
schema or operation keyword, but never where they are a name — a model field or
a path that happens to be called ``description`` or ``title`` stays.
``operationId`` in particular is not stable: FastAPI builds it from the first
method of a multi-method route's method *set*, so it changes with the process
hash seed. ``info.version`` is pinned so a release bump does not dirty the
snapshot.

Regenerate after an intended backend API change::

    python tests/contracts/openapi_snapshot.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("openapi.json")

_METADATA_KEYS = frozenset({"description", "summary", "examples", "example", "operationId", "title"})

# Mappings whose keys are names (field names, schema names, paths, status codes,
# media types, header names) rather than keywords. Their keys are always kept;
# their values are schema or object nodes again.
_NAME_MAPS = frozenset(
    {
        "properties",
        "patternProperties",
        "$defs",
        "definitions",
        "schemas",
        "paths",
        "responses",
        "content",
        "headers",
        "dependentSchemas",
        "securitySchemes",
        "callbacks",
        "links",
        "encoding",
        "requestBodies",
        "parameters",
    }
)


def _normalize(node: Any, *, keys_are_names: bool = False) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key in sorted(node):
            if not keys_are_names and key in _METADATA_KEYS:
                continue
            out[key] = _normalize(node[key], keys_are_names=key in _NAME_MAPS and not keys_are_names)
        return out
    if isinstance(node, list):
        return [_normalize(item) for item in node]
    return node


def build_snapshot() -> dict[str, Any]:
    """Return the normalized OpenAPI document of the current backend."""
    from scistudio.api.app import create_app

    spec = dict(create_app().openapi())
    info = dict(spec.get("info") or {})
    info["version"] = "snapshot"
    spec["info"] = info
    normalized: dict[str, Any] = _normalize(spec)
    return normalized


def render(spec: dict[str, Any]) -> str:
    """Serialize a snapshot deterministically (sorted keys, LF newlines)."""
    return json.dumps(spec, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="rewrite the committed snapshot")
    args = parser.parse_args(argv)
    spec = build_snapshot()
    if args.write:
        SNAPSHOT_PATH.write_text(render(spec), encoding="utf-8", newline="\n")
        print(f"wrote {SNAPSHOT_PATH} ({len(spec.get('paths', {}))} paths)")
        return 0
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if committed == spec:
        print("OpenAPI snapshot is current")
        return 0
    print("OpenAPI snapshot is stale; run: python tests/contracts/openapi_snapshot.py --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
