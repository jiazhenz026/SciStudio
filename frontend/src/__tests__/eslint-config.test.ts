import { describe, it, expect } from "vitest";
import { ESLint } from "eslint";

const linter = new ESLint({ cwd: process.cwd() });

async function lintAs(filePath: string, source: string) {
  const results = await linter.lintText(source, { filePath });
  return results[0].messages.map((m) => m.ruleId).filter((r): r is string => r !== null);
}

describe("frontend ESLint configuration (#1412)", () => {
  it("loads the project flat config without parser errors", async () => {
    const cfg = await linter.calculateConfigForFile("src/main.tsx");
    expect(cfg).toBeDefined();
  });

  it("flags loose equality (eqeqeq) on a non-waivered file", async () => {
    const source = `export const x = (a: number, b: number) => a == b;\n`;
    const ruleIds = await lintAs("src/__tests__/eslint-fixture-eqeqeq.ts", source);
    expect(ruleIds).toContain("eqeqeq");
  });

  it("flags react-hooks/rules-of-hooks on a non-waivered file", async () => {
    const source = `import { useState } from "react";
export function Bad({ early }: { early: boolean }) {
  if (early) return null;
  const [count] = useState(0);
  return count;
}
`;
    const ruleIds = await lintAs("src/__tests__/eslint-fixture-hooks.tsx", source);
    expect(ruleIds).toContain("react-hooks/rules-of-hooks");
  });

  it("flags @typescript-eslint/no-explicit-any on a non-waivered file", async () => {
    // Use a path outside __tests__/ since the test-override turns no-explicit-any off there.
    const source = `export const fn = (x: any) => x;\n`;
    const ruleIds = await lintAs("src/eslint-fixture-any.ts", source);
    expect(ruleIds).toContain("@typescript-eslint/no-explicit-any");
  });

  it("flags max-lines on a non-waivered file longer than 500 lines", async () => {
    const lines = Array.from({ length: 520 }, (_, i) => `export const v${i} = ${i};`);
    const source = lines.join("\n") + "\n";
    const ruleIds = await lintAs("src/__tests__/eslint-fixture-maxlines.ts", source);
    expect(ruleIds).toContain("max-lines");
  });

  it("does NOT flag max-lines on App.tsx (#1422 waiver)", async () => {
    const lines = Array.from({ length: 520 }, (_, i) => `export const v${i} = ${i};`);
    const source = lines.join("\n") + "\n";
    const ruleIds = await lintAs("src/App.tsx", source);
    expect(ruleIds).not.toContain("max-lines");
  });

  it("does NOT flag react-hooks/rules-of-hooks on BlockNode.tsx (#1420 waiver)", async () => {
    const source = `import { useState } from "react";
export function Bad({ early }: { early: boolean }) {
  if (early) return null;
  const [count] = useState(0);
  return count;
}
`;
    const ruleIds = await lintAs("src/components/nodes/BlockNode.tsx", source);
    expect(ruleIds).not.toContain("react-hooks/rules-of-hooks");
  });
});
