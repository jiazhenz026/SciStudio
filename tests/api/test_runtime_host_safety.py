"""ApiRuntime host-safety configuration wiring tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scistudio.api.runtime import ApiRuntime


def _runtime_with_mocked_manager(
    tmp_path: Path,
    max_concurrent_blocks: int | None = None,
) -> tuple[ApiRuntime, MagicMock]:
    with (
        patch("scistudio.api.runtime.Path.home", return_value=tmp_path),
        patch("scistudio.api.runtime.ResourceManager") as manager_type,
    ):
        runtime = ApiRuntime(max_concurrent_blocks=max_concurrent_blocks)
    return runtime, manager_type


def test_runtime_uses_default_global_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCISTUDIO_MAX_CONCURRENT_BLOCKS", raising=False)
    _, manager_type = _runtime_with_mocked_manager(tmp_path)
    manager_type.assert_called_once_with(max_concurrent_blocks=255)


def test_explicit_runtime_limit_wins_over_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_MAX_CONCURRENT_BLOCKS", "300")
    _, manager_type = _runtime_with_mocked_manager(tmp_path, max_concurrent_blocks=512)
    manager_type.assert_called_once_with(max_concurrent_blocks=512)


def test_runtime_reads_operator_limit_from_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_MAX_CONCURRENT_BLOCKS", "300")
    _, manager_type = _runtime_with_mocked_manager(tmp_path)
    manager_type.assert_called_once_with(max_concurrent_blocks=300)


@pytest.mark.parametrize("value", ["not-an-int", "1.5"])
def test_runtime_rejects_non_integer_environment(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_MAX_CONCURRENT_BLOCKS", value)
    with pytest.raises(ValueError, match="positive integer"):
        ApiRuntime()


def test_runtime_rejects_nonpositive_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_MAX_CONCURRENT_BLOCKS", "0")
    with (
        patch("scistudio.api.runtime.Path.home", return_value=tmp_path),
        pytest.raises(ValueError, match="positive integer"),
    ):
        ApiRuntime()
