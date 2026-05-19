"""Compare spec-defined signatures against implementation."""

from __future__ import annotations

import argparse
import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa._shared import AuditFinding, AuditReport
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.schemas.facts import Fact, FactsRegistry, load_facts
from scieasy.qa.schemas.signatures import ExpectedCliCommand, ExpectedModelField, ExpectedSignature, ParameterSpec


def _resolve_symbol(symbol: str) -> Any:
    parts = symbol.split(".")
    for index in range(len(parts), 0, -1):
        module_name = ".".join(parts[:index])
        attrs = parts[index:]
        try:
            current = importlib.import_module(module_name)
        except Exception:
            continue
        for attr in attrs:
            current = getattr(current, attr)
        return current
    raise ImportError(symbol)


def _symbol_index(facts: FactsRegistry) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for fact in facts.facts:
        if fact.kind != "symbol" or not isinstance(fact.subject, str):
            continue
        short_name = fact.subject.rsplit(".", 1)[-1]
        index.setdefault(short_name, [])
        if fact.subject not in index[short_name]:
            index[short_name].append(fact.subject)
    return index


def _resolve_expected(symbol: str, index: dict[str, list[str]]) -> Any:
    candidates = [symbol]
    if "." not in symbol:
        candidates.extend(index.get(symbol, []))
    errors: list[Exception] = []
    for candidate in candidates:
        try:
            return _resolve_symbol(candidate)
        except Exception as exc:
            errors.append(exc)
    raise ImportError(symbol) from (errors[-1] if errors else None)


def _annotation(value: Any) -> str | None:
    if value is inspect.Signature.empty:
        return None
    if isinstance(value, str):
        return value
    return getattr(value, "__name__", str(value).replace("typing.", ""))


def _param_kind(kind: inspect._ParameterKind) -> str:
    return {
        inspect.Parameter.POSITIONAL_ONLY: "positional-only",
        inspect.Parameter.POSITIONAL_OR_KEYWORD: "positional-or-keyword",
        inspect.Parameter.VAR_POSITIONAL: "var-positional",
        inspect.Parameter.KEYWORD_ONLY: "keyword-only",
        inspect.Parameter.VAR_KEYWORD: "var-keyword",
    }[kind]


def _actual_parameters(obj: Any) -> list[ParameterSpec]:
    signature = inspect.signature(obj)
    params: list[ParameterSpec] = []
    for parameter in signature.parameters.values():
        if parameter.name in {"self", "cls"}:
            continue
        params.append(
            ParameterSpec(
                name=parameter.name,
                kind=_param_kind(parameter.kind),  # type: ignore[arg-type]
                annotation=_annotation(parameter.annotation),
                default=None if parameter.default is inspect.Signature.empty else repr(parameter.default),
                required=parameter.default is inspect.Signature.empty,
            )
        )
    return params


def _fact_value(fact: Fact) -> dict[str, Any]:
    return fact.value if isinstance(fact.value, dict) else {}


