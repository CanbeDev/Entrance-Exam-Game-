# How the game works

These rules follow the official brief. Human and NPC actions use the same engine.
Approved choices for unspecified details are listed at the end.

## Starting a game

The human chooses one country; nine distinct others are sampled without
replacement. One human and nine NPCs each start with one country.

| Population | Soldiers |
| --- | ---: |
| Up to 5 million | 1 |
| Above 5, up to 10 million | 2 |
| Above 10, up to 25 million | 3 |
| Above 25, up to 50 million | 4 |
| Above 50, up to 75 million | 5 |
| Above 75, up to 100 million | 6 |
| Above 100, up to 125 million | 7 |
| Above 125, up to 150 million | 8 |
| Above 150 million | 9 |

Populations must be positive integers, excluding booleans. Each country stores
immutable `base_soldier_value` and current `soldiers`, initially equal.
See [population data](ARCHITECTURE.md#population-data).

## Turns and battles

Only the active participant acts. Round one has no reinforcements. From round two,
allocate `2 * owned_country_count` soldiers completely before other actions.
Eliminated participants are skipped; wrapping the saved order advances the round.

A turn allows one enemy target, with no geographic restrictions. Starting an
attack locks its owned source and enemy target but rolls no dice. Each exchange
rolls `min(source.soldiers - 1, target.soldiers)` independent dice per side, each
from 1 to 6. Pair by original index, without sorting. The lower die loses a
soldier; ties lose none. Apply losses together.

The attacker may continue against that target or stop, which ends the turn.
Reaching one source soldier forces failure. There is no exchange limit.
Conquest changes ownership and gives the captured country
`max(2, base_soldier_value // 2)` soldiers. Survivors stay at the source.

Transfers move positive integer amounts between different owned countries,
leaving at least one behind. They have no distance or count limit. Controlling
all ten countries wins immediately; participants owning none are eliminated.

| Turn state | Actions |
| --- | --- |
| `allocating` | Complete `allocate` |
| `deciding` | `transfer`, `start_attack`, `skip` |
| `attacking` | `roll`, `stop_attack` |
| `post_attack` | `transfer`, `end_turn` |
| `finished` | None |

Invalid actions leave gameplay state and receipts unchanged.

## Project conventions

The approved A-H choices are: **A** use immutable base values for rewards;
**B** place rewards in the captured country and move survivors only by transfer;
**C** lock the battle pair and separate starting from rolling; **D** allow transfers
but no second attack after conquest/forced failure, while voluntary stopping ends
the turn; **E** permit transfers between any owned countries outside battle;
**F** allocate the full reinforcement budget at once; **G** retain the original
order and round boundaries when skipping eliminated players; **H** finish on the
final conquest.

The 195-country eligibility list, one-human/nine-NPC setup and saved full-order
shuffle are also approved conventions. The brief explicitly randomizes the first
participant; the shuffled order starts at index zero in round one.
