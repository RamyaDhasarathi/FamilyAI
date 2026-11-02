// "Ask FamilyOS" glass bar with the white mic button (AGENT_WEB.md §8.1.5).
// The bar opens the chat; `/` focuses it on Home (key hint on desktop). The mic
// shows a fake listening state (pulse, waveform) and never asks for the
// microphone; the caller drops a canned transcript into the chat afterwards.
// Desktop (MASTER_AGENT.md §7 Phase 2.2) passes `onSubmit` to make it a real
// text field, plus `hintKeys` (⌘K) and `onAttach` (paperclip); without those
// optional props it renders exactly as before.
import { forwardRef, useState, type Ref } from 'react';
import clsx from 'clsx';
import { Keyboard, MessageCircle, Mic, Paperclip, Sparkles } from 'lucide-react';
import { copy } from '../mocks/data';
import { webCopy } from '../mocks/webData';
import { T } from '../theme/typography';
import { KeyHint } from './Labels';
import { Pressable } from './Pressable';

interface Props {
  placeholder: string;
  icon?: 'keyboard' | 'message' | 'sparkles';
  onPress?: () => void;
  onMic?: () => void;
  listening?: boolean;
  slashHint?: boolean;
  className?: string;
  /** Desktop: a real text field; Enter submits the trimmed text. */
  onSubmit?: (text: string) => void;
  inputRef?: Ref<HTMLInputElement>;
  /** Desktop: key hint chips instead of the `/` hint (e.g. ['⌘K']). */
  hintKeys?: string[];
  /** Desktop: a paperclip button before the mic. */
  onAttach?: () => void;
  attachLabel?: string;
  micLabel?: string;
}

const ICONS = { keyboard: Keyboard, message: MessageCircle, sparkles: Sparkles };

export const AskBar = forwardRef<HTMLButtonElement, Props>(function AskBar(
  { placeholder, icon = 'keyboard', onPress, onMic, listening = false, slashHint, className, onSubmit, inputRef, hintKeys, onAttach, attachLabel, micLabel },
  ref
) {
  const Icon = ICONS[icon];
  if (onSubmit) {
    return (
      <AskField
        {...{ placeholder, Icon, onSubmit, inputRef, hintKeys, onAttach, attachLabel, onMic, listening, className }}
        micLabel={micLabel ?? 'Speak to FamilyOS'}
      />
    );
  }
  return (
    <div className={clsx('ask-bar', listening && 'ask-bar--listening', className)}>
      <Pressable ref={ref} className="ask-bar__input" onClick={onPress} pressScale={0.98} lift={false} aria-label={`${placeholder}. Opens the chat`}>
        <Icon size={18} strokeWidth={1.8} className="ask-bar__icon" aria-hidden />
        {listening ? (
          <span className="ask-bar__wave" aria-hidden>
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <i key={i} style={{ animationDuration: `${260 + i * 70}ms` }} />
            ))}
            <span className={clsx(T.input, 'ask-bar__listening')}>{copy.listening}</span>
          </span>
        ) : (
          <span className={clsx(T.input, 'ask-bar__placeholder')}>{placeholder}</span>
        )}
        {slashHint && !listening ? <KeyHint keys={[webCopy.slashHint]} className="ask-bar__hint" /> : null}
      </Pressable>
      {onMic ? (
        <span className="ask-bar__mic-wrap">
          <span className="ask-bar__mic-ring" aria-hidden />
          <Pressable className="ask-bar__mic" onClick={onMic} lift={false} aria-label={listening ? 'Listening' : 'Speak to FamilyOS'} aria-pressed={listening}>
            <Mic size={18} strokeWidth={2} aria-hidden />
          </Pressable>
        </span>
      ) : null}
      <span className="sr-only" aria-live="polite">
        {listening ? copy.listening : ''}
      </span>
    </div>
  );
});

/** The desktop text-field variant (only rendered when `onSubmit` is passed). */
function AskField({
  placeholder, Icon, onSubmit, inputRef, hintKeys, onAttach, attachLabel, onMic, micLabel, listening, className,
}: Pick<Props, 'placeholder' | 'onSubmit' | 'inputRef' | 'hintKeys' | 'onAttach' | 'attachLabel' | 'onMic' | 'micLabel' | 'listening' | 'className'> & { Icon: typeof Keyboard }) {
  const [text, setText] = useState('');
  return (
    <div className={clsx('ask-bar', 'ask-bar--field', listening && 'ask-bar--listening', className)}>
      <form
        className="ask-bar__input"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          const t = text.trim();
          if (!t) return;
          onSubmit?.(t);
          setText('');
        }}
      >
        <Icon size={18} strokeWidth={1.8} className="ask-bar__icon" aria-hidden />
        {listening ? (
          <span className="ask-bar__wave" aria-hidden>
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <i key={i} style={{ animationDuration: `${260 + i * 70}ms` }} />
            ))}
            <span className={clsx(T.input, 'ask-bar__listening')}>{copy.listening}</span>
          </span>
        ) : (
          <input
            ref={inputRef}
            className={clsx(T.input, 'ask-bar__field')}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={placeholder}
            aria-label={placeholder}
            enterKeyHint="send"
            autoComplete="off"
          />
        )}
        {hintKeys && !listening ? <KeyHint keys={hintKeys} className="ask-bar__hint" /> : null}
      </form>
      {onAttach ? (
        <Pressable className="ask-bar__attach" onClick={onAttach} lift={false} aria-label={attachLabel ?? 'Attach a file'} title={attachLabel}>
          <Paperclip size={17} strokeWidth={1.9} aria-hidden />
        </Pressable>
      ) : null}
      {onMic ? (
        <span className="ask-bar__mic-wrap">
          <span className="ask-bar__mic-ring" aria-hidden />
          <Pressable className="ask-bar__mic" onClick={onMic} lift={false} aria-label={listening ? 'Listening' : micLabel} aria-pressed={listening}>
            <Mic size={18} strokeWidth={2} aria-hidden />
          </Pressable>
        </span>
      ) : null}
      <span className="sr-only" aria-live="polite">
        {listening ? copy.listening : ''}
      </span>
    </div>
  );
}
