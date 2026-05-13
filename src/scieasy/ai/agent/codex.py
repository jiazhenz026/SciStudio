"""Codex CLI provider implementation.

The real Codex CLI differs from Claude Code in two important ways:

* non-interactive streaming is exposed through ``codex exec --json``;
* conversation continuity is exposed by spawning a new process with
  ``codex exec --json ... resume <thread_id> -``.

This module adapts that per-turn process model to SciEasy's
``AgentSession`` protocol. A ``CodexSession`` is a logical chat session;
each user message starts one Codex subprocess and ``stream_events()``
keeps waiting for subsequent turns until the SciEasy session is closed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from scieasy.ai.agent.binary_discovery import find_binary
from scieasy.ai.agent.errors import AgentLaunchError, AgentNotInstalledError
from scieasy.ai.agent.provider import (
    AgentEvent,
    AgentProvider,
    AgentSession,
    AssistantTextDeltaEvent,
    DoneEvent,
    ErrorEvent,
    InitEvent,
    OtherEvent,
    PermissionMode,
    ProviderStatus,
    ToolResultEvent,
    ToolUseEvent,
)

logger = logging.getLogger(__name__)


_VERSION_TIMEOUT_SECONDS = 5.0
_LOGIN_PROBE_TIMEOUT_SECONDS = 2.0
_CLOSE_GRACE_SECONDS = 5.0

_INSTALL_HINT = "Install the Codex CLI: see https://github.com/openai/codex for installation and login instructions."


def _toml_string(value: str) -> str:
    """Return a TOML-compatible quoted string for ``codex -c`` overrides."""
    return json.dumps(value)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(v) for v in values) + "]"


async def _read_stderr(stream: asyncio.StreamReader | None) -> str:
    if stream is None:
        return ""
    chunks: list[bytes] = []
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


async def _read_stdout_lines(stream: asyncio.StreamReader) -> AsyncIterator[bytes]:
    while True:
        line = await stream.readline()
        if not line:
            return
        yield line


def _normalise_codex_event(payload: dict[str, Any]) -> AgentEvent | list[AgentEvent]:
    """Translate Codex JSONL frames to SciEasy's canonical event taxonomy."""
    event_type = payload.get("type")

    if event_type == "thread.started":
        thread_id = payload.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            return InitEvent(kind="init", raw=payload, session_id=thread_id)
        return OtherEvent(kind="thread.started", raw=payload)

    if event_type == "turn.started":
        return OtherEvent(kind="turn.started", raw={**payload, "_chat_hidden": True})

    if event_type == "turn.completed":
        return DoneEvent(kind="done", raw=payload)

    if event_type in {"turn.failed", "error"}:
        message = payload.get("message") or payload.get("error") or json.dumps(payload)
        return ErrorEvent(kind="error", raw=payload, message=str(message), error_type=str(event_type))

    if event_type in {"item.completed", "item.started", "item.updated"}:
        item = payload.get("item")
        if not isinstance(item, dict):
            return OtherEvent(kind=str(event_type), raw=payload)
        item_type = item.get("type")
        if item_type == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text:
                return AssistantTextDeltaEvent(kind="assistant_text_delta", raw=payload, delta=text)
            return OtherEvent(kind="agent_message", raw={**payload, "_chat_hidden": True})
        if item_type in {"function_call", "tool_call"}:
            name = item.get("name") or item.get("tool_name")
            arguments = item.get("arguments") or item.get("input") or item.get("tool_input") or {}
            if isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                    arguments = parsed if isinstance(parsed, dict) else {"arguments": parsed}
                except json.JSONDecodeError:
                    arguments = {"arguments": arguments}
            call_id = item.get("call_id") or item.get("id")
            if isinstance(name, str) and isinstance(arguments, dict) and isinstance(call_id, str):
                return ToolUseEvent(
                    kind="tool_use",
                    raw=payload,
                    tool_name=name,
                    tool_input=arguments,
                    tool_use_id=call_id,
                )
        if item_type in {"function_call_output", "tool_call_output"}:
            call_id = item.get("call_id") or item.get("tool_use_id") or item.get("id")
            output = item.get("output") or item.get("content") or ""
            if isinstance(call_id, str):
                return ToolResultEvent(
                    kind="tool_result",
                    raw=payload,
                    tool_use_id=call_id,
                    output=output,
                    is_error=bool(item.get("is_error", False)),
                )
        return OtherEvent(kind=f"{event_type}/{item_type}" if item_type else str(event_type), raw=payload)

    return OtherEvent(kind=str(event_type) if isinstance(event_type, str) else "other", raw=payload)


