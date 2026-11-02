// The Loading screen plays once per browser session (AGENT_WEB.md §8.8).
const SESSION_KEY = 'familyos.session';

export function sessionStarted() {
  try {
    return window.sessionStorage.getItem(SESSION_KEY) === '1';
  } catch {
    return true;
  }
}

export function markSessionStarted() {
  try {
    window.sessionStorage.setItem(SESSION_KEY, '1');
  } catch {
    /* private window: the session flag can't be kept */
  }
}
