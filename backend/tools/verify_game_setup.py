"""Manual setup preview; --persist explicitly writes one new game via the service.

Run from backend: .venv/Scripts/python.exe -m tools.verify_game_setup
"""
import argparse

from app.engine.game_setup import initialize_game
from app.models.game import GameSetupRequest
from app.services.country_catalog import CountryCatalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="south-africa", help="Country ID from GET /countries")
    parser.add_argument("--name", default="Phase 1 Manual Check")
    parser.add_argument("--persist", action="store_true", help="Insert one initialized game into configured MongoDB")
    options = parser.parse_args()
    try:
        request = GameSetupRequest(game_name=options.name, starting_country_id=options.country)
        catalog = CountryCatalog.load()
        if not options.persist:
            game = initialize_game(request, catalog)
            print(game.model_dump_json(indent=2))
            print("Preview only: no database connection or write.")
            return

        # These imports are intentionally absent from preview execution.
        from app.repositories.game_repository import MongoGameRepository
        from app.services.game_service import GameService
        repository = MongoGameRepository()
        game_id = GameService(repository, catalog).create_game(request)
        print(f"Created game ID: {game_id}")
        print(f"Verify via GET /games/{game_id} or inspect this document in Atlas.")
    except Exception as error:
        # No exception message/traceback: driver/config errors can contain connection details.
        parser.exit(1, f"Setup verification failed ({type(error).__name__}). Check inputs and local configuration.\n")


if __name__ == "__main__":
    main()
