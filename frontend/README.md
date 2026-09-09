# TenderSense frontend

Vite + React 19 + TypeScript (strict), shadcn/ui (Base UI, `nova` style, Tailwind v4),
TanStack Router (file-based) + React Query, zustand, openapi-fetch, react-hook-form + zod.

## Scripts

| Command             | What it does                                                  |
| ------------------- | ------------------------------------------------------------- |
| `npm run dev`       | Dev server on http://localhost:5173 (proxies `/api` to :8000) |
| `npm run build`     | `tsc -b && vite build` → `dist/`                              |
| `npm run lint`      | ESLint                                                        |
| `npm test`          | Vitest (jsdom + MSW)                                          |
| `npm run e2e`       | Playwright smoke tests (`e2e/`)                               |
| `npm run api:types` | Regenerate `src/lib/api/schema.d.ts` from the backend OpenAPI |
| `npm run format`    | Prettier                                                      |

Set `VITE_MOCK_API=1` (see `.env.example`) to serve API responses from MSW handlers in `src/mocks/`.

## Layout

- `src/routes/` — file routes. `_auth` (public auth pages) and `_app` (authenticated shell) are pathless layouts.
- `src/components/ui/` — shadcn components (managed by `npx shadcn@latest add`).
- `src/components/layout/` — app shell pieces (`AppSidebar`, `AppHeader`, `PageHeader`, `AuthCard`).
- `src/lib/api/` — typed client, error normalization, query keys.
- `src/lib/auth/` — zustand session store, silent-refresh bootstrap.
- `src/lib/forms/` — `useZodForm` + `RhfField` (shadcn `Field` bridge for react-hook-form).
- `src/features/` — feature modules (e.g. `tenders/GradeBadge`).
