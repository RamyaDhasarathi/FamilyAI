// The FamilyOS backend (/v1) as the app reaches it: base URL, the member's
// bearer token, and one request helper. Set EXPO_PUBLIC_FAMILYOS_API (see
// mobile/.env.example) to use the backend; unset, the app runs on mocks.
import * as SecureStore from 'expo-secure-store';
import * as CollectNative from '../../../modules/familyos-collect';

/** e.g. http://localhost:8000 with `adb reverse tcp:8000 tcp:8000`, or the Mac's LAN address. */
export const API_BASE = (process.env.EXPO_PUBLIC_FAMILYOS_API ?? '').replace(/\/+$/, '');
export const API_ENABLED = API_BASE.length > 0;

const TOKEN_KEY = 'familyos.token';
const SECURE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
// Home's /brief can take 20–35 s on the shared Azure database (famos-notes/AUDIT.md, 29 Oct): a 30 s limit turned a slow
// answer into "signed out". 90 s until the backend is hosted next to the database.
const TIMEOUT_MS = 90_000;

let token: string | null = null;

export async function loadToken(): Promise<string | null> {
  if (token) return token;
  token = await SecureStore.getItemAsync(TOKEN_KEY, SECURE_OPTS).catch(() => null);
  return token;
}

export async function saveToken(value: string): Promise<void> {
  token = value;
  await SecureStore.setItemAsync(TOKEN_KEY, value, SECURE_OPTS);
  // The live SMS service sends new SMS by itself with this session (kept by Android, encrypted in its Keystore).
  if (API_BASE) CollectNative.setSession(API_BASE, value);
}

export async function clearToken(): Promise<void> {
  token = null;
  await SecureStore.deleteItemAsync(TOKEN_KEY, SECURE_OPTS).catch(() => undefined);
  CollectNative.clearSession(); // signed out: live SMS stops and forgets the session
}

/** The backend said the token is missing, expired or revoked. */
export class SignedOut extends Error {}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = await loadToken();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/v1${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch {
    throw new ApiError(0, `Can't reach the FamilyOS server at ${API_BASE}`);
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 401) {
    await clearToken();
    throw new SignedOut('Your session has ended. Sign in again.');
  }
  if (!res.ok) {
    // The backend answers {"error": code, "detail": sentence}.
    const err = await res.json().catch(() => null);
    const detail = err?.detail;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `The server said ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
