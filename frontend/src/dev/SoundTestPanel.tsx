import { useEffect, useState } from 'react';
import { pageSound } from '../sound/SoundSettings.tsx';
import { soundAssets } from '../sound/assets.ts';
import type { SoundEvent } from '../sound/assets.ts';
import './sound-test.css';
/** Imported only by the separate offline preview entry, never the real App. */
export function SoundTestPanel() {
  const [status, setStatus] = useState(pageSound.inspect());
  useEffect(() => {
    const update = () => setStatus(pageSound.inspect());
    const unsubscribe = pageSound.subscribe(update), timer = setInterval(update, 150);
    return () => { unsubscribe(); clearInterval(timer); };
  }, []);
  return <details className="geo-sound-test"><summary>Offline sound test panel</summary>
    <p>Individual clip audition only. These buttons never submit gameplay or create receipts.</p>
    <a href="#sound-settings">Sound on/off and effects volume</a>
    <p role="status" className="geo-sound-test__status">{status.event ?? 'No event'} · {status.phase}
      {status.message && ` · ${status.message}`}</p>
    <output aria-label="Playback progress" aria-live="off">{status.currentTime.toFixed(2)} s · volume {Math.round(status.volume * 100)}%</output>
    <ul>{(Object.keys(soundAssets) as SoundEvent[]).map(event => <li key={event} data-sound-event={event}>
      <div><strong>{event}</strong><span>{soundAssets[event]}</span></div>
      <button type="button" onClick={() => {
        if (pageSound.inspect().enabled) pageSound.activate();
        pageSound.play(event, { important: true });
      }}>Test {event}</button>
    </li>)}</ul>
    <button type="button" onClick={() => pageSound.stop()}>Stop test sound</button>
  </details>;
}
if (!import.meta.env.DEV) throw Error('Sound test panel is offline development tooling only.');
