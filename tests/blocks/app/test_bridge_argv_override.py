"""Test FileExchangeBridge.launch argv_override parameter (#420)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from scieasy.blocks.app.bridge import FileExchangeBridge


def test_launch_appends_exchange_dir_by_default(tmp_path: Path) -> None:
    """When argv_override is None, launch appends str(exchange_dir) to argv."""
    bridge = FileExchangeBridge()
    exchange = tmp_path / "exchange"
    exchange.mkdir()

    with patch("scieasy.blocks.app.bridge.subprocess.Popen") as mock_popen:
        mock_popen.return_value = mock_popen
        bridge.launch([sys.executable, "-c", "pass"], exchange)

    args_used = mock_popen.call_args[0][0]
    assert args_used[-1] == str(exchange)


def test_launch_uses_argv_override_when_provided(tmp_path: Path) -> None:
    """When argv_override is given, those args replace the default exchange_dir suffix."""
    bridge = FileExchangeBridge()
    exchange = tmp_path / "exchange"
    exchange.mkdir()
    override = ["/some/file.tif", "/other/file.tif"]

    with patch("scieasy.blocks.app.bridge.subprocess.Popen") as mock_popen:
        mock_popen.return_value = mock_popen
        bridge.launch([sys.executable, "-c", "pass"], exchange, argv_override=override)

    args_used = mock_popen.call_args[0][0]
    assert args_used[-2:] == override
    assert str(exchange) not in args_used


def test_launch_macos_app_bundle_uses_open_w_and_n(tmp_path: Path) -> None:
    """On darwin, launching a .app must use ``open -W -n -a`` (#677).

    ``-W`` makes ``open`` block until the .app exits so the returned
    ``Popen`` tracks the .app's lifetime (otherwise the watcher would
    immediately see the launcher die and raise
    ``ProcessExitedWithoutOutputError``). ``-n`` forces a new instance
    so the launched process is the one the watcher is keyed to.
    """
    bridge = FileExchangeBridge()
    exchange = tmp_path / "exchange"
    exchange.mkdir()
    fake_app = "/Applications/Fiji.app"

    with (
        patch.object(sys, "platform", "darwin"),
        patch("scieasy.blocks.app.bridge.subprocess.Popen") as mock_popen,
        # validate_app_command rejects nonexistent executables; bypass it
        # so we can assert the macOS-specific argv rewrite in isolation.
        patch("scieasy.blocks.app.command_validator.validate_app_command", return_value=[fake_app]),
    ):
        mock_popen.return_value = mock_popen
        bridge.launch(fake_app, exchange)

    args_used = mock_popen.call_args[0][0]
    assert args_used[0] == "open"
    assert "-W" in args_used, f"expected -W flag in argv: {args_used}"
    assert "-n" in args_used, f"expected -n flag in argv: {args_used}"
    # ``-a <app>`` must follow so ``open`` resolves the .app bundle.
    assert "-a" in args_used
    a_index = args_used.index("-a")
    assert args_used[a_index + 1] == fake_app
    # The .app path itself must not be the executable — that would
    # bypass ``open`` and cause the regression in #677.
    assert args_used[0] != fake_app


def test_launch_non_darwin_does_not_inject_open(tmp_path: Path) -> None:
    """On non-darwin platforms, the .app rewrite must not fire (#677)."""
    bridge = FileExchangeBridge()
    exchange = tmp_path / "exchange"
    exchange.mkdir()
    fake_app = "/some/path/Tool.app"

    with (
        patch.object(sys, "platform", "linux"),
        patch("scieasy.blocks.app.bridge.subprocess.Popen") as mock_popen,
        patch("scieasy.blocks.app.command_validator.validate_app_command", return_value=[fake_app]),
    ):
        mock_popen.return_value = mock_popen
        bridge.launch(fake_app, exchange)

    args_used = mock_popen.call_args[0][0]
    assert args_used[0] == fake_app
    assert "open" not in args_used
    assert "-W" not in args_used
