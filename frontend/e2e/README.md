# SciStudio Playwright E2E Discovery Harness

This harness runs browser-level discovery scenarios against the real Vite GUI
and FastAPI backend. The initial issue #1384 suite is non-blocking: a failure
can expose a product bug while still producing useful evidence.

## Commands

```bash
cd frontend
npm run test:e2e:smoke
npm run test:e2e
```

The scripts use `npm exec --package @playwright/test` through
`e2e/support/run-playwright.mjs` so the harness can land
without changing `frontend/package-lock.json`. For local runs, install the
browser once if Playwright asks for it:

```bash
cd frontend
npm exec --yes --package @playwright/test@1.57.0 -- node e2e/support/run-playwright.mjs install chromium
```

## Artifacts

By default artifacts are written under `frontend/.e2e-artifacts/`.

- `service-logs/backend.log`
- `service-logs/frontend.log`
- `test-results/**`
- `playwright-report/**`
- `results.json`
- `results.xml`

Each test using `e2e/support/test.ts` also writes browser console logs, failed
network responses, request failures, and an isolated project snapshot.

## Fixtures

`e2e/fixtures/syntheticFluorescence.ts` creates a deterministic grayscale PNG
with several pseudo-fluorescent spots. `e2e/fixtures/minimalWorkflow.ts` writes
a minimal workflow fixture:

```text
load image -> threshold -> save mask
```

The fixture uses real project paths and real workflow YAML. It intentionally
does not patch frontend state or mock product APIs.

## Failure Classification

Discovery failures should be classified before fixing:

- Product bug: the GUI/API/runtime launched, the test followed a real user path,
  and the product returned wrong behavior or an error.
- Test bug: selectors, fixture shape, waits, or assertions are inconsistent with
  the documented product contract.
- Infra flake: service startup, browser installation, ports, or machine
  resources failed before product behavior was meaningfully exercised.

CI uploads artifacts for all three cases and keeps the E2E discovery job
non-blocking until the suite is promoted to a required check.
