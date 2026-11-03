import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { cardPosition } from '../country/facts.ts';
import { SoldierToken } from '../ui/components.tsx';
import type { Faction } from '../ui/components.tsx';
import rawData from './mapData.generated.json';
import type { AtlasProps, MapData } from './types.ts';
import { factionMap, formatMapCount, tokenLayout, validateAtlas } from './layout.ts';

const data: MapData = rawData;
const color = (faction: number) => `var(--geo-${faction === 0 ? 'forest' : `rival-${faction}`})`;

function ownerLabel(props: AtlasProps, id: string) {
  const player = props.players.find(p => p.id === id)!;
  const name = data.countries.find(c => c.id === player.starting_country_id)?.name ?? player.starting_country_id;
  return `${name} (${player.kind === 'human' ? 'Human' : 'NPC'})`;
}

function roster(props: AtlasProps, handlers: ReadonlyMap<string, () => void>, showHomeIdentity = false) {
  const factions = factionMap(props);
  return <div className="geo-atlas__roster">
    {props.countries.map(country => <div key={country.id} data-roster-country={country.id} data-selected={props.selectedId === country.id}>
      <SoldierToken country={country.name} owner={ownerLabel(props, country.owner_id)} soldiers={country.soldiers}
        kind={props.players.find(p => p.id === country.owner_id)!.kind} faction={factions.get(country.owner_id)! as Faction}
        state={country.id === props.targetId ? 'target' : country.id === props.fromId ? 'from' : country.id === props.playingId ? 'playing' : 'default'}
        onSelect={handlers.get(country.id)} />
      {showHomeIdentity && props.players.filter(p => p.starting_country_id === country.id).map(p =>
        <span key={p.id} className="geo-help">Home participant: {ownerLabel(props, p.id)}</span>)}
      {props.selectedId === country.id && <span className="geo-help">Selected</span>}
    </div>)}
  </div>;
}

/** Same roster and selection contract, optionally placed outside the map panel. */
export function AtlasRoster(props: AtlasProps) {
  validateAtlas(props, data);
  return roster(props, new Map(props.countries.map(c => [c.id, () => props.onSelect(c.id)])), true);
}

