// The FamilyOS backend (/v1) as the web app reaches it. The app is served by
// the backend itself (/app/), so the API is on the same origin; `npm run dev`
// proxies /v1 to it (vite.config.ts). The session is the backend's HttpOnly
// cookie (familyos/session_cookie.py): script never holds the token, and every
// call carries the CSRF header that marks it as FamilyOS's own page.
// VITE_FAMILYOS_API=on (web/.env.production) uses the backend; off, the mocks.

export const API_ENABLED = import.meta.env.VITE_FAMILYOS_API === 'on';

// Home's /brief can take 20–35 s on the shared Azure database (famos-notes/AUDIT.md, 29 Oct): a 30 s limit turned a slow
// answer into "signed out". 90 s until the backend is hosted next to the database.
const TIMEOUT_MS = 90_000;

/** The backend said there is no session, or it ended. */
export class SignedOut extends Error {}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`/v1${path}`, {
      method,
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'X-FamilyOS-CSRF': '1',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch {
    throw new ApiError(0, "Can't reach the FamilyOS server.");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 401) throw new SignedOut('Your session has ended. Sign in again.');
  if (!res.ok) {
    // The backend answers {"error": code, "detail": sentence}.
    const err = await res.json().catch(() => null);
    const detail = err?.detail;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `The server said ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
