import { useState } from 'react';
import { AtlasMap } from '../map/AtlasMap.tsx';
import type { AtlasCountry } from '../map/types.ts';
import { Button, Panel, SegmentedControl } from '../ui/components.tsx';
import map from '../map/mapData.generated.json';
import '../map/atlas.css';

const scenarios = {
  world: ['brazil', 'canada', 'uk', 'norway', 'australia', 'angola', 'czechia', 'state-of-palestine', 'bahrain', 'seychelles'],
  identities: ['congo', 'democratic-republic-of-the-congo', 'north-korea', 'south-korea', 'swaziland', 'russia', 'cabo-verde', 'micronesia', 'saint-kitts-and-nevis', 'saint-vincent-and-the-grenadines'],
  microstates: ['andorra', 'holy-see', 'liechtenstein', 'monaco', 'san-marino', 'singapore', 'kiribati', 'luxembourg', 'malta', 'switzerland'],
  islands: ['kiribati', 'seychelles', 'singapore', 'fiji', 'samoa', 'tonga', 'palau', 'nauru', 'tuvalu', 'micronesia'],
};
export function AtlasPreview() {
  const [scenario, setScenario] = useState<keyof typeof scenarios>('world');
  const [selected, setSelected] = useState<string | null>(null), [conquest, setConquest] = useState(false);
  const ids = scenarios[scenario];
  const players = ids.map((id, i) => ({ id: `fixture-${i}`, starting_country_id: id, kind: i === 0 ? 'human' as const : 'npc' as const }));
  const countries: AtlasCountry[] = ids.map((id, i) => ({ id, name: map.countries.find(c => c.id === id)!.name,
    soldiers: i === 9 ? 1234567 : 10 + i * 7, owner_id: conquest && i === 1 ? 'fixture-0' : `fixture-${i}` }));
  return <div className="geo-atlas-preview"><Panel title="World atlas · development fixtures">
    <p>Ten synthetic participants and counts. Selection and the conquest switch change only this local example.</p>
    <div className="geo-atlas-preview__options">
      <SegmentedControl label="Atlas fixtures" value={scenario} onChange={(next) => { setScenario(next); setSelected(null); setConquest(false); }}
        options={[{ value: 'world', label: 'World' }, { value: 'identities', label: 'Aliases' },
          { value: 'microstates', label: 'Missing shapes' }, { value: 'islands', label: 'Islands' }]} />
      <Button variant="secondary" onClick={() => setConquest(!conquest)}>{conquest ? 'Reset fixture ownership' : 'Show fixture conquest'}</Button>
    </div>
    <p role="status">Selected fixture country: {selected ? countries.find(c => c.id === selected)!.name : 'None'}.</p>
    <AtlasMap countries={countries} players={players} turnOrder={players.map(p => p.id)} onSelect={setSelected}
      selectedId={selected} fromId={conquest ? null : ids[0]} targetId={conquest ? null : ids[1]} playingId={ids[3]}
      battle={conquest ? null : { source_id: ids[0], target_id: ids[1], preview: true }} />
  </Panel></div>;
}
