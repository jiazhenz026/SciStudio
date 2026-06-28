# Audit — Docstring quality of the public block API surface (no-context, #1845)

- Date: 2026-06-28
- Persona: audit_reviewer (independent, no-context)
- Branch / worktree: `audit/1845-1` @ `/Users/jiazhenz/scistudio-wt-1845-audit1`
- Standard judged against: `docs/contributing/docstring-style.md`
- Scope (read-only): `src/scistudio/blocks/**` — base, process, io, app, subworkflow,
  code, ai, registry.

## 1. Scope and method

I audited the **public** block surface: names in each module's `__all__` (non-underscore)
plus non-underscore `@stable` / `@provisional` classes/functions/methods. I ignored
`_`-prefixed members and members explicitly marked `Internal (...)`. Per the standard I
checked: (1) no internal project-record citations in user-facing prose; (2) summary +
plain-language purpose + contract (+ Example where it helps); (3) Example accuracy;
(4) public attributes/ClassVars/properties carry attribute docstrings so they render;
(5) bench-scientist readability; (6) changes look docstring/comment-only.

Method:
- Grepped the full citation family (`ADR/FR/DSN/SC/OQ/ECA/OBS/BCP/AC/TRK/BUG-NNN`,
  `Addendum N`, `Tier N`, `ADR-NNN D7`, bare `#NNNN`) across `blocks/**`, then read every
  hit to separate `#` comments (allowed) and private/internal members (out of scope) from
  PUBLIC docstrings and user-facing string values.
- Read every public symbol in all eight subtrees (parallelized, then verified the
  load-bearing findings myself by reading the exact lines).
- Inspected the **generated** reference under `docs/user/reference/*.md` to confirm what
  actually renders to users, and grepped those pages for citation leaks.
- Ran `python -m doctest` over the non-underscore block files to spot-check Examples.

Key structural fact I verified: the published reference roots are
`blocks.base`, `blocks.app`, `blocks.code`, `blocks.io`, `blocks.process` (plus
`core.*` / `previewers.*`). **`blocks.registry`, `blocks.subworkflow`, and `blocks.ai`
are NOT rendered reference roots.** Citations in those three subtrees therefore do not
leak into the published API reference, but block `description` / config-form text in
`subworkflow` and `ai` is still shown to users in the product UI (palette + config form),
which the standard's §2.1 ("a docstring **and any prose a user reads**") covers.

## 2. Headline result

The rendered public reference (base/app/code/io/process) is in **strong** shape:
summary + purpose + contract present, attribute docstrings on essentially every public
ClassVar/dataclass-field/property, and **zero** internal-record citations leaked into the
generated `.md` pages (the only citation-family hits in `docs/user/reference/*.md` are the
generator's own boilerplate header/footer and an `#1817` follow-up note in `index.md`,
emitted by `scripts/docs/build_reference.py` — outside the blocks docstring surface).

The residual problems are concentrated in (a) ADR citations in **user-facing block UI
strings** (subworkflow palette descriptions, AI permission help), (b) ADR citations in
**user-facing runtime/validation messages** (code), (c) one real docstring-prose citation
in a private, non-rendered registry helper, and (d) one broken Example.

## 3. Findings by severity

### P1 — must fix before merge

**P1-1 — `subworkflow_block.py:45`: internal record in the block's palette description.**
```python
description: ClassVar[str] = "Reference a workflow file as a single authoring-time node (ADR-044)"
```
This string is the one-line description shown to the user in the block palette (its own
attribute docstring at line 46 says so). A bench scientist literally reads "(ADR-044)".
Drop the citation; keep the behavior text. (Standard §2.1.)

**P1-2 — `subworkflow_block.py:176`: internal record in the block's palette description.**
```python
description: ClassVar[str] = "Unresolved subworkflow reference marker (ADR-044 §10)"
```
Same issue for `SubWorkflowBroken`. Remove "(ADR-044 §10)".

