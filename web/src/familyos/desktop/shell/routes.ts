// Route rules for the desktop shell, kept free of icons and copy so App.tsx
// can import them without growing the main bundle.

/** Routes that already have their own Ask bar, so the floating one hides (§7 Phase 2.2). */
export function pageHasOwnAsk(path: string): boolean {
  if (path === '/' || path === '/ask' || path.startsWith('/ask/')) return true;
  return /^\/agents?\/(finance|education|household|grocery|calendar)\/?$/.test(path);
}

/** Auth and splash pages never get the desktop shell. */
const CHROMELESS = ['/login', '/signup', '/verify', '/loading'];
export const isChromeless = (path: string) => CHROMELESS.some((p) => path === p || path.startsWith(`${p}/`));

/** Where a question goes: the full Ask page, which reads `?q=` (§7 Phase 2.2). */
export const askPath = (q: string) => `/ask?q=${encodeURIComponent(q)}`;
