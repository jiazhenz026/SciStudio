/**
 * `mockBackend()` — a contract-checked fake backend for frontend tests (#2297).
 *
 * Replaces `fetch` so the real `lib/api` client code runs, and answers each
 * request from the routes a test declares. Every declared route must be an
 * endpoint of the backend (`tests/contracts/openapi.json`), and every JSON body
 * it returns — and every JSON body the client sends — must match that
 * endpoint's schema. A mismatch, an undeclared call, or a call to an endpoint
 * the backend does not have fails the test with a message naming the endpoint
 * and the offending field.
 *
 * ```ts
 * const backend = mockBackend({
 *   "GET /api/ai/availability": READY,                    // static body, checked now
 *   "POST /api/plots/run": (req) => ({ ...RUN, ...req.body as object }), // checked per call
 *   "DELETE /api/plots/{name}": reply(204),
 * });
 * afterEach(() => backend.restore());
 * ```
 */
import { vi, type Mock } from "vitest";

import { isHttpMethod, loadContract, type ContractOperation, type HttpMethod } from "./openapi";

/** Thrown when a mock or a request breaks the backend contract. */
export class ContractViolation extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractViolation";
  }
}

const REPLY = Symbol("mockBackend.reply");

/** An explicit status (and optional JSON body) for a route. */
export interface MockReply {
  readonly [REPLY]: true;
  status: number;
  body?: unknown;
}

/** Answer with `status` and an optional JSON body. */
export function reply(status: number, body?: unknown): MockReply {
  return { [REPLY]: true, status, body };
}

function isReply(value: unknown): value is MockReply {
  return typeof value === "object" && value !== null && REPLY in value;
}

/** What a route handler sees. */
export interface MockRequest {
  method: HttpMethod;
  /** Path without the query string, e.g. `/api/plots/plot%20one`. */
  path: string;
  query: URLSearchParams;
  /** Parsed JSON body, or the raw body when it is not JSON. */
  body: unknown;
  operation: ContractOperation;
}

/** A route: a body (answered with 200), a `reply()`, or a function returning either. */
export type MockHandler =
  | MockReply
  | ((request: MockRequest) => unknown)
  | string
  | number
  | boolean
  | null
  | object;

/** A request the fake backend answered. */
export interface RecordedCall {
  /** The route key that answered, as declared by the test. */
  route: string;
  method: HttpMethod;
  path: string;
  /** Path plus query string, as the client requested it. */
  url: string;
  query: URLSearchParams;
  body: unknown;
  status: number;
}

export interface MockBackend {
  /** Every answered request, in order. */
  readonly calls: RecordedCall[];
  /** The installed fake `fetch`; it records a call before it is answered. */
  readonly fetch: Mock<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>;
  /** The answered requests for one declared route key. */
  callsTo(route: string): RecordedCall[];
  /** Put the previous `fetch` back. */
  restore(): void;
}

interface Route {
  key: string;
  method: HttpMethod;
  path: string;
  concrete: boolean;
  operation: ContractOperation;
  handler: MockHandler;
}

function parseKey(key: string): { method: HttpMethod; path: string } {
  const [rawMethod = "", ...rest] = key.trim().split(/\s+/);
  const method = rawMethod.toUpperCase();
  const path = rest.join(" ");
  if (!isHttpMethod(method) || !path.startsWith("/")) {
    throw new ContractViolation(`mockBackend: route "${key}" must look like "GET /api/..."`);
  }
  // A template route keeps its `{param}` braces; URL parsing would encode them.
  // A concrete route is encoded the way the client's request URL will be.
  const bare = path.split("?")[0] ?? path;
  return { method, path: isTemplate(bare) ? bare : new URL(bare, "http://contract.test").pathname };
}

function isTemplate(path: string): boolean {
  return /\{[^}]+\}/.test(path);
}

function assertResponse(route: Route, status: number, body: unknown): void {
  const errors = loadContract().checkResponseBody(route.operation, status, body);
  if (errors.length > 0) {
    throw new ContractViolation(
      `mockBackend: the mock for "${route.key}" does not match the backend ` +
        `${route.operation.key} ${status} response:\n  ${errors.join("\n  ")}\n` +
        "Fix the test data, or if the backend really returns this, the backend and frontend disagree.",
    );
  }
}

