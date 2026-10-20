"""Synthetic Phase 4 HTTP demonstration. In-memory test store ONLY; no MongoDB."""
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.dependencies import Phase4SecurityMiddleware, install_security_handlers
from app.api.games import router as games_router
from app.security.config import SecuritySettings
from app.services.auth_service import AuthService
from app.services.authorized_game_service import AuthorizedGameService
from app.services.phase4_context import Phase4Context
from app.services.public_game_service import public_game

# This dev-only demonstration deliberately reuses the explicitly labelled test
# adapter. It is never installed as an application persistence fallback.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from phase4_helpers import MemorySecurityStore


def main():
    clock = lambda: datetime.now(timezone.utc)
    store = MemorySecurityStore(clock=clock)
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True,
                                trusted_origins=("https://demo.test",))
    context = Phase4Context(settings, AuthService(store, settings, clock),
                            AuthorizedGameService(store, settings, clock, setup_rng=random.Random(14)))
    demo = FastAPI()
    demo.state.phase4 = context
    demo.add_middleware(Phase4SecurityMiddleware)
    install_security_handlers(demo)
    demo.include_router(auth_router)
    demo.include_router(games_router)

    @demo.get("/games/{game_id}")
    def read_game(game_id: str):
        if game_id not in store.games:
            raise HTTPException(404)
        return public_game(store.games[game_id])

    print("Synthetic HTTP demonstration: injected memory storage; no database or network.")
    with TestClient(demo, base_url="https://demo.test") as owner, \
            TestClient(demo, base_url="https://demo.test") as other, \
            TestClient(demo, base_url="https://demo.test") as visitor:
        for client, name in ((owner, "DemoOwner"), (other, "DemoVisitor")):
            client.headers["Origin"] = "https://demo.test"
            # Synthetic credentials never leave TestClient and are not printed.
            credentials = {"username": name, "password": "Synthetic demonstration words 4001!"}
            assert client.post("/auth/register", json=credentials).status_code == 201
            assert client.post("/auth/login", json=credentials).status_code == 200
            client.headers["X-CSRF-Token"] = client.get("/auth/csrf").json()["csrf_token"]
        request = {"game_name": "Local authenticated demonstration", "starting_country_id": "south-africa"}
        first = owner.post("/games", json=request, headers={"Idempotency-Key": "demo-first"})
        assert first.status_code == 201
        game = first.json()
        game_id = game["_id"]
        retry = owner.post("/games", json=request, headers={"Idempotency-Key": "demo-first"})
        assert retry.json() == game
        assert len(game["countries"]) == 10 and "access" not in game
        assert visitor.get(f"/games/{game_id}").status_code == 200
        command = {"action_id": "demo-human-skip", "expected_revision": 0, "action": {"type": "skip"}}
        assert other.post(f"/games/{game_id}/actions", json=command).status_code == 403
        assert visitor.post(f"/games/{game_id}/actions", json=command,
                            headers={"Origin": "https://demo.test"}).status_code == 401
        result = owner.post(f"/games/{game_id}/actions", json=command)
        assert result.status_code == 200
        assert owner.post(f"/games/{game_id}/actions", json=command).json() == result.json()
        npc = owner.post(f"/games/{game_id}/npc-steps", json={"expected_revision": 1})
        assert npc.status_code == 200
        assert owner.post(f"/games/{game_id}/npc-steps", json={"expected_revision": 1}).json() == npc.json()
        assert npc.json()["npc_decision"]["explanation"]
        history = visitor.get(f"/games/{game_id}/events").json()
        assert len(history["events"]) == 2
        second = owner.post("/games", json=request, headers={"Idempotency-Key": "demo-second"})
        assert second.status_code == 201 and second.json()["_id"] != game_id
        assert len(owner.get("/me/games").json()["games"]) == 2
        assert other.get("/me/games").json()["games"] == []
        assert owner.post("/auth/logout").status_code == 204
        assert owner.get("/auth/me").status_code == 401
    print("Registration/login, secure cookie/CSRF, two independent games and creation replay: passed.")
    print("Anonymous reads, cross-account denial, human/NPC replay and committed history: passed.")
    print("Logout invalidation: passed. Production application and write gates unchanged.")


if __name__ == "__main__":
    main()
