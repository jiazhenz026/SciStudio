"""ADR-042 fact generation helpers."""

from __future__ import annotations

import ast
import hashlib
import inspect
import re
import tomllib
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa._shared import AuditReport
from scieasy.qa.audit.frontmatter_lint import parse_markdown_document
from scieasy.qa.schemas.facts import Fact, FactKind, FactsRegistry, write_facts
from scieasy.qa.schemas.frontmatter import ADRFrontmatter, SpecFrontmatter
from scieasy.qa.schemas.signatures import (
    ExpectedCliCommand,
    ExpectedModelField,
    ExpectedSignature,
    ParameterSpec,
)


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _fact_id(kind: str, source: str, subject: str) -> str:
    raw = f"{kind}:{source}:{subject}"
    digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", f"{kind}:{subject}")[:120].strip("-")
    return f"{slug}:{digest}"


def _stable_generated_at(repo_root: Path) -> datetime:
    del repo_root
    return datetime.fromtimestamp(0, UTC)


def _source_tree_sha(repo_root: Path) -> str:
    hasher = hashlib.sha256()
    roots = [
        repo_root / "docs" / "adr",
        repo_root / "docs" / "specs",
        repo_root / "src" / "scieasy",
        repo_root / ".github" / "workflows",
    ]
    files = [
        repo_root / "pyproject.toml",
        repo_root / ".pre-commit-config.yaml",
        repo_root / "pyrightconfig.json",
        repo_root / "MAINTAINERS",
        repo_root / "docs" / "user" / "reference" / "generated-docs.yaml",
    ]
    for root in roots:
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    for path in sorted(set(files)):
        if not path.exists() or "__pycache__" in path.parts:
            continue
        rel = _repo_relative(path, repo_root)
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _make_fact(
    *,
    kind: FactKind,
    source: str,
    subject: str,
    value: Any,
    owner: str | None,
    generated_at: datetime,
    source_sha: str,
    confidence: str,
    stability: str = "stable",
) -> Fact:
    return Fact(
        id=_fact_id(kind, source, subject),
        kind=kind,
        source=source,
        subject=subject,
        value=value,
        owner=owner,
        generated_at=generated_at,
        source_sha=source_sha,
        confidence=confidence,  # type: ignore[arg-type]
        stability=stability,  # type: ignore[arg-type]
    )


def _markdown_frontmatter(path: Path, repo_root: Path) -> dict[str, Any]:
    doc = parse_markdown_document(path, repo_root=repo_root)
    return dict(doc.frontmatter)


def _extract_adr_spec_facts(repo_root: Path, generated_at: datetime, source_sha: str) -> list[Fact]:
    facts: list[Fact] = []
    for path in sorted((repo_root / "docs" / "adr").glob("ADR-*.md")):
        source = _repo_relative(path, repo_root)
        fm = _markdown_frontmatter(path, repo_root)
        try:
            adr = ADRFrontmatter.model_validate(fm)
        except Exception:
            continue
        facts.append(
            _make_fact(
                kind="adr",
                source=source,
                subject=f"ADR-{adr.adr:03d}",
                value=adr.model_dump(mode="json"),
                owner=adr.owner,
                generated_at=generated_at,
                source_sha=source_sha,
                confidence="normative",
            )
        )
        for module in adr.governs.modules:
            facts.append(
                _make_fact(
                    kind="symbol",
                    source=source,
                    subject=module,
                    value={"governed_by": f"ADR-{adr.adr:03d}", "surface": "module"},
                    owner=adr.owner,
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="normative",
                )
            )
        for contract in adr.governs.contracts:
            facts.append(
                _make_fact(
                    kind="symbol",
                    source=source,
                    subject=contract,
                    value={"governed_by": f"ADR-{adr.adr:03d}", "surface": "contract"},
                    owner=adr.owner,
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="normative",
                )
            )
        for file_path in adr.governs.files:
            facts.append(
                _make_fact(
                    kind="file",
                    source=source,
                    subject=file_path,
                    value={"governed_by": f"ADR-{adr.adr:03d}"},
                    owner=adr.owner,
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="normative",
                )
            )

    for path in sorted((repo_root / "docs" / "specs").glob("*.md")):
        source = _repo_relative(path, repo_root)
        fm = _markdown_frontmatter(path, repo_root)
        try:
            spec = SpecFrontmatter.model_validate(fm)
        except Exception:
            continue
        facts.append(
            _make_fact(
                kind="spec",
                source=source,
                subject=spec.spec_id,
                value=spec.model_dump(mode="json", by_alias=True),
                owner=", ".join(spec.owners),
                generated_at=generated_at,
                source_sha=source_sha,
                confidence="normative",
            )
        )
        for module in spec.governs.modules:
            facts.append(
                _make_fact(
                    kind="symbol",
                    source=source,
                    subject=module,
                    value={"governed_by": spec.spec_id, "surface": "module"},
                    owner=", ".join(spec.owners),
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="normative",
                )
            )
        for contract in spec.governs.contracts:
            facts.append(
                _make_fact(
                    kind="symbol",
                    source=source,
                    subject=contract,
                    value={"governed_by": spec.spec_id, "surface": "contract"},
                    owner=", ".join(spec.owners),
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="normative",
                )
            )
        for file_path in spec.governs.files:
            facts.append(
                _make_fact(
                    kind="file",
                    source=source,
                    subject=file_path,
                    value={"governed_by": spec.spec_id},
                    owner=", ".join(spec.owners),
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="normative",
                )
            )
    return facts


