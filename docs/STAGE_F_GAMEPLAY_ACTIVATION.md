# Stage F: production gameplay activation and acceptance

Latest response-confirmation investigation, 2026-10-31 (user-provided evidence):
one newly approved NPC attempt from expected revision 7 committed revision 8,
receipt `npc-balanced-v1-1-7`, NPC Cambodia (`npc-4`), a two-soldier transfer to
Seychelles. Its decision explanation persisted. The production tab on `02aea09`
still displays revision 7 and its saved operation; the attempt counter is 1 of 3.
No further NPC POST is authorized during this investigation. The public receipt
confirms commitment; this review has not changed or reconciled the browser tab.

Earlier continuation status, 2026-10-31 (user-confirmed): production frontend
`02aea09`, game `6ae4c18db5333f4d0e2e50a9`, revision 7, NPC Cambodia in
`post_attack` after conquering Seychelles. The original expected-revision-6
operation was reconciled through committed revision-7 history. No retry is
needed. This supersedes the unresolved status in the historical record below;
the agent did not execute production recovery or gameplay.

The following original activation plan is retained as historical context. Use
the final continuation procedure at the end for the current existing game.

Prepared 2026-10-30. Offline review/procedure only. No production access or
change, application-code change, test execution, commit or push was performed.

## Accepted baseline and blockers

Use the user's confirmed Vercel frontend `https://entrance-exam-game.vercel.app`,
Render API `https://entrance-exam-game.onrender.com` and database
`geopolitics_game`. D2 is passed/closed, D3 is complete and Stage E core production
authentication passed. Current user-confirmed settings are auth true, gameplay
false and exactly the Vercel origin trusted.

Stage E evidence supplied by the user: registration 201; login, CSRF, restoration
and My Games 200; logout 204; bad login 401; missing CSRF 403; missing Origin
403 origin_rejected; Secure/HttpOnly/SameSite=Lax cookie flags observed. Absence
of Domain in the live Set-Cookie was not independently confirmed. Source omits
Domain and the existing cookie test explicitly asserts its absence. This is a
recorded evidence gap, not a demonstrated gameplay-activation blocker.

No genuine activation blocker is demonstrated by the offline review. Reuse the
757-pass isolated backend baseline, recorded real TEST transaction/ownership
coverage, 23-pass validator-enabled TEST suite, D2, 54 frontend tests and manual
offline-fixture acceptance. Do not repeat them. Actual production gameplay is
what Stage F will establish; a successful signup is not proof of every game path.

## Exact change and controlled rollout (separate approval required)

Change only `PHASE4_GAMEPLAY_WRITES_ENABLED` from `false` to `true`:

```text
PHASE4_AUTH_WRITES_ENABLED=true
PHASE4_GAMEPLAY_WRITES_ENABLED=true
PHASE4_TRUSTED_ORIGINS=["https://entrance-exam-game.vercel.app"]
```

1. Confirm the two unchanged values above. Leave all credentials, database,
   limits, proxy and other environment settings unchanged.
2. Save/apply the single flag change in one controlled Render configuration
   rollout. No source deploy or separate diagnostic restart is requested.
3. Check that rollout's fresh logs and successful application startup/live
   status. Existing lifespan rejects startup unless storage readiness is ready
   whenever either write flag is enabled. Configuration also forbids gameplay
   without auth and auth without trusted origins. No explicit ready log line is
   emitted; neither an old worker nor /health alone proves this rollout passed.
4. STOP if startup/readiness fails. Do not bypass guards, repair/provision storage
   or reopen D2. Begin the bounded journey only after the rollout succeeds.

## Existing operations used by the frontend

All browser requests stay under the Vercel origin. Paths below include `/api`;
the rewrite removes that prefix before FastAPI. Use the designated Stage E
account; no new account or fixture identity is required.

