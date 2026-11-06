import { useId } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { assertIntegerRange, numberForKey, numberFromInput, stepNumber } from './number.ts';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'quiet';
  loading?: boolean;
  loadingLabel?: string;
  disabledReason?: string;
}

export function Button({ variant = 'primary', loading = false, loadingLabel = 'Working…',
  disabled = false, disabledReason, children, className = '', type = 'button',
  'aria-describedby': describedBy, ...props }: ButtonProps) {
  const reasonId = useId();
  const reason = disabled && !loading ? disabledReason : undefined;
  return <span className="geo-button-wrap">
    <button {...props} type={type} className={`geo-button geo-button--${variant} ${className}`}
      disabled={disabled || loading} aria-busy={loading || undefined}
      aria-describedby={[describedBy, reason ? reasonId : undefined].filter(Boolean).join(' ') || undefined}>
      {loading ? loadingLabel : children}
    </button>
    {reason && <span className="geo-help" id={reasonId}>{reason}</span>}
  </span>;
}

export function Panel({ title, children, className = '', headingLevel = 2 }: {
  title: string; children: ReactNode; className?: string; headingLevel?: 2 | 3 | 4;
}) {
  const id = useId();
  const Heading = `h${headingLevel}` as 'h2' | 'h3' | 'h4';
  return <section className={`geo-panel ${className}`} aria-labelledby={id}>
    <Heading className="geo-panel__title" id={id}>{title}</Heading>
    {children}
  </section>;
}

export function StatusIndicator({ tone = 'neutral', children }: {
  tone?: 'neutral' | 'success' | 'warning' | 'danger'; children: ReactNode;
}) {
  return <span className={`geo-status geo-status--${tone}`} role="status">
    <span className="geo-status__dot" aria-hidden="true" />{children}
  </span>;
}

export interface SegmentOption<T extends string> { value: T; label: string; disabled?: boolean }

/** Native radios provide Tab/arrow/Space selection, including disabled-option skipping. */
export function SegmentedControl<T extends string>({ label, options, value, onChange, disabled = false }: {
  label: string; options: readonly SegmentOption<T>[]; value: T;
  onChange: (value: T) => void; disabled?: boolean;
}) {
  const name = useId();
  return <fieldset className="geo-segments" disabled={disabled}>
    <legend className="geo-label">{label}</legend>
    <div className="geo-segments__track">
      {options.map((option) => <label className="geo-segments__option" key={option.value}>
        <input type="radio" name={name} value={option.value} checked={value === option.value}
          disabled={disabled || option.disabled} onChange={() => onChange(option.value)} />
        <span>{option.label}</span>
      </label>)}
    </div>
  </fieldset>;
}

export function NumericStepper({ label, value, min, max, onChange, disabled = false }: {
  label: string; value: number; min: number; max: number; onChange: (value: number) => void; disabled?: boolean;
}) {
  assertIntegerRange(value, min, max);
  const id = useId(), helpId = useId();
  function change(next: number | undefined): void {
    if (!disabled && next !== undefined && next !== value) onChange(next);
  }
  return <div className="geo-stepper">
    <label className="geo-field-label" htmlFor={id}>{label}</label>
    <div className="geo-stepper__controls">
      <button type="button" aria-label={`Decrease ${label}`} disabled={disabled || value <= min}
        onClick={() => change(stepNumber(value, min, max, -1))}>−</button>
      <input id={id} type="number" inputMode="numeric" min={min} max={max} step={1} value={value}
        disabled={disabled} aria-describedby={helpId}
        onChange={(event) => change(numberFromInput(event.currentTarget.value, min, max))}
        onKeyDown={(event) => {
          const next = numberForKey(event.key, value, min, max);
          if (next !== undefined) { event.preventDefault(); change(next); }
        }} />
      <button type="button" aria-label={`Increase ${label}`} disabled={disabled || value >= max}
        onClick={() => change(stepNumber(value, min, max, 1))}>+</button>
    </div>
    <p className="geo-help" id={helpId}>Allowed: {min} to {max}. Arrow keys change by one; Home/End use the limits.</p>
  </div>;
}

export type Faction = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;
export type TokenState = 'default' | 'from' | 'target' | 'playing';

export function SoldierToken({ country, owner, soldiers, kind, faction, state = 'default', onSelect, disabled = false }: {
  country: string; owner: string; soldiers: number; kind: 'human' | 'npc'; faction: Faction;
  state?: TokenState; onSelect?: () => void; disabled?: boolean;
}) {
  assertIntegerRange(soldiers, 0, Number.MAX_SAFE_INTEGER);
  const stateLabel = { default: '', from: 'Attack from', target: 'Target', playing: 'Playing' }[state];
  const label = `${country}, held by ${owner}, ${soldiers} ${soldiers === 1 ? 'soldier' : 'soldiers'}${stateLabel ? `, ${stateLabel}` : ''}`;
  const content = <>
    <span className="geo-token__count" aria-hidden="true">{soldiers}</span>
    <span className="geo-token__description" aria-hidden="true">
      <span className="geo-token__country">{country}</span>
      <span className="geo-help">Held by {owner}</span>
      {stateLabel && <span className="geo-token__state">{stateLabel}</span>}
    </span>
  </>;
  const className = `geo-token geo-token--${kind} geo-token--${state}`;
  return onSelect ? <button type="button" className={className} data-faction={faction}
    aria-label={label} disabled={disabled} onClick={onSelect}>{content}</button>
    : <span className={className} data-faction={faction} role="img" aria-label={label}>{content}</span>;
}

export function TurnIndicator({ name, state }: {
  name: string; state: 'active' | 'completed' | 'upcoming' | 'eliminated';
}) {
  const labels = { active: 'Playing', completed: 'Turn taken', upcoming: 'Upcoming', eliminated: 'Eliminated' };
  const symbols = { active: '●', completed: '✓', upcoming: '○', eliminated: '×' };
  return <div className={`geo-turn geo-turn--${state}`} aria-current={state === 'active' ? 'step' : undefined}>
    <span aria-hidden="true">{symbols[state]}</span>
    {state === 'eliminated' ? <s>{name}</s> : <span>{name}</span>}
    <span className="geo-turn__state">{labels[state]}</span>
  </div>;
}

export function CountryProgress({ held, label = 'Countries held' }: { held: number; label?: string }) {
  assertIntegerRange(held, 0, 10);
  return <div className="geo-progress">
    <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={10} aria-valuenow={held}
      aria-valuetext={`${held} of 10 countries`} className="geo-progress__track">
      {Array.from({ length: 10 }, (_, index) => <span key={index} aria-hidden="true"
        className={`geo-progress__segment${index < held ? ' geo-progress__segment--held' : ''}`} />)}
    </div>
    <p>{held} of 10 countries</p>
  </div>;
}
