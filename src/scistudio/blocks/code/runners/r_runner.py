"""RRunner — R code execution via Rscript subprocess.

ADR-017: All block execution in isolated subprocesses. RRunner spawns
an Rscript child process for R code execution.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class RRunner:
    """R code execution environment via Rscript subprocess.

    ADR-017: Spawns Rscript as a child process. Data is transferred
    via JSON serialization through temporary files.
    """

    def execute_inline(self, script: str, namespace: dict[str, Any]) -> dict[str, Any]:
        """Execute R script string via Rscript subprocess.

        Writes the script to a temporary file, passes namespace as JSON
        via a temporary input file, and reads results from a temporary
        output file.
        """
        with tempfile.TemporaryDirectory(prefix="scistudio_r_") as tmp_dir:
            tmp = Path(tmp_dir)
            input_path = tmp / "inputs.json"
            output_path = tmp / "outputs.json"
            script_path = tmp / "script.R"

            # Write inputs
            input_path.write_text(json.dumps(namespace, default=str), encoding="utf-8")

            # Build R script that reads inputs, runs user code, writes outputs
            r_code = (
                f'inputs <- jsonlite::fromJSON("{input_path.as_posix()}")\n'
                f"for (nm in names(inputs)) assign(nm, inputs[[nm]])\n"
                f"{script}\n"
                f"env_vars <- ls()\n"
                f'env_vars <- env_vars[!grepl("^\\\\.", env_vars)]\n'
                f'env_vars <- env_vars[env_vars != "inputs"]\n'
                f"result <- lapply(env_vars, function(x) get(x))\n"
                f"names(result) <- env_vars\n"
                f'jsonlite::write_json(result, "{output_path.as_posix()}", '
                f"auto_unbox = TRUE)\n"
            )
            script_path.write_text(r_code, encoding="utf-8")

            proc = subprocess.run(
                ["Rscript", str(script_path)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Rscript failed (exit {proc.returncode}): {proc.stderr}")

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
        """Execute R function from script file via Rscript subprocess.

        Sources the script file, then calls the named function with
        inputs and config passed as JSON.
        """
        path = Path(script_path)
        if not path.exists():
            raise FileNotFoundError(f"R script not found: {path}")

        with tempfile.TemporaryDirectory(prefix="scistudio_r_") as tmp_dir:
            tmp = Path(tmp_dir)
            input_path = tmp / "inputs.json"
            config_path = tmp / "config.json"
            output_path = tmp / "outputs.json"
            wrapper_path = tmp / "wrapper.R"

            input_path.write_text(json.dumps(inputs, default=str), encoding="utf-8")
            config_path.write_text(json.dumps(config, default=str), encoding="utf-8")

            wrapper = (
                f'source("{path.as_posix()}")\n'
                f'inputs <- jsonlite::fromJSON("{input_path.as_posix()}")\n'
                f'config <- jsonlite::fromJSON("{config_path.as_posix()}")\n'
                f"result <- {entry_function}(inputs, config)\n"
                f'jsonlite::write_json(result, "{output_path.as_posix()}", '
                f"auto_unbox = TRUE)\n"
            )
            wrapper_path.write_text(wrapper, encoding="utf-8")

            proc = subprocess.run(
                ["Rscript", str(wrapper_path)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Rscript failed (exit {proc.returncode}): {proc.stderr}")

            if output_path.exists():
                result: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
                return result
            return {}
