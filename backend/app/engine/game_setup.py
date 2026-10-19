import random
from typing import Protocol, Sequence, TypeVar

from app.engine.population_rules import soldiers_from_population
from app.models.country import GameCountry
from app.models.game import GameSetupRequest, InitializedGame
from app.models.player import Player
from app.services.country_catalog import CountryCatalog

T = TypeVar("T")


class SetupRandom(Protocol):
    def sample(self, population: Sequence[T], k: int) -> list[T]: ...
    def shuffle(self, items: list) -> None: ...


def initialize_game(
    request: GameSetupRequest,
    catalog: CountryCatalog,
    rng: SetupRandom | None = None,
) -> InitializedGame:
    """Pure setup: no DB, HTTP, authentication, or turn execution.

    Convention: shuffle all participants once and persist that order.
    Player IDs are local to a game; human identity is not an account identity.
    """
    rng = rng if rng is not None else random.SystemRandom()
    human_country = catalog.get(request.starting_country_id)
    alternatives = [country for country in catalog.countries if country.id != human_country.id]
    if len(alternatives) < 9:
        raise ValueError("At least ten eligible countries are required")
    selected = [human_country, *rng.sample(alternatives, 9)]
    players = [
        Player(id="human" if index == 0 else f"npc-{index}",
               kind="human" if index == 0 else "npc", starting_country_id=country.id)
        for index, country in enumerate(selected)
    ]
    countries = [
        GameCountry(**country.model_dump(), owner_id=player.id,
                    base_soldier_value=soldiers_from_population(country.population),
                    soldiers=soldiers_from_population(country.population))
        for player, country in zip(players, selected)
    ]
    turn_order = [player.id for player in players]
    rng.shuffle(turn_order)
    return InitializedGame(game_name=request.game_name, countries=countries,
                           players=players, turn_order=turn_order,
                           population_snapshot=catalog.snapshot)
