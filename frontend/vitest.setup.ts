import { expect, vi } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";

expect.extend(matchers);

vi.mock("react-plotly.js", () => ({
  default: () => null,
}));

/*
 * jsdom has no reader and no motion, so every media query about motion
 * answers "reduce" here. The tutorial dialogue types its lines out a
 * character at a time in a real browser (ADR-053, `useTypewriter`); under the
 * runner it must put the whole line up at once, or every assertion about
 * what a step says would be racing an interval.
 *
 * Assigned unconditionally: jsdom does provide a `matchMedia` that reports
 * `matches: false` for everything, which is the wrong answer rather than a
 * missing one. The two xterm suites install their own afterwards.
 */
window.matchMedia = ((query: string) => ({
  matches: /prefers-reduced-motion/.test(query),
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

if (!window.URL.createObjectURL) {
  window.URL.createObjectURL = vi.fn(() => "blob:mock");
}

// Node 26 exposes a global `localStorage` that throws unless --localstorage-file
// is given, and it shadows jsdom's window.localStorage. Install a simple
// in-memory storage so storage-backed app code (e.g. resetAppStore) works
// under the test runner regardless of the host Node version.
class MemoryStorage {
  private store = new Map<string, string>();
  get length() {
    return this.store.size;
  }
  clear() {
    this.store.clear();
  }
  getItem(key: string) {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null;
  }
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  const storage = new MemoryStorage();
  for (const target of [globalThis, typeof window !== "undefined" ? window : undefined]) {
    if (!target) continue;
    try {
      Object.defineProperty(target, name, {
        value: storage,
        configurable: true,
        writable: true,
      });
    } catch {
      /* property is locked down; best effort under the test runner */
    }
  }
}

/*
 * jsdom implements no `ResizeObserver`, and `@xyflow/react` constructs one
 * unconditionally when a flow mounts — so any suite that renders the workflow
 * canvas or ADR-054's dependency-graph view throws on mount rather than
 * failing an assertion. Installed here for the same reason `matchMedia` is:
 * it is an environment gap, not a component's problem, and every suite that
 * mounts a flow would otherwise carry the same six lines.
 *
 * A no-op: it never fires, so nothing observes a size change under the runner
 * and a component that only resizes in response to one behaves as it does with
 * a container that never changed size. Defined only when absent, so the
 * terminal harness's own `vi.stubGlobal("ResizeObserver", ...)` — which does
 * fire, on purpose — still wins.
 */
if (!("ResizeObserver" in globalThis)) {
  class NoopResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  for (const target of [globalThis, typeof window !== "undefined" ? window : undefined]) {
    if (!target) continue;
    Object.defineProperty(target, "ResizeObserver", {
      value: NoopResizeObserver,
      configurable: true,
      writable: true,
    });
  }
}