/** Pure content function also permits offline interaction/SSR tests without a DOM. */
type InformationProps = { information?: ReactNode; inspectedId?: string | null; onInspect?: (id: string) => void };
export function AtlasContent(props: AtlasProps & InformationProps) {
  validateAtlas(props, data);
  const layout = tokenLayout(props.countries, data, props.viewportWidth ?? 1000);
  const countries = new Map(props.countries.map(c => [c.id, c])), factions = factionMap(props);
  const groups = new Map(data.groups.map(g => [g.key, g]));
  const handlers = new Map(props.countries.map(c => [c.id, () => props.onSelect(c.id)]));
  const state = (id: string) => id === props.targetId ? 'target' : id === props.fromId ? 'from' : id === props.playingId ? 'playing' : 'default';
  const ownerName = (id: string) => {
    const player = props.players.find(p => p.id === id)!;
    const name = data.countries.find(c => c.id === player.starting_country_id)?.name ?? player.starting_country_id;
    return `${name} (${player.kind === 'human' ? 'Human' : 'NPC'})`;
  };
  const relation = props.battle;
  const battleText = relation ? `${relation.preview ? 'Preview' : 'Attack'}: ${countries.get(relation.source_id)!.name} → ${countries.get(relation.target_id)!.name}` : null;
  const point = (id: string) => data.countries.find(c => c.id === id)!.anchor;
  return <section className="geo-atlas" aria-label="Interactive world atlas">
    <p>Any rival country can be attacked regardless of distance. Select a country to inspect it.</p>
    <p className="geo-help">On narrow screens, scroll the map horizontally or use the full country list below.</p>
    {battleText && <p className="geo-atlas__relationship">{battleText}</p>}
    <div className="geo-atlas__scroll" role="region" aria-label="Scrollable world map" tabIndex={0}>
      <div className="geo-atlas__canvas" style={{ width: layout.width, height: layout.height }}>
        <svg viewBox="0 0 2000 857" className="geo-atlas__svg" aria-hidden="true" focusable="false">
          {data.paths.map((path, index) => {
            const group = groups.get(path.groupKey)!, country = group.canonicalId ? countries.get(group.canonicalId) : undefined;
            return <path key={index} d={path.d} data-map-group={group.key} data-country={country?.id} data-inspectable={group.canonicalId && props.onInspect ? group.canonicalId : undefined}
              data-captured={country ? props.capturedIds?.includes(country.id) || undefined : undefined}
              onAnimationEnd={country ? event => { if (event.animationName === 'geo-country-captured') props.onCaptureSettled?.(country.id); } : undefined}
              fill={country ? color(factions.get(country.owner_id)!) : 'var(--geo-land)'}
              fillOpacity={country ? factions.get(country.owner_id) === 0 ? 0.42 : 0.3 : 1}
              className={country ? 'geo-atlas__country' : undefined}
              onClick={country ? handlers.get(country.id) : group.canonicalId && props.onInspect ? () => props.onInspect!(group.canonicalId!) : undefined} />;
          })}
          {relation && <line className="geo-atlas__battle" x1={point(relation.source_id).x} y1={point(relation.source_id).y}
            x2={point(relation.target_id).x} y2={point(relation.target_id).y} />}
          {layout.placements.map(token => <g key={token.id}>
            {token.leader && <line className="geo-atlas__leader" data-leader-for={token.id}
              x1={token.anchor.x / layout.scale} y1={token.anchor.y / layout.scale}
              x2={token.pin.x / layout.scale} y2={token.pin.y / layout.scale} />}
            <circle className="geo-atlas__anchor" cx={token.anchor.x / layout.scale} cy={token.anchor.y / layout.scale} r={2 / layout.scale} />
          </g>)}
        </svg>
        {layout.placements.map(token => {
          const country = countries.get(token.id)!, faction = factions.get(country.owner_id)!;
          const currentState = state(country.id), entry = data.countries.find(c => c.id === country.id)!;
          const cue = { default: '', from: 'FROM', target: 'TARGET', playing: 'PLAYING' }[currentState];
          return <button key={country.id} type="button" className="geo-atlas__token" data-map-country={country.id}
            data-human={faction === 0} data-state={currentState} aria-pressed={props.selectedId === country.id}
            aria-label={`${country.name}, held by ${ownerName(country.owner_id)}, ${country.soldiers} soldiers${cue ? `, ${cue}` : ''}${entry.missingShape ? ', location marker: no source border' : ''}`}
            onClick={handlers.get(country.id)} style={{ left: token.x, top: token.y, width: token.width, height: token.height,
              '--geo-faction': color(faction) } as CSSProperties}>
            <span className="geo-atlas__number" data-compact={country.soldiers >= 1_000_000}>{formatMapCount(country.soldiers)}</span>
            <span className="geo-atlas__name">{country.name}</span>
            <span className="geo-atlas__cue">{cue || (props.selectedId === country.id ? 'SELECTED' : entry.missingShape ? 'LOCATION MARKER' : '')}</span>
          </button>;
        })}
      </div>
    </div>
    <p className="geo-help">Map geometry: Simplemaps (MIT). Small countries without source borders use verified location markers.</p>
    {layout.packed && <p className="geo-help">Country markers are arranged for readability; lines connect them to their locations.</p>}
    {props.showRoster !== false && <h3 className="geo-panel__title">Countries and soldiers</h3>}
    {props.selectedId && <p role="status">Selected: {countries.get(props.selectedId)!.name}, {countries.get(props.selectedId)!.soldiers} soldiers,
      {' '}held by {ownerName(countries.get(props.selectedId)!.owner_id)}.</p>}
    {props.showRoster !== false && roster(props, handlers)}
    {!props.countries.length && <p>No participating countries supplied.</p>}
  </section>;
}

export function AtlasMap(props: AtlasProps & InformationProps) {
  const ref = useRef<HTMLDivElement>(null), [width, setWidth] = useState(props.viewportWidth ?? 1000);
  useEffect(() => {
    if (props.viewportWidth !== undefined || !ref.current) return;
    const element = ref.current;
    const update = () => { if (element.clientWidth > 0) setWidth(element.clientWidth); };
    update();
    const observer = new ResizeObserver(update); observer.observe(element);
    return () => observer.disconnect();
  }, [props.viewportWidth]);
  const anchor = data.countries.find(c => c.id === props.inspectedId)?.anchor;
  const position = cardPosition((anchor?.x ?? 1000) / 2000 * width, width);
  return <div className="geo-atlas-host" ref={ref}><AtlasContent {...props} viewportWidth={props.viewportWidth ?? width} />
    {props.information && <div className="geo-country-anchor" style={{ '--geo-card-left': `${position.left}px` } as CSSProperties}>{props.information}</div>}
  </div>;
}
