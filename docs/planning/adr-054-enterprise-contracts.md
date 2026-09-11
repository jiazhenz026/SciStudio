---
title: "ADR-054 Phase A Enterprise Integration Contracts"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs: [54, 55]
related_specs: [adr-054-panels, adr-054-miniapp, adr-055-enterprise-support, adr-055-identity-seam, adr-055-prefix-independence]
language_source: en
---

# ADR-054 Phase A Enterprise Integration Contracts

Implementation acceptance matrix for #2293, coordinated under #2296. These are
planned checks against the existing contracts, not claims that panels are implemented.

## Existing Integration Points

At `7b132175`, `scistudio.api.seam` already supplies replacement guards,
`register_self_authenticating_prefix`, `GuardContext.route_path`, lifespan hooks,
and capabilities. `tests/api/fake_guard.py` and `tests/api/seam_contract.py`
provide the reusable guard harness. Frontend URL construction uses
`frontend/src/lib/api/base-path.ts`.

Enterprise UI PR #2336 was open at initial inspection, head `0e8546ff`.
It changes `api/app.py`, `api/routes/data.py`, seam/capability definitions,
`frontend/src/lib/api/data.ts`, toolbar and BottomPanel. Phase A must preserve
its incoming changes. No Phase A agent owns seam/capability definitions or
enterprise UI. App and data-route overlaps are reviewed hunk by hunk during
integration. Do not assume that unmerged APIs exist on the baseline.

## Acceptance Matrix

| Boundary | Required behavior | Owner | Verification |
|---|---|---|---|
| Identity seam | Register only `/api/panels/t/`; self-authenticating routes verify their own token | A1 | Default and fake guard, root and `/user/alice/scistudio` mounts |
| Host operations | Catalog/context/read/close requests remain behind the installed guard; a static token grants no data or mutation authority | A1 | Missing session, valid session, static token misuse, sibling/lookalike paths |
| Static resources | Token is per mount, restricted to that panel, expiring/renewable while active, invalid after close; assets, SDK, library modules/fonts load without cookies | A1/A2 | Valid/invalid/revoked/cross-panel tokens; path traversal and symlink escape |
| Prefix | Backend-generated entry/SDK/lib URLs and frontend requests preserve normalized root path once | A1/A2 | Root and prefixed tests; no hardcoded origin or double prefix |
| Global refusal | All null-Origin POST/PUT/PATCH/DELETE requests are refused, including edition routes and token paths | A3 | Default/replacement guard and supplied edition router |
| CORS | Reject `*` and `null` configuration; permissive noncredentialed CORS only for authenticated static token responses | A3/A1 | Startup errors, ordinary API rejection headers, module preflight behavior |
| Sandbox | Exactly `allow-scripts`, no-referrer, CSP connect-src none, one channel per mount, teardown on navigation | A2 | Frame attributes, wrong-window/port messages, remount/close and timeout |
| Save | Generated panel bytes are saved through an explicit user choice to this computer; never silently written into the server project | A2 | Browser download and existing native dialog paths; size limit and cancel |
| Project lifetime | Stale contexts cannot access a new project or retained/replaced output by reusing an old reference | A1 | Project switch, context close, ref authorization and frozen target tests |
| Host layout | Reuse the same panel host in desktop/browser/AI presentation without requiring a right column | A2 | Existing presentation and preview-tab regression tests |
| MiniApp readiness | A does not start panel Python; D adds call/process lifecycle and follows ai_chat_disabled policy for guided creation | A1/A2 | No Python execution in preview/interactive; D scope remains in its spec |

## Scope Decisions

The owner selected preserving the existing sidebar entry during A. D performs
the MiniApps/All Previewers transition. Phase A SDK sample mode is still required
by T-010; it does not imply an interim Panels sidebar or directory promotion.

No Hub OAuth, cookies, XSRF, transfer endpoints or enterprise deployment code is
introduced here. The public fake-guard/prefix harness validates the open-source
contract. Real Hub integration remains the enterprise repository's responsibility
under ADR-055; results must not be reported as real-Hub verification.

## Remaining Delivery Evidence

- [ ] Committed root/prefix guard and token contract tests.
- [ ] Security checks on installed edition routes and normal APIs.
- [ ] SDK/frame and preview/interactive integration tests.
- [ ] Current enterprise overlap review and integration commit.
- [ ] Gate, audits, browser smoke, and CI on the final Phase A candidate.
