import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Button, CountryProgress, NumericStepper, Panel, SegmentedControl, SoldierToken,
  StatusIndicator, TurnIndicator } from '../ui/components.tsx';
import '../ui/components.css';
import { AtlasPreview } from './AtlasPreview.tsx';

function ComponentPreview() {
  const [selection, setSelection] = useState('overview');
  const [amount, setAmount] = useState(2);
  const [held, setHeld] = useState(2);
  const [message, setMessage] = useState('No preview button selected.');
  return <main className="geo-ui geo-preview">
    <div className="geo-preview__intro">
      <p className="geo-label">Stage 2 · development fixtures only</p>
      <h1 className="geo-display">Design System V1</h1>
      <p>Isolated component examples. Every count and country below is a development fixture.
        These controls change only this preview; no account, game or commentary service is connected.</p>
      <p className="geo-help">Fonts: {document.documentElement.dataset.webFonts === 'true'
        ? 'Newsreader and DM Sans requested with swap; system fallbacks remain available.'
        : 'offline system fallbacks; named Newsreader and DM Sans stacks are configured.'}</p>
    </div>
    <div className="geo-preview__grid">
      <Panel title="Buttons"><div className="geo-preview__stack">
        <Button onClick={() => setMessage('Primary preview button selected.')}>Primary action</Button>
        <Button variant="secondary" onClick={() => setMessage('Secondary preview button selected.')}>Secondary action</Button>
        <Button variant="quiet" onClick={() => setMessage('Quiet preview button selected.')}>Quiet action</Button>
        <Button disabled disabledReason="Complete the fixture selection to continue.">Selection required</Button>
        <Button loading loadingLabel="Preparing preview…">Prepare preview</Button>
        <p role="status">{message}</p>
      </div></Panel>
      <Panel title="Typography"><div className="geo-preview__stack">
        <p className="geo-heading-lg">Geopolitics</p>
        <p className="geo-heading-md">Your next move</p>
        <p className="geo-title">Soldiers and countries</p>
        <p>Body text uses the 15px interface scale.</p>
        <p className="geo-help">Small body text stays at 13px.</p>
        <p className="geo-label">Uppercase label</p>
        <p className="geo-narrative">Narrative typography sample, not generated battle commentary.</p>
      </div></Panel>
      <Panel title="Status indicators" className="geo-preview__status-panel"><div className="geo-preview__statuses">
        <StatusIndicator tone="success">Your turn</StatusIndicator>
        <StatusIndicator>Round 4</StatusIndicator>
        <StatusIndicator><span className="geo-status__label">From</span></StatusIndicator>
        <StatusIndicator tone="warning"><span className="geo-status__label">Target</span></StatusIndicator>
        <StatusIndicator tone="success">Playing</StatusIndicator>
        <StatusIndicator tone="danger">Eliminated</StatusIndicator>
      </div></Panel>
      <Panel title="Segmented selection"><div className="geo-preview__stack">
        <SegmentedControl label="Preview section" value={selection} onChange={setSelection}
          options={[{ value: 'overview', label: 'Overview' }, { value: 'details', label: 'Details' },
            { value: 'unavailable', label: 'Unavailable', disabled: true }]} />
        <p role="status">Selected: {selection}</p>
        <SegmentedControl label="Disabled selection" value="first" onChange={() => {}} disabled
          options={[{ value: 'first', label: 'First' }, { value: 'second', label: 'Second' }]} />
      </div></Panel>
      <Panel title="Numeric stepper"><div className="geo-preview__stack">
        <NumericStepper label="Fixture amount" value={amount} min={0} max={9} onChange={setAmount} />
        <NumericStepper label="Unavailable amount" value={0} min={0} max={0} onChange={() => {}} disabled />
      </div></Panel>
      <Panel title="Soldier tokens"><div className="geo-preview__stack">
        <SoldierToken country="Brazil" owner="You" soldiers={9} kind="human" faction={0}
          onSelect={() => setMessage('Brazil fixture selected.')} />
        <SoldierToken country="United Kingdom" owner="United Kingdom NPC" soldiers={6} kind="npc" faction={2}
          onSelect={() => setMessage('United Kingdom fixture selected.')} />
        <SoldierToken country="Canada" owner="You" soldiers={10} kind="human" faction={0} state="from" />
        <SoldierToken country="Indonesia" owner="Japan NPC" soldiers={12} kind="npc" faction={4} state="target" />
        <SoldierToken country="Norway" owner="Norway NPC" soldiers={23} kind="npc" faction={1} state="playing" />
        <SoldierToken country="St. Vincent & Grenadines" owner="A long fixture owner name" soldiers={1234567} kind="npc" faction={9} />
        <SoldierToken country="France" owner="France NPC" soldiers={1} kind="npc" faction={3} disabled onSelect={() => {}} />
      </div></Panel>
      <Panel title="Turn indicators"><div className="geo-preview__stack">
        <TurnIndicator name="Japan NPC" state="active" />
        <TurnIndicator name="Brazil (you)" state="completed" />
        <TurnIndicator name="Germany NPC" state="upcoming" />
        <TurnIndicator name="Canada NPC" state="eliminated" />
      </div></Panel>
      <Panel title="Ten-country progress"><div className="geo-preview__stack">
        <NumericStepper label="Fixture countries held" value={held} min={0} max={10} onChange={setHeld} />
        <CountryProgress held={held} />
        <CountryProgress held={0} label="Empty fixture progress" />
        <CountryProgress held={10} label="Complete fixture progress" />
      </div></Panel>
      <Panel title="Paper panel and card">
        <p>This panel uses the approved paper surface, warm divider and 16px radius.</p>
        <Panel title="Nested inset example" headingLevel={3}>
          <p className="geo-help">A reusable named section. No invented shadow or decorative effect.</p>
        </Panel>
      </Panel>
    </div>
    <AtlasPreview />
  </main>;
}

if (!import.meta.env.DEV) throw new Error('The component preview is development-only.');
createRoot(document.getElementById('root')!).render(<ComponentPreview />);