| Operation | Contract |
| --- | --- |
| GET /api/countries | Public catalog; select starting_country_id and compare starting soldiers to base_soldier_value |
| POST /api/games | game_name, starting_country_id; original Idempotency-Key; session, Origin, CSRF; 201 state |
| GET /api/me/games | Authenticated owner listing/search/filter/cursor; 200 |
| GET /api/games/{id} | Public authoritative state; 200 |
| GET /api/games/{id}/events | Public committed history; after_revision/limit; 200 |
| POST /api/games/{id}/actions | action_id, expected_revision, exact action; session, owner, Origin, CSRF; 200 state/events |
| POST /api/games/{id}/npc-steps | expected_revision; same protections; 200 state/events/npc_decision; one NPC action |

Action types remain allocate, transfer, start_attack, roll, stop_attack, skip and
end_turn. The UI supplies typed payloads; do not invent aliases or game actor IDs.
Use ActionOutcome.state for display; route identity is separate when returned
action state omits _id. Preserve the original receipt's events/NPC explanation.

## One bounded acceptance journey (separate approval required)

Scope: ONE new game named `Stage F Acceptance 2026-10-30`, using the existing
designated account. Select a catalog country with at least two starting soldiers
(preferably a high base value). Do not assume the human goes first or survives.
Do not touch either historical game. Record the new game ID once returned.

Bound the entire acceptance session to at most 30 NPC POST attempts, including
earlier attempts and retries. Reconcile the used allowance first; its remaining
balance is not assumed. After separately approved deployment of the recovery
patch, set the optional NPC acceptance limit before testing. The limit is a total
for the current page and includes individual actions and retries. It resets on
reload; changing it does not reset its counter. Keep an external total across
pages. No five-second manual Pause requirement applies. Use an attended capped
run; it must stop at the cap, human turn, completion, Pause or any error. Let an
already-submitted action settle. If the allowance is unknown or exhausted, STOP.
If the human turn is not reached within scope, record NOT EXERCISED and request
further approval. No intentional invalid writes, disconnects or failure injection.

Continuation safety: the existing acceptance game is
`6ae4c18db5333f4d0e2e50a9`. Do not create another game to continue this procedure.
The user reports an unresolved saved NPC request. Preserve its original tab and
exact game/revision/account identity; do not reload to obtain the patch. A later
deployment cannot migrate that in-memory operation. Before any fresh gameplay,
separately authorize one identical recovery attempt within the verified remaining
allowance. A replay may return a receipt or perform the original move if it never
committed. Stop again on interruption, preparation/auth/ownership failure,
conflict or rate limit; a disappearing retry button alone is not reconciliation.

1. Log in through Vercel using the designated account. Create the named game
   once. Expect 201 and one owned game ID. Confirm ten distinct countries, one
   human/nine NPCs, one initial owner per country, initial soldiers equal the
   catalog's base values, round 1 and current participant selected by the saved
   turn_order/current_turn. The randomized first participant may be an NPC.
2. If necessary, advance NPCs within the budget until a legal human turn. At the
   human deciding phase, choose an owned source with at least two soldiers and
   any enemy target. Start attack, then perform ONE roll. Expect separate server
   events and returned dice/losses, not particular numbers or a guaranteed conquest.
   Paired dice retain their returned order; ties lose no soldier. Compare the
   displayed board to authoritative returned state, never local calculations.
3. If the battle continues, use Stop attack to end the turn. If it ended in
   conquest/forced failure, use the available post_attack controls. Transfer only
   when two owned countries and a legal positive amount exist, retaining one
   soldier at source. Otherwise allocate the full server budget if an allocating
   phase is reached later. Do not force conquest or an illegal move to tick a box.
   If neither transfer nor allocation becomes legal within scope, keep that
   acceptance item open; it is not itself a defect.
4. End the human turn only using an available legal control. Advance at least one
   NPC action. Expect a committed revision/event and strategic npc_decision
   explanation. Test the attended capped fast-forward run and Pause; explanations
   must stay visible. It must stop at a human turn, completion or error. After
   Pause, no further POST may start after the current request finishes.
