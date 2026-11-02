// Where the backend sends a browser back to /app/ (familyos/identity.py, api/routes.py), read once at start-up and
// taken out of the address bar at once, as the founder's console did:
//   /app/#link=…                                a mailed sign-in link        → spend it for the session cookie
//   /app/?signin=new#found=…&email=…            a founding mail, or Google
//                                               with no household yet        → Sign up, with the ticket and address
//   /app/?signin=cancelled | ?signin=failed     Google came back without one → say so
//   /app/#/notices/<id>, #/today, #/chat, #/errands/<id>, #/home?mailbox=…
//                                               the founder's console addresses the backend still writes into
//                                               calendar events, chat replies and errand messages → the same page here
import { API_ENABLED } from './api';

export type Landing =
  | { kind: 'link'; link: string }
  | { kind: 'found'; founding: string; email: string }
  | { kind: 'said'; signin: 'cancelled' | 'failed' }
  | { kind: 'goto'; path: string };

/** The founder's hash routes → this app's pages. */
function pageFor(route: string): string | null {
  const [path] = route.split('?');
  const [, first, second] = path.split('/');
  if (first === 'notices') return second ? `/inbox/${second}` : '/inbox';
  if (first === 'errands') return second ? `/errands/${second}` : '/errands';
  if (first === 'today') return '/today';
  if (first === 'chat' || first === 'ask') return '/ask';
  if (first === 'home' && route.includes('mailbox=')) return '/settings/household';
  return first ? '/' : null;
}

function read(): Landing | null {
  if (!API_ENABLED || typeof window === 'undefined') return null;
  const { hash, search, pathname } = window.location;
  const h = new URLSearchParams(hash.replace(/^#/, ''));
  const q = new URLSearchParams(search);
  let found: Landing | null = null;
  const page = hash.startsWith('#/') ? pageFor(hash.slice(1)) : null;
  if (page) found = { kind: 'goto', path: page };
  else if (h.get('link')) found = { kind: 'link', link: h.get('link')! };
  else if (h.get('found')) found = { kind: 'found', founding: h.get('found')!, email: h.get('email') ?? '' };
  else if (q.get('signin') === 'cancelled' || q.get('signin') === 'failed') found = { kind: 'said', signin: q.get('signin') as 'cancelled' | 'failed' };
  if (found || q.has('signin')) window.history.replaceState(window.history.state, '', pathname);
  return found;
}

/** The landing this page load arrived with, if any (read once, when this module loads). */
export const landing: Landing | null = read();
