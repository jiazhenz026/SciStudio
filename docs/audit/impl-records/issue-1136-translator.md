---
title: "Phase 1D sub-PR 1 — TC-1D.9 translator implementation record"
phase: 1
tc: 1D.9
status: implemented
date: 2026-05-18
issue: 1143
parent_issue: 1136
umbrella: 1113
branch: feat/issue-1143/tc-1d-9-translator
tracking_branch: track/adr-042/1d-docs-translator
session: 20260518-061854-tc-1d-9-translator-sub-pr-1-of-issue-113
agent: claude
adr_refs:
  - ADR-042 §22 (Documentation Language Policy + Translator)
  - ADR-042 §22.3 (CLI shape)
  - ADR-042 §22.4 (Default provider DeepL + pluggable Google/Azure/Manual)
  - ADR-042 §22.5 (`pydantic-settings` env-var loader, `SCIEASY_TRANSLATION_` prefix)
  - ADR-042 §22.6 (Incremental translation via `source_sha`)
  - ADR-042 §22.7 (Translation workflow CI with three-tier path-allowlist + PR-creating commit)
agent_editable: true
---

# Phase 1D sub-PR 1 — TC-1D.9 translator implementation record

## Scope delivered

Per the [DISPATCH-TEMPLATE-V1: implement] message dated 2026-05-18 and the
investigation summary at `docs/planning/phase-1-investigation/SUMMARY.md`,
this sub-PR ships **only** the translator slice of Phase 1D (sub-PR 1 of
four). Sub-PRs 2–4 (Sphinx config / catalog directives / generators +
doc skeletons) depend on Phase 1A schemas (not yet merged) and follow in
subsequent PRs.

## Files added

| Path | Lines (approx.) | Purpose |
|---|---|---|
| `src/scieasy/qa/__init__.py` | 19 | Namespace package init |
| `src/scieasy/qa/translation/__init__.py` | 56 | Public re-exports |
| `src/scieasy/qa/translation/client.py` | 644 | `TranslatorClient` + 4 providers + mask/unmask + file helpers |
| `src/scieasy/qa/translation/settings.py` | 77 | `TranslationSettings` (pydantic-settings) |
| `scripts/translate_docs.py` | 184 | CLI per ADR-042 §22.3 |
| `.github/workflows/translation.yml` | 93 | Auto-translate workflow per ADR-042 §22.7 |
| `tests/qa/__init__.py` | 1 | Test package init |
| `tests/qa/test_translation_settings.py` | 105 | Env-var loading, defaults, key-redaction |
| `tests/qa/test_translation_client.py` | 380 | Mask/unmask, helpers, facade |
| `tests/qa/test_translation_providers.py` | 248 | DeepL/Azure/Google/Manual via `httpx.MockTransport` |
| `tests/qa/test_translate_docs.py` | 200 | CLI end-to-end (manual provider only) |
| `docs/zh-CN/adr/ADR-042.md` | (generated) | Manual-provider stub deliverable |
| `docs/zh-CN/adr/ADR-043.md` | (generated) | Manual-provider stub deliverable |
| `docs/zh-CN/adr/ADR-044.md` | (generated) | Manual-provider stub deliverable |

## Files modified

| Path | Change |
|---|---|
| `pyproject.toml` | Add `pydantic-settings>=2.5` to `[project] dependencies` |
| `CHANGELOG.md` | Add `[#1143][#1136]` entry under `[Unreleased] / Added` |

## Implementation rationale

### Why a self-contained translator package (no schema imports)

Per ADR-042 §22.3, the translator imports
`scieasy.qa.translation.{TranslatorClient, DeepLProvider,
GoogleProvider, AzureProvider}` and `scieasy.qa.translation.settings.
TranslationSettings`. It does **not** import from
`scieasy.qa.schemas.*` or `scieasy.qa.docs.schemas.*`. This means
sub-PR 1 is dependency-free with respect to Phase 1A schemas — even
though the dispatch template claimed those schemas were merged on
main, repo inspection shows they are not. The translator code can
ship today without blocking on 1A.

The future `Translation` schema (ADR-044 §5, owned by TC-1A.10) lives
in `scieasy.qa.docs.schemas` and is consumed by `closure.
check_bidirectional` (TC-1B.4 doc extensions); it does NOT live inside
the translator. When 1A.10 lands, the `complete_artifacts.check` audit
tool (TC-1B.7) will validate that every English source doc has a
matching `docs/zh-CN/X.md` with `source_sha` matching `file_sha(src)`.

### Placeholder masking design

