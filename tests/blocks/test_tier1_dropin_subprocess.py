"""Regression tests for #706 — Tier 1 drop-in blocks in worker subprocess.

The bug: ``BlockRegistry._scan_tier1`` registers each drop-in class under a
synthetic module name ``_scieasy_dropin_<stem>_<mtime>`` that only exists in
the *parent* process's ``sys.modules``. The worker subprocess (ADR-017) is a
fresh interpreter and cannot ``importlib.import_module`` that synthetic name,
so any execute attempt failed with ``ModuleNotFoundError``.

The fix:
  * Registry stamps ``cls._scieasy_file_path = str(py_file)`` on each Tier-1
    class.
  * ``LocalRunner`` reads that attribute and threads it through
    ``build_worker_payload`` as ``block_file_path``.
  * The worker, on receiving the optional ``block_file_path`` key, reloads
    the module via ``importlib.util.spec_from_file_location`` and registers
    it under the synthetic name in its own ``sys.modules`` before resolving
    the class.

These tests exercise:
  1. Registry stamps ``_scieasy_file_path`` on Tier-1 classes only.
  2. ``build_worker_payload`` includes ``block_file_path`` only when given.
  3. End-to-end: a fresh ``python -m scieasy.engine.runners.worker`` process
     fed a Tier-1 drop-in payload returns the expected output (no
     ``ModuleNotFoundError``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scieasy.blocks.registry import BlockRegistry
from scieasy.engine.runners.process_handle import build_worker_payload

# ---------------------------------------------------------------------------
# Shared drop-in source. Echoes config["value"] back out via the "out" port
# as a plain string so the worker doesn't need any DataObject reconstruction.
# ---------------------------------------------------------------------------

DROPIN_SOURCE = """\
from typing import Any, ClassVar
from scieasy.blocks.base.block import Block
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import OutputPort
from scieasy.core.types.base import DataObject


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


# ---------------------------------------------------------------------------
# Unit-level checks: registry stamp + payload builder.
# ---------------------------------------------------------------------------


class TestRegistryStampsFilePath:
    def test_tier1_class_gets_scieasy_file_path(self, tmp_path: Path) -> None:
        """Tier 1 scan must stamp ``_scieasy_file_path`` on the class."""
        dropin = tmp_path / "echo_block.py"
        dropin.write_text(DROPIN_SOURCE)

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        block = reg.instantiate("Issue706Echo")
        # The attribute lives on the class, not the instance, but ``getattr``
        # walks the MRO either way.
        assert hasattr(block.__class__, "_scieasy_file_path")
        assert block.__class__._scieasy_file_path == str(dropin)  # type: ignore[attr-defined]

    def test_imported_block_class_in_dropin_is_not_stamped(self, tmp_path: Path) -> None:
        """#706 audit: ``dir(module)`` enumerates Block subclasses imported by
        the drop-in file (e.g. a user file that ``from scieasy.blocks.code
        import CodeBlock``).  Those classes must NOT be stamped with the
        drop-in's ``file_path`` and must NOT be re-registered as Tier-1
        specs — otherwise the worker would try to ``spec_from_file_location``
        the wrong source.  Only classes whose ``__module__`` is the synthetic
        drop-in module name should be touched.
        """
        from scieasy.blocks.code.code_block import CodeBlock

        # Drop-in that imports a real concrete Block subclass alongside its
        # own class.  Without the audit guard the import alone is enough to
        # stamp CodeBlock.
        dropin = tmp_path / "imports_codeblock.py"
        dropin.write_text(
            DROPIN_SOURCE + "\n" + "from scieasy.blocks.code.code_block import CodeBlock  # noqa: E402, F401\n"
        )

        original_stamp = getattr(CodeBlock, "_scieasy_file_path", None)
        try:
            reg = BlockRegistry()
            reg.add_scan_dir(tmp_path)
            reg.scan()
            # The drop-in's own class must still be stamped.
            assert "Issue706Echo" in reg.all_specs()
            # The imported CodeBlock must NOT have acquired the drop-in path.
            current_stamp = getattr(CodeBlock, "_scieasy_file_path", None)
            assert current_stamp == original_stamp, (
                f"CodeBlock._scieasy_file_path leaked: was {original_stamp!r}, "
                f"became {current_stamp!r} after scanning a drop-in that merely "
                f"imports CodeBlock"
            )
        finally:
            # Restore the prior state so this test does not leak into other
            # tests in the same session.
            if original_stamp is None:
                # Only delete if we (or a prior test) set it; setattr-then-delete
                # is safe under ``contextlib.suppress``.
                import contextlib as _ctx

                with _ctx.suppress(AttributeError):
                    del CodeBlock._scieasy_file_path
            else:
                CodeBlock._scieasy_file_path = original_stamp

    def test_tier2_or_builtin_class_does_not_have_scieasy_file_path(self) -> None:
        """Built-in blocks (registered via ``_register_builtins`` or Tier 2
        entry points) must NOT carry ``_scieasy_file_path`` — the worker
        relies on its absence to take the standard ``import_module`` path.
        """
        reg = BlockRegistry()
        reg.scan()
        # ``Merge`` is a built-in entry-point block.
        if "Merge" not in reg.all_specs():
            pytest.skip("Merge block not registered; entry-points unavailable in this env")
        block = reg.instantiate("Merge")
        assert not hasattr(block.__class__, "_scieasy_file_path"), (
            "Tier-2 / builtin blocks must not be stamped with _scieasy_file_path"
        )


