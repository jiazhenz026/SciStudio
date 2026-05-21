"""T-TRK-015 — AppBlock + Fiji integration audit.

This module launches a real Fiji install through :class:`AppBlock` with a
headless macro fixture and audits four behaviours:

1. End-to-end launch-and-collect: Fiji opens the test image, applies a
   Gaussian blur, and writes the result to ``outputs/``; ``AppBlock``
   detects it and returns an ``Artifact``.
2. FileWatcher cleanup: after :meth:`AppBlock.run` returns, no new
   long-lived threads are left hanging from the watcher.
3. Process cleanup: the Fiji :class:`subprocess.Popen` spawned by the
   bridge is reaped (no zombie) after the block exits.
4. Exchange-directory cleanup: when the block is constructed with a
   tempfile-backed exchange dir (no ``project_dir``), the directory is
   removed on successful exit.

All four tests are guarded by ``@pytest.mark.requires_fiji`` and skipped
cleanly when Fiji is not installed at the master-plan §10 path.

Per the T-TRK-015 spec §j, this is an **audit**. If a behaviour test
exposes a bug in the current ``AppBlock``/``FileWatcher``/``bridge``
implementation, the test is marked ``xfail(strict=False)`` with a
pointer to the audit-finding issue — the fix lands in a separate PR.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest

from scistudio.blocks.app.app_block import AppBlock
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.state import BlockState
from tests.fixtures.test_images import K562_L_2845_TIF

FIJI_EXE = Path(r"C:\Program Files\Fiji\fiji-windows-x64.exe")
MACRO_PATH = Path(__file__).parent / "fixtures" / "headless_macro.ijm"

# The tests launch the real Fiji GUI process in headless mode; on a
# cold JVM start that routinely takes 30-60 s on Windows. Give the
# watcher plenty of headroom.
FIJI_WATCH_TIMEOUT = 240


def _fiji_available() -> bool:
    return FIJI_EXE.is_file() and K562_L_2845_TIF.is_file() and MACRO_PATH.is_file()


# Module-level skip keeps the whole file out of collection when Fiji is
# not installed, which is the normal state for CI. Individual tests keep
# the marker so selection by ``-m requires_fiji`` still works.
pytestmark = [
    pytest.mark.requires_fiji,
    pytest.mark.skipif(not _fiji_available(), reason="Fiji or test image not available"),
]


def _make_block() -> AppBlock:
    """Return an AppBlock already transitioned to RUNNING.

    :meth:`AppBlock.run` transitions to PAUSED, so the block must start
    in RUNNING (per the existing pattern in ``tests/blocks/test_app_block.py``).
    """
    block = AppBlock()
    block.transition(BlockState.READY)
    block.transition(BlockState.RUNNING)
    return block


def _make_config(
    *,
    tmp_path: Path,
    output_image_path: Path,
    exchange_dir: Path | None = None,
    project_dir: Path | None = None,
    block_id: str | None = None,
) -> BlockConfig:
    """Build a BlockConfig that drives Fiji through the headless macro.

    The macro's single argument is a path to an ``args.txt`` file that
    holds the input and output image paths on two separate lines. This
    indirection is required because the existing
    :func:`validate_app_command` rejects argv entries containing shell
    metacharacters — and the T-TRK-003 test image filename contains
    parentheses, which ``_SHELL_META`` treats as metacharacters.
    """
    args_file = tmp_path / "macro_args.txt"
    args_file.write_text(
        f"{K562_L_2845_TIF}\n{output_image_path}\n",
        encoding="utf-8",
    )

    # List-form command bypasses shlex.split (which would choke on the
    # spaces in "Program Files"). Each element is still scanned for
    # shell metacharacters by validate_app_command.
    command = [
        str(FIJI_EXE),
        "--headless",
        "-macro",
        str(MACRO_PATH),
        str(args_file),
    ]

    params: dict[str, object] = {
        "app_command": command,
        "output_patterns": "*.tif",
        "watch_timeout": FIJI_WATCH_TIMEOUT,
        # Shorter stability period keeps the test fast once Fiji writes.
        "stability_period": 1.0,
    }
    if exchange_dir is not None:
        params["exchange_dir"] = str(exchange_dir)
    if project_dir is not None:
        params["project_dir"] = str(project_dir)
    if block_id is not None:
        params["block_id"] = block_id
    return BlockConfig(params=params)


def test_appblock_fiji_launch_and_macro(tmp_path: Path) -> None:
    """Launch Fiji with the headless macro and collect the blurred output.

    Asserts that the block returns an Artifact pointing at a non-empty
    TIFF written by the macro.
    """
    exchange_dir = tmp_path / "exchange"
    output_image = exchange_dir / "outputs" / "blurred.tif"

    block = _make_block()
    config = _make_config(
        tmp_path=tmp_path,
        output_image_path=output_image,
        exchange_dir=exchange_dir,
    )

    result = block.run(inputs={}, config=config)

    assert output_image.is_file(), "Fiji macro did not produce the expected output TIFF"
    assert output_image.stat().st_size > 0, "Fiji output TIFF is empty"

    # The block should have collected the output as an Artifact wrapped
    # in a Collection (ADR-020). Key is the file stem.
    assert "blurred" in result, f"expected 'blurred' in result keys, got {list(result)}"


def test_appblock_fiji_filewatcher_cleanup(tmp_path: Path) -> None:
    """After run() returns, no FileWatcher-owned threads are alive.

    The current :class:`FileWatcher` implementation polls in the caller
    thread and does not spawn a worker, so this test asserts that the
    thread count does not grow across a run. If a future implementation
    adds a background thread, it must still terminate by the time
    ``run()`` returns.
    """
    exchange_dir = tmp_path / "exchange"
    output_image = exchange_dir / "outputs" / "blurred.tif"

    before_threads = {t.ident for t in threading.enumerate()}

    block = _make_block()
    config = _make_config(
        tmp_path=tmp_path,
        output_image_path=output_image,
        exchange_dir=exchange_dir,
    )
    block.run(inputs={}, config=config)

    # Give any background thread a brief moment to unwind.
    time.sleep(0.2)
    after_threads = {t.ident for t in threading.enumerate() if t.is_alive()}
    leaked = after_threads - before_threads
    assert not leaked, f"FileWatcher leaked threads after run(): {leaked}"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "AUDIT FINDING (T-TRK-015, tracked as #338): AppBlock.run does "
        "not call proc.wait() on the external subprocess after the "
        "watcher returns, so the child process remains alive after "
        "run() returns. Fix lands in a separate PR per spec §j."
    ),
)
def test_appblock_fiji_process_cleanup(tmp_path: Path) -> None:
    """The Fiji subprocess is fully reaped after run() returns.

    We monkey-patch :class:`subprocess.Popen` via a wrapper class so we
    can capture the process handle the bridge creates, then assert it
    has exited (``poll()`` returns an int) shortly after ``run()``.
    """
    exchange_dir = tmp_path / "exchange"
    output_image = exchange_dir / "outputs" / "blurred.tif"

    captured: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    class _CapturingPopen(real_popen):  # type: ignore[type-arg,misc]
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            captured.append(self)  # type: ignore[arg-type]

    # Patch only within the bridge module to avoid interfering with
    # unrelated subprocesses (e.g. pytest's own plumbing).
    import scistudio.blocks.app.bridge as bridge_mod

    original = bridge_mod.subprocess.Popen
    bridge_mod.subprocess.Popen = _CapturingPopen  # type: ignore[attr-defined,misc]
    try:
        block = _make_block()
        config = _make_config(
            tmp_path=tmp_path,
            output_image_path=output_image,
            exchange_dir=exchange_dir,
        )
        block.run(inputs={}, config=config)
    finally:
        bridge_mod.subprocess.Popen = original  # type: ignore[attr-defined]

    assert captured, "bridge.launch did not create a subprocess"
    proc = captured[0]

    # Give Fiji a moment to wind down after writing output.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.2)

    assert proc.poll() is not None, f"Fiji process (pid={proc.pid}) was not reaped after AppBlock.run() returned"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "AUDIT FINDING (T-TRK-015, tracked as #339): AppBlock.run does "
        "not remove the tempfile-backed exchange directory on successful "
        "exit. Fix lands in a separate PR per spec §j."
    ),
)
def test_appblock_exchange_dir_cleanup(tmp_path: Path) -> None:
    """The tempfile exchange directory is removed after a successful run.

    We force the tempfile fallback path by not passing ``project_dir`` or
    ``exchange_dir``; on exit the directory should no longer exist.
    """
    # We still need to know where Fiji writes its output so the macro has
    # a concrete path — put it under tmp_path rather than the (unknown)
    # tempfile-backed exchange_dir.
    output_image = tmp_path / "blurred.tif"

    block = _make_block()
    config = _make_config(
        tmp_path=tmp_path,
        output_image_path=output_image,
    )

    # Snapshot existing tempdirs so we can find the one AppBlock creates.
    import tempfile as _tempfile

    tempdir_root = Path(_tempfile.gettempdir())
    before = {p for p in tempdir_root.glob("scistudio_app_*") if p.is_dir()}

    block.run(inputs={}, config=config)

    after = {p for p in tempdir_root.glob("scistudio_app_*") if p.is_dir()}
    created = after - before
    assert not created, f"AppBlock left tempfile exchange dir(s) on disk after successful run: {created}"
