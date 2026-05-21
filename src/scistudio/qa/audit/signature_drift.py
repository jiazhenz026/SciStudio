"""Compare expected signature facts against griffe symbol facts."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from scistudio.qa.audit.signature_contracts import extract_governed_signature_contracts
from scistudio.qa.schemas.facts import Fact, FactsRegistry
from scistudio.qa.schemas.report import AuditReport, AuditStatus, DriftClass, Finding, Severity
from scistudio.qa.schemas.signatures import ExpectedCliCommand, ExpectedModelField, ExpectedSignature


def _symbol_facts(facts: FactsRegistry) -> dict[str, Fact]:
    return {fact.subject: fact for fact in facts.find(kind="symbol")}


def _expected_signature_facts(facts: FactsRegistry) -> list[Fact]:
    return facts.find(kind="expected-signature")


def _expected_model_field_facts(facts: FactsRegistry) -> list[Fact]:
    return facts.find(kind="expected-model-field")


def _expected_cli_command_facts(facts: FactsRegistry) -> list[Fact]:
    return facts.find(kind="expected-cli-command")


def _cli_facts(facts: FactsRegistry) -> dict[str, Fact]:
    return {fact.subject: fact for fact in facts.find(kind="cli")}


def _normalize(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "None"}:
        return None
    return text.strip("'\"")


def _param_shape(parameters: object) -> list[tuple[str, str | None, bool]]:
    if not isinstance(parameters, list):
        return []
    shaped: list[tuple[str, str | None, bool]] = []
    for parameter in parameters:
        if not isinstance(parameter, Mapping):
            continue
        name = str(parameter.get("name", ""))
        if name in {"self", "cls"}:
            continue
        shaped.append((name, _normalize(parameter.get("annotation")), bool(parameter.get("required", True))))
    return shaped


def _resolve_symbol(expected: ExpectedSignature, symbols: dict[str, Fact]) -> tuple[Fact | None, str | None]:
    if expected.subject in symbols:
        return symbols[expected.subject], None
    matches = [fact for subject, fact in symbols.items() if subject.endswith(f".{expected.subject}")]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, "missing"
    return None, "ambiguous"


def _finding(
    rule_id: str,
    expected: ExpectedSignature,
    message: str,
    *,
    symbol: str | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        file=expected.source_path,
        line=expected.line,
        message=message,
        symbol=symbol or expected.subject,
        drift_class=DriftClass.SIGNATURE_DRIFT,
    )


def _resolve_dotted_object(symbol: str, repo_root: Path) -> Any:
    src_path = str((repo_root / "src").resolve())
    inserted = False
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
        inserted = True
    try:
        parts = symbol.split(".")
        last_error: Exception | None = None
        for index in range(len(parts), 0, -1):
            module_name = ".".join(parts[:index])
            try:
                obj: Any = importlib.import_module(module_name)
            except Exception as exc:
                last_error = exc
                continue
            for attr in parts[index:]:
                obj = getattr(obj, attr)
            return obj
        raise ImportError(f"could not import {symbol}: {last_error}")
    finally:
        if inserted:
            with suppress(ValueError):
                sys.path.remove(src_path)


def _annotation_name(annotation: object) -> str | None:
    if annotation is None:
        return None
    name = getattr(annotation, "__name__", None)
    module = getattr(annotation, "__module__", None)
    if isinstance(name, str):
        return name if module in {None, "builtins"} else f"{module}.{name}"
    return _normalize(annotation)


def _field_default(field: object) -> str | None:
    if hasattr(field, "is_required") and field.is_required():
        return None
    default = getattr(field, "default", None)
    return _normalize(default)


def _compare_expected_model_field(expected_fact: Fact, repo_root: Path) -> list[Finding]:
    expected = ExpectedModelField.model_validate(expected_fact.value)
    try:
        model = _resolve_dotted_object(expected.model_symbol, repo_root)
    except (AttributeError, ImportError) as exc:
        return [
            Finding(
                rule_id="signature-drift.missing-model",
                severity=Severity.ERROR,
                file=expected.source_spec,
                line=expected.source_line,
                message=f"expected model is missing: {expected.model_symbol} ({exc})",
                symbol=expected.model_symbol,
                drift_class=DriftClass.SIGNATURE_DRIFT,
            )
        ]
    fields = getattr(model, "model_fields", None)
    if not isinstance(fields, Mapping):
        return [
            Finding(
                rule_id="signature-drift.not-pydantic-model",
                severity=Severity.ERROR,
                file=expected.source_spec,
                line=expected.source_line,
                message=f"expected Pydantic model has no model_fields: {expected.model_symbol}",
                symbol=expected.model_symbol,
                drift_class=DriftClass.SIGNATURE_DRIFT,
            )
        ]
    actual = fields.get(expected.field_name)
    if actual is None:
        return [
            Finding(
                rule_id="signature-drift.missing-model-field",
                severity=Severity.ERROR,
                file=expected.source_spec,
                line=expected.source_line,
                message=f"expected model field is missing: {expected.model_symbol}.{expected.field_name}",
                symbol=f"{expected.model_symbol}.{expected.field_name}",
                drift_class=DriftClass.SIGNATURE_DRIFT,
            )
        ]
    findings: list[Finding] = []
    actual_annotation = _annotation_name(getattr(actual, "annotation", None))
    if _normalize(expected.annotation) != actual_annotation:
        findings.append(
            Finding(
                rule_id="signature-drift.model-field-annotation-mismatch",
                severity=Severity.ERROR,
                file=expected.source_spec,
                line=expected.source_line,
                message=(
                    f"model field annotation differs for {expected.model_symbol}.{expected.field_name}; "
                    f"expected {_normalize(expected.annotation)}, actual {actual_annotation}"
                ),
                symbol=f"{expected.model_symbol}.{expected.field_name}",
                drift_class=DriftClass.SIGNATURE_DRIFT,
            )
        )
    actual_required = bool(actual.is_required()) if hasattr(actual, "is_required") else False
    if expected.required != actual_required:
        findings.append(
            Finding(
                rule_id="signature-drift.model-field-required-mismatch",
                severity=Severity.ERROR,
                file=expected.source_spec,
                line=expected.source_line,
                message=(
                    f"model field required flag differs for {expected.model_symbol}.{expected.field_name}; "
                    f"expected {expected.required}, actual {actual_required}"
                ),
                symbol=f"{expected.model_symbol}.{expected.field_name}",
                drift_class=DriftClass.SIGNATURE_DRIFT,
            )
        )
    actual_default = _field_default(actual)
    if _normalize(expected.default) != actual_default:
        findings.append(
            Finding(
                rule_id="signature-drift.model-field-default-mismatch",
                severity=Severity.ERROR,
                file=expected.source_spec,
                line=expected.source_line,
                message=(
                    f"model field default differs for {expected.model_symbol}.{expected.field_name}; "
                    f"expected {_normalize(expected.default)}, actual {actual_default}"
                ),
                symbol=f"{expected.model_symbol}.{expected.field_name}",
                drift_class=DriftClass.SIGNATURE_DRIFT,
            )
        )
    return findings


def _compare_expected_cli_command(expected_fact: Fact, cli_facts: Mapping[str, Fact]) -> list[Finding]:
    expected = ExpectedCliCommand.model_validate(expected_fact.value)
    subject = " ".join(expected.command)
    actual = cli_facts.get(subject)
    if actual is None:
        return [
            Finding(
                rule_id="signature-drift.missing-cli-command",
                severity=Severity.ERROR,
                file=expected.source_spec,
                line=expected.source_line,
                message=f"expected CLI command is missing from CLI facts: {subject}",
                symbol=subject,
                drift_class=DriftClass.SIGNATURE_DRIFT,
            )
        ]
    actual_value = actual.value if isinstance(actual.value, Mapping) else {}
    actual_exit_codes = {int(k): str(v) for k, v in dict(actual_value.get("exit_codes", {})).items()}
    expected_exit_codes = {int(k): str(v) for k, v in expected.expected_exit_codes.items()}
    if expected_exit_codes != actual_exit_codes:
        return [
            Finding(
                rule_id="signature-drift.cli-exit-codes-mismatch",
                severity=Severity.ERROR,
                file=expected.source_spec,
                line=expected.source_line,
                message=f"CLI exit codes differ for {subject}; expected {expected_exit_codes}, actual {actual_exit_codes}",
                symbol=subject,
                drift_class=DriftClass.SIGNATURE_DRIFT,
            )
        ]
    return []


def _compare_expected_signature(expected_fact: Fact, symbols: dict[str, Fact]) -> list[Finding]:
    expected = ExpectedSignature.model_validate(expected_fact.value)
    actual, resolution = _resolve_symbol(expected, symbols)
    if resolution == "missing":
        return [_finding("signature-drift.missing-symbol", expected, f"expected symbol is missing: {expected.subject}")]
    if resolution == "ambiguous":
        return [
            _finding(
                "signature-drift.ambiguous-symbol",
                expected,
                f"expected symbol name resolves to multiple implementation symbols: {expected.subject}",
            )
        ]
    if actual is None:
        return []

    actual_value = actual.value if isinstance(actual.value, Mapping) else {}
    actual_kind = _normalize(actual_value.get("kind"))
    if expected.kind != actual_kind:
        return [
            _finding(
                "signature-drift.kind-mismatch",
                expected,
                f"expected {expected.kind} but implementation fact is {actual_kind}",
                symbol=actual.subject,
            )
        ]
    if expected.kind in {"class", "attribute", "pydantic-model", "cli-command"}:
        return []

    findings: list[Finding] = []
    expected_params = [
        (param.name, _normalize(param.annotation), param.required)
        for param in expected.parameters
        if param.name not in {"self", "cls"}
    ]
    actual_params = _param_shape(actual_value.get("parameters"))
    if expected_params != actual_params:
        findings.append(
            _finding(
                "signature-drift.parameters-mismatch",
                expected,
                f"parameter shape differs for {actual.subject}; expected {expected_params}, actual {actual_params}",
                symbol=actual.subject,
            )
        )
    expected_return = _normalize(expected.return_annotation)
    actual_return = _normalize(actual_value.get("return_annotation"))
    if expected_return != actual_return:
        findings.append(
            _finding(
                "signature-drift.return-mismatch",
                expected,
                f"return annotation differs for {actual.subject}; expected {expected_return}, actual {actual_return}",
                symbol=actual.subject,
            )
        )
    return findings


def check_expected_signatures(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    check_cli: bool = True,
    cli_timeout_seconds: int = 10,
) -> AuditReport:
    """Compare expected signature facts against implementation symbol facts."""

    del check_cli, cli_timeout_seconds
    symbols = _symbol_facts(facts)
    expected_facts = _expected_signature_facts(facts)
    expected_model_fields = _expected_model_field_facts(facts)
    expected_cli_commands = _expected_cli_command_facts(facts)
    actual_cli_facts = _cli_facts(facts)
    findings: list[Finding] = []
    for expected_fact in expected_facts:
        findings.extend(_compare_expected_signature(expected_fact, symbols))
    for expected_fact in expected_model_fields:
        findings.extend(_compare_expected_model_field(expected_fact, repo_root))
    for expected_fact in expected_cli_commands:
        findings.extend(_compare_expected_cli_command(expected_fact, actual_cli_facts))
    return AuditReport(
        tool="signature_drift",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=facts.source_sha,
        findings=findings,
        summary={
            "expected_signatures_checked": len(expected_facts),
            "expected_model_fields_checked": len(expected_model_fields),
            "expected_cli_commands_checked": len(expected_cli_commands),
            "symbols_available": len(symbols),
            "cli_facts_available": len(actual_cli_facts),
        },
    )


def extract_expected_signature_facts(
    repo_root: Path,
    *,
    source_sha: str,
) -> list[Fact]:
    """Extract expected signature facts from active specs and ADRs."""

    return extract_governed_signature_contracts(
        repo_root=repo_root,
        source_sha=source_sha,
    )
