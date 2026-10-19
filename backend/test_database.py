
from app.models.game import GameCreate
from app.repositories.game_repository import (
    create_game,
    get_game,
)

# Step 1: Create a new game
new_game = GameCreate(game_name="My First Game")

game_id = create_game(new_game)

print("Game created successfully!")
print("Game ID:", game_id)

# Step 2: Retrieve the same game
saved_game = get_game(game_id)

assert saved_game is not None
assert saved_game["game_name"] == "My First Game"
assert saved_game["_id"] == game_id

print("\nGame retrieved from MongoDB:")
print(saved_game)
