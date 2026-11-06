import { useState } from 'react';
import type { SubmitEvent } from 'react';
import type { AppState, GameController } from '../game/controller.ts';
import type { GameFilters } from '../api/index.ts';
import { CopyWatchLink } from './WatchEntry.tsx';
import { receiptTime } from './chronicle-view.ts';
import { uiSound } from '../sound/SoundSettings.tsx';
import { countryFlag } from '../flags/flags.ts';

type Props = { state: AppState; controller: GameController; disabled: boolean; origin?: string; mode?: 'all' | 'library' | 'create' };
export function Dashboard({ mode = 'all', ...props }: Props) {
  return <>{mode !== 'create' && <GameLibrary {...props} />}{mode !== 'library' && <NewCampaign {...props} />}</>;
}
export function GameLibrary({ state, controller, disabled, origin = '' }: Props) {
  function search(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault(); if (disabled) return;
    const data = new FormData(event.currentTarget), status = String(data.get('status'));
    void controller.dashboard({ query: String(data.get('query')), status: status === '' ? undefined : status as GameFilters['status'] });
  }
  const filtered = !!state.filters.query || !!state.filters.status;
  return <section className="geo-library" aria-labelledby="games-title">
    <header className="geo-page-heading"><div><span className="geo-label">Your campaign library</span><h2 id="games-title">My Games</h2>
      <p>Resume a campaign, review its result, or begin again with a new country.</p></div>
      {!state.pending && <a className="geo-screen-primary" href="/new">New campaign</a>}</header>
    <form className="geo-library__filters" onSubmit={search}><fieldset disabled={disabled}>
      <legend className="geo-visually-hidden">Find a saved game</legend>
      <label>Search games <input name="query" maxLength={100} defaultValue={state.filters.query ?? ''} placeholder="Search by campaign name" /></label>
      <label>Status <select name="status" defaultValue={state.filters.status ?? ''}><option value="">All statuses</option>
        <option value="active">Active</option><option value="completed">Completed</option><option value="waiting">Waiting</option></select></label>
      <button type="submit">Search</button></fieldset></form>
    {state.games ? <>
      {state.games.games.length === 0 ? <div className="geo-empty"><span className="geo-label">{filtered ? 'No matches' : 'A clean map'}</span>
        <h3>{filtered ? 'No campaigns match this search.' : 'Your first campaign starts with one choice.'}</h3>
        <p>{filtered ? 'Try a different game name or status.' : 'Pick a starting country and meet nine randomly selected rival commanders.'}</p>
        {!filtered && !state.pending && <a href="/new">Choose your country</a>}</div>
        : <ol className="geo-library__list">{state.games.games.map(game => {
          const updated = game.updated_at ? receiptTime(game.updated_at) : null;
          return <li key={game._id}><article className="geo-campaign" aria-label={game.game_name}>
            <div className="geo-campaign__title"><h3><a href={`/games/${game._id}`}>{game.game_name}</a></h3>
              <span className="geo-campaign__status">{game.status === 'completed' ? 'Completed' : game.status === 'active' ? 'Active' : 'Waiting'}</span></div>
            <dl><div><dt>Round</dt><dd>{game.round ?? 'Not recorded'}</dd></div>
              {updated && <div><dt>Updated</dt><dd><time dateTime={game.updated_at!}>{updated}</time></dd></div>}</dl>
            <div className="geo-campaign__links"><a className="geo-screen-primary" href={`/games/${game._id}`}>{game.status === 'completed' ? 'View result' : 'Resume'}</a>
              <CopyWatchLink origin={origin} gameId={game._id} disabled={!!state.pending} /></div>
          </article></li>;
        })}</ol>}
      <nav className="geo-library__pages" aria-label="Saved game pages"><span>Page {state.cursors.length}</span>
        <button disabled={disabled || state.cursors.length === 1} onClick={() => { if (!disabled && state.cursors.length > 1) void controller.page(false); }}>Previous page</button>
        <button disabled={disabled || !state.games.next_cursor} onClick={() => { if (!disabled && state.games?.next_cursor) void controller.page(true); }}>Next page</button></nav>
    </> : <div className="geo-empty" role="status"><h3>{state.busy ? 'Loading your campaigns…' : 'Saved games are not loaded.'}</h3>
      <p>{state.busy ? 'Your campaign library will appear when the server responds.' : 'Check your connection and try again.'}</p>
      {!state.busy && <button disabled={disabled} onClick={() => { if (!disabled) void controller.dashboard(); }}>Load My Games</button>}</div>}
  </section>;
}

