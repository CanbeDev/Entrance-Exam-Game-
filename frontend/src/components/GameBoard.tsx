import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { PublicActionResult, PublicCommittedAction, PublicGame } from '../api/index.ts';
import { ResultPoster } from './ResultPoster.tsx';
import { LiveGameplay, SavedNpcDecision } from './LiveGameplay.tsx';
import { phaseLabel, nextSavedParticipant } from './gameplay-view.ts';
import { participantCountryName } from './refresh-view.ts';
import { observePresentation } from './presentation.ts';
import type { PresentationSnapshot } from './presentation.ts';
import { activeParticipant, participantName } from '../game/view.ts';
import { AtlasMap, AtlasRoster } from '../map/AtlasMap.tsx';
import { validateAtlas } from '../map/layout.ts';
import type { AtlasProps, MapData } from '../map/types.ts';
import mapData from '../map/mapData.generated.json';
import { CountryProgress, Panel, TurnIndicator } from '../ui/components.tsx';
import '../ui/components.css';
import '../map/atlas.css';
import './game-shell.css';
import { CountryCard, CountryInspection } from '../country/CountryCard.tsx';
import { uiSound } from '../sound/SoundSettings.tsx';

/** Read-only presentation adapter. It never repairs or writes authoritative state. */
export function boardPresentation(game: PublicGame, selectedId: string | null, onSelect: (id: string) => void) {
  const countries = game.countries ?? [], players = game.players ?? [];
  const human = players.find(player => player.kind === 'human');
  const ownershipKnown = countries.length === 10 && new Set(countries.map(c => c.id)).size === 10
    && players.length === 10 && new Set(players.map(p => p.id)).size === 10
    && countries.every(c => players.some(p => p.id === c.owner_id));
  const active = game.status === 'active' ? activeParticipant(game) : undefined;
  const battle = game.status === 'active' && game.phase === 'attacking' ? game.battle : null;
  const selected = countries.some(c => c.id === selectedId) ? selectedId : null;
  const home = active && countries.find(c => c.id === active.starting_country_id && c.owner_id === active.id);
  const atlas: AtlasProps = { countries, players, turnOrder: game.turn_order ?? [], onSelect, selectedId: selected,
    fromId: battle?.source_id, targetId: battle?.target_id,
    playingId: home?.id, battle: battle ? { ...battle, preview: false } : null, showRoster: false };
  let atlasAvailable = countries.length === 10 && players.length === 10;
  if (atlasAvailable) {
    try { validateAtlas(atlas, mapData as MapData); } catch { atlasAvailable = false; }
  }
  return { atlas, atlasAvailable, human, active, ownershipKnown,
    humanHeld: human && ownershipKnown ? countries.filter(c => c.owner_id === human.id).length : null };
}

export interface GameBoardProps {
  game: PublicGame;
  actions?: ReactNode;
  history?: ReactNode;
  owner?: boolean; pending?: boolean;
  latest?: PublicActionResult | null;
  committed?: readonly PublicCommittedAction[];
}
const emptyHistory: readonly PublicCommittedAction[] = [];

/** Kept mounted through revision/background updates; selection submits nothing. */
export function GameBoard(props: GameBoardProps) {
  const [selectedId, setSelected] = useState<string | null>(null);
  const select = (id: string | null) => { setSelected(id); if (id) uiSound('select'); };
  const previous = useRef<PresentationSnapshot | null>(null);
  const reducedMotion = useRef(false);
  const [feedback, setFeedback] = useState<{ celebrate: boolean; captured: string[] }>({ celebrate: false, captured: [] });
  const committed = props.committed ?? emptyHistory;
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => { reducedMotion.current = preference.matches;
      if (preference.matches) setFeedback({ celebrate: false, captured: [] }); };
    update(); preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    const old = previous.current;
    const events = props.latest && props.latest.state.revision === props.game.revision ? props.latest.events
      : committed.find(entry => entry.revision === props.game.revision)?.events ?? [];
    const next = observePresentation(old, props.game, events);
    previous.current = next.snapshot;
    if (old?.revision != null && next.snapshot.revision != null && next.snapshot.revision > old.revision)
      setFeedback(reducedMotion.current || props.pending ? { celebrate: false, captured: [] } : { celebrate: next.celebrate, captured: next.captured });
  }, [props.game, props.latest, props.pending, committed]);
  return <GameBoardContent {...props} selectedId={selectedId} onSelect={select} celebrate={feedback.celebrate}
    capturedIds={feedback.captured} onCelebrationSettled={() => setFeedback(value => ({ ...value, celebrate: false }))}
    onCaptureSettled={id => setFeedback(value => ({ ...value, captured: value.captured.filter(country => country !== id) }))} />;
}

