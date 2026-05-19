"""Generate API reference docs from FastAPI app OpenAPI schema."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from scieasy.qa.docs._helpers import build_result

MARKER = "<!-- generated-by: openapi_reference -->"
DEFAULT_TARGET_PATH = Path("docs/user/reference/server-api.md")


def _import_app(import_path: str):
    module_name, symbol = import_path.split(":", 1)
    module = import_module(module_name)
    target = getattr(module, symbol)
    if callable(target):
        return target()
    return target


def generate(
    repo_root: Path,
    *,
    output_path: Path = DEFAULT_TARGET_PATH,
    app_import: str = "scieasy.api.app:create_app",
) -> object:
    app = _import_app(app_import)
    schema = app.openapi()
    lines = [MARKER, "# Server API", ""]
    if not schema:
        lines.append("No OpenAPI schema generated.")
        content = "\n".join(lines) + "\n"
        return build_result(
            generator_id="openapi_reference",
            repo_root=repo_root,
            target_path=output_path,
            source_paths=[Path("src/scieasy/api")],
            content=content,
            marker=MARKER,
        )

    for path, methods in sorted(schema.get("paths", {}).items()):
        lines.append(f"## {path}")
        for method, details in sorted(methods.items()):
            summary = details.get("summary", "")
            lines.append(f"- {method.upper()}: {summary}")
        lines.append("")
    content = "\n".join(lines) + "\n"
    return build_result(
        generator_id="openapi_reference",
        repo_root=repo_root,
        target_path=output_path,
        source_paths=[Path("src/scieasy/api")],
        content=content,
        marker=MARKER,
    )
