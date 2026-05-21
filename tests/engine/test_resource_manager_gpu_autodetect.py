"""Tests for ResourceManager GPU auto-detect (ADR-027 D10, T-002).

These tests cover the contract introduced by ADR-027 D10:

- ``ResourceManager.__init__(gpu_slots=None)`` triggers
  ``_auto_detect_gpu_slots()``.
- The auto-detect probe tries ``torch.cuda.device_count()`` first, then
  ``nvidia-smi -L``, then returns 0.
- Explicit integer values (including 0) bypass auto-detect entirely.
- A single WARNING is emitted when ``gpu_slots == 0`` and a ``requires_gpu``
  block is dispatched.
"""

from __future__ import annotations

import builtins
import logging
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scistudio.engine.resources import (
    ResourceManager,
    ResourceRequest,
    _auto_detect_gpu_slots,
)


def _mock_vm(percent: float) -> MagicMock:
    vm = MagicMock()
    vm.percent = percent
    return vm


# ---------------------------------------------------------------------------
# Explicit gpu_slots: auto-detect must NOT run
# ---------------------------------------------------------------------------


class TestExplicitGPUSlotsRespected:
    def test_explicit_gpu_slots_respected(self) -> None:
        """ResourceManager(gpu_slots=4) honours the explicit value verbatim."""
        with patch("scistudio.engine.resources._auto_detect_gpu_slots") as mock_detect:
            rm = ResourceManager(gpu_slots=4)
            assert rm.gpu_slots == 4
            assert rm._gpu_slots_auto_detected is False
            mock_detect.assert_not_called()

    def test_explicit_zero_gpu_slots_respected(self) -> None:
        """ResourceManager(gpu_slots=0) is treated as an explicit override."""
        with patch("scistudio.engine.resources._auto_detect_gpu_slots") as mock_detect:
            rm = ResourceManager(gpu_slots=0)
            assert rm.gpu_slots == 0
            assert rm._gpu_slots_auto_detected is False
            mock_detect.assert_not_called()

    def test_explicit_integer_overrides_auto_detect(self) -> None:
        """Per ADR-027 D10: explicit integers short-circuit auto-detect.

        This is the canonical regression test enumerated in standards-doc
        T-002 §h: ``ResourceManager(gpu_slots=2)`` does NOT call
        ``_auto_detect_gpu_slots``.
        """
        with patch("scistudio.engine.resources._auto_detect_gpu_slots") as mock_detect:
            rm = ResourceManager(gpu_slots=2)
            assert rm.gpu_slots == 2
            mock_detect.assert_not_called()


# ---------------------------------------------------------------------------
# gpu_slots=None triggers _auto_detect_gpu_slots()
# ---------------------------------------------------------------------------


class TestNoneTriggersAutoDetect:
    def test_gpu_slots_none_triggers_auto_detect(self) -> None:
        """ResourceManager() (default) calls _auto_detect_gpu_slots once."""
        with patch("scistudio.engine.resources._auto_detect_gpu_slots", return_value=3) as mock_detect:
            rm = ResourceManager()
            assert rm.gpu_slots == 3
            assert rm._gpu_slots_auto_detected is True
            mock_detect.assert_called_once_with()

    def test_gpu_slots_none_explicit_triggers_auto_detect(self) -> None:
        """Passing gpu_slots=None explicitly is equivalent to omitting it."""
        with patch("scistudio.engine.resources._auto_detect_gpu_slots", return_value=1) as mock_detect:
            rm = ResourceManager(gpu_slots=None)
            assert rm.gpu_slots == 1
            mock_detect.assert_called_once_with()


# ---------------------------------------------------------------------------
# _auto_detect_gpu_slots() probe order
# ---------------------------------------------------------------------------


