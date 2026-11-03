import type { ReactNode } from 'react';
import map from '../map/mapData.generated.json';

export function Landing({ children }: { children: ReactNode }) {
  return <div className="geo-landing"><section className="geo-landing__story" aria-labelledby="landing-title">
    <span className="geo-label">A game of countries and chance</span>
    <h2 id="landing-title">Pick a country.<br /><em>Roll for the world.</em></h2>
    <p className="geo-screen-lead">Nine NPC rivals. Ten countries. Choose your battles and hold them all to win.</p>
    <figure className="geo-landing__map"><svg viewBox="0 0 2000 857" role="img" aria-label="World map illustration; no campaign ownership is shown">
      {map.paths.map((path, index) => <path key={index} d={path.d} />)}</svg>
      <figcaption>Choose from {map.countries.length} countries. Starting soldiers follow each country's population.</figcaption>
    </figure>
    <a href="/rules">Learn how to play</a>
  </section><div className="geo-landing__entry">{children}</div></div>;
}
