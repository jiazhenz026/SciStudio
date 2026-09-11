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

The core id reservation follows descriptor FR-002 pending owner reconciliation of
its wording with the same-id customization story. A custom panel can use a new id
and its same type to win the existing routing ladder.

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
