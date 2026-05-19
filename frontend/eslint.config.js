import js from "@eslint/js";
import jsdoc from "eslint-plugin-jsdoc";
import reactHooks from "eslint-plugin-react-hooks";
import tsdoc from "eslint-plugin-tsdoc";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}", "vite.config.ts", "vitest.setup.ts"],
    languageOptions: {
      globals: {
        afterEach: "readonly",
        beforeEach: "readonly",
        clearTimeout: "readonly",
        console: "readonly",
        describe: "readonly",
        document: "readonly",
        expect: "readonly",
        fetch: "readonly",
        it: "readonly",
        setTimeout: "readonly",
        vi: "readonly",
        window: "readonly",
      },
    },
    plugins: {
      jsdoc,
      "react-hooks": reactHooks,
      tsdoc,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "jsdoc/check-tag-names": "error",
      "tsdoc/syntax": "error",
    },
  },
);
