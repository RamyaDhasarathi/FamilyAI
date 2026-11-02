// Signing up or in is done once the backend has made the session: reading Home's data belongs to the Loading screen.
// (30 Oct 2026: after "Create account" the family was made and the cookie set, but Home's /brief took longer than the
// request limit on the shared database, so sign-up reported a failure and the page stayed; a second click spent no ticket.)
import { beforeEach, describe, expect, it, vi } from 'vitest';

let calls: string[];

beforeEach(() => {
  calls = [];
  vi.resetModules();
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^\/v1/, '');
    calls.push(`${init?.method ?? 'GET'} ${path}`);
    if (path === '/sign-up/dev') return new Response(JSON.stringify({ founding: 'fnd_x' }), { status: 200 });
    if (path === '/households') return new Response(JSON.stringify({ credentials: { member: { id: 'm1' } } }), { status: 201 });
    if (path === '/sign-in/dev') return new Response(JSON.stringify({ token: null }), { status: 200 });
    // Home's data is slow or failing right now.
    return new Response(JSON.stringify({ detail: 'busy' }), { status: 500 });
  }) as typeof fetch;
});

describe('signing up and in on our backend', () => {
  it('sign-up succeeds once the household is made, whatever Home\'s data does', async () => {
    const { apiService } = await import('./apiService');
    const r = await apiService.signUp({ name: 'Asha Rao', email: 'asha@example.in', family: 'The Raos' });
    expect(r.ok).toBe(true);
    expect(calls).toEqual(['POST /sign-up/dev', 'POST /households']);
  });

  it('sign-up with a ticket Google gave uses it and asks for no other', async () => {
    const { apiService } = await import('./apiService');
    const r = await apiService.signUp({ name: 'Asha Rao', email: 'asha@example.in', family: 'The Raos', founding: 'fnd_google' });
    expect(r.ok).toBe(true);
    expect(calls).toEqual(['POST /households']);
  });

  it('sign-in succeeds once the backend has made the session', async () => {
    const { apiService } = await import('./apiService');
    const r = await apiService.logIn('asha@example.in', '');
    expect(r.ok).toBe(true);
    expect(calls).toEqual(['POST /sign-in/dev']);
  });
});
