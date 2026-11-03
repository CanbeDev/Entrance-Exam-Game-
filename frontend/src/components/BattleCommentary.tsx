import { useEffect, useRef, useState } from 'react';
import type { BattleCommentary, GameApi, PublicCommittedAction, PublicGame } from '../api/index.ts';

export interface CommentaryDisplay {
  commentary: BattleCommentary | null;
  loading: boolean;
  error: string | null;
  requested: boolean;
}
/** Pure presentation keeps narration clearly separate from authoritative dice/results. */
export function BattleCommentaryView({ entry, display, canGenerate, generate, check }: {
  game: PublicGame; entry: PublicCommittedAction; display: CommentaryDisplay; canGenerate: boolean;
  generate: () => void; check: () => void;
}) {
  const value = display.commentary;
  const ready = value?.status === 'ready' && value.source === 'groq';
  const pending = value?.status === 'pending';
  const text = value && ['ready', 'fallback'].includes(value.status) ? value.text : '';
  const box = !!text || display.loading || pending;
  return <>
    {box && <section className="geo-commentary" aria-label={`Commentary for move ${entry.revision}`}>
      <h5>Commentary</h5>
      {text && <p className="geo-commentary__prose">{text}</p>}
      {display.loading && <p role="status">Loading commentary. Gameplay remains available.</p>}
      {pending && <p role="status">Commentary is being prepared. Check its saved outcome when ready.</p>}
      {value?.status === 'fallback' && <p className="geo-help">Saved battle summary.</p>}
    </section>}
    {display.error && <p role="status">Commentary could not be confirmed. Gameplay is unaffected; check its saved outcome before trying again.</p>}
    {!box && !display.error && <p className="geo-help">Commentary is not available for this exchange.</p>}
    {canGenerate && !display.loading && !display.requested && (!value || value.status === 'not_generated')
      && <button onClick={generate}>Generate commentary</button>}
    {!display.loading && (pending || value?.status === 'not_generated' || display.error || display.requested && !ready && value?.status !== 'fallback')
      && <button onClick={check}>Check saved commentary</button>}
  </>;
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
