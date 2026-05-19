"""Generate schema catalog from in-repo Pydantic model declarations."""

from __future__ import annotations

import ast
from pathlib import Path

from scieasy.qa.docs._helpers import build_result

MARKER = "<!-- generated-by: schema_reference -->"


def _scan_for_models(path: Path, package_prefix: str) -> list[str]:
    names: list[str] = []
    for file in path.rglob("*.py"):
        if ".venv" in file.parts:
            continue
        try:
            source = file.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(file))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            inherits = False
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "BaseModel":
                    inherits = True
                    break
                if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
                    inherits = True
                    break
            if not inherits:
                continue
            relative = str(file.relative_to(path.parent.parent))
            module_path = relative[:-3].replace("\\", ".").replace("/", ".")
            names.append(f"{package_prefix}.{module_path}.{node.name}")
    return sorted(set(names))


def _class_for_prefix(prefixes: tuple[str, ...]) -> list[str]:
    if not prefixes:
        return ["scieasy"]
    return list(prefixes)


def generate(
    repo_root: Path,
    *,
    output_dir: Path = Path("docs/user/reference/schemas"),
    package_prefixes: tuple[str, ...] = ("scieasy",),
) -> list:
    targets = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for prefix in _class_for_prefix(package_prefixes):
        package_root = repo_root / "src" / prefix.replace(".", "/")
        if not package_root.exists():
            continue
        models = _scan_for_models(package_root, prefix)
        lines = [MARKER, f"# Schema Reference: {prefix}", ""]
        if models:
            for model in models:
                lines.append(f"- {model}")
        else:
            lines.append("No pydantic models discovered.")
        output = output_dir / f"{prefix.replace('.', '_')}_schemas.md"
        content = "\n".join(lines) + "\n"
        targets.append(
            build_result(
                generator_id="schema_reference",
                repo_root=repo_root,
                target_path=output,
                source_paths=[Path(f"src/{prefix.replace('.', '/')}")],
                content=content,
                marker=MARKER,
            )
        )
    return targets