5. Pause all progression and wait for the current request to settle. If a saved
   request or uncertain result remains, STOP and keep the original tab; retain
   its key/action ID/payload/revision/account for reviewed recovery. Do not reload.
   Only after reconciliation, note the authoritative revision, turn, ownership
   and soldiers. Reload, then return to My Games and reopen the SAME ID. Expect
   the same state/revision and committed history; GETs must not advance the game.
   Recovery uses only an explicitly approved identical saved-request retry,
   never a new identity or another creation click.
6. Open the copied game URL in an unauthenticated Incognito session. Expect
   public board/history and no gameplay controls or gameplay POSTs. Reuse existing
   backend/real TEST and frontend non-owner-denial evidence for the second-account
   case; no extra production account is needed. Do not claim a new live
   cross-account denial test was performed.

Record PASS/STOP/NOT EXERCISED per item and only non-sensitive metadata: game ID,
revision, action IDs, statuses, board observations and event/explanation presence.
Do not capture passwords, Cookie/CSRF header values or connection strings.

## Expected writes and scope evidence

Expected gameplay effects are one new owned game and its action receipts/state
updates. Normal authentication/session authorization-fence and rate-limit records
also update during this journey, including authenticated GETs; these are expected,
not unexplained game mutations. No credential/schema/role changes are in scope.

Verify every game mutation targets the recorded new ID and that its committed
events/revisions correspond to the submitted operations. No mutation request may
target a historical ID. This is request/state/receipt evidence, not independent
BSON-level proof that other documents are byte-identical. No Atlas access or new
broad database audit is proposed. Stop if evidence suggests an unrelated mutation.

## STOP and 409 interpretation

- Stop requests/fast-forward on startup/readiness failure, unexpected 401/403,
  409/429/5xx, uncertain write, wrong ownership, missing auth protection, unexplained
  revisions, unrelated mutations, failure to pause, or rules inconsistent with
  the official brief and approved GAME_RULES.md conventions.
- 409 revision_conflict can be a legitimate stale request: the API refetches
  state and never blindly resubmits. Pause, inspect current state/history and
  choose a new action only as a deliberate new user intent. An old idempotent
  replay may return an older receipt; it must not rewind newer displayed state.
- Repeated conflicts for fresh serialized valid requests, action_id_conflict on
  an unchanged saved operation, or state changes from a rejected action require
  investigation. Do not replace an ID merely to force acceptance.
- For 429, honor Retry-After without retry loops. For expiry, permission failures
  or uncertain/5xx responses, preserve evidence and original operation identities
  before any deliberate recovery; do not keep playing through an unexplained error.

## Rollback (must be explicitly included in approval, or separately approved)

For failed startup/readiness or a functional/security/data-integrity blocker,
stop gameplay requests and approve/apply this single flag rollback once:

```text
PHASE4_AUTH_WRITES_ENABLED=true
PHASE4_GAMEPLAY_WRITES_ENABLED=false
PHASE4_TRUSTED_ORIGINS=["https://entrance-exam-game.vercel.app"]
```

Only gameplay changes back to false. Confirm fresh successful startup. Preserve
Stage E auth, all game/account/session records and historical games. No delete,
restore, role change, schema change or source rollback is included. An ordinary
recoverable 409 or 429 pauses testing; it is not automatic grounds for a rollout.

## Next approval

Approve (1) the single gameplay-flag configuration rollout, (2) the named one-game
acceptance journey above, including normal auth/session/rate-limit effects and
the bounded NPC budget, and (3) gameplay-only rollback if the stated blocker
conditions occur. Alternatively approve activation alone first and authorize
the journey/rollback separately. No part has been executed by this review.

Mandatory GroqCloud battle commentary and final submission evidence remain
outstanding; this core gameplay acceptance does not certify the full assignment.

References: [API contract](api-contract.md), [Stage E](STAGE_E_AUTH_ACTIVATION.md),
[rules/conventions](../backend/docs/GAME_RULES.md),
[test evidence](../backend/docs/TESTING.md),
[requirements](../backend/docs/REQUIREMENTS.md).

