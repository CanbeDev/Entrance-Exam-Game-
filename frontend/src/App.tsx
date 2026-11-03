import { useEffect, useState, useSyncExternalStore } from 'react';
import { GameController } from './game/controller.ts';
import type { AppState } from './game/controller.ts';
import { AuthForm } from './components/AuthForm.tsx';
import { Dashboard } from './components/Dashboard.tsx';
import { GameBoard } from './components/GameBoard.tsx';
import { GameplayControls } from './components/Controls.tsx';
import { History } from './components/History.tsx';
import { Landing } from './components/Landing.tsx';
import { Rules } from './components/Rules.tsx';
import { WatchEntry, CopyWatchLink } from './components/WatchEntry.tsx';
import { presentationScreen } from './components/screen-view.ts';
import type { PageScreen } from './components/screen-view.ts';
import './components/screens.css';
import './base.css';
import { GameplaySound, SoundSettings, uiSound } from './sound/SoundSettings.tsx';

export function App() {
  const [controller] = useState(() => new GameController());
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const screen = presentationScreen(window.location.pathname);
    if (screen === 'rules') return () => controller.dispose();
    const path = /^\/games\/([a-fA-F0-9]{24})\/?$/.exec(window.location.pathname);
    void controller.initialize(path?.[1].toLowerCase() ?? null);
    const poll = setInterval(() => { void controller.poll(); }, 5000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { clearInterval(poll); clearInterval(tick); controller.dispose(); };
  }, [controller]);
  useEffect(() => {
    if (state.gameId && window.location.pathname !== `/games/${state.gameId}`) {
      window.history.replaceState(null, '', `/games/${state.gameId}`);
    }
  }, [state.gameId]);
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    if (state.pending) window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [state.pending]);
  return <AppView state={state} controller={controller} now={now} origin={window.location.origin} screen={presentationScreen(window.location.pathname)} />;
}

