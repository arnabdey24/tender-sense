import path from "path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  // Where `npm run dev` forwards /api and /openapi.json. Override with
  // VITE_API_PROXY_TARGET when the API runs on a non-default port.
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://localhost:8000"

  return {
    plugins: [
      // Must run before the React plugin so route files are transformed first.
      tanstackRouter({
        target: "react",
        autoCodeSplitting: true,
        routesDirectory: "./src/routes",
        generatedRouteTree: "./src/routeTree.gen.ts",
        // Route tests live beside their routes but export no Route.
        routeFileIgnorePattern: "\\.(test|spec)\\.tsx?$",
      }),
      react(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true, ws: true },
        "/openapi.json": { target: apiTarget, changeOrigin: true },
      },
    },
    /*
     * `preview` serves the built bundle, and it needs the same proxy as `dev`
     * so the production output can be driven against a real API.
     *
     * Without it the only way to see built CSS was to deploy, and built CSS is
     * where this project's sharpest bug so far lived: Tailwind emits utilities
     * in a different order than the dev server does, so an override that won
     * in development lost in production and the assistant panel sat shifted by
     * half its own size on the deployed site alone.
     */
    preview: {
      port: 5190,
      strictPort: true,
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true, ws: true },
        "/openapi.json": { target: apiTarget, changeOrigin: true },
      },
    },
  }
})
