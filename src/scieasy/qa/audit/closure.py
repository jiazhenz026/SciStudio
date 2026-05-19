"""Bidirectional ownership and governed-surface closure checks."""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import sys
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.schemas.facts import Fact, FactsRegistry, load_facts
from scieasy.qa.schemas.maintainers import Maintainers, load_maintainers


def _has_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[]")


def _path_exists(repo_root: Path, pattern: str) -> bool:
    if _has_glob(pattern):
        return any(repo_root.glob(pattern))
    return (repo_root / pattern).exists()


def _symbol_exists(symbol: str) -> bool:
    parts = symbol.split(".")
    for index in range(len(parts), 0, -1):
        module_name = ".".join(parts[:index])
        attrs = parts[index:]
        try:
            current = importlib.import_module(module_name)
        except Exception:
            continue
        for attr in attrs:
            if not hasattr(current, attr):
                return False
            current = getattr(current, attr)
        return True
    return False


def _is_tracked_future_work(repo_root: Path, subject: str) -> bool:
    needle = subject.replace("\\", "/")
    for path in sorted((repo_root / "docs").rglob("*.md")) if (repo_root / "docs").exists() else []:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if needle in text and ("TODO(#" in text or "future-work" in text or "tracking_issue" in text):
            return True
    return False


def _maintainer_covers(maintainers: Maintainers, subject: str) -> bool:
    return any(fnmatch.fnmatch(subject, rule.pattern) for rule in maintainers.rules)


def _normative_facts(facts: FactsRegistry, kind: str) -> list[Fact]:
    return [fact for fact in facts.facts if fact.kind == kind and fact.confidence == "normative"]


def check_bidirectional(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    maintainers: Maintainers | None = None,
):
    repo_root = repo_root.resolve()
    maintainers = maintainers or load_maintainers(repo_root / "MAINTAINERS")
    findings = []

    for fact in _normative_facts(facts, "file"):
        subject = fact.subject
        if _path_exists(repo_root, subject) or _is_tracked_future_work(repo_root, subject):
            continue
        findings.append(
            build_finding(
                finding_id="closure-phantom-governed-file",
                tool="closure",
                finding_class="phantom-reference",
                severity="error",
                message=f"Governed file path does not resolve: {subject}",
                path=fact.source,
                subject=subject,
                remediation="Create the path, correct the governed file claim, or record tracked future work.",
            )
        )

    for fact in _normative_facts(facts, "symbol"):
        subject = fact.subject
        if (
            subject.startswith("scieasy.")
            and not _symbol_exists(subject)
            and not _is_tracked_future_work(repo_root, subject)
        ):
            findings.append(
                build_finding(
                    finding_id="closure-phantom-governed-symbol",
                    tool="closure",
                    finding_class="phantom-reference",
                    severity="error",
                    message=f"Governed symbol does not resolve: {subject}",
                    path=fact.source,
                    subject=subject,
                    remediation="Implement the symbol, correct the governed claim, or record tracked future work.",
                )
            )

    normative_subjects = {fact.subject for fact in _normative_facts(facts, "symbol")}
    for fact in [item for item in facts.facts if item.kind == "symbol" and item.confidence == "generated"]:
        if fact.subject in normative_subjects:
            continue
        file_subject = str(fact.value.get("path", "")) if isinstance(fact.value, dict) else ""
        covered = (
            bool(fact.owner)
            or _maintainer_covers(maintainers, fact.subject)
            or _maintainer_covers(maintainers, file_subject)
        )
        if not covered:
            findings.append(
                build_finding(
                    finding_id="closure-missing-symbol-owner",
                    tool="closure",
                    finding_class="missing-documentation",
                    severity="error",
                    message=f"Public symbol has no ADR/spec or maintainer owner: {fact.subject}",
                    path=fact.source,
                    subject=fact.subject,
                    remediation="Add an ADR/spec governed contract or MAINTAINERS rule.",
                )
            )

    return build_report(tool="closure", repo_root=repo_root, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ADR-042 closure checks.")
    parser.add_argument("--facts", default="docs/facts/generated.yaml")
    parser.add_argument("--maintainers", default="MAINTAINERS")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    try:
        report = check_bidirectional(
            Path.cwd(),
            load_facts(Path(args.facts)),
            maintainers=load_maintainers(Path(args.maintainers)),
        )
    except Exception as exc:
        print(f"closure: {exc}", file=sys.stderr)
        return 2
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
