export type PageScreen = 'home' | 'new' | 'rules' | 'watch' | 'invalid';

/** Presentation routes only. Game loading remains with the existing controller. */
export function presentationScreen(path: string): PageScreen {
  if (path === '/' || /^\/games\/[a-fA-F0-9]{24}\/?$/.test(path)) return 'home';
  if (/^\/new\/?$/.test(path)) return 'new';
  if (/^\/rules\/?$/.test(path)) return 'rules';
  if (/^\/watch\/?$/.test(path)) return 'watch';
  return 'invalid';
}
export function watchGameId(input: string, origin: string): string | null {
  const value = input.trim();
  if (/^[a-fA-F0-9]{24}$/.test(value)) return value.toLowerCase();
  try {
    const url = new URL(value, origin);
    if (url.origin !== new URL(origin).origin || !['http:', 'https:'].includes(url.protocol)
        || url.username || url.password || url.search || url.hash) return null;
    return /^\/games\/([a-fA-F0-9]{24})\/?$/.exec(url.pathname)?.[1].toLowerCase() ?? null;
  } catch { return null; }
}
export function watchLink(origin: string, gameId: string): string | null {
  if (!/^[a-fA-F0-9]{24}$/.test(gameId)) return null;
  try {
    const url = new URL(origin);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    return `${url.origin}/games/${gameId.toLowerCase()}`;
  } catch { return null; }
}
