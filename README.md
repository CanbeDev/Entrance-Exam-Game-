# Geopolitics Game

## Project Overview

UCT INF4001N 2027 Honours Entrance Exam project. One human plays against nine
NPCs to control ten countries.

## Features

- Registration, login, owner-only play and public spectator viewing.
- Saved games with search, filtering, pagination and resume.
- Country selection, battles, reinforcements and soldier transfers.
- Strategic NPCs, visible fast-forward and battle history.
- GroqCloud battle commentary with saved narration and a deterministic fallback.

Commentary is implemented locally and awaits deployment and real-provider
acceptance. Production fast-forward acceptance remains incomplete.

## Technology Stack

| Component | Technology |
| --- | --- |
| Frontend | React, TypeScript and Vite; hosted on Vercel |
| Backend | Python 3.14, FastAPI and Pydantic; hosted on Render |
| Database | MongoDB Atlas |
| Battle narration | GroqCloud, called only by the backend |

## Project Structure

- `frontend/`: React interface, API client, tests and deployment configuration.
- `backend/`: API, game engine, database services, tests and requirements.
- `docs/`: API contracts and verification documentation.

See the [assignment requirements](backend/docs/REQUIREMENTS.md),
[game rules](backend/docs/GAME_RULES.md) and [NPC strategy](backend/docs/NPC_STRATEGY.md).

## Local Setup

For the offline interface, use Node.js 24+ and PowerShell from the repository root:

```powershell
cd frontend
npm.cmd ci --ignore-scripts --no-audit --no-fund
node tests/serve-smoke.mjs
```

Open `http://127.0.0.1:5174`. This runs the frontend and mock API without a database
or production connection. Stop it with Ctrl+C. See [frontend setup](frontend/README.md).

The real backend requires private process settings `MONGODB_URI` and
`MONGODB_DB_NAME`. There is no default database name. Web startup does not load
`.env` automatically. See [backend configuration](backend/docs/phase4-startup.md).

## Deployment

Render hosts the API. Vercel uses root directory `frontend`,
Vite preset, build command `npm run build` and output directory `dist`.
The Vercel `/api/*` proxy forwards to Render after removing `/api`.

Production authentication and gameplay writes are enabled, as confirmed by the
project owner. Further gameplay tests and deployments require separate approval.
Keep credentials server-side; never expose them through frontend variables.
See [commentary configuration and rollout](docs/PHASE4_GROQ_COMMENTARY.md).

## Testing

From `frontend`:

```powershell
npm.cmd test
npm.cmd run check:contracts
npm.cmd run build
```

Phase 3 passed 54 automated tests, TypeScript checks and the production build.
The user reported successful core manual browser acceptance against the offline
fixture. Automated Chrome testing was blocked by a browser URL policy check.
Production acceptance remains pending. See [backend testing](backend/docs/TESTING.md).

The commentary patch passes 167 frontend tests and 43 contract checks, with
TypeScript/build checks passing. Mocked provider tests do not prove live Groq delivery.
