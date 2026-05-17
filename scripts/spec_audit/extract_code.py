"""extract_code — pull interface records from `src/scieasy/**` via static + runtime introspection.

V1 coverage:
  - Python ABCs / typing.Protocol classes (AST walker)
  - Pydantic v2 BaseModel subclasses (import + model_json_schema)
  - FastAPI routes (import app + app.openapi())
  - Typer CLI commands (import app + introspect Command tree)
  - Entry-points (parse pyproject.toml [project.entry-points.*])

V1 NOT covered (intentionally — will fold in follow-up PR after SSOT freezes):
  - MCP @mcp.tool decorators — TODO(#1090): needs FastMCP server boot + `await mcp.list_tools()`.
    The FastMCP runtime is async + requires project context; defer to follow-up.
  - WebSocket message-type discriminators — TODO(#1090): needs deeper AST inference
    (walk `WebSocket.send_json({"type": "X", ...})` literals). Manual entry into SSOT for V1.

Usage:
    python -m scripts.spec_audit.extract_code [--repo-root PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from .models import InterfaceRecord

# Maps src/scieasy/<sub>/ → Phase-1 module name. Manager curates after Phase 1 locks.
# Until Phase 1 locks N, we infer module = top-level subpackage.
DEFAULT_MODULE_MAP: dict[str, str] = {
    "blocks/base": "block-abc",
    "blocks/process": "block-abc",
    "blocks/io": "block-abc",
    "blocks/code": "block-abc",
    "blocks/app": "block-abc",
    "blocks/ai": "block-abc",
    "blocks/subworkflow": "block-abc",
    "core/types": "dataobject-types",
    "core/storage": "storage-backends",
    "core/lineage": "storage-backends",
    "core/versioning": "storage-backends",
    "api/routes": "rest-api",
    "api/ws": "ws-protocol",
    "ai/agent/mcp": "mcp-tools",
    "engine": "engine-runner",
    "workflow": "workflow-yaml",
    "cli": "cli-surface",
    "agent_provisioning": "provisioning",
}


def _module_for_path(path: Path, repo_root: Path) -> str:
    rel = path.relative_to(repo_root).as_posix()
    # Strip "src/scieasy/" prefix
    if rel.startswith("src/scieasy/"):
        rel = rel[len("src/scieasy/") :]
    for key, mod in DEFAULT_MODULE_MAP.items():
        if rel.startswith(key + "/") or rel == key + ".py":
            return mod
    # Fallback: first directory component
    parts = rel.split("/")
    return parts[0] if parts else "unknown"


# ---------------------------------------------------------------------------
# A. AST walk for ABC / Protocol / class-with-abstractmethod
# ---------------------------------------------------------------------------


def _is_abc_or_protocol(node: ast.ClassDef) -> str | None:
    """Return 'abc' / 'protocol' / None based on bases + decorators."""
    for base in node.bases:
        base_name = ast.unparse(base).strip()
        if base_name in {"ABC", "abc.ABC"}:
            return "abc"
        if base_name in {"Protocol", "typing.Protocol", "Protocol[*]"}:
            return "protocol"
        # Generic Protocol[T]
        if base_name.startswith("Protocol[") or base_name.startswith("typing.Protocol["):
            return "protocol"
    # @abstractmethod on any method also makes it ABC-flavored
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in item.decorator_list:
                deco_str = ast.unparse(deco).strip()
                if deco_str in {"abstractmethod", "abc.abstractmethod"}:
                    return "abc"
    return None


def _extract_signature(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    """Return a structured signature dict from a function AST node."""
    args = []
    for arg in func.args.args:
        args.append(
            {
                "name": arg.arg,
                "annotation": ast.unparse(arg.annotation).strip() if arg.annotation else None,
            }
        )
    returns = ast.unparse(func.returns).strip() if func.returns else None
    return {
        "name": func.name,
        "args": args,
        "returns": returns,
        "is_async": isinstance(func, ast.AsyncFunctionDef),
        "decorators": [ast.unparse(d).strip() for d in func.decorator_list],
    }


def _walk_python_file(path: Path, repo_root: Path) -> list[InterfaceRecord]:
    """Walk one .py file, emit records for ABCs / Protocols / Pydantic models."""
    records: list[InterfaceRecord] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        print(f"[extract_code] skip {path}: {exc}", file=sys.stderr)
        return records

    module = _module_for_path(path, repo_root)
    rel = path.relative_to(repo_root).as_posix()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        kind = _is_abc_or_protocol(node)
        bases = [ast.unparse(b).strip() for b in node.bases]
        is_pydantic = any(b in {"BaseModel", "pydantic.BaseModel"} for b in bases)

        if kind is None and not is_pydantic:
            continue

        cls_id = f"{module}.{node.name}"
        end_line = getattr(node, "end_lineno", node.lineno)

        # Emit the class itself
        records.append(
            InterfaceRecord(
                interface_id=cls_id,
                kind="pydantic" if is_pydantic else (kind or "abc"),
                module=module,
                source_file=rel,
                source_lines=f"L{node.lineno}-L{end_line}",
                signature={
                    "class_name": node.name,
                    "bases": bases,
                    "docstring": ast.get_docstring(node),
                },
            )
        )

        # Emit each public method (ABCs / Protocols only; Pydantic methods are usually private)
        if kind is not None:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_") and item.name != "__init__":
                        continue
                    sig = _extract_signature(item)
                    end = getattr(item, "end_lineno", item.lineno)
                    records.append(
                        InterfaceRecord(
                            interface_id=f"{cls_id}.{item.name}",
                            kind=kind,
                            module=module,
                            source_file=rel,
                            source_lines=f"L{item.lineno}-L{end}",
                            signature=sig,
                        )
                    )

    return records


# ---------------------------------------------------------------------------
# B. FastAPI app.openapi() snapshot
# ---------------------------------------------------------------------------


def _extract_fastapi(repo_root: Path) -> list[InterfaceRecord]:
    """Boot the FastAPI app, dump openapi(), emit a record per (path, method)."""
    records: list[InterfaceRecord] = []
    try:
        # Add src/ to sys.path
        src_path = repo_root / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        from scieasy.api.app import create_app  # type: ignore[import-not-found]

        app = create_app()
        spec = app.openapi()
        for path, methods in spec.get("paths", {}).items():
            for method, op in methods.items():
                if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                op_id = op.get("operationId") or f"{method.upper()} {path}"
                records.append(
                    InterfaceRecord(
                        interface_id=f"rest-api.{method.upper()}_{path}",
                        kind="fastapi_route",
                        module="rest-api",
                        source_file=None,  # FastAPI's introspection doesn't track source line
                        source_lines=None,
                        signature={
                            "method": method.upper(),
                            "path": path,
                            "summary": op.get("summary"),
                            "operation_id": op_id,
                            "parameters": op.get("parameters", []),
                            "request_body": op.get("requestBody"),
                            "responses": {
                                code: {"description": r.get("description")}
                                for code, r in op.get("responses", {}).items()
                            },
                        },
                    )
                )
    except Exception as exc:
        print(f"[extract_code] FastAPI introspection failed: {exc}", file=sys.stderr)
    return records


# ---------------------------------------------------------------------------
# C. Typer CLI commands
# ---------------------------------------------------------------------------


def _extract_typer(repo_root: Path) -> list[InterfaceRecord]:
    """Import scieasy.cli.main:app, walk registered commands."""
    records: list[InterfaceRecord] = []
    try:
        from scieasy.cli.main import app as cli_app  # type: ignore[import-not-found]

        # Typer wraps Click; introspect via cli_app.registered_commands and registered_groups
        for cmd in getattr(cli_app, "registered_commands", []):
            name = cmd.name or cmd.callback.__name__
            sig = {
                "command": name,
                "callback": cmd.callback.__qualname__,
                # `cmd.callback.__doc__` is the help text
                "help": (cmd.callback.__doc__ or "").strip().split("\n")[0],
            }
            records.append(
                InterfaceRecord(
                    interface_id=f"cli-surface.{name}",
                    kind="typer_command",
                    module="cli-surface",
                    source_file=None,
                    source_lines=None,
                    signature=sig,
                )
            )
        # Subgroups (e.g. `scieasy install` is a subcommand group)
        for grp in getattr(cli_app, "registered_groups", []):
            grp_name = grp.name or grp.typer_instance.info.name or "<unnamed>"
            for cmd in getattr(grp.typer_instance, "registered_commands", []):
                name = cmd.name or cmd.callback.__name__
                full = f"{grp_name} {name}"
                records.append(
                    InterfaceRecord(
                        interface_id=f"cli-surface.{grp_name}_{name}",
                        kind="typer_command",
                        module="cli-surface",
                        source_file=None,
                        source_lines=None,
                        signature={
                            "command": full,
                            "callback": cmd.callback.__qualname__,
                            "help": (cmd.callback.__doc__ or "").strip().split("\n")[0],
                        },
                    )
                )
    except Exception as exc:
        print(f"[extract_code] Typer introspection failed: {exc}", file=sys.stderr)
    return records


# ---------------------------------------------------------------------------
# D. Entry-points from pyproject.toml
# ---------------------------------------------------------------------------


def _extract_entry_points(repo_root: Path) -> list[InterfaceRecord]:
    records: list[InterfaceRecord] = []
    pp = repo_root / "pyproject.toml"
    if not pp.exists():
        return records
    data = tomllib.loads(pp.read_text(encoding="utf-8"))
    groups = data.get("project", {}).get("entry-points", {})
    for group_name, entries in groups.items():
        for ep_name, target in entries.items():
            ep_id = f"entry-points.{group_name}.{ep_name}"
            records.append(
                InterfaceRecord(
                    interface_id=ep_id,
                    kind="entry_point",
                    module="entry-points",
                    source_file="pyproject.toml",
                    source_lines=None,
                    signature={
                        "group": group_name,
                        "name": ep_name,
                        "target": target,
                    },
                )
            )
    return records


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def extract_all(repo_root: Path) -> list[InterfaceRecord]:
    records: list[InterfaceRecord] = []

    # A. Walk every .py under src/scieasy/ for ABC / Protocol / Pydantic
    src = repo_root / "src" / "scieasy"
    if src.exists():
        for py in src.rglob("*.py"):
            # Skip __pycache__ + test fixtures
            if "__pycache__" in py.parts or "_skills" in py.parts:
                continue
            records.extend(_walk_python_file(py, repo_root))

    # B. FastAPI routes
    records.extend(_extract_fastapi(repo_root))

    # C. Typer commands
    records.extend(_extract_typer(repo_root))

    # D. Entry-points
    records.extend(_extract_entry_points(repo_root))

    # TODO(#1090): MCP @mcp.tool surface — requires FastMCP server boot.
    #   Out of scope per spec_audit V1 — Phase 6 manager hand-enters these into
    #   INTERFACE_SPEC.md from the post-ADR-040 26-tool inventory; follow-up PR
    #   adds runtime introspection.
    # TODO(#1090): WS message type discriminators — requires AST inference
    #   of WebSocket.send_json({"type": "X", ...}) literals. Manual entry for V1.

    return records


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract interface records from code")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--out", type=Path, default=Path("build/spec-audit/code.json"))
    args = ap.parse_args()

    records = extract_all(args.repo_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([r.to_dict() for r in records], indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[extract_code] wrote {len(records)} records → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
