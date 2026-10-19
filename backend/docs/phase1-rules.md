# Phase 1: initialized games

## Requirements and scope

The official INF4001N 2027 brief, pp.1-2, supplies the ten-country setup,
human country selection, nine random countries, population table, full initial
soldier allocation, and random first player. The marksheet motivates separated
database access, clear models/OOP, and input validation. The solo development
plan is supporting guidance, not an additional official specification.

The user approved one human plus nine NPCs, each initially owning one country,
and shuffling the complete participant order once at setup. Full-order shuffling
is our implementation convention; the brief only explicitly randomizes the first
player. current_turn is the zero-based index into turn_order. Setup starts at
round 1, current_turn 0, active status, and no winner. Active here means initialized;
turn execution is not implemented in this phase.

No authentication, HTTP creation route, frontend, combat, reinforcements, NPC
strategy, deployments, or automatic Atlas writes are included. Human player ID
`human` is local to a game; it is not an authenticated account ID. Do not expose
the creation service over HTTP until access control is approved and implemented.

## Population source and eligibility decision

Reviewed before dataset finalization:

- Population: https://www.worldometers.info/world-population/population-by-country/
- Eligibility: https://www.worldometers.info/geography/alphabetical-list-of-countries/
- Population reference year: **2026**; retrieved **2026-10-19** (client local date).
- Dataset ID: `worldometer-2026-2026-10-19`.

The population table has 234 country/dependency entries. Our eligible list is
the separate Worldometer 195-country list, including Holy See and State of
Palestine. The other 39 population entries are retained in `excluded_entries`
for audit but cannot be selected or sampled. This is a documented project
eligibility convention, not an official assignment restriction or a statement
about political recognition. In particular, Taiwan and Western Sahara are
excluded by this list-based rule along with dependent territories. Holy See
represents the brief's Vatican City example.

The JSON records every excluded name, ID and population. Examples include
Hong Kong, Macao, Greenland, Puerto Rico, and the Cook Islands. Matching uses
the source's country-page URL slug rather than display names; IDs are local
stable slugs, not ISO codes. Population display names are preserved, including
source naming differences between the two tables.

`countries.json` contains all 195 eligible population records, source URLs,
reference year, retrieval date, policy, and SHA-256 hashes of both retrieved HTML
pages. Populations are the fixed 2026 table values, not live country-page clocks.
No network request is made during catalog loading or game creation. Each saved
game embeds its selected populations, base values, and snapshot provenance;
changing the catalog later does not rewrite saved games.

To deliberately rebuild after reviewing source changes:

```powershell
.venv/Scripts/python.exe tools/build_country_dataset.py --retrieved-on YYYY-MM-DD --population-year YYYY
```

This maintenance tool downloads public pages and overwrites the local JSON. It
fails on unexpected eligibility counts/matches or year changes; review the diff
and update snapshot-specific tests and this document before accepting a rebuild.

## Official soldier allocation

Use the first inclusive upper bound that contains the positive integer population:

| Upper bound | Soldiers |
|---|---:|
| 5,000,000 | 1 |
| 10,000,000 | 2 |
| 25,000,000 | 3 |
| 50,000,000 | 4 |
| 75,000,000 | 5 |
| 100,000,000 | 6 |
| 125,000,000 | 7 |
| 150,000,000 | 8 |
| Above 150,000,000 | 9 |

Zero/negative populations, booleans, floats and numeric strings are rejected as
invalid data. This validation is a software constraint, not a new gameplay rule.
Both `base_soldier_value` and `soldiers` start at this result. No reinforcement
or conquest rule is executed here.

## Architecture and persistence

1. `models/country.py`, `models/player.py`, `models/game.py`: validated input,
   immutable country definitions, players, and strict initialized state.
2. `services/country_catalog.py`: local dataset validation and eligible lookup.
3. `engine/population_rules.py`: pure official population conversion.
4. `engine/game_setup.py`: excludes the chosen country before sampling nine
   without replacement, assigns one country per participant, allocates soldiers,
   and shuffles turn order. Defaults to SystemRandom; tests inject seeded RNGs.
5. `services/game_service.py`: initializes and validates before calling an
   injected repository once. Returns the new game ID.
6. `repositories/game_repository.py`: injects a collection for tests or lazily
   uses the existing database module for real persistence. Revalidates setup
   state, converts snapshot dates to BSON-safe ISO text, and inserts one complete
   game document. created_at remains a BSON datetime. No new collection required.
7. `api/countries.py`: read-only GET /countries; includes snapshot metadata,
   eligible records and calculated base values. main.py only registers this router.

Legacy Game/GameCreate and create_game/get_game functions remain available.
Old empty waiting documents, including My First Game, are returned without
migration or new validation requirements. InitializedGame is a separate setup
model with schema_version 2; it is not a validator for future combat states.
database.py, environment names, existing health behavior, and production
requirements.txt are unchanged.

## Isolated testing

From backend:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
```

The runtime dependencies in requirements.txt must already be installed in a
matching Python environment. The existing environment uses Python 3.14.
pytest.ini restricts discovery to tests/, excluding test_database.py and
verify_persistence.py, which perform Atlas operations at import time.

Tests use an injected in-memory collection and fake database module for API
checks. External socket connections are blocked; Windows asyncio's internal
loopback connection is allowed. No real environment secrets or database are
needed. Tests check all threshold boundaries, validation, eligibility, uniqueness,
ownership, initialization, shuffled order, BSON encoding, saved-state retrieval,
legacy compatibility, errors, and absence of POST routes. This is not a live
Atlas persistence test.

Implementation verification on 2026-10-19: **106 passed, 0 failed, 1 warning**
(1.37 seconds, Python 3.14). The warning is Starlette's deprecation of HTTPX
in TestClient; it recommends HTTPX2. Runtime dependencies were left unchanged.
An initial Python 3.12/3.14 environment mismatch and an overly broad test socket
guard were corrected before this successful run. The no-write manual preview
also succeeded, and git diff --check passed.

## Manual verification

From backend, preview a newly initialized game without touching MongoDB:

```powershell
.venv/Scripts/python.exe -m tools.verify_game_setup --country south-africa
```

Inspect ten unique countries, one human and nine NPCs, one owner per country,
South Africa owned by human with base value and current soldiers both 5,
snapshot metadata, and ten distinct IDs in turn_order. The starting participant
is turn_order[current_turn], with current_turn 0. Rerun to see different selections
and orders. Preview does not exercise repository writes.

If you explicitly want to create one new Atlas game using the configured local
environment, run:

```powershell
.venv/Scripts/python.exe -m tools.verify_game_setup --country south-africa --persist
```

This invokes GameService with MongoGameRepository and prints only the game ID
and retrieval path. Read it with the existing GET /games/{id} endpoint, or inspect
it in Atlas. Restart the API and retrieve the same ID to check real persistence.
Existing games remain untouched. Do not share environment files or connection
strings. No real Atlas verification was performed during implementation.

For the read-only catalog, start the API normally from backend and request
GET /countries; it should return 195 records. API startup retains its existing
database configuration requirement. There is no POST /games endpoint.

## Remaining requirements

There are no unresolved Phase 1 gameplay decisions under the approved conventions.
Future work must add authenticated account ownership and authorized creation,
turn progression, combat, reinforcements and strategic NPC actions. No such
functionality should be inferred from active status or the saved turn order.
