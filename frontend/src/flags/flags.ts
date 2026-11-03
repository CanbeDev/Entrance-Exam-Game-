import flags from './countries.json';
/** Presentation aliases only; gameplay IDs, atlas aliases and stored records are untouched. */
const aliases: Readonly<Record<string, string>> = {
  'vatican-city': 'holy-see', 'czech-republic': 'czechia', palestine: 'state-of-palestine',
  eswatini: 'swaziland', 'united-kingdom': 'uk', 'united-states': 'us', 'cape-verde': 'cabo-verde', brunei: 'brunei-darussalam',
};
export function countryFlag(id: string | null | undefined): { canonicalId: string; src: string } | null {
  if (!id) return null;
  const canonicalId = Object.hasOwn(aliases, id) ? aliases[id]! : id;
  const code = Object.hasOwn(flags, canonicalId) ? (flags as Readonly<Record<string, string>>)[canonicalId] : null;
  return code && /^[a-z]{2}$/.test(code) ? { canonicalId, src: `/assets/flags/${code}.svg` } : null;
}
