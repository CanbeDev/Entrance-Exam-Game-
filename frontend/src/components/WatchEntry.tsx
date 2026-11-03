import { useId, useState } from 'react';
import type { SubmitEvent } from 'react';
import { watchGameId, watchLink } from './screen-view.ts';

export function WatchEntry({ disabled, origin, open }: { disabled: boolean; origin: string; open: (id: string) => void }) {
  const [error, setError] = useState('');
  const hint = useId();
  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    const id = watchGameId(String(new FormData(event.currentTarget).get('game_id')), origin);
    if (!id) { setError('Enter a 24-character game ID or a game link from this site.'); return; }
    setError(''); open(id);
  }
  return <section className="geo-watch" aria-labelledby="watch-title"><span className="geo-label">Just watching?</span>
    <h2 id="watch-title">Watch a shared game</h2>
    <p>Follow the countries, battles and saved commentary. Anyone with the link can watch; only the owner can play.</p>
    <form onSubmit={submit}><fieldset disabled={disabled}><legend className="geo-visually-hidden">Open a public game</legend>
      <label>Game link or ID <input name="game_id" required maxLength={2048} aria-describedby={hint}
        aria-invalid={!!error} autoComplete="off" placeholder="Paste a game link or ID" onChange={() => setError('')} /></label>
      <p id={hint} className="geo-help">Use a shared link from this site, or the game's 24-character ID.</p>
      <button className="geo-screen-primary" type="submit">View game</button>
    </fieldset></form>
    {error && <p role="alert">{error}</p>}
  </section>;
}

export function CopyWatchLink({ origin, gameId, disabled = false }: { origin: string; gameId: string; disabled?: boolean }) {
  const [message, setMessage] = useState('');
  const link = watchLink(origin, gameId);
  if (!link) return null;
  return <span className="geo-share">{!disabled && <a href={`/games/${gameId}`}>Watch link</a>}
    <button type="button" disabled={disabled} onClick={() => {
      if (disabled) return;
      if (!navigator.clipboard?.writeText) { setMessage(`Copy this link: ${link}`); return; }
      void navigator.clipboard.writeText(link).then(() => setMessage('Watch link copied.'), () => setMessage(`Copy this link: ${link}`));
    }}>Copy watch link</button>
    {message && <span className="geo-help" role="status">{message}</span>}
  </span>;
}
