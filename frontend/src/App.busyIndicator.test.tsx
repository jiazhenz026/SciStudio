/**
 * #2019 — the global busy indicator must outrank every overlay in the app.
 *
 * The pill carried no z-index at all, so it landed on the base stacking level
 * while modals sit at z-50 or z-[9999], most of them over a `backdrop-blur`.
 * The one affordance that says "still working" therefore rendered blurred and
 * underneath the very dialog that was waiting on that work.
 *
 * Asserting `z-[10000]` literally would only restate the source. This guard
 * instead reads every z-index in the frontend and pins the *relationship*: the
 * indicator outranks all of them. Adding a new overlay above it fails here.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// vitest runs with the frontend package as its working directory.
const SRC_DIR = join(process.cwd(), "src");
const BUSY_TESTID = "global-busy-indicator";

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "node_modules" ? [] : sourceFiles(full);
    }
    // Tests are not rendered UI, and they quote z-indexes in prose/fixtures.
    if (/\.(test|spec)\.tsx?$/.test(entry.name)) return [];
    return /\.(tsx?|css)$/.test(entry.name) ? [full] : [];
  });
}

/** Drop comments — prose about z-indexes is not a stacking declaration. */
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/** Tailwind `z-50` / `z-[9999]` -> numeric stacking levels. */
function zIndexesIn(text: string): number[] {
  // No trailing \b: the arbitrary-value form ends in `]`, and `]` followed by
  // a space is not a word boundary.
  const matches = text.matchAll(/\bz-(?:\[(\d+)\]|(\d+)\b)/g);
  return [...matches].map((m) => Number(m[1] ?? m[2]));
}

/** The className of the element carrying the busy-indicator test id. */
function busyIndicatorClassName(): string {
  const app = readFileSync(join(SRC_DIR, "App.tsx"), "utf8");
  const testIdAt = app.indexOf(`data-testid="${BUSY_TESTID}"`);
  expect(testIdAt, `no element carrying data-testid="${BUSY_TESTID}" in App.tsx`).toBeGreaterThan(
    -1,
  );

  // Attributes are alphabetised, so className is the nearest one before the
  // test id on the same element.
  const preceding = app.slice(Math.max(0, testIdAt - 500), testIdAt);
  const className = preceding.match(/className="([^"]*)"/g)?.pop();
  expect(className, "busy indicator has no className").toBeTruthy();
  return (className as string).slice('className="'.length, -1);
}

describe("global busy indicator layering (#2019)", () => {
  it("declares a stacking level at all", () => {
    expect(zIndexesIn(busyIndicatorClassName())).toHaveLength(1);
  });

  it("outranks every other z-index in the frontend", () => {
    const busyClass = busyIndicatorClassName();
    const busyZ = zIndexesIn(busyClass)[0];

    const others = sourceFiles(SRC_DIR).flatMap((file) => {
      const text = stripComments(readFileSync(file, "utf8"));
      // Drop the indicator's own declaration before ranking the rest.
      return zIndexesIn(text.split(busyClass).join("")).map((z) => ({ file, z }));
    });

    expect(others.length, "expected to find overlay z-indexes to compare against").toBeGreaterThan(
      0,
    );

    const highest = others.reduce((a, b) => (b.z > a.z ? b : a));
    expect(
      busyZ,
      `busy indicator is z-${busyZ} but ${highest.file} declares z-${highest.z}; ` +
        "an overlay would paint over the busy pill",
    ).toBeGreaterThan(highest.z);
  });

  it("does not intercept clicks now that it sits on top of everything", () => {
    expect(busyIndicatorClassName()).toContain("pointer-events-none");
  });
});
