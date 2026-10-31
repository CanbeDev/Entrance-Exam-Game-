import { useEffect, useRef, useState } from 'react';
import type { BattleCommentary, GameApi, PublicCommittedAction, PublicGame } from '../api/index.ts';

export interface CommentaryDisplay {
  commentary: BattleCommentary | null;
  loading: boolean;
  error: string | null;
  requested: boolean;
}
function summary(game: PublicGame, entry: PublicCommittedAction): string {
  const battle = entry.events.find((event) => event.type === 'dice_exchange');
  if (!battle) return '';
  const country = (id: string | null | undefined) => game.countries?.find((item) => item.id === id)?.name ?? id ?? 'Unknown country';
  const outcome = entry.events.some((event) => event.type === 'conquered') ? ' A conquest was committed.' : '';
  const eliminated = entry.events.some((event) => event.type === 'eliminated') ? ' A participant was eliminated.' : '';
  return `${country(battle.source_id)} attacked ${country(battle.target_id)}. Attacker dice: ${battle.attacker_dice?.join(', ') || 'none'}; defender dice: ${battle.defender_dice?.join(', ') || 'none'}. Attacker losses: ${battle.attacker_losses ?? 0}; defender losses: ${battle.defender_losses ?? 0}.${outcome}${eliminated}`;
}

/** Pure presentation keeps narration clearly separate from authoritative dice/results. */
export function BattleCommentaryView({ game, entry, display, canGenerate, generate, check }: {
  game: PublicGame; entry: PublicCommittedAction; display: CommentaryDisplay; canGenerate: boolean;
  generate: () => void; check: () => void;
}) {
  const value = display.commentary;
  const ai = value?.status === 'ready' && value.source === 'groq';
  const pending = value?.status === 'pending';
  return <section aria-label={`AI Battle Commentary for move ${entry.revision}`}>
    <h5>AI Battle Commentary</h5>
    {display.loading && <p role="status">Loading battle commentary. Gameplay remains available.</p>}
    {pending && <p role="status">AI commentary is being prepared. Check its saved outcome; no automatic retry is sent.</p>}
    <p>{ai ? 'LLM-generated narration' : 'Deterministic battle summary'}: {value?.text || summary(game, entry)}</p>
    <p>Dice, losses and ownership shown above are the authoritative game results.</p>
    {display.error && <p role="status">{display.error}</p>}
    {value?.status === 'fallback' && <p>AI narration is unavailable for this move. The saved summary remains available.</p>}
    {canGenerate && !display.loading && !display.requested && (!value || value.status === 'not_generated')
      && <button onClick={generate}>Generate AI commentary</button>}
    {!display.loading && (pending || value?.status === 'not_generated' || display.error || display.requested && !ai && value?.status !== 'fallback')
      && <button onClick={check}>Check saved commentary</button>}
  </section>;
}

export function BattleCommentaryPanel({ api, gameId, game, entry, canGenerate, automatic, permitted }: {
  api: GameApi; gameId: string; game: PublicGame; entry: PublicCommittedAction; canGenerate: boolean;
  automatic?: CommentaryDisplay;
  permitted: () => boolean;
}) {
  const [display, setDisplay] = useState<CommentaryDisplay>({ commentary: null, loading: true, error: null, requested: false });
  const active = useRef(false);
  const generation = useRef(0);
  const revision = entry.revision, actionId = entry.action_id;
  useEffect(() => {
    const current = ++generation.current;
    active.current = true;
    setDisplay({ commentary: null, loading: true, error: null, requested: false });
    void api.battleCommentary(gameId, revision).then((value) => {
      if (generation.current !== current) return;
      if (value.action_id !== actionId) throw new Error('Commentary identity mismatch');
      setDisplay({ commentary: value, loading: false, error: null, requested: false });
    }).catch(() => {
      if (generation.current === current) setDisplay({ commentary: null, loading: false,
        error: 'Saved AI commentary could not be loaded. The battle summary is still available.', requested: false });
    }).finally(() => { if (generation.current === current) active.current = false; });
    return () => { generation.current++; active.current = false; };
  }, [api, gameId, revision, actionId]);
  useEffect(() => {
    if (!automatic || automatic.commentary && automatic.commentary.action_id !== actionId) return;
    setDisplay((previous) => ({ ...automatic, commentary: automatic.commentary ?? previous.commentary }));
  }, [automatic, actionId]);
  async function request(generate: boolean) {
    if (active.current || generate && !canGenerate) return;
    active.current = true;
    const current = generation.current;
    setDisplay((previous) => ({ ...previous, loading: true, error: null, requested: previous.requested || generate }));
    try {
      const value = generate ? await api.generateBattleCommentary(gameId, revision, permitted) : await api.battleCommentary(gameId, revision, true);
      if (generation.current !== current) return;
      if (value.action_id !== actionId) throw new Error('Commentary identity mismatch');
      setDisplay((previous) => ({ ...previous, commentary: value, loading: false, error: null }));
    } catch {
      if (generation.current === current) setDisplay((previous) => ({ ...previous, loading: false,
        error: 'AI commentary could not be confirmed. Gameplay is unaffected; check the saved commentary without resubmitting.' }));
    } finally { if (generation.current === current) active.current = false; }
  }
  return <BattleCommentaryView game={game} entry={entry} display={display} canGenerate={canGenerate}
    generate={() => { void request(true); }} check={() => { void request(false); }} />;
}
