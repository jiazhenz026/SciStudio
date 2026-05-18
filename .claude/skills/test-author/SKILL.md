---
name: test-author
description: Write meaningful tests that assert observable behavior, not exercise code
allowed-tools: [Read, Write, Edit, Bash]
metadata:
  priority: P0
  source_adr: ADR-043
  source_section: "§4.4"
---

# test-author

When asked to write tests, you MUST follow this protocol in order:

1. **Identify the contract.** What observable behavior is being tested?
   Articulate it in one sentence before writing any test code.

2. **Write the assertion first.**

   ```python
   def test_normalize_returns_lowercase():
       result = normalize("AbC")
       assert result == "abc"     # write THIS first
   ```

3. **Run pytest.** Confirm the test FAILS with the expected error type and
   message.

4. **Write the minimum implementation** to make the test pass.

5. **Run pytest again.** Confirm the test PASSES — and verify it's passing
   for the right reason (the assertion you wrote, not a coincidence).

6. **Add edge cases** by repeating 2–5 for each.

7. **Add a property test** with `hypothesis` for the function's invariants
   (e.g., `normalize(normalize(s)) == normalize(s)`).

## Forbidden patterns

The following are AST-flagged as errors by
`src/scieasy/qa/test_quality/ast_lint.py` (rule-IDs in the `TQAST-` namespace):

- `assert response is not None` (too weak — what should `response` BE?)
- `mock.assert_called_once()` alone (only verifies invocation, not result)
- `def test_X(): foo()` (no assertion at all)
- Mocking the function or class under test
- Hardcoded magic numbers without a comment explaining significance
- Snapshot tests without one-line reasoning

The full anti-pattern list is in ADR-043 §4.2.1 and the rule
implementations live in `src/scieasy/qa/test_quality/ast_lint.py`.

## When uncertain, prefer no edit with explanation.

If you cannot identify a meaningful assertion for some behavior, do not
write a placeholder test. Add a `TODO(#NNN)` and a one-line note explaining
what assertion is missing and why.

## Mutation score targets (ADR-043 §4.5)

After authoring a test, your mutation score for the touched module must
meet the §4.5 table:

| Path | Target |
|---|---|
| `src/scieasy/qa/**` | ≥ 0.90 |
| `src/scieasy/core/**` | ≥ 0.85 |
| `src/scieasy/{blocks,engine,api,workflow}/**` | ≥ 0.75 |
| `src/scieasy/ai/**` | ≥ 0.70 |

Run locally on Linux/macOS:

```bash
python -m scripts.audit.mutation_runner \\
    --modules src/scieasy/qa/test_quality \\
    --baseline docs/audit/baselines/mutation.json
```

Windows users: mutation testing requires `os.fork()` and must run inside
WSL. The CI Linux runner is authoritative; local Windows runs are skipped
with an INFO-level `TQMUT-unavailable-platform` finding.

---

<!--
TODO(#1145): This file is the in-repo Claude Code mirror. The canonical
source body lives at `src/scieasy/_skills/qa/test-author/SKILL.md` and the
cross-runtime installer (`agent_provisioning.qa_skills`, shipped by 1H
sub-PR 3) will sync it to all five supported agent runtimes. Until 1H
sub-PR 3 lands, this manually-written mirror is the only operational
copy. Followup: 1H sub-PR 3 dispatch (umbrella #1113, phase-lead #1145).
-->
