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

    print(f"unknown ADR-042 check: {check}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
