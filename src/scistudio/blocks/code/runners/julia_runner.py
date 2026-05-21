"""JuliaRunner — Julia code execution via julia subprocess.

ADR-017: All block execution in isolated subprocesses. JuliaRunner spawns
a julia child process for Julia code execution.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class JuliaRunner:
    """Julia code execution environment via julia subprocess.

    ADR-017: Spawns julia as a child process. Data is transferred
    via JSON serialization through temporary files.
    """

    def execute_inline(self, script: str, namespace: dict[str, Any]) -> dict[str, Any]:
        """Execute Julia script string via julia subprocess.

        Writes the script to a temporary file, passes namespace as JSON,
        and reads results from a temporary output file.
        """
        with tempfile.TemporaryDirectory(prefix="scistudio_jl_") as tmp_dir:
            tmp = Path(tmp_dir)
            input_path = tmp / "inputs.json"
            output_path = tmp / "outputs.json"
            script_path = tmp / "script.jl"

            input_path.write_text(json.dumps(namespace, default=str), encoding="utf-8")

            jl_code = (
                f"using JSON\n"
                f'inputs = JSON.parsefile("{input_path.as_posix()}")\n'
                f"for (k, v) in inputs\n"
                f"    @eval $(Symbol(k)) = $v\n"
                f"end\n"
                f"{script}\n"
                f"# Collect all non-module variables defined in Main\n"
                f"result = Dict{{String, Any}}()\n"
                f"for name in names(Main; all=false)\n"
                f"    val = getfield(Main, name)\n"
                f'    if !(val isa Module) && string(name) != "inputs"'
                f' && string(name) != "result"\n'
                f"        result[string(name)] = val\n"
                f"    end\n"
                f"end\n"
                f'open("{output_path.as_posix()}", "w") do f\n'
                f"    JSON.print(f, result)\n"
                f"end\n"
            )
            script_path.write_text(jl_code, encoding="utf-8")

            proc = subprocess.run(
                ["julia", str(script_path)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Julia failed (exit {proc.returncode}): {proc.stderr}")

            if output_path.exists():
                result: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
                return result
            return {}

    def execute_script(
        self,
        script_path: str | Path,
        entry_function: str,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Julia function from script file via julia subprocess."""
        path = Path(script_path)
        if not path.exists():
            raise FileNotFoundError(f"Julia script not found: {path}")

        with tempfile.TemporaryDirectory(prefix="scistudio_jl_") as tmp_dir:
            tmp = Path(tmp_dir)
            input_path = tmp / "inputs.json"
            config_path = tmp / "config.json"
            output_path = tmp / "outputs.json"
            wrapper_path = tmp / "wrapper.jl"

            input_path.write_text(json.dumps(inputs, default=str), encoding="utf-8")
            config_path.write_text(json.dumps(config, default=str), encoding="utf-8")

            wrapper = (
                f"using JSON\n"
                f'include("{path.as_posix()}")\n'
                f'inputs = JSON.parsefile("{input_path.as_posix()}")\n'
                f'config = JSON.parsefile("{config_path.as_posix()}")\n'
                f"result = {entry_function}(inputs, config)\n"
                f'open("{output_path.as_posix()}", "w") do f\n'
                f"    JSON.print(f, result)\n"
                f"end\n"
            )
            wrapper_path.write_text(wrapper, encoding="utf-8")

            proc = subprocess.run(
                ["julia", str(wrapper_path)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Julia failed (exit {proc.returncode}): {proc.stderr}")

            if output_path.exists():
                result: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
                return result
            return {}
