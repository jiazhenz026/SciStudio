"""Category (b) MCP tools — block authoring helpers (5 tools).

T-ECA-203. See ``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-203.
"""

from __future__ import annotations

import inspect
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from scieasy.ai.agent.mcp._context import _resolve_project_root, get_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# (b.1) read_block_source
# ---------------------------------------------------------------------------


def read_block_source(type_name: str) -> dict[str, Any]:
    """Return the Python source file backing a registered block type.

    Raises
    ------
    KeyError
        If *type_name* is not registered.
    """
    ctx = get_context()
    spec = ctx.block_registry.get_spec(type_name)
    if spec is None:
        raise KeyError(f"Block type '{type_name}' is not registered")

    # Prefer the recorded file_path for Tier 1 blocks; otherwise resolve
    # via importlib for Tier 2 entry-point blocks.
    if spec.file_path:
        path = Path(spec.file_path)
    else:
        try:
            module = ctx.block_registry.instantiate(type_name).__class__.__module__
            mod = sys.modules.get(module)
            if mod is None:
                import importlib

                mod = importlib.import_module(module)
            path = Path(inspect.getfile(mod))
        except Exception as exc:
            raise RuntimeError(f"Could not resolve source file for '{type_name}': {exc}") from exc

    if not path.exists():
        raise FileNotFoundError(f"Block source file not found: {path}")

    return {
        "path": str(path),
        "source": path.read_text(encoding="utf-8"),
        "language": "python",
    }


# ---------------------------------------------------------------------------
# (b.2) list_block_examples
# ---------------------------------------------------------------------------

# Initial curation: a small set of example block paths under
# ``src/scieasy/blocks/{category}/``. Per spec §6 T-ECA-203, v2 makes
# this configurable via project settings. The list is intentionally
# short so the agent has a quick pattern-match reference rather than an
# exhaustive directory dump.
_EXAMPLE_CURATION: dict[str, list[str]] = {
    "io": ["scieasy.blocks.io.loaders.load_data", "scieasy.blocks.io.savers.save_data"],
    "process": [
        "scieasy.blocks.process.builtins.merge",
        "scieasy.blocks.process.builtins.split",
        "scieasy.blocks.process.builtins.data_router",
    ],
    "code": ["scieasy.blocks.code"],
    "app": ["scieasy.blocks.app"],
    "ai": ["scieasy.blocks.ai.ai_block"],
    "subworkflow": ["scieasy.blocks.subworkflow.subworkflow_block"],
}


def list_block_examples(category: str) -> list[dict[str, Any]]:
    """List curated example blocks for a category.

    Raises
    ------
    KeyError
        If *category* is not one of the recognised base categories.
    """
    if category not in _EXAMPLE_CURATION:
        raise KeyError(f"Unknown block category '{category}'. Known: {sorted(_EXAMPLE_CURATION)}")
    import importlib

    out: list[dict[str, Any]] = []
    for mod_path in _EXAMPLE_CURATION[category]:
        try:
            mod = importlib.import_module(mod_path)
            path = Path(inspect.getfile(mod))
            description = (mod.__doc__ or "").strip().split("\n", 1)[0]
        except Exception as exc:  # pragma: no cover - rare import failure
            logger.warning("list_block_examples: could not import %s: %s", mod_path, exc)
            continue
        out.append({"name": mod_path, "path": str(path), "description": description})
    return out


# ---------------------------------------------------------------------------
# (b.3) scaffold_block
# ---------------------------------------------------------------------------

_SCAFFOLD_TEMPLATE = '''"""Block scaffolded by SciEasy MCP scaffold_block.

Edit this file then call ``reload_blocks`` to register the change.
"""

from __future__ import annotations

from typing import Any

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.ports import InputPort, OutputPort


class {class_name}(Block):
    """TODO: describe what this block does."""

    name = "{class_name}"
    description = "TODO: one-line description"
    version = "0.1.0"

    input_ports = [
        # InputPort(name="in", type=DataObject, required=True),
    ]
    output_ports = [
        # OutputPort(name="out", type=DataObject),
    ]
    config_schema: dict[str, Any] = {{
        "type": "object",
        "properties": {{}},
        "required": [],
    }}

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """TODO: implement."""
        raise NotImplementedError
'''


def _snake_to_camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def scaffold_block(name: str, category: str) -> dict[str, Any]:
    """Render a new block module from the project's block templates.

    Writes ``{project}/blocks/{name}.py``. Write-class tool: subject to
    STRICT-mode approval.

    Raises
    ------
    FileExistsError
        If the target path already exists.
    """
    ctx = get_context()
    root = _resolve_project_root(ctx)
    blocks_dir = root / "blocks"
    blocks_dir.mkdir(parents=True, exist_ok=True)
    target = blocks_dir / f"{name}.py"
    if target.exists():
        raise FileExistsError(f"{target} already exists")

    class_name = _snake_to_camel(name) or "MyBlock"
    text = _SCAFFOLD_TEMPLATE.format(class_name=class_name)
    target.write_text(text, encoding="utf-8")
    logger.info("scaffold_block: created %s (category=%s)", target, category)
    return {
        "path": str(target),
        "created": True,
        "template_used": "scieasy.ai.agent.mcp.tools_authoring:_SCAFFOLD_TEMPLATE",
    }


# ---------------------------------------------------------------------------
# (b.4) reload_blocks
# ---------------------------------------------------------------------------


def reload_blocks() -> dict[str, Any]:
    """Hot-reload the block registry."""
    ctx = get_context()
    before = set(ctx.block_registry.all_specs().keys())
    ctx.block_registry.hot_reload()
    after = set(ctx.block_registry.all_specs().keys())
    added = sorted(after - before)
    removed = sorted(before - after)
    logger.info("reload_blocks: added=%s removed=%s", added, removed)
    return {"reloaded": len(after), "added": added, "removed": removed}


# ---------------------------------------------------------------------------
# (b.5) run_block_tests
# ---------------------------------------------------------------------------


def run_block_tests(type_name: str) -> dict[str, Any]:
    """Run pytest against the test module associated with a block.

    Heuristic: ``tests/blocks/test_<lower(name)>.py`` relative to the
    project root.
    """
    ctx = get_context()
    root = _resolve_project_root(ctx)
    test_path = root / "tests" / "blocks" / f"test_{type_name.lower()}.py"
    found = test_path.exists()
    if not found:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"test file not found: {test_path}",
            "test_path": str(test_path),
            "found": False,
        }
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_path), "--tb=short", "-q"],
        capture_output=True,
        text=True,
        cwd=str(root),
        timeout=300,
    )
    logger.info("run_block_tests: %s rc=%d", test_path, proc.returncode)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "test_path": str(test_path),
        "found": True,
    }
