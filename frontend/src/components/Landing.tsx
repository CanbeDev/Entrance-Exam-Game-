import { memo } from 'react';
import type { ReactNode } from 'react';
import map from '../map/mapData.generated.json';
import './landing.css';

type SymbolName = 'compass' | 'flag' | 'shield' | 'dice' | 'dice-two' | 'signal' | 'target' | 'binoculars' | 'laurel';
function CampaignSymbol({ name }: { name: SymbolName }) {
  return <svg className="geo-landing-symbol" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {name === 'compass' && <><circle cx="16" cy="16" r="11" /><path d="m20 12-2 6-6 2 2-6Z M16 2v4m0 20v4M2 16h4m20 0h4" /></>}
    {name === 'flag' && <><path d="M8 28V5m0 1c7-5 10 5 17 0v13c-7 5-10-5-17 0M4 28h9" /></>}
    {name === 'shield' && <><path d="M16 3 5 8v8c0 7 11 13 11 13s11-6 11-13V8Z M16 10v12m-6-6h12" /></>}
    {name === 'dice' && <><rect x="5" y="5" width="22" height="22" rx="4" /><circle cx="11" cy="11" r="1" /><circle cx="21" cy="11" r="1" /><circle cx="16" cy="16" r="1" /><circle cx="11" cy="21" r="1" /><circle cx="21" cy="21" r="1" /></>}
    {name === 'dice-two' && <><rect x="5" y="5" width="22" height="22" rx="4" /><circle cx="11" cy="11" r="1" /><circle cx="21" cy="21" r="1" /></>}
    {name === 'signal' && <><circle cx="16" cy="16" r="2" /><path d="M10 10a8.5 8.5 0 0 0 0 12m12-12a8.5 8.5 0 0 1 0 12M6 6a14 14 0 0 0 0 20M26 6a14 14 0 0 1 0 20M16 19v10" /></>}
    {name === 'target' && <><circle cx="16" cy="16" r="11" /><circle cx="16" cy="16" r="6" /><path d="M16 2v6m0 16v6M2 16h6m16 0h6" /></>}
    {name === 'binoculars' && <><path d="M5 19 9 6h5v14m4 0V6h5l4 13M14 11h4" /><circle cx="9" cy="22" r="6" /><circle cx="23" cy="22" r="6" /></>}
    {name === 'laurel' && <><path d="M12 28C4 24 1 14 8 5m12 23c8-4 11-14 4-23M5 12l5 1-1-6M4 19l6-1-4-5m2 12 5-4-6-2m20-7-5 1 1-6m5 12-6-1 4-5m-2 12-5-4 6-2M12 28l4-2 4 2" /></>}
  </svg>;
}

/** Static geography only: these colours and compass are decorative, never game state. */
const CampaignAtlas = memo(function CampaignAtlas() {
  return <figure className="geo-landing__map">
    <div className="geo-landing__atlas-frame">
      <div className="geo-landing__atlas-heading"><span>World atlas</span><span>Strategy &amp; chance</span></div>
      <svg className="geo-landing__geography" viewBox="0 0 2000 857" role="img" aria-label="World map illustration; no campaign ownership is shown">
        <g className="geo-landing__grid" aria-hidden="true">{[250, 500, 750, 1000, 1250, 1500, 1750].map(x => <path key={`x${x}`} d={`M${x} 0v857`} />)}
          {[214, 428, 642].map(y => <path key={`y${y}`} d={`M0 ${y}h2000`} />)}</g>
        <g className="geo-landing__countries">{map.paths.map((path, index) => <path key={index} d={path.d} />)}</g>
      </svg>
      <div className="geo-landing__atlas-key" aria-hidden="true"><span>Across borders. Beyond distance.</span><span className="geo-landing__atlas-seal"><CampaignSymbol name="dice-two" /><CampaignSymbol name="compass" /></span></div>
    </div>
    <figcaption>Illustrative atlas · Decorative colours, not a live campaign. Geography: Simplemaps.</figcaption>
  </figure>;
});

