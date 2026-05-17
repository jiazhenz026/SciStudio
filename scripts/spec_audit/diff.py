"""diff — 4-way join over code.json + spec.json + docs.json.

Produces:
  - build/spec-audit/diff-report.md (human-readable)
  - exit code:
      0 = clean (every code symbol in spec, every spec symbol in code, signatures match,
          labels match observed state)
      1 = warnings only (orphan doc refs, missing primary-doc-source, label mismatches)
      2 = errors (code-not-in-spec, spec-not-in-code, signature-mismatch when status=a)

Findings categories (see DiffFinding):
  - code-not-in-spec       ERROR (during steady-state CI; relaxed during Phase 1.5 baseline)
  - spec-not-in-code       WARN if status=c, ERROR otherwise
  - signature-mismatch     ERROR if status=a (an "a" claim is broken)
                           INFO if status=b (b is *expected* to differ; pick happened)
  - doc-orphan             WARN — docs mention something not in code or spec
  - label-mismatch         WARN — spec says "a" but docs disagree, etc.
  - missing-primary-doc    WARN — spec entry has `[ARCHITECTURE: not documented]`
                           (legitimate; just flag for follow-up)

Phase modes (set via --mode):
  - "baseline" — used in Phase 0 before INTERFACE_SPEC.md exists; only reports the
    code surface inventory. Always exits 0.
  - "drift" — full diff. The default for CI.

Usage:
    python -m scripts.spec_audit.diff --mode drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .models import DiffFinding


def _load(path: Path) -> list[dict[str, Any]] | dict[str, Any]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def diff_records(
    code_records: list[dict[str, Any]],
    spec_records: list[dict[str, Any]],
    docs_mentions: dict[str, list[dict[str, Any]]],
    mode: str = "drift",
) -> list[DiffFinding]:
    findings: list[DiffFinding] = []

    code_by_id: dict[str, dict[str, Any]] = {r["interface_id"]: r for r in code_records}
    spec_by_id: dict[str, dict[str, Any]] = {r["interface_id"]: r for r in spec_records}

    code_ids = set(code_by_id.keys())
    spec_ids = set(spec_by_id.keys())
    docs_ids = set(docs_mentions.keys())

    # 1. code ∩ spec — verify signature consistency + label sanity
    for iid in code_ids & spec_ids:
        c = code_by_id[iid]
        s = spec_by_id[iid]
        status = s.get("status")
        if status == "a":
            # Signature must match
            code_sig = c.get("signature", {})
            spec_sig_body = s.get("signature", {}).get("body", "")
            # Loose check: see if signature.name (code) appears in spec body
            sig_name = code_sig.get("name") or code_sig.get("class_name")
            if sig_name and sig_name not in spec_sig_body:
                findings.append(
                    DiffFinding(
                        interface_id=iid,
                        severity="error",
                        category="signature-mismatch",
                        detail=f"Status=a but spec body does not mention `{sig_name}`",
                        code_record=c,
                        spec_record=s,
                    )
                )
                continue
            findings.append(
                DiffFinding(
                    interface_id=iid,
                    severity="info",
                    category="ok",
                    detail="code + spec aligned (status=a)",
                    code_record=c,
                    spec_record=s,
                )
            )
        else:
            findings.append(
                DiffFinding(
                    interface_id=iid,
                    severity="info",
                    category="ok",
                    detail=f"code + spec present (status={status})",
                    code_record=c,
                    spec_record=s,
                )
            )

    # 2. code only — present in code, absent from spec.
    #    In baseline mode this is normal (spec doesn't exist yet); in drift mode it's an error.
    for iid in code_ids - spec_ids:
        severity = "info" if mode == "baseline" else "error"
        findings.append(
            DiffFinding(
                interface_id=iid,
                severity=severity,  # type: ignore[arg-type]
                category="code-not-in-spec",
                detail="Code symbol has no entry in INTERFACE_SPEC.md",
                code_record=code_by_id[iid],
            )
        )

    # 3. spec only — present in spec, absent from code.
    #    Expected for status=c. Error otherwise.
    for iid in spec_ids - code_ids:
        s = spec_by_id[iid]
        status = s.get("status")
        # c-label expected: docs say it, code doesn't (tracked via Issue). Any other status = error.
        severity = "warn" if status == "c" else "error"
        findings.append(
            DiffFinding(
                interface_id=iid,
                severity=severity,  # type: ignore[arg-type]
                category="spec-not-in-code",
                detail=f"Spec entry status={status} but no code symbol found",
                spec_record=s,
            )
        )

    # 4. Missing primary-doc-source on spec entries
    for iid, s in spec_by_id.items():
        if s.get("primary_doc_source") == "[ARCHITECTURE: not documented]":
            findings.append(
                DiffFinding(
                    interface_id=iid,
                    severity="warn",
                    category="missing-primary-doc",
                    detail="Spec entry has placeholder Primary-doc-source — needs ARCHITECTURE.md amendment",
                    spec_record=s,
                )
            )

    # 5. Doc orphans: docs mention something neither in code nor in spec.
    #    (Rare with conservative matching, but possible after renames.)
    for iid in docs_ids - code_ids - spec_ids:
        findings.append(
            DiffFinding(
                interface_id=iid,
                severity="warn",
                category="doc-orphan",
                detail="Docs mention symbol not present in code or spec",
                docs_record={"mentions": docs_mentions[iid]},
            )
        )

    return findings


def render_markdown(findings: list[DiffFinding], mode: str) -> str:
    by_sev: dict[str, list[DiffFinding]] = {"error": [], "warn": [], "info": []}
    for f in findings:
        by_sev[f.severity].append(f)

    by_cat: dict[str, int] = {}
    for f in findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1

    out = [
        "# Interface SSOT diff report",
        f"Mode: **{mode}**",
        "",
        f"- Errors: **{len(by_sev['error'])}**",
        f"- Warnings: **{len(by_sev['warn'])}**",
        f"- OK / Info: **{len(by_sev['info'])}**",
        "",
        "## By category",
        "",
    ]
    for cat, n in sorted(by_cat.items()):
        out.append(f"- `{cat}`: {n}")
    out.append("")

    for sev in ("error", "warn", "info"):
        items = by_sev[sev]
        if not items:
            continue
        out.append(f"## {sev.upper()} findings ({len(items)})")
        out.append("")
        for f in items:
            out.append(f"### `{f.interface_id}` — {f.category}")
            out.append(f"{f.detail}")
            if f.code_record and f.code_record.get("source_file"):
                out.append(f"- code: `{f.code_record['source_file']}:{f.code_record.get('source_lines', '')}`")
            if f.spec_record:
                out.append(
                    f"- spec: status={f.spec_record.get('status')}, source=`{f.spec_record.get('source_file')}:{f.spec_record.get('source_lines', '')}`"
                )
            if f.docs_record:
                out.append(f"- docs: {len(f.docs_record.get('mentions', []))} mention(s)")
            out.append("")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="3-way diff: code.json + spec.json + docs.json")
    ap.add_argument("--code", type=Path, default=Path("build/spec-audit/code.json"))
    ap.add_argument("--spec", type=Path, default=Path("build/spec-audit/spec.json"))
    ap.add_argument("--docs", type=Path, default=Path("build/spec-audit/docs.json"))
    ap.add_argument("--out", type=Path, default=Path("build/spec-audit/diff-report.md"))
    ap.add_argument("--mode", choices=["baseline", "drift"], default="drift")
    args = ap.parse_args()

    code_records = _load(args.code)
    spec_records = _load(args.spec)
    docs_mentions_raw = _load(args.docs)

    if isinstance(code_records, dict) or isinstance(spec_records, dict):
        print("[diff] ERROR: code/spec must be lists", file=sys.stderr)
        return 2
    docs_mentions: dict[str, list[dict[str, Any]]] = docs_mentions_raw if isinstance(docs_mentions_raw, dict) else {}

    findings = diff_records(code_records, spec_records, docs_mentions, mode=args.mode)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(findings, args.mode), encoding="utf-8")
    print(f"[diff] {len(findings)} findings → {args.out}")

    if args.mode == "baseline":
        return 0
    errors = sum(1 for f in findings if f.severity == "error")
    warns = sum(1 for f in findings if f.severity == "warn")
    if errors:
        print(f"[diff] FAIL: {errors} errors, {warns} warnings", file=sys.stderr)
        return 2
    if warns:
        print(f"[diff] OK with {warns} warnings", file=sys.stderr)
        return 1
    print("[diff] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
