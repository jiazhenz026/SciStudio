# [DISPATCH-TEMPLATE-V1: skeleton]

> Use for S35 / S36 (Phase 1 skeleton scaffolding).
> Read `00-common-boilerplate.md` first — every rule there applies.

## Role-specific rules — Skeleton

You are creating the **scaffolding** for an ADR. Your job is to make sure every file the implementation phase will need exists, with the right signatures, and with **detailed comments telling the next agent what to build and how to test it**.

**Hard rules unique to this role:**

1. **NO real logic.** Every function/method body is `raise NotImplementedError("see comment block above")` (Python) or `throw new Error("not implemented — see comment above")` (TypeScript) — except for trivial type definitions / dataclass declarations / pure scaffolding constants.

2. **Every NotImplementedError is preceded by a docstring + structured implementation-plan comment** with:
   - **Purpose**: 1 sentence, what this function does
   - **Signature contract**: arg types, return type, raised exceptions, error envelopes
   - **Implementation steps**: numbered list, the algorithm in pseudocode
   - **Edge cases**: list of "what if X happens" with the answer
   - **Test plan**: list of test cases the implementation phase MUST add (positive, negative, edge)
   - **References**: ADR section numbers + line ranges of any existing code being mirrored

   Example shape:
   ```python
   def write_manifest(self, path: Path, inputs: list[InputPort], outputs: list[OutputPort]) -> None:
       """Write the AI Block manifest.json.

       Implementation plan (per ADR-035 §3.4):
         1. Build the dict shape shown in §3.4 of ADR-035
         2. Resolve each input's storage_ref to absolute path
         3. Write atomically (tempfile + rename)

       Edge cases:
         - input is in memory only (no storage_ref): materialize first via `to_memory()`
         - output port has no expected_path: default to ./{block_name}_outputs/{port}.{ext}

       Test plan:
         - test_write_manifest_basic: 1 input, 1 output, verify JSON shape matches ADR §3.4
         - test_write_manifest_atomic: kill mid-write, file remains old or new (never partial)
         - test_write_manifest_inmemory_input: triggers materialization

       References: ADR-035 §3.4, src/scieasy/blocks/app/bridge.py:31-142 (similar pattern)
       """
       raise NotImplementedError("see comment block above")
   ```

3. **Tests are also stubs.** Create test files with the test-case skeletons described in your test plan, marked `@pytest.mark.xfail(reason="skeleton — implementation phase fills in")` or `it.skip("skeleton")` for vitest. Each test docstring contains the test plan.

4. **No new dependencies in skeleton phase** unless they are listed in the dispatch as required for skeleton (typically just listing in `package.json` for frontend without installing). Document any required dep in PR body.

5. **Skeleton must build** — `pytest --collect-only` runs without errors; `npm run build` (or `tsc --noEmit`) passes; `ruff check` passes; `mypy` passes. xfail tests are fine.

6. **Skeleton coverage matches the checklist exactly** — for every box under your "Skeleton (S##)" section, there is a corresponding stub file or stub function. Tick boxes as you go (with `→ <commit-sha>` artifact).

## PR body template — Skeleton

```markdown
Closes #<issue>

## Skeleton scope

This is the **Phase 1 skeleton** for ADR-0<35|36>. No real logic — all
function bodies raise NotImplementedError with detailed implementation
plans + test plans in the preceding comments. Implementation phase
agents will fill them in.

## Files added / modified

- <list of paths>

## Comment-block coverage

Every NotImplementedError has a preceding docstring with: Purpose,
Signature contract, Implementation steps, Edge cases, Test plan,
References. Implementation agents should be able to start coding
without re-reading the ADR.

## Test stubs

- <list of test files added>

All tests are xfail (Python) or skip (vitest) with the test plan in
the docstring.

## Checklist updates

Ticked rows in `docs/planning/adr-035-036-checklist.md` under
`Skeleton (S##)`:
- <bullet list with → commit-sha for each>

## CI status

[ ] All CI checks green (filled in after PR opens + checks complete)
```

## Task content (filled in by dispatcher)

(below this line is task-specific)

---
