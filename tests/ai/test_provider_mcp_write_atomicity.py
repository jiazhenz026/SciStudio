"""ADR-034 FR-017a — atomicity of the provider-owned MCP config write.

``<project>/.kimi-code/mcp.json`` belongs to Kimi Code, not to SciStudio. It is
the only file this change writes that the user may already own content in, which
makes it the highest-consequence code in the change: a wrong write destroys
configuration with no recovery path.

``tests/ai/test_providers_registry.py`` covers the *content* half of FR-017a and
FR-017b thoroughly — malformed input, non-object documents, a non-object
``mcpServers`` value, a missing key, an empty file, idempotence, and preservation
of unrelated servers and unrelated top-level keys. What it does not cover is the
half spec §2 Edge Cases states separately:

    Two SciStudio processes inject into the same provider-owned config file
    concurrently. The write MUST be atomic so the file is never observed
    half-written.

That is a property about *observers*, and observation is what the tests here
add. Two AI Blocks configured with ``kimi-code`` running in the same project is
an ordinary workflow, not a contrived race, so the path is reachable.

.. warning::

   These tests pin the guarantee that currently holds — no reader ever sees a
   partial or truncated file — and deliberately do **not** assert that
   concurrent *writers* all succeed, because on this implementation they do not.
   See :func:`test_a_concurrent_reader_never_observes_a_half_written_file` for
   the measured behaviour and the tracked follow-up. Asserting the current
   writer behaviour as if it were intended would convert a defect into a
   specification, which is the failure mode these tests exist to prevent.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path

import pytest

from scistudio.ai.agent import providers_registry as registry
from scistudio.ai.agent import terminal

KIMI = registry.get("kimi-code")

#: A server entry the user registered themselves. Nothing SciStudio does may
#: change it, at any point during a write, as seen by any reader.
USER_SERVER = {"command": "my-own-server", "args": ["--serve", "--port", "9999"], "env": {"TOKEN": "keep-me"}}


def _seed(project_dir: Path) -> Path:
    config = project_dir / ".kimi-code" / "mcp.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps({"mcpServers": {"user-owned": USER_SERVER}, "trustedFolders": ["/a", "/b"]}, indent=2),
        encoding="utf-8",
    )
    return config


# ---------------------------------------------------------------------------
# The write must land through a rename, never an in-place truncate
# ---------------------------------------------------------------------------


def test_the_target_file_is_untouched_when_the_rename_never_happens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural proof that all mutation happens off to the side.

    If the merge wrote into the target and only then tried to finish, a failure
    partway would leave the user's file damaged. Breaking the rename is the
    cleanest way to ask "was anything written to the real path yet?" — and the
    answer must be no, byte for byte, including the file's modification time
    not being the thing under test.
    """
    config = _seed(tmp_path)
    before = config.read_bytes()

    def refuse(_src: object, _dst: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(OSError, match="simulated rename failure"):
        terminal._merge_provider_mcp_config(KIMI, tmp_path)

    assert config.read_bytes() == before, "the user's file was mutated before the atomic swap"


def test_every_intermediate_state_of_the_file_parses_as_json(tmp_path: Path) -> None:
    """A reader interleaved with a writer must never catch a partial document.

    Read *after* each of a series of writes rather than during, to pin the
    weaker but still necessary property that the file is left valid; the
    concurrent version below covers the during case.
    """
    _seed(tmp_path)
    config = tmp_path / ".kimi-code" / "mcp.json"
    for _ in range(5):
        terminal._merge_provider_mcp_config(KIMI, tmp_path)
        data = json.loads(config.read_text(encoding="utf-8"))
        assert data["mcpServers"]["user-owned"] == USER_SERVER
        assert data["trustedFolders"] == ["/a", "/b"]
        assert set(data["mcpServers"]) == {"user-owned", "scistudio"}


def test_a_key_added_between_two_writes_survives_the_second(tmp_path: Path) -> None:
    """The merge re-reads the file each time rather than caching what it saw.

    Kimi owns this file and edits it while SciStudio is running — registering a
    server through its own CLI is exactly the scenario. A merge that reused a
    snapshot from the first launch would silently revert that edit on the
    second, which no test that writes only once can catch.
    """
    _seed(tmp_path)
    config = tmp_path / ".kimi-code" / "mcp.json"
    terminal._merge_provider_mcp_config(KIMI, tmp_path)

    # Kimi (or the user) adds a server and a top-level key out of band.
    data = json.loads(config.read_text(encoding="utf-8"))
    data["mcpServers"]["added-later"] = {"command": "later"}
    data["addedLaterTopLevel"] = {"kept": True}
    config.write_text(json.dumps(data, indent=2), encoding="utf-8")

    terminal._merge_provider_mcp_config(KIMI, tmp_path)

    final = json.loads(config.read_text(encoding="utf-8"))
    assert final["mcpServers"]["added-later"] == {"command": "later"}
    assert final["mcpServers"]["user-owned"] == USER_SERVER
    assert final["addedLaterTopLevel"] == {"kept": True}
    assert final["trustedFolders"] == ["/a", "/b"]
    assert set(final["mcpServers"]) == {"user-owned", "added-later", "scistudio"}


# ---------------------------------------------------------------------------
# Spec §2 Edge Cases — concurrent injection
# ---------------------------------------------------------------------------


def test_a_concurrent_reader_never_observes_a_half_written_file(tmp_path: Path) -> None:
    """The spec's stated atomicity property, measured under real contention.

    Readers poll the config while several writers merge into it. Every read
    must either parse or fail to open; a read that parses must still contain
    the user's own server. A byte-level interleaving would show up as a
    ``JSONDecodeError``, and a lost-update as a missing ``user-owned`` entry.

    .. note::

       Concurrent *writers* are a different matter and are not asserted here.
       Measured on Windows at the time of writing, roughly 95% of overlapping
       calls raise ``PermissionError`` rather than serialising, because
       :func:`scistudio.cli.install._atomic_write_json` stages every write
       through one fixed temp path (``mcp.json.tmp``) that all writers share.
       The rename itself is atomic, which is why the reader-facing property
       below holds and the file is never corrupted — but the losing writer's
       MCP entry is simply not registered, and on the spawn path that surfaces
       as an agent launched without SciStudio's tools. A concurrent *reader*
       makes it worse still: a reader holding the file open blocks
       ``os.replace`` on Windows, so a provider CLI reading its own config
       while SciStudio launches can cause every writer to lose. Left unasserted
       rather than pinned, because the spec requires the write to *be* atomic,
       not to fail loudly.

       TODO(#1994): stage the merge write through a unique temp name (e.g.
       ``tempfile.mkstemp`` in the target directory) so overlapping writers
       serialise instead of colliding.
       Out of scope for this dispatch: A7 is test-only per
       ``docs/planning/adr-034-multi-provider-dispatch-prompts.md`` §A7, and
       ``scistudio/cli/install.py`` is production code.
       Followup: reported to the manager on issue #1994; needs an owner
       decision before ``_atomic_write_json`` changes, since ``scistudio
       install`` shares it.
    """
    _seed(tmp_path)
    config = tmp_path / ".kimi-code" / "mcp.json"

    partial_reads: list[str] = []
    lost_updates: list[list[str]] = []
    reads_completed = 0
    stop = threading.Event()
    lock = threading.Lock()

    def reader() -> None:
        nonlocal reads_completed
        while not stop.is_set():
            try:
                raw = config.read_text(encoding="utf-8")
            except OSError:
                # The file is momentarily unopenable during the swap on
                # Windows. Not an observation of partial content.
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                with lock:
                    partial_reads.append(f"{exc}: {raw[:120]!r}")
                continue
            with lock:
                reads_completed += 1
            servers = data.get("mcpServers", {})
            if "user-owned" not in servers or servers.get("user-owned") != USER_SERVER:
                with lock:
                    lost_updates.append(sorted(servers))

    def writer() -> None:
        for _ in range(40):
            # See the note above: writer contention is a known defect and is
            # not the property under test here, so a losing writer is ignored.
            with contextlib.suppress(OSError):
                terminal._merge_provider_mcp_config(KIMI, tmp_path)

    readers = [threading.Thread(target=reader, daemon=True) for _ in range(3)]
    writers = [threading.Thread(target=writer) for _ in range(4)]
    for thread in [*readers, *writers]:
        thread.start()
    for thread in writers:
        thread.join()
    stop.set()
    for thread in readers:
        thread.join(timeout=10)

    assert partial_reads == [], f"a reader observed a half-written file: {partial_reads[:3]}"
    assert lost_updates == [], f"a reader observed the user's own server missing: {lost_updates[:3]}"
    assert reads_completed > 0, "the readers never managed a successful read; the test proved nothing"

    # Whatever the writers managed, the user's content is intact and the file
    # parses. Deliberately no assertion that the SciStudio entry landed: with
    # readers holding the file open, Windows fails ``os.replace`` outright, so
    # under a hot reader *every* writer can lose. That is the second half of
    # the defect described above — a provider CLI reading its own config while
    # SciStudio launches is enough to stop the injection — and pinning the
    # entry here would make the test flake rather than make the write correct.
    # ``test_at_least_one_concurrent_writer_registers_the_scistudio_entry``
    # covers the writer-only case, which is deterministic.
    final = json.loads(config.read_text(encoding="utf-8"))
    assert final["mcpServers"]["user-owned"] == USER_SERVER
    assert final["trustedFolders"] == ["/a", "/b"]


def test_at_least_one_concurrent_writer_registers_the_scistudio_entry(tmp_path: Path) -> None:
    """The floor the current implementation does meet.

    Whatever happens to the losers of a write race, the file must end up with
    the SciStudio entry present and every unrelated key intact. This is
    deliberately the weakest assertion that is still worth making: it is what
    stops a future "fix" for the contention defect from trading correctness for
    liveness.
    """
    _seed(tmp_path)
    config = tmp_path / ".kimi-code" / "mcp.json"
    barrier = threading.Barrier(6)

    def writer() -> None:
        barrier.wait()
        # Losing a write race is tolerated; leaving the file wrong is not.
        with contextlib.suppress(OSError):
            terminal._merge_provider_mcp_config(KIMI, tmp_path)

    threads = [threading.Thread(target=writer) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    data = json.loads(config.read_text(encoding="utf-8"))
    assert "scistudio" in data["mcpServers"]
    assert data["mcpServers"]["user-owned"] == USER_SERVER
    assert data["trustedFolders"] == ["/a", "/b"]


def test_no_stray_temp_file_is_left_behind_after_a_successful_write(tmp_path: Path) -> None:
    """FR-013's sibling: the staging file must not become litter.

    An orphaned ``mcp.json.tmp`` in a directory the provider owns is confusing
    at best and, for a CLI that globs its config directory, actively harmful.
    """
    _seed(tmp_path)
    terminal._merge_provider_mcp_config(KIMI, tmp_path)

    leftovers = sorted(p.name for p in (tmp_path / ".kimi-code").iterdir() if p.name != "mcp.json")
    assert leftovers == [], f"staging files survived the write: {leftovers}"
