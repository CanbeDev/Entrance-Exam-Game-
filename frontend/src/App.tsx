import { useEffect, useState, useSyncExternalStore } from 'react';
import type { SubmitEvent } from 'react';
import { GameController } from './game/controller.ts';
import { AuthForm } from './components/AuthForm.tsx';
import { Dashboard } from './components/Dashboard.tsx';
import { GameBoard } from './components/GameBoard.tsx';
import { GameplayControls } from './components/Controls.tsx';
import { History } from './components/History.tsx';
import './base.css';

export function App() {
  const [controller] = useState(() => new GameController());
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const path = /^\/games\/([a-fA-F0-9]{24})\/?$/.exec(window.location.pathname);
    void controller.initialize(path?.[1].toLowerCase() ?? null);
    const poll = setInterval(() => controller.poll(), 5000);
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
  const disabled = !state.ready || state.busy || !!state.pending || now < state.retryAt;
  function open(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void controller.openGame(String(data.get('game_id')).toLowerCase());
  }
  return <main>
    <header><h1>Geopolitics</h1>
      <nav aria-label="Main navigation">{!state.pending && <a href="/">My Games / Home</a>}</nav>
      {state.session && <p>Logged in as {state.session.user.username}. <button disabled={disabled} onClick={() => void controller.logout()}>Log out</button></p>}
    </header>
    {!state.ready && <p role="status">Restoring session…</p>}
    {state.busy && <p role="status">Loading…</p>}
    {state.notice && <p role="status">{state.notice}</p>}
    {state.error && <p role="alert">{state.error}</p>}
    {now < state.retryAt && <p role="status">Try again in {Math.ceil((state.retryAt - now) / 1000)} seconds.</p>}
    {state.pending && !state.busy && <section aria-label="Unresolved request">
      <p>The submitted request is saved in this page. Retry the same request before leaving; a new request could repeat an operation.</p>
      <button disabled={now < state.retryAt} onClick={() => void controller.retryPending()}>Retry saved request</button>
    </section>}
    {state.ready && !state.session && <AuthForm disabled={disabled} onSubmit={(credentials, register) => void controller.authenticate(credentials, register)} />}
    {!state.gameId && <>
      {state.session && <Dashboard state={state} controller={controller} disabled={disabled} />}
      <section aria-labelledby="watch-title"><h2 id="watch-title">Watch a shared game</h2>
        <form onSubmit={open}><fieldset disabled={disabled}>
          <legend>Open a public game</legend>
          <label>Game ID <input name="game_id" required pattern="[a-fA-F0-9]{24}" maxLength={24} /></label>
          <button type="submit">View game</button>
        </fieldset></form>
      </section>
    </>}
    {state.game && <>
      <p>Share this game: <a href={`/games/${state.gameId}`}>{window.location.origin}/games/{state.gameId}</a></p>
      <button disabled={disabled || state.fastForward} onClick={() => void controller.refresh()}>Refresh game</button>
      <div className="play-area">
        <GameBoard game={state.game} />
        <GameplayControls key={`${state.gameId}:${state.game.revision}`} game={state.game} owner={state.owner && !!state.session}
          disabled={disabled || state.fastForward} fastForward={state.fastForward}
          act={(action) => void controller.act(action)} step={() => void controller.stepNpc()}
          fast={() => void controller.fastForward()} pause={() => controller.pause()} />
      </div>
      <History game={state.game} events={state.events} latest={state.lastResult} more={state.moreEvents}
        disabled={disabled || state.fastForward} loadMore={() => void controller.moreHistory()} />
    </>}
    {state.ready && state.error && !state.pending && <button disabled={disabled} onClick={() => void controller.initialize(state.gameId)}>Reconnect</button>}
  </main>;
}