**P1-3 — `ai_block.py:240`: internal record + opaque jargon in a config-form help string.**
Inside `AIBlock.config_schema`, the `permission_mode` field description (rendered in the
block's config form):
```python
"Bypass = full filesystem access — same as a hand-launched ADR-034 tab."
```
`AIBlock` is public (`ai/__init__.py __all__`). "ADR-034 tab" is both a record citation and
meaningless to the target user. Reword to plain language (e.g. "…same as launching the
agent in a terminal yourself"). (The `# ... ADR-034 ...` comment at lines 231-234 is a `#`
comment and may stay.)

### P2 — quality / correctness, should fix

**P2-1 — `registry/_capability.py:396`: ADR citation in a PUBLIC function docstring prose.**
```python
def list_format_capabilities(...):
    """List registered ADR-043 IO format capabilities matching filters."""
```
`list_format_capabilities` is a non-underscore name in `_capability.py`'s `__all__`, so it
is public by the letter of the rule. Mitigation (why P2, not P1): the module is private
(`_capability.py`), `blocks.registry` is **not** a rendered reference root (verified absent
from `docs/user/reference/`), and the user-facing surface is the `BlockRegistry.list_format_capabilities`
method (`registry/__init__.py:584`), whose docstring is clean and fully shaped. Still a real
§2.1 docstring-prose hit — remove "ADR-043" (write "registered IO format capabilities …").

**P2-2 — `code/config.py:336`: ADR citation surfaced in a user-facing validation message.**
```python
suggested_target="Adapt the script to ADR-041 file exchange or keep the logic in a ProcessBlock."
```
Produced by `legacy_migration_diagnostics` (Internal-marked) but the value is folded into a
PUBLIC `CodeBlockValidationDiagnostic` message at `validation.py:208`
(`message=f"{diagnostic.message} Suggested target: {diagnostic.suggested_target}"`) and
rendered to the workflow editor via `CodeBlockValidationDiagnostic.render()`. A user editing
a legacy CodeBlock config sees "ADR-041 file exchange". Reword (e.g. "Adapt the script to use
typed file-exchange ports …"). Not a docstring, so P2.

**P2-3 — `code/code_block.py:492`: ADR citation in a diagnostic reachable via a public attribute.**
```python
suggested_target="Remove legacy runner fields and use ADR-041 file exchange."
```
Reachable through the documented public attribute `CodeBlockMigrationError.diagnostics`
(`code_block.py:110-111`, "each with a suggested fix"). Same reword as P2-2. (The exception
*message* values at lines 488-491 are clean.)

**P2-4 — `code/interpreters.py:114`: internal taxonomy jargon in a user-facing error.**
```python
f"CodeBlock v2 Track A supports .py scripts only; got {...}"
```
Raised as the public `UnsupportedScriptExtensionError`. "Track A" is internal project
terminology a bench scientist will not understand. Drop "Track A" (keep "CodeBlock supports
.py scripts only").

**P2-5 — `subworkflow_block.py:156-158`: ADR citation in a raised error message.**
```python
"SubWorkflowBlock is authoring-only (ADR-044); it must be inline-flattened before scheduler dispatch and must never reach run()."
```
A defensive "should never happen" `RuntimeError`, so low exposure, but it is user-readable
prose with a record citation. Reword without "(ADR-044)".

**P2-6 — `app/bridge.py:93`: broken Example (won't run as written).**
`FileExchangeBridge` is a public reference symbol; its `Example:` is executed by doctest and
fails:
```python
>>> bridge.prepare({"image": some_array}, Path("/tmp/exchange"))   # NameError: some_array
>>> proc = bridge.launch("/Applications/Fiji.app", Path("/tmp/exchange"))  # spawns a real process
```
`some_array` is an undefined placeholder, so a reader copying the snippet hits `NameError`
before anything else. Make it self-contained or mark it `# doctest: +SKIP`. (The task lists
broken examples as a possible P1; ranked P2 here because it is clearly illustrative
pseudo-code on a provisional class.)

**P2-7 — `code/config.py` doc-accuracy: fields documented as live but inert on the run path.**
- `timeout_seconds` (docstring line 171) and `working_directory` (line 161) are documented as
  effective settings, but `CodeBlock.run` strips them
  (`code_block.py:476` `dropped = runtime_only | {"timeout_seconds", "working_directory"}`),
  forcing defaults. A user reading the public `CodeBlockConfig` believes they can set these
  through the block.
- `exchange_directory_policy` (docstring lines 172-173) is documented but never consumed
  anywhere in `blocks/code/**` (grep-confirmed) — documents a setting with no observable
  effect.
  Either align the docstrings with actual behavior or note the limitation. (If this is
  intentional runtime-only stripping, say so in the field docstring.)

### P3 — nits / observations

- **`base/ports.py:22-26`** — the five inherited `Port` dataclass fields (`name`,
  `accepted_types`, `is_collection`, `description`, `required`) carry no attribute docstring.
  `Port` is correctly `Internal`, and the public `InputPort` (line 31) / `OutputPort`
  (line 66) docstrings enumerate these fields in prose bullet lists, so the contract is
  conveyed. With `show_if_no_docstring` off they would not render as per-field entries, but
  the prose mitigates it; low priority. (`InputPort`'s own added fields `default`,
  `constraint`, `constraint_description` do carry attribute docstrings.)
- **`io/capabilities.py:39-40`** — `VALID_CAPABILITY_DIRECTIONS` / `VALID_METADATA_FIDELITY_LEVELS`
  are non-underscore module constants with no docstring, not `@stable`, no `__all__`, and (unlike
  the two documented type-aliases above them) no "public" comment; only used internally. Likely
  out of scope; if intended public, add attribute docstrings.
- **`io/capabilities.py:117-129`** — `normalize_extensions` (plural) is non-underscore,
  undecorated, not in `__all__`, and not marked `Internal` (its singular sibling at line 96 is
  `Internal`). One-line docstring only. Either mark it private or give it a full contract.
- **`ai_block.py:147`** — `AIBlock.description` value uses "PTY tab" jargon
  ("Spawn a claude/codex agent in a PTY tab …"); no citation, but "PTY" is opaque to a bench
  scientist. The class docstring uses the friendlier "terminal tab" — align the description.
- **`io/loaders/load_data.py:104-107` and `io/savers/save_data.py:341`** — `LoadData` /
  `SaveData` palette descriptions surface code identifiers ("DataObject", "core_type") in
  user-visible strings. No record citation, so not a §2.1 violation, but a readability nit.
- **`code/*` pydantic models** — `model_config = ConfigDict(extra="forbid")` ClassVar on the
  six public models (`PortFileConfig`, `CodeBlockConfig`, `ResolvedInterpreter`,
  `ScriptProvenance`, `EnvironmentSnapshot`, `CodeBlockProvenancePayload`) has no attribute
  docstring. It is pydantic plumbing, not a user data field; almost certainly acceptable.
- **`registry/_capability.py:440, 459`** — `find_loader_capability` / `find_saver_capability`
  are public-by-`__all__` but one-line summaries with no Args/Returns. As with P2-1 the
  user-facing surface is the fully-documented `BlockRegistry` method wrappers
  (`registry/__init__.py:625, 672`), so impact is low.
- **`process/builtins/data_router.py`, `pair_editor.py`** — interactive blocks have no code
  `Example:`; defensible for interactive/UI blocks.
- **Doctest side effects (observation):** several app/io `Example:` blocks contain live,
  side-effecting calls (subprocess launch, blocking `FileWatcher.wait_for_output`) without
  `# doctest: +SKIP`, so `python -m doctest` over those modules executes/blocks. Acceptable
  for inherently side-effecting provisional blocks, but worth a `+SKIP` for hygiene.
- **Out-of-scope observation (not a blocks finding):** the generated reference `index.md`
  (lines 5, 7, 15) and per-page stability footers contain "ADR-052 §7 / §8.1" and an "#1817"
  follow-up note. These are emitted by `scripts/docs/build_reference.py` (outside the
  `blocks/**` docstring surface), so they are not part of this audit, but they are
  user-facing reference prose and the owner may want them de-jargoned separately.

## 4. Docstring-only check

The changes I inspected read as docstring / attribute-docstring / comment content. I saw no
behavior-changing edits in the public symbols I read. One latent doc/behavior mismatch is
noted (P2-7) but it is a pre-existing accuracy gap, not a behavior change introduced here.

## 5. Per-module pass/fail

| Module | Result | Notes |
| --- | --- | --- |
| `base` | PASS | Clean, fully shaped; all public ClassVars/properties documented. Minor: inherited `Port` fields lack attr docstrings (P3, mitigated by prose); `Block.dynamic_ports` dense. |
| `process` (+ builtins) | PASS | Clean across `ProcessBlock` and all five builtin blocks; descriptions citation-free; attributes documented. |
| `io` | PASS | Rendered surface clean and shaped; only P3 borderline constants/helpers + "DataObject/core_type" readability. |
| `app` | PASS-WITH-FIXES | P2-6 broken `FileExchangeBridge` example; `ExternalAppBridge` protocol method stubs are one-liners (minor). Otherwise clean + documented. |
| `subworkflow` | PASS-WITH-FIXES | P1-1, P1-2 (ADR-044 in palette descriptions), P2-5 (ADR-044 in raised message). Docstrings/attributes otherwise fine. |
| `code` | PASS-WITH-FIXES | P2-2/P2-3 (ADR-041 in user-facing diagnostics), P2-4 ("Track A" jargon), P2-7 (doc accuracy). Docstring shape + attribute coverage otherwise excellent. |
| `ai` | PASS-WITH-FIXES | P1-3 (ADR-034 in permission help), P3 ("PTY" jargon). `AIBlock` docstring + ClassVars otherwise strong. |
| `registry` | PASS-WITH-FIXES | P2-1 (ADR-043 in `list_format_capabilities` docstring, non-rendered); thin standalone capability funcs. `BlockRegistry`/`BlockSpec` (34 documented fields) and error classes are clean. |

## 6. Overall recommendation

**pass-with-fixes.**

The published reference surface (base/app/code/io/process) is citation-clean, well-shaped,
and has full attribute-docstring coverage — a genuinely good result. Before merge, fix the
three P1 user-facing de-jargon items (subworkflow palette descriptions ×2, AI permission
help) and ideally the broken `FileExchangeBridge` example (P2-6); the remaining P2 items
(ADR citations in code diagnostics, the registry helper docstring, the "Track A" jargon, and
the CodeBlock config doc-accuracy gap) are quality follow-ups that do not affect the rendered
reference. No issue rises to **block**.
