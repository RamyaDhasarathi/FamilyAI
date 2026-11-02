// Back navigation that works for deep links: go back in history when there
// is somewhere to go back to, otherwise to a sensible parent page.
import type { useNavigate } from 'react-router';

export function goBack(navigate: ReturnType<typeof useNavigate>, fallback = '/') {
  if (window.history.state && window.history.state.idx > 0) navigate(-1);
  else navigate(fallback, { replace: true });
}
