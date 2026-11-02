// "Ask FamilyOS" / "Ask {Agent}" chat (AGENT_WEB.md §8.6, video 1:45 and
// 2:55). Enter sends, Shift+Enter adds a line. Replies come from the mock
// service after a typing indicator; new messages slide up, and the list
// follows the latest unless the user has scrolled up. "Ask about this" and
// the mic arrive with a message already queued, sent on open.
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ArrowUp } from 'lucide-react';
import type { AgentId } from '../../theme/tokens';
import { colors, withAlpha } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { agentNames, copy } from '../../mocks/data';
import { useFamilyOS } from '../../store/useFamilyOS';
import { ChatBubble, SuggestionChips, TypingDots } from '../../components/Chat';
import { ClosePill } from '../../components/Pills';
import { Pressable } from '../../components/Pressable';
import { Sheet } from '../../components/Sheet';

const NO_CHIPS: string[] = [];

export function ChatPanel({ open, onClose, thread }: { open: boolean; onClose: () => void; thread: string }) {
  const messages = useFamilyOS((s) => s.threads[thread]);
  const typing = useFamilyOS((s) => !!s.typing[thread]);
  const chips = useFamilyOS((s) => s.suggestions[thread]) ?? NO_CHIPS;
  const send = useFamilyOS((s) => s.sendChat);
  const takePending = useFamilyOS((s) => s.takePending);
  const ensureThread = useFamilyOS((s) => s.ensureThread);
  const [text, setText] = useState('');
  const input = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLUListElement>(null);
  const stick = useRef(true);
  const isAgent = thread !== 'home';
  const accent = isAgent ? colors.agents[thread as AgentId] : '#7F8CFF';
  const title = isAgent ? copy.chatAgentTitle(agentNames[thread as AgentId]) : copy.chatTitle;

  useEffect(() => {
    if (!open) return;
    void ensureThread(thread);
    stick.current = true;
    const pending = takePending();
    if (pending) void send(thread, pending);
  }, [open, thread, send, takePending, ensureThread]);

  // Follow the newest message unless the user scrolled up to read.
  useLayoutEffect(() => {
    const el = scroller.current?.parentElement;
    if (el && stick.current) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [messages?.length, typing]);
  useEffect(() => {
    const el = scroller.current?.parentElement;
    if (!el) return;
    const onScroll = () => {
      stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  });

  const submit = (t: string) => {
    if (!t.trim()) return;
    setText('');
    stick.current = true;
    void send(thread, t);
    input.current?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit(text);
    }
  };

  const header = (
    <div className="chat-head">
      <div>
        <h2 id="chat-title" className={T.sheetTitle}>
          {title}
        </h2>
        <span className="title-underline" style={{ background: `linear-gradient(90deg, ${accent}, ${withAlpha(accent, 0)})` }} aria-hidden />
      </div>
      <ClosePill onClick={onClose} />
    </div>
  );
  const footer = (
    <div className="chat-foot">
      <SuggestionChips chips={chips} onPick={submit} />
      <form
        className="chat-input"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          submit(text);
        }}
      >
        <label htmlFor={`chat-in-${thread}`} className="sr-only">
          {copy.typeMessage}
        </label>
        <textarea
          id={`chat-in-${thread}`}
          ref={input}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder={copy.typeMessage}
          className="chat-input__field t-input"
          style={{ caretColor: accent }}
          autoComplete="off"
          enterKeyHint="send"
        />
        <Pressable type="submit" className="chat-input__send" aria-label="Send" lift={false}>
          <ArrowUp size={18} strokeWidth={2.2} aria-hidden />
        </Pressable>
      </form>
    </div>
  );
  return (
    <Sheet open={open} onClose={onClose} labelledBy="chat-title" header={header} footer={footer} close="none" fixedFrac={0.8} drawerWidth={480} initialFocus={input}>
      <ul ref={scroller} className="chat-list" aria-live="polite" aria-label="Conversation">
        {messages?.map((m) => <ChatBubble key={m.id} msg={m} />)}
        {typing ? <TypingDots /> : null}
      </ul>
    </Sheet>
  );
}
