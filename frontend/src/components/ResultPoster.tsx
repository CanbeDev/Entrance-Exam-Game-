import { useState } from 'react';
import type { PublicGame } from '../api/index.ts';
import { campaignResult } from './presentation.ts';
import './result-poster.css';

/** Formatting only; the result service already supplies the exact integer sum. */
export const formatResultSoldiers = (value: string): string => BigInt(value).toLocaleString('en-US');

/** Plain local image; unavailable assets become labelled text rather than a broken image. */
export function ResultFlag({ src, name }: { src: string | null; name: string }) {
  const [failed, setFailed] = useState(false);
  return <ResultFlagView src={src} name={name} failed={failed} onError={() => setFailed(true)} />;
}
export function ResultFlagView({ src, name, failed, onError }: { src: string | null; name: string; failed: boolean; onError: () => void }) {
  return src && !failed ? <img className="geo-result__flag" src={src} alt={`Flag of ${name}`} width={640} height={480} onError={onError} />
    : <div className="geo-result__flag-fallback" role="img" aria-label={`Flag unavailable for ${name}`}><span>National flag unavailable</span></div>;
}
export function ResultPoster({ game, owner = false, pending = false, celebrate = false, onSettled }: {
  game: PublicGame; owner?: boolean; pending?: boolean; celebrate?: boolean; onSettled?: () => void;
}) {
  const result = campaignResult(game);
  if (!result) return null;
  const personalVictory = owner && result.winner?.kind === 'human' && result.allTen;
  const personalDefeat = owner && result.winner?.kind === 'npc' && result.allTen && game.players?.filter(player => player.kind === 'human').length === 1;
  const name = result.name ?? 'Winner not recorded';
  return <section className={`geo-result${celebrate ? ' geo-result--arrive' : ''}`} aria-labelledby="campaign-result-outcome campaign-result-title"
    data-result={personalVictory ? 'victory' : 'complete'}
    data-flag-layout={result.flag?.canonicalId === 'nepal' ? 'irregular' : result.flag?.canonicalId === 'holy-see' ? 'bright' : 'rectangular'}
    onAnimationEnd={event => { if (event.target === event.currentTarget) onSettled?.(); }}>
    <header className="geo-result__top"><div>
      <p className="geo-result__headline" id="campaign-result-outcome">{personalVictory ? 'Victory' : 'Campaign Over'}</p>
      <p className="geo-result__subtitle">{personalVictory ? 'World Conqueror' : personalDefeat ? 'Defeat · Your participant was eliminated' : 'Campaign complete'}</p>
    </div><p className="geo-result__campaign">{game.game_name}</p></header>
    <div className="geo-result__art">
      <ResultFlag key={result.flag?.src ?? name} src={result.flag?.src ?? null} name={name} />
      <div className="geo-result__identity">
        <h2 id="campaign-result-title">{name}</h2>
        <p>{personalVictory ? 'The world is yours.' : result.winner ? `${name} has won the campaign.` : 'The campaign is complete. The winner is not recorded.'}</p>
        {result.winner && <p className="geo-result__kind">{result.winner.kind === 'human' ? 'Human winner' : 'NPC winner'}
          {result.allTen ? ' · Holds all ten participating countries' : ''}</p>}
      </div>
    </div>
    <div className="geo-result__achievement"><div className="geo-result__conquest">
      {result.held !== null ? <><span className="geo-result__number">{result.held}</span>
        <span className="geo-result__descriptor">of {result.total} participating countries held</span></>
        : <p className="geo-result__descriptor">Territorial outcome not recorded</p>}
    </div><dl className="geo-result__stats">
      {result.round != null && <div><dt>Campaign complete</dt><dd>Round {result.round}</dd></div>}
      {result.soldiers !== null && <div><dt>In the winner's countries</dt><dd>{formatResultSoldiers(result.soldiers)} soldiers</dd></div>}
    </dl><nav aria-label="Campaign result navigation"><a className="geo-result__primary" href="#campaign-record">Review campaign</a>
      {!pending && <a className="geo-result__secondary" href="/">Return to My Games</a>}</nav></div>
  </section>;
}
