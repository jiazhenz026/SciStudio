"""Extract ADR-042 expected signature facts from structured spec sections."""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from scieasy.qa.audit._util import git_tracked_relative_paths, is_tracked_path, load_spec_frontmatter, normalise_path
from scieasy.qa.schemas.facts import Fact
from scieasy.qa.schemas.signatures import ExpectedParameter, ExpectedSignature

_FENCE_RE = re.compile(r"^```(?:python|py)\s*$")


def _annotation(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _default(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _parameters(args: ast.arguments) -> list[ExpectedParameter]:
    positional = [*args.posonlyargs, *args.args]
    positional_defaults: list[ast.AST | None] = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    parameters: list[ExpectedParameter] = []
    for arg, default in zip(positional, positional_defaults, strict=True):
        parameters.append(
            ExpectedParameter(
                name=arg.arg,
                kind="positional or keyword",
                annotation=_annotation(arg.annotation),
                default=_default(default),
                required=default is None,
            )
        )
    if args.vararg is not None:
        parameters.append(
            ExpectedParameter(
                name=args.vararg.arg,
                kind="variadic positional",
                annotation=_annotation(args.vararg.annotation),
                required=False,
            )
        )
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        parameters.append(
            ExpectedParameter(
                name=arg.arg,
                kind="keyword-only",
                annotation=_annotation(arg.annotation),
                default=_default(default),
                required=default is None,
            )
        )
    if args.kwarg is not None:
        parameters.append(
            ExpectedParameter(
                name=args.kwarg.arg,
                kind="variadic keyword",
                annotation=_annotation(args.kwarg.annotation),
                required=False,
            )
        )
    return parameters


def _is_property(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(decorator, ast.Name) and decorator.id == "property" for decorator in node.decorator_list)


def _qualify_subject(subject: str, contracts_by_leaf: dict[str, str]) -> str:
    parts = subject.split(".")
    leaf = parts[-1]
    qualified = contracts_by_leaf.get(leaf)
    if qualified is None:
        return subject
    if len(parts) == 1:
        return qualified
    return ".".join([*qualified.split(".")[:-1], *parts])


def _signature_from_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_path: str,
    line: int,
    contracts_by_leaf: dict[str, str],
) -> ExpectedSignature:
    kind: Literal["function", "attribute"] = "attribute" if _is_property(node) else "function"
    return ExpectedSignature(
        subject=_qualify_subject(node.name, contracts_by_leaf),
        kind=kind,
        parameters=_parameters(node.args),
        return_annotation=_annotation(node.returns),
        source_path=source_path,
        line=line + node.lineno - 1,
    )


def _signature_facts_from_code(
    code: str,
    *,
    source_path: str,
    source_line: int,
    source_sha: str,
    owner: str | None,
    contracts_by_leaf: dict[str, str],
) -> list[Fact]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    signatures: list[ExpectedSignature] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            signatures.append(
                ExpectedSignature(
                    subject=_qualify_subject(node.name, contracts_by_leaf),
                    kind="class",
                    source_path=source_path,
                    line=source_line + node.lineno - 1,
                )
            )
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    signature = _signature_from_function(child, source_path, source_line, contracts_by_leaf)
                    signature.subject = f"{_qualify_subject(node.name, contracts_by_leaf)}.{child.name}"
                    signatures.append(signature)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            signatures.append(_signature_from_function(node, source_path, source_line, contracts_by_leaf))

    return [
        Fact(
            id=f"expected-signature:{signature.source_path}:{signature.line}:{signature.subject}",
            kind="expected-signature",
            source=signature.source_path,
            subject=signature.subject,
            value=signature.model_dump(mode="json"),
            owner=owner,
            source_sha=source_sha,
            confidence="normative",
            stability="stable",
        )
        for signature in signatures
    ]


def _signature_section_body(body: str) -> str:
    lines = body.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("### ") and "Signature-Level Contracts" in line:
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _unique_contracts_by_leaf(contracts: list[str]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for contract in contracts:
        grouped.setdefault(contract.rsplit(".", 1)[-1], []).append(contract)
    return {leaf: values[0] for leaf, values in grouped.items() if len(values) == 1}


def extract_signature_contracts(
    spec_paths: Sequence[Path],
    *,
    repo_root: Path,
    source_sha: str,
) -> list[Fact]:
    """Extract expected signature facts from spec code blocks."""

    facts: list[Fact] = []
    tracked_paths = git_tracked_relative_paths(repo_root)
    for path in sorted(spec_paths):
        if not is_tracked_path(path, repo_root, tracked_paths):
            continue
        spec, body, findings = load_spec_frontmatter(path)
        if spec is None or findings:
            continue
        if spec.status not in {"Planned", "Implemented"}:
            continue
        contracts_by_leaf = _unique_contracts_by_leaf(spec.governs.contracts)
        section = _signature_section_body(body)
        if not section:
            continue
        section_lines = section.splitlines()
        in_fence = False
        fence_start = 0
        buffer: list[str] = []
        for index, line in enumerate(section_lines, start=1):
            if not in_fence and _FENCE_RE.match(line.strip()):
                in_fence = True
                fence_start = index + 1
                buffer = []
                continue
            if in_fence and line.strip() == "```":
                source_path = normalise_path(path.relative_to(repo_root))
                facts.extend(
                    _signature_facts_from_code(
                        "\n".join(buffer),
                        source_path=source_path,
                        source_line=fence_start,
                        source_sha=source_sha,
                        owner=spec.owners[0] if spec.owners else None,
                        contracts_by_leaf=contracts_by_leaf,
                    )
                )
                in_fence = False
                continue
            if in_fence:
                buffer.append(line)
    return facts
