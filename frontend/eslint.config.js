import js from "@eslint/js";
import tseslint from "typescript-eslint";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import prettier from "eslint-config-prettier";
import globals from "globals";

// #2297 — tests that still replace the backend client with `vi.mock(lib/api)`.
// New tests must use `mockBackend()` (src/__tests__/contract/mockBackend.ts),
// which checks every mock against the backend OpenAPI contract and runs the
// real client code.
// TODO(#2300): migrate these files to mockBackend() and empty this list.
//   Out of scope for #2297 per the owner-approved incremental migration.
//   Followup: https://github.com/jiazhenz026/SciStudio/issues/2300
const LIB_API_MOCK_GRANDFATHERED = [
  "src/App.parts/__tests__/newDropinFile.test.tsx",
  "src/App.parts/useCanvasHandlers.test.tsx",
  "src/App.parts/useWorkflowExecutionActions.test.tsx",
  "src/App.parts/useWorkflowSync.test.tsx",
  "src/components/__tests__/BringInMyWorkDialog.test.tsx",
  "src/components/__tests__/edgePortColorParity.test.tsx",
  "src/components/__tests__/LearningCenter.test.tsx",
  "src/components/__tests__/OpenAsDialog.test.tsx",
  "src/components/__tests__/PreviewerPalette.test.tsx",
  "src/components/__tests__/ProjectTree.test.tsx",
  "src/components/__tests__/tutorialAutoAdvance.test.tsx",
  "src/components/__tests__/tutorialProjectOpens.test.tsx",
  "src/components/__tests__/typeColorSource.test.tsx",
  "src/components/__tests__/TypePalette.test.tsx",
  "src/components/__tests__/WorkImportOffer.test.tsx",
  "src/components/BottomPanel.parts/ConfigPanel.test.tsx",
  "src/components/BottomPanel.parts/ConfigPanelBrowse.test.tsx",
  "src/components/BottomPanel.parts/PlotsTab.test.tsx",
  "src/components/BottomPanel.parts/PlotTargetPicker.test.tsx",
  "src/components/BottomPanel.parts/SubworkflowConfigEditor.test.tsx",
  "src/components/BottomPanel.test.tsx",
  "src/components/DataPreview.parts/PreviewHost.dynamic.test.tsx",
  "src/components/DataPreview.parts/PreviewHost.exportFallback.test.tsx",
  "src/components/DataPreview.parts/PreviewHost.test.tsx",
  "src/components/DataPreview.test.tsx",
  "src/components/Git/__tests__/ConflictResolveView.test.tsx",
  "src/components/Git/__tests__/MergeFlow.test.tsx",
  "src/components/LearningCenter.parts/__tests__/DocsBrowser.test.tsx",
  "src/components/LearningCenter.parts/__tests__/ReadingSurface.test.tsx",
  "src/components/nodes/__tests__/BlockNode/test-utils.tsx",
  "src/components/Lineage/__tests__/LineageTab.test.tsx",
  "src/components/Lineage/__tests__/RestoreDialog.test.tsx",
  "src/components/Lineage/__tests__/RunDetail.restore.test.tsx",
  "src/components/Lineage/__tests__/RunDetail.test.tsx",
  "src/components/Lineage/__tests__/RunsList.test.tsx",
  "src/components/PackageManagerDialog.test.tsx",
  "src/components/promotion/__tests__/entryPoints.test.tsx",
  "src/components/promotion/__tests__/revealInLibrary.test.tsx",
  "src/components/WorkflowPanel.test.tsx",
  "src/hooks/__tests__/useWebSocket.versionVector.test.ts",
  "src/hooks/useWebSocket.test.ts",
  "src/store/__tests__/gitLogRetryStorm.test.ts",
  "src/store/__tests__/gitSlice.test.ts",
  "src/store/__tests__/lineageSlice.test.ts",
  "src/store/__tests__/previewerCatalogInvalidation.test.ts",
  "src/store/__tests__/tabSlice.versionVector.test.ts",
  "src/store/__tests__/tabState.test.ts",
  "src/store/__tests__/typeCatalogInvalidation.test.ts",
  "src/store/__tests__/userLibraryTab.test.ts",
  "src/store/__tests__/workflowSlice.subworkflowRef.test.ts",
  "src/store/__tests__/workflowSlice.variadicPorts.test.ts",
  "src/webmcp/register.test.ts",
];

// #1412 baseline waivers RETIRED by the #1426 cleanup cascade
// (PRs #1435 #1450 #1447 #1446 #1457 #1478 + this Wave 4 integration commit).
//
// Wave 1 (#1420 #1421): rules-of-hooks + exhaustive-deps fixed in source.
// Wave 2 (#1422):       god files split into <file>.parts/ siblings.
// Wave 3-E (#1416 #1417 #1419):
//                       test type-imports + non-overlap unused-vars +
//                       ban-ts-comment descriptions fixed in source.
// Wave 3-D (#1413 #1414 partial #1419 partial #1417):
//                       max-lines-per-function + complexity + max-depth +
//                       overlap unused-vars fixed in source.
// Wave 4 (#1415 + threshold bump + waiver strip, this commit):
//                       eqeqeq fixed in source. max-lines bumped to 750,
//                       max-lines-per-function to 400, complexity to 50 —
//                       the looser thresholds still catch egregious size
//                       and complexity regressions but accept the
//                       repository's current orchestrator-pattern reality.
//                       Future ratchet back toward stricter limits is a
//                       follow-up cleanup, not part of the #1412 cascade.

export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "coverage/**",
      "**/*.config.js",
      "**/*.config.ts",
      "src/scistudio/api/static/**",
      // Nested git worktrees from sub-agent dispatch should never be
      // linted as part of the manager worktree (#1426 main-merge hygiene).
      ".claude/**",
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
      // `== null` / `!= null` is the idiomatic JS/TS check for "null or
      // undefined" and is widely used across this codebase (see #1415 +
      // Wave 4 integration). The `null: "ignore"` option keeps the rule
      // strict on every other comparison while accepting that idiom.
      eqeqeq: ["error", "always", { null: "ignore" }],
      complexity: ["error", 50],
      "max-lines": ["error", { max: 750, skipBlankLines: true, skipComments: true }],
      "max-lines-per-function": [
        "error",
        { max: 400, skipBlankLines: true, skipComments: true, IIFEs: true },
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
  {
    files: ["src/**/*.test.{ts,tsx}", "src/**/__tests__/**/*.{ts,tsx}"],
    ignores: LIB_API_MOCK_GRANDFATHERED,
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.object.name='vi'][callee.property.name='mock'][arguments.0.value=/lib\\/api(\\/|$)/]",
          message:
            "Do not vi.mock the backend client (#2297). Use mockBackend() from src/__tests__/contract/mockBackend so the mock is checked against the backend OpenAPI contract.",
        },
      ],
    },
  },
  prettier,
);
