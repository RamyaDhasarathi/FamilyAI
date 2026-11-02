// Shared pieces of the account pages (design.md §13.3–13.4): frosted inputs
// with a 1 px border, a checkbox, and the page frame (one centred glass card
// over the onboarding glow; no split-screen layout on desktop).
import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { Check, Eye, EyeOff } from 'lucide-react';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { MiniGem } from '../../components/MiniGem';
import { OnboardingBackdrop } from '../../components/OnboardingBackdrop';
import { ToastHost } from '../../components/Toast';

export function AuthFrame({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="auth">
      <OnboardingBackdrop />
      <main id="main" className="auth__card glass page-in">
        <div className="auth__gem">
          <MiniGem size={120} still />
        </div>
        <h1 className={clsx(T.greeting, 't-center')}>{title}</h1>
        <p className={clsx(T.small, 't-center', 'auth__sub')}>{subtitle}</p>
        {children}
      </main>
      <ToastHost bottom={24} />
    </div>
  );
}

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> {
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  hint?: string;
  prefix?: string;
  /** Password field with a show/hide button. */
  secret?: boolean;
  after?: ReactNode;
}

export function AuthField({ label, value, onChange, error, hint, prefix, secret, after, type = 'text', ...rest }: FieldProps) {
  const id = useId();
  const [shown, setShown] = useState(false);
  return (
    <div className={clsx('field', error && 'field--error')}>
      <label htmlFor={id} className="field__label">
        {label}
      </label>
      <div className="field__box">
        {prefix ? <span className="field__prefix">{prefix}</span> : null}
        <input
          id={id}
          className="field__input"
          type={secret ? (shown ? 'text' : 'password') : type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error || hint ? `${id}-msg` : undefined}
          autoCapitalize="none"
          spellCheck={false}
          {...rest}
        />
        {secret ? (
          <button type="button" className="field__icon-btn" onClick={() => setShown((s) => !s)} aria-label={shown ? 'Hide password' : 'Show password'} aria-pressed={shown}>
            {shown ? <EyeOff size={18} aria-hidden /> : <Eye size={18} aria-hidden />}
          </button>
        ) : null}
      </div>
      {after}
      {error ? (
        <p id={`${id}-msg`} className="field__error" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-msg`} className="field__hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function Checkbox({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <button type="button" role="checkbox" aria-checked={checked} className="check" onClick={() => onChange(!checked)}>
      <span className="check__box" aria-hidden>
        {checked ? <Check size={12} color="#fff" strokeWidth={3} /> : null}
      </span>
      <span className={T.small} style={{ color: 'var(--ink)' }}>
        {label}
      </span>
    </button>
  );
}
