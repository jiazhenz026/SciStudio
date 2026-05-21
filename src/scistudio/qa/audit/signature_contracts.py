"""Extract ADR-042 expected signature facts from governed documents."""

from __future__ import annotations

import ast
import re
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from scistudio.qa.audit._util import (
    git_tracked_relative_paths,
    is_tracked_path,
    load_adr_frontmatter,
    load_spec_frontmatter,
    normalise_path,
)
from scistudio.qa.schemas.facts import Fact
from scistudio.qa.schemas.signatures import ExpectedCliCommand, ExpectedModelField, ExpectedParameter, ExpectedSignature

_FENCE_RE = re.compile(r"^```(?:python|py)\s*$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_EXIT_CODE_RE = re.compile(r"\b([0-9]{1,3})\b")


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


def _model_field_facts_from_class(
    node: ast.ClassDef,
    *,
    source_path: str,
    source_line: int,
    source_sha: str,
    owner: str | None,
    contracts_by_leaf: dict[str, str],
) -> list[Fact]:
    model_symbol = _qualify_subject(node.name, contracts_by_leaf)
    facts: list[Fact] = []
    for child in node.body:
        if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
            continue
        field = ExpectedModelField(
            model_symbol=model_symbol,
            field_name=child.target.id,
            annotation=_annotation(child.annotation) or "",
            default=_default(child.value),
            required=child.value is None,
            source_spec=source_path,
            source_line=source_line + child.lineno - 1,
        )
        facts.append(
            Fact(
                id=f"expected-model-field:{field.source_spec}:{field.source_line}:{field.model_symbol}.{field.field_name}",
                kind="expected-model-field",
                source=field.source_spec,
                subject=f"{field.model_symbol}.{field.field_name}",
                value=field.model_dump(mode="json"),
                owner=owner,
                source_sha=source_sha,
                confidence="normative",
                stability="stable",
            )
        )
    return facts


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
    model_field_facts: list[Fact] = []
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
            model_field_facts.extend(
                _model_field_facts_from_class(
                    node,
                    source_path=source_path,
                    source_line=source_line,
                    source_sha=source_sha,
                    owner=owner,
                    contracts_by_leaf=contracts_by_leaf,
                )
            )
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
    ] + model_field_facts


def _body_start_line(path: Path) -> int:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n") and not raw.startswith("---\r\n"):
        return 1
    marker = "\r\n---\r\n" if raw.startswith("---\r\n") else "\n---\n"
    start = 5 if marker.startswith("\r\n") else 4
    end = raw.find(marker, start)
    if end < 0:
        return 1
    return raw[: end + len(marker)].count("\n") + 1


def _signature_section_body(body: str, *, body_start_line: int) -> tuple[str, int]:
    lines = body.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("### ") and "Signature-Level Contracts" in line:
            start = index + 1
            break
    if start is None:
        return "", 0
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## ") or lines[index].startswith("### "):
            end = index
            break
    return "\n".join(lines[start:end]), body_start_line + start


