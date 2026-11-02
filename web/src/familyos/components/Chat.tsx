// Chat pieces (AGENT_WEB.md §8.6): bubbles, typing indicator, suggestion chips.
import { motion } from 'framer-motion';
import clsx from 'clsx';
import type { ChatMessage } from '../services/interfaces';
import { Pressable } from './Pressable';

export function ChatBubble({ msg }: { msg: ChatMessage }) {
  const mine = msg.role === 'user';
  return (
    <motion.li
      className={clsx('bubble', mine ? 'bubble--mine' : 'bubble--theirs')}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.26 }}
    >
      <span className="sr-only">{mine ? 'You: ' : 'FamilyOS: '}</span>
      {msg.text}
    </motion.li>
  );
}

export function TypingDots() {
  return (
    <motion.li className="bubble bubble--theirs bubble--typing" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
      <span className="sr-only">FamilyOS is typing</span>
      <i aria-hidden />
      <i aria-hidden />
      <i aria-hidden />
    </motion.li>
  );
}

export function SuggestionChips({ chips, onPick }: { chips: string[]; onPick: (c: string) => void }) {
  if (!chips.length) return null;
  return (
    <div className="chips-bar no-scrollbar" role="group" aria-label="Suggestions">
      {chips.map((c) => (
        <Pressable key={c} className="chip" onClick={() => onPick(c)} aria-label={`Ask: ${c}`} lift={false}>
          {c}
        </Pressable>
      ))}
    </div>
  );
}
