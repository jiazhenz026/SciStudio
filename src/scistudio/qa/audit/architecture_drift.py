"""Audit architecture-document references against generated repository facts."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from scistudio.qa.audit._util import normalise_path
from scistudio.qa.schemas.facts import Fact, FactsRegistry
from scistudio.qa.schemas.report import AuditReport, AuditStatus, DriftClass, Finding, Severity

DEFAULT_ARCHITECTURE_PATH = Path("docs/architecture/ARCHITECTURE.md")

_FENCE_OPEN_RE = re.compile(r"^```\s*([A-Za-z0-9_.+-]*)?.*$")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_DOTTED_SCISTUDIO_RE = re.compile(r"\bscistudio(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_SRC_PATH_RE = re.compile(r"\bsrc/scistudio/[A-Za-z0-9_./-]+(?:\.py)?\b")
_PYTHON_CALLABLE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*\(")
_NON_NORMATIVE_MARKERS = ("non-normative", "illustrative", "example only", "pseudocode")
_ELIGIBLE_FENCE_LANGS = {"", "python", "py", "bash", "shell", "sh", "toml", "yaml", "yml", "json"}
_GENERIC_BARE_NAMES = {
    "Any",
    "BaseModel",
    "ClassVar",
    "Enum",
    "False",
    "Iterator",
    "None",
    "Path",
    "Self",
    "True",
}
_REPO_SYMBOL_SUFFIXES = (
    "Block",
    "Data",
    "Event",
    "Handle",
    "Harness",
    "Manager",
    "Model",
    "Object",
    "Policy",
    "Port",
    "Record",
    "Reference",
    "Registry",
    "Runner",
    "Service",
    "Store",
    "Workflow",
)


@dataclass(frozen=True)
class _Fence:
    lang: str
    start_line: int
    end_line: int
    code: str
    context: str


def _symbol_facts(facts: FactsRegistry) -> dict[str, Fact]:
    return {fact.subject: fact for fact in facts.find(kind="symbol")}


def _symbols_by_leaf(symbols: Mapping[str, Fact]) -> dict[str, list[Fact]]:
    grouped: dict[str, list[Fact]] = {}
    for subject, fact in symbols.items():
        grouped.setdefault(subject.rsplit(".", 1)[-1], []).append(fact)
    return grouped


def _value_kind(fact: Fact | None) -> str | None:
    if fact is None or not isinstance(fact.value, Mapping):
        return None
    kind = fact.value.get("kind")
    return kind if isinstance(kind, str) else None


def _normalize(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "None"}:
        return None
    return text.strip("'\"")


def _annotation(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _parameters(args: ast.arguments) -> list[tuple[str, str | None, bool]]:
    positional = [*args.posonlyargs, *args.args]
    positional_defaults: list[ast.AST | None] = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    parameters: list[tuple[str, str | None, bool]] = []
    for arg, default in zip(positional, positional_defaults, strict=True):
        if arg.arg not in {"self", "cls"}:
            parameters.append((arg.arg, _annotation(arg.annotation), default is None))
    if args.vararg is not None:
        parameters.append((args.vararg.arg, _annotation(args.vararg.annotation), False))
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        parameters.append((arg.arg, _annotation(arg.annotation), default is None))
    if args.kwarg is not None:
        parameters.append((args.kwarg.arg, _annotation(args.kwarg.annotation), False))
    return parameters


def _fact_parameters(fact: Fact) -> list[tuple[str, str | None, bool]]:
    value = fact.value if isinstance(fact.value, Mapping) else {}
    raw_parameters = value.get("parameters", [])
    if not isinstance(raw_parameters, list):
        return []
    parameters: list[tuple[str, str | None, bool]] = []
    for parameter in raw_parameters:
        if not isinstance(parameter, Mapping):
            continue
        name = str(parameter.get("name", ""))
        if name in {"self", "cls"}:
            continue
        parameters.append((name, _normalize(parameter.get("annotation")), bool(parameter.get("required", True))))
    return parameters


def _is_non_normative(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _NON_NORMATIVE_MARKERS)


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _finding(
    rule_id: str,
    file: Path,
    message: str,
    *,
    line: int | None = None,
    symbol: str | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        file=normalise_path(file),
        line=line,
        message=message,
        symbol=symbol,
        drift_class=DriftClass.SIGNATURE_DRIFT
        if "signature" in rule_id or "parameters" in rule_id or "return" in rule_id
        else DriftClass.PHANTOM_REFERENCE,
    )


def _extract_fences(text: str) -> tuple[list[_Fence], str]:
    lines = text.splitlines()
    fences: list[_Fence] = []
    prose_lines: list[str] = []
    in_fence = False
    lang = ""
    fence_start = 0
    buffer: list[str] = []
    context_lines: list[str] = []
    for index, line in enumerate(lines, start=1):
        if not in_fence:
            match = _FENCE_OPEN_RE.match(line.strip())
            if match:
                in_fence = True
                lang = (match.group(1) or "").lower()
                fence_start = index + 1
                buffer = []
                context_lines = lines[max(0, index - 4) : index]
                continue
            prose_lines.append(line)
            continue
        if line.strip() == "```":
            fences.append(
                _Fence(
                    lang=lang,
                    start_line=fence_start,
                    end_line=index,
                    code="\n".join(buffer),
                    context="\n".join(context_lines),
                )
            )
            in_fence = False
            continue
        buffer.append(line)
    return fences, "\n".join(prose_lines)


def _is_repo_path_reference(token: str) -> bool:
    return token.startswith("src/scistudio/")


def _is_dotted_repo_reference(token: str) -> bool:
    return bool(_DOTTED_SCISTUDIO_RE.fullmatch(token)) and len(token.split(".")) >= 3


def _is_bare_symbol_reference(token: str) -> bool:
    if token in _GENERIC_BARE_NAMES:
        return False
    if "." in token or "/" in token or " " in token:
        return False
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
        return False
    return (
        token.endswith(_REPO_SYMBOL_SUFFIXES)
        or token.endswith(("_block", "_runner", "_registry"))
        or token.startswith(("get_", "load_", "save_", "run_"))
    )


def _path_exists(repo_root: Path, token: str) -> bool:
    path = repo_root / token
    if path.exists():
        return True
    if path.suffix:
        return False
    return path.with_suffix(".py").exists() or (path / "__init__.py").exists()


def _resolve_module_or_symbol(token: str, symbols: Mapping[str, Fact]) -> Fact | None:
    if token in symbols:
        return symbols[token]
    module_token = token.removesuffix(".py").replace("/", ".")
    if module_token.startswith("src."):
        module_token = module_token.removeprefix("src.")
    return symbols.get(module_token)


def _resolve_bare_symbol(token: str, by_leaf: Mapping[str, list[Fact]]) -> tuple[Fact | None, str | None]:
    matches = by_leaf.get(token, [])
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, "ambiguous"
    return None, "missing"


def _check_reference(
    token: str,
    *,
    repo_root: Path,
    architecture_file: Path,
    line: int,
    symbols: Mapping[str, Fact],
    by_leaf: Mapping[str, list[Fact]],
) -> list[Finding]:
    stripped = token.strip().strip(".,:;()[]{}")
    if not stripped:
        return []
    if _is_repo_path_reference(stripped):
        if _path_exists(repo_root, stripped):
            return []
        return [
            _finding(
                "architecture-drift.missing-module-path",
                architecture_file,
                f"architecture document references missing repository path: {stripped}",
                line=line,
                symbol=stripped,
            )
        ]
    if _is_dotted_repo_reference(stripped):
        if _resolve_module_or_symbol(stripped, symbols) is not None:
            return []
        return [
            _finding(
                "architecture-drift.missing-dotted-reference",
                architecture_file,
                f"architecture document references missing repository symbol or module: {stripped}",
                line=line,
                symbol=stripped,
            )
        ]
    if _is_bare_symbol_reference(stripped):
        _, resolution = _resolve_bare_symbol(stripped, by_leaf)
        if resolution is None:
            return []
        return [
            _finding(
                f"architecture-drift.{resolution}-bare-symbol",
                architecture_file,
                f"architecture document references {resolution} repository symbol name: {stripped}",
                line=line,
                symbol=stripped,
            )
        ]
    return []


def _iter_prose_references(prose: str) -> Iterable[tuple[str, int]]:
    for match in _BACKTICK_RE.finditer(prose):
        yield match.group(1), _line_for_offset(prose, match.start())
    for regex in (_SRC_PATH_RE, _DOTTED_SCISTUDIO_RE):
        for match in regex.finditer(prose):
            yield match.group(0), _line_for_offset(prose, match.start())


def _expected_subject(name: str, by_leaf: Mapping[str, list[Fact]]) -> tuple[str | None, str | None]:
    fact, resolution = _resolve_bare_symbol(name, by_leaf)
    return (fact.subject, None) if fact is not None else (None, resolution)


def _compare_callable_signature(
    expected_subject: str,
    expected_parameters: list[tuple[str, str | None, bool]],
    expected_return: str | None,
    *,
    architecture_file: Path,
    line: int,
    symbols: Mapping[str, Fact],
) -> list[Finding]:
    actual = symbols.get(expected_subject)
    if actual is None:
        return [
            _finding(
                "architecture-drift.missing-signature-symbol",
                architecture_file,
                f"architecture code block defines missing repository callable: {expected_subject}",
                line=line,
                symbol=expected_subject,
            )
        ]
    findings: list[Finding] = []
    actual_parameters = _fact_parameters(actual)
    if expected_parameters != actual_parameters:
        findings.append(
            _finding(
                "architecture-drift.parameters-mismatch",
                architecture_file,
                f"signature parameters differ for {expected_subject}; expected {expected_parameters}, actual {actual_parameters}",
                line=line,
                symbol=expected_subject,
            )
        )
    actual_value = actual.value if isinstance(actual.value, Mapping) else {}
    actual_return = _normalize(actual_value.get("return_annotation"))
    if _normalize(expected_return) != actual_return:
        findings.append(
            _finding(
                "architecture-drift.return-mismatch",
                architecture_file,
                f"return annotation differs for {expected_subject}; expected {_normalize(expected_return)}, actual {actual_return}",
                line=line,
                symbol=expected_subject,
            )
        )
    return findings


def _check_python_imports(
    tree: ast.Module,
    *,
    architecture_file: Path,
    source_line: int,
    symbols: Mapping[str, Fact],
) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if not name.startswith("scistudio."):
                    continue
                if _resolve_module_or_symbol(name, symbols) is None:
                    findings.append(
                        _finding(
                            "architecture-drift.missing-import-module",
                            architecture_file,
                            f"architecture code block imports missing repository module: {name}",
                            line=source_line + node.lineno - 1,
                            symbol=name,
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not module.startswith("scistudio."):
                continue
            if _resolve_module_or_symbol(module, symbols) is None:
                findings.append(
                    _finding(
                        "architecture-drift.missing-import-module",
                        architecture_file,
                        f"architecture code block imports from missing repository module: {module}",
                        line=source_line + node.lineno - 1,
                        symbol=module,
                    )
                )
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                subject = f"{module}.{alias.name}"
                if subject not in symbols:
                    findings.append(
                        _finding(
                            "architecture-drift.missing-import-symbol",
                            architecture_file,
                            f"architecture code block imports missing repository symbol: {subject}",
                            line=source_line + node.lineno - 1,
                            symbol=subject,
                        )
                    )
    return findings


def _check_python_block(
    fence: _Fence,
    *,
    architecture_file: Path,
    symbols: Mapping[str, Fact],
    by_leaf: Mapping[str, list[Fact]],
) -> list[Finding]:
    try:
        tree = ast.parse(fence.code)
    except SyntaxError:
        return []
    findings = _check_python_imports(
        tree,
        architecture_file=architecture_file,
        source_line=fence.start_line,
        symbols=symbols,
    )
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            subject, resolution = _expected_subject(node.name, by_leaf)
            line = fence.start_line + node.lineno - 1
            if subject is None:
                findings.append(
                    _finding(
                        f"architecture-drift.{resolution}-class",
                        architecture_file,
                        f"architecture code block defines {resolution} repository class: {node.name}",
                        line=line,
                        symbol=node.name,
                    )
                )
                continue
            if _value_kind(symbols.get(subject)) != "class":
                findings.append(
                    _finding(
                        "architecture-drift.kind-mismatch",
                        architecture_file,
                        f"architecture code block expects class but repository fact is {_value_kind(symbols.get(subject))}: {subject}",
                        line=line,
                        symbol=subject,
                    )
                )
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    method_subject = f"{subject}.{child.name}"
                    findings.extend(
                        _compare_callable_signature(
                            method_subject,
                            _parameters(child.args),
                            _annotation(child.returns),
                            architecture_file=architecture_file,
                            line=fence.start_line + child.lineno - 1,
                            symbols=symbols,
                        )
                    )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            subject, resolution = _expected_subject(node.name, by_leaf)
            line = fence.start_line + node.lineno - 1
            if subject is None:
                findings.append(
                    _finding(
                        f"architecture-drift.{resolution}-function",
                        architecture_file,
                        f"architecture code block defines {resolution} repository function: {node.name}",
                        line=line,
                        symbol=node.name,
                    )
                )
                continue
            findings.extend(
                _compare_callable_signature(
                    subject,
                    _parameters(node.args),
                    _annotation(node.returns),
                    architecture_file=architecture_file,
                    line=line,
                    symbols=symbols,
                )
            )
    return findings


def _check_text_references(
    text: str,
    *,
    repo_root: Path,
    architecture_file: Path,
    line_offset: int,
    symbols: Mapping[str, Fact],
    by_leaf: Mapping[str, list[Fact]],
) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line_text in enumerate(text.splitlines(), start=line_offset):
        if _is_non_normative(line_text):
            continue
        for token, _ in _iter_prose_references(line_text):
            findings.extend(
                _check_reference(
                    token,
                    repo_root=repo_root,
                    architecture_file=architecture_file,
                    line=line_number,
                    symbols=symbols,
                    by_leaf=by_leaf,
                )
            )
        for match in _PYTHON_CALLABLE_RE.finditer(line_text.strip()):
            name = match.group(1)
            findings.extend(
                _check_reference(
                    name,
                    repo_root=repo_root,
                    architecture_file=architecture_file,
                    line=line_number,
                    symbols=symbols,
                    by_leaf=by_leaf,
                )
            )
    return findings


def check(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    architecture_path: Path = DEFAULT_ARCHITECTURE_PATH,
) -> AuditReport:
    """Validate the architecture document against generated repository facts."""

    root = repo_root.resolve()
    path = architecture_path if architecture_path.is_absolute() else root / architecture_path
    display_path = path if path.is_absolute() else root / path
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            _finding(
                "architecture-drift.unreadable",
                display_path,
                f"architecture document is missing or unreadable: {exc}",
                line=1,
            )
        )
        return AuditReport(
            tool="architecture_drift",
            status=AuditStatus.FAIL,
            source_sha=facts.source_sha,
            findings=findings,
            summary={"architecture_path": normalise_path(display_path), "symbols_available": 0},
        )

    symbols = _symbol_facts(facts)
    by_leaf = _symbols_by_leaf(symbols)
    fences, prose = _extract_fences(text)
    findings.extend(
        _check_text_references(
            prose,
            repo_root=root,
            architecture_file=display_path,
            line_offset=1,
            symbols=symbols,
            by_leaf=by_leaf,
        )
    )
    checked_fences = 0
    skipped_fences = 0
    for fence in fences:
        if fence.lang not in _ELIGIBLE_FENCE_LANGS:
            continue
        if _is_non_normative(fence.context) or _is_non_normative(fence.code.splitlines()[0] if fence.code else ""):
            skipped_fences += 1
            continue
        checked_fences += 1
        if fence.lang in {"python", "py"}:
            findings.extend(
                _check_python_block(
                    fence,
                    architecture_file=display_path,
                    symbols=symbols,
                    by_leaf=by_leaf,
                )
            )
        findings.extend(
            _check_text_references(
                fence.code,
                repo_root=root,
                architecture_file=display_path,
                line_offset=fence.start_line,
                symbols=symbols,
                by_leaf=by_leaf,
            )
        )

    return AuditReport(
        tool="architecture_drift",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=facts.source_sha,
        findings=findings,
        summary={
            "architecture_path": normalise_path(display_path),
            "symbols_available": len(symbols),
            "fences_checked": checked_fences,
            "fences_skipped": skipped_fences,
            "references_checked": len(findings),
        },
    )
