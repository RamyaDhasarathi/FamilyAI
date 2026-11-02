// Floating "Ask FamilyOS anything…" bar (MASTER_AGENT.md §3.1, §7 Phase 2.2;
// FamilyOS.mp4 1:50, 10:50): the home Ask bar as a real text field, ≈640 px
// wide, 24 px from the bottom of the content area, with a ⌘K hint, a
// paperclip and the mic. Enter opens /ask?q=…; the paperclip reads a file
// into a new notice (nothing else happens); the mic fills in what it heard.
// `/` focuses it. Pages with their own Ask bar don't render it.
import { useRef } from 'react';
import { useNavigate } from 'react-router';
import { AskBar } from '../../components/AskBar';
import { useHotkeys } from '../../hooks/useHotkeys';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useListening } from '../../screens/home/useHomeEffects';
import { deskCopy } from '../copy';
import { askPath } from './nav';

export function FloatingAsk() {
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const { listening, listen } = useListening(null, (t) => navigate(askPath(t)));
  useHotkeys({
    '/': (e) => {
      e.preventDefault();
      input.current?.focus();
    },
  });

  const onFile = (f: File | undefined) => {
    if (!f) return;
    const kb = Math.max(1, Math.round(f.size / 1024));
    const id = useDesk.getState().addNotice({
      title: f.name,
      body: `${f.name} (${kb} KB), added from this browser. FamilyOS has not read it yet.`,
      source: 'paste',
      attachments: 1,
    });
    useFamilyOS.getState().toast(deskCopy.ask.attached(f.name));
    navigate(`/inbox/${id}`);
  };

  return (
    <div className="desk-ask" role="region" aria-label={deskCopy.ask.placeholder}>
      <AskBar
        placeholder={deskCopy.ask.placeholder}
        icon="sparkles"
        onSubmit={(q) => navigate(askPath(q))}
        inputRef={input}
        hintKeys={['⌘K']}
        onAttach={() => file.current?.click()}
        attachLabel={deskCopy.ask.attach}
        onMic={listen}
        micLabel={deskCopy.ask.mic}
        listening={listening}
      />
      <input
        ref={file}
        type="file"
        hidden
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          onFile(e.target.files?.[0]);
          e.target.value = '';
        }}
      />
    </div>
  );
}
