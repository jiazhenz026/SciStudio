# Impact-Scope Report — Issue #1579

`refactor(previewers): make frontend_manifest a first-class session-envelope field`

Investigation agent output (read-only), committed verbatim and handed to the
implementing agent. Branch: `track/issue-1579-frontend-manifest` (off ADR-048
SPEC 1 `track/adr-048-spec1-preview-system`). Task kind: **refactor**.

Refs #1579. Refs #1574 (origin audit).

---

## A. Current state — how the manifest flows today

- **`FrontendManifest`** — `src/scistudio/previewers/models.py:178-218`. Frozen
  dataclass: `previewer_id, module_url, export_name="default", css=(),
  version="0", api_version=PREVIEWER_API_VERSION, asset_root: str | None = None`.
  `to_dict()` (209-218) emits the wire shape and **omits `asset_root`**
  (backend-only path-confinement value).
- **`PreviewerSpec.frontend_manifest`** — `models.py:257`, serialized in
  `PreviewerSpec.to_dict()` at line 277. Set by imaging `get_previewers()` at
  `packages/.../previewers/__init__.py:400` (Image) / `:411` (Label), built by
  `_frontend_manifest()` (89-99, which passes `asset_root`).
- **Imaging embeds via `_embed_manifest`** (`previewers/__init__.py:189-198`),
  writing `metadata.extra["frontend_manifest"]` at **3 call sites**:
  `_error_envelope` (213), `image_provider` (290), `label_provider` (365).
- **`PreviewSessionManager` does NOT touch the manifest.** `session.py` never
  references it. The injection seam is `_render()` (`session.py:214-253`):
  provider returns the envelope at line 240; manager calls
  `envelope.with_session(session_id)` at line 253 before returning. `spec` is a
  `_render` parameter, so `spec.frontend_manifest` is in scope.
  **`with_session()` (`models.py:402-414`) rebuilds the frozen envelope
  field-by-field — it must carry any new field or the field is dropped.**
- **API serialization** — `src/scistudio/api/routes/data.py` builds
  `PreviewEnvelopeModel(**envelope.to_dict())` (lines 164/175/188).
  `PreviewEnvelope.to_dict()` (`models.py:389-400`) emits
  `metadata: self.metadata.to_dict()`; `PreviewMetadata.to_dict()`
  (`models.py:305-315`) does `data.update(self.extra)`, flattening
  `metadata.extra["frontend_manifest"]` to a top-level `metadata.frontend_manifest`
  wire key. `PreviewEnvelopeModel` (`schemas.py:272-283`) has **no
  `frontend_manifest` field**; the manifest survives only inside the free-form
  `metadata: dict[str, Any]`.
- **Frontend read** — `PreviewHost.tsx` `readManifest()` (lines 64-71) reads
  `envelope.metadata?.frontend_manifest` (the flattened top-level metadata key,
  not `metadata.extra`). `dynamicPreviewer.ts` / `previewerHostApi.ts` only
  consume the extracted manifest object.
- **TS types** — `frontend/src/types/api.ts`: `PreviewerManifest` (291-306);
  `PreviewMetadata` (321-333) already has `frontend_manifest?` at line 330 +
  index signature; `PreviewEnvelope` (355-365) has **no** `frontend_manifest`.
- **Legacy `/api/data/{ref}/preview` (FR-008)** — `api/runtime/_data.py`
  `preview_data` → `_envelope_to_legacy_preview` (315-389) **discards
  `metadata`**, never surfaced the manifest, needs **no change** (it shares the
  provider path, so a stamped envelope is simply ignored — harmless).

## B. Exact change set (ordered)

1. **`src/scistudio/previewers/models.py`** — add
   `frontend_manifest: FrontendManifest | None = None` to `PreviewEnvelope`
   (after `error`, optional so plot/core/error envelopes stay valid). Update
   `to_dict()` to emit
   `"frontend_manifest": self.frontend_manifest.to_dict() if self.frontend_manifest else None`.
   **Update `with_session()` to pass `frontend_manifest=self.frontend_manifest`**
   (critical — it always runs at `session.py:253`). Update the class docstring.
2. **`src/scistudio/previewers/session.py`** — in `_render()` before
   `return envelope.with_session(session_id)`, stamp the spec default only when
   absent:
   ```python
   if envelope.frontend_manifest is None and spec.frontend_manifest is not None:
       envelope = replace(envelope, frontend_manifest=spec.frontend_manifest)
   ```
   Add `from dataclasses import replace`. The `MISSING_BUNDLE` early-return
   (224-229) is left as-is (no provider ⇒ no mountable UI).
