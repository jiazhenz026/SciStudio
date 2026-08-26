---
spec_id: i18n-framework-zh-cn
title: "Interface And End-User Content Internationalization, With A Simplified Chinese Locale"
status: Draft
feature_branch: guided/2064-i18n-framework-zh-cn
created: 2026-08-25
input: "Owner directive: build an i18n framework and ship a Simplified Chinese build. Locale tag zh-CN. Use an i18n library rather than an in-house catalog. Translation keys are the English source strings. Error messages and logs stay English and are never translated. Translate end-user-facing content only. Translations are produced by DeepL plus a committed glossary and human review, never authored by an AI agent. Traditional Chinese is deferred."
owners:
  - "@jiazhenz026"
related_adrs:
  - 37
  - 52
  - 53
related_specs: []
scope:
  in:
    - Frontend i18n runtime, locale resolution, persisted language switch.
    - Frontend UI string extraction into locale catalogs keyed by English source text.
    - Electron shell user-facing strings (menus, OTA dialogs, failure prompts).
    - Built-in block and data-type display name/description localization contract.
    - Tutorial manifest copy (title, summary, step titles, step beats).
    - Hand-written in-project user guide prose under src/scistudio/_user_guide/.
    - A committed, reproducible DeepL-plus-glossary translation pipeline with human review.
    - CJK input and rendering correctness (IME composition guard, font fallback, terminal wide-character width).
    - Migration of frontend tests off English display copy.
  out:
    - Traditional Chinese (zh-Hant / zh-TW / zh-HK). Deferred by owner decision.
    - Backend API error text (HTTPException detail) and all runtime exception and log messages. They stay English by owner decision.
    - The generated public API reference (src/scistudio/_user_guide/api-reference/**, docs/user/reference/**). Generated docs stay generated and stay English.
    - docs/package-development/** and docs/contributing/**. Developer-facing, not end-user-facing.
    - docs/adr/**, docs/specs/**, docs/planning/**, docs/audit/**, docs/architecture/**, docs/ai-developer/**.
    - Third-party block packages. The localization contract is optional for them.
    - Python docstrings.
governs:
  modules:
    - scistudio.tutorials.manifest
    - scistudio.tutorials.discovery
    - scistudio.agent_provisioning.docs
    - scistudio.api.routes.user_docs
    - scistudio.api.routes.tutorials
    - scistudio.blocks.base.block
  contracts: []
  entry_points: []
  files:
    - frontend/src/**
    - desktop/main.js
    - src/scistudio/tutorials/**
    - src/scistudio/_user_guide/**
    - src/scistudio/blocks/**
  excludes:
    - src/scistudio/_user_guide/api-reference/**
    - docs/user/reference/**
    - docs/package-development/**
    - docs/contributing/**
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - frontend/src/i18n/**
    - frontend/src/locales/**
    - scripts/i18n/**
    - src/scistudio/_user_guide/zh-CN/**
  excludes: []
tests:
  - frontend/src/i18n/__tests__/localeResolution.test.ts
  - frontend/src/i18n/__tests__/catalogIntegrity.test.ts
  - frontend/src/components/__tests__/imeCompositionGuard.test.tsx
  - tests/i18n/test_translation_pipeline.py
  - tests/i18n/test_glossary_postpass.py
  - tests/tutorials/test_locale_overlay.py
  - tests/agent_provisioning/test_docs_locale_provisioning.py
  - tests/blocks/test_block_metadata_i18n.py
acceptance_source: issue
language_source: en
---

# Interface And End-User Content Internationalization, With A Simplified Chinese Locale

## 1. Change Summary

SciStudio has no internationalization infrastructure. There is no i18n library, no
locale catalog, no language switch, and no locale concept anywhere in the frontend,
the Electron shell, the tutorial runtime, or the packaged user guide. Every
user-facing string is hardcoded at its use site: roughly 560 candidate strings
across 156 non-test `.tsx` files (about 28,000 lines) under `frontend/src/`, about
36 `label:` / `title:` / `message:` sites in `desktop/main.js`, 55 `name` /
`description` `ClassVar` declarations under `src/scistudio/`, 1,359 lines of
tutorial manifest copy, and 70,057 characters of hand-written user guide prose.

The users this blocks are bench scientists who write some code but do not read
English fluently. ADR-037 §7 recorded i18n as required-but-deferred at the time
the desktop application was specified; issue #2064 scoped the first pass. This
spec is the design for that pass, narrowed and extended by owner decisions taken
on 2026-08-25.

The change has four parts:

1. **An i18n runtime.** `react-i18next` in the frontend, a locale-resolution
   chain, and a persisted language switch. The catalog key is the English source
   string, so a missing translation renders English rather than a key artifact.
2. **A translation supply chain.** A committed extraction step, a committed
   human-authored glossary, a DeepL translation script, per-entry provenance,
   and human review in the pull request diff. No translation is authored by an
   AI agent.
3. **End-user content localization.** Tutorial copy through a locale overlay
   file, the hand-written user guide through per-locale packaged trees, and
   built-in block/type metadata through an optional mapping on the block
   contract that unlocalized third-party packages inherit safely.
4. **CJK correctness.** Three defects that harm Chinese users today independently
   of translation: Enter submits during IME composition, no CJK font fallback,
   and no terminal wide-character width handling.

Error text and logs are deliberately untouched. The 228 `HTTPException(detail=)`
sites in `src/scistudio/api/` are surfaced verbatim to the user by
`frontend/src/lib/api/core.ts`, and they stay English, as do all runtime
exception messages and log lines. Traditional Chinese is deferred; the design
does not preclude it, but no zh-Hant artifact is produced by this work.

## 2. User Scenarios & Testing

### User Story 1 - Switch the interface to Simplified Chinese (Priority: P1)

A scientist installs SciStudio, finds the language control, selects 简体中文, and
the entire interface renders in Chinese. The choice survives closing and
reopening the application.

**Why this priority**: Every other story depends on the runtime, the catalog
format, and the switch existing. Nothing else can be delivered or reviewed until
this is in place.

**Independent Test**: With no tutorial, user guide, or block metadata
localization present, set the locale to `zh-CN` and confirm the main window,
dialogs, palettes, bottom-panel tabs, welcome screen, and Electron menus and
update prompts render Chinese, and that the choice persists across a restart.

**Acceptance Scenarios**:

- **Given** a fresh install on an OS configured for Chinese, **When** the
  application starts for the first time, **Then** the interface renders in
  Simplified Chinese without the user changing any setting.
- **Given** a fresh install on an OS configured for English, **When** the
  application starts, **Then** the interface renders in English.
- **Given** the interface is in English, **When** the user selects 简体中文 from
  the language control, **Then** every visible surface re-renders in Chinese
  without a restart.
- **Given** the user selected 简体中文, **When** the application is closed and
  reopened, **Then** it starts in Chinese.
- **Given** a catalog entry is missing for a string, **When** that string
  renders under `zh-CN`, **Then** the English source text renders and no key
  artifact or empty string is shown.

### User Story 2 - Type Chinese without the interface fighting the input method (Priority: P2)

A Chinese user types into any text field using an IME, presses Enter to select a
candidate word, and the dialog does not submit. Chinese text renders with a
consistent typeface in the interface, the code editor, and the terminal, and
wide characters occupy the correct number of terminal columns.

**Why this priority**: These are live defects today, before any translation
lands, and they are independent of the catalog work. A Chinese interface that
cannot accept Chinese input is worse than an English one.

**Independent Test**: With the interface still in English, drive each of the
12 Enter-submitting handlers with a composition sequence and confirm no
submission fires during composition; render a Chinese string in the interface,
Monaco, and xterm and confirm an explicit font is resolved; print CJK text to
the terminal and confirm column alignment.

**Acceptance Scenarios**:

- **Given** a dialog with an Enter-to-submit handler, **When** the user presses
  Enter while an IME composition is active, **Then** the dialog does not submit
  and the composition candidate is accepted.
- **Given** the same dialog, **When** the user presses Enter with no active
  composition, **Then** the dialog submits as before.
- **Given** Chinese text in the interface, the code editor, or the terminal,
  **When** it renders on Windows, macOS, and Linux, **Then** it resolves through
  an explicit declared CJK fallback rather than an unspecified OS default.
- **Given** CJK text printed in the embedded terminal, **When** it is rendered,
  **Then** each wide character occupies two columns and following text stays
  aligned.

### User Story 3 - Work through a tutorial in Chinese (Priority: P3)

A scientist opens the Learning Center under the `zh-CN` locale and every
tutorial title, summary, step title, and spoken beat reads in Chinese, while the
tutorial's structure, highlights, conditions, and asset paths behave identically
to the English run.

**Why this priority**: The tutorial is the first thing a new user touches and
carries the densest prose. It depends on the runtime from Story 1 but on nothing
else.

**Independent Test**: Run both core tutorials end to end under `zh-CN` and
confirm the copy is Chinese, every step completes on the same conditions as the
English run, and no highlight or replay action changes behavior.

**Acceptance Scenarios**:

- **Given** the locale is `zh-CN` and a locale overlay exists for a tutorial,
  **When** the Learning Center lists and runs it, **Then** its title, summary,
  step titles, and beats render in Chinese.
- **Given** the locale is `zh-CN` and a tutorial has no overlay, **When** it is
  listed and run, **Then** its English copy renders and the tutorial completes
  normally.
- **Given** an overlay whose step ids do not match the manifest, **When** the
  tutorial is validated, **Then** validation fails with a message naming the
  unmatched ids.
- **Given** a beat carrying a mood prefix or bold markers, **When** it is
  translated, **Then** the prefix and markers survive intact in the Chinese
  beat.

### User Story 4 - Read the in-project user guide in Chinese (Priority: P4)

A scientist creating a project under the `zh-CN` locale finds the provisioned
`user-guide/` tree in Chinese, while the generated API reference inside it stays
English.

**Why this priority**: The user guide is reference material read after the
tutorial, not during first contact. It is the largest prose surface and the
slowest to review, so it should not block the interface shipping.

**Independent Test**: Create a project with the locale set to `zh-CN` and
confirm the hand-written guide pages are Chinese, `user-guide/api-reference/**`
is English, and the same project created under `en` is entirely English.

**Acceptance Scenarios**:

- **Given** the locale is `zh-CN`, **When** a project is provisioned, **Then**
  `<project>/user-guide/` contains the Chinese hand-written pages.
- **Given** the locale is `zh-CN`, **When** a project is provisioned, **Then**
  `<project>/user-guide/api-reference/` is the English generated reference,
  unchanged.
- **Given** a Chinese page whose English source has since changed, **When** the
  staleness check runs, **Then** it reports that page as stale and names the
  source commit it was translated from.

### User Story 5 - See built-in blocks named in Chinese, with third-party blocks intact (Priority: P5)

Under `zh-CN` the block palette and hover cards show Chinese names and
descriptions for built-in blocks and data types, while a block from an
unlocalized third-party package shows its English name and description without
error.

**Why this priority**: It is the only part of this work that changes a public
contract package authors write against, so it is sequenced last and gated on a
governance decision. The palette is usable in the meantime with English block
names.

**Independent Test**: Install a third-party package that declares no
localization, switch to `zh-CN`, and confirm built-in blocks render Chinese
while the third-party block renders English and the palette does not error.

**Acceptance Scenarios**:

- **Given** the locale is `zh-CN`, **When** the palette lists a built-in block,
  **Then** its Chinese name and description render.
- **Given** the locale is `zh-CN`, **When** the palette lists a block from a
  package that declares no localization mapping, **Then** its English `name` and
  `description` render and no error is raised.
- **Given** a package declares a localization mapping for a locale that is not
  active, **When** the palette lists its block, **Then** the English fallback
  renders.

### Edge Cases

- A catalog entry exists but its English source string has since been edited.
  The entry is orphaned: the new English text is the key, so English renders and
  the stale entry is reported by the catalog integrity check rather than
  silently shipping the old translation against the new string.
- An English source string contains `.` or `:`. `i18next` reads those as key and
  namespace separators by default and would silently nest the catalog.
  Separators must be disabled.
- A string is assembled from fragments at the use site. Concatenated fragments
  cannot be translated correctly into Chinese, whose word order differs.
  Fragmented strings must be rewritten as a single interpolated string before
  extraction.
- A translated string carries an interpolation placeholder. The translation
  engine must not reorder or translate the placeholder token.
- The same English word means different things in different places, for example
  `Type` as a data type and `Type` as an input action. Identical keys collide.
  Colliding strings need disambiguated keys with an explicit context.
- The user's OS locale is a Chinese variant other than `zh-CN`, for example
  `zh-TW` or `zh-HK`. With Traditional Chinese deferred, resolution must land on
  a defined locale rather than a missing catalog.
- DeepL is unreachable, rate-limited, or the API key is absent when the
  translation script runs. The script must fail without writing a partial
  catalog.
- A glossary term appears inside a code span or a fenced code block in a
  Markdown page. Code must not be translated or term-substituted.

## 3. Requirements

### Functional Requirements

- **FR-001**: The frontend MUST use `react-i18next` as its i18n runtime. An
  in-house catalog implementation is rejected.
- **FR-002**: The source locale MUST be `en` and the first translated locale MUST
  be tagged `zh-CN`.
- **FR-003**: Catalog keys MUST be the English source strings verbatim. The
  runtime MUST be configured with key and namespace separators disabled so that
  `.` and `:` inside English copy do not nest or namespace the catalog.
- **FR-004**: A missing or empty catalog entry MUST render the English key text.
  It MUST NOT render a key artifact, an empty string, or a placeholder marker.
- **FR-005**: Locale resolution MUST follow: explicit user selection, then the
  OS or browser preferred locale, then `en`. Any Chinese preferred locale that
  is not an available catalog MUST resolve to `zh-CN` while Traditional Chinese
  is deferred.
- **FR-006**: The selected locale MUST be persisted through the existing
  `zustand` `persist` store and restored on startup.
- **FR-007**: A language control MUST be reachable from the running interface,
  and changing it MUST re-render the interface without a restart.
- **FR-008**: Every user-facing string in `frontend/src/**` MUST be routed
  through the translation function. Developer-facing strings, test fixtures,
  and log or diagnostic text are excluded.
- **FR-009**: Strings assembled by concatenating fragments MUST be rewritten as a
  single string with interpolation placeholders before extraction.
- **FR-010**: Strings whose identical English text carries different meanings in
  different places MUST be disambiguated with an explicit translation context.
- **FR-011**: Every user-facing string in `desktop/main.js` — menu labels,
  dialog titles, OTA update prompts, and failure messages — MUST be routed
  through the same catalog format, resolved in the main process.
- **FR-012**: Catalog extraction MUST be performed by a committed, repeatable
  command using `i18next-parser`. Extraction output MUST be deterministic so
  that re-running it on an unchanged tree produces no diff.
- **FR-013**: A human-authored glossary of SciStudio domain terms MUST be
  committed at `scripts/i18n/glossary.csv`. Each row MUST carry the English
  term, the approved Chinese term, and an optional note.
- **FR-014**: Machine translation MUST be performed by a committed script
  invoking the DeepL API. The script MUST NOT be an AI agent authoring
  translations, and generated catalogs MUST NOT be hand-authored by an agent.
- **FR-015**: The translation script MUST protect non-translatable tokens before
  sending text to DeepL and restore them afterward: interpolation placeholders,
  Markdown inline code and fenced code blocks, bold markers, tutorial beat mood
  prefixes, file paths, and identifiers.
- **FR-016**: The glossary MUST be enforced by a deterministic post-pass over
  DeepL output so that term consistency does not depend on the engine's glossary
  language-pair support. A native DeepL glossary MAY additionally be used where
  the language pair supports it.
- **FR-017**: Each translated entry MUST carry provenance: the engine that
  produced it, a fingerprint of the English source it was translated from, and a
  reviewed flag.
- **FR-018**: An entry whose source fingerprint no longer matches the current
  English source MUST be reported as stale. A stale entry MUST NOT render; the
  English source renders instead.
- **FR-019**: A translated entry MUST NOT ship with its reviewed flag unset. The
  reviewed flag is set by a human reviewer in the pull request, never by the
  translation script.
- **FR-020**: A repository check MUST fail when a catalog contains an entry with
  no corresponding source string, an unreviewed entry, or a stale entry.
- **FR-021**: The tutorial manifest format MUST accept a per-locale overlay file
  alongside `tutorial.yaml`, carrying only translatable fields: `title`,
  `summary`, and per-step `title` and `say` beats, keyed by step id.
- **FR-022**: The tutorial loader MUST merge the overlay for the active locale
  and MUST fall back to the English manifest field-by-field when an overlay is
  absent or an individual field is missing.
- **FR-023**: Overlay validation MUST reject a step id that does not exist in the
  manifest, and MUST reject a `say` list whose beat count does not match the
  manifest's, because `say_moods` and `highlights` are positionally parallel to
  `say`.
- **FR-024**: An overlay MUST NOT be able to change tutorial structure,
  highlights, prefills, completion conditions, routes, or asset paths. Only copy.
- **FR-025**: The tutorial JSON schema MUST be extended to describe the overlay
  format, and the overlay MUST be validated in the same pass that validates the
  manifest.
- **FR-026**: The hand-written user guide MUST be packaged per locale at
  `src/scistudio/_user_guide/<locale>/**`, leaving the existing English tree at
  its current paths as the source locale.
- **FR-027**: `scistudio.agent_provisioning.docs` MUST provision the user guide
  tree for the active locale, and MUST fall back per-file to the English page
  when a translated page is absent.
- **FR-028**: The generated API reference MUST NOT be translated and MUST remain
  provisioned in English regardless of locale.
- **FR-029**: `scistudio.api.routes.user_docs` MUST serve the active locale's
  page when one exists and the English page otherwise.
- **FR-030**: Each translated Markdown page MUST record in its frontmatter the
  locale, the source path, the source commit it was translated from, and whether
  it was machine-generated, matching the `Translation` schema already defined in
  the ADR-042 document standards.
- **FR-031**: The block contract MUST gain optional class-level localization
  mappings for display name and description, keyed by locale. They MUST be
  optional, and a block that declares none MUST render its existing English
  `name` and `description`.
- **FR-032**: The data-type contract MUST gain the same optional mappings on the
  same terms.
- **FR-033**: The block and type catalog API responses MUST carry the resolved
  localized name and description for the requested locale, with the English
  fallback already applied server-side, so the frontend does not need to know
  which packages are localized.
- **FR-034**: A third-party package that declares no localization MUST load,
  list, and run under `zh-CN` with no error and no visual degradation beyond
  showing English metadata.
- **FR-035**: All 12 `key === "Enter"` submit handlers under `frontend/src/**`
  MUST guard against IME composition and MUST NOT submit while a composition is
  active.
- **FR-036**: Any new Enter-to-submit handler MUST carry the same guard. A lint
  rule or shared handler helper MUST make the guard the default rather than a
  thing each site remembers.
- **FR-037**: The interface, code editor, and terminal font stacks MUST declare
  explicit CJK fallback families for Windows, macOS, and Linux.
- **FR-038**: The embedded terminal MUST load a Unicode 11 width provider so CJK
  and emoji occupy correct column widths.
- **FR-039**: Frontend tests MUST NOT query by English display copy. Queries MUST
  use stable test ids or roles that do not change with locale.
- **FR-040**: The frontend test suite MUST pass under both `en` and `zh-CN`.
- **FR-041**: Backend API error text, runtime exception messages, and log lines
  MUST remain English and MUST NOT be routed through any catalog.
- **FR-042**: No Traditional Chinese catalog, overlay, or packaged tree is
  produced by this work.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `LocaleCatalog` | The per-locale message store the frontend and Electron shell read. | `locale`, entries keyed by English source string, per-entry `value`, `engine`, `source_fingerprint`, `reviewed` | One per locale; `en` is the identity catalog produced by extraction |
| `GlossaryEntry` | A human-approved term mapping enforced after machine translation. | `term_en`, `term_zh`, `note` | Applied to every `LocaleCatalog` entry and every translated Markdown page |
| `TranslationRecord` | Provenance frontmatter on a translated Markdown page. | `locale`, `source_path`, `source_sha`, `auto_generated`, `reviewed` | One per translated page; mirrors the ADR-042 `Translation` schema |
| `TutorialLocaleOverlay` | Per-locale copy for one tutorial, alongside its manifest. | `locale`, `title`, `summary`, per-step `title` and `say` keyed by step id | One per (tutorial, locale); merged over `TutorialManifest` at load |
| `BlockMetadataI18n` | Optional class-level locale mapping on a block or data type. | mapping of locale to display name, mapping of locale to description | Optional on every block and type; absent means English fallback |

## 4. Implementation Plan

### 4.1 Technical Approach

**Runtime.** `react-i18next` is initialized once in `frontend/src/i18n/`, with
`keySeparator: false` and `nsSeparator: false` so English copy containing `.` or
`:` is treated as a flat key. `fallbackLng: "en"` plus a catalog whose missing
entries return the key gives the English-fallback behavior of FR-004 with no
extra machinery: the key *is* the English string. Locale resolution reads the
persisted selection first, then the platform preference, then `en`, and any
`zh-*` preference maps to `zh-CN` for as long as Traditional Chinese is
deferred. The selection lives in the existing persisted `zustand` store rather
than a new persistence mechanism.

**Choosing English source strings as keys** is the owner's decision and it sets
the shape of everything downstream. It buys a trivial migration — wrap the
literal, no naming pass over 156 files — and it makes English structurally
impossible to lose. It costs stability: editing an English string orphans its
translation. FR-017 and FR-018 pay that cost explicitly by fingerprinting the
source and refusing to render a translation whose source moved, so an edited
string degrades to English and is reported, rather than shipping a translation
that no longer matches what it sits under.

**Electron shell.** The main process cannot share the React runtime. It loads
the same catalog JSON and resolves through a small lookup with the same
English-key and fallback semantics, so there is one catalog format and one
translation pipeline, not two.

**Supply chain.** Extraction, translation, and review are three separate,
individually reviewable steps:

```
i18next-parser  ──▶  locales/en.json          (identity catalog, generated)
                          │
scripts/i18n/translate.py │  protect tokens → DeepL → restore → glossary post-pass
                          ▼
                     locales/zh-CN.json       (machine output, committed, reviewed:false)
                          │
                     human review in the PR diff → reviewed:true
                          ▼
                     scripts/i18n/check.py    (CI: orphaned / stale / unreviewed)
```

Token protection (FR-015) is the part that decides output quality. Placeholders,
inline and fenced code, bold markers, and tutorial mood prefixes are replaced
with opaque sentinels and DeepL is called with XML tag handling and those
sentinels ignored, then restored. The glossary is applied as a deterministic
post-pass rather than relying on the engine, so term consistency holds
regardless of which language pairs DeepL's native glossary supports and so the
pipeline stays engine-replaceable.

Volume for a first full pass is roughly 110,000 characters — about 15,000 for
interface strings, about 25,000 for the translatable subset of tutorial copy,
and 70,057 for the hand-written user guide. That fits inside DeepL's free
monthly allowance; subsequent runs translate only entries whose fingerprint
changed.

**Tutorials.** A sibling overlay file per locale rather than inline per-field
maps. The English manifest stays the single structural source and reviewers read
one Chinese file per tutorial instead of a manifest doubled in size. The overlay
carries copy only (FR-024), and validation enforces the positional parallelism
that `say_moods` and `highlights` depend on (FR-023).

**User guide.** Per-locale packaged subtrees under `_user_guide/`, with the
English tree left where it is so the source locale's paths never move.
Provisioning and the docs route both resolve per-file with English fallback,
which means a partially translated guide is shippable. `api-reference/**` is
excluded at the provisioning layer, not by convention, so a future translated
page cannot accidentally shadow generated output.

**Block metadata.** Optional class-level locale mappings, resolved server-side
so the catalog API hands the frontend already-resolved strings and the frontend
never learns which packages are localized. This is the one public contract
change and the only piece that a third-party package author can observe;
optionality is what keeps it non-breaking.

**CJK correctness.** A shared submit-handler helper carrying the composition
guard, so FR-036 is satisfied by construction rather than by 12 remembered
checks; explicit font fallback declarations; and the xterm Unicode 11 width
addon.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `frontend/package.json` | modify | Add `react-i18next`, `i18next`, `i18next-parser`, `@xterm/addon-unicode11` |
| `frontend/src/i18n/**` | create | Runtime init, locale resolution, catalog loading, translation hook re-export |
| `frontend/src/locales/en.json` | generate | Identity catalog produced by extraction |
| `frontend/src/locales/zh-CN.json` | create | Machine-translated, human-reviewed catalog |
| `frontend/src/**/*.tsx` | modify | Route user-facing strings through the translation function (about 156 files) |
| `frontend/src/store/uiSlice.ts` | modify | Persisted locale selection |
| `frontend/src/index.css` | modify | CJK font fallback in the interface stack |
| `frontend/src/components/**` | modify | Shared composition-guarded submit helper; 12 Enter handlers migrated |
| `frontend/src/components/AIChat/**` | modify | xterm Unicode 11 width provider; terminal font fallback |
| `frontend/src/**/__tests__/**` | modify | Migrate 113 English-copy queries onto stable test ids (about 47 files) |
| `desktop/main.js` | modify | Route about 36 shell strings through the catalog |
| `scripts/i18n/extract.*` | create | Deterministic `i18next-parser` invocation |
| `scripts/i18n/glossary.csv` | create | Human-authored domain term list |
| `scripts/i18n/translate.py` | create | Token protection, DeepL call, glossary post-pass, provenance stamping |
| `scripts/i18n/check.py` | create | Orphaned, stale, and unreviewed entry check for CI |
| `src/scistudio/tutorials/manifest.py` | modify | Overlay loading, merge, and validation |
| `src/scistudio/tutorials/discovery.py` | modify | Discover overlays alongside manifests |
| `src/scistudio/tutorials/schema/tutorial.schema.json` | modify | Describe the overlay format |
| `src/scistudio/tutorials/core/*/tutorial.zh-CN.yaml` | create | Chinese copy for the two core tutorials |
| `src/scistudio/api/routes/tutorials.py` | modify | Resolve the active locale when listing and running |
| `src/scistudio/_user_guide/zh-CN/**` | create | Chinese hand-written guide pages |
| `src/scistudio/agent_provisioning/docs.py` | modify | Per-locale provisioning with per-file English fallback |
| `src/scistudio/api/routes/user_docs.py` | modify | Serve the active locale with English fallback |
| `src/scistudio/blocks/base/block.py` | modify | Optional localization mapping on the block contract |
| `src/scistudio/core/types/registry.py` | modify | Optional localization mapping on the type contract |
| `src/scistudio/blocks/**`, `src/scistudio/core/types/**` | modify | Populate mappings on built-in blocks and types (55 sites) |
| `src/scistudio/api/routes/blocks.py`, `types.py` | modify | Resolve localized metadata server-side |
| `tests/i18n/**`, `tests/tutorials/**`, `tests/blocks/**` | create/modify | Coverage per §4.4 |
| `docs/adr/ADR-0NN-addendum*.md` | create | Governance record for the block contract change (see §4.5) |

`src/scistudio/_user_guide/api-reference/**`, `docs/user/reference/**`,
`docs/package-development/**`, and `docs/contributing/**` are explicitly not
touched.

### 4.3 Implementation Sequence

Sequenced so each phase is independently reviewable and independently
shippable. The phase boundaries are the natural pull request boundaries; §4.5
records why this is not one pull request.

| Task | Title | Story | Depends on | Verification |
|---|---|---|---|---|
| T-001 | CJK correctness: composition guard helper, 12 handler migrations, font stacks, terminal width | US2 | — | Composition-sequence tests; manual IME check on Windows and macOS |
| T-002 | Test-id migration for the 113 English-copy query sites | US1 | — | Existing suites pass unchanged |
| T-003 | i18n runtime, locale resolution, persisted switch, language control | US1 | T-002 | Resolution and persistence unit tests |
| T-004 | Extraction tooling and the generated `en.json` identity catalog | US1 | T-003 | Re-running extraction produces no diff |
| T-005 | Glossary, translation script, provenance, and the CI integrity check | US1 | T-004 | Pipeline tests with a stubbed engine; glossary post-pass tests |
| T-006 | Route frontend strings through the catalog | US1 | T-004 | Suite passes under both locales |
| T-007 | Route Electron shell strings through the catalog | US1 | T-004 | Shell dialog and menu tests |
| T-008 | Translate and review the interface catalog | US1 | T-005, T-006, T-007 | Human review; integrity check green |
| T-009 | Tutorial overlay format, loader merge, schema, validation | US3 | T-003 | Overlay merge, fallback, and rejection tests |
| T-010 | Translate and review the two core tutorial overlays | US3 | T-009, T-005 | Both tutorials completed end to end under `zh-CN` |
| T-011 | Per-locale user guide packaging, provisioning, and serving | US4 | T-003 | Provisioning and fallback tests; reference stays English |
| T-012 | Translate and review the 16 hand-written guide pages | US4 | T-011, T-005 | Human review; staleness check green |
| T-013 | Block and type localization contract, plus governance record | US5 | T-003 | Contract tests; unlocalized third-party package renders English |
| T-014 | Populate and review built-in block and type metadata (55 sites) | US5 | T-013, T-005 | Palette renders Chinese; fallback holds |

### 4.4 Verification Plan

- **Automated tests.** Locale resolution and persistence; catalog integrity
  (orphaned, stale, unreviewed); glossary post-pass determinism; token
  protection round-trips including placeholders, code spans, fenced blocks, bold
  markers, and mood prefixes; composition-guard behavior on every migrated
  handler; tutorial overlay merge, per-field fallback, and the two rejection
  cases; user guide provisioning fallback and API-reference exclusion; block and
  type metadata resolution with an unlocalized package.
- **Dual-locale suite.** The frontend suite runs under both `en` and `zh-CN`.
  Any test that fails under one locale and passes under the other is a test
  still bound to display copy.
- **Repository checks.** `gate_record check` selects the tier-appropriate CI
  set. The new i18n integrity check joins it as a repository check so an
  unreviewed or stale entry cannot merge.
- **Manual verification.** IME composition on Windows and macOS with a real
  input method — the automated composition events approximate but do not
  replace this. Both core tutorials run end to end under `zh-CN`. A project
  provisioned under `zh-CN` inspected for guide language and reference language.
  A third-party package installed and listed under `zh-CN`.
- **Human translation review.** Every catalog entry, overlay beat, and guide page
  is read by a human in the pull request diff before its reviewed flag is set.
  This is the acceptance step for the translation itself; no automated check
  substitutes for it.

### 4.5 Risks And Rollback

| Risk | Mitigation |
|---|---|
| Delivery size. Issue #2064 estimates 2–3 weeks and 2,500–4,000 lines across about 150 frontend files; this spec adds tutorials, the user guide, and the pipeline on top. A single pull request would be unreviewable, and the translation review inside it would be unreviewable twice over. | Ship along the §4.3 phase boundaries. T-001 and T-002 carry no user-visible behavior change and can land first. See the open decision below on issue split. |
| English-as-key instability. An English copy edit orphans its translation. | FR-017/FR-018 fingerprint the source and degrade to English on mismatch; FR-020 fails CI on stale entries. Accepted cost of the owner's key decision. |
| Machine translation quality on short interface strings. Isolated words like `Run`, `Type`, `Save`, and `Bind` lack the context any engine needs. | The glossary carries SciStudio's domain terms and is applied deterministically; disambiguation contexts (FR-010) separate colliding words. Human review is the acceptance gate, and interface strings are where reviewer effort should concentrate. |
| Block contract change is observable by third-party package authors and is not cheaply reversible. | Optional by construction with English fallback (FR-031, FR-034); recorded in a governance document before T-014 populates the 55 sites. |
| Tutorial positional parallelism. `say_moods` and `highlights` are index-parallel to `say`, so a translated beat list of the wrong length would silently misalign moods and highlights. | FR-023 rejects a mismatched beat count at validation rather than at runtime. |
| DeepL is an external dependency with a key, a quota, and network access. | The engine is isolated behind one script and the glossary post-pass is engine-independent (FR-016), so replacing the engine does not touch the catalogs. The script fails without writing partial output. Translation is a local authoring step, never a build or CI step. |
| Partial translation shipping as a broken mixed interface. | English fallback is total: a missing, stale, or unreviewed entry renders English everywhere (FR-004, FR-018). A partially translated build is coherent, not broken. |

**Rollback.** Each phase reverts independently. Reverting the locale catalogs
leaves the interface English with the runtime intact. Reverting the runtime
leaves the CJK fixes and test-id migration in place, both of which are
improvements independent of localization. The block contract change is the only
one-way door, which is why it is sequenced last and gated on a governance
record.

**Open decisions this spec does not settle.** These are owner decisions
recorded here rather than assumed:

1. **Issue split.** #2064 is titled "interface only" and explicitly places
   documentation out of scope, so tutorial and user guide translation (US3, US4)
   are not tracked by it. Either #2064's body is amended to cover them, or a
   second issue tracks end-user content translation. Given the delivery-size
   risk above, separate issues track the phases more honestly.
2. **Governance record for the block contract.** Whether FR-031 through FR-034
   land as an ADR addendum ahead of implementation or alongside T-013.
3. **CJK defect split.** Whether T-001 ships as its own bug-fix pull request
   ahead of this work — it fixes live defects and depends on nothing here — or
   travels with the i18n line.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: A user can switch between English and Simplified Chinese from the
  running interface, and the choice survives a restart.
- **SC-002**: Under `zh-CN`, zero English strings remain visible on the main
  window, dialogs, palettes, bottom-panel tabs, welcome screen, Electron menus,
  and OTA update prompts, excluding backend error text and log output which stay
  English by design.
- **SC-003**: All 12 Enter-to-submit handlers refuse to submit during IME
  composition, verified by test and by manual IME use on Windows and macOS.
- **SC-004**: The interface, code editor, and terminal each declare an explicit
  CJK fallback family, and CJK text in the embedded terminal occupies correct
  column widths.
- **SC-005**: Both core tutorials complete end to end under `zh-CN` with all
  copy in Chinese and with step completion identical to the English run.
- **SC-006**: All 16 hand-written user guide pages are provisioned in Chinese
  under `zh-CN`, and `user-guide/api-reference/` remains English.
- **SC-007**: All 55 built-in block and data-type name/description sites render
  Chinese under `zh-CN`.
- **SC-008**: A third-party package declaring no localization loads, lists, and
  runs under `zh-CN` with English metadata and no error.
- **SC-009**: The frontend test suite passes under both `en` and `zh-CN`, and
  zero tests query by English display copy.
- **SC-010**: The catalog integrity check fails the build on an orphaned, stale,
  or unreviewed entry, demonstrated by a test for each of the three cases.
- **SC-011**: Every shipped translated entry and page carries provenance naming
  its engine, its source fingerprint, and a reviewed flag set by a human.
- **SC-012**: Re-running extraction and translation on an unchanged tree
  produces no diff.

## 6. Assumptions

| Assumption | Source |
|---|---|
| The locale tag is `zh-CN` rather than `zh-Hans`, accepting that a future Traditional locale will be tagged by region rather than by script. | owner |
| Traditional Chinese is deferred entirely; no zh-Hant artifact is produced, and any Chinese OS preference resolves to `zh-CN` in the meantime. | owner |
| Catalog keys are English source strings, accepting the orphaning cost that FR-017/FR-018 mitigate. | owner |
| Error text, exception messages, and log lines stay English at every layer. | owner |
| "End-user facing" means the hand-written user guide and tutorial copy. `docs/package-development/**` and `docs/contributing/**` are developer-facing and stay English. | owner |
| The generated API reference stays generated and stays English; translating it would mean translating Python docstrings, which are developer-facing API contract text. | owner, existing-system |
| Translations are produced by DeepL plus a committed glossary and reviewed by a human. No translation is authored by an AI agent. | owner |
| `react-i18next` is acceptable as a new frontend dependency. | owner |
| Third-party block packages are not required to localize, and the contract addition must be optional. | issue #2064 |
| A DeepL API key is available to whoever runs the translation script. Translation is a local authoring step and is never invoked from CI. | inferred |
| The existing `zustand` `persist` store is the right home for the locale selection; no new user-preference backend is introduced. | existing-system |
| The `Translation` frontmatter schema already defined in the ADR-042 document standards is the record format for translated Markdown pages, even though the user guide lives under `src/scistudio/_user_guide/` rather than `docs/<locale>/`. | existing-system |