def _unique_contracts_by_leaf(contracts: list[str]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for contract in contracts:
        grouped.setdefault(contract.rsplit(".", 1)[-1], []).append(contract)
    return {leaf: values[0] for leaf, values in grouped.items() if len(values) == 1}


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _cli_command_facts_from_section(
    section: str,
    *,
    section_start_line: int,
    source_path: str,
    source_sha: str,
    owner: str | None,
) -> list[Fact]:
    facts: list[Fact] = []
    headers: list[str] | None = None
    for line_no, line in enumerate(section.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            headers = None
            continue
        cells = _table_cells(stripped)
        lowered = [cell.lower() for cell in cells]
        if any("command" in cell for cell in lowered):
            headers = lowered
            continue
        if headers is None or set(stripped.replace("|", "").strip()) <= {"-", ":"}:
            continue
        command_index = next((idx for idx, header in enumerate(headers) if "command" in header), None)
        if command_index is None or command_index >= len(cells):
            continue
        command_match = _BACKTICK_RE.search(cells[command_index])
        if command_match is None:
            continue
        try:
            command = shlex.split(command_match.group(1), posix=False)
        except ValueError:
            command = command_match.group(1).split()
        exit_codes: dict[int, str] = {}
        for idx, header in enumerate(headers):
            if idx >= len(cells) or "exit" not in header:
                continue
            for match in _EXIT_CODE_RE.finditer(cells[idx]):
                exit_codes[int(match.group(1))] = cells[idx]
        cli = ExpectedCliCommand(
            command=command,
            expected_exit_codes=exit_codes,
            source_spec=source_path,
            source_line=section_start_line + line_no - 1,
        )
        subject = " ".join(cli.command)
        facts.append(
            Fact(
                id=f"expected-cli-command:{source_path}:{cli.source_line}:{subject}",
                kind="expected-cli-command",
                source=source_path,
                subject=subject,
                value=cli.model_dump(mode="json"),
                owner=owner,
                source_sha=source_sha,
                confidence="normative",
                stability="stable",
            )
        )
    return facts


def _signature_contract_facts_from_document(
    path: Path,
    *,
    body: str,
    contracts: list[str],
    owner: str | None,
    repo_root: Path,
    source_sha: str,
) -> list[Fact]:
    contracts_by_leaf = _unique_contracts_by_leaf(contracts)
    section, section_start_line = _signature_section_body(body, body_start_line=_body_start_line(path))
    if not section:
        return []
    source_path = normalise_path(path.relative_to(repo_root))
    facts = _cli_command_facts_from_section(
        section,
        section_start_line=section_start_line,
        source_path=source_path,
        source_sha=source_sha,
        owner=owner,
    )
    section_lines = section.splitlines()
    in_fence = False
    fence_start = 0
    buffer: list[str] = []
    for index, line in enumerate(section_lines, start=1):
        if not in_fence and _FENCE_RE.match(line.strip()):
            in_fence = True
            fence_start = section_start_line + index
            buffer = []
            continue
        if in_fence and line.strip() == "```":
            facts.extend(
                _signature_facts_from_code(
                    "\n".join(buffer),
                    source_path=source_path,
                    source_line=fence_start,
                    source_sha=source_sha,
                    owner=owner,
                    contracts_by_leaf=contracts_by_leaf,
                )
            )
            in_fence = False
            continue
        if in_fence:
            buffer.append(line)
    return facts


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
        facts.extend(
            _signature_contract_facts_from_document(
                path,
                body=body,
                contracts=spec.governs.contracts,
                owner=spec.owners[0] if spec.owners else None,
                repo_root=repo_root,
                source_sha=source_sha,
            )
        )
    return facts


def extract_adr_signature_contracts(
    adr_paths: Sequence[Path],
    *,
    repo_root: Path,
    source_sha: str,
) -> list[Fact]:
    """Extract expected signature facts from ADR Signature-Level Contracts sections."""

    facts: list[Fact] = []
    tracked_paths = git_tracked_relative_paths(repo_root)
    for path in sorted(adr_paths):
        if not is_tracked_path(path, repo_root, tracked_paths):
            continue
        adr, body, findings = load_adr_frontmatter(path)
        if adr is None or findings:
            continue
        if adr.status not in {"Accepted", "Proposed"}:
            continue
        facts.extend(
            _signature_contract_facts_from_document(
                path,
                body=body,
                contracts=adr.governs.contracts,
                owner=adr.owner,
                repo_root=repo_root,
                source_sha=source_sha,
            )
        )
    return facts


def extract_governed_signature_contracts(
    *,
    repo_root: Path,
    source_sha: str,
) -> list[Fact]:
    """Extract expected signature facts from active specs and ADRs."""

    return [
        *extract_signature_contracts(
            sorted((repo_root / "docs" / "specs").glob("*.md")),
            repo_root=repo_root,
            source_sha=source_sha,
        ),
        *extract_adr_signature_contracts(
            sorted((repo_root / "docs" / "adr").glob("ADR-*.md")),
            repo_root=repo_root,
            source_sha=source_sha,
        ),
    ]
