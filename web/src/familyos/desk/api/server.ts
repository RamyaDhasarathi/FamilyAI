// The desk store on the FamilyOS backend (VITE_FAMILYOS_API=on). Each action still changes the screen at once (the
// store's own code); this layer then sends the same decision to the server and, when it has answered, reads the
// household again so the screen shows the server's record, not the guess. A refusal (a guardian-only step, a stale
// record) is said in a toast and the screen goes back to what the server holds. Endpoints: famos-notes/WEB_MAPPING.md §3.
//
// What the server cannot do here is said, not faked:
//  • Erase everything and Withdraw consent are refused while background jobs are off (FAMILYOS_JOBS_ENABLED=false):
//    the server would lock the household, or withdraw the consent and never erase.
//  • Editing an errand, asking for a new one, "Not right?" on a notice and the conflict "Fix for me" have no endpoint.
//  • A pasted notice is stored, but nothing reads it while jobs are off.
import { useFamilyOS } from '../../store/useFamilyOS';
import { request, SignedOut } from '../../services/api';
import type { DeskState } from '../store';
import type { ToggleId } from '../types';
import { COUNTRIES, emptyDeskData, loadDeskData, RULE_KEY, type ServerIds } from './load';

type Store = { getState(): DeskState; setState(p: Partial<DeskState>): void };

let ids: ServerIds | null = null;
let store: Store | null = null;
let loading: Promise<void> | null = null;
let reloadTimer: ReturnType<typeof setTimeout> | null = null;
/** The server to-do made when a task or payment proposal was accepted, so Undo can take it away. */
const todoOfProposal: Record<string, string> = {};

const toast = (text: string) => useFamilyOS.getState().toast(text, { duration: 5000 });
const said = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

/** Read the whole household from the server into the desk store. */
export function loadDesk(): Promise<void> {
  if (!store) return Promise.resolve();
  if (loading) return loading;
  loading = loadDeskData()
    .then(({ data, actor, ids: fresh }) => {
      ids = fresh;
      store!.setState({ ...data, actor });
    })
    .catch((e) => {
      // No session is Log in's business (App.tsx); anything else is said.
      if (!(e instanceof SignedOut)) toast(said(e, 'Could not read the household.'));
    })
    .finally(() => {
      loading = null;
    });
  return loading;
}

function reloadSoon() {
  if (reloadTimer) clearTimeout(reloadTimer);
  reloadTimer = setTimeout(() => void loadDesk(), 300);
}

/** Send one write; reload either way so the screen ends up on the server's record. */
async function send(what: () => Promise<unknown>, failed: string): Promise<boolean> {
  try {
    await what();
    reloadSoon();
    return true;
  } catch (e) {
    toast(said(e, failed));
    reloadSoon();
    return false;
  }
}

const post = (path: string, body?: unknown) => request('POST', path, body ?? {});
const dayAndTime = (when: string | undefined) => {
  if (!when) return {};
  if (/^\d{4}-\d{2}-\d{2}$/.test(when)) return { due_date: when };
  const tz = store!.getState().settings.timezone;
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(when));
  const v = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  return { due_date: `${v('year')}-${v('month')}-${v('day')}`, due_time: `${v('hour')}:${v('minute')}` };
};

/** The notice's text and what was read from it, fetched when it is opened (one call each, not one per notice up front). */
export async function loadNoticeDetail(id: string): Promise<void> {
  if (!store) return;
  const s = store.getState();
  const n = s.notices.find((x) => x.id === id);
  if (!n || n.body) return;
  const [text, extraction] = await Promise.all([
    fetch(`/v1/artifacts/${id}/text`, { credentials: 'same-origin' }).then((r) => (r.ok ? r.text() : '')).catch(() => ''),
    request<{ extraction: { claims?: { id: string; quote?: string | null; amount?: number | null }[] } | null }>('GET', `/artifacts/${id}/extraction`).catch(() => null),
  ]);
  const claims = Object.fromEntries((extraction?.extraction?.claims ?? []).map((c) => [c.id, c]));
  const st = store.getState();
  store.setState({
    notices: st.notices.map((x) => (x.id === id ? { ...x, body: text || x.summary || '(This notice has no text to show; open the original.)' } : x)),
    proposals: st.proposals.map((p) => {
      const c = p.noticeId === id && ids ? claims[ids.claimOf[p.id]] : undefined;
      return c ? { ...p, quote: c.quote ?? p.quote, amount: c.amount ?? p.amount } : p;
    }),
  });
}

/** A phone token from the server: shown once, as the server says. */
export async function createPhoneToken(device: string): Promise<{ token: string; shareUrl?: string } | null> {
  try {
    const r = await request<{ token: string; share_url?: string }>('POST', '/devices', { label: device });
    reloadSoon();
    return { token: r.token, shareUrl: r.share_url };
  } catch (e) {
    toast(said(e, 'Could not make a phone token.'));
    return null;
  }
}

/** Who handles a notice (desk/ext/phase3.ts assignNotice). */
export function serverAssign(noticeId: string, memberId: string | null) {
  void send(() => post(`/artifacts/${noticeId}/assign`, { member_id: memberId }), 'Could not change who handles it.');
}

