"""Regression tests for #706 — Tier 1 drop-in blocks in worker subprocess.

The bug: ``BlockRegistry._scan_tier1`` registered each drop-in class under a
synthetic module name ``_scistudio_dropin_<stem>_<mtime>`` that only existed in
the *parent* process's ``sys.modules``. The worker subprocess (ADR-017) is a
fresh interpreter and could not ``importlib.import_module`` that name, so any
execute attempt failed with ``ModuleNotFoundError``.

ADR-056 removed the cause (spec CHANGE-050): a drop-in file is imported under
its own stem from the user import path, and the worker receives that path in
its environment and imports the block by module and class name like any other
block. These tests pin:

  1. The registry names a Tier-1 block by its file stem and stamps nothing on
     the class.
  2. ``build_worker_payload`` carries no file path and no import roots.
  3. End-to-end: a fresh ``python -m scistudio.engine.runners.worker`` process
     given the user import path runs the drop-in, including one that imports a
     helper file beside it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scistudio.blocks.registry import BlockRegistry
from scistudio.core.user_code import user_import_path_env
from scistudio.engine.runners.process_handle import build_worker_payload

# ---------------------------------------------------------------------------
# Shared drop-in source. Echoes config["value"] back out via the "out" port
# as a plain string so the worker doesn't need any DataObject reconstruction.
# ---------------------------------------------------------------------------

DROPIN_SOURCE = """\
from typing import Any, ClassVar
from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.core.types.base import DataObject


