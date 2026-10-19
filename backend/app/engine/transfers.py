from app.engine.errors import GameRuleError
from app.models.country import GameCountry


def validate_transfer(source: GameCountry, target: GameCountry, actor_id: str, amount: int) -> None:
    if source.id == target.id or source.owner_id != actor_id or target.owner_id != actor_id:
        raise GameRuleError("Transfer requires two distinct owned countries")
    if type(amount) is not int or amount < 1 or source.soldiers - amount < 1:
        raise GameRuleError("Transfer must leave at least one soldier behind")
