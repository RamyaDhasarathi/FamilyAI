// One-time code (design.md §13.4): six digit boxes with auto-advance,
// Backspace to the previous box, paste support, a 30-second resend timer and
// a link to change the number. Any six digits work while mocked; verifying
// logs in and plays the Loading screen.
import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { pageMeta, webCopy } from '../../mocks/webData';
import { useFamilyOS } from '../../store/useFamilyOS';
import { usePageMeta } from '../../hooks/usePageMeta';
import { PillButton } from '../../components/Pills';
import { AuthFrame } from './authBits';

const N = 6;

export default function OtpScreen() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const to = params.get('to') || 'your phone';
  const isNew = params.get('new') === '1';
  const o = webCopy.otp;
  const logIn = useFamilyOS((s) => s.logIn);
  const toast = useFamilyOS((s) => s.toast);
  const [digits, setDigits] = useState<string[]>(Array(N).fill(''));
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState(30);
  const [busy, setBusy] = useState(false);
  const boxes = useRef<(HTMLInputElement | null)[]>([]);
  usePageMeta(pageMeta.otp, true);

  useEffect(() => {
    if (left <= 0) return;
    const t = window.setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => window.clearTimeout(t);
  }, [left]);
  useEffect(() => {
    boxes.current[0]?.focus();
  }, []);

  const put = (i: number, v: string) => {
    const d = v.replace(/\D/g, '');
    if (!d) return;
    const next = [...digits];
    let k = i;
    for (const ch of d.slice(0, N - i)) next[k++] = ch;
    setDigits(next);
    setError(null);
    boxes.current[Math.min(N - 1, k)]?.focus();
  };
  const onKey = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      e.preventDefault();
      const next = [...digits];
      if (next[i]) next[i] = '';
      else if (i > 0) {
        next[i - 1] = '';
        boxes.current[i - 1]?.focus();
      }
      setDigits(next);
    } else if (e.key === 'ArrowLeft' && i > 0) boxes.current[i - 1]?.focus();
    else if (e.key === 'ArrowRight' && i < N - 1) boxes.current[i + 1]?.focus();
  };
  const onPaste = (e: ClipboardEvent) => {
    e.preventDefault();
    put(0, e.clipboardData.getData('text'));
  };
  const verify = async () => {
    if (digits.some((d) => !d)) {
      setError(o.invalid);
      boxes.current[digits.findIndex((d) => !d)]?.focus();
      return;
    }
    setBusy(true);
    await logIn(to, digits.join(''));
    try {
      window.sessionStorage.removeItem('familyos.session');
    } catch {
      /* ignore */
    }
    navigate(isNew ? '/loading?welcome=1' : '/loading', { replace: true });
  };

  return (
    <AuthFrame title={o.title} subtitle={o.subtitle(to)}>
      <form
        className="auth__form"
        onSubmit={(e) => {
          e.preventDefault();
          void verify();
        }}
        noValidate
      >
        <fieldset className="otp" onPaste={onPaste} style={{ border: 0, padding: 0 }}>
          <legend className="sr-only">{o.title}</legend>
          {digits.map((d, i) => (
            <input
              key={i}
              ref={(el) => {
                boxes.current[i] = el;
              }}
              className="otp__box"
              value={d}
              inputMode="numeric"
              autoComplete={i === 0 ? 'one-time-code' : 'off'}
              maxLength={N}
              aria-label={`Digit ${i + 1} of ${N}`}
              aria-invalid={!!error}
              onChange={(e) => put(i, e.target.value)}
              onKeyDown={(e) => onKey(i, e)}
              onFocus={(e) => e.target.select()}
            />
          ))}
        </fieldset>
        {error ? (
          <p className="field__error t-center" role="alert">
            {error}
          </p>
        ) : null}
        <PillButton type="submit" label={busy ? '…' : o.verify} aria-label={o.verify} variant="violet" block className="gap-top" disabled={busy} />
        <div className="auth__row" style={{ marginTop: 16, justifyContent: 'center', gap: 20 }}>
          {left > 0 ? (
            <span className="t-small" aria-live="polite">
              {o.resendIn(left)}
            </span>
          ) : (
            <button
              type="button"
              className="auth__link"
              onClick={() => {
                setLeft(30);
                toast(o.resent);
              }}
            >
              {o.resend}
            </button>
          )}
          <button type="button" className="auth__link" onClick={() => navigate(-1)}>
            {o.change}
          </button>
        </div>
        <p className="auth__note">{o.note}</p>
      </form>
    </AuthFrame>
  );
}
