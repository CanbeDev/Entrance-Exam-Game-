# Stage 9 - human connected-game acceptance

Date: 2026-11-03, Africa/Johannesburg. The human operates the connected game;
Codex reviews sanitized evidence. No Codex production access or mutation is authorized.

## Before playing

Record the connected frontend URL/build, backend environment, date/browser and
campaign name/ID. Use your own already-authorized account. Never paste credentials,
cookies, CSRF tokens, MongoDB URIs or full HAR files into reports/chat.

- Use the reviewer-designated connected site, not the inert `5175` presentation
  preview or scripted `5174` mock server. Localhost alone does not prove database isolation.
- Confirm the tested build actually includes the UI/audio patch. A different live
  build cannot certify these changes. Do not deploy or repoint a proxy as part of this guide.
- Keep any old pending production tab untouched. In the chosen test game, establish
  no unresolved operation before starting; do not infer this from revision alone.
- Respect any current environment-specific action allowance. Do not reuse historical
  Stage F balances or expose the hidden developer cap. If a configured cap is
  reached, record it and stop; do not bypass/reset it with reload.
- Create only a campaign already covered by your manual testing authorization.
  One complete match is the first priority; an opposite result or rare tie can
  remain NOT TESTED until encountered in further authorized play.
- Turn on Sound deliberately and choose comfortable volume. After refresh, use
  Enable playback in this tab if shown. Sound-panel playback already passed human
  review; it does not establish connected action-trigger success.

For each row replace NOT TESTED with PASS or FAIL only after observation. Record
game ID, before/after revision, action/round, brief expected-versus-actual detail
and a screenshot or sanitized request status/duration on failure. Show no secrets.
An accepted API response is not sufficient if board/history contradict it.

## Start and first human turn

| # / Where | What to do | Expected result | Record if it fails | Result |
| --- | --- | --- | --- | --- |
| 1. Login | Log in with your own account. When safe later, test session restoration, logout and login again. If registration is in scope, use one authorized account only. | Correct identity; owner controls only for your campaigns. Ordinary checks reuse accepted Stage E behavior; no infrastructure revalidation. | Error text/status and build; no password/session data. | NOT TESTED |
| 2. My Games | Search by campaign name, filter by supported status and use Next/Previous when available. Resume an existing owned campaign if available. | Only your games; real summary fields; correct game resumes. Empty/paging branches not encountered remain NOT TESTED. | Search/filter, displayed game ID/status and unexpected entries. | NOT TESTED |
| 3. New campaign / country | Choose a canonical starting country; inspect population/starting soldiers. Listen for selection feedback. Enter a name and click Create game once. | Selected human country, nine server-selected distinct rivals and one created campaign. No rival preview before creation. | Selection, population/base value, creation count and returned ID. | NOT TESTED |
| 4. Board / roster | Count the ten countries and participants. Inspect flags, soldiers, ownership and saved turn order. | One human/nine NPCs; initial soldiers follow population bands; first actor may be NPC. All ten countries remain accessible on map/roster. | Country IDs, starting values, active actor/round and screenshot. | NOT TESTED |
| 5. First turn | If an NPC starts, use Steps 10-13 until your turn. Otherwise inspect available human actions. | No round-one reinforcement; controls match the authoritative active actor/phase. | Actor/phase and any wrongly enabled action. | NOT TESTED |

## Battle and turn progression

