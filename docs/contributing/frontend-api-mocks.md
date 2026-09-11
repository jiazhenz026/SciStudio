---
title: "Mocking The Backend In Frontend Tests"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs: []
language_source: en
---

# Mocking The Backend In Frontend Tests

## 1. Why

A frontend test that invents a backend response only proves the frontend agrees
with itself. When the backend renames or drops a field, every such test stays
green and the break shows up at runtime. Frontend tests therefore answer backend
calls with `mockBackend()`, which checks every mocked body against the backend's
OpenAPI document (#2297).

## 2. Using `mockBackend()`

`frontend/src/__tests__/contract/mockBackend.ts` replaces `fetch`, so the real
`lib/api` client code runs. Declare the routes the test expects:

```ts
import { mockBackend, reply, type MockBackend } from "../../__tests__/contract/mockBackend";

let backend: MockBackend | undefined;
afterEach(() => backend?.restore());

it("loads the plot list", async () => {
  backend = mockBackend({
    "GET /api/plots": { count: 0, plots: [], warnings: [] }, // checked when declared
    "POST /api/plots/run": (req) => runResponseFor(req.body), // checked on every call
    "DELETE /api/plots/{plot_id}": reply(204),               // template route
  });

  await dataApi.listPlots({ workflowId: "main" });

  expect(backend.calls[0]?.url).toBe("/api/plots?workflow_id=main");
});
```

- A route key is `"<METHOD> <path>"`. Use the concrete path or the OpenAPI
  template; an exact concrete route wins over a template for the same endpoint.
- `reply(status, body?)` sets an explicit status. Non-2xx bodies are passed
  through unchecked, so error handling can be tested with any `detail`.
- `backend.calls` records each answered request (`method`, `path`, `url`,
  `query`, parsed `body`, `status`). `backend.fetch` is the raw `vi.fn` for
  call counts, including calls that are still in flight.
- The test fails when a mocked response does not match the endpoint's schema,
  when the client sends a request body the backend would reject, when the
  client calls a route the test did not declare, or when a route does not exist
  in the backend at all.
- For a mock that does not go through `fetch`, call
  `checkMockBody("GET /api/...", body)` from `contract/openapi.ts`.

Do not `vi.mock` the `lib/api` client in new tests. ESLint rejects it
(`frontend/eslint.config.js`). Files that already do are listed there and are
being migrated under #2300.

## 3. The contract snapshot

The schemas come from `tests/contracts/openapi.json`, a normalized copy of
`create_app().openapi()`. Descriptions, examples, titles, and operation ids are
stripped; everything that defines the wire shape is kept.

`tests/contracts/test_openapi_snapshot.py` regenerates the document and fails
when the backend no longer matches it, naming the operations and schemas that
moved. After an intended API change, refresh it and fix any frontend mocks the
new contract rejects:

```bash
python tests/contracts/openapi_snapshot.py --write
cd frontend && npx vitest run
```

A mock the contract rejects means either the test data is stale (fix the test)
or the frontend and backend really disagree (fix the product, and say which in
the PR).

## 4. Limits

The contract is only as precise as the backend's declared models. Endpoints that
return an untyped `dict`, and file or stream endpoints documented as empty JSON,
accept any body; #2301 tracks giving them real response models. Transport-level
tests (timeouts, base path, logging reflux) keep stubbing `fetch` directly,
because they test `fetch` behaviour rather than an endpoint's payload.
