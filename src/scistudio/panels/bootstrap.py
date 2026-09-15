"""The resident panel subprocess: import ``panel.py``, run ``setup``, serve calls."""
# The resident panel subprocess: import ``panel.py``, run ``setup``, serve calls.
#
# Run as ``python -m scistudio.panels.bootstrap`` by the process host
# (:mod:`scistudio.panels.process`). ADR-054 MiniApp FR-006/FR-007/FR-009.
#
# Before any author code runs the bootstrap reserves the control channel: the
# process's original stdin/stdout become the request/response pipe, then fd 0/1/2
# are redirected so ``print`` and any early write land in the per-context log the
# host attached to stderr — never on the channel — and a read of stdin returns
# EOF. The channel is a plain OS pipe; no network port is opened, and the process
# exits when the request pipe closes so it cannot outlive a backend that died.

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import json
import os
import sys
import traceback
from types import ModuleType
from typing import Any, BinaryIO

from scistudio.panels.process_config import max_result_bytes
from scistudio.panels.protocol import ProtocolError, recv_frame, send_frame

_RESERVED = {"setup", "teardown"}


def _reserve_channel() -> tuple[BinaryIO, BinaryIO]:
    """Save stdin/stdout as the pipe, then point fd 0/1/2 away from it.

    Returns ``(response, request)`` binary streams. ``os.dup`` copies the pipe
    ends to fresh descriptors; ``os.dup2(2, 1)`` makes stdout follow stderr into
    the host's log, and stdin is reopened on the null device so author code that
    reads it simply sees EOF. ``dup``/``dup2`` behave identically on POSIX and
    Windows.
    """
    request_fd = os.dup(0)
    response_fd = os.dup(1)
    os.dup2(2, 1)
    null_fd = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null_fd, 0)
    os.close(null_fd)
    # Rebind Python's own stdio objects to the redirected descriptors so a
    # print() or an uncaught traceback inside author code reaches the log.
    sys.stdout = os.fdopen(1, "w", buffering=1, closefd=False)
    sys.stdin = os.fdopen(0, "r", closefd=False)
    return os.fdopen(response_fd, "wb", buffering=0), os.fdopen(request_fd, "rb", buffering=0)


