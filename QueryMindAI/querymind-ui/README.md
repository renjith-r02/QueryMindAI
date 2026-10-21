# QueryMind

React app for asking plain-English questions about e-commerce data. By default it runs against a built-in mock backend, so no database or account system is needed. History and settings stay in the browser.

## Install

Requires Node 20 or newer.

```bash
npm install
npm run dev
```

Open http://localhost:8080.

Production:

```bash
npm run build
npm run preview
```

`dist/` is static files. Serve them with any static server, or keep using `npm run preview`.

## Scripts

| Script                            | What it does                           |
| --------------------------------- | -------------------------------------- |
| `npm run dev`                     | Vite dev server on port 8080           |
| `npm run build`                   | Type-check, then build to `dist/`      |
| `npm run typecheck`               | `tsc -b` for app and Vite config       |
| `npm run lint` / `lint:fix`       | ESLint                                 |
| `npm run format` / `format:check` | Prettier (with Tailwind class sorting) |
| `npm test` / `test:watch`         | Vitest + Testing Library (jsdom)       |

## Backend

Questions on the Ask page can be answered by `querymind-api` (`POST /run`):
it generates SQL with the server's model (Gemini `gemini-3.8-flash` by default; see
`LLM_PROVIDER` in querymind-api), runs it read-only on the real
databases, and writes an answer from the results.

```bash
# terminal 1, in querymind-api
uv run uvicorn app.main:app --reload
# terminal 2, here
echo "VITE_API_URL=http://localhost:8000" > .env.local
npm run dev
```

| Variable         | Meaning                                                        |
| ---------------- | -------------------------------------------------------------- |
| `VITE_API_URL`   | Base URL of `querymind-api`. Empty means use the mock backend. |
| `VITE_USE_MOCKS` | `true` forces mocks even when `VITE_API_URL` is set.           |

Only asking questions uses the API. Home suggestions and the Admin screens
still use mock data. Data sources in Settings are loaded from and saved to the API
(`/datasources`, stored in Qdrant). Guardrail and model settings in the Admin console
do not affect API answers; the server's configuration applies. The API allows
browser requests from `http://localhost:8080` (`QUERYMIND_CORS_ORIGINS` in
querymind-api).

All backend calls go through `src/api/`. `src/api/runAdapter.ts` converts the
`/run` response into the UI's result format.

## Structure

```
src/
├── main.tsx              # entry: fonts, global CSS, mock seed, render
├── app/                  # App, router, routes, error page, layout + sidebar config
├── api/                  # typed backend calls (mock or HTTP)
├── mocks/                # mock backend: question catalog, schema, seed history
├── features/
│   ├── ask/              # question flow store, Composer, clarify/heal/blocked UI
│   ├── results/          # QueryView, SQL panel, table, graph view; chart-type selection (chartViews.ts)
│   ├── datasources/      # Settings: data sources and their schema documentation
│   ├── dashboard/        # charts saved from results (snapshots kept in the browser)
│   ├── history/          # persisted run history
│   └── settings/         # persisted settings
├── pages/                # one thin component per route (+ optional `loader`)
├── components/ui/        # Button, Card, Switch, SelectField, PageHeader, Notice…
├── lib/                  # generic helpers: cn, format, theme, storage
├── types/                # shared domain types
├── config/env.ts         # typed environment variables
└── styles/globals.css    # Tailwind + design tokens
```

## Expand

| Change        | Where                                                                                  |
| ------------- | -------------------------------------------------------------------------------------- |
| New question  | `src/mocks/catalog.ts`: add an intent above the broad product fallback                 |
| New table     | `src/mocks/schema.ts`                                                                  |
| New screen    | Page in `src/pages/`, route in `src/app/routes.tsx`, label in `src/app/layouts/nav.ts` |
| Shared widget | `src/components/ui/`                                                                   |

Specific question matches must sit above the product/revenue fallback. A `suggestion` string shows the question on Home.

## Try these

- Top 10 products by revenue last quarter
- Show total amount last month (asks which amount you mean)
- Product sales summary (fails once, then self-heals)
