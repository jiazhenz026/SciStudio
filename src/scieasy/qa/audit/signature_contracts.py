"""Extract ADR-042 expected signature facts from structured spec sections."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from scieasy.qa.audit._util import load_spec_frontmatter, normalise_path
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


def _signature_from_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, source_path: str, line: int
) -> ExpectedSignature:
    return ExpectedSignature(
        subject=node.name,
        kind="function",
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
                    subject=node.name,
                    kind="class",
                    source_path=source_path,
                    line=source_line + node.lineno - 1,
                )
            )
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    signature = _signature_from_function(child, source_path, source_line)
                    signature.subject = f"{node.name}.{child.name}"
                    signatures.append(signature)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            signatures.append(_signature_from_function(node, source_path, source_line))

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


def extract_signature_contracts(
    spec_paths: list[Path],
    *,
    repo_root: Path,
    source_sha: str,
) -> list[Fact]:
    """Extract expected signature facts from spec code blocks."""

    facts: list[Fact] = []
    for path in sorted(spec_paths):
        spec, body, findings = load_spec_frontmatter(path)
        if spec is None or findings:
            continue
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
                    )
                )
                in_fence = False
                continue
            if in_fence:
                buffer.append(line)
    return facts
