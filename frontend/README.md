# FinAlly Frontend

Next.js 15 + TypeScript + Tailwind v4. Static-export build (`output: 'export'`) consumed by FastAPI on `/`.

## Scripts

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # produces ./out (static export)
npm run typecheck
npm run test       # vitest
```

## Layout

```
src/
  app/          # Next.js App Router (root layout, page)
  components/   # UI components
  hooks/        # React hooks (e.g. usePriceStream)
  lib/          # api client, formatters
  types/        # API/contract types
```

All API calls go to same-origin `/api/*` — no CORS, no env vars.
