---
title: "ADR-054 Phase A Backend Implementation Notes"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [54, 55]
related_specs: [adr-054-panels, adr-054-miniapp, adr-055-identity-seam, adr-055-prefix-independence]
language_source: en
---

# ADR-054 Phase A Backend Implementation Notes

Implementation under #2293, coordinated by #2296 and umbrella #2353. This note
records backend choices; integrated gate, browser and CI results remain manager
obligations, not claims made by this slice.

## Contracts

Panels adapt their preview type claims into `PreviewerSpec` candidates in the
existing `PreviewRouter`. Interactive/MiniApp-only descriptors occupy the shared
namespace but never enter preview routing. Same-tier panels shadow legacy ids;
project, user, package and core precedence applies across ids and tiers. The
catalog reports renderer, descriptor, shadowing and diagnostics. Both legacy
provider forms remain functional through 0.5.x. The sidebar entry stays unchanged
until Phase D.

`POST /api/panels/contexts` takes `{kind, target: {kind, ref}, panel_id?,
preview_session_id?, parent_context_id?, view_state?}` for preview; interactive
takes `{kind, workflow_id, block_id, panel_id}`. Both return HTTP 200 with
`context_id`, `panel: {id, api_version, name}`, `kind`, `operations`, `services`,
`input`, `view_state`, `token`, `expires_at`, `entry_url`, `sdk_url` and
`lib_base_url`. `expires_at` is UNIX seconds. DELETE closes idempotently with 204;
POST `/contexts/{id}/renew` extends the same token by 600 seconds and returns the
same response shape. Context and static tokens use at least 128 random bits.
The contexts are bounded at 128 concurrent mounts; limits are refused explicitly.

Reads use `{ref, op, params}` and return operation JSON with `sampled`,
`truncated`, `complete`. Numeric binary replies use `application/octet-stream`,
little-endian dtype, and `X-Panel-Dtype`, `X-Panel-Shape` (JSON),
`X-Panel-Metadata` (JSON including flags). Read routes run as synchronous FastAPI
handlers in its worker pool. Budgets: 8 MiB encoded response, 200 table rows,
200 collection items, 512 x 512 plane/tile, 2,000 series/XY points, 64 KiB text.
Unsupported operations fail explicitly; parameters never choose filesystem paths.

Errors use `{detail: {code, message}}`: unauthorized refs/static tokens 403,
unknown contexts/panels 404, changed project/registry/data or nonwaiting blocks
409, invalid requests 422, unsupported operations 400, budget overflow 413.
Create/renew and binary/JSON reads carry explicit OpenAPI schemas.

## Authority And Enterprise Adaptation

The runtime catalog reconstructs scalar target type/storage. Collection output
registration adds a backend-owned opaque `collection_ref`, retaining snapshots
for their catalog/project lifetime. A mounted context retains its own frozen
snapshot, so unrelated registrations cannot evict a visible output or active panel.
Single-item output normalization stays unchanged. Client `_collection_items`,
`_storage`, type and shape values are not panel authority. Reachable slot paths
must stay under their parent composite. Context reads verify source identity and
storage inode/mtime/size, and fail after replacement or removal.

Only `/api/panels/t/` is registered with the existing identity seam. Assets, SDK,
and libraries authenticate their own context static token, independent of session
cookies. Operations remain under the default/replacement guard. URLs use ASGI
root_path once. CSP uses the absolute token path, `connect-src 'none'`, the three
SciStudio CDN hosts, and no broad same-origin source. Static responses allow
noncredentialed CORS and authenticated OPTIONS. General API errors do not gain
permissive CORS.

`artifact.file` creates a separate random grant token plus opaque grant id, bound
to exactly one context-authorized frozen storage reference. Its URL is
`/api/panels/t/{grant_token}/artifact/{grant_id}`. The static token cannot read an
artifact, and an artifact grant cannot load panel files/SDK/libraries. Closing or
expiring the owning context revokes both. Cached plot artifacts work through their
registered data record; no caller-provided filename or project-wide token exists.
Artifact responses carry attachment disposition and sandbox CSP.

The existing EventBus `interactive_prompt` provides the frozen interactive input.
Open confirms the matching scheduler future is pending and block state is PAUSED.
New-panel WebSocket `interactive_complete` includes `context_id` outside its
response. The WS hook validates and claims that context exactly once, then emits
the unchanged existing event. Remember handling remains frontend workflow config;
no new engine event or REST completion path exists. Cancel/resume/terminal events
revoke contexts. Interactive reads authorize no references. Neither preview nor
interactive imports or starts `panel.py`.

## Phased Migration And Documentation Landing

The owner confirmed strict core id reservation under descriptor FR-002. Both
panel descriptors and the shared legacy registry reject non-core `core.*` ids.
A custom panel can use a new id and its same type to win the existing routing
ladder or user choice.

