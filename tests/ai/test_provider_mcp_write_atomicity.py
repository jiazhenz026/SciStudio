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

These tests originally pinned only the reader-facing half, because concurrent
*writers* demonstrably did not all succeed: every write staged through one fixed
``mcp.json.tmp`` path, so overlapping writers collided and 227 of 240 raised
``PermissionError``. That defect is fixed — :func:`~scistudio.cli.install.
_atomic_write_json` now stages each write through a uniquely named file in the
target's own directory — so the writer half is asserted here too, and the
weakened assertions that documented the defect are gone.

One boundary is worth stating precisely, because two different Windows sharing
problems live on this path and only one of them is the write:

* **The rename**, which this file's fix owns. Now collision-free: 240
  overlapping ``_atomic_write_json`` calls complete with zero failures.
* **The read** that :func:`scistudio.ai.agent.terminal._merge_provider_mcp_config`
  performs before merging. ``os.replace`` briefly makes the destination
  unopenable on Windows, so a concurrent reader can still catch a
  ``PermissionError`` opening it. Every residual failure measured under sustained
  writer contention originates there, not in the write. It is a separate defect
  in a separate module and is deliberately not pinned here as if it were
  intended.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import threading
from pathlib import Path
from unittest import mock

import pytest

from scistudio.ai.agent import providers_registry as registry
from scistudio.ai.agent import terminal
from scistudio.cli import install

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

       Three readers spinning as fast as Python can open a file is a
       pathological load, not a realistic one, and it is used here precisely
       because it is the harshest test of the reader-facing property. Under it,
       writer failures are tolerated rather than asserted away, for two reasons
       that are both about the platform rather than about this test being
       lenient:

       * ``os.replace`` cannot rename over a destination another process holds
         open on Windows, and a reader in a tight loop essentially never lets
         go. :func:`~scistudio.cli.install._replace_with_retry` spends a bounded
         budget and then **raises**, which is the deliberate choice — a lost
         write must be loud, since silently skipping it launches an agent with
         no SciStudio tools and no explanation.
       * The merge's own read can fail the same way, and that half lives in
         ``terminal.py`` rather than in the write helper.

       The realistic simultaneous-launch case is asserted strictly instead, with
       no tolerance at all, by
       :func:`test_simultaneous_launches_all_register_without_colliding`.
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
            # See the note above: under a pathological hot reader a write can
            # legitimately fail loudly, and the merge's own read can fail too.
            # Neither is the property under test here.
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

    # Whatever the writers managed, the user's content is intact, the file
    # parses, and the SciStudio entry is registered. Under a hot reader some
    # individual writes legitimately raise, but they cannot all be lost: with
    # unique staging files the writers no longer knock each other out, so at
    # least one rename lands.
    final = json.loads(config.read_text(encoding="utf-8"))
    assert final["mcpServers"]["user-owned"] == USER_SERVER
    assert final["trustedFolders"] == ["/a", "/b"]
    assert "scistudio" in final["mcpServers"]


def test_simultaneous_launches_all_register_without_colliding(tmp_path: Path) -> None:
    """The defect this fix exists to remove, asserted with no tolerance.

    Several AI Blocks configured ``kimi-code`` starting in one project is an
    ordinary workflow, and every one of those launches must register its entry.

    Before the fix, every write staged through the same ``mcp.json.tmp``, so the
    writers destroyed each other's staging file: 227 of 240 overlapping calls
    raised ``PermissionError``. Nothing surfaced that to the user — the rename
    was still atomic and the file never corrupt — so the only symptom was an
    agent that came up with no SciStudio tools.

    Nothing is suppressed and nothing is tolerated here: any failure is a real
    regression and must fail the test. The barrier makes the overlap genuine
    rather than hoping the threads happen to interleave.
    """
    _seed(tmp_path)
    config = tmp_path / ".kimi-code" / "mcp.json"
    launches = 8
    barrier = threading.Barrier(launches)
    failures: list[str] = []
    lock = threading.Lock()

    def writer() -> None:
        barrier.wait()
        try:
            terminal._merge_provider_mcp_config(KIMI, tmp_path)
        except OSError as exc:  # pragma: no cover - the regression this guards
            with lock:
                failures.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=writer) for _ in range(launches)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == [], f"{len(failures)} of {launches} concurrent launches lost their write: {failures[:3]}"

    data = json.loads(config.read_text(encoding="utf-8"))
    assert "scistudio" in data["mcpServers"]
    assert data["mcpServers"]["user-owned"] == USER_SERVER
    assert data["trustedFolders"] == ["/a", "/b"]


