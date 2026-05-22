import js from "@eslint/js";
import tseslint from "typescript-eslint";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import prettier from "eslint-config-prettier";
import globals from "globals";

// Baseline waivers established in #1412 (initial ESLint introduction).
// Each waiver below points at the followup issue that will retire it.

// #1422 — god files exceeding max-lines (500 LOC).
const GOD_FILE_SIZE_WAIVERS = [
  "src/App.tsx",
  "src/components/nodes/BlockNode.tsx",
  "src/components/nodes/BlockNode.test.tsx",
  "src/components/DataPreview.tsx",
  "src/components/BottomPanel.tsx",
  "src/components/BottomPanel.test.tsx",
  "src/components/Lineage/RunDetail.tsx",
  "src/lib/api.ts",
  "src/components/Git/ConflictMarkerDecoration.ts",
];

// #1413 — functions exceeding max-lines-per-function (150 LOC).
const MAX_LINES_PER_FN_WAIVERS = [
  "src/components/AIChat/SetupScreen.tsx",
  "src/components/AIChat/TerminalTabs.tsx",
  "src/components/CodeEditor.tsx",
  "src/components/DataRouterModal.tsx",
  "src/components/Git/BranchPicker.tsx",
  "src/components/Git/CommitDialog.tsx",
  "src/components/Git/GitGraph/GraphSVG.tsx",
  "src/components/Git/GitGraph/laneAssign.ts",
  "src/components/Git/GitHistoryList.tsx",
  "src/components/Git/MergeFlow.tsx",
  "src/components/Lineage/RerunDialog.tsx",
  "src/components/ProjectDialog.tsx",
  "src/components/ProjectTree.tsx",
  "src/components/Toolbar.tsx",
  "src/components/WorkflowCanvas.tsx",
  "src/hooks/useWebSocket.ts",
  "src/store/tabSlice.ts",
  "src/store/workflowSlice.ts",
];

// #1414 — cyclomatic complexity above 15.
const COMPLEXITY_WAIVERS = [
  "src/components/Git/GitGraph/GraphSVG.tsx",
  "src/components/Git/GitGraph/edgeRouter.ts",
  "src/components/Git/GitGraph/laneAssign.ts",
  "src/components/Git/GitHistoryList.tsx",
  "src/components/Git/MergeFlow.tsx",
  "src/components/PortEditor/CapabilityDropdown.tsx",
  "src/components/Toolbar.tsx",
  "src/components/WorkflowCanvas.tsx",
  "src/hooks/useWebSocket.ts",
  "src/store/executionSlice.ts",
];

// #1415 — loose equality (== / !=).
const EQEQEQ_WAIVERS = [
  "src/App.tsx",
  "src/components/BottomPanel.tsx",
  "src/components/DataPreview.tsx",
  "src/components/DataRouterModal.tsx",
  "src/components/PairEditorModal.tsx",
  "src/components/PortEditorTable.tsx",
  "src/components/ProjectTree.tsx",
  "src/components/nodes/BlockNode.tsx",
  "src/store/executionSlice.ts",
];

// #1416 — test files using `import('...').T` instead of `import type`.
const CONSISTENT_TYPE_IMPORT_WAIVERS = [
  "src/components/Git/__tests__/ConflictResolveView.test.tsx",
  "src/components/Git/__tests__/MergeFlow.test.tsx",
  "src/components/Lineage/__tests__/LineageTab.test.tsx",
  "src/components/Lineage/__tests__/RerunDialog.test.tsx",
  "src/components/Lineage/__tests__/RunDetail.test.tsx",
  "src/components/Lineage/__tests__/RunsList.test.tsx",
  "src/components/__tests__/ProjectTree.test.tsx",
  "src/hooks/useWebSocket.test.ts",
  "src/lib/fileExistence.test.ts",
  "src/store/__tests__/gitSlice.test.ts",
  "src/store/__tests__/lineageSlice.test.ts",
  "src/store/__tests__/tabState.test.ts",
];

// #1417 — unused vars / imports.
const NO_UNUSED_VARS_WAIVERS = [
  "src/App.tsx",
  "src/components/DataRouterModal.tsx",
  "src/components/Lineage/RunsList.tsx",
  "src/components/Lineage/__tests__/RunsList.test.tsx",
  "src/components/PairEditorModal.tsx",
  "src/hooks/useWebSocket.ts",
  "src/store/workflowSlice.ts",
];

export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "coverage/**",
      "**/*.config.js",
      "**/*.config.ts",
      "src/scistudio/api/static/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    settings: {
      react: { version: "18.3" },
    },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      "react-hooks/exhaustive-deps": "error",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      eqeqeq: ["error", "always"],
      complexity: ["error", 15],
      "max-lines": ["error", { max: 500, skipBlankLines: true, skipComments: true }],
      "max-lines-per-function": [
        "error",
        { max: 150, skipBlankLines: true, skipComments: true, IIFEs: true },
      ],
      "max-depth": ["error", 4],
      "react/jsx-key": "error",
      "react/no-array-index-key": "warn",
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx}", "src/**/__tests__/**/*.{ts,tsx}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.jest,
      },
    },
    rules: {
      "max-lines-per-function": "off",
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  // ===== Baseline waivers (#1412 introduction). =====
  // Each block below corresponds to a tracked followup issue that will retire it.
  // To narrow scope, remove individual files as they are fixed.
  {
    // #1422 — god-file refactor umbrella.
    files: GOD_FILE_SIZE_WAIVERS,
    rules: {
      "max-lines": "off",
      "max-lines-per-function": "off",
      complexity: "off",
    },
  },
  {
    // #1413 — refactor functions exceeding 150 LOC.
    files: MAX_LINES_PER_FN_WAIVERS,
    rules: { "max-lines-per-function": "off" },
  },
  {
    // #1414 — reduce cyclomatic complexity below 16.
    files: COMPLEXITY_WAIVERS,
    rules: { complexity: "off" },
  },
  {
    // #1415 — replace `==` / `!=` with `===` / `!==`.
    files: EQEQEQ_WAIVERS,
    rules: { eqeqeq: "off" },
  },
  {
    // #1416 — convert `import('...').T` to `import type` in tests.
    files: CONSISTENT_TYPE_IMPORT_WAIVERS,
    rules: { "@typescript-eslint/consistent-type-imports": "off" },
  },
  {
    // #1417 — remove unused vars / prefix API-contract args with `_`.
    files: NO_UNUSED_VARS_WAIVERS,
    rules: { "@typescript-eslint/no-unused-vars": "off" },
  },
  {
    // #1419 — nested 5 deep in laneAssign.ts.
    files: ["src/components/Git/GitGraph/laneAssign.ts"],
    rules: { "max-depth": "off" },
  },
  {
    // #1419 — add description after @ts-expect-error in useWebSocket.test.ts.
    files: ["src/hooks/useWebSocket.test.ts"],
    rules: { "@typescript-eslint/ban-ts-comment": "off" },
  },
  {
    // #1421 — investigate 10 missing-deps in App.tsx (potential stale-closure bugs).
    files: ["src/App.tsx"],
    rules: { "react-hooks/exhaustive-deps": "off" },
  },
  {
    // #1420 — REAL BUG: BlockNode.tsx calls Hooks conditionally after early return.
    files: ["src/components/nodes/BlockNode.tsx"],
    rules: { "react-hooks/rules-of-hooks": "off" },
  },
  prettier,
);