| # / Where | What to do | Expected result | Record if it fails | Result |
| --- | --- | --- | --- | --- |
| 6. Your turn - Start an attack | Choose an owned source with at least two soldiers and any enemy target, including a distant country if available. Start attack. | Pair locks; attack cue follows confirmation; no dice until Roll battle dice. One attack per turn; geography does not restrict targets. | Source/target IDs, soldiers, phase and receipt/revision. | NOT TESTED |
| 7. Battle / Chronicle | Roll once; compare each saved pair in original order. Continue normally, or test Stop attack and end turn on a suitable later turn. | Each side rolls min(source soldiers minus one, target soldiers), with no three-dice cap. Lower die loses one; tie loses none. Source retains at least one. Stop ends the turn. | Before counts, all dice pairs, losses, after counts and revision. Rare unobserved branches stay NOT TESTED. | NOT TESTED |
| 8. Conquest | Continue until a country is conquered when feasible. Inspect ownership/reward and committed history. | Ownership changes once; reward max(2, floor(captured base soldiers / 2)) is already placed there. No separate conquest-confirm step. Final conquest completes immediately. | Captured base, reward, current owner/soldiers, receipt. | NOT TESTED |
| 9. After attack | If you hold two countries and the source can spare soldiers, use Transfer soldiers with a positive amount, then End turn. Test Skip turn on another deciding turn when suitable. | Transfer moves the exact amount and leaves one; no new attack after conquest this turn. Skip/end advances the server turn. | Before/after counts, amount, selected countries and revision. | NOT TESTED |
| 10. NPC controls - Step | Click Advance one NPC action once; observe board and explanation. | One serialized NPC operation; saved decision/explanation and actual result. Controls prevent overlapping moves. A single action need not finish the whole NPC turn. | Actor, phase, request count/identities if available, before/after revision. | NOT TESTED |
| 11. NPC controls - Fast-forward | Click Fast-forward NPCs once. Watch several committed actions. | Visible sequential moves, explanations and dice; stops at the human turn, game completion, cap or error. No speed selector or manual five-second deadline. | Ordered revisions, actor transitions, explanation and any overlapping request evidence. | NOT TESTED |
| 12. Pause during processing | While a request is visibly in flight, click Pause NPC fast-forward. If no request is caught in flight, record that branch NOT TESTED. A repeated Pause action, if still available, must be harmless. | No further NPC action is scheduled. The already-submitted one may settle or enter recovery; Pause does not undo a committed move. | Pause time, request already started, subsequent request starts, final/pending revision. | NOT TESTED |
| 13. Resume | After the in-flight result is definitively reconciled and no operation remains pending, click Fast-forward NPCs again if it is still an NPC turn. | Starts from the latest state, with no duplicate old move or skipped required human decision. | Previous receipt identity/revision, first resumed receipt and current actor. | NOT TESTED |
| 14. Safe refresh / persistence | Pause, wait for no busy/pending operation, then use Check game status. Reload/reopen only after settlement and within any test limits. If an interruption occurs naturally, follow the STOP procedure below instead. | Same committed board/history and correct ownership; no historical success sounds, duplicate narration or replacement mutation. | Before/after ID, revision, soldiers, history and sanitized failure. | NOT TESTED |
| 15. Round two onward | Reach your next allocating turn. Allocate the complete displayed pool across owned countries and submit once. | Exactly two new soldiers per currently held country at turn start. Full pool assigned, then normal actions unlock; eliminated actors receive none. | Round, held-country count, pool, allocations and resulting counts. | NOT TESTED |

## Sound, commentary and finish

