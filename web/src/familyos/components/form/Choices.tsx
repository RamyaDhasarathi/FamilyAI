// Choice controls (mobile components/form/Choices.tsx): wrapped glass chips
// (selected = white with dark text), a toggle row with a switch, and a small
// label + error frame.
import { useId, type CSSProperties, type ReactNode } from 'react';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { Pressable } from '../Pressable';

export function FieldFrame({ label, required, error, children, id }: { label: string; required?: boolean; error?: string | null; children: ReactNode; id?: string }) {
  const gen = useId();
  const labelId = id ?? gen;
  return (
    <div className="field-frame" role="group" aria-labelledby={labelId}>
      <p id={labelId} className={clsx(T.small, 'field-frame__label')}>
        {label}
        {required ? ' *' : ''}
      </p>
      {children}
      {error ? (
        <p className={clsx(T.small, 'field-error')} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface ChipsProps {
  options: string[];
  value: string | string[] | undefined;
  onChange: (v: string | string[]) => void;
  multi?: boolean;
  accent: string;
  label: string;
}

export function ChoiceChips({ options, value, onChange, multi, accent, label }: ChipsProps) {
  const selected = (o: string) => (multi ? Array.isArray(value) && value.includes(o) : value === o);
  return (
    <div className="choice-chips" role={multi ? 'group' : 'radiogroup'} aria-label={label} style={{ '--accent': accent } as CSSProperties}>
      {options.map((o) => {
        const on = selected(o);
        return (
          <Pressable
            key={o}
            className={clsx('choice-chip t-chip', on && 'is-on', on && multi && 'is-multi')}
            onClick={() => {
              if (!multi) onChange(o);
              else {
                const cur = Array.isArray(value) ? value : [];
                onChange(on ? cur.filter((x) => x !== o) : [...cur, o]);
              }
            }}
            role={multi ? 'checkbox' : 'radio'}
            aria-checked={on}
            pressScale={0.95}
            lift={false}
            data-field-input
          >
            {o}
          </Pressable>
        );
      })}
    </div>
  );
}

export function ToggleRow({ label, value, onChange, accent, required, error }: { label: string; value: boolean; onChange: (v: boolean) => void; accent: string; required?: boolean; error?: string | null }) {
  const id = useId();
  return (
    <div>
      <div className="toggle-row">
        <label htmlFor={id} className={clsx(T.small, 'toggle-row__text')}>
          {label}
          {required ? ' *' : ''}
        </label>
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={value}
          className="switch"
          style={{ '--switch-on': accent } as CSSProperties}
          onClick={() => onChange(!value)}
          data-field-input
        />
      </div>
      {error ? (
        <p className={clsx(T.small, 'field-error')} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