## Pending NPC identity: user-reported memory evidence, 2026-10-31

This local operational record supplements the earlier activation plan. The user
ran the approved memory-only expression in the original production tab; the agent
did not independently inspect that tab. No recovery is claimed or authorized here.

| Field | Captured evidence |
| --- | --- |
| Game ID | `6ae4c18db5333f4d0e2e50a9` |
| Pending operation | `npc` |
| Original request body | `{"expected_revision":6}` |
| Displayed revision | `6` |
| Cached account | `test_user1`; all three cached account IDs reported equal |
| Cached ownership | true; ownership-check game and session object match |
| Cached absolute expiry | null; server session freshness remains unverified |
| Client activity | busy/fast-forward/refreshing false; mutations 0; no background read |
| Retry delay | 0 |

Committed cached NPC receipts:

| Committed revision | Action ID | Original expected revision |
| --- | --- | --- |
| 5 | `npc-balanced-v1-1-4` | 4 |
| 6 | `npc-balanced-v1-1-5` | 5 |

The pending expected-revision-6 operation is distinct from the committed
revision-6 receipt. Its successful successor would be revision 7, which has not
been verified. No additional cached history pages were indicated; that is not a
fresh server observation. The reported Render 200 at 19:48:15 on 2026-10-30 has
not been conclusively correlated with this pending operation.

The total NPC POST attempt count and remaining original 30-attempt allowance are
unknown. Preserve the original tab and the user's sanitized JSON, including its
actual public account ID values. Do not reload, retry, change identity or assume
cached ownership/session data proves current authorization. A separately approved
anonymous public history read after revision 6 may establish commitment without a
new NPC POST. No such request or deployment has been performed by this review.

## Final bounded continuation proposal, 2026-10-31

Investigation/documentation only. No production test is authorized by this text.
User-confirmed production evidence covers authentication, game creation, human
battles/transfers, NPC decisions/dice/conquest, persistence, My Games, anonymous
spectators and reconciliation of the original uncertain operation at revision 7.
The 105-test offline baseline covers recovery, serialization, attempt limits,
Pause and stopping at a human turn or completion. Do not repeat Stage D/E checks.

The original 30-NPC-POST balance cannot be reconstructed from the available
receipts and uncorrelated Render responses. Successful replays count as attempts
without advancing revision. Request separate approval for at most THREE additional
NPC POST attempts, explicitly amending the former budget; do not claim these fit
within an established remaining balance. Include individual steps and any later
separately approved saved retries in that same three-attempt allowance.

After approval only:

1. Use the same owned game and account, revision-7 baseline, with no unresolved
   request or active mutation. Record the displayed per-page NPC attempt count C.
2. Set the optional maximum to C + 3, and confirm the displayed limit before
   starting. No reload, navigation, extra tab, limit increase or counter reset
   during the test. An unset or unknown limit/count means STOP.
3. Click Fast-forward NPCs once. Observe each authoritative board update and
   decision explanation. Click Pause during an in-flight action if possible;
   there is no five-second deadline. The already-submitted action may settle.
4. After the submitted action settles, observe at least two seconds with no new
   NPC POST after Pause. If idle, error-free and still on an NPC turn, resume
   only within the unchanged C + 3 ceiling. If automatic
   stopping occurred before Pause could be exercised, record Pause NOT TESTED
   rather than spending another allowance without approval.
5. Stop at the ceiling, human turn, completion, Pause or any error. Record the
   actual attempt delta, distinct committed receipts, final revision/turn/phase,
   visible dice/losses/outcomes and retained explanations/history. Preserve the
   existing revision-7 conquest entry. Do not retry automatically on failure.

PASS applies only to exercised conditions: at most three additional NPC POSTs,
serialized execution, one revision increment per distinct new committed action,
cap/Pause stopping, visible events/explanations, and no NPC POST once a human turn
or completion is reached. FAIL and STOP immediately on a cap breach, duplicate
commit, overlapping client mutations, POST after Pause/human/completion, state
rewind or loss of committed evidence. STOP without declaring a safety failure on
an uncertain response, unexpected 401/403/409/429/5xx, wrong account/game, reset
counter or unknown allowance. Preserve any new pending identity for review.

