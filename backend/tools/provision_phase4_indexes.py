"""Print the index plan locally. Provisioning existing databases is not supported."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.repositories.phase4_indexes import phase4_indexes


def main():
    # Intentionally no URI, MongoClient, environment or execution switch here.
    # A separately approved real verification fixture must provision only its
    # generated disposable database and own the exact-name cleanup lifecycle.
    if len(sys.argv) != 1:
        raise SystemExit("Plan-only tool: database operations require separate approval.")
    for collection, indexes in phase4_indexes().items():
        print(collection)
        for index in indexes:
            print(f"  {index.document!r}")


if __name__ == "__main__":
    main()
