"""Schema reference generator — ADR-044 §10.3 (TC-1D.6).

Emits one ``docs/user/reference/schemas/<name>.md`` file per pydantic
model discovered in ``src/scieasy/qa/schemas/`` and related modules.
Each file uses ``autodoc-pydantic`` directive format and carries
``generation: auto`` frontmatter.

Entry-point signature per ADR-044 §11.5::

    def generate(docs_root: Path, output: Path) -> None: ...
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any

# Modules to scan for pydantic models.
_SCHEMA_MODULES = [
    "scieasy.qa.schemas.report",
    "scieasy.qa.schemas.frontmatter",
    "scieasy.qa.schemas.classification",
    "scieasy.qa.schemas.facts",
    "scieasy.qa.schemas.governance",
    "scieasy.qa.schemas.identity",
    "scieasy.qa.schemas.maintainers",
    "scieasy.qa.schemas.tracker",
    "scieasy.qa.schemas.test_quality",
    "scieasy.qa.schemas.codemod",
    "scieasy.qa.docs.schemas",
]

_FILE_TEMPLATE = """\
---
generation: auto
source.last_generated_sha: {source_sha}
---

<!-- generated — do not hand-edit; re-run `python -m scieasy.qa.docs.generators.schema_reference` -->

# `{class_name}`

**Module**: `{module_path}`

```{{eval-rst}}
.. autopydantic_model:: {full_path}
   :model-show-json: False
   :model-show-config-summary: True
   :model-show-validator-summary: True
   :member-order: bysource
```
"""


def generate(
    docs_root: Path,
    output: Path,
    source_sha: str = "unknown",
) -> None:
    """Emit per-schema Markdown files under *output* directory.

    Walks ``_SCHEMA_MODULES``, discovers all Pydantic ``BaseModel``
    subclasses, and writes one ``.md`` file per model to
    ``output/<schema-name>.md``.

    Parameters
    ----------
    docs_root:
        Root of the Sphinx source directory (unused here but kept for
        API symmetry).
    output:
        Destination *directory*.  Individual files are written as
        ``<ClassName>.md`` under this directory.
    source_sha:
        Git SHA recorded in the frontmatter for drift detection.
    """
    output.mkdir(parents=True, exist_ok=True)

    models = _collect_models()
    for class_name, full_path, _cls in models:
        file_path = output / f"{class_name}.md"
        file_path.write_text(
            _FILE_TEMPLATE.format(
                source_sha=source_sha,
                class_name=class_name,
                module_path=full_path.rsplit(".", 1)[0],
                full_path=full_path,
            ),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _is_pydantic_model(obj: Any) -> bool:
    """Return True if *obj* is a concrete pydantic BaseModel subclass."""
    try:
        from pydantic import BaseModel  # type: ignore[import-untyped]

        return inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel
    except ImportError:
        return False


def _collect_models() -> list[tuple[str, str, Any]]:
    """Return (class_name, full_dotted_path, class) for all discovered models."""
    seen: set[str] = set()
    results: list[tuple[str, str, Any]] = []

    for module_name in _SCHEMA_MODULES:
        try:
            mod: ModuleType = importlib.import_module(module_name)
        except ImportError:
            continue
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if not _is_pydantic_model(obj):
                continue
            full_path = f"{obj.__module__}.{obj.__qualname__}"
            if full_path in seen:
                continue
            seen.add(full_path)
            results.append((name, full_path, obj))

    results.sort(key=lambda r: r[0])
    return results
