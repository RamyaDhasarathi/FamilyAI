// Log in (design.md §13.3, mobile LoginScreen): email or mobile and password
// (show / hide), "Keep me logged in", "Forgot password?" (toast), violet Log
// in, Continue with Google (the existing web console's sign-in), a one-time
// code, and a link to create an account. Any credentials work while the
// backend is mocked; logging in plays the Loading screen, then Home. On the
// backend (VITE_FAMILYOS_API=on) the email signs in (development sign-in) and
// Google is offered only where the server has it set up.
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { copy, profile } from '../../mocks/data';
import { pageMeta, webCopy } from '../../mocks/webData';
import { useFamilyOS } from '../../store/useFamilyOS';
import { usePageMeta } from '../../hooks/usePageMeta';
import { API_ENABLED } from '../../services/api';
import { googleSignInUrl } from '../../services/apiService';
import { PillButton } from '../../components/Pills';
import { AuthField, AuthFrame, Checkbox } from './authBits';

export default function LoginScreen() {
  const navigate = useNavigate();
  const logIn = useFamilyOS((s) => s.logIn);
  const toast = useFamilyOS((s) => s.toast);
  const [email, setEmail] = useState(API_ENABLED ? '' : profile.email);
  const [password, setPassword] = useState('');
  const [keep, setKeep] = useState(true);
  const [busy, setBusy] = useState(false);
  usePageMeta(pageMeta.login, true);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (busy) return;
    setBusy(true);
    const ok = await logIn(email, password);
    setBusy(false);
    if (ok) {
      try {
        window.sessionStorage.removeItem('familyos.session');
      } catch {
        /* ignore */
      }
      navigate('/loading', { replace: true });
    }
  };

  const google = async () => {
    const url = await googleSignInUrl();
    if (url) window.location.assign(url);
    else toast(webCopy.googleOff, { duration: 5000 });
  };

  return (
    <AuthFrame title={copy.login.title} subtitle={copy.login.subtitle}>
      <form className="auth__form" onSubmit={submit} noValidate>
        <AuthField label={copy.login.email} value={email} onChange={setEmail} autoComplete="username" inputMode="email" />
        <AuthField label={copy.login.password} value={password} onChange={setPassword} secret autoComplete="current-password" />
        <div className="auth__row">
          <Checkbox checked={keep} onChange={setKeep} label={copy.login.keep} />
          <button type="button" className="auth__link" onClick={() => toast(copy.login.forgotToast)}>
            {copy.login.forgot}
          </button>
        </div>
        <PillButton type="submit" label={busy ? '…' : copy.login.submit} aria-label={copy.login.submit} variant="violet" block disabled={busy} />
        <PillButton label={copy.login.google} onClick={() => void (API_ENABLED ? google() : submit())} block className="auth__alt" />
        <Link to={`/verify?to=${encodeURIComponent(email)}`} className="auth__link auth__center-link">
          {copy.login.otp}
        </Link>
        <p className="t-small auth__switch">
          {webCopy.noAccount}{' '}
          <Link to="/signup" className="auth__link">
            {webCopy.createAccount}
          </Link>
        </p>
        <p className="auth__note">{API_ENABLED ? copy.login.noteServer : copy.login.note}</p>
      </form>
    </AuthFrame>
  );
}
