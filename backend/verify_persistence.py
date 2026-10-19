
from app.repositories.game_repository import get_game

# Retrieve the previously saved game
game_id = "6ad62d07bbea03dce1685add"

print("Checking MongoDB persistence...")

saved_game = get_game(game_id)

if saved_game is None:
    print("FAILED: Game was not found.")
else:
    assert saved_game["_id"] == game_id
    assert saved_game["game_name"] == "My First Game"

    print("SUCCESS: Game survived the restart!")
    print("Game ID:", saved_game["_id"])
    print("Game name:", saved_game["game_name"])
    print("Status:", saved_game["status"])
    print("Round:", saved_game["round"])
    print("Full game data:", saved_game)
