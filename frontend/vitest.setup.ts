import { expect, vi } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";

expect.extend(matchers);

vi.mock("react-plotly.js", () => ({
  default: () => null,
}));

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
