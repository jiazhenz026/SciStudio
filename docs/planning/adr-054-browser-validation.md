---
title: "ADR-054 Phase A Automated Browser Validation"
status: Approved
owners: ["@jiazhenz026"]
related_adrs: [54, 55]
language_source: en
---

# ADR-054 Phase A Automated Browser Validation

Issue: #2293. Source candidate: manager `90cc975b`; browser dependency head
`ffeec67f` has identical `src/` and `frontend/src/` content. Executed 2026-09-11
with Playwright 1.60.0 and Chromium 148.0.7778.96. Result: **24 passed (1.3m)**.

## Coverage

Six scenarios run under each of four deployments: root/default guard,
root/replacement guard, `/user/browser/scistudio`/default guard, and that
prefix/replacement guard. The replacement is the existing cookie guard
installed through `create_app(guard=...)`.

- Production PanelFrame and PreviewHost each perform opaque-origin SDK ready,
  metadata/text reads, artifact-grant hydration to actual ArrayBuffer bytes,
  and a host download with verified filename and exact `hello panel` contents.
- Unmount returns DELETE 204; the original entry token and artifact grant
  subsequently return 403. The SDK static route succeeds without session cookies.
- A browser-created sandboxed form sends an actual Origin:null POST; production
  global middleware returns 403 with its explicit opaque-origin refusal.
- An entry that navigates immediately, before load, never delivers authorized
  init data to its successor. Host timeout revokes the context. A separate
  post-ready navigation also rejects and revokes. Browser frame message
  instrumentation observes successor init messages; no bridge is mocked.
- Composite panel opens a real legacy text renderer, returns, opens a table
  panel, and transfers its frozen session to an independent PreviewHost mount.
  Parent and old child close; the new context still reads the two table rows.

## Commands

From `frontend/`, with `PANEL_TEST_PYTHON` set to an isolated interpreter with
repository test dependencies (the source is supplied through PYTHONPATH):

```sh
npm ci --ignore-scripts
PANEL_TEST_PYTHON="$PANEL_TEST_PYTHON" npx playwright test -c playwright.panels.config.ts
npx eslint --no-ignore e2e/specs/panel-runtime.spec.ts e2e/helpers/panel-browser-host.tsx playwright.panels.config.ts
npx tsc -p e2e/helpers/panel-fixtures/tsconfig.json --noEmit
npx prettier --check e2e/specs/panel-runtime.spec.ts e2e/helpers/panel-browser-host.tsx e2e/helpers/panel-browser-host.html e2e/helpers/panel-fixtures playwright.panels.config.ts
```

From the repository root:

```sh
python -m ruff check frontend/e2e/helpers/panel-backend.py
python -m ruff format --check frontend/e2e/helpers/panel-backend.py
python -m scistudio.qa.governance.gate_record check --record .workflow/records/2293-panel-browser-tests.json --base ffeec67f --mode local --only lint_format --only format_check
```

Browser, lint, and strict TypeScript checks passed. Build imports the production
host components and backend serves the production SDK, middleware, routes,
registry, context/session services and storage readers. Test-only fixtures own
the data catalog and waiting-free runtime; uvicorn lifespan is disabled to
avoid desktop/MCP/background startup side effects. Ports 8191–8194 are owned by
the suite; existing servers are never reused. Run outputs remain ignored under
`.workflow/local/browser-final.log` and `.workflow/local/panel-browser-results/`.

## Limits and integration handoff

This is automated Chromium integration evidence, not a manually driven complete
SciStudio app workflow or Electron native OS-save-dialog evidence. The maximize
button in the test host consumes the production snapshot/session contract;
full application tab controls are separately covered by A2 tests. No production
fixes were needed during this browser run. Initial failures were fixture setup
(directory/id matching and registry installation) and an opaque fetch-observation
limitation, corrected without changing production contracts or assertions.

TODO(#2293): Browser WS-confirm extension is outside the immediate completed
matrix handoff per owner direction to open the PR now; A1/A2 automated WS and
frontend acknowledgement tests remain the evidence for that behavior.
Followup: https://github.com/jiazhenz026/SciStudio/issues/2293.

The scoped local gate records only the checks actually executed. Sentrux MCP
is unavailable. Full integration gate, pre-PR reconciliation, CI, issue closure
and release status belong to the manager and are not claimed by this report.
Phases B–D remain unstarted (#2294, #2295, #2354); 0.6 removal stays in #2288.
