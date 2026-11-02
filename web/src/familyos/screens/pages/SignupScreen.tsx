// Sign up (design.md §13.4): full name, email, mobile, date of birth,
// password with a four-step strength meter, an optional pod name and the
// terms. Each field gets a plain message under it, and messages clear as soon
// as the field is fixed. The pod owner must be 18 or older. Creating the
// account goes to the one-time-code screen. The existing web console's
// "create a household" is this flow; nothing is sent while mocked.
// On the backend (VITE_FAMILYOS_API=on) it founds the household: name and
// email make the guardian, the pod name the household (else "<first>'s
// family"), mobile and birthday are saved on the guardian after. The backend
// signs in by email link, so there is no password to set: the field is not
// shown. A founding ticket a mailed link or Google gave arrives in the
// route's state (services/landing.ts) with the address it was given for.
import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { pageMeta, webCopy } from '../../mocks/webData';
import { checks, formatters, phonePrefix } from '../../family/region';
import { ageOf } from '../../family/model';
import { usePageMeta } from '../../hooks/usePageMeta';
import { API_ENABLED } from '../../services/api';
import { useFamilyOS } from '../../store/useFamilyOS';
import { PillButton } from '../../components/Pills';
import { AuthField, AuthFrame, Checkbox } from './authBits';

const STRENGTH_COLORS = ['#FF5A5F', '#FF9E33', '#FFD56E', '#6BF294'];

/** 0–4: length ≥ 8, mixed case, a digit, a symbol. */
function passwordStrength(p: string) {
  if (p.length < 8) return 0;
  return Math.min(4, 1 + (/[a-z]/.test(p) && /[A-Z]/.test(p) ? 1 : 0) + (/\d/.test(p) ? 1 : 0) + (/[^A-Za-z0-9]/.test(p) ? 1 : 0));
}

type Form = { name: string; email: string; mobile: string; dob: string; password: string; pod: string; terms: boolean };
type Errors = Partial<Record<keyof Form, string>>;

function validate(f: Form): Errors {
  const e: Errors = {};
  if (!/^[\p{L} .'-]{2,60}$/u.test(f.name.trim())) e.name = 'Use 2–60 letters, spaces or . \' -';
  const em = checks.email(f.email);
  if (em) e.email = em;
  const mo = checks.mobile(f.mobile);
  if (mo) e.mobile = mo;
  if (!f.dob) e.dob = 'Required';
  else if (new Date(f.dob) > new Date()) e.dob = 'Can’t be in the future';
  else if (ageOf(f.dob) < 18) e.dob = webCopy.signup.ownerAge;
  if (!API_ENABLED && f.password.length < 8) e.password = 'Use at least 8 characters';
  if (!f.terms) e.terms = 'Please agree to continue';
  return e;
}

export default function SignupScreen() {
  const navigate = useNavigate();
  const s = webCopy.signup;
  const handed = (useLocation().state ?? null) as { founding?: string; email?: string } | null;
  const signUp = useFamilyOS((st) => st.signUp);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState<Form>({ name: '', email: handed?.email ?? '', mobile: '', dob: '', password: '', pod: '', terms: false });
  const [errors, setErrors] = useState<Errors>({});
  usePageMeta(pageMeta.signup, true);
  const set = (patch: Partial<Form>) => {
    const next = { ...f, ...patch };
    setF(next);
    if (Object.keys(errors).length) setErrors(validate(next));
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const errs = validate(f);
    setErrors(errs);
    const first = Object.keys(errs)[0];
    if (first) {
      document.querySelector<HTMLElement>(`[data-field="${first}"] input, [data-field="${first}"] button`)?.focus();
      return;
    }
    if (!API_ENABLED) {
      navigate(`/verify?to=${encodeURIComponent(`${phonePrefix} ${f.mobile}`)}&new=1`);
      return;
    }
    setBusy(true);
    const given = f.name.trim().split(/\s+/)[0];
    const ok = await signUp({ name: f.name, email: f.email, family: f.pod.trim() || `${given}'s family`, phone: f.mobile, dateOfBirth: f.dob, founding: handed?.founding });
    setBusy(false);
    if (ok) {
      try {
        window.sessionStorage.removeItem('familyos.session');
      } catch {
        /* ignore */
      }
      navigate('/loading?welcome=1', { replace: true });
    }
  };
  const strength = passwordStrength(f.password);
  return (
    <AuthFrame title={s.title} subtitle={s.subtitle}>
      <form className="auth__form" onSubmit={submit} noValidate>
        <div data-field="name">
          <AuthField label={s.fullName} value={f.name} onChange={(v) => set({ name: v })} error={errors.name} autoComplete="name" autoCapitalize="words" />
        </div>
        <div data-field="email">
          <AuthField label={s.email} value={f.email} onChange={(v) => set({ email: v })} error={errors.email} type="email" autoComplete="email" inputMode="email" />
        </div>
        <div data-field="mobile">
          <AuthField label={s.mobile} value={f.mobile} onChange={(v) => set({ mobile: formatters.phone(v) })} error={errors.mobile} prefix={phonePrefix} type="tel" autoComplete="tel-national" inputMode="tel" />
        </div>
        <div data-field="dob">
          <AuthField label={s.dob} value={f.dob} onChange={(v) => set({ dob: v })} error={errors.dob} type="date" autoComplete="bday" max={new Date().toISOString().slice(0, 10)} />
        </div>
        {API_ENABLED ? null : (
        <div data-field="password">
          <AuthField
            label={s.password}
            value={f.password}
            onChange={(v) => set({ password: v })}
            error={errors.password}
            secret
            autoComplete="new-password"
            hint={f.password ? s.strength[strength] : undefined}
            after={
              <div className="strength" aria-hidden>
                {[0, 1, 2, 3].map((i) => (
                  <i key={i} style={{ background: i < strength ? STRENGTH_COLORS[strength - 1] : undefined }} />
                ))}
              </div>
            }
          />
        </div>
        )}
        <AuthField label={s.podName} value={f.pod} onChange={(v) => set({ pod: v })} hint={s.podHint} autoCapitalize="words" />
        <div data-field="terms" className="field">
          <Checkbox checked={f.terms} onChange={(v) => set({ terms: v })} label={s.terms} />
          {errors.terms ? (
            <p className="field__error" role="alert">
              {errors.terms}
            </p>
          ) : null}
        </div>
        <PillButton type="submit" label={busy ? '…' : s.submit} aria-label={s.submit} variant="violet" block disabled={busy} />
        <p className="t-small auth__switch">
          {s.haveAccount}{' '}
          <Link to="/login" className="auth__link">
            {s.login}
          </Link>
        </p>
        <p className="auth__note">{API_ENABLED ? s.noteServer : s.note}</p>
      </form>
    </AuthFrame>
  );
}