def _extract_entry_point_facts(repo_root: Path, generated_at: datetime, source_sha: str) -> list[Fact]:
    path = repo_root / "pyproject.toml"
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    entry_points = project.get("entry-points", {}) if isinstance(project, dict) else {}
    facts: list[Fact] = []
    if not isinstance(entry_points, dict):
        return facts
    for group, values in sorted(entry_points.items()):
        if not isinstance(values, dict):
            continue
        for name, target in sorted(values.items()):
            facts.append(
                _make_fact(
                    kind="entry-point",
                    source="pyproject.toml",
                    subject=f"{group}:{name}",
                    value={"target": target},
                    owner=None,
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="generated",
                )
            )
    return facts


def _extract_workflow_config_facts(repo_root: Path, generated_at: datetime, source_sha: str) -> list[Fact]:
    facts: list[Fact] = []
    for path in sorted((repo_root / ".github" / "workflows").glob("*.yml")) + sorted(
        (repo_root / ".github" / "workflows").glob("*.yaml")
    ):
        source = _repo_relative(path, repo_root)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        jobs = sorted((data.get("jobs") or {}).keys()) if isinstance(data, dict) else []
        facts.append(
            _make_fact(
                kind="workflow",
                source=source,
                subject=source,
                value={"jobs": jobs},
                owner=None,
                generated_at=generated_at,
                source_sha=source_sha,
                confidence="normative",
            )
        )
    for config_path in ["pyproject.toml", ".pre-commit-config.yaml", "pyrightconfig.json"]:
        if (repo_root / config_path).exists():
            facts.append(
                _make_fact(
                    kind="file",
                    source=config_path,
                    subject=config_path,
                    value={"tool_config": True},
                    owner=None,
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="normative",
                )
            )
    return facts


def _extract_symbol_facts(repo_root: Path, generated_at: datetime, source_sha: str) -> list[Fact]:
    facts: list[Fact] = []
    src = repo_root / "src"
    for path in sorted((src / "scieasy").rglob("*.py")) if (src / "scieasy").exists() else []:
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        module = "scieasy." + path.relative_to(src / "scieasy").with_suffix("").as_posix().replace("/", ".")
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith(
                "_"
            ):
                subject = f"{module}.{node.name}"
                facts.append(
                    _make_fact(
                        kind="symbol",
                        source=_repo_relative(path, repo_root),
                        subject=subject,
                        value={"kind": node.__class__.__name__, "line": node.lineno},
                        owner=None,
                        generated_at=generated_at,
                        source_sha=source_sha,
                        confidence="generated",
                    )
                )
    return facts


def _signature_kind_from_name(name: str) -> str:
    if name and name[0].isupper():
        return "class"
    return "function"


def _parameter_kind(parameter: inspect.Parameter) -> str:
    mapping = {
        inspect.Parameter.POSITIONAL_ONLY: "positional-only",
        inspect.Parameter.POSITIONAL_OR_KEYWORD: "positional-or-keyword",
        inspect.Parameter.VAR_POSITIONAL: "var-positional",
        inspect.Parameter.KEYWORD_ONLY: "keyword-only",
        inspect.Parameter.VAR_KEYWORD: "var-keyword",
    }
    return mapping[parameter.kind]