export function GameBoardContent({ game, actions, history, latest, committed = emptyHistory, selectedId, onSelect, owner, pending, celebrate = false,
  capturedIds = [], onCelebrationSettled, onCaptureSettled }: GameBoardProps & {
  selectedId: string | null; onSelect: (id: string | null) => void;
  celebrate?: boolean; capturedIds?: readonly string[];
  onCelebrationSettled?: () => void; onCaptureSettled?: (id: string) => void;
}) {
  const model = boardPresentation(game, selectedId, onSelect);
  const ordered = game.turn_order?.map(id => game.players?.find(player => player.id === id));
  const orderKnown = !!ordered?.length && ordered.every(Boolean)
    && new Set(game.turn_order).size === game.turn_order!.length;
  const turnKnown = game.schema_version === 3 && game.status === 'active'
    && Number.isInteger(game.current_turn) && game.current_turn! >= 0
    && game.current_turn! < (ordered?.length ?? 0) && !!model.active
    && model.ownershipKnown && game.countries?.some(c => c.owner_id === model.active!.id);
  const next = turnKnown ? nextSavedParticipant(game) : null;
  return <div className="geo-game-board">
    <ResultPoster game={game} owner={owner} pending={pending} celebrate={celebrate} onSettled={onCelebrationSettled} />
    {game.status === 'active' && model.humanHeld === 0 && <section className="geo-elimination" aria-labelledby="elimination-title">
      <span className="geo-label">The campaign continues</span><h2 id="elimination-title">{owner ? 'Your participant has been eliminated.' : 'The human participant has been eliminated.'}</h2>
      <p>No countries remain under the human participant's control. The game is still active.</p>
      <p>{owner ? 'You can continue the remaining rival turns using Step or Fast-forward, or review the Chronicle.' : 'Follow the remaining rivals and their committed decisions in the Chronicle.'}</p>
      <a href="#history-title">Review the Chronicle</a>
    </section>}
    <section className="geo-situation" aria-labelledby="situation-title">
      <div><span className="geo-label">Round {game.round ?? 'not recorded'} · {model.active?.kind === 'human' ? 'Human turn' : model.active ? 'Rival turn' : game.status ?? 'Status not recorded'}</span>
        <h2 id="situation-title">{model.active ? `${participantCountryName(game, model.active.id)}’s turn` : game.status === 'completed' ? 'Campaign complete' : 'Current turn not recorded'}</h2>
        <p>{phaseLabel(game)}{next && <span className="geo-situation__next"> · Next in this round: {participantCountryName(game, next)}</span>}</p></div>
      <div className="geo-situation__control"><span className="geo-label">{owner ? 'Your' : 'Human'} territory control</span>
        {model.humanHeld !== null ? <CountryProgress held={model.humanHeld} label="Human participant's countries held" /> : <p>Not recorded</p>}</div>
      <nav className="geo-game-shortcuts" aria-label="Gameplay sections">
        <a href="#game-actions">{owner ? 'Go to actions' : 'Viewing controls'}</a><a href="#live-action">Latest action</a><a href="#countries-title">Countries</a><a href="#history-title">Chronicle</a>
      </nav>
    </section>
    <details className="geo-turn-strip">
      <summary id="turn-order-title">Full turn order{orderKnown ? ` · ${ordered!.length} participants` : ''}</summary>
      {orderKnown ? <ol>{ordered!.map((player, index) => {
        const eliminated = model.ownershipKnown && !game.countries!.some(c => c.owner_id === player!.id);
        const state = eliminated ? 'eliminated' : turnKnown ? index === game.current_turn ? 'active'
          : index < game.current_turn! ? 'completed' : 'upcoming' : null;
        return <li key={player!.id} data-turn-player={player!.id}>
          {state ? <TurnIndicator name={participantName(game, player!.id)} state={state} />
            : <span>{participantName(game, player!.id)} · {game.status === 'completed' ? 'Game complete' : 'Turn status not recorded'}</span>}
        </li>;
      })}</ol> : <p>Saved turn order is not available.</p>}
    </details>
    <div className="geo-game-grid" id="campaign-record" tabIndex={-1}>
      <Panel title="World atlas" className="geo-game-map">
        {model.atlasAvailable ? <><AtlasMap {...model.atlas} capturedIds={capturedIds} onCaptureSettled={onCaptureSettled}
          inspectedId={selectedId} onInspect={onSelect} information={selectedId && <CountryCard key={selectedId} id={selectedId} game={game}
            dismiss={() => { onSelect(null); document.getElementById('inspect-country')?.focus(); }} />} />
        </> : <p>The atlas is unavailable for these incomplete or historical country identities. Available records remain in the country list.</p>}
        {model.atlas.selectedId && <p className="geo-help">Home participant: {participantName(game,
          game.players?.find(p => p.starting_country_id === model.atlas.selectedId)?.id)}.</p>}
        <CountryInspection game={game} selectedId={selectedId} select={onSelect} showCard={!model.atlasAvailable} />
        <details className="geo-board-help"><summary>Campaign details</summary>
          <dl className="geo-game-facts">
            <div><dt>Status</dt><dd>{game.status ?? 'Not recorded'}</dd></div>
            <div><dt>Revision</dt><dd>{game.revision ?? 'Not recorded'}</dd></div>
            {game.winner && <div><dt>Winner</dt><dd>{participantName(game, game.winner)}</dd></div>}
          </dl>
        </details>
      </Panel>
      <aside className="geo-panel geo-game-actions" aria-label="Game actions">
        <div id="game-actions" tabIndex={-1}>{actions ?? <p>No action controls supplied.</p>}</div>
        <SavedNpcDecision game={game} latest={latest} committed={committed} />
      </aside>
      <div className="geo-panel geo-game-live"><LiveGameplay game={game} latest={latest} committed={committed} pending={pending} /></div>
      <div id="countries-title" tabIndex={-1} className="geo-game-roster"><Panel title="Countries and soldiers">
        {model.atlasAvailable ? <AtlasRoster {...model.atlas} /> : <table>
          <caption>Available country records</caption>
          <thead><tr><th scope="col">Country</th><th scope="col">Held by</th><th scope="col">Soldiers</th></tr></thead>
          <tbody>{game.countries?.map(country => <tr key={country.id}>
            <th scope="row">{country.name}</th><td>{participantName(game, country.owner_id)}</td><td>{country.soldiers}</td>
          </tr>)}</tbody>
        </table>}
        {!game.countries?.length && <p>No country records are available.</p>}
        {model.humanHeld === 0 && game.countries?.length === 10 && <p>The human participant has been eliminated.
          {game.status === 'active' && ' The remaining rivals can finish the match.'}</p>}
        <details className="geo-board-help"><summary>About ownership</summary><p className="geo-help">A country stays in play when its original participant is eliminated. Its ring and owner label identify its current owner.</p></details>
      </Panel></div>
      <div className="geo-panel geo-game-history" aria-label="Chronicle">
        {history ?? <p>No history supplied.</p>}
      </div>
    </div>
  </div>;
}
