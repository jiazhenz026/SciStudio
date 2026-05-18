---
title: "doc_drift.classify_repo — algorithm pseudocode"
relates_to: ADR-042
section: §9.2
agent_editable: false
date_created: 2026-05-18
---

# `doc_drift.classify_repo` — Algorithm

This file holds the companion pseudocode for ADR-042 §9.2. The ADR itself
keeps only the function-level overview; the detailed steps live here per
§28.0 so `pytest-examples` does not attempt to execute the prose-form
pseudocode embedded in the ADR.

> Status: **non-executable reference**. The Phase 1B implementation in
> `src/scieasy/qa/audit/doc_drift.py` is the source of truth; this file
> tracks the algorithm shape for human reviewers and out-of-band
> audit cycles.

---

## Inputs

* `repo_root: Path` — the working tree (any clean checkout).
* (Implicit) the set of Accepted ADRs discovered under `docs/adr/`.

## Outputs

A `scieasy.qa.schemas.report.AuditReport` with one `ToolRun` for the
`doc_drift` tool. The report aggregates a/b/c1/c2/c3/d findings plus the
two boolean flags `bidirectional_closure_ok` and `translation_ok`.

## Pipeline

```
classify_repo(repo_root):
    code_index = build_code_symbol_index(repo_root)
        # griffe.GriffeLoader(search_paths=[repo_root/"src"])
        # walks every importable module under src/scieasy/; returns
        #   {dotted_path: griffe.Object}.

    adr_frontmatters = []
    for path in repo_root.glob("docs/adr/ADR-*.md"):
        fm = parse_frontmatter(path)
        if fm.status == Status.ACCEPTED:
            adr_frontmatters.append(fm)

    doc_cited = build_doc_cited_symbols(adr_frontmatters)
        # union of every Accepted ADR's governs.contracts list.

    findings = []

    # ── Forward pass ───────────────────────────────────────────────
    for adr in adr_frontmatters:
        for symbol in adr.governs.contracts:
            if symbol in code_index:
                if not signatures_match(symbol, code_index[symbol]):
                    findings.append(b_class_finding(symbol, adr))
                # else: a-class (silent; per ADR §7.2 only emit on disagreement)
            else:
                evidence = git_history_for_symbol(symbol, repo_root)
                findings.append(c_class_finding(symbol, adr, evidence))

    # ── Reverse pass ───────────────────────────────────────────────
    for dotted_path, obj in code_index.items():
        if not is_public(obj):
            continue
        if obj.is_class and dotted_path not in doc_cited:
            findings.append(d_class_orphan_class(dotted_path))
        if obj.is_function and not obj.docstring:
            findings.append(d_class_missing_docstring(dotted_path))

    # ── Bidirectional closure (delegated) ─────────────────────────
    closure_findings = closure.check_bidirectional(repo_root)
    findings.extend(closure_findings)

    # ── Translation freshness (delegated; Phase 1D ships full impl) ─
    translation_ok = check_translation_freshness(repo_root)

    return assemble_audit_report(findings, closure_findings, translation_ok)
```

## c-class disambiguation (§9.3)

```
git_history_for_symbol(symbol, repo_root):
    deleting_commit = git_log_pickaxe(symbol)  # `git log -S`
    if deleting_commit:
        return Evidence(was_present_then_deleted=True,
                        deleting_commit_sha=deleting_commit.sha,
                        deleting_commit_author=deleting_commit.author)
    else:
        return Evidence(never_existed=True)

# C1: was present then deleted
# C2: never existed (likely doc hallucination)
# C3: mixed evidence (e.g. dotted path matched a different symbol kind)
```

## b-class signature matching (§9.5)

```
signatures_match(symbol_path, griffe_obj) -> bool:
    # Compare four attributes:
    #   1. parameter names (positional + keyword, in order)
    #   2. parameter type annotations
    #   3. return type annotation
    #   4. raised exceptions (from Raises: docstring section)
```

The matcher returns `False` plus the disagreeing attribute name; the
caller surfaces that in the b-class finding's `message`.

## d-class scope (§9.4)

* Every public **class** must be in some Accepted ADR's `governs.contracts`
  OR a member of a module in `governs.modules`. Otherwise →
  `rule_id="doc-drift.orphan-class"`.
* Every public **function/method** must carry a Google-style docstring.
  Otherwise → `rule_id="doc-drift.missing-docstring"`.
* "Public" = listed in `__all__` if `__all__` is present, else
  not-leading-underscore.

## Phase-1 notes

* Missing `__all__` is reported as a `warning` finding during Phase 1
  (manager default; promoted to `error` from Phase 2 onwards).
* `signatures_match` falls back to a best-effort string compare when
  griffe cannot statically resolve a parameter annotation.
* The `closure` and translation passes return their own findings; the
  doc-drift report includes them so a single `AuditReport` covers the
  full forward+reverse+closure picture (consumers can filter by
  `tool` if they only want one sub-tool's view).
