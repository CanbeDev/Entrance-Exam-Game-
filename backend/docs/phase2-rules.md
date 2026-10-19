# Phase 2 rule contract

Authority: official INF4001N 2027 Geopolitics brief pp.2-5 and official 2027
marksheet (both reread before this implementation). Approved user conventions
resolve operational ambiguities; they are not additional official UCT rules.
See REQUIREMENTS.md for the requirement/evidence/rubric checklist.

## Mandatory rules

- Preserve the randomly selected, persisted participant order from setup.
- One attack per turn or skip. Any enemy country is reachable regardless of geography.
- Attacker needs at least two soldiers; one always stays behind.
- Per exchange both sides roll min(attacker - 1, defender) independent dice, 1..6.
- Pair by index, without sorting. Higher roll defeats one opposing soldier;
  tied pairs cause no casualties. Resolve an entire exchange simultaneously.
- Continue until capture, source has one soldier, or voluntary stop. Stopping
  immediately ends the turn; failure never forfeits the source territory.
- Conquest reward is max(2, floor(country soldier value / 2)).
- Transfers only between owned countries outside a battle, leaving one behind.
- No reinforcements in round 1. From round 2, award two per controlled country
  at turn start, distributed among controlled countries.
- Zero countries means elimination: skip future turns and award no reinforcements.
- Ownership of all ten countries wins.

## Approved conventions A-H and clarifications

A. Reward uses immutable population-derived base_soldier_value, including recapture.
B. Reward goes to captured country; surviving attackers stay at their source.
   Any other movement requires an explicit transfer that leaves one behind.
C. Source and target lock for the entire attack. Starting and rolling are separate
   actions. Each roll resolves one exchange; there is no arbitrary exchange limit.
D. After conquest or forced failure, enter post_attack: allow legal transfers
   and end_turn, but no second attack. stop_attack ends the turn immediately.
E. Transfers can involve any owned countries, including starting/newly captured
   ones, in deciding/post_attack only. No additional count limit.
F. Allocate the complete reinforcement budget atomically before any other action.
G. Preserve original slots and round boundary; eliminated slots are skipped.
   Wraparound increments the round even when skipped slots straddle the boundary.
H. Final conquest applies casualties, reward and ownership, then completes the game
   immediately, without waiting for optional transfers/end_turn.

Actor identity is a trusted local service input, not authentication. Human and
NPC actors obey identical legality checks. No strategic NPC choices, public write
routes, frontend, authentication, commentary, deployment or live data writes are
part of this phase. Factual events support those later mandatory features.

## Architecture and compatibility

RuntimeGame (schema 3) is separate from InitializedGame (schema 2). Phase 1 setup
and old read endpoints remain unchanged. A valid schema-2 setup is adapted in
memory; only a valid committed action persists its schema-3 runtime fields.
Waiting/unsupported legacy games remain readable but reject gameplay. Reads do
not migrate documents. Runtime country/player/order containers are immutable;
the dispatcher constructs and validates a new state, never mutating its input.
Runtime timestamps normalize to UTC milliseconds to match BSON's date precision
and the existing client's default naive-UTC reads; client settings stay unchanged.

The engine has no FastAPI/MongoDB imports. GameActionService handles receipt lookup,
revision checks, injected dice/clock, and repository commit. MongoActionRepository
receives an explicit database/client; it never imports the production connection.
Transactional writes are disabled by default and require explicit opt-in after
real verification. See phase2-verification.md before enabling them.

Receipts store the full original result and factual events. Their deterministic
compound game/action _id uses MongoDB's built-in unique index. State update and
receipt insert commit in a single transaction. No unbounded receipt array is added
to the game document. Identical retries return the original receipt; reused IDs
with different content fail. Revision conflicts are not silently replayed against
new state. Transaction retries reuse the precomputed dice/events/result.
