// Ask, /ask?q=… (MASTER_AGENT.md §7 Phase 3 "Ask", §10 footer copy;
// FamilyOS.mp4 4:40–5:40, frames f_057–f_068). The conversation itself is
// AskChat (shared with the desktop Home once a message is sent). A question
// in ?q= (from the floating Ask bar, ⌘K or "Ask about this") is asked once on
// arrival. Clear empties the conversation. The existing Home Ask panel is
// unchanged on mobile.
import { useEffect } from 'react';
import { useLocation, useSearchParams } from 'react-router';
import { Sparkles } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { PillButton } from '../../components/Pills';
import { DeskPage } from '../shell/DeskPage';
import { useAsk } from './askStore';
import { AskChat } from './AskChat';
import { ASK_DESCRIPTION } from './askCopy';

export default function AskPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const empty = useAsk((s) => !s.msgs.length && s.pending === 0);
  const clear = useAsk((s) => s.clear);
  const q = params.get('q');

  // Ask the ?q= question once per navigation (Back to this entry, or a re-render, never re-asks).
  useEffect(() => {
    if (q?.trim()) useAsk.getState().askOnce(location.key, q);
  }, [q, location.key]);

  return (
    <DeskPage
      icon={Sparkles}
      color={colors.violet}
      title="Ask"
      className="ak-page"
      description={ASK_DESCRIPTION}
      actions={<PillButton label="Clear" aria-label="Clear the conversation" onClick={clear} disabled={empty} />}
    >
      <AskChat autoFocus={!q} />
    </DeskPage>
  );
}
