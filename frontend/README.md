# TrustGraph Frontend (M6)

React + Vite + Tailwind CSS + React Flow + Recharts + Lucide React. See
`../backend/README.md` for the full project architecture (M1–M6) and
the primary demo workflow -- this file covers frontend-specific setup.

## Setup

```bash
npm install
cp .env.example .env    # points VITE_API_BASE_URL at the backend (default http://127.0.0.1:8000)
npm run dev              # http://localhost:5173
```

The backend must be running first (see `../backend/README.md`) --
without it the app shows a clear "TrustGraph backend unavailable"
state rather than a blank screen.

## Scripts

```bash
npm run dev       # development server with HMR
npm run build     # production build -> dist/
npm run preview   # serve the production build locally
npm test          # run the Vitest suite (30 tests, no backend required)
```

## Environment variables

Only `VITE_API_BASE_URL` is ever read (see `.env.example`). Vite only
exposes variables prefixed `VITE_` to the browser bundle by design --
`GEMINI_API_KEY`, `DATABASE_URL`, and every other backend secret stay
server-side and are never referenced anywhere in this directory
(enforced by `src/test/noSecretsOrHardcodedData.test.js`, and verified
directly against the production `dist/` bundle during M6 verification).

## Structure

```
src/
  api/          client.js (fetch wrapper), clusters.js, investigations.js, workflow.js, evaluation.js
  components/
    layout/       TopBar, NavLink (no router dependency -- hash-based)
    dashboard/     KpiCard, RiskDistributionChart
    clusters/       ClusterList, ClusterGraph (React Flow), GraphNode, NodeDetailPanel,
                      RiskPanel, ExposurePanel, EvidencePanel, InvestigationPanel,
                      PolicyPanel, ActionPanel, AuditTimeline, WorkflowStages
    common/          Badge, States (Loading/Error/BackendUnavailable/Empty)
  context/        ActivityContext -- session-scoped "recent investigations/actions" (never a fabricated lifetime count)
  lib/            format.js, severity.js, useApi.js (shared fetch hook)
  pages/          DashboardPage, ClustersPage, EvaluationPage
  test/           Vitest + Testing Library suite
```

## Design notes

- No Redux/Zustand -- component state + one small `ActivityContext`.
- No router dependency -- three pages don't warrant one; hash-based
  navigation (`#/clusters`) still gives bookmarkable URLs.
- No risk/signal computation happens here -- every number displayed
  (`risk.score`, `contribution`, `exposure`, evaluation metrics) comes
  directly from a backend JSON response, never recomputed in React.
