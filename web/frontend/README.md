# ST-EVA Web Frontend

This directory contains the React, TypeScript, and Vite browser client. It sends requests to the FastAPI service under `/api`.

## Local development

Start the backend from the repository root:

```powershell
python -m uvicorn web.app:create_app --factory --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend:

```powershell
cd web/frontend
npm install
npm run dev
```

Vite serves the client on port `5173` and proxies `/api` requests to `http://127.0.0.1:8000`, as configured in `vite.config.ts`.

## Checks

```powershell
npm run build
npm run lint
```

## Current UI boundary

The current page supports ticker submission and presents summary valuation metrics, source/evidence identifiers, admission status, and archive/replay status. It is an incomplete front end for the intended reverse-valuation product: it does not yet expose the full configurable reverse-requirements matrix or the input/formula/source trace for each scenario.

Do not infer from the presence of backend schemas or calculation functions that a capability is available in the browser. The root [README](../../README.md) defines the intended product and first-release acceptance conditions.