def _annotation_to_str(value: Any) -> str | None:
    if value is inspect.Signature.empty:
        return None
    if isinstance(value, str):
        return value
    return getattr(value, "__name__", str(value).replace("typing.", ""))


def _default_to_str(value: Any) -> str | None:
    if value is inspect.Signature.empty:
        return None
    return repr(value)


def _expected_from_ast(
    node: ast.AST,
    *,
    symbol_prefix: str,
    source_spec: str,
) -> ExpectedSignature | None:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return None
    symbol = f"{symbol_prefix}.{node.name}" if symbol_prefix else node.name
    if isinstance(node, ast.ClassDef):
        return ExpectedSignature(symbol=symbol, kind="class", source_spec=source_spec, source_line=node.lineno)
    parameters: list[ParameterSpec] = []
    defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)
    for arg, default in zip(node.args.args, defaults, strict=False):
        if arg.arg in {"self", "cls"}:
            continue
        parameters.append(
            ParameterSpec(
                name=arg.arg,
                kind="positional-or-keyword",
                annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                default=ast.unparse(default) if default else None,
                required=default is None,
            )
        )
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False):
        parameters.append(
            ParameterSpec(
                name=arg.arg,
                kind="keyword-only",
                annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                default=ast.unparse(default) if default else None,
                required=default is None,
            )
        )
    return ExpectedSignature(
        symbol=symbol,
        kind="function",
        parameters=parameters,
        return_annotation=ast.unparse(node.returns) if node.returns else None,
        source_spec=source_spec,
        source_line=node.lineno,
    )


def _iter_fenced_blocks(text: str) -> Iterable[tuple[str, int]]:
    lines = text.splitlines()
    in_block = False
    block: list[str] = []
    start_line = 0
    language = ""
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_block:
                language = stripped[3:].strip().lower()
                if language in {"python", "py"}:
                    in_block = True
                    block = []
                    start_line = index + 1
                continue
            yield "\n".join(block), start_line
            in_block = False
            language = ""
            continue
        if in_block:
            block.append(line)


def extract_signature_contracts(spec_paths: Sequence[Path], *, repo_root: Path) -> list[Fact]:
    generated_at = _stable_generated_at(repo_root)
    source_sha = _source_tree_sha(repo_root)
    facts: list[Fact] = []
    for spec_path in spec_paths:
        source = _repo_relative(spec_path, repo_root)
        text = spec_path.read_text(encoding="utf-8")
        current_prefix = ""
        for line in text.splitlines():
            match = re.search(r"#\s*(?:module|symbol-prefix):\s*([\w.]+)", line)
            if match:
                current_prefix = match.group(1)
        for block, start_line in _iter_fenced_blocks(text):
            try:
                tree = ast.parse(block)
            except SyntaxError:
                continue
            for node in tree.body:
                expected = _expected_from_ast(node, symbol_prefix=current_prefix, source_spec=source)
                if expected is not None:
                    facts.append(
                        _make_fact(
                            kind="expected-signature",
                            source=source,
                            subject=expected.symbol,
                            value={
                                **expected.model_dump(mode="json"),
                                "source_line": expected.source_line + start_line - 1,
                            },
                            owner=None,
                            generated_at=generated_at,
                            source_sha=source_sha,
                            confidence="normative",
                        )
                    )
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            model_symbol = f"{current_prefix}.{node.name}" if current_prefix else node.name
                            field = ExpectedModelField(
                                model_symbol=model_symbol,
                                field_name=item.target.id,
                                annotation=ast.unparse(item.annotation),
                                default=ast.unparse(item.value) if item.value is not None else None,
                                required=item.value is None,
                                source_spec=source,
                                source_line=item.lineno + start_line - 1,
                            )
                            facts.append(
                                _make_fact(
                                    kind="expected-model-field",
                                    source=source,
                                    subject=f"{field.model_symbol}.{field.field_name}",
                                    value=field.model_dump(mode="json"),
                                    owner=None,
                                    generated_at=generated_at,
                                    source_sha=source_sha,
                                    confidence="normative",
                                )
                            )
        for match in re.finditer(r"python\s+-m\s+([\w.]+)([^\n`]*)", text):
            command = ["python", "-m", match.group(1), *match.group(2).strip().split()]
            expected_cli = ExpectedCliCommand(
                command=command,
                module=match.group(1),
                source_spec=source,
                source_line=text[: match.start()].count("\n") + 1,
            )
            facts.append(
                _make_fact(
                    kind="expected-cli-command",
                    source=source,
                    subject=" ".join(command),
                    value=expected_cli.model_dump(mode="json"),
                    owner=None,
                    generated_at=generated_at,
                    source_sha=source_sha,
                    confidence="normative",
                )
            )
    return facts