Live fast-forward/Pause/cap evidence remains PARTIAL pending this test. Live
human-return/completion boundaries and round-two allocation/full-match victory
are not established by the supplied production record; retain their offline test
evidence and do not force them within this small smoke test. A cap-stop alone
does not prove a live human-return. Further bounded continuation needs separate
approval if full production end-to-end acceptance is required. Mandatory
GroqCloud battle commentary remains a separate Phase 4 submission gap.

Phase 4 recommendation (not implemented): hide configuration/counters by default
in normal play; retain an explicit opt-in acceptance mode with a finite allowance
required before NPC submissions. Keep the guard at the API submission boundary,
independent of panel visibility. Hiding/closing a panel must not clear the cap;
loss of test configuration must stop acceptance mode rather than select unlimited
play. Ordinary fast-forward still proceeds visibly to the human turn/completion.
This client test aid grants no privileges and is not a server-enforced quota.

## NPC response-confirmation diagnosis and local correction

The delivery failure's root cause remains unresolved: there is no failed POST's
browser duration/status to distinguish the 20-second frontend deadline from a
network/proxy failure. A Render 200 does not establish complete browser delivery.
The separately observed background GET 503 is not proof of a common cause.

Source flow: App fast-forward -> GameController.stepNpc/submitPending ->
GameApi.npcStep/mutate -> HttpClient.request -> Vercel rewrite -> FastAPI npc_step
-> authenticated/CSRF/owned facade -> NpcController preparation and validated
GameActionService execution -> atomic revision update plus receipt -> public
response -> HTTP parse/cache -> controller board/history. The client timer is
20 seconds through response parsing. Pause does not abort the POST. MongoDB's
5-second connection/selection and 10-second socket limits are per operation,
not a total NPC request deadline. Repository config does not establish hosted
proxy runtime limits; no infrastructure change is justified by current evidence.

Confirmed gaps: uncertain NPC outcomes had no read-only receipt-confirmation path;
body-read TypeError/abort failures were classified as malformed; an older received
receipt followed by a failed state refresh could release pending without a usable
UI outcome. The local correction checks the existing public event endpoint once,
and reads the public board if the exact NPC receipt matches. It preserves the
original account/operation/observation and lock on mismatch or failure, and stops
fast-forward even when read-only confirmation succeeds. A manual read-only check
is also available. It adds no mutation endpoint, request replay or idempotency key.
The existing NPC semantic replay key remains game + expected revision + NPC kind;
canonical server action ID, original actor and turn sequence corroborate it.

Timeout and AbortController deadline behavior remain unchanged. New sanitized
diagnostics distinguish response wait, body read and validation, elapsed time and
observed HTTP headers without storing secrets or raw driver text. This fixes the
confirmation gap and improves future evidence; it does not claim to eliminate
unmeasured backend/proxy/network latency. No production request, retry, deployment,
environment change, gameplay-rule change or NPC-strategy change was performed.

Verification: 141 frontend tests passed, 0 failed/skipped, including all previous
105 and 36 new deterministic confirmation cases. TypeScript/Vite build, 40 OpenAPI
component checks and whitespace checks passed. No backend tests were repeated:
backend/engine source is unchanged. The official brief's visible fast-forward,
battle events and NPC explanations, and the marksheet's functionality/UI/security
criteria remain the relevant constraints. Mandatory G17 commentary is still absent.

Review/deployment boundary: this patch is local only. The production `02aea09` tab
does not gain the new check button or observation metadata automatically. Preserve
its saved expected revision 7 and the verified revision-8 receipt before any later
approved transition. A future production verification should use a separately
approved bounded allowance and record the new sanitized diagnostics if a natural
failure occurs; do not force disconnects or retry the old operation for this review.
No further NPC POST is currently authorized, regardless of the displayed 1/3.
