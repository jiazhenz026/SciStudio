"""Compare expected signature facts against griffe symbol facts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from scieasy.qa.audit.signature_contracts import extract_signature_contracts
from scieasy.qa.schemas.facts import Fact, FactsRegistry
from scieasy.qa.schemas.report import AuditReport, AuditStatus, DriftClass, Finding, Severity
from scieasy.qa.schemas.signatures import ExpectedSignature


def _symbol_facts(facts: FactsRegistry) -> dict[str, Fact]:
    return {fact.subject: fact for fact in facts.find(kind="symbol")}


def _expected_signature_facts(facts: FactsRegistry) -> list[Fact]:
    return facts.find(kind="expected-signature")


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
    if expected.kind == "class":
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

    del repo_root, check_cli, cli_timeout_seconds
    symbols = _symbol_facts(facts)
    expected_facts = _expected_signature_facts(facts)
    findings: list[Finding] = []
    for expected_fact in expected_facts:
        findings.extend(_compare_expected_signature(expected_fact, symbols))
    return AuditReport(
        tool="signature_drift",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=facts.source_sha,
        findings=findings,
        summary={"expected_signatures_checked": len(expected_facts), "symbols_available": len(symbols)},
    )


def extract_expected_signature_facts(
    repo_root: Path,
    *,
    source_sha: str,
) -> list[Fact]:
    """Extract expected signature facts from all specs."""

    return extract_signature_contracts(
        sorted((repo_root / "docs" / "specs").glob("*.md")),
        repo_root=repo_root,
        source_sha=source_sha,
    )