class CodexSession:
    """Logical Codex chat session backed by one subprocess per user turn."""

    def __init__(
        self,
        *,
        argv0: list[str],
        project_dir: Path,
        chat_id: str,
        system_prompt: str,
        mcp_config: dict[str, Any],
        permission_mode: PermissionMode,
        model: str | None,
        resume_session_id: str | None,
        temp_files: list[Path],
    ) -> None:
        self._argv0 = argv0
        self._project_dir = project_dir
        self._chat_id = chat_id
        self._system_prompt = system_prompt
        self._mcp_config = mcp_config
        self._permission_mode = permission_mode
        self._model = model
        self._temp_files = list(temp_files)
        self._turn_ready = asyncio.Event()
        self._closed = False
        self._cancelled = False
        self._active_proc: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[str] | None = None

        self.session_id: str | None = resume_session_id
        self.pid: int = 0

    @property
    def temp_files(self) -> list[Path]:
        return list(self._temp_files)

    async def send_user_message(self, content: str) -> None:
        if self._closed:
            raise AgentLaunchError("codex session is closed; cannot send_user_message")
        if self._active_proc is not None and self._active_proc.returncode is None:
            raise AgentLaunchError("codex turn already in progress")

        argv = self._build_turn_argv()
        env = os.environ.copy()
        env["SCIEASY_PERMISSION_MODE"] = self._permission_mode.value
        env["SCIEASY_CHAT_ID"] = self._chat_id
        env["SCIEASY_PROJECT_DIR"] = str(self._project_dir)

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0

        logger.info("CodexSession.send_user_message: spawning argv=%r cwd=%s", argv, self._project_dir)
        try:
            proc = await _spawn(argv=argv, cwd=self._project_dir, env=env, creationflags=creationflags)
        except OSError as exc:
            raise AgentLaunchError(f"failed to spawn codex subprocess: {exc}") from exc

        self._active_proc = proc
        self.pid = proc.pid
        self._stderr_task = asyncio.create_task(_read_stderr(proc.stderr))

        if proc.stdin is None:
            raise AgentLaunchError("codex subprocess stdin is not piped")
        proc.stdin.write(self._compose_prompt(content).encode("utf-8"))
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            await proc.stdin.drain()
        with contextlib.suppress(OSError):
            proc.stdin.close()
        with contextlib.suppress(OSError, asyncio.CancelledError, AttributeError):
            await proc.stdin.wait_closed()
        self._turn_ready.set()

    async def stream_events(self) -> AsyncIterator[AgentEvent]:
        while True:
            await self._turn_ready.wait()
            if self._closed:
                return

            proc = self._active_proc
            if proc is None:
                self._turn_ready.clear()
                continue
            if proc.stdout is None:
                raise AgentLaunchError("codex subprocess stdout is not piped")

            async for line in _read_stdout_lines(proc.stdout):
                try:
                    payload = json.loads(line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError as exc:
                    logger.warning("CodexSession.stream_events: non-JSON stdout line ignored: %s", exc)
                    continue
                if not isinstance(payload, dict):
                    yield OtherEvent(kind="other", raw={"payload": payload})
                    continue
                event_or_events = _normalise_codex_event(payload)
                events = event_or_events if isinstance(event_or_events, list) else [event_or_events]
                for event in events:
                    if isinstance(event, InitEvent):
                        self.session_id = event.session_id
                    yield event

            returncode = await proc.wait()
            stderr = ""
            if self._stderr_task is not None:
                stderr = await self._stderr_task
            self._active_proc = None
            self._stderr_task = None
            self._turn_ready.clear()

            if returncode != 0 and not self._cancelled:
                yield ErrorEvent(
                    kind="error",
                    raw={"returncode": returncode, "stderr": stderr},
                    message=stderr.strip() or f"codex exited with status {returncode}",
                    error_type="CodexExitError",
                )

    def _build_turn_argv(self) -> list[str]:
        argv = [*self._argv0, "exec"]
        argv += ["--json", "--skip-git-repo-check", "-C", str(self._project_dir)]
        if self._model is not None:
            argv += ["--model", self._model]
        if self._permission_mode is PermissionMode.BYPASS:
            argv += ["--dangerously-bypass-approvals-and-sandbox"]
        else:
            argv += ["--sandbox", "read-only"]
        argv += self._mcp_overrides()
        if self.session_id is not None:
            argv += ["resume", self.session_id, "-"]
        else:
            argv.append("-")
        return argv

    def _mcp_overrides(self) -> list[str]:
        server = (self._mcp_config.get("mcpServers") or {}).get("scieasy")
        if not isinstance(server, dict):
            return []
        command = server.get("command")
        args = server.get("args", [])
        env = server.get("env", {})
        if not isinstance(command, str) or not isinstance(args, list):
            return []

        overrides = [
            "-c",
            f"mcp_servers.scieasy.command={_toml_string(command)}",
            "-c",
            f"mcp_servers.scieasy.args={_toml_array([str(arg) for arg in args])}",
        ]
        if isinstance(env, dict):
            entries = [f"{key}={_toml_string(str(value))}" for key, value in sorted(env.items())]
            if entries:
                overrides += ["-c", "mcp_servers.scieasy.env={" + ", ".join(entries) + "}"]
        return overrides

    def _compose_prompt(self, content: str) -> str:
        return (
            "System instructions for this SciEasy embedded agent session:\n"
            f"{self._system_prompt}\n\n"
            "User message:\n"
            f"{content}\n"
        )

    def _kill_process_tree(self, *, caller: str) -> None:
        proc = self._active_proc
        if proc is None or proc.returncode is not None:
            return
        if sys.platform == "win32":
            with contextlib.suppress(OSError):
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False, capture_output=True)
        else:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        logger.info("CodexSession.%s: killed active turn process pid=%s", caller, proc.pid)

    async def cancel(self) -> None:
        self._cancelled = True
        self._kill_process_tree(caller="cancel")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._turn_ready.set()

        proc = self._active_proc
        if proc is not None and proc.returncode is None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=_CLOSE_GRACE_SECONDS)
            except TimeoutError:
                self._kill_process_tree(caller="close")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
        if self._stderr_task is not None:
            with contextlib.suppress(Exception):
                await self._stderr_task
        for path in self._temp_files:
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)