def _extract_generated_doc_facts(repo_root: Path, generated_at: datetime, source_sha: str) -> list[Fact]:
    manifest_path = repo_root / "docs" / "user" / "reference" / "generated-docs.yaml"
    if not manifest_path.exists():
        return []
    try:
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    entries = loaded.get("entries", []) if isinstance(loaded, dict) else []
    facts: list[Fact] = []
    iterable_entries = entries if isinstance(entries, list) else []
    for entry in iterable_entries:
        if not isinstance(entry, dict):
            continue
        target = str(entry.get("target_path", ""))
        if not target:
            continue
        facts.append(
            _make_fact(
                kind="generated-doc",
                source=_repo_relative(manifest_path, repo_root),
                subject=target,
                value=entry,
                owner=None,
                generated_at=generated_at,
                source_sha=source_sha,
                confidence="generated",
            )
        )
    return facts


def generate_facts(
    repo_root: Path,
    *,
    source_sha: str | None = None,
    include_observed: bool = False,
    include_signature_contracts: bool = True,
) -> FactsRegistry:
    del include_observed
    repo_root = repo_root.resolve()
    resolved_sha = source_sha or _source_tree_sha(repo_root)
    generated_at = _stable_generated_at(repo_root)
    facts: list[Fact] = []
    facts.extend(_extract_adr_spec_facts(repo_root, generated_at, resolved_sha))
    facts.extend(_extract_entry_point_facts(repo_root, generated_at, resolved_sha))
    facts.extend(_extract_workflow_config_facts(repo_root, generated_at, resolved_sha))
    facts.extend(_extract_symbol_facts(repo_root, generated_at, resolved_sha))
    facts.extend(_extract_generated_doc_facts(repo_root, generated_at, resolved_sha))
    if include_signature_contracts:
        spec_paths = sorted((repo_root / "docs" / "specs").glob("*.md"))
        facts.extend(extract_signature_contracts(spec_paths, repo_root=repo_root))

    unique = {fact.id: fact for fact in facts}
    return FactsRegistry(
        generated_at=generated_at,
        source_sha=resolved_sha,
        facts=sorted(unique.values(), key=lambda fact: (fact.kind, fact.subject, fact.source, fact.id)),
    )


def check_generated_facts(
    repo_root: Path,
    *,
    facts_path: Path = Path("docs/facts/generated.yaml"),
    update: bool = False,
) -> AuditReport:
    repo_root = repo_root.resolve()
    target = facts_path if facts_path.is_absolute() else repo_root / facts_path
    registry = generate_facts(repo_root)
    if update:
        write_facts(registry, target)
        return build_report(tool="generate_facts", repo_root=repo_root, findings=[])

    findings = []
    if not target.exists():
        findings.append(
            build_finding(
                finding_id="facts-missing",
                tool="generate_facts",
                finding_class="phantom-reference",
                severity="error",
                message=f"Generated facts file is missing: {_repo_relative(target, repo_root)}",
                path=target,
                remediation="Run scripts/audit/generate_facts.py --write",
            )
        )
    else:
        expected = yaml.safe_dump(registry.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
        actual = target.read_text(encoding="utf-8")
        if actual != expected:
            findings.append(
                build_finding(
                    finding_id="facts-stale",
                    tool="generate_facts",
                    finding_class="behavior-drift",
                    severity="error",
                    message="Generated facts are stale.",
                    path=target,
                    remediation="Run scripts/audit/generate_facts.py --write",
                )
            )
    return build_report(tool="generate_facts", repo_root=repo_root, findings=findings)


__all__ = [
    "check_generated_facts",
    "extract_signature_contracts",
    "generate_facts",
    "write_facts",
]