class TestBuildWorkerPayload:
    def test_payload_omits_block_file_path_when_none(self) -> None:
        payload_bytes = build_worker_payload(
            block_class="some.mod.Cls",
            inputs_refs={},
            config={},
            output_dir=None,
        )
        payload = json.loads(payload_bytes.decode("utf-8"))
        assert "block_file_path" not in payload

    def test_payload_includes_block_file_path_when_set(self, tmp_path: Path) -> None:
        path_str = str(tmp_path / "mod.py")
        payload_bytes = build_worker_payload(
            block_class="some.mod.Cls",
            inputs_refs={},
            config={},
            output_dir=None,
            block_file_path=path_str,
        )
        payload = json.loads(payload_bytes.decode("utf-8"))
        assert payload["block_file_path"] == path_str


# ---------------------------------------------------------------------------
# End-to-end: spawn a real worker subprocess and feed it a Tier-1 payload.
# ---------------------------------------------------------------------------


class TestWorkerSubprocessRoundtrip:
    """Spawn ``python -m scieasy.engine.runners.worker`` and verify that a
    Tier-1 drop-in payload (with ``block_file_path``) executes without
    raising ``ModuleNotFoundError``.
    """

    def test_dropin_executes_in_fresh_worker(self, tmp_path: Path) -> None:
        # 1. Drop a block file into a scan dir.
        dropin = tmp_path / "echo_block.py"
        dropin.write_text(DROPIN_SOURCE)

        # 2. Scan it to (a) verify the registry path and (b) recover the
        #    synthetic module_path the parent assigned.
        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        spec = reg.all_specs().get("Issue706Echo")
        assert spec is not None, "Drop-in scan did not register Issue706Echo"
        assert spec.source == "tier1"
        assert spec.file_path == str(dropin)
        # Synthetic module name from registry._scan_tier1.
        assert spec.module_path.startswith("_scieasy_dropin_")

        block = reg.instantiate("Issue706Echo")
        block_file_path = getattr(block.__class__, "_scieasy_file_path", None)
        assert block_file_path == str(dropin)

        block_class_path = f"{spec.module_path}.{spec.class_name}"

        # 3. Build the payload exactly as LocalRunner would.
        payload_bytes = build_worker_payload(
            block_class=block_class_path,
            inputs_refs={},
            config={"value": "hello-706"},
            output_dir=None,
            block_file_path=block_file_path,
        )

        # 4. Spawn a real fresh worker subprocess.
        proc = subprocess.run(
            [sys.executable, "-m", "scieasy.engine.runners.worker"],
            input=payload_bytes,
            capture_output=True,
            timeout=60,
        )

        # Diagnostic detail on failure: regression for the original symptom
        # is a non-zero exit with ModuleNotFoundError in stdout.
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        assert proc.returncode == 0, f"Worker exited {proc.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"

        result = json.loads(stdout)
        assert "error" not in result, f"Worker reported error: {result.get('error')}"
        # Worker wraps outputs under an "outputs" key alongside diagnostic
        # metadata (environment, etc.).
        outputs = result.get("outputs", result)
        assert outputs.get("out") == "hello-706", f"Unexpected worker result: {result}"

    def test_worker_without_block_file_path_still_works_for_importable_module(
        self,
    ) -> None:
        """Tier-2 / builtin path: no ``block_file_path`` -> standard
        ``importlib.import_module``. Regression guard ensuring the fix did
        not break the existing dispatch route.
        """
        # MergeBlock is a real, fully-importable built-in block.
        from scieasy.blocks.process.builtins.merge import MergeBlock

        block_class_path = f"{MergeBlock.__module__}.{MergeBlock.__qualname__}"
        # Payload without ``block_file_path`` -> worker uses import_module.
        payload_bytes = build_worker_payload(
            block_class=block_class_path,
            inputs_refs={"data": "scalar-passthrough"},
            config={},
            output_dir=None,
            # block_file_path intentionally omitted.
        )
        payload = json.loads(payload_bytes.decode("utf-8"))
        assert "block_file_path" not in payload, "Tier-2 dispatch must not include block_file_path"

        proc = subprocess.run(
            [sys.executable, "-m", "scieasy.engine.runners.worker"],
            input=payload_bytes,
            capture_output=True,
            timeout=60,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        # The point of this test is solely that the import path still
        # imports cleanly. Whether MergeBlock can actually process a scalar
        # input is irrelevant — we only check that the regression symptom
        # (the worker failing to find the target module) does not appear.
        #
        # NOTE: unrelated optional plugins (e.g. ``scieasy_blocks_lcms``)
        # may legitimately fail to import on machines without them; those
        # are logged as warnings by the TypeRegistry but do not affect
        # dispatch. So we check only that the *target* module path
        # resolved.
        assert MergeBlock.__module__ not in stderr, (
            f"Worker failed to import target module {MergeBlock.__module__}:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )
        # And the worker should have written *some* JSON on stdout
        # (error envelope or success envelope) — not died before any
        # output was produced.
        assert stdout.strip(), f"Worker produced no stdout:\nSTDERR:\n{stderr}"