3. **`src/scistudio/api/schemas.py`** — move `PreviewFrontendManifestModel`
   (286-295) **above** `PreviewEnvelopeModel` (272-283), then add
   `frontend_manifest: PreviewFrontendManifestModel | None = None` to
   `PreviewEnvelopeModel`. The `**envelope.to_dict()` spread populates it; no
   route change needed.
4. **`frontend/src/types/api.ts`** — add `frontend_manifest?: PreviewerManifest | null;`
   to the `PreviewEnvelope` interface (355-365) with a doc comment.
5. **`frontend/src/components/DataPreview.parts/PreviewHost.tsx`** —
   `readManifest()`: `const manifest = envelope.frontend_manifest ?? envelope.metadata?.frontend_manifest;`
   (prefer first-class, keep metadata fallback). Update doc comments
   (PreviewHost top + `previewerHostApi.ts:29`).
6. **`packages/scistudio-blocks-imaging/.../previewers/__init__.py`** — delete
   `_embed_manifest` (189-198); call sites → `extra=extra` (image/label),
   `extra={}` (error). Update the "Manifest-delivery seam" docstring (23-29) to
   say the manifest is framework-stamped by `PreviewSessionManager`. The spec's
   `frontend_manifest=...` at 400/411 stays (single source of truth).

## C. Compatibility / correctness decisions (locked)

1. **Keep the frontend `metadata.frontend_manifest` fallback** —
   `envelope.frontend_manifest ?? envelope.metadata?.frontend_manifest`. Primary
   read is first-class; fallback is zero-risk defense for un-migrated providers.
2. **Precedence: stamp only when `envelope.frontend_manifest is None`.** A
   provider that sets its own manifest wins; providers that set nothing inherit
   the spec default (the point of #1579).
3. **Field is optional/`None`** — confirmed required for plot/core/collection/
   error envelopes; a required field would break the core-fallback tests.
4. **Legacy `/api/data/{ref}/preview`** — separate path, discards metadata,
   no change.

## D. Tests impacted / needed

Update (assert on old `metadata.extra` channel):
- `packages/scistudio-blocks-imaging/tests/test_previewer_registration.py`
  lines 262-267, 287, 318 + header docstring 14-16 → retarget to assert the
  manifest reaches the **session envelope** (drive through `PreviewSessionManager`
  and assert `envelope.frontend_manifest`), and that the provider alone no longer
  embeds into `metadata.extra`.
- `frontend/.../PreviewHost.test.tsx` 133-141/161-169/191-200 still pass via the
  fallback; **add** a case with a top-level `envelope.frontend_manifest`.

New:
- Backend session-manager test: spec manifest auto-injected when provider sets
  none; provider-set manifest NOT overwritten (precedence); spec with no manifest
  ⇒ `envelope.frontend_manifest is None`.
- Backend serialization (`tests/api/test_previewers.py`): Image session JSON has
  top-level `body["frontend_manifest"]["previewer_id"] == "imaging.image.viewer"`
  (needs `SCISTUDIO_DEV=1` imaging discovery — see `test_collection_session_lists_items`);
  core dataframe ⇒ `body["frontend_manifest"] is None`.
- Frontend `PreviewHost.test.tsx`: first-class read case.

## E. Docs (REQUIRED)

1. `docs/specs/adr-048-preview-system.md` §3 — `PreviewEnvelope` table
   (lines 323-335) add a `frontend_manifest` row: *"Optional same-origin
   manifest, framework-stamped by the session manager from the resolved
   `PreviewerSpec`. Null for core fallbacks."* Add a clause to FR-020 (269-270)
   noting first-class delivery on `PreviewEnvelope.frontend_manifest`.
2. `docs/adr/ADR-048.md` §4 (lines 209-212) — add: *"The session manager stamps
   the resolved previewer's `frontend_manifest` onto the `PreviewEnvelope` it
   returns, so providers declare the manifest once on their `PreviewerSpec` and
   never re-embed it per envelope; the host reads it from
   `envelope.frontend_manifest`."*
3. `docs/block-development/**` — grep found **no** old-channel mentions ⇒ record
   N/A in the gate ledger.

## F. Governance / gate

- `src/scistudio/previewers/**` and `src/scistudio/api/**` are **NOT**
  protected-core (`gate_record/surfaces.py:73-79` lists only core/engine/blocks/
  workflow/utils). **No `admin-approved:core-change` label.**
- No governance surface touched (`docs/ai-developer/**` and `ADR-042*` only) ⇒
  **no `governance_touch`**. ADR-048/spec are architecture/spec docs (normal
  docs checks).
- **No `pyproject.toml` / entry-point change.**
- Sentrux applies (src/frontend/packages/tests/docs-adr-specs) ⇒ plan a
  **PASS**, not a skip.
- CHANGELOG `[Unreleased]` conflict risk if other PRs open (recurring).
- Task kind **refactor**, implementation category ⇒ **tests mandatory**.
