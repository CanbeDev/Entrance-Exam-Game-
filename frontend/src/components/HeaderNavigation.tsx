import { useRef, useState } from 'react';

/** One navigation instance; mobile disclosure changes presentation only. */
export function HeaderNavigation({ available, landing, onLoginNavigation }: { available: boolean; landing: boolean; onLoginNavigation?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  if (!available) return null;
  return <>
    <button ref={toggle} type="button" className="geo-menu-toggle" aria-expanded={expanded}
      aria-controls="main-navigation" onClick={() => setExpanded(value => !value)}
      onKeyDown={event => { if (event.key === 'Escape') setExpanded(false); }}>Menu</button>
    <nav id="main-navigation" className="geo-main-navigation" aria-label="Main navigation" data-expanded={expanded}
      onClick={() => setExpanded(false)} onKeyDown={event => {
        if (expanded && event.key === 'Escape') {
          event.preventDefault(); setExpanded(false);
          if (toggle.current?.getClientRects().length) toggle.current.focus();
        }
      }}>
      <a href="/">My Games / Home</a><a href="/new">New campaign</a><a href="/rules">Rules</a><a href="/watch">Watch</a>
      {landing && <a className="geo-header-login" href="#command-access" onClick={onLoginNavigation}><svg className="geo-header-login__icon" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d="M19 5h8v22h-8M4 16h16m-6-6 6 6-6 6" /></svg>Log in</a>}
    </nav>
  </>;
}
