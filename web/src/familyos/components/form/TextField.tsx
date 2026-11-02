// Glass text field (mobile components/form/TextField.tsx): 1 px border that
// takes the section colour on focus, a floating label, an optional prefix
// (+1, $), as-you-type formatting, and a mask shown whenever the field isn't
// focused (XXXX XXXX 0193, ••••••••6789).
import { useId, useState, type CSSProperties, type Ref } from 'react';
import clsx from 'clsx';
import { T } from '../../theme/typography';

export const ERROR_RED = '#FF7A85';

export type Keyboard = 'default' | 'number-pad' | 'decimal-pad' | 'email-address' | 'phone-pad';

const inputMode = (k?: Keyboard) =>
  k === 'number-pad' ? 'numeric' : k === 'decimal-pad' ? 'decimal' : k === 'email-address' ? 'email' : k === 'phone-pad' ? 'tel' : 'text';

interface Props {
  label: string;
  value: string;
  onChange: (v: string) => void;
  accent: string;
  required?: boolean;
  error?: string | null;
  hint?: string;
  prefix?: string;
  keyboard?: Keyboard;
  format?: (v: string) => string;
  mask?: (v: string) => string;
  autoCapitalize?: 'none' | 'words' | 'characters' | 'sentences';
  autoFocus?: boolean;
  className?: string;
  onFocus?: () => void;
  compact?: boolean;
  inputRef?: Ref<HTMLInputElement>;
}

export function TextField({
  label, value, onChange, accent, required, error, hint, prefix, keyboard = 'default', format, mask,
  autoCapitalize = 'sentences', autoFocus, className, onFocus, compact, inputRef,
}: Props) {
  const id = useId();
  const [focused, setFocused] = useState(false);
  const up = focused || !!value;
  const shown = !focused && mask && value ? mask(value) : value;
  const msgId = `${id}-msg`;
  return (
    <div className={clsx('text-field', compact && 'text-field--compact', className)} style={{ '--accent': accent } as CSSProperties}>
      <div className={clsx('text-field__box', focused && 'is-focused', error && 'is-error', up && 'is-up')}>
        <label htmlFor={id} className={clsx(T.small, 'text-field__label')}>
          {label}
          {required ? ' *' : ''}
        </label>
        <div className="text-field__row">
          {prefix && up ? <span className={clsx(T.input, 'text-field__prefix')}>{prefix}</span> : null}
          <input
            id={id}
            ref={inputRef}
            className={clsx(T.input, 'text-field__input')}
            value={shown}
            onChange={(e) => onChange(format ? format(e.target.value) : e.target.value)}
            onFocus={() => {
              setFocused(true);
              onFocus?.();
            }}
            onBlur={() => setFocused(false)}
            inputMode={inputMode(keyboard)}
            type={keyboard === 'email-address' ? 'email' : 'text'}
            autoCapitalize={format ? 'none' : autoCapitalize}
            autoCorrect="off"
            autoComplete="off"
            spellCheck={false}
            autoFocus={autoFocus}
            aria-required={required}
            aria-invalid={!!error}
            aria-describedby={error || hint ? msgId : undefined}
            data-field-input
          />
        </div>
      </div>
      {error ? (
        <p id={msgId} className={clsx(T.small, 'field-error')} role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={msgId} className={clsx(T.small, 'field-hint', !focused && 'sr-only')}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