TODO(#2294): Remove the explicit compiled-window exceptions for
`core.interactive.data_router` and `core.interactive.pair_editor` when Phase B
ships their real HTML panels. Out of scope per ADR-054 Phase A/B split;
follow-up: https://github.com/jiazhenz026/SciStudio/issues/2294.
Missing generic ids and resolved context mismatches remain errors.

The new descriptor/registry/context Python helpers are internal implementation,
not an advertised provisional author Python SDK. The author surface is panel.json
and the dependency-free browser SDK. Package contract inventory now recognizes
PanelDescriptor, PanelRegistry, parse_descriptor, validate_interactive_panel,
validate_external_references and resolve_panel_file. Manager/ADR-author owns
contract-table rows, ADR-049 PV-12-001 exception wording, owner-controlled ADR
frontmatter, generated references and architecture landing.

## Verification

Dependency slice: 50 descriptor/confinement/routing/context and existing routing
tests pass. Further route, read-extension, collection, WS, guard/prefix tests and
local gate evidence are recorded in the final slice update. No browser or CI
success is claimed here.

Follow-up validation: 119 existing interactive engine/block/API/tutorial
compatibility cases passed. The existing
`test_the_loader_refuses_what_it_does_not_read` failed when installed tifffile
requested missing `imagecodecs.DEFLATE.available`; no tutorial source changes
were made. Genuine panel entry-point fixtures preserve registry validation.
Own panel/route mypy checks pass (10 source files); the new import cycle was
removed by sharing asset validation in panels/files.py. Route/collection/WS
authority coverage now includes root prefixes, artifact grant separation,
binary byte order, thread-pool reads, and >1,024 retained collection outputs.
Integrated generated docs/OpenAPI, full gate and CI remain manager obligations.

Entry initialization uses a required `bootstrap_proof` on create/renew (256 random
bits, stable during renewal). Only the descriptor entry response prepends a
standards doctype and trusted inline script before all original bytes. The script
keeps a private MessageChannel endpoint in its document closure and sends
`{v:1,id:"bootstrap",type:"bootstrap",proof}` plus the other endpoint to the parent.
The host verifies the expected frame, proof and one port, then sends canonical
init and the SDK port only through that retained endpoint after load. The old
document's channel cannot initialize a replacement document. Original SDK init
receives one synthetic parent-source message; the bootstrap endpoint closes.
Secondary HTML, modules, libraries, artifacts and OPTIONS carry no bootstrap.
Proof escaping prevents markup termination; no CSP or sandbox permissions change.

Post-bootstrap targeted suite: 118 passed across descriptor/routing/context,
collection authority, WS claims, real installed guard/prefix routes, static
security, import-cycle and docstring policy tests. Manager separately reproduced
the earlier TIFF test successfully in the isolated A3 gate environment.

Entry review follow-up: descriptor entry paths normalize redundant dot segments
before URL generation, so `./index.html` and nested `./views/./index.html`
receive the same document bootstrap as their browser-normalized paths. Bootstrap
serving checks the opened file size against the shared 16 MiB source-validation
limit before reading and still caps the subsequent read at limit + 1 byte to
handle concurrent growth. Oversized sources return 413/read_budget. The targeted
route/descriptor suite passes 38 cases; Ruff and mypy (10 sources) pass.

Independent audit follow-up: guarded `POST /api/panels/contexts/{id}/open` accepts
only `{ref}` and returns the existing `PreviewEnvelopeModel`. The parent authorizes
the child; the backend supplies frozen type/storage/collection query values to
the real preview session pipeline, supporting both legacy/core and HTML panels.
The child session retains its own frozen authority after parent close; maximize
reads that session, then creates a fresh panel context with its session id.
Composite slot authority retains its catalog ancestor. Session get, patch and
resource reads validate project, registry and source, and session eviction
removes validation/authority state. Private query patch fields are rejected.
No internal storage query is included in the returned envelope.

New-panel WS decisions now receive connection-local acknowledgement after the
existing interactive_complete event is emitted: `{type:"panel_accepted",
context_id,workflow_id,block_id}`. Rejections carry the same identity and
`{type:"panel_error",error:{code,message}}`. Hosts must wait for matching accepted
before remembering the decision or closing/deleting the context. Dispatch failure
after claim returns completion_failed and requires remount; duplicates never
emit a second completion. No runtime event or lineage payload changed.

Lifecycle cleanup retains the originally subscribed EventBus even if a recorder
replaces runtime.event_bus. The shared legacy registry now rejects non-core
core.* registrations before tier precedence. Targeted audit-follow-up suites
cover real legacy child content, composite independent mounts, private-query
tampering, project/service/data invalidation for every session operation,
eviction, delayed WS acknowledgements, duplicate/error scoping, original-bus
cleanup and direct/entry-point core reservation. Ruff and mypy (12 sources) pass.

Final catalog audit fix: the shared preview catalog also adapts the PanelRegistry
shadowed descriptors into complete panel cards. Winner and shadowed cards retain
owner tier/name, contexts, all declared types and priority, including interactive-
only panels. These cards never enter the routing candidate set. Same-id project
and user panel regressions cover both registry and root/prefixed API listings;
48 focused tests pass, with Ruff and targeted mypy checks.
