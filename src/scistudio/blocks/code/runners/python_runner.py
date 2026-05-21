"""PythonRunner — Python code execution via exec/importlib.

ADR-017: All block execution happens in isolated subprocesses. PythonRunner
operates INSIDE that subprocess — so exec() and importlib are safe here.
The subprocess isolation is handled by the engine layer (spawn_block_process).
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path
from typing import Any


class PythonRunner:
    """Python code execution environment.

    ADR-017: This runner executes inside an already-isolated subprocess.
    The engine's LocalRunner spawns the subprocess; this runner handles
    the actual Python code execution within it.

    Inline mode:
        Serializes script + namespace, executes via exec() in isolated
        namespace, returns public variables as output dict.

    Script mode:
        Loads user script via importlib, calls the named entry function
        with inputs and config, returns the function's return value.
    """

    def execute_inline(self, script: str, namespace: dict[str, Any]) -> dict[str, Any]:
        """Execute *script* source code within *namespace* and return results.

        Runs the script via ``exec()`` inside a copy of *namespace*.
        Returns all public (non-underscore) variables that were created
        or modified by the script, excluding the original namespace keys
        and imported modules.
        """
        exec_ns: dict[str, Any] = dict(namespace)
        original_keys = set(exec_ns.keys())
        exec(script, exec_ns)
        # Return only new public variables, excluding original namespace keys
        # and imported modules (which are execution noise, not results)
        return {
            k: v
            for k, v in exec_ns.items()
            if k not in original_keys
            and not k.startswith("_")
            and k != "__builtins__"
            and not isinstance(v, types.ModuleType)
        }

    def execute_script(
        self,
        script_path: str | Path,
        entry_function: str,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute *entry_function* from *script_path* with *inputs* and *config*.

        Loads the script as a Python module via importlib, resolves the named
        function, and calls it with the provided inputs and config.
        """
        path = Path(script_path)
        if not path.exists():
            raise FileNotFoundError(f"Script not found: {path}")

        spec = importlib.util.spec_from_file_location("user_block_script", str(path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load script: {path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        func = getattr(module, entry_function, None)
        if func is None:
            raise AttributeError(f"Script {path} has no function '{entry_function}'")

        result = func(inputs, config)
        if not isinstance(result, dict):
            return {"_result": result}
        return result
