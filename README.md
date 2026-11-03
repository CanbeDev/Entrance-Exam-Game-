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
- Interactive world atlas, animated battle dice and Flag Poster results.
- Optional sound effects, volume preferences and country information cards.

The current UI redesign and audio patch await final connected-game acceptance.
Earlier live commentary evidence does not certify this working-tree release.

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

Stage 9 offline checks pass 358 public frontend tests, 929 backend tests and 43 contract
components. TypeScript, build and data-drift checks pass. All 44 real-database
tests remain skipped. Mocks do not prove live persistence or provider delivery.

See [backend testing](backend/docs/TESTING.md), the
[manual gameplay checklist](docs/STAGE9_HUMAN_GAMEPLAY_ACCEPTANCE.md) and
[acceptance report](docs/UI_STAGE9_ACCEPTANCE_REPORT.md). Connected gameplay and
release approval remain human tasks. The earlier Phase 3 browser-automation
limitation is preserved in its [historical report](docs/FRONTEND_PHASE3_REPORT.md).
