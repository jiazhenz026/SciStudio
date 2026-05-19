"""Run ADR-042 QA checks from pre-commit and CI without editable installs."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _skip_if_no_paths(args: list[str]) -> int | None:
    return 0 if not args else None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: run_adr042_check.py <check> [args...]", file=sys.stderr)
        return 2

    check = args.pop(0)
    if check == "code-score":
        from scieasy.qa import code_score

        return code_score.main(args)
    if check == "frontmatter-lint":
        if (skip := _skip_if_no_paths(args)) is not None:
            return skip
        from scieasy.qa.audit import frontmatter_lint

        return frontmatter_lint.main(args)
    if check == "doc-length-lint":
        if (skip := _skip_if_no_paths(args)) is not None:
            return skip
        from scieasy.qa.audit import doc_length_lint

        return doc_length_lint.main(args)
    if check == "auto-generated-lint":
        from scieasy.qa.audit import auto_generated_lint

        return auto_generated_lint.main(args)
    if check == "skill-pointer-sync":
        from scieasy.qa.audit import skill_pointer_sync

        return skill_pointer_sync.main(args)
    if check == "generate-facts":
        from scieasy.qa.audit.facts import check_generated_facts

        update = "--write" in args
        filtered = [arg for arg in args if arg != "--write"]
        facts_path = "docs/facts/generated.yaml"
        if "--facts-path" in filtered:
            index = filtered.index("--facts-path")
            facts_path = filtered[index + 1]
        report = check_generated_facts(REPO_ROOT, facts_path=Path(facts_path), update=update)
        print(report.model_dump_json() if "--format=json" in args or "--json" in args else report.status)
        return 1 if report.status == "failed" else 0
    if check == "doc-drift":
        from scieasy.qa.audit.doc_drift import main as doc_drift_main

        return doc_drift_main(args)
    if check == "fact-drift":
        from scieasy.qa.audit.fact_drift import main as fact_drift_main

        return fact_drift_main(args)
    if check == "closure":
        from scieasy.qa.audit.closure import main as closure_main

        return closure_main(args)
    if check == "signature-drift":
        from scieasy.qa.audit.signature_drift import main as signature_drift_main

        return signature_drift_main(args)
    if check == "full-audit":
        from scieasy.qa.audit.full_audit import main as full_audit_main

        return full_audit_main(args)
    if check == "local-gate":
        from scieasy.qa.governance.local_gate import _main as local_gate_main

        return local_gate_main(args)
    if check == "docs-landing":
        from scieasy.qa.governance.docs_landing import main as docs_landing_main

        return docs_landing_main(args)
    if check == "persona-policy":
        from scieasy.qa.governance.persona_policy import main as persona_policy_main

        return persona_policy_main(args)
    if check == "human-bypass":
        from scieasy.qa.governance.human_bypass_guard import main as human_bypass_main

        return human_bypass_main(args)
    if check == "weakened-ci":
        from scieasy.qa.governance.weakened_ci_check import main as weakened_ci_main

        return weakened_ci_main(args)
    if check == "core-change-guard":
        from scieasy.qa.governance.core_change_guard import main as core_change_main

        return core_change_main(args)
    if check == "governance-mod-guard":
        from scieasy.qa.governance.mod_guard import main as mod_guard_main

        return mod_guard_main(args)
    if check == "complete-artifacts":
        from scieasy.qa.audit.complete_artifacts import main as complete_artifacts_main

        return complete_artifacts_main(args)
    if check == "codemod-lint":
        from scieasy.qa.audit.codemod_lint import main as codemod_lint_main

        return codemod_lint_main(args)
    if check == "trailer-lint":
        from scieasy.qa.audit.trailer_lint import main as trailer_lint_main

        return trailer_lint_main(args)

    print(f"unknown ADR-042 check: {check}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