def test_concurrent_writes_never_share_a_staging_file(tmp_path: Path) -> None:
    """The mechanism, not just the symptom: every write stages somewhere unique.

    A future refactor could reintroduce a deterministic temp name and the timing
    tests above would still pass on a fast enough machine, because the collision
    is timing dependent. Capturing the source path of every rename removes that
    luck: the names must all differ, and they must sit in the target's own
    directory, because ``os.replace`` is only atomic within one filesystem.
    """
    target = tmp_path / "provider" / "mcp.json"
    staged: list[Path] = []
    lock = threading.Lock()
    real_replace = os.replace

    def recording_replace(src: object, dst: object) -> None:
        with lock:
            staged.append(Path(str(src)))
        real_replace(src, dst)  # type: ignore[arg-type]

    with mock.patch.object(os, "replace", recording_replace):
        barrier = threading.Barrier(8)

        def writer(index: int) -> None:
            barrier.wait()
            for attempt in range(5):
                install._atomic_write_json(target, {"mcpServers": {"scistudio": {"w": index, "n": attempt}}})

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    # ``staged`` counts rename *attempts*, which can exceed the 40 writes when a
    # busy destination is retried — a retry reuses its own staging file, so the
    # distinct-path count is what pins uniqueness.
    assert len(staged) >= 40
    assert len(set(staged)) == 40, "two writes staged through the same temp path"
    assert {p.parent for p in staged} == {target.parent}, "staging happened outside the target's directory"
    assert set(json.loads(target.read_text(encoding="utf-8"))["mcpServers"]["scistudio"]) == {"w", "n"}


def test_a_failed_write_leaves_no_staging_file_behind(tmp_path: Path) -> None:
    """A crashed write must not litter a directory the provider owns.

    A stray ``.mcp.json.<pid>-<uuid>.tmp`` is confusing at best, and for a CLI
    that globs its own config directory it is actively harmful. The failure is
    injected at the rename, so the staging file definitely exists by then.
    """
    config = _seed(tmp_path)
    before = config.read_bytes()

    def refuse(_src: object, _dst: object) -> None:
        raise OSError("simulated rename failure")

    with mock.patch.object(os, "replace", refuse), pytest.raises(OSError, match="simulated rename failure"):
        terminal._merge_provider_mcp_config(KIMI, tmp_path)

    leftovers = sorted(p.name for p in (tmp_path / ".kimi-code").iterdir() if p.name != "mcp.json")
    assert leftovers == [], f"a failed write left staging files behind: {leftovers}"
    assert config.read_bytes() == before


def test_a_busy_destination_is_retried_and_then_raised(tmp_path: Path) -> None:
    """Retry-then-raise: transient contention absorbed, a stuck one surfaced.

    Windows refuses to rename over a destination another process holds open, and
    that clears on its own in microseconds, so a bounded retry turns nearly every
    occurrence into a success. When it does not clear, the error must propagate.
    Swallowing it is the one outcome that is never acceptable: it produces
    exactly the silent, unexplained tool-less agent this fix exists to remove.
    """
    target = tmp_path / "mcp.json"
    real_replace = os.replace
    calls = itertools.count()

    def busy_twice(src: object, dst: object) -> None:
        if next(calls) < 2:
            raise PermissionError(13, "The process cannot access the file")
        real_replace(src, dst)  # type: ignore[arg-type]

    with mock.patch.object(os, "replace", busy_twice):
        install._atomic_write_json(target, {"ok": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}

    def always_busy(_src: object, _dst: object) -> None:
        raise PermissionError(13, "The process cannot access the file")

    with mock.patch.object(os, "replace", always_busy), pytest.raises(PermissionError):
        install._atomic_write_json(tmp_path / "never.json", {"ok": True})

    assert not (tmp_path / "never.json").exists()
    leftovers = sorted(p.name for p in tmp_path.iterdir() if p.name != "mcp.json")
    assert leftovers == [], f"an exhausted retry left staging files behind: {leftovers}"


def test_no_stray_temp_file_is_left_behind_after_a_successful_write(tmp_path: Path) -> None:
    """FR-013's sibling: the staging file must not become litter.

    An orphaned ``mcp.json.tmp`` in a directory the provider owns is confusing
    at best and, for a CLI that globs its config directory, actively harmful.
    """
    _seed(tmp_path)
    terminal._merge_provider_mcp_config(KIMI, tmp_path)

    leftovers = sorted(p.name for p in (tmp_path / ".kimi-code").iterdir() if p.name != "mcp.json")
    assert leftovers == [], f"staging files survived the write: {leftovers}"