function toStatusAndBody(value: unknown): { status: number; body: unknown } {
  return isReply(value) ? { status: value.status, body: value.body } : { status: 200, body: value };
}

function readRequest(
  input: RequestInfo | URL,
  init?: RequestInit,
): {
  method: string;
  url: URL;
  rawBody: unknown;
} {
  const isRequest = typeof Request !== "undefined" && input instanceof Request;
  const href = isRequest ? input.url : input instanceof URL ? input.href : String(input);
  const method = (init?.method ?? (isRequest ? input.method : "GET")).toUpperCase();
  return { method, url: new URL(href, "http://contract.test"), rawBody: init?.body };
}

function parseBody(raw: unknown): unknown {
  if (typeof raw !== "string") return raw;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

function toResponse(status: number, body: unknown): Response {
  const text = status === 204 || body === undefined ? null : JSON.stringify(body);
  return new Response(text, {
    status,
    headers: text === null ? {} : { "Content-Type": "application/json" },
  });
}

/**
 * Install a contract-checked fake backend. Static bodies are checked when the
 * routes are declared; function handlers are checked on every call.
 */
export function mockBackend(routes: Record<string, MockHandler>): MockBackend {
  const contract = loadContract();
  const table: Route[] = Object.entries(routes).map(([key, handler]) => {
    const { method, path } = parseKey(key);
    const operation = contract.resolve(method, path);
    if (!operation) {
      throw new ContractViolation(
        `mockBackend: "${key}" is not an endpoint of the backend (tests/contracts/openapi.json).`,
      );
    }
    const route: Route = {
      key,
      method,
      path,
      concrete: !isTemplate(path),
      operation,
      handler,
    };
    if (typeof handler !== "function") {
      const { status, body } = toStatusAndBody(handler);
      if (status >= 200 && status < 300 && status !== 204) assertResponse(route, status, body);
    }
    return route;
  });

  const calls: RecordedCall[] = [];
  const previousFetch = globalThis.fetch;

  const fakeFetch = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const { method: rawMethod, url, rawBody } = readRequest(input, init);
      if (!isHttpMethod(rawMethod)) {
        throw new ContractViolation(`mockBackend: unsupported method ${rawMethod} ${url.pathname}`);
      }
      const method = rawMethod;
      const operation = contract.resolve(method, url.pathname);
      if (!operation) {
        throw new ContractViolation(
          `mockBackend: the client called ${method} ${url.pathname}, which is not an endpoint of the backend.`,
        );
      }
      // An exact concrete route wins over a template route for the same endpoint.
      const candidates = table.filter(
        (r) => r.method === method && r.operation.key === operation.key,
      );
      const route =
        candidates.find((r) => r.concrete && r.path === url.pathname) ??
        candidates.find((r) => !r.concrete);
      if (!route) {
        throw new ContractViolation(
          `mockBackend: unmocked call ${method} ${url.pathname}${url.search} (${operation.key}). ` +
            "Declare it in mockBackend({...}).",
        );
      }

      const body = parseBody(rawBody);
      if (body !== undefined && typeof body !== "string" && !(body instanceof FormData)) {
        const requestErrors = contract.checkRequestBody(operation, body);
        if (requestErrors.length > 0) {
          throw new ContractViolation(
            `mockBackend: the client sent a body the backend would reject for ${operation.key}:\n  ` +
              requestErrors.join("\n  "),
          );
        }
      }

      const request: MockRequest = {
        method,
        path: url.pathname,
        query: url.searchParams,
        body,
        operation,
      };
      const produced =
        typeof route.handler === "function" ? await route.handler(request) : route.handler;
      const { status, body: responseBody } = toStatusAndBody(produced);
      if (status >= 200 && status < 300 && status !== 204)
        assertResponse(route, status, responseBody);

      calls.push({
        route: route.key,
        method,
        path: url.pathname,
        url: url.pathname + url.search,
        query: url.searchParams,
        body,
        status,
      });
      return toResponse(status, responseBody);
    },
  );

  globalThis.fetch = fakeFetch as unknown as typeof fetch;

  return {
    calls,
    fetch: fakeFetch,
    callsTo: (key: string) => calls.filter((call) => call.route === key),
    restore: () => {
      globalThis.fetch = previousFetch;
    },
  };
}