The locked translation rule (DO NOT translate code, frontmatter, links,
tech IDs, etc.) is enforced by `mask_non_translatable`:

1. Markdown links/images run first with a callback-based substitution
   so `[text](url)` becomes `[text](<x id=N/>)` — preserving the
   visible text for translation while freezing the URL.
2. Eight ordered regex passes mask code fences, frontmatter, HTML
   tags (with a negative lookahead `(?!x )` that excludes our own
   placeholder shape — found via a self-overlap bug during testing
   where the html-tag pattern double-masked the code-fence
   placeholders), inline code, technical IDs (`ADR-NNN`, `TC-X.Y`,
   `§N.M`, `#NNNN`, etc.), 3+ segment dotted Python paths, and POSIX
   file paths.
3. DeepL receives the masked text with `tag_handling=xml` +
   `ignore_tags=code,pre,kbd,samp,x` as defence-in-depth, so even
   if our regex misses a token class the engine preserves the body
   of those tags verbatim.
4. `unmask` uses a relaxed regex (`<x [^>]*?id="(\d+)"[^>]*?/?>`,
   case-insensitive) to tolerate providers that strip the
   `data-kind` attribute or change case. Unknown placeholder ids
   from the provider are passed through rather than raising.

### Why three HTTP providers without third-party SDKs

DeepL, Google, and Azure all expose REST APIs that take JSON or
form-encoded payloads. To keep the dep footprint minimal we use
`httpx` (already a project dep) directly. The Google provider
optionally delegates to `google-auth` for OAuth2 token fetching when
it's installed; otherwise it raises with a clear pointer. This
matches ADR-042 §22.4's "pluggable providers" intent without pulling
in `deepl`/`google-cloud-translate`/`azure-ai-translation-text` SDK
deps for the default path.

### Why the workflow opens a PR instead of pushing directly

ADR-042 §22.7 specifies PR-creating behaviour because (1) `main` has
branch protection that rejects direct pushes, and (2) pushes
authenticated with `GITHUB_TOKEN` do **not** trigger downstream
workflows — meaning a direct-pushed translation refresh would skip
CI on the translation commit. The PR flow keeps CI on every
translation pass.

The three-tier path-allowlist enforcement (unstaged + staged +
untracked) is per ADR-042 §22.7's audit P0.2 fix; pure
`git diff --name-only HEAD~1` misses newly-introduced files.

## Deviations from investigation summary

The Phase 1 investigation summary did not produce a per-TC report
for 1D.9 (per the SUMMARY.md "dispatch-mode note" — investigation
agents were dispatched as `Plan` not `general-purpose` and could
not persist per-TC files). This impl record fills the gap.

Deviations from the ADR text:

1. **Google provider implementation depth**: ADR-042 §22.4 names
   Google as a pluggable provider but gives no implementation
   detail. I implemented an OAuth2 path that *requires* `google-auth`
   (clear error otherwise) and uses the v2 REST endpoint
   (`https://translation.googleapis.com/language/translate/v2`)
   rather than the v3 gRPC API to avoid the
   `google-cloud-translate` dep tree. Documented as `TODO(#1136):`
   in `client.py:_fetch_access_token`. Owner can deepen if Google
   becomes a routine CI provider.

2. **DeepL language code normalisation**: DeepL Free rejects
   `ZH-HANS` (Pro-only); accepts `ZH`. I normalise via
   `_normalise_deepl_lang` so `zh-CN`/`zh-Hans`/`zh` all map to
   `ZH`. ADR is silent on this; the deviation is a correctness
   fix, not a contract change.

3. **CLI `--dry-run` flag**: ADR-042 §22.3 sample does not include
   `--dry-run`; I added it because it's an obvious affordance for
   developers verifying what would change before running a billable
   provider. Standard CLI ergonomics.

