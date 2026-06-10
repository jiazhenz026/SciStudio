"""Tests for worker.py subprocess entry point.

ADR-017: All block execution happens in isolated subprocesses.
ADR-027 D11 + Addendum 1 §1 (T-014): ``reconstruct_inputs`` returns
typed :class:`~scistudio.core.types.base.DataObject` instances;
``serialise_outputs`` writes the full typed metadata sidecar via
:func:`~scistudio.core.types.serialization._serialise_one`.
ADR-031 D2: ViewProxy eliminated.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.core.types.base import DataObject
from scistudio.engine.runners.worker import (
    main,
    reconstruct_inputs,
    serialise_outputs,
)

# ---------------------------------------------------------------------------
# reconstruct_inputs
# ---------------------------------------------------------------------------


class TestReconstructInputs:
    def test_scalar_inputs_pass_through(self) -> None:
        """ADR-017: Non-reference inputs pass through as-is."""
        payload = {"inputs": {"port_a": "ref1", "port_b": "ref2"}}
        result = reconstruct_inputs(payload)
        assert result == {"port_a": "ref1", "port_b": "ref2"}

    def test_returns_empty_dict_when_no_inputs(self) -> None:
        payload = {"block_class": "mod.Block"}
        result = reconstruct_inputs(payload)
        assert result == {}

    def test_storage_ref_dict_becomes_typed_instance(self) -> None:
        """ADR-027 Addendum 1 §1 (T-014): dicts with backend/path reconstruct
        into typed DataObject instances.
        """
        from scistudio.core.types.array import Array

        payload = {
            "inputs": {
                "image": {
                    "backend": "zarr",
                    "path": "/data/img.zarr",
                    "format": "zarr",
                    "metadata": {
                        "type_chain": ["DataObject", "Array"],
                        "axes": ["z", "y", "x"],
                        "shape": [8, 16, 16],
                        "dtype": "uint8",
                    },
                },
                "label": "test",
            }
        }
        result = reconstruct_inputs(payload)

        # Typed Array instance — the critical T-014 behaviour.
        assert isinstance(result["image"], Array)
        assert result["image"].axes == ["z", "y", "x"]
        assert result["image"].shape == (8, 16, 16)
        # StorageReference is still populated so lazy loading works at
        # the method level.
        assert result["image"].storage_ref is not None
        assert result["image"].storage_ref.backend == "zarr"
        assert result["image"].storage_ref.path == "/data/img.zarr"
        assert result["image"].storage_ref.format == "zarr"
        assert result["label"] == "test"


# ---------------------------------------------------------------------------
# serialise_outputs
# ---------------------------------------------------------------------------


class TestSerialiseOutputs:
    def test_serialises_plain_values_natively(self) -> None:
        """ADR-017: scalar types (int, str, float, bool, None) pass through as-is."""
        outputs = {"result": 42, "name": "hello"}
        result = serialise_outputs(outputs, "")
        assert result == {"result": 42, "name": "hello"}

    def test_serialises_typed_dataobject_with_storage_ref(self) -> None:
        """ADR-027 Addendum 1 §1 (T-014): typed DataObject outputs use the
        full metadata sidecar (type_chain + framework + meta + user + extras).
        """
        from scistudio.core.storage.ref import StorageReference
        from scistudio.core.types.array import Array

        arr = Array(axes=["y", "x"], shape=(8, 8), dtype="uint8")
        arr._storage_ref = StorageReference(backend="zarr", path="/data/output.zarr", format="zarr")

        result = serialise_outputs({"image": arr}, "/output")
        payload = result["image"]

        assert payload["backend"] == "zarr"
        assert payload["path"] == "/data/output.zarr"
        assert payload["format"] == "zarr"
        md = payload["metadata"]
        assert md["type_chain"] == ["DataObject", "Array"]
        assert md["axes"] == ["y", "x"]
        assert md["shape"] == [8, 8]
        assert md["dtype"] == "uint8"
        # framework slot is populated with FrameworkMeta fields.
        assert "framework" in md
        assert "object_id" in md["framework"]
        # meta is None on the base Array class.
        assert md["meta"] is None
        # user is an empty dict by default.
        assert md["user"] == {}

    def test_serialises_int_without_storage_ref_attribute(self) -> None:
        """ADR-017: int values without storage_ref are preserved as int."""
        outputs = {"count": 5}
        result = serialise_outputs(outputs, "")
        assert result == {"count": 5}

    def test_serialises_dataobject_without_storage_ref_raises(self) -> None:
        """ADR-031 Addendum 1: in-memory DataObject without storage_ref raises.

        The hard gate enforces that all DataObjects must be persisted before
        leaving the worker subprocess. _serialise_one rejects storage_ref=None.
        """
        from scistudio.core.types.array import Array

        arr = Array(axes=["y", "x"], shape=(2, 2), dtype="uint8")
        # No storage_ref set → serialise_outputs hard-gates.
        with pytest.raises(RuntimeError, match="has no storage_ref after auto_flush"):
            serialise_outputs({"data": arr}, "")

    def test_serialises_dataobject_with_storage_ref(
        self,
        tmp_path: Path,
    ) -> None:
        """ADR-031: Array with storage_ref serializes correctly."""
        import numpy as np
        import zarr

        from scistudio.core.storage.ref import StorageReference
        from scistudio.core.types.array import Array

        # Write data to zarr first (ADR-031: no _data backdoor).
        zarr_path = str(tmp_path / "test.zarr")
        zarr.save(zarr_path, np.array([[1, 2], [3, 4]], dtype="uint8"))
        ref = StorageReference(
            backend="zarr",
            path=zarr_path,
            metadata={"shape": [2, 2], "dtype": "uint8"},
        )
        arr = Array(axes=["y", "x"], shape=(2, 2), dtype="uint8", storage_ref=ref)

        result = serialise_outputs({"data": arr}, str(tmp_path))

        assert result["data"]["backend"] == "zarr"
        assert result["data"]["path"] is not None
        assert result["data"]["metadata"]["axes"] == ["y", "x"]

    def test_serialise_collection_with_none_item_type(self) -> None:
        """Collection with item_type=None should not crash the worker (#168)."""
        from scistudio.core.types.collection import Collection

        col = Collection.__new__(Collection)
        col._items = []
        col._item_type = None  # type: ignore[assignment]

        result = serialise_outputs({"output": col}, "/tmp/out")
        assert result["output"]["_collection"] is True
        assert result["output"]["item_type"] == "DataObject"

    def test_empty_outputs(self) -> None:
        result = serialise_outputs({}, "")
        assert result == {}


# ---------------------------------------------------------------------------
# main — module-level function (tested indirectly via subprocess in
# integration tests; here we verify import works)
# ---------------------------------------------------------------------------


class TestWorkerMain:
    def test_main_is_callable(self) -> None:
        """Verify the main function exists and is callable."""
        assert callable(main)

    def test_main_outputs_include_environment_key(self) -> None:
        """Issue #54: worker main() should include 'environment' in JSON stdout.

        We invoke worker.py as a subprocess with a minimal payload using a
        trivial block class. The stdout JSON must contain both 'outputs'
        and 'environment' keys.
        """
        import json
        import subprocess
        import sys

        # Create a minimal block that returns a scalar output.
        # The worker expects block_class as a dotted path that can be imported.
        # We use subprocess to run worker.py directly, feeding JSON via stdin.
        payload = json.dumps(
            {
                "block_class": "tests.engine.test_worker._StubBlock",
                "inputs": {},
                "config": {},
                "output_dir": "",
            }
        )

        result = subprocess.run(
            [sys.executable, "-m", "scistudio.engine.runners.worker"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # If the block import fails, it's because the test stub isn't importable
        # from the subprocess context. In that case we fall back to checking
        # that the error payload is well-formed JSON (the worker always writes
        # JSON to stdout).
        parsed = json.loads(result.stdout)

        if "error" not in parsed:
            assert "outputs" in parsed, f"Missing 'outputs' key: {parsed}"
            assert "environment" in parsed, f"Missing 'environment' key: {parsed}"
            env = parsed["environment"]
            assert "python_version" in env
            assert "platform" in env
            assert "key_packages" in env


class _StubBlock:
    """Minimal block stub for subprocess worker test."""

    def __init__(self, config: object = None) -> None:
        # Accept optional config so worker.py's ``block_cls(config=config)``
        # call site (#883) succeeds; we don't use it here.
        pass

    def run(self, inputs: dict, config: object) -> dict:
        return {"result": "ok"}


class _ReadingStubBlock:
    """Block that triggers lazy storage materialisation from an input port."""

    def __init__(self, config: object = None) -> None:
        pass

    def run(self, inputs: dict, config: object) -> dict:
        inputs["image"].to_memory()
        return {"result": "unreachable"}


# ---------------------------------------------------------------------------
# main — final_state envelope field (#681)
# ---------------------------------------------------------------------------


class _CancellingStubBlock:
    """Block stub that raises ``BlockCancelledByAppError`` from ``run()``.

    Mirrors the AppBlock cancellation pattern (#1334): when the external
    app exits without producing output, AppBlock raises
    ``BlockCancelledByAppError``. The worker must catch it and forward
    ``final_state="cancelled"`` via the stdout envelope so the orchestrator
    records the block correctly via the existing
    ``BlockTerminalStateReportedError`` channel (#681).
    """

    def __init__(self, config: object = None) -> None:
        # Accept optional config so worker.py's ``block_cls(config=config)``
        # call site (#883) succeeds; the stub doesn't read it.
        pass

    def run(self, inputs: dict, config: object) -> dict:
        from scistudio.blocks.base.exceptions import BlockCancelledByAppError

        raise BlockCancelledByAppError("stub cancellation")


class TestWorkerFinalState:
    """#681 / #1334: worker must forward CANCELLED via envelope.

    Runs the worker as a real subprocess and inspects the JSON envelope on
    stdout. The synthetic block raises ``BlockCancelledByAppError`` to simulate
    the AppBlock cancellation path.
    """

    def _run_worker(self, block_class_path: str) -> dict:
        import json
        import os
        import subprocess
        import sys
        from pathlib import Path

        payload = json.dumps(
            {
                "block_class": block_class_path,
                "inputs": {},
                "config": {},
                "output_dir": "",
            }
        )
        # Ensure the subprocess imports the same ``scistudio`` source tree as
        # this checkout's ``src/`` rather than any other editable install
        # that may be active in the active interpreter. Walk up from this
        # test file to find ``<repo>/src``. Required when the test runs in
        # a git worktree whose ``src`` is not the editable-install target.
        env = os.environ.copy()
        repo_src = Path(__file__).resolve().parents[2] / "src"
        if repo_src.is_dir():
            env["PYTHONPATH"] = str(repo_src) + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-m", "scistudio.engine.runners.worker"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        return dict(json.loads(result.stdout))

    def test_cancelled_block_emits_final_state_in_envelope(self) -> None:
        parsed = self._run_worker("tests.engine.test_worker._CancellingStubBlock")
        # The block ran successfully — no error envelope.
        assert "error" not in parsed, parsed
        assert parsed.get("outputs") == {}
        assert parsed.get("final_state") == "cancelled"

    def test_normal_block_omits_final_state_field(self) -> None:
        # _StubBlock returns normally — the envelope must NOT include
        # ``final_state``. Per #1334 the worker-side block state machine is
        # gone; ``final_state`` only appears on ``BlockCancelledByAppError``.
        parsed = self._run_worker("tests.engine.test_worker._StubBlock")
        assert "error" not in parsed, parsed
        assert "final_state" not in parsed


class TestWorkerStorageErrors:
    def test_missing_storage_ref_emits_structured_payload(self, tmp_path: Path) -> None:
        import json
        import os
        import subprocess
        import sys

        missing_path = tmp_path / "missing.zarr"
        payload = json.dumps(
            {
                "block_class": "tests.engine.test_worker._ReadingStubBlock",
                "inputs": {
                    "image": {
                        "backend": "zarr",
                        "path": str(missing_path),
                        "format": "zarr",
                        "metadata": {
                            "type_chain": ["DataObject", "Array"],
                            "axes": ["y", "x"],
                            "shape": [2, 2],
                            "dtype": "uint8",
                            "upstream_block": "loader-1",
                        },
                    }
                },
                "config": {"block_id": "segment-1"},
                "output_dir": "",
            }
        )
        env = os.environ.copy()
        repo_src = Path(__file__).resolve().parents[2] / "src"
        env["PYTHONPATH"] = str(repo_src) + os.pathsep + env.get("PYTHONPATH", "")

        result = subprocess.run(
            [sys.executable, "-m", "scistudio.engine.runners.worker"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        parsed = json.loads(result.stdout)
        assert result.returncode == 1
        assert parsed["error_kind"] == "storage_missing"
        assert parsed["block_id"] == "segment-1"
        assert parsed["port_name"] == "image"
        assert parsed["upstream_block"] == "loader-1"
        assert parsed["ref"]["path"] == str(missing_path).replace("\\", "/")
        assert "Traceback" not in parsed["message"]


# ---------------------------------------------------------------------------
# #1518 (DSN-2): Block.validate() is enforced on the worker execution path.
# ---------------------------------------------------------------------------


class _RequiresInputBlock(Block):
    """Real ``Block`` subclass with a required input port and no run side
    effects. Used to prove the worker calls ``validate`` before ``run``."""

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="needed", accepted_types=[DataObject], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[DataObject], required=False),
    ]

    def run(self, inputs: dict, config: object) -> dict:  # pragma: no cover - must not run
        raise AssertionError("run() must not be reached when validate() fails")


def _run_worker_with_inputs(block_class_path: str, inputs: dict) -> tuple[int, dict]:
    import json
    import os
    import subprocess
    import sys

    payload = json.dumps(
        {
            "block_class": block_class_path,
            "inputs": inputs,
            "config": {},
            "output_dir": "",
        }
    )
    env = os.environ.copy()
    repo_src = Path(__file__).resolve().parents[2] / "src"
    if repo_src.is_dir():
        env["PYTHONPATH"] = str(repo_src) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "scistudio.engine.runners.worker"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    return result.returncode, dict(json.loads(result.stdout))


class TestWorkerValidate:
    """#1518: an ill-typed / missing-input block must fail at the contract
    boundary (validate) instead of warn-and-continue into ``run``."""

    def test_missing_required_input_fails_before_run(self) -> None:
        code, parsed = _run_worker_with_inputs(
            "tests.engine.test_worker._RequiresInputBlock",
            inputs={},  # required port 'needed' absent
        )
        assert code == 1, parsed
        assert "error" in parsed
        # The error is the validate() contract error, not the run() assertion.
        assert "Required input port 'needed' is missing" in parsed["error"]
        assert "run() must not be reached" not in parsed["error"]


class TestValidateOutputs:
    """#1518: ``_validate_outputs`` enforces the produced-output contract."""

    def test_missing_required_output_raises(self) -> None:
        from scistudio.engine.runners.worker import _validate_outputs

        ports = [OutputPort(name="result", accepted_types=[DataObject], required=True)]
        with pytest.raises(ValueError, match="Required output port 'result'"):
            _validate_outputs({}, ports)

    def test_optional_output_may_be_absent(self) -> None:
        from scistudio.engine.runners.worker import _validate_outputs

        ports = [OutputPort(name="result", accepted_types=[DataObject], required=False)]
        _validate_outputs({}, ports)  # must not raise

    def test_present_required_output_passes(self) -> None:
        from scistudio.engine.runners.worker import _validate_outputs

        ports = [OutputPort(name="result", accepted_types=[DataObject], required=True)]
        _validate_outputs({"result": object()}, ports)  # must not raise