class TestAutoDetectUsesTorchWhenAvailable:
    def test_auto_detect_uses_torch_when_available(self) -> None:
        """torch.cuda path returns device_count() and never invokes nvidia-smi.

        We inject a fake ``torch`` module via sys.modules so the function's
        ``import torch`` succeeds, then mock ``cuda.is_available`` and
        ``cuda.device_count``.
        """
        fake_torch = SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: True,
                device_count=lambda: 2,
            )
        )
        with (
            patch.dict("sys.modules", {"torch": fake_torch}),
            patch("subprocess.run") as mock_run,
        ):
            assert _auto_detect_gpu_slots() == 2
            mock_run.assert_not_called()

    def test_torch_present_but_cuda_unavailable_falls_through(self) -> None:
        """If torch is importable but cuda is unavailable, fall through.

        Falls through to nvidia-smi (which we mock to also fail).
        """
        fake_torch = SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: False,
                device_count=lambda: 0,
            )
        )
        with (
            patch.dict("sys.modules", {"torch": fake_torch}),
            patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi")),
        ):
            assert _auto_detect_gpu_slots() == 0


class TestAutoDetectFallsBackToNvidiaSmi:
    def test_auto_detect_falls_back_to_nvidia_smi(self) -> None:
        """When torch import fails, parse `nvidia-smi -L` output."""
        # Force the `import torch` inside the function to raise ImportError
        # by patching builtins.__import__. The original import is captured
        # before patching so other imports continue to work normally.
        original_import = builtins.__import__

        def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "torch":
                raise ImportError("torch not installed")
            return original_import(name, *args, **kwargs)

        completed = subprocess.CompletedProcess(
            args=["nvidia-smi", "-L"],
            returncode=0,
            stdout="GPU 0: NVIDIA RTX A6000 (UUID: GPU-abc)\nGPU 1: NVIDIA RTX A6000 (UUID: GPU-def)\n",
            stderr="",
        )
        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch("subprocess.run", return_value=completed) as mock_run,
        ):
            assert _auto_detect_gpu_slots() == 2
            mock_run.assert_called_once()
            # Verify we asked for `nvidia-smi -L`
            args, _ = mock_run.call_args
            assert args[0] == ["nvidia-smi", "-L"]

    def test_nvidia_smi_returns_zero_gpus(self) -> None:
        """nvidia-smi running successfully but with no GPU lines returns 0."""
        original_import = builtins.__import__

        def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "torch":
                raise ImportError("torch not installed")
            return original_import(name, *args, **kwargs)

        completed = subprocess.CompletedProcess(
            args=["nvidia-smi", "-L"],
            returncode=0,
            stdout="No devices were found\n",
            stderr="",
        )
        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch("subprocess.run", return_value=completed),
        ):
            assert _auto_detect_gpu_slots() == 0


class TestAutoDetectReturnsZeroWhenNoGPU:
    @staticmethod
    def _fake_import_no_torch():  # type: ignore[no-untyped-def]
        original_import = builtins.__import__

        def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "torch":
                raise ImportError("torch not installed")
            return original_import(name, *args, **kwargs)

        return fake_import

    def test_auto_detect_returns_zero_when_no_gpu(self) -> None:
        """Both torch and nvidia-smi unavailable: return 0."""
        with (
            patch("builtins.__import__", side_effect=self._fake_import_no_torch()),
            patch(
                "subprocess.run",
                side_effect=FileNotFoundError("nvidia-smi: command not found"),
            ),
        ):
            assert _auto_detect_gpu_slots() == 0

    def test_auto_detect_handles_nvidia_smi_timeout(self) -> None:
        """nvidia-smi timing out is handled gracefully and returns 0."""
        with (
            patch("builtins.__import__", side_effect=self._fake_import_no_torch()),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["nvidia-smi", "-L"], timeout=2),
            ),
        ):
            assert _auto_detect_gpu_slots() == 0

    def test_auto_detect_handles_nvidia_smi_nonzero_exit(self) -> None:
        """nvidia-smi exiting non-zero is treated as zero GPUs detected."""
        completed = subprocess.CompletedProcess(
            args=["nvidia-smi", "-L"],
            returncode=9,
            stdout="",
            stderr="NVIDIA-SMI has failed",
        )
        with (
            patch("builtins.__import__", side_effect=self._fake_import_no_torch()),
            patch("subprocess.run", return_value=completed),
        ):
            assert _auto_detect_gpu_slots() == 0