4. **Manual-provider stub marker**: ADR-042 §22.5 says the manual
   provider emits a stub "marked `needs-manual`". I implemented this
   as `translation_status: needs-manual` injected into the
   frontmatter (or as an HTML comment when there's no frontmatter).
   The exact field name is unspecified in the ADR.

5. **`_ensure_source_sha` indentation handling**: a real ADR (e.g.
   ADR-043) carries an indented `source_sha:` field deep inside
   its own `translations:` list (per ADR-042 §22.6 tracking). The
   regex used for injection is line-anchored so it only matches
   the top-level `^source_sha:` line, leaving the indented
   occurrence untouched. Verified live against ADR-042/043/044.

## Tests added

76 tests across four files. All pass with `pytest --timeout=60`
in 0.65 s.

- `test_translation_settings.py` (9 tests): defaults; DeepL/manual/
  Azure env loading; extra-env tolerance; invalid-provider raises;
  `require_deepl_key` happy + missing; credential redaction in
  `repr()`.
- `test_translation_client.py` (29 tests): mask/unmask round-trip
  across all 8 token classes (code-fence, inline-code, frontmatter,
  link, image, link-with-title, tech-id, dotted-path, file-path,
  html-tag); unmask tolerates attribute reordering and unknown
  placeholder ids; `diagnose_text`; `file_sha` stability;
  `_ensure_source_sha`/`_annotate_manual_stub` with/without
  frontmatter + idempotence; `translation_is_up_to_date`
  missing/match/mismatch; `walk_pairs` file+dir+target-skip+
  suffix-filter; `TranslatorClient` provider dispatch + invalid
  name; language normalisers for all three providers.
- `test_translation_providers.py` (16 tests): Manual identity;
  DeepL happy/header/empty-translations/HTTP-error/missing-key/
  XML-tag-handling-sent; Azure happy/region-header/missing-key/
  missing-endpoint/empty-response; Google missing-credentials/
  HTTP-path-with-mocked-token/empty-response.
- `test_translate_docs.py` (7 tests): single-file translation;
  directory recursion; `--incremental` skip + re-translate; `--dry-run`
  writes nothing; missing source → exit 2; empty dir → exit 0.

## Coverage

- `src/scieasy/qa/translation/client.py`: **96%** (228 stmts, 9 missing).
  Missing lines are inside the Google `_fetch_access_token` real-OAuth
  path (TODO-tagged) and two `# pragma: no cover` branches.
- `src/scieasy/qa/translation/settings.py`: **100%**.
- Aggregate translator coverage: **96.5%** — exceeds the ≥95% gate
  per ADR-042 §21.6 for new QA code.

## Known TODOs left in code

```python
# src/scieasy/qa/translation/client.py:_fetch_access_token
# TODO(#1136): light Google integration — uses ``google-auth``
# if installed, else raises with a pointer to the optional dep.
# Out of scope for ADR-042 §22.4 (default provider is DeepL).
# Followup: open a dedicated issue if Google becomes a routine
# CI provider.
```

## Quality gates

| Gate | Result |
|---|---|
| `ruff check src/scieasy/qa/ scripts/translate_docs.py tests/qa/` | Clean |
| `ruff format --check ...` | Clean |
| `mypy src/scieasy/qa/translation/ scripts/translate_docs.py` | No issues |
| `pytest tests/qa/ --timeout=60` | 76 passed |
| Coverage (translator only) | 96.5% |
| `python scripts/audit/temp_review.py` | 0 findings |
| Manual-provider CLI smoke (ADR-042/043/044) | 3/3 stubs produced |

## Out of scope (handled in subsequent sub-PRs / cascade phases)

- Sphinx `conf.py`, deps additions, `consolidate_cascade.py` — **Sub-PR 2**.
- `ScieasyBlockCatalog` / `ScieasyRunnerCatalog` / `ScieasyAIBlockCatalog`
  directives — **Sub-PR 3**.
- 5 generators (`llms_txt`, `entry_point_catalog`, `cli_reference`,
  `openapi_reference`, `schema_reference`) + ~40 doc skeletons —
  **Sub-PR 4**.
- `Translation` schema (lives in `scieasy.qa.docs.schemas` per 1A.10) —
  blocks on Phase 1A merge; the translator itself does not import it.
- `complete_artifacts.check()` consumption of `source_sha` for
  audit reporting — blocks on TC-1B.7.
- Closure-check coverage of zh-CN outputs — blocks on TC-1B.4 ext.

## Deliverable validation

Per the dispatch's Definition of Done:

- `python scripts/translate_docs.py --provider=manual --source docs/adr/ADR-042.md --target docs/zh-CN/adr/`
  produces `docs/zh-CN/adr/ADR-042.md` (no network).
- `--provider=deepl` path is mock-tested (`test_deepl_provider_happy_path`,
  `test_deepl_provider_sends_xml_tag_handling`,
  `test_deepl_provider_authorization_header`); will run against the
  real DeepL endpoint on first CI run after merge once
  `SCIEASY_TRANSLATION_DEEPL_API_KEY` is wired in GitHub Secrets.
- The three deliverable stubs at `docs/zh-CN/adr/ADR-04{2,3,4}.md`
  carry `translation_status: needs-manual` + top-level
  `source_sha: <16-hex>`; DeepL re-translates them automatically on
  first push to main post-merge.
