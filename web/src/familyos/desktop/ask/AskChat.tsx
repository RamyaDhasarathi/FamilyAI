// The Ask conversation (MASTER_AGENT.md §7 Phase 3 "Ask"; FamilyOS.mp4
// 4:40–5:40): empty state with suggestion chips, our chat bubbles, answers
// with citation chips that open the source notice, action cards, and the
// composer pinned to the bottom with the honest footer. Rendered by the Ask
// page and by the desktop Home once its first message is sent (HomeChat).
import { useId, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ArrowUp } from 'lucide-react';
import { T } from '../../theme/typography';
import { copy } from '../../mocks/data';
import { ChatBubble, SuggestionChips, TypingDots } from '../../components/Chat';
import { MiniGem } from '../../components/MiniGem';
import { Pressable } from '../../components/Pressable';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import { useDesk } from '../../desk/store';
import { useDeskFormat } from '../../desk/hooks';
import { zonedParts } from '../../desk/format';
import NoticeDrawer from '../inbox/NoticeDrawer';
import { SUGGESTIONS } from './answer';
import { useAsk } from './askStore';
import { AskAnswer } from './AskAnswer';
import './ask.css';

const FOOTER = 'The assistant sees only what you can see. It never sends, pays or changes anything on its own.';

export function AskChat({ autoFocus = true }: { autoFocus?: boolean }) {
  const reduced = useReducedMotion();
  const f = useDeskFormat();
  const msgs = useAsk((s) => s.msgs);
  const typing = useAsk((s) => s.pending > 0);
  const ask = useAsk((s) => s.ask);
  const me = useDesk((s) => s.members.find((m) => m.id === s.actor)?.name ?? '');
  const [text, setText] = useState('');
  const [source, setSource] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const fieldId = useId();

  useLayoutEffect(() => {
    if (msgs.length || typing) end.current?.scrollIntoView({ block: 'end', behavior: reduced ? 'auto' : 'smooth' });
  }, [msgs.length, typing, reduced]);

  const submit = (t: string) => {
    if (!t.trim()) return;
    ask(t);
    setText('');
    input.current?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit(text);
    }
  };
  const hour = zonedParts(new Date(), f.tz).h;
  const greeting = hour < 12 ? copy.greeting.morning : hour < 17 ? copy.greeting.afternoon : copy.greeting.evening;
  const empty = !msgs.length && !typing;

  return (
    <>
      <div className="ak-convo">
        {empty ? (
          <div className="ak-empty">
            <MiniGem size={64} />
            <h2 className={T.headline}>
              {greeting}
              {me ? `, ${me}` : ''}.
            </h2>
            <p className={T.small}>The family’s notices, the dates spotted, the to-dos and what you pay for are all in front of me. Ask away, or try one below.</p>
          </div>
        ) : (
          <ul className="chat-list ak-list" aria-live="polite" aria-label="Conversation">
            {msgs.map((m) =>
              m.role === 'user' || !m.answer ? (
                <ChatBubble key={m.id} msg={{ id: m.id, role: m.role, text: m.text }} />
              ) : (
                <AskAnswer key={m.id} msgId={m.id} answer={m.answer} text={f.text} onCite={setSource} onAsk={submit} />
              ),
            )}
            {typing ? <TypingDots /> : null}
          </ul>
        )}
        <div ref={end} />
      </div>
      <div className="ak-composer">
        {empty ? <SuggestionChips chips={SUGGESTIONS} onPick={submit} /> : null}
        <form
          className="chat-input ak-input"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            submit(text);
          }}
        >
          <label htmlFor={fieldId} className="sr-only">
            Ask, or say what should happen
          </label>
          <textarea id={fieldId} ref={input} rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} placeholder="Ask, or say what should happen…" className="chat-input__field t-input" autoComplete="off" enterKeyHint="send" autoFocus={autoFocus} />
          <Pressable type="submit" className="chat-input__send" aria-label="Send" lift={false} disabled={!text.trim()}>
            <ArrowUp size={18} strokeWidth={2.2} aria-hidden />
          </Pressable>
        </form>
        <p className={`${T.small} ak-foot`}>{FOOTER}</p>
      </div>
      <NoticeDrawer noticeId={source} onClose={() => setSource(null)} />
    </>
  );
}
