# Geopolitics Game

## Project Overview

UCT INF4001N 2027 Honours Entrance Exam project. One human plays against nine
NPCs to control ten countries.

## Features

- Registration, login, owner-only play and public spectator viewing.
- Saved games with search, filtering, pagination and resume.
- Country selection, battles, reinforcements and soldier transfers.
- Strategic NPCs, visible fast-forward and battle history.

These features are implemented locally. Production activation and mandatory
GroqCloud battle commentary remain pending.

## Technology Stack

| Component | Technology |
| --- | --- |
| Frontend | React, TypeScript and Vite; planned Vercel hosting |
| Backend | Python 3.14, FastAPI and Pydantic; hosted on Render |
| Database | MongoDB Atlas |

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

Render hosts the API. Vercel hosting is planned with root directory `frontend`,
Vite preset, build command `npm run build` and output directory `dist`.
The Vercel `/api/*` proxy forwards to Render after removing `/api`.

Production authentication and gameplay writes remain disabled. Activation and
HTTPS cookie/Origin/CSRF verification require separate approval. Keep credentials
server-side; never commit them or expose them through frontend variables.

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
