// Title, description and robots per page (AGENT_WEB.md §11.5): public pages
// (log in, sign up) are indexable; everything behind sign-in is noindex.
import { useEffect } from 'react';

function meta(name: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.name = name;
    document.head.appendChild(el);
  }
  el.content = content;
}

export function usePageMeta(m: { title: string; description: string }, isPublic = false) {
  useEffect(() => {
    document.title = m.title;
    meta('description', m.description);
    meta('robots', isPublic ? 'index, follow' : 'noindex, nofollow');
  }, [m.title, m.description, isPublic]);
}
