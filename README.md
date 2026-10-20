# Geopolitics Game

My UCT INF4001N 2027 Honours Entrance Exam project. One human plays against nine
NPCs to control ten countries. The backend uses FastAPI, Pydantic and MongoDB Atlas.

Game setup, turns, battles, reinforcements and strategic NPCs are implemented.
Accounts, sessions and owner-only actions are also implemented, but authentication
and gameplay writes remain **disabled by default**. Render currently serves the
health, country catalog and saved-game endpoints. The frontend, visible
fast-forward and LLM battle commentary are still to come.

## Running the backend

From the repository root, using Python 3.14 and PowerShell:

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Skip creating `.venv` if it already exists. Set `MONGODB_URI` privately in
`backend/.env` or the hosting environment. `MONGODB_DB_NAME` defaults to
`geopolitics_game`. Use a development database locally; never commit credentials.

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. Public reads include `/health`, `/countries`
and `/games/{game_id}`. Startup and the health check need MongoDB configuration;
offline tests do not.

## Documentation

- [Requirements](backend/docs/REQUIREMENTS.md)
- [Architecture and API](backend/docs/ARCHITECTURE.md)
- [Game rules](backend/docs/GAME_RULES.md)
- [NPC strategy](backend/docs/NPC_STRATEGY.md)
- [Tests and offline demos](backend/docs/TESTING.md)

Render needs the runtime dependencies, MongoDB settings and an ASGI command for
`app.main:app` bound to its assigned interface and port. There is no Render service
definition in this repository. Protected features need a separate activation
review; see [deployment requirements](backend/docs/ARCHITECTURE.md#deployment-requirements).
