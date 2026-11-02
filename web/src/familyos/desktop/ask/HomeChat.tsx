// Desktop Home after its first message: the orb and stones fade out
// (shell.css, html.home-chatting) and the Ask page's chat fades in over the
// stage — the same DeskPage header, bubbles, answers, composer and footer as
// /ask (AskChat). "New chat" clears it and brings the stones back; so do the
// sidebar's Today and the logo. Only HomeOrbit renders this, only on desktop.
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { pageMeta } from '../../mocks/webData';
import { PillButton } from '../../components/Pills';
import { DeskPage } from '../shell/DeskPage';
import { AskChat } from './AskChat';
import { ASK_DESCRIPTION } from './askCopy';
import { useAsk } from './askStore';

export default function HomeChat({ onNewChat }: { onNewChat: () => void }) {
  return (
    <motion.div
      className="home-chat"
      initial={{ opacity: 0, scale: 0.985 }}
      animate={{ opacity: 1, scale: 1, transition: { duration: 0.34, delay: 0.18, ease: [0.2, 0.7, 0.2, 1] } }}
      exit={{ opacity: 0, scale: 0.985, transition: { duration: 0.22 } }}
    >
      <DeskPage
        icon={Sparkles}
        color={colors.violet}
        title="Ask"
        className="ak-page"
        metaTitle={pageMeta.home.title}
        description={ASK_DESCRIPTION}
        actions={
          <PillButton
            label="New chat"
            aria-label="New chat: clear this conversation and show the agents again"
            onClick={() => {
              useAsk.getState().clear();
              onNewChat();
            }}
          />
        }
      >
        <AskChat />
      </DeskPage>
    </motion.div>
  );
}
