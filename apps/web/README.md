# Web app

Next.js 15 (app router) + Tailwind 4. Every page is a client component that reads the FastAPI backend
directly. There is no server-side data layer, because the API is the single source of truth.

```bash
bun install
bun dev          # http://localhost:3010 (API expected at http://localhost:8010)
bun run build    # type-check + production build
```

`NEXT_PUBLIC_API_URL` overrides the API address.

| Route | What it shows |
|---|---|
| `/` | projects, create a project |
| `/projects/[id]` | upload footage, processing stages, new edit, scene search |
| `/edits/[id]` | preview, timeline with issue markers, version history, evaluation, version diff, feedback, action log |
| `/memory` | learned preferences, pending confirmations |
| `/improvement` | agent versions, promotions, experiments, failure clusters |
| `/improvement/experiments/[id]` | candidate strategy, gates, baseline vs candidate (in scope / all), holdout, approve or decline |
| `/improvement/compare` | config diff between two agent versions and the experiments that compared them |

Code layout: `lib/api.ts` (fetch + errors), `lib/hooks.ts` (`useApi` with polling), `lib/types.ts` (API shapes),
`components/` (timeline, evaluation report, comparison tables, feedback).
