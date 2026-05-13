# Coffee Records — Frontend

React 19 + TypeScript SPA built with Vite and Mantine UI. In production it is compiled and embedded into the Flask container (see the root `README.md`). In development it runs as a separate Vite dev server that proxies `/api` requests to the Flask backend.

## Development

```bash
npm install
npm run dev       # Vite dev server on :5173, proxies /api to :5000
```

Flask must be running locally on port 5000 for API calls to work (see root README for backend setup).

## Build

```bash
npm run build     # compiles to dist/
```

The multi-stage `Dockerfile` at the project root runs this automatically. You do not need to build manually for deployment.

## Type checking

```bash
npx tsc --noEmit
```

## Key libraries

| Library | Purpose |
|---|---|
| Mantine v8 | UI components and layout |
| `@mantine/charts` | BarChart / LineChart (Recharts wrapper) |
| React Router v7 | Client-side routing |
| Axios | HTTP client (`src/api/client.ts`) |
| Vite | Build tooling and dev server |
