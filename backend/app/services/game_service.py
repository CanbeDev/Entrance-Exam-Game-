from typing import Protocol

from app.engine.game_setup import SetupRandom, initialize_game
from app.models.game import GameSetupRequest, InitializedGame
from app.services.country_catalog import CountryCatalog


class GameStore(Protocol):
    def save_initialized_game(self, game: InitializedGame) -> str: ...


class GameService:
    def __init__(self, repository: GameStore, catalog: CountryCatalog | None = None,
                 rng: SetupRandom | None = None):
        self._repository = repository
        self._catalog = catalog if catalog is not None else CountryCatalog.load()
        self._rng = rng

    def create_game(self, request: GameSetupRequest) -> str:
        game = initialize_game(request, self._catalog, self._rng)
        return self._repository.save_initialized_game(game)
