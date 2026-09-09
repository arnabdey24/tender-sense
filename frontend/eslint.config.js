import js from "@eslint/js"
import globals from "globals"
import reactHooks from "eslint-plugin-react-hooks"
import reactRefresh from "eslint-plugin-react-refresh"
import tseslint from "typescript-eslint"
import { defineConfig, globalIgnores } from "eslint/config"

export default defineConfig([
  globalIgnores([
    "dist",
    "src/routeTree.gen.ts",
    "public/mockServiceWorker.js",
    "playwright-report",
    "test-results",
  ]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    // TanStack Router file routes export `Route` alongside the page component
    // by design; test utilities re-export Testing Library helpers.
    files: ["src/routes/**/*.tsx", "src/test/**/*.tsx"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
  {
    // shadcn-generated primitives export `*Variants` helpers next to components.
    files: ["src/components/ui/**/*.tsx"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
  {
    // shadcn-generated hook syncs a matchMedia value on mount.
    files: ["src/hooks/use-mobile.ts"],
    rules: {
      "react-hooks/set-state-in-effect": "off",
    },
  },
])
