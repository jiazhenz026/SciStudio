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

  it("flags max-lines on a non-waivered file longer than 750 lines", async () => {
    // #1426 Wave 4 raised the threshold from 500 → 750 to fit the
    // post-#1422 codebase reality (orchestrator files still > 500 after
    // splitting into .parts/ siblings). Regression guard: any file > 750
    // LOC must still lint-fail.
    const lines = Array.from({ length: 770 }, (_, i) => `export const v${i} = ${i};`);
    const source = lines.join("\n") + "\n";
    const ruleIds = await lintAs("src/__tests__/eslint-fixture-maxlines.ts", source);
    expect(ruleIds).toContain("max-lines");
  });

  it("DOES flag max-lines on App.tsx (#1422 waiver retired)", async () => {
    // #1426 Wave 4 stripped the GOD_FILE_SIZE_WAIVERS block, so every file
    // — including App.tsx — is now under the global max-lines limit (750).
    // A regression that bloats App.tsx past 750 LOC MUST now lint-fail.
    const lines = Array.from({ length: 770 }, (_, i) => `export const v${i} = ${i};`);
    const source = lines.join("\n") + "\n";
    const ruleIds = await lintAs("src/App.tsx", source);
    expect(ruleIds).toContain("max-lines");
  });

  it("DOES flag react-hooks/rules-of-hooks on BlockNode.tsx (#1420 waiver retired)", async () => {
    // The waiver was retired in #1420/#1421: BlockNode.tsx is back under the
    // default rules-of-hooks enforcement now that the conditional-hook
    // refactor (extract InlineTextInputField) lets hooks live at the top
    // level of every component in the file. A regression that re-introduces
    // a hook after an early return MUST now lint-fail on this exact path.
    const source = `import { useState } from "react";
export function Bad({ early }: { early: boolean }) {
  if (early) return null;
  const [count] = useState(0);
  return count;
}
`;
    const ruleIds = await lintAs("src/components/nodes/BlockNode.tsx", source);
    expect(ruleIds).toContain("react-hooks/rules-of-hooks");
  });

  it("DOES flag react-hooks/exhaustive-deps on App.tsx (#1421 waiver retired)", async () => {
    // The waiver was retired in #1420/#1421: every App.tsx hook either now
    // includes the missing dep or carries an inline disable with rationale.
    // A regression that re-introduces a bare missing-dep MUST now lint-fail.
    const source = `import { useEffect } from "react";
export function Bad({ value }: { value: number }) {
  useEffect(() => { console.log(value); }, []);
  return null;
}
`;
    const ruleIds = await lintAs("src/App.tsx", source);
    expect(ruleIds).toContain("react-hooks/exhaustive-deps");
  });
});
