import { useEffect, useRef, useState } from 'react';
import type { CommentaryPreference, GameApi } from '../api/index.ts';

export function useCommentaryPreference(api: GameApi, gameId: string, accountId: string | null) {
  const [value, setValue] = useState<CommentaryPreference | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const generation = useRef(0);
  const active = useRef(false);
  async function check(current = generation.current) {
    if (!accountId || active.current) return;
    active.current = true; setBusy(true);
    try {
      const response = await api.commentaryPreference(gameId);
      if (response.game_id !== gameId) throw new Error('Preference identity mismatch');
      if (current === generation.current) { setValue(response); setError(false); }
    } catch { if (current === generation.current) setError(true); }
    finally { if (current === generation.current) { active.current = false; setBusy(false); } }
  }
  useEffect(() => {
    const current = ++generation.current;
    active.current = false; setValue(null); setError(false);
    void check(current);
    return () => { generation.current++; active.current = false; };
  }, [api, gameId, accountId]);
  async function change(enabled: boolean) {
    if (!value || value.mode !== 'worker' || active.current || !accountId) return;
    const current = generation.current;
    active.current = true; setBusy(true); setError(false);
    try {
      const response = await api.setCommentaryPreference(gameId, enabled, value.version);
      if (response.game_id !== gameId) throw new Error('Preference identity mismatch');
      if (current === generation.current) setValue(response);
    } catch {
      // No automatic POST retry. An explicit check reconciles uncertain consent.
      if (current === generation.current) { setValue(null); setError(true); }
    } finally { if (current === generation.current) { active.current = false; setBusy(false); } }
  }
  return { value, busy, error, check: () => check(), change };
}
