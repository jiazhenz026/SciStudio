/**
 * The backend OpenAPI contract, for validating frontend test mocks (#2297).
 *
 * Frontend tests used to return hand-written payloads that nobody checked
 * against the backend, so a renamed or removed field left every test green.
 * This module loads the committed snapshot `tests/contracts/openapi.json` —
 * regenerated from the backend by `tests/contracts/openapi_snapshot.py` and
 * kept current by `tests/contracts/test_openapi_snapshot.py` — resolves a
 * request's method and URL to its OpenAPI operation, and validates JSON request
 * and response bodies with ajv (JSON Schema 2020-12, the OpenAPI 3.1 dialect).
 *
 * Tests normally use it through `mockBackend()`; `checkMockBody()` is exported
 * for mocks that do not go through `fetch`.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

import type { ErrorObject, ValidateFunction } from "ajv";
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

const HTTP_METHODS: readonly HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE"];

interface MediaTypeObject {
  schema?: unknown;
}

interface ResponseObject {
  content?: Record<string, MediaTypeObject>;
}

interface OperationObject {
  operationId?: string;
  requestBody?: { content?: Record<string, MediaTypeObject> };
  responses?: Record<string, ResponseObject>;
}

interface OpenApiDocument {
  paths: Record<string, Record<string, OperationObject>>;
  components?: Record<string, unknown>;
}

/** One backend endpoint, as the contract describes it. */
export interface ContractOperation {
  method: HttpMethod;
  /** OpenAPI path template, e.g. `/api/blocks/{block_type}/schema`. */
  template: string;
  /** `"<METHOD> <template>"`, the key used in messages. */
  key: string;
  operation: OperationObject;
}

interface IndexedOperation extends ContractOperation {
  pattern: RegExp;
  literalSegments: number;
  params: number;
}

const SNAPSHOT_RELATIVE = join("tests", "contracts", "openapi.json");
const CONTRACT_ID = "https://scistudio.test/openapi.json";
const JSON_MEDIA_TYPE = "application/json";

export function isHttpMethod(value: string): value is HttpMethod {
  return (HTTP_METHODS as readonly string[]).includes(value);
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
}

function compileTemplate(template: string): { pattern: RegExp; literal: number; params: number } {
  let literal = 0;
  let params = 0;
  const body = template
    .split("/")
    .map((segment) => {
      if (!segment.includes("{")) {
        literal += 1;
        return escapeRegExp(segment);
      }
      params += 1;
      return segment
        .split(/(\{[^}]+\})/)
        .map((part) => (/^\{[^}]+\}$/.test(part) ? "[^/]+" : escapeRegExp(part)))
        .join("");
    })
    .join("/");
  return { pattern: new RegExp(`^${body}$`), literal, params };
}

/** Rewrite document-relative `$ref`s so they resolve inside the registered contract. */
function anchorRefs(node: unknown): unknown {
  if (Array.isArray(node)) return node.map(anchorRefs);
  if (node && typeof node === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(node)) {
      out[key] =
        key === "$ref" && typeof value === "string" && value.startsWith("#/")
          ? `${CONTRACT_ID}${value}`
          : anchorRefs(value);
    }
    return out;
  }
  return node;
}

function collectFormats(node: unknown, found: Set<string>): void {
  if (Array.isArray(node)) {
    node.forEach((item) => collectFormats(item, found));
  } else if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      if (key === "format" && typeof value === "string") found.add(value);
      else collectFormats(value, found);
    }
  }
}

function formatErrors(errors: ErrorObject[] | null | undefined): string[] {
  return (errors ?? []).map((error) => {
    const where = error.instancePath || "(root)";
    // ajv already names a missing property in its message; enum failures do
    // not list the allowed values, so add them.
    const detail =
      "allowedValues" in error.params ? ` ${JSON.stringify(error.params.allowedValues)}` : "";
    return `${where} ${error.message ?? "is invalid"}${detail}`;
  });
}

/** The loaded contract: endpoint lookup plus body validation. */
export class OpenApiContract {
  private readonly operations: IndexedOperation[];
  private readonly ajv: Ajv2020;
  private readonly validators = new Map<string, ValidateFunction | null>();