export function NewCampaign({ state, controller, disabled }: Props) {
  const [selected, setSelected] = useState('');
  const [query, setQuery] = useState('');
  const country = state.catalog?.countries.find(item => item.id === selected);
  const flag = countryFlag(country?.id);
  const choices = state.catalog?.countries.filter(item => item.id === selected || item.name.toLowerCase().includes(query.toLowerCase().trim())) ?? [];
  function create(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault(); if (disabled || !country) return;
    void controller.create({ game_name: String(new FormData(event.currentTarget).get('game_name')), starting_country_id: country.id });
  }
  return <section className="geo-setup" aria-labelledby="create-title">
    <header className="geo-page-heading"><span className="geo-label">New campaign</span><h2 id="create-title">Choose where your story begins.</h2>
      <p>Choose your country. The server selects nine distinct rivals and the turn order when you create the game.</p></header>
    <div className="geo-setup__layout"><form onSubmit={create}><fieldset disabled={disabled || !state.catalog}>
      <legend>Choose your starting country</legend>
      <label>Find a country <input value={query} onChange={event => { if (!disabled) setQuery(event.target.value); }} type="search" maxLength={100} /></label>
      <label>Starting country <select name="starting_country_id" required value={selected} onChange={event => { if (!disabled) { setSelected(event.target.value); uiSound('confirm'); } }}>
        <option value="" disabled>Choose a country</option>{choices.map(item => <option value={item.id} key={item.id}>{item.name} — {item.base_soldier_value} starting {item.base_soldier_value === 1 ? 'soldier' : 'soldiers'}</option>)}
      </select></label>
      {choices.length === 0 && state.catalog && <p role="status">No countries match that name.</p>}
      <label>Game name <input name="game_name" required maxLength={100} placeholder="Name your campaign" /></label>
      <p className="geo-help">You are not guaranteed to take the first turn. Rivals appear after creation succeeds.</p>
      <button className="geo-screen-primary" disabled={!country} type="submit">Create game</button>
      {!country && <p className="geo-help">Choose a country before creating your campaign.</p>}
    </fieldset></form><aside className="geo-country-detail" aria-live="polite"><span className="geo-label">Your starting position</span>
      {country ? <>{flag && <img key={flag.src} className="geo-setup-flag" src={flag.src} alt={`Flag of ${country.name}`} width={64} height={48} onError={event => { event.currentTarget.hidden = true; }} />}<h3>{country.name}</h3><dl><div><dt>Population</dt><dd>{country.population.toLocaleString('en-US')}</dd></div>
        <div><dt>Starting soldiers</dt><dd className="geo-country-detail__soldiers">{country.base_soldier_value}</dd></div></dl>
        <p>Starting strength comes from the population band. Reinforcements and conquests will change your position during play.</p></>
        : <><h3>One country. Your choice.</h3><p>Select a country to see its recorded population and starting soldiers.</p></>}
      {!state.catalog && <p role="status">The country catalog is unavailable. Wait for loading or use Reconnect if an error is shown.</p>}
      {!state.pending && <a href="/rules#rules-setup">See starting soldier bands</a>}
    </aside></div>{!state.pending && <a className="geo-setup__back" href="/">Return to My Games</a>}
  </section>;
}
