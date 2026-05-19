"""Generate CLI reference docs from Typer application metadata."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from scieasy.qa.docs._helpers import build_result, join_markdown_lines
from scieasy.qa.docs._models import GeneratorResult

MARKER = "<!-- generated-by: cli_reference -->"
DEFAULT_TARGET_PATH = Path("docs/user/reference/cli.md")


def _import_command(command_import: str) -> Any:
    module_name, symbol = command_import.split(":", 1)
    module = import_module(module_name)
    return getattr(module, symbol)


def _collect_commands(app: Any) -> list[str]:
    commands: list[object] = []

    for attr in ("registered_commands", "commands", "_objects"):
        value = getattr(app, attr, None)
        if value is None:
            continue
        if isinstance(value, dict):
            if attr == "commands":
                commands = list(value.values())
                break
            commands = list(value.values())
            break
        if isinstance(value, list | tuple):
            commands = list(value)
            break

    rows: list[str] = []
    if not commands:
        return []

    for command in sorted(commands, key=lambda item: str(getattr(item, "name", ""))):
        name = getattr(command, "name", "")
        if not name:
            continue
        help_text = (getattr(command, "help", "") or "").strip()
        params = ", ".join(str(getattr(param, "name", "")) for param in getattr(command, "params", []))
        rows.append(f"- `{name}` {help_text} (params: {params or 'none'})")

    return rows


def generate(
    repo_root: Path,
    *,
    output_path: Path = DEFAULT_TARGET_PATH,
    command_import: str = "scieasy.cli.main:app",
) -> GeneratorResult:
    app = _import_command(command_import)
    commands = _collect_commands(app)
    if not commands:
        commands = ["No CLI commands found."]

    content = join_markdown_lines([MARKER, "# CLI Reference", "", "## Commands", *commands])
    return build_result(
        generator_id="cli_reference",
        repo_root=repo_root,
        target_path=output_path,
        source_paths=[Path("src/scieasy/cli/main.py")],
        content=content,
        marker=MARKER,
    )