  constructor(document: OpenApiDocument) {
    this.ajv = new Ajv2020({ strict: false, allErrors: true });
    addFormats(this.ajv);
    const formats = new Set<string>();
    collectFormats(document, formats);
    for (const format of formats) {
      if (!(format in this.ajv.formats)) this.ajv.addFormat(format, true);
    }
    this.ajv.addSchema({ $id: CONTRACT_ID, components: document.components ?? {} });

    this.operations = [];
    for (const [template, item] of Object.entries(document.paths)) {
      for (const [rawMethod, operation] of Object.entries(item)) {
        const method = rawMethod.toUpperCase();
        if (!isHttpMethod(method)) continue;
        const { pattern, literal, params } = compileTemplate(template);
        this.operations.push({
          method,
          template,
          key: `${method} ${template}`,
          operation,
          pattern,
          literalSegments: literal,
          params,
        });
      }
    }
    // Most specific first: a literal segment beats a parameter, so
    // `/api/data/open-as` wins over `/api/data/{data_ref}`.
    this.operations.sort(
      (a, b) =>
        b.literalSegments - a.literalSegments ||
        a.params - b.params ||
        b.template.length - a.template.length,
    );
  }

  /** Find the operation a request would reach, or `undefined` if the backend has none. */
  resolve(method: HttpMethod, pathOrUrl: string): ContractOperation | undefined {
    const pathname = new URL(pathOrUrl, "http://contract.test").pathname;
    return this.operations.find((op) => op.method === method && op.pattern.test(pathname));
  }

  /** Validate a JSON request body. Returns human-readable errors, empty when valid. */
  checkRequestBody(op: ContractOperation, body: unknown): string[] {
    const schema = op.operation.requestBody?.content?.[JSON_MEDIA_TYPE]?.schema;
    return this.check(`${op.key} request`, schema, body);
  }

  /** Validate a JSON response body for `status`. Returns errors, empty when valid. */
  checkResponseBody(op: ContractOperation, status: number, body: unknown): string[] {
    const responses = op.operation.responses ?? {};
    const response =
      responses[String(status)] ?? responses[`${Math.floor(status / 100)}XX`] ?? responses.default;
    if (!response) {
      if (status >= 200 && status < 300) {
        return [`(status) ${op.key} declares no ${status} response`];
      }
      return [];
    }
    const schema = response.content?.[JSON_MEDIA_TYPE]?.schema;
    return this.check(`${op.key} ${status} response`, schema, body);
  }

  private check(cacheKey: string, schema: unknown, body: unknown): string[] {
    if (schema === undefined) return [];
    let validate = this.validators.get(cacheKey);
    if (validate === undefined) {
      const empty =
        typeof schema === "object" && schema !== null && Object.keys(schema).length === 0;
      validate = empty ? null : this.ajv.compile(anchorRefs(schema) as object);
      this.validators.set(cacheKey, validate);
    }
    if (validate === null) return [];
    return validate(body) ? [] : formatErrors(validate.errors);
  }
}

let cached: OpenApiContract | null = null;

/**
 * Walk up from the test runner's working directory (`frontend/` under
 * `npm test`) to the repository's snapshot. `import.meta.url` is not a
 * `file:` URL under the jsdom environment, so it cannot anchor the path.
 */
function findSnapshot(): string {
  let dir = resolve(process.cwd());
  for (;;) {
    const candidate = join(dir, SNAPSHOT_RELATIVE);
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) {
      throw new Error(
        `OpenAPI contract snapshot ${SNAPSHOT_RELATIVE} not found above ${process.cwd()}`,
      );
    }
    dir = parent;
  }
}

/** The contract from `tests/contracts/openapi.json`, loaded once per test worker. */
export function loadContract(): OpenApiContract {
  if (cached === null) {
    const text = readFileSync(findSnapshot(), "utf8");
    cached = new OpenApiContract(JSON.parse(text) as OpenApiDocument);
  }
  return cached;
}

/**
 * Check a mocked body against the contract without going through `fetch`
 * (for mocks installed some other way). Throws a readable error when the
 * endpoint does not exist or the body does not match.
 */
export function checkMockBody(key: string, body: unknown, status = 200): void {
  const [rawMethod = "", ...rest] = key.trim().split(/\s+/);
  const method = rawMethod.toUpperCase();
  const path = rest.join(" ");
  if (!isHttpMethod(method))
    throw new Error(`checkMockBody: "${key}" does not start with an HTTP method`);
  const contract = loadContract();
  const op = contract.resolve(method, path);
  if (!op) throw new Error(`checkMockBody: "${key}" is not an endpoint of the backend contract`);
  const errors = contract.checkResponseBody(op, status, body);
  if (errors.length > 0) {
    throw new Error(
      `checkMockBody: mock for ${op.key} does not match the backend:\n  ${errors.join("\n  ")}`,
    );
  }
}