class CodexProvider:
    """Provider for the real ``codex`` CLI."""

    name: ClassVar[str] = "codex"
    binary_name: ClassVar[str] = "codex"

    def __init__(self, *, binary_override: Path | None = None) -> None:
        self._binary_override = binary_override

    @classmethod
    def discover(cls) -> ProviderStatus:
        binary_path = find_binary(cls.binary_name)
        if binary_path is None:
            return ProviderStatus(
                name=cls.name,
                available=False,
                binary_path=None,
                version=None,
                logged_in=False,
                install_hint=_INSTALL_HINT,
            )

        version: str | None = None
        available = False
        try:
            completed = subprocess.run(
                [str(binary_path), "--version"],
                capture_output=True,
                text=True,
                timeout=_VERSION_TIMEOUT_SECONDS,
                check=False,
            )
            if completed.returncode == 0:
                version = (completed.stdout or completed.stderr or "").strip() or None
                available = True
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("CodexProvider.discover: --version probe failed: %s", exc)

        logged_in = False
        if available:
            try:
                completed = subprocess.run(
                    [str(binary_path), "login", "status"],
                    capture_output=True,
                    text=True,
                    timeout=_LOGIN_PROBE_TIMEOUT_SECONDS,
                    check=False,
                )
                logged_in = completed.returncode == 0
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.debug("CodexProvider.discover: login probe failed: %s", exc)

        return ProviderStatus(
            name=cls.name,
            available=available,
            binary_path=binary_path if available else None,
            version=version,
            logged_in=logged_in,
            install_hint=None if available else _INSTALL_HINT,
        )

    async def start_session(
        self,
        *,
        project_dir: Path,
        chat_id: str,
        system_prompt: str,
        mcp_config: dict[str, Any],
        resume_session_id: str | None,
        permission_mode: PermissionMode,
        model: str | None = None,
    ) -> AgentSession:
        if self._binary_override is not None:
            argv0 = [sys.executable, str(self._binary_override)]
        else:
            binary_path = find_binary(self.binary_name)
            if binary_path is None:
                raise AgentNotInstalledError("codex binary not found on PATH or in any fallback location")
            argv0 = [str(binary_path)]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as prompt_handle:
            prompt_handle.write(system_prompt)
            prompt_path = Path(prompt_handle.name)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as mcp_handle:
            json.dump(mcp_config, mcp_handle)
            mcp_path = Path(mcp_handle.name)

        return CodexSession(
            argv0=argv0,
            project_dir=project_dir,
            chat_id=chat_id,
            system_prompt=system_prompt,
            mcp_config=mcp_config,
            permission_mode=permission_mode,
            model=model,
            resume_session_id=resume_session_id,
            temp_files=[prompt_path, mcp_path],
        )


async def _spawn(
    *,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    creationflags: int,
) -> asyncio.subprocess.Process:
    kwargs: dict[str, Any] = dict(
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
        env=env,
    )
    if creationflags:
        kwargs["creationflags"] = creationflags
    elif sys.platform != "win32":
        kwargs["start_new_session"] = True
    return await asyncio.create_subprocess_exec(*argv, **kwargs)


_PROTOCOL_CONFORMANCE: type[AgentProvider] = CodexProvider