# ---------------------------------------------------------------------------
# One-time WARNING when no GPU but a block requires one
# ---------------------------------------------------------------------------


class TestWarningEmittedOnceWhenNoGPUButRequired:
    def test_warning_emitted_once_when_no_gpu_but_required(self, caplog: pytest.LogCaptureFixture) -> None:
        """A single WARNING is logged regardless of how many GPU dispatches.

        Standards-doc T-002 §e + ADR-027 D10: the warning fires once per
        ResourceManager instance, even if can_dispatch is called repeatedly.
        """
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        gpu_request = ResourceRequest(requires_gpu=True, gpu_memory_gb=4.0)

        with (
            caplog.at_level(logging.WARNING, logger="scistudio.engine.resources"),
            patch("psutil.virtual_memory", return_value=_mock_vm(50.0)),
        ):
            for _ in range(5):
                assert rm.can_dispatch(gpu_request) is False

        warnings = [r for r in caplog.records if "No GPU detected" in r.getMessage()]
        assert len(warnings) == 1
        assert warnings[0].levelno == logging.WARNING
        assert "gpu_slots" in warnings[0].getMessage()

    def test_warning_logged_when_zero_slots_but_gpu_block_dispatched(self, caplog: pytest.LogCaptureFixture) -> None:
        """Standards-doc T-002 §e named test: warning fires on first dispatch.

        Verifies the warning fires whether ``gpu_slots == 0`` came from
        auto-detect (mocked here) or explicit configuration.
        """
        with patch("scistudio.engine.resources._auto_detect_gpu_slots", return_value=0):
            rm = ResourceManager()  # auto-detect → 0
        assert rm.gpu_slots == 0
        assert rm._gpu_slots_auto_detected is True

        with (
            caplog.at_level(logging.WARNING, logger="scistudio.engine.resources"),
            patch("psutil.virtual_memory", return_value=_mock_vm(50.0)),
        ):
            assert rm.can_dispatch(ResourceRequest(requires_gpu=True)) is False

        warnings = [r for r in caplog.records if "No GPU detected" in r.getMessage()]
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# No warning when no GPU block is dispatched
# ---------------------------------------------------------------------------


class TestNoWarningWhenNoGPUBlockDeclared:
    def test_no_warning_when_no_gpu_block_declared(self, caplog: pytest.LogCaptureFixture) -> None:
        """gpu_slots=0 + only CPU dispatches → no warning logged."""
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        cpu_request = ResourceRequest(requires_gpu=False, cpu_cores=2)

        with (
            caplog.at_level(logging.WARNING, logger="scistudio.engine.resources"),
            patch("psutil.virtual_memory", return_value=_mock_vm(50.0)),
        ):
            for _ in range(3):
                assert rm.can_dispatch(cpu_request) is True

        warnings = [r for r in caplog.records if "No GPU detected" in r.getMessage()]
        assert warnings == []

    def test_no_warning_when_gpu_slots_positive(self, caplog: pytest.LogCaptureFixture) -> None:
        """gpu_slots > 0 + GPU dispatch succeeds → no warning logged."""
        rm = ResourceManager(gpu_slots=2, cpu_workers=4)
        gpu_request = ResourceRequest(requires_gpu=True, gpu_memory_gb=2.0)

        with (
            caplog.at_level(logging.WARNING, logger="scistudio.engine.resources"),
            patch("psutil.virtual_memory", return_value=_mock_vm(50.0)),
        ):
            assert rm.can_dispatch(gpu_request) is True

        warnings = [r for r in caplog.records if "No GPU detected" in r.getMessage()]
        assert warnings == []
