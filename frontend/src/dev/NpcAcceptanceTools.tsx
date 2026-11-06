import type { AppState, GameController } from '../game/controller.ts';

/** Imported only by the isolated development entry. Never configures a limit on mount. */
export function NpcAcceptanceTools({ state, controller }: { state: AppState; controller: GameController }) {
  return <details><summary>Optional NPC acceptance limit · development only</summary>
    <p>NPC POST attempts on this page: {state.npcAttempts}. Limit: {state.npcAttemptBudget ?? 'not set'}.</p>
    <form onSubmit={event => {
      event.preventDefault();
      controller.configureNpcBudget(Number(new FormData(event.currentTarget).get('npc_limit')));
    }}><fieldset disabled={state.busy || state.fastForward}>
      <legend>Maximum NPC POST attempts on this page</legend>
      <label>Limit <input name="npc_limit" type="number" required min={0} step={1} defaultValue={state.npcAttemptBudget ?? ''} /></label>
      <button type="submit">Set limit</button>
    </fieldset></form>
    <p>Includes individual actions and retries. Changing the limit preserves the counter; reloading resets this per-page aid.
      Production testing requires separate approval and a verified configured allowance. This fixture submits no NPC requests.</p>
  </details>;
}
