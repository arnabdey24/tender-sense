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
        "/api": { target: apiTarget, changeOrigin: true },
        "/openapi.json": { target: apiTarget, changeOrigin: true },
      },
    },
  }
})