def _check_signature(repo_root: Path, fact: Fact, index: dict[str, list[str]]) -> list[AuditFinding]:
    expected = ExpectedSignature.model_validate(_fact_value(fact))
    findings = []
    try:
        obj = _resolve_expected(expected.symbol, index)
    except Exception:
        return [
            build_finding(
                finding_id="signature-drift-missing-symbol",
                tool="signature_drift",
                finding_class="signature-drift",
                severity="error",
                message=f"Expected symbol is missing: {expected.symbol}",
                path=expected.source_spec,
                line=expected.source_line,
                subject=expected.symbol,
            )
        ]
    if expected.kind in {"function", "method"}:
        actual_params = _actual_parameters(obj)
        expected_projection = [(p.name, p.kind, p.required) for p in expected.parameters]
        actual_projection = [(p.name, p.kind, p.required) for p in actual_params]
        if actual_projection != expected_projection:
            findings.append(
                build_finding(
                    finding_id="signature-drift-parameters",
                    tool="signature_drift",
                    finding_class="signature-drift",
                    severity="error",
                    message=f"Parameter list differs for {expected.symbol}",
                    path=expected.source_spec,
                    line=expected.source_line,
                    subject=expected.symbol,
                    expected=expected_projection,
                    actual=actual_projection,
                )
            )
        actual_return = _annotation(inspect.signature(obj).return_annotation)
        if expected.return_annotation and actual_return != expected.return_annotation:
            findings.append(
                build_finding(
                    finding_id="signature-drift-return",
                    tool="signature_drift",
                    finding_class="signature-drift",
                    severity="error",
                    message=f"Return annotation differs for {expected.symbol}",
                    path=expected.source_spec,
                    line=expected.source_line,
                    subject=expected.symbol,
                    expected=expected.return_annotation,
                    actual=actual_return,
                )
            )
    elif expected.kind == "class" and not inspect.isclass(obj):
        findings.append(
            build_finding(
                finding_id="signature-drift-kind",
                tool="signature_drift",
                finding_class="signature-drift",
                severity="error",
                message=f"Expected {expected.symbol} to be a class",
                path=expected.source_spec,
                line=expected.source_line,
                subject=expected.symbol,
                expected="class",
                actual=type(obj).__name__,
            )
        )
    return findings


def _check_model_field(fact: Fact, index: dict[str, list[str]]) -> list[AuditFinding]:
    expected = ExpectedModelField.model_validate(_fact_value(fact))
    try:
        model = _resolve_expected(expected.model_symbol, index)
    except Exception:
        return [
            build_finding(
                finding_id="signature-drift-missing-model",
                tool="signature_drift",
                finding_class="signature-drift",
                severity="error",
                message=f"Expected model is missing: {expected.model_symbol}",
                path=expected.source_spec,
                line=expected.source_line,
                subject=expected.model_symbol,
            )
        ]
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        return []
    fields = getattr(model, "model_fields", {})
    if expected.field_name not in fields:
        return [
            build_finding(
                finding_id="signature-drift-model-field",
                tool="signature_drift",
                finding_class="signature-drift",
                severity="error",
                message=f"Expected Pydantic field is missing: {expected.model_symbol}.{expected.field_name}",
                path=expected.source_spec,
                line=expected.source_line,
                subject=f"{expected.model_symbol}.{expected.field_name}",
            )
        ]
    return []


def _check_cli(fact: Fact, *, check_cli: bool) -> list[AuditFinding]:
    if not check_cli:
        return []
    expected = ExpectedCliCommand.model_validate(_fact_value(fact))
    if expected.module is None:
        return []
    try:
        importlib.import_module(expected.module)
    except Exception as exc:
        return [
            build_finding(
                finding_id="signature-drift-missing-cli",
                tool="signature_drift",
                finding_class="signature-drift",
                severity="error",
                message=f"Expected CLI module is missing: {expected.module}",
                path=expected.source_spec,
                line=expected.source_line,
                subject=" ".join(expected.command),
                actual=type(exc).__name__,
            )
        ]
    return []


def check_expected_signatures(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    check_cli: bool = True,
    cli_timeout_seconds: int = 10,
) -> AuditReport:
    del cli_timeout_seconds
    repo_root = repo_root.resolve()
    findings = []
    index = _symbol_index(facts)
    for fact in facts.facts:
        if fact.kind == "expected-signature":
            findings.extend(_check_signature(repo_root, fact, index))
        elif fact.kind == "expected-model-field":
            findings.extend(_check_model_field(fact, index))
        elif fact.kind == "expected-cli-command":
            findings.extend(_check_cli(fact, check_cli=check_cli))
    return build_report(tool="signature_drift", repo_root=repo_root, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ADR-042 signature drift checks.")
    parser.add_argument("--facts", default="docs/facts/generated.yaml")
    parser.add_argument("--no-cli", action="store_true")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    try:
        report = check_expected_signatures(Path.cwd(), load_facts(Path(args.facts)), check_cli=not args.no_cli)
    except Exception as exc:
        print(f"signature_drift: {exc}", file=sys.stderr)
        return 2
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
