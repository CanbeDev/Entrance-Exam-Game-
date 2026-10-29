import type { SubmitEvent } from 'react';
import type { AppState } from '../game/controller.ts';
import type { GameController } from '../game/controller.ts';

export function Dashboard({ state, controller, disabled }: { state: AppState; controller: GameController; disabled: boolean }) {
  function search(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void controller.dashboard({ query: String(data.get('query')), status: String(data.get('status')) as 'active' || undefined });
  }
  function create(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void controller.create({ game_name: String(data.get('game_name')), starting_country_id: String(data.get('starting_country_id')) });
  }
  return <>
    <section aria-labelledby="games-title">
      <h2 id="games-title">My Games</h2>
      <form onSubmit={search}><fieldset disabled={disabled}>
        <legend>Find a saved game</legend>
        <label>Search games <input name="query" maxLength={100} defaultValue={state.filters.query ?? ''} /></label>
        <label>Status <select name="status" defaultValue={state.filters.status ?? ''}>
          <option value="">All statuses</option><option value="active">Active</option>
          <option value="completed">Completed</option><option value="waiting">Waiting</option>
        </select></label>
        <button type="submit">Search</button>
      </fieldset></form>
      {state.games ? <>
        {state.games.games.length === 0 ? <p>No matching games. Start a new game below.</p> : <ul>
          {state.games.games.map((game) => <li key={game._id}>
            <a href={`/games/${game._id}`}>{game.game_name}</a> — {game.status}, round {game.round ?? '—'}
          </li>)}
        </ul>}
        <p>Page {state.cursors.length}</p>
        <button disabled={disabled || state.cursors.length === 1} onClick={() => void controller.page(false)}>Previous page</button>
        <button disabled={disabled || !state.games.next_cursor} onClick={() => void controller.page(true)}>Next page</button>
      </> : <p>Saved games are not loaded.</p>}
    </section>
    <section aria-labelledby="create-title">
      <h2 id="create-title">Start a new game</h2>
      <form onSubmit={create}><fieldset disabled={disabled || !state.catalog}>
        <legend>Choose your starting country</legend>
        <label>Game name <input name="game_name" required maxLength={100} /></label>
        <label>Starting country <select name="starting_country_id" required defaultValue="">
          <option value="" disabled>Choose a country</option>
          {state.catalog?.countries.map((country) => <option value={country.id} key={country.id}>
            {country.name} — {country.base_soldier_value} starting soldiers
          </option>)}
        </select></label>
        <p>Nine other countries and the first participant are selected by the server.</p>
        <button type="submit">Create game</button>
      </fieldset></form>
    </section>
  </>;
}
