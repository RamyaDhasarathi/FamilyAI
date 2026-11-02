// Agent Deep Layer page, /agent/:id (AGENT_WEB.md §8.7; video 3:20 Finance,
// 4:06 Calendar, 4:34 Grocery). Back button and a mini gem in the agent's
// colours on top; a glass panel with the title, hero, stat tiles and the
// "WHAT I DID" timeline; an "Ask {Agent} anything" bar that opens the agent
// chat. Phone: one column like the mobile screen; desktop: hero and tiles
// on the left, the timeline on the right (max 1080 px). Back: the button,
// browser back, Esc, or Backspace when not typing. Arriving through a
// satellite's reveal it fades in; otherwise it slides in like a pushed screen.
// Desktop (useIsDesktopWeb): the same page, also at /agents/:id, with the
// desktop-only sections (AgentDesktopExtras, MASTER_AGENT.md §4) below.
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import type { AgentDetail } from '../../services/interfaces';
import type { AgentId } from '../../theme/tokens';
import { colors, withAlpha } from '../../theme/tokens';
import { durations } from '../../theme/motion';
import { T } from '../../theme/typography';
import { agentNames, copy } from '../../mocks/data';
import { pageMeta } from '../../mocks/webData';
import { service } from '../../mocks/services';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useViewport } from '../../hooks/useBreakpoint';
import { useEscape } from '../../hooks/useEscape';
import { useHotkeys } from '../../hooks/useHotkeys';
import { usePageMeta } from '../../hooks/usePageMeta';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import { useIsDesktopWeb } from '../../hooks/useIsDesktopWeb';
import { AgentHero } from '../../components/AgentHero';
import { AskBar } from '../../components/AskBar';
import { SectionLabel } from '../../components/Labels';
import { MiniGem } from '../../components/MiniGem';
import { BackButton } from '../../components/ScreenShell';
import { goBack } from '../../components/navigation';
import { StatTile } from '../../components/StatTile';
import { TimelineItem } from '../../components/TimelineItem';
import { ToastHost } from '../../components/Toast';
import { ChatPanel } from '../panels/ChatPanel';
import { useListening } from '../home/useHomeEffects';
import './agent.css';

const AgentDesktopExtras = lazy(() => import('../../desktop/spaces/AgentDesktopExtras'));

export default function AgentPage({ agent }: { agent: AgentId }) {
  const navigate = useNavigate();
  const location = useLocation();
  const reduced = useReducedMotion();
  const { wide } = useViewport();
  const desk = useIsDesktopWeb();
  const color = colors.agents[agent];
  const name = agentNames[agent];
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const undone = useFamilyOS((s) => s.undone);
  const undo = useFamilyOS((s) => s.undo);
  const queueChat = useFamilyOS((s) => s.queueChat);
  const askRef = useRef<HTMLButtonElement>(null);
  const viaReveal = (location.state as { via?: string } | null)?.via === 'reveal';
  usePageMeta(pageMeta.agent(agent));

  useEffect(() => {
    let live = true;
    void service.getAgentDetail(agent).then((d) => live && setDetail(d));
    return () => {
      live = false;
    };
  }, [agent]);

  const openChat = (pending?: string) => {
    queueChat(agent, pending);
    setChatOpen(true);
  };
  const { listening, listen } = useListening(null, () => openChat(detail?.chips[0]));
  const back = () => goBack(navigate, '/');
  useEscape(!chatOpen, back);
  useHotkeys(
    {
      Backspace: back,
      '/': (e) => {
        e.preventDefault();
        openChat();
      },
    },
    !chatOpen
  );

  const enter = viaReveal || reduced ? { initial: { opacity: 0 }, animate: { opacity: 1 } } : { initial: { opacity: 0, x: 40 }, animate: { opacity: 1, x: 0 } };
  const hero = detail ? (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.36 }}>
      <AgentHero hero={detail.hero} color={color} />
    </motion.div>
  ) : null;
  const stats = detail ? (
    <motion.div className="stats" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16, duration: 0.36 }}>
      {detail.stats.map((s) => (
        <StatTile key={s.label} stat={s} color={color} />
      ))}
    </motion.div>
  ) : null;
  const timeline = detail ? (
    <section aria-labelledby="whatidid" className="agent__timeline">
      <SectionLabel id="whatidid" className="agent__section">
        {copy.whatIDid}
      </SectionLabel>
      <ul className="timeline">
        {detail.timeline.map((e, i) => (
          <motion.li key={e.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.22 + (i * durations.stagger) / 1000, duration: 0.32 }}>
            <TimelineItem entry={e} color={color} undone={!!undone[e.id]} onUndo={() => undo(e.id)} onAsk={() => openChat(copy.tellMeMore(e.title))} />
          </motion.li>
        ))}
      </ul>
    </section>
  ) : null;

  return (
    <div className="agent" style={{ ['--accent' as string]: color }}>
      <div className="agent__glow" style={{ background: `radial-gradient(70vmax 40vmax at 50% -10%, ${withAlpha(color, 0.14)}, transparent 60%)` }} aria-hidden />
      <header className="agent__top">
        <BackButton onClick={back} />
        <span className="agent__gem">
          <MiniGem size={72} agentColor={color} />
        </span>
        <span className="agent__top-spacer" />
      </header>
      <motion.main id="main" className="agent__panel" {...enter} transition={{ duration: viaReveal ? 0.35 : 0.32, ease: [0.33, 1, 0.68, 1] }}>
        <div className="agent__head">
          <h1 className={T.agentTitle}>{detail?.title ?? name}</h1>
          <span className="title-underline" style={{ background: `linear-gradient(90deg, ${color}, ${withAlpha(color, 0)})` }} aria-hidden />
          <p className={clsx(T.small, 'agent__subtitle')}>{detail?.subtitle ?? ' '}</p>
        </div>
        {wide ? (
          <div className="agent__cols">
            <div className="agent__col">
              {hero}
              {stats}
            </div>
            <div className="agent__col">{timeline}</div>
          </div>
        ) : (
          <>
            {hero}
            {stats}
            {timeline}
          </>
        )}
      </motion.main>
      {desk ? (
        <Suspense fallback={null}>
          <div className="desk-agent-extras">
            <AgentDesktopExtras agent={agent} />
          </div>
        </Suspense>
      ) : null}
      <div className="agent__ask">
        <AskBar ref={askRef} placeholder={copy.askAgent(name)} icon="message" onPress={() => openChat()} onMic={listen} listening={listening} slashHint />
      </div>
      <ToastHost bottom="calc(84px + env(safe-area-inset-bottom))" />
      <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} thread={agent} />
    </div>
  );
}