/** A school's portal is kept on the school (desk/ext/phase3.ts addPortal). */
export function serverPortal(school: string, url: string) {
  const id = ids?.schoolOf[school];
  if (!id) {
    toast('Add the school on the server first; this portal is only on this screen.');
    return;
  }
  void send(() => request('PUT', `/household/schools/${id}`, { portal_url: url }), 'Could not save the portal.');
}

/** Wrap the store's actions so each also reaches the server. Called once, with the store, when the API is on. */
export function bindServer(desk: Store) {
  store = desk;
  desk.setState({ ...emptyDeskData(), actor: '' });
  const local = { ...desk.getState() };

  // Read at once, beside Home's own start-up rather than after it (a visit with no session just gets a 401, which
  // loadDesk keeps quiet); again on signing in; empty again on signing out.
  let signedIn = false;
  void loadDesk();
  useFamilyOS.subscribe(({ loggedIn }) => {
    if (loggedIn && !signedIn && !desk.getState().actor) void loadDesk();     // not again when the first read already worked
    if (!loggedIn && signedIn) desk.setState({ ...emptyDeskData(), actor: '' });
    signedIn = loggedIn;
  });

  const proposal = (id: string) => desk.getState().proposals.find((p) => p.id === id);

  desk.setState({
    acceptProposal(id) {
      const before = proposal(id);
      if (!local.acceptProposal(id)) return false;
      const amendment = before && ids ? ids.amendmentOf[ids.claimOf[id]] : undefined;
      void send(async () => {
        if (before?.state === 'changed' && amendment) await post(`/amendments/${amendment}/decision`, { status: 'confirmed' });
        else await post(`/obligations/${id}/decision`, { status: 'accepted' });
        // The server makes no to-do on accept; the desk's "to the to-dos" is kept by making one.
        if (before && before.kind !== 'calendar' && before.kind !== 'reminder') {
          const t = await request<{ id: string }>('POST', '/todos', { title: before.title, ...dayAndTime(before.due), note: 'From a notice FamilyOS read' });
          todoOfProposal[id] = t.id;
        }
      }, 'Could not accept it on the server.');
      return true;
    },

    dismissProposal(id) {
      const before = proposal(id);
      if (!local.dismissProposal(id)) return false;
      const amendment = before && ids ? ids.amendmentOf[ids.claimOf[id]] : undefined;
      void send(
        () => (before?.state === 'changed' && amendment ? post(`/amendments/${amendment}/decision`, { status: 'rejected' }) : post(`/obligations/${id}/decision`, { status: 'dismissed' })),
        'Could not dismiss it on the server.',
      );
      return true;
    },

    undoProposal(id) {
      if (!local.undoProposal(id)) return false;
      void send(async () => {
        // The server's undo is the Activity Ledger's: the latest decision on this record that can still be undone.
        const acts = await request<{ id: number; target?: { id?: string } | null; undo?: unknown }[]>('GET', '/activity?limit=50');
        const act = acts.find((a) => a.target?.id === id && a.undo);
        if (!act) throw new Error('The server has no undo for this decision any more.');
        await post(`/activity/${act.id}/undo`);
        const todo = todoOfProposal[id];
        if (todo) {
          await request('DELETE', `/todos/${todo}`).catch(() => undefined);
          delete todoOfProposal[id];
        }
      }, 'Could not undo it on the server.');
      return true;
    },

    toggleTodo(id) {
      const t = desk.getState().todos.find((x) => x.id === id);
      local.toggleTodo(id);
      if (t) void send(() => request('PATCH', `/todos/${id}`, { done: !t.done }), 'Could not change the to-do on the server.');
    },

    addTodo(input) {
      const id = local.addTodo(input);
      const owner = desk.getState().members.find((m) => m.id === input.ownerId);
      void send(
        () => request('POST', '/todos', { title: input.title, ...dayAndTime(input.due), assigned_to: owner && owner.role !== 'child' ? owner.id : null }),
        'Could not add the to-do on the server.',
      );
      return id;
    },

    removeTodo(id) {
      if (!local.removeTodo(id)) return false;
      void send(() => request('DELETE', `/todos/${id}`), 'Could not remove the to-do on the server.');
      return true;
    },

    approveErrand(id) {
      if (!local.approveErrand(id)) return false;
      void send(() => post(`/errands/${id}/approve`, { params_sha256: ids?.paramsOf[id] ?? '', run_on: null }), 'Could not approve the errand.');
      return true;
    },

    editErrand() {
      toast('Changing an errand is not on the server yet: cancel it and ask again.');
      return false;
    },

    cancelErrand(id, reason) {
      if (!local.cancelErrand(id, reason)) return false;
      void send(() => post(`/errands/${id}/cancel`), 'Could not cancel the errand.');
      return true;
    },

    requestErrand(input) {
      toast('A new errand needs a signed-in site first; it is not on the server yet.');
      return local.requestErrand(input);
    },

    addNotice(input) {
      const id = local.addNotice(input);
      const form = new FormData();
      form.append('file', new Blob([`${input.title}\n\n${input.body}`], { type: 'text/plain' }), `${input.title.slice(0, 60) || 'notice'}.txt`);
      form.append('visibility', 'shared');
      void send(async () => {
        const r = await fetch('/v1/artifacts', { method: 'POST', credentials: 'same-origin', headers: { 'X-FamilyOS-CSRF': '1' }, body: form });
        if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `The server said ${r.status}`);
        toast('Kept. Nothing reads it on this server yet (background jobs are off).');
      }, 'Could not keep the notice.');
      return id;
    },

    flagNotice(noticeId, note) {
      local.flagNotice(noticeId, note);
      toast('Noted on this screen; the server has no place for it yet.');
    },

    openOriginal(noticeId) {
      local.openOriginal(noticeId);
      window.open(`/v1/artifacts/${noticeId}/original`, '_blank', 'noopener');
    },

    releaseQuarantine(id) {
      local.releaseQuarantine(id);
      void send(() => post(`/quarantine/${id}/accept`, { visibility: 'shared' }), 'Could not release it.');
    },

    deleteQuarantine(id) {
      local.deleteQuarantine(id);
      void send(() => post(`/quarantine/${id}/reject`), 'Could not delete it.');
    },

    setPlanStatus(planId, status) {
      local.setPlanStatus(planId, status);
      void send(() => request('PATCH', `/plans/${planId}`, { status }), 'Could not change the plan.');
    },

    markBooked(planId, bookingId, booked) {
      local.markBooked(planId, bookingId, booked);
      void send(() => post(`/plans/${planId}/choose`, { option_id: bookingId, booked }), 'Could not change the booking.');
    },

    revertRevision(id) {
      if (!local.revertRevision(id)) return false;
      void send(() => post(`/activity/${id}/undo`), 'Could not undo it on the server.');
      return true;
    },

    setSetting(key, value) {
      const before = desk.getState().settings;
      local.setSetting(key, value);
      const next = { ...before, [key]: value };
      if (key === 'name') void send(() => request('PATCH', '/household', { name: value }), 'Could not rename the household.');
      else if (key === 'familyAddress') void send(() => request('PUT', '/household/handle', { handle: String(value).split('@')[0] }), 'Could not change the address.');
      else {
        const typed = next.country.trim();
        const code = Object.entries(COUNTRIES).find(([, n]) => n.toLowerCase() === typed.toLowerCase())?.[0] ?? (/^[A-Za-z]{2}$/.test(typed) ? typed.toUpperCase() : null);
        if (!code) {
          toast('Use a country the server knows, or its two-letter code (IN, US, GB, AE …).');
          reloadSoon();
          return;
        }
        void send(() => request('PUT', '/household/locale', { country: code, timezone: next.timezone, currency: next.currency }), 'Could not change where we live.');
      }
    },

    setToggle(id: ToggleId, on) {
      local.setToggle(id, on);
      const key = RULE_KEY[id];
      if (key) void send(() => request('PUT', '/household/rules', { [key]: on }), 'Could not change the switch.');
      else toast('This switch is kept in this browser only; the server has no rule for it.');
    },

    connectMailbox() {
      // Google's own page asks which mailbox; the address typed here is not needed.
      void (async () => {
        try {
          const r = await request<{ url: string }>('POST', '/google/mailboxes/authorize', {});
          window.location.assign(r.url);
        } catch (e) {
          toast(said(e, 'Gmail is not set up on this server yet.'));
        }
      })();
    },

    disconnectMailbox(id) {
      local.disconnectMailbox(id);
      void send(() => post(`/google/mailboxes/${id}/disconnect`), 'Could not disconnect the mailbox.');
    },

    newPhoneToken(device) {
      // The page asks the server itself (createPhoneToken) so it can show the real token once.
      return local.newPhoneToken(device);
    },

    revokeToken(id) {
      local.revokeToken(id);
      void send(() => request('DELETE', `/devices/${id}`), 'Could not revoke the token.');
    },

    stopWatcher(id) {
      local.stopWatcher(id);
      if (id.startsWith('school:')) void send(() => request('PUT', `/household/schools/${id.slice(7)}`, { portal_url: null }), 'Could not stop watching the portal.');
      else void send(() => request('DELETE', `/watches/${id}`), 'Could not stop the watcher.');
    },

    withdrawConsent() {
      toast('Withdrawing consent erases the child’s records, and this server cannot run the erasure yet (background jobs are off). Nothing was changed.');
    },

    signOutEverywhere(memberId) {
      local.signOutEverywhere(memberId);
      void send(() => post(`/members/${memberId}/signout`), 'Could not sign them out.');
    },

    openSitting(input) {
      const id = local.openSitting(input);
      const host = input.site.replace(/^https?:\/\//, '').split('/')[0];
      void send(() => post('/harvests', { label: input.purpose, allow_hosts: [host], minutes: input.minutes }), 'Could not open the sitting.');
      return id;
    },

    eraseAll() {
      toast('Erasing the household cannot run on this server yet (background jobs are off): it would lock the household without erasing it. Nothing was changed.');
      return false;
    },
  });
}