/** Presentation only: lifecycle, polling and navigation protection remain in App. */
export function AppView({ state, controller, now, origin, screen = 'home' }: {
  state: AppState; controller: GameController; now: number; origin: string; screen?: PageScreen;
}) {
  const disabled = !state.ready || state.busy || !!state.pending || now < state.retryAt;
  const recoveryLogin = !!state.pending && state.session?.user.id !== state.pending.account.id;
  const npcLimitReached = state.npcAttemptBudget !== null && state.npcAttempts >= state.npcAttemptBudget;
  const staticPage = screen === 'rules' || screen === 'invalid';
  const landing = !state.gameId && !state.session && !state.pending && !staticPage && screen !== 'watch';
  const accountForm = state.ready && (!state.session || recoveryLogin) && <AuthForm key={state.pending ? 'recovery' : 'login'}
    recoveryUsername={state.pending?.account.username} disabled={!state.ready || state.busy || now < state.retryAt}
    onSubmit={(credentials, register) => void controller.authenticate(credentials, register)} />;
  const watch = <WatchEntry disabled={disabled} origin={origin} open={id => void controller.openGame(id)} />;
  return <main className={state.gameId ? 'geo-ui geo-game-page' : 'geo-ui geo-screen-page'}>
    <a className="geo-skip-link" href="#page-content">Skip to content</a>
    <header><h1>Geopolitics</h1>
      {state.game && <p className="geo-game-context">{state.game.game_name} · Round {state.game.round ?? 'not recorded'} · {state.game.status ?? 'Status not recorded'}</p>}
      <nav aria-label="Main navigation">{!state.pending && <><a href="/">My Games / Home</a><a href="/new">New campaign</a><a href="/rules">Rules</a><a href="/watch">Watch</a></>}</nav>
      {state.game && <CopyWatchLink origin={origin} gameId={state.gameId!} disabled={!!state.pending} />}
      {state.session && <p>Logged in as {state.session.user.username}. <button disabled={disabled} onClick={() => void controller.logout()}>Log out</button></p>}
    </header>
    <div id="page-content" tabIndex={-1} />
    <SoundSettings />
    <GameplaySound state={state} />
    {!state.ready && !staticPage && <p className="geo-sync" role="status">Restoring session…</p>}
    {state.busy && !state.confirmingPending && <p className="geo-sync" role="status">{state.pending ? 'Waiting for the submitted action. Keep this page open.' : state.game ? 'Checking game status…' : 'Loading…'}</p>}
    {state.confirmingPending && <p role="status">Checking the saved NPC outcome using read-only history…</p>}
    {state.refreshing && !state.busy && <p className="geo-sync" role="status">Updating game…</p>}
    {state.refreshError && <p role="alert">Game update failed: {state.refreshError} The last confirmed board is still shown. Use Check game status to try again.</p>}
    {state.ready && state.gameId && !state.game && !state.busy && <section className="geo-empty" aria-labelledby="game-unavailable-title"><h2 id="game-unavailable-title">Game unavailable</h2>
      <p role="status">No game data is available. The link may be incorrect or the game could not be loaded. Review any error below or use Reconnect.</p>{watch}</section>}
    {state.notice && <p role="status">{state.notice}</p>}
    {state.error && <p role="alert">{state.error}</p>}
    {now < state.retryAt && <p role="status">Try again in {Math.ceil((state.retryAt - now) / 1000)} seconds.</p>}
    {state.pending && !state.busy && !state.fastForward && <section className="geo-recovery" aria-label="Unresolved request">
      <h2>Confirm your submitted move</h2>
      <p>The outcome is not yet confirmed. The original request is saved in this page and new moves are locked. Keep this page open; do not reload or submit a replacement move.</p>
      <p>Original account: {state.pending.account.username}.</p>
      {state.pending.kind !== 'create' && <p>Saved {state.pending.kind === 'npc' ? 'NPC' : 'human'} request:
        {' '}game {state.pending.operation.gameId}, expected revision {state.pending.operation.command.expected_revision}.</p>}
      {state.pending.kind === 'npc' && <p>First check the committed outcome. This only reads saved history and does not submit another move.</p>}
      {state.pending.kind === 'npc' && <button disabled={now < state.retryAt}
        onClick={() => void controller.checkPendingNpc()}>Check committed outcome (read only)</button>}
      <button disabled={now < state.retryAt || recoveryLogin || state.pending.kind === 'npc' && npcLimitReached}
        onClick={() => void controller.retryPending()}>Retry saved request</button>
      <p className="geo-help">Retry submits only the saved request with its original identity, after session and ownership checks. It does not create a replacement action.</p>
      {recoveryLogin && <p>Log in with the original account below. Signing in does not automatically retry the move.</p>}
      {state.pending.kind === 'npc' && npcLimitReached && <p>The configured NPC limit is reached. Read-only confirmation remains available; another NPC submission is blocked.</p>}
    </section>}
    {screen === 'rules' && !state.pending && <Rules />}
    {screen === 'invalid' && !state.pending && <><section className="geo-empty" role="alert"><h2>This link does not identify a game.</h2><p>Use a shared game link or return to My Games.</p></section>{watch}</>}
    {landing && <Landing>{accountForm}{watch}</Landing>}
    {recoveryLogin && !landing && accountForm}
    {!landing && !recoveryLogin && !staticPage && state.gameId && !state.session && <details className="geo-game-signin"><summary>Log in to play your own games</summary>{accountForm}</details>}
    {!state.gameId && !staticPage && !landing && <>
      {state.session && screen !== 'watch' && <Dashboard state={state} controller={controller} disabled={disabled} origin={origin} mode={screen === 'new' ? 'create' : 'library'} />}
      {screen === 'watch' && watch}
    </>}
    {state.game && <>
      <div className="geo-sync-tools"><button disabled={disabled || state.fastForward} onClick={() => void controller.refresh()}>Check game status</button>
        <span className="geo-help">{state.pending ? 'Resolve the saved request before refreshing.' : 'The board updates automatically.'}</span></div>
      <GameBoard key={state.gameId} game={state.game} owner={state.owner && !!state.session} pending={!!state.pending}
        latest={state.lastResult} committed={state.events} actions={
        <GameplayControls key={`${state.gameId}:${state.game.revision}`} game={state.game} owner={state.owner && !!state.session}
          disabled={disabled || state.fastForward} fastForward={state.fastForward}
          busy={state.busy} pending={!!state.pending} latest={state.lastResult} npcLimitReached={npcLimitReached}
          disabledReason={!state.ready ? 'Wait for session restoration.' : now < state.retryAt ? 'Wait for the retry delay above.' : undefined}
          act={(action) => void controller.act(action)} step={() => void controller.stepNpc()}
          fast={() => { void controller.fastForward(); if (controller.getSnapshot().fastForward) uiSound('fast'); }}
          pause={() => { const wasRunning = controller.getSnapshot().fastForward; controller.pause(); if (wasRunning) uiSound('pause'); }} />
      } history={<History key={`${state.gameId}:${state.session?.user.id ?? 'spectator'}`} game={state.game} events={state.events} latest={state.lastResult} more={state.moreEvents}
        api={controller.api} gameId={state.gameId!} canGenerateCommentary={state.owner && !!state.session && !disabled && !state.fastForward}
        commentaryAccountId={state.owner ? state.session?.user.id ?? null : null}
        liveCommentaryAllowed={state.owner && !!state.session && !state.pending && !state.busy}
        canStartCommentary={() => { const current = controller.getSnapshot();
          return current.gameId === state.gameId && current.session?.user.id === state.session?.user.id
            && current.owner && !!current.session && !current.pending && !current.busy; }}
        disabled={disabled || state.fastForward} loadMore={() => void controller.moreHistory()} />} />
    </>}
    {state.ready && state.error && !state.pending && <button disabled={disabled} onClick={() => void controller.initialize(state.gameId)}>Reconnect</button>}
    <footer className="geo-site-footer"><span>Geopolitics · UCT INF4001N 2027 entrance project</span><span>Map: Simplemaps (MIT) · Population data: Worldometer</span>
      {!state.pending && <a href="/rules#rules-watch">About battle narration and results</a>}</footer>
  </main>;
}