const orders: readonly { title: string; copy: string; icon: SymbolName }[] = [
  { title: 'Choose your nation', copy: 'Choose from 195 countries. Begin with one of the ten countries in your campaign.', icon: 'flag' },
  { title: 'Deploy your forces', copy: 'From round two, place your available reinforcements across the countries you hold.', icon: 'shield' },
  { title: 'Wage strategic battles', copy: 'Choose your attacks. Read every recorded dice pair and respond to the outcome.', icon: 'dice' },
  { title: 'Claim global victory', copy: 'Outmanoeuvre nine rival commanders. Hold all ten participating countries to win.', icon: 'laurel' },
];

/** Public presentation only. The original auth and spectator components are passed through. */
export function Landing({ account, watch, onBeginCampaign }: { account: ReactNode; watch: ReactNode; onBeginCampaign?: () => void }) {
  return <div className="geo-landing geo-landing--public">
    <section className="geo-landing__hero" aria-labelledby="landing-title">
      <div className="geo-landing__story">
        <div className="geo-landing__brief"><span className="geo-landing__eyebrow"><CampaignSymbol name="compass" /> A world of strategy &amp; chance</span></div>
        <h2 id="landing-title"><span>Command a nation.</span><em>Conquer the world.</em></h2>
        <p className="geo-landing__tagline">Every order shapes the world.<br />Every roll changes its fate.</p>
        <p className="geo-landing__lead">Choose your country. Command its soldiers. Meet nine autonomous rival commanders in a turn-based contest of strategy and dice.</p>
        <div className="geo-landing__cta"><a className="geo-landing__primary" href="#command-access" onClick={onBeginCampaign}>Begin your campaign <span aria-hidden="true">↗</span></a><a className="geo-landing__secondary" href="#observation">Watch a campaign</a></div>
        <div className="geo-landing__campaign-note"><p className="geo-landing__metadata">One human. Nine rivals. Ten countries.</p>
          <div className="geo-landing__watermark" aria-hidden="true"><CampaignSymbol name="dice" /><CampaignSymbol name="dice-two" /></div></div>
      </div>
      <CampaignAtlas />
    </section>
    <section className="geo-landing__access" id="command-access" tabIndex={-1} aria-labelledby="command-access-title">
      <div className="geo-landing__introduction"><span className="geo-landing__eyebrow"><CampaignSymbol name="flag" /> Your command</span>
        <h2 id="command-access-title">Your campaign <br /><em>awaits.</em></h2>
        <p>Log in to issue orders, read the Chronicle and continue your pursuit of global control.</p>
        <p className="geo-landing__note">Your next move starts with a country.</p>
        <a className="geo-landing__text-link" href="/rules">Read the rules <span aria-hidden="true">↗</span></a>
      </div>
      <div className="geo-landing__account"><div className="geo-landing__account-heading"><span className="geo-landing__eyebrow">Command access</span><CampaignSymbol name="shield" /></div>{account}</div>
    </section>
    <section className="geo-landing__observation" id="observation" tabIndex={-1} aria-labelledby="observation-title">
      <div className="geo-landing__introduction"><span className="geo-landing__eyebrow"><CampaignSymbol name="binoculars" /> Intelligence observation</span>
        <h2 id="observation-title">Observe <em>the battlefield.</em></h2>
        <p>Follow changing territories, rival decisions and saved battle commentary in a shared campaign.</p>
        <p className="geo-landing__note">Read only. Watch the campaign unfold; only its authenticated owner can issue orders.</p>
      </div>
      <div className="geo-landing__watch">{watch}</div>
    </section>
    <section className="geo-landing__orders" aria-labelledby="four-orders-title">
      <header className="geo-landing__section-heading"><span className="geo-landing__eyebrow"><CampaignSymbol name="target" /> The art of conquest</span><h2 id="four-orders-title">Four orders.<br /><em>One campaign.</em></h2>
        <figure className="geo-landing__epigraph"><blockquote cite="https://www.gutenberg.org/files/17405/17405-h/17405-h.htm"><p>“Know the enemy and know yourself.”</p></blockquote>
          <figcaption>— Sun Tzu, <cite>The Art of War</cite>, Chapter 3<span>Concise English rendering</span></figcaption></figure></header>
      <ol>{orders.map((order, index) => <li key={order.title}><div className="geo-landing__order-number"><span>0{index + 1}</span><CampaignSymbol name={order.icon} /></div><h3>{order.title}</h3><p>{order.copy}</p></li>)}</ol>
    </section>
  </div>;
}