class Issue706Echo(Block):
    type_name: ClassVar[str] = "test.issue706_echo"
    name: ClassVar[str] = "Issue706Echo"
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = [OutputPort(name="out", accepted_types=[DataObject])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        cfg_dict = config.model_dump() if hasattr(config, "model_dump") else dict(config)
        return {"out": cfg_dict.get("value", "default")}
"""


def _run_worker(payload: bytes, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "scistudio.engine.runners.worker"],
        input=payload,
        capture_output=True,
        timeout=60,
        env=env,
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Unit-level checks: module name + payload builder.
# ---------------------------------------------------------------------------


class TestRegistryNamesTheModuleByItsStem:
    def test_tier1_spec_and_class_use_the_file_stem(self, tmp_path: Path) -> None:
        """ADR-056: the module is the file's own stem; nothing is stamped on the class."""
        (tmp_path / "echo_block.py").write_text(DROPIN_SOURCE)

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        spec = reg.get_spec("Issue706Echo")
        block = reg.instantiate("Issue706Echo")
        assert spec is not None
        assert spec.module_path == "echo_block"
        assert block.__class__.__module__ == "echo_block"
        assert not hasattr(block.__class__, "_scistudio_file_path")
        assert sys.modules["echo_block"].__file__ == str((tmp_path / "echo_block.py").resolve())

    def test_instantiate_returns_the_registered_class(self, tmp_path: Path) -> None:
        """Instantiation reuses the module the scan imported; the file is not re-executed."""
        (tmp_path / "echo_block.py").write_text(DROPIN_SOURCE)
        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()
        registered = sys.modules["echo_block"].Issue706Echo

        (tmp_path / "echo_block.py").write_text("raise RuntimeError('must not run again')\n")

        assert type(reg.instantiate("Issue706Echo")) is registered

    def test_imported_block_class_in_dropin_is_not_registered_twice(self, tmp_path: Path) -> None:
        """#706 audit: a Block subclass a drop-in *imports* registers from its own module only."""
        (tmp_path / "imports_codeblock.py").write_text(
            DROPIN_SOURCE + "\n" + "from scistudio.blocks.code.code_block import CodeBlock  # noqa: E402, F401\n"
        )

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        assert "Issue706Echo" in reg.all_specs()
        assert [spec.name for spec in reg.all_specs().values() if spec.source == "tier1"] == ["Issue706Echo"]


class TestBuildWorkerPayload:
    def test_payload_carries_no_file_path_and_no_import_roots(self) -> None:
        payload_bytes = build_worker_payload(
            block_class="some.mod.Cls",
            inputs_refs={},
            config={},
            output_dir=None,
        )
        payload = json.loads(payload_bytes.decode("utf-8"))
        assert set(payload) == {"block_class", "inputs", "config", "output_dir"}

    def test_the_removed_parameters_are_gone(self) -> None:
        with pytest.raises(TypeError):
            build_worker_payload(  # type: ignore[call-arg]
                block_class="some.mod.Cls", inputs_refs={}, config={}, block_file_path="x.py"
            )


# ---------------------------------------------------------------------------
# End-to-end: spawn a real worker subprocess and feed it a Tier-1 payload.
# ---------------------------------------------------------------------------


class TestWorkerSubprocessRoundtrip:
    """Spawn ``python -m scistudio.engine.runners.worker`` and verify that a
    Tier-1 drop-in named by its module runs when the user import path is in the
    worker's environment.
    """

    def test_dropin_executes_in_fresh_worker(self, tmp_path: Path) -> None:
        (tmp_path / "echo_block.py").write_text(DROPIN_SOURCE)
        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()
        spec = reg.all_specs().get("Issue706Echo")
        assert spec is not None and spec.source == "tier1"

        payload_bytes = build_worker_payload(
            block_class=f"{spec.module_path}.{spec.class_name}",
            inputs_refs={},
            config={"value": "hello-706"},
            output_dir=None,
        )
        returncode, stdout, stderr = _run_worker(payload_bytes, env={**_base_env(), **user_import_path_env([tmp_path])})

        assert returncode == 0, f"Worker exited {returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        result = json.loads(stdout)
        assert result.get("wire_version") == 1  # #1530: wire-format version stamp
        assert "error" not in result, f"Worker reported error: {result.get('error')}"
        assert result.get("outputs", result).get("out") == "hello-706", f"Unexpected worker result: {result}"

    def test_a_dropin_importing_a_helper_beside_it_runs_in_a_fresh_worker(self, tmp_path: Path) -> None:
        blocks = tmp_path / "blocks"
        blocks.mkdir()
        (blocks / "runtime_dep.py").write_text("VALUE = 'runtime-ok'\n", encoding="utf-8")
        (blocks / "helper_block.py").write_text(
            "from typing import Any\n"
            "\n"
            "import runtime_dep\n"
            "from scistudio.blocks.base.block import Block\n"
            "from scistudio.blocks.base.config import BlockConfig\n"
            "\n"
            "class HelperBlock(Block):\n"
            '    name = "HelperBlock"\n'
            "    input_ports = []\n"
            "    output_ports = []\n"
            '    config_schema = {"type": "object", "properties": {}}\n'
            "\n"
            "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
            "        return {'out': runtime_dep.VALUE}\n",
            encoding="utf-8",
        )
        payload_bytes = build_worker_payload(
            block_class="helper_block.HelperBlock", inputs_refs={}, config={}, output_dir=None
        )

        returncode, stdout, stderr = _run_worker(payload_bytes, env={**_base_env(), **user_import_path_env([blocks])})

        assert returncode == 0, f"Worker exited {returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        result = json.loads(stdout)
        assert "error" not in result, f"Worker reported error: {result.get('error')}"
        assert result.get("outputs", {}).get("out") == "runtime-ok"

    def test_without_the_user_import_path_the_dropin_is_not_found(self, tmp_path: Path) -> None:
        """The environment variable is what makes the module importable (FR-012)."""
        (tmp_path / "echo_block.py").write_text(DROPIN_SOURCE)
        payload_bytes = build_worker_payload(
            block_class="echo_block.Issue706Echo", inputs_refs={}, config={}, output_dir=None
        )

        _returncode, stdout, _stderr = _run_worker(payload_bytes, env=_base_env())

        assert "echo_block" in json.loads(stdout).get("error", "")

    def test_worker_imports_a_builtin_module_by_name(self) -> None:
        """Tier-2 / builtin path: the same ``import_module`` route."""
        from scistudio.blocks.process.builtins.merge import MergeBlock

        block_class_path = f"{MergeBlock.__module__}.{MergeBlock.__qualname__}"
        payload_bytes = build_worker_payload(
            block_class=block_class_path,
            inputs_refs={"data": "scalar-passthrough"},
            config={},
            output_dir=None,
        )
        _returncode, stdout, stderr = _run_worker(payload_bytes)
        # Only the import matters here, not whether MergeBlock can process a
        # scalar input.
        assert MergeBlock.__module__ not in stderr, (
            f"Worker failed to import target module {MergeBlock.__module__}:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )
        assert stdout.strip(), f"Worker produced no stdout:\nSTDERR:\n{stderr}"


def _base_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env.pop("SCISTUDIO_USER_IMPORT_PATH", None)
    return env


# ---------------------------------------------------------------------------
# #1531: broken / hostile drop-in must not crash the palette refresh.
# ---------------------------------------------------------------------------


class TestBrokenDropInDoesNotCrashScan:
    """Issue #1531: a failing or hostile drop-in module must not crash scan().

    Before the #1531 hardening, ``_scan_tier1`` called ``spec.loader.exec_module``
    without its own try/except.  A SyntaxError or any exception raised at
    module top-level (e.g. ``raise RuntimeError("hostile")`` in a drop-in)
    propagated all the way out, killing the palette refresh and leaving the
    palette empty.

    The fix wraps exec_module in a per-file try/except: the offending file is
    logged as a warning and skipped; any other drop-ins in the same or a
    different scan dir continue to register normally.
    """

    def test_broken_dropin_does_not_crash_scan(self, tmp_path: Path) -> None:
        """A drop-in that raises at import time must not crash scan()."""
        broken = tmp_path / "broken_block.py"
        broken.write_text("raise RuntimeError('hostile drop-in')\n")

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        # scan() must not raise — the broken file is skipped with a warning.
        reg.scan()

    def test_broken_dropin_does_not_prevent_good_dropin_from_registering(self, tmp_path: Path) -> None:
        """A broken drop-in must not prevent a good one in the same dir from registering."""
        (tmp_path / "broken_block.py").write_text("raise RuntimeError('hostile')\n")
        (tmp_path / "good_block.py").write_text(DROPIN_SOURCE)

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        assert "Issue706Echo" in reg.all_specs(), (
            "Good drop-in must still register even when another drop-in in the same dir crashes"
        )

    def test_broken_dropin_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """A failing drop-in must emit at least one WARNING log entry referencing the file."""
        import logging

        broken = tmp_path / "hostile_block.py"
        broken.write_text("raise RuntimeError('hostile drop-in')\n")

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        with caplog.at_level(logging.WARNING, logger="scistudio.blocks.registry._scan"):
            reg.scan()

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("hostile_block.py" in r.getMessage() for r in warnings), (
            "Expected a warning log mentioning the broken drop-in filename"
        )

    def test_syntax_error_dropin_does_not_crash_scan(self, tmp_path: Path) -> None:
        """A drop-in with a SyntaxError must be skipped gracefully."""
        bad = tmp_path / "syntax_error_block.py"
        bad.write_text("this is not valid python !!!!\n")

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        # Must not raise SyntaxError (or any other exception).
        reg.scan()
