import { useEffect, useRef, useState } from 'react';
import type { PublicGame } from '../api/index.ts';
import { countryFacts, canonicalCountries } from './facts.ts';
import './country.css';
export function CountryCard({ id, game, dismiss }: { id: string; game?: PublicGame; dismiss: () => void }) {
  const model = countryFacts(id, game), [failed, setFailed] = useState(false);
  if (!model) return <p role="status">Country information is unavailable.</p>;
  const number = (value: number | null) => value == null ? 'Not recorded' : value.toLocaleString('en-US');
  return <section id="country-info" tabIndex={-1} className="geo-country-card" aria-label={`Country information: ${model.name}`} onKeyDown={event => {
    if (event.key === 'Escape') { event.stopPropagation(); dismiss(); }
  }}>
    <header><h4>{model.name}</h4>{model.flag && !failed && <img src={model.flag.src} alt={`Flag of ${model.name}`} width={32} height={24} onError={() => setFailed(true)} />}
      <button type="button" aria-label="Close country information" onClick={dismiss}>×</button></header>
    <dl>
      {model.capital && <div><dt><span aria-hidden="true">⌂</span> Capital reference</dt><dd>{model.capital}</dd></div>}
      <div><dt><span aria-hidden="true">◎</span> Population</dt><dd>{number(model.population)}</dd></div>
      <div><dt><span aria-hidden="true">♟</span> Starting soldiers</dt><dd>{number(model.startingSoldiers)}</dd></div>
      {model.participating ? <><div><dt><span aria-hidden="true">♟</span> Current soldiers</dt><dd>{number(model.currentSoldiers)}</dd></div>
        <div data-target={model.target || undefined}><dt><span aria-hidden="true">⚑</span> Held by</dt><dd>{model.owner ?? 'Not recorded'}{model.target ? ' · TARGET' : model.from ? ' · FROM' : ''}</dd></div></>
        : <div><dt>Game status</dt><dd>Neutral · Not participating</dd></div>}
    </dl>
    <details className="geo-country-card__sources"><summary>About these country facts</summary><p>Population and starting soldiers: {model.snapshot}. Starting soldiers are the initial allocation, not today's total. Neutral countries have no current soldiers or owner.</p>
      {model.capital && <p>Capital reference: GeoNames (CC BY 4.0). This single-city reference is not a complete account of every constitutional or administrative arrangement.</p>}
    </details>
  </section>;
}
export function CountryInspector({ game, selectedId, select, showCard = true }: { game: PublicGame; selectedId: string | null; select: (id: string | null) => void; showCard?: boolean }) {
  const [query, setQuery] = useState('');
  const options = canonicalCountries.filter(c => c.id === selectedId || c.name.toLowerCase().includes(query.toLowerCase().trim()));
  function dismiss() { select(null); document.getElementById('inspect-country')?.focus(); }
  return <div className="geo-country-inspector">
    <label htmlFor="inspect-search">Find country information</label><input id="inspect-search" type="search" maxLength={100} value={query} onChange={event => setQuery(event.target.value)} placeholder="Participating or neutral country" />
    <label htmlFor="inspect-country">Inspect a country</label><select id="inspect-country" value={selectedId ?? ''} onChange={event => select(event.target.value || null)}>
      <option value="">Choose a country to inspect</option>{options.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}
    </select>
    {selectedId && <button type="button" onClick={() => document.getElementById('country-info')?.focus()}>Read selected country information</button>}
    {options.length === 0 && <p role="status">No country names match.</p>}
    {selectedId && showCard && <CountryCard key={selectedId} id={selectedId} game={game} dismiss={dismiss} />}
  </div>;
}
/** Keep the native disclosure open after dismissal so return focus stays visible. */
export function CountryInspection(props: Parameters<typeof CountryInspector>[0]) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => { if (props.selectedId && ref.current) ref.current.open = true; }, [props.selectedId]);
  return <details className="geo-board-help" ref={ref}><summary>Find or inspect a country</summary><CountryInspector {...props} /></details>;
}