def _import_panel() -> ModuleType:
    """Import ``panel.py`` from the panel directory as the module named ``panel``."""
    panel_dir = os.environ["SCISTUDIO_PANEL_DIR"]
    if panel_dir not in sys.path:
        sys.path.insert(0, panel_dir)
    path = os.path.join(panel_dir, "panel.py")
    spec = importlib.util.spec_from_file_location("panel", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load panel.py from {panel_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["panel"] = module
    spec.loader.exec_module(module)
    return module


def _collect_callables(module: ModuleType) -> dict[str, Any]:
    """Public functions defined in ``panel.py`` itself, other than setup/teardown."""
    # Public functions defined in ``panel.py`` itself, other than setup/teardown.
    #
    # FR-007 names *functions*: a class defined in ``panel.py`` is callable and
    # carries the module's ``__module__``, but constructing one over the call
    # channel is not what the page was given a function surface for, and the
    # instance it returns is not a result the protocol can send. ``isfunction``
    # keeps the surface to what the author wrote as a function.
    #
    # A name the module only imports has a different ``__module__`` and is not
    # callable through the panel either.
    result: dict[str, Any] = {}
    for name, value in vars(module).items():
        if name.startswith("_") or name in _RESERVED:
            continue
        if inspect.isfunction(value) and getattr(value, "__module__", None) == module.__name__:
            result[name] = value
    return result


def _reconstruct(payload: Any) -> Any:
    """Rebuild the target as a SciStudio data object from its storage reference.

    Uses the engine's own reconstruction (:func:`_reconstruct_one`), which keeps
    data lazy until the panel reads it. A collection payload becomes a list of
    reconstructed items; ``None`` (no resolvable target) is passed through.
    """
    if payload is None:
        return None
    from scistudio.core.types.serialization import _reconstruct_one

    if isinstance(payload, dict) and payload.get("kind") == "collection":
        return [_reconstruct_one(item) for item in payload.get("items", []) if isinstance(item, dict)]
    return _reconstruct_one(payload)


def _error(exc: BaseException) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }


def _result_frame(request_id: Any, value: Any) -> tuple[dict[str, Any], bytes]:
    """A NumPy array is sent as a raw buffer with dtype and shape; else JSON."""
    # A NumPy array is sent as a raw buffer with dtype and shape; else JSON.
    #
    # Enforces the result byte budget on this side so an oversized result fails
    # with ``too_large`` before it crosses the pipe (FR-011).
    import json

    limit = max_result_bytes()
    array = _as_numpy(value)
    if array is not None:
        import numpy as np

        contiguous = np.ascontiguousarray(array)
        buffer = contiguous.tobytes()
        if len(buffer) > limit:
            return {"id": request_id, "type": "error", "error_code": "too_large"}, b""
        header = {
            "id": request_id,
            "type": "result",
            "binary": True,
            "dtype": contiguous.dtype.str,
            "shape": list(contiguous.shape),
        }
        return header, buffer
    body = json.dumps({"result": value}, allow_nan=False)
    if len(body.encode("utf-8")) > limit:
        return {"id": request_id, "type": "error", "error_code": "too_large"}, b""
    return {"id": request_id, "type": "result", "result": value}, b""


def _as_numpy(value: Any) -> Any:
    if type(value).__module__.split(".")[0] != "numpy":
        return None
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a core dependency
        return None
    return value if isinstance(value, np.ndarray) else None


def _dispatch(callables: dict[str, Any], header: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    request_id = header.get("id")
    fn_name = header.get("fn")
    fn = callables.get(fn_name) if isinstance(fn_name, str) else None
    if fn is None:
        return {
            "id": request_id,
            "type": "error",
            "error": {"type": "UnknownFunction", "message": f"panel.py has no callable {fn_name!r}", "traceback": ""},
        }, b""
    args = header.get("args") or {}
    if not isinstance(args, dict):
        return {
            "id": request_id,
            "type": "error",
            "error": {"type": "TypeError", "message": "args must be a JSON object", "traceback": ""},
        }, b""
    try:
        return _result_frame(request_id, fn(**args))
    except Exception as exc:  # an author exception must not end the process (FR-011)
        return {"id": request_id, "type": "error", "error": _error(exc)}, b""


def _serve(request: BinaryIO, response: BinaryIO, module: ModuleType | None, callables: dict[str, Any]) -> None:
    while True:
        try:
            header, _ = recv_frame(request, max_payload=max_result_bytes())
        except ProtocolError:
            _teardown(module)
            return
        kind = header.get("type")
        if kind == "shutdown":
            _teardown(module)
            return
        if kind != "call":
            continue
        out_header, payload = _dispatch(callables, header)
        try:
            send_frame(response, out_header, payload)
        except (OSError, ProtocolError):
            _teardown(module)
            return


def _teardown(module: ModuleType | None) -> None:
    teardown = getattr(module, "teardown", None) if module is not None else None
    if callable(teardown):
        try:
            teardown()
        except Exception:  # teardown failures must not block exit
            traceback.print_exc()


def main() -> None:
    response, request = _reserve_channel()
    try:
        header, _ = recv_frame(request, max_payload=max_result_bytes())
    except ProtocolError:
        return
    if header.get("type") != "setup":
        return
    module: ModuleType | None = None
    callables: dict[str, Any] = {}
    try:
        from scistudio.engine.runners.worker import _prepend_runtime_import_roots

        _prepend_runtime_import_roots(json.loads(os.environ.get("SCISTUDIO_PANEL_IMPORT_ROOTS", "[]")))
        module = _import_panel()
        data = _reconstruct(header.get("data"))
        callables = _collect_callables(module)
        setup = getattr(module, "setup", None)
        if callable(setup):
            setup(data)
    except BaseException as exc:  # import/setup failure is start_failed, then exit
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        with contextlib.suppress(OSError, ProtocolError):
            send_frame(response, {"type": "setup_failed", "error": _error(exc)})
        return
    try:
        send_frame(response, {"type": "ready"})
    except (OSError, ProtocolError):
        return
    _serve(request, response, module, callables)


if __name__ == "__main__":
    main()