| # / Where | What to do | Expected result | Record if it fails | Result |
| --- | --- | --- | --- | --- |
| 16. Sound | During the actual actions above, listen for selection, attack, dice/loss, conquest, transfer, NPC, Fast-forward/Pause and newly completed result cues. Change volume, mute during playback, then restore it. After a safe reload confirm the preference and explicit tab activation. | Confirmed events produce their configured cues; mute stops/prevents audio. No success sound for uncertain/failed writes, duplicate receipts or old game/result loads. Sound never blocks moves/Pause. | Missing event, receipt/revision, enabled/activation/volume, motion mode and device. Give each event its own result below. | NOT TESTED |
| 17. Chronicle - Commentary | Keep Commentary for new battles on. Observe newly committed human and NPC dice exchanges, including Fast-forward. Expand their entries. Briefly opt out/re-enable during appropriate play. | Generation is automatic for eligible new owner exchanges; saved prose appears under the corresponding exchange. Dice/results remain authoritative. Opt-out prevents queued new work; re-enable does not backfill history. Fallback is truthful, not proof of Groq success. | Revision/action ID, human/NPC, ready/fallback/pending state, saved prose and sanitized status. | NOT TESTED |
| 18. Spectator | Copy watch link after settlement; open it in a separate signed-out/private window. Keep the owner tab unchanged. | Public board, history and saved commentary; no play or generation controls. Viewing does not create commentary. | URL game ID, visible controls and any unexpected request type; no cookies. | NOT TESTED |
| 19. Human elimination | If you lose all countries, inspect the outcome and continue NPC play as the owner while the game remains active. Otherwise leave this branch NOT TESTED. | Human is eliminated; owner may still advance NPCs. Eliminated actors are skipped; remaining countries keep real ownership. | Held-country counts, active/completed status and subsequent actors. | NOT TESTED |
| 20. Complete match | Continue legal human turns and NPC playback until one participant holds all ten. Do not stop evidence collection at human elimination alone. | Server marks completed, winner set and gameplay stops. No additional NPC move after final conquest. | Final board, revision, winner, round and final committed victory event. | NOT TESTED |
| 21. Flag Poster | Inspect the completed result on desktop and a narrow viewport. Listen for the new result cue. | Actual winner/home-country flag, ten held countries and real final data. Human victory or NPC victory uses the correct perspective and exactly the corresponding victory/defeat cue. | Winner/flag, totals, perspective, sound and viewport screenshot. | NOT TESTED |
| 22. Reopen completed match | After settlement, return to My Games and reopen/view result. Log out when safe; confirm signed-out read access and no play controls. | Saved completed state/history/commentary persists; no move, victory/defeat replay or automatic historical narration generation. | Final versus reopened revision/state, unexpected sound/request or changed totals. | NOT TESTED |

### Per-event audio record

| Event | Result (PASS / FAIL / NOT TESTED) | Receipt/revision or local action; observation |
| --- | --- | --- |
| Country selection | NOT TESTED | |
| Attack initiation | NOT TESTED | |
| Dice roll | NOT TESTED | |
| Soldier-loss aftermath | NOT TESTED | |
| Conquest | NOT TESTED | |
| Transfer | NOT TESTED | |
| NPC Step / specific committed NPC result | NOT TESTED | |
| Fast-forward | NOT TESTED | |
| Pause | NOT TESTED | |
| New human victory | NOT TESTED | |
| New NPC victory / owner defeat | NOT TESTED | |
| Mute / volume / preference restore | NOT TESTED | |
| Historical/duplicate receipts stay silent | NOT TESTED | |
| Uncertain write has no false success cue | NOT TESTED | |

One representative loss cue may follow dice's natural end. Mixed losses select
defender-loss priority; rapid/reduced-motion/Skip can omit aftermath. Newer cues
replace older audio, and fast-forward cooldown intentionally suppresses some
cues. Do not require every loss clip in one exchange or delay gameplay for audio.
Mark an event NOT TESTED if its required circumstance did not occur.

## STOP and evidence procedure

Stop new moves on duplicate/conflicting receipts, wrong ownership, inconsistent
soldiers/reinforcement, inability to finish, an unexpected account, uncertainty or
an error. Pause when available. Keep a pending tab open: do not reload, navigate,
logout, switch accounts or submit a replacement move. Do not deliberately force
a network failure or retry for this acceptance run.

Capture non-secret game ID, displayed revision, original expected revision/action
identity if already visible, actor/phase, warning and sanitized Network status/
duration. A server 200 or newer board alone does not establish the original
operation committed. Existing Check committed outcome (read only) uses receipt
evidence; an identical saved-request retry requires separate recovery review and
applicable allowance. No automatic replay should occur.

When finished, send the filled results, tested build/environment, final game ID/
revision/winner, unresolved branches and selected sanitized screenshots/receipts.
Codex will update the [existing acceptance report](UI_STAGE9_ACCEPTANCE_REPORT.md)
without restarting completed automated work. Report both generation and display
for commentary; provider success requires approved evidence beyond a fallback.

Before submission, separately confirm audio rights, source ZIP, deployed URL,
README, examiner application/database access and required disclosures. Supply
credentials through the official private submission channel, never public source.
Deadline supplied by the reviewer: **Friday, 6 November 2026, 23:00 SAST**.
