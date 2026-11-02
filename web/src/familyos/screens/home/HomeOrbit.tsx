// Home — the Orbit screen (AGENT_WEB.md §8.1, video 0:00). Layers, back →
// front: WebGL stage (ambient, dust, satellites, gem, morph) → crystal and
// satellite hit areas → text and controls → Dashboard → panels → toasts.
// It stays mounted (paused, hidden) while other pages are open, so coming
// back is instant and the WebGL context is never recreated.
// Desktop (useIsDesktopWeb, MASTER_AGENT.md §7 Phase 1): a click on a stone
// opens /agents/:id and on the crystal /today, through the same openAgent
// path as the Dashboard tiles, after stopping any walkthrough instantly.
// Desktop also has no avatar pill (the sidebar shows the profile) and no
// "Your agents" panel (handle, D / arrow keys, swipe and wheel), no
// "Today's summary" line or right-side Today / Needs-you panels (read mode
// and "+N more" open the Today and Waiting pages instead), and the
// Ask bar is a text field: its first message fades the stones away and turns
// Home into the Ask page's chat (HomeChat) until "New chat".
import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router';
import clsx from 'clsx';
import { AnimatePresence } from 'framer-motion';
import { ChevronUp } from 'lucide-react';
import type { AgentId } from '../../theme/tokens';
import { AGENT_IDS } from '../../theme/tokens';
import { scenarioThemes } from '../../theme/stateThemes';
import { copy, walkLabel } from '../../mocks/data';
import { pageMeta, webCopy } from '../../mocks/webData';
import { headlineItem, summaryCount } from '../../mocks/scenarios';
import { useFamilyOS, useMood } from '../../store/useFamilyOS';
import { storedLowPower, useWebUI } from '../../store/useWebUI';
import { OrbitEngine } from '../../engine/OrbitEngine';
import { settleDash } from '../../engine/coreInput';
import { useViewport } from '../../hooks/useBreakpoint';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import { useIsDesktopWeb } from '../../hooks/useIsDesktopWeb';
import { deskCopy } from '../../desktop/copy';
import { useDeskUI } from '../../desktop/shell/useDeskUI';
import { useEscape } from '../../hooks/useEscape';
import { useHotkeys } from '../../hooks/useHotkeys';
import { usePageMeta } from '../../hooks/usePageMeta';
import { AskBar } from '../../components/AskBar';
import { KeyHint } from '../../components/Labels';
import { Pressable } from '../../components/Pressable';
import { SummaryButton } from '../../components/SummaryButton';
import { SwipeCard } from '../../components/SwipeCard';
import { ToastHost } from '../../components/Toast';
import { TodayPanel } from '../panels/TodayPanel';
import { NeedsYouPanel } from '../panels/NeedsYouPanel';
import { ChatPanel } from '../panels/ChatPanel';
import { ProfileMenu } from '../panels/ProfileMenu';
import { HelpOverlay } from '../panels/HelpOverlay';
import { EngineContext, useFrame } from './engineContext';
import { HomeHeader, StatusBlock } from './HomeHeader';
import { SatelliteLayer } from './SatelliteLayer';
import { CoreHit } from './CoreHit';
import { DashboardPanel } from './DashboardPanel';
import { AgentReveal } from './AgentReveal';
import { StageFallback } from './StageFallback';
import { useCelebration, useListening, useScenarioSync } from './useHomeEffects';
import { useWalkthrough } from './useWalkthrough';
import { useDashGestures } from './useDashGestures';
import './home.css';

const HomeChat = lazy(() => import('../../desktop/ask/HomeChat'));

/** Desktop: start a fresh Ask conversation with this first message (loaded only when used). */
function askFresh(text: string) {
  void import('../../desktop/ask/askStore').then(({ useAsk }) => {
    useAsk.getState().clear();
    useAsk.getState().ask(text);
  });
}

export default function HomeOrbit({ active }: { active: boolean }) {
  const { W, H } = useViewport();
  const [engine] = useState(() => new OrbitEngine('calm', window.innerWidth, window.innerHeight));
  const canvas = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();
  const lowPower = useFamilyOS((s) => s.lowPower);
  const fallback = useSyncExternalStore(
    (cb) => engine.subscribe(cb),
    () => engine.fallback
  );

  useEffect(() => {
    if (!canvas.current) return;
    void engine.attach(canvas.current);
    engine.setOnLowPower(() => {
      if (storedLowPower() === null) useFamilyOS.getState().setLowPower(true);
    });
    return () => engine.detach();
  }, [engine]);
  useEffect(() => {
    engine.resize(W, H);
  }, [engine, W, H]);
  useEffect(() => {
    engine.setActive(active);
  }, [engine, active]);
  useEffect(() => {
    engine.setReduced(reduced);
  }, [engine, reduced]);
  useEffect(() => {
    engine.setLowPower(lowPower);
    document.documentElement.classList.toggle('low-power', lowPower);
  }, [engine, lowPower]);
  useEffect(() => {
    if (!active) return;
    document.documentElement.classList.add('no-overscroll');
    return () => document.documentElement.classList.remove('no-overscroll');
  }, [active]);

  return (
    <EngineContext.Provider value={engine}>
      <div className={clsx('home', !active && 'home--hidden')} aria-hidden={!active} inert={!active}>
        <canvas ref={canvas} className="home__canvas" aria-hidden />
        {fallback ? <StageFallback /> : null}
        <HomeUI engine={engine} active={active} />
      </div>
    </EngineContext.Provider>
  );
}

function HomeUI({ engine, active }: { engine: OrbitEngine; active: boolean }) {
  const navigate = useNavigate();
  const { wide } = useViewport();
  const st = useFamilyOS();
  const mood = useMood();
  const dashOpen = useWebUI((s) => s.dashOpen);
  const setDashOpen = useWebUI((s) => s.setDashOpen);
  const helpOpen = useWebUI((s) => s.helpOpen);
  const setHelpOpen = useWebUI((s) => s.setHelpOpen);
  const reveal = useWebUI((s) => s.reveal);
  const setReveal = useWebUI((s) => s.setReveal);
  const layer = useRef<HTMLDivElement>(null);
  const avatar = useRef<HTMLButtonElement>(null);
  const askRef = useRef<HTMLButtonElement>(null);
  const askInput = useRef<HTMLInputElement>(null);
  const { start, stop, stopNow } = useWalkthrough(engine);
  const desk = useIsDesktopWeb();
  const todayCount = useDeskUI((s) => s.todayCount);
  const homeChat = useDeskUI((s) => s.homeChat);
  const chatting = desk && homeChat;
  usePageMeta(pageMeta.home);
  useScenarioSync(engine, mood);
  useCelebration(engine);

  const walking = st.walk.active;
  // Opening a panel, the Dashboard or another page ends a running walkthrough.
  useEffect(() => {
    if ((st.sheet !== null || dashOpen || !active) && useFamilyOS.getState().walk.active) stop();
  }, [st.sheet, dashOpen, active, stop]);
  useEffect(() => {
    if (active) return;
    if (useFamilyOS.getState().sheet) useFamilyOS.getState().closeSheet();
  }, [active]);

  // The text layer fades as the Dashboard rises (mobile: 1 − 1.8·dashT).
  useFrame(engine, (e) => {
    const el = layer.current;
    if (!el) return;
    const o = Math.max(0, 1 - e.scene.v.dashT * 1.8);
    el.style.opacity = o.toFixed(3);
    el.style.pointerEvents = o < 0.05 ? 'none' : '';
  });

  const openDash = useCallback(() => {
    settleDash(engine.scene, true);
    engine.kick();
    setDashOpen(true);
  }, [engine, setDashOpen]);
  const closeDash = useCallback(() => {
    settleDash(engine.scene, false);
    engine.kick();
    setDashOpen(false);
  }, [engine, setDashOpen]);
  const stopIfWalking = useCallback(() => {
    if (useFamilyOS.getState().walk.active) stop();
  }, [stop]);
  const bindSwipe = useDashGestures(engine, layer, active && !dashOpen && !desk, stopIfWalking);
  // Widening the window to desktop with the panel open closes it (desktop has no "Your agents" panel).
  useEffect(() => {
    if (desk && dashOpen) closeDash();
  }, [desk, dashOpen, closeDash]);

  const agentPath = useCallback((agent: AgentId) => (desk ? `/agents/${agent}` : `/agent/${agent}`), [desk]);
  const openAgent = useCallback(
    (agent: AgentId) => {
      st.closeSheet();
      if (desk) stopNow();
      else stop();
      navigate(agentPath(agent));
    },
    [navigate, st, stop, stopNow, desk, agentPath]
  );
  const openToday = useCallback(() => {
    st.closeSheet();
    stopNow();
    navigate('/today');
  }, [navigate, st, stopNow]);
  // Desktop Home → Ask chat: the first message from the Ask bar (or the mic).
  const startChat = (text: string) => {
    st.closeSheet();
    stopNow();
    useDeskUI.getState().setHomeChat(true);
    askFresh(text);
  };
  const focusAsk = () => askInput.current?.focus();
  const { listening, listen } = useListening(engine, (t) => (desk ? startChat(t) : st.openChat('home', t)));
  useLayoutEffect(() => {
    const on = chatting && active;
    document.documentElement.classList.toggle('home-chatting', on);
    return () => document.documentElement.classList.remove('home-chatting');
  }, [chatting, active]);

  const onSummaryButton = () => {
    if (walking) stop();
    else if (st.summaryMode === 'read') {
      if (desk) openToday();
      else st.openSheet('today');
    }
    else void start(undefined, true);
  };
  const playSummary = () => void start(undefined, st.summaryMode === 'listen');
  const openNeeds = () => st.openSheet(st.needs.length ? 'needs' : 'today');
  const onMenu = (path: string) => {
    st.closeSheet();
    navigate(path);
  };
  const onLogout = async () => {
    stop();
    await st.logOut();
    navigate('/login', { replace: true });
  };

  useEscape(active && walking, stop);
  const quiet = active && st.sheet === null && !helpOpen && !chatting;
  useHotkeys(
    {
      '/': (e) => {
        e.preventDefault();
        if (desk) focusAsk();
        else st.openChat('home');
      },
      t: () => (dashOpen ? undefined : onSummaryButton()),
      ...(desk ? {} : { n: openNeeds }),
      ...(desk
        ? {}
        : {
            d: () => (dashOpen ? closeDash() : openDash()),
            ArrowUp: () => !dashOpen && openDash(),
            PageDown: () => !dashOpen && openDash(),
            ArrowDown: () => dashOpen && closeDash(),
            PageUp: () => dashOpen && closeDash(),
          }),
      '?': () => setHelpOpen(true),
      ...Object.fromEntries(AGENT_IDS.map((id, i) => [String(i + 1), () => openAgent(id)])),
      ...(import.meta.env.DEV ? { 'Shift+S': () => st.cycleScenario() } : {}),
    },
    quiet
  );

  const step = st.walk.steps[st.walk.index];
  const top = headlineItem(st.needs);
  const { n, word } = summaryCount(st.needs);
  const theme = scenarioThemes[mood];
  const single = !walking && st.needs.length === 1 && st.sheet === null ? st.needs[0] : null;
  const label = walking && step ? walkLabel(step.agent, st.walk.index + 1, st.walk.steps.length, !!st.walk.agent) : theme.label;
  const labelColor = walking && step ? `var(--agent-${step.agent})` : theme.dot;
  const headline = walking && step ? step.text : mood === 'calm' || !top ? copy.calmHeadline : top.text;

  return (
    <>
      <div ref={layer} className="home__layer" inert={chatting || undefined} {...bindSwipe()}>
        {walking ? <button type="button" className="home__stop" onClick={stop} aria-label={copy.core.stopLabel} tabIndex={-1} /> : null}
        <main id={chatting ? undefined : 'main'} className="home__ui">
          {st.profile ? (
            <HomeHeader
              ref={avatar}
              profile={st.profile}
              summaryWord={mood === 'calm' ? copy.allClear : `${n} ${word}`}
              summaryDot={theme.dot}
              onSummary={openNeeds}
              onAvatar={() => st.openSheet('profile')}
              avatarOpen={st.sheet === 'profile'}
              showAvatar={!desk}
              showSummary={!desk}
              onDateHold={import.meta.env.DEV ? st.cycleScenario : undefined}
            />
          ) : null}
          <section className="home__stage-ui" aria-label="Family core and agents">
            <CoreHit
              walking={walking}
              onHold={playSummary}
              onStop={stop}
              pressMode={desk ? 'navigate' : undefined}
              onOpen={desk ? openToday : undefined}
              tip={desk ? { title: deskCopy.stones.coreTitle(todayCount), hint: deskCopy.stones.coreHint, label: deskCopy.stones.coreLabel } : undefined}
            />
            <SatelliteLayer
              needs={st.needs}
              cards={st.dashboard}
              pressMode={desk ? 'navigate' : undefined}
              onTap={(a) => (desk ? openAgent(a) : void start(a, st.summaryMode === 'listen'))}
              onOpen={(agent, x, y) => {
                if (desk) stopNow();
                else stop();
                setReveal({ agent, x, y });
              }}
            />
          </section>
          <div className={clsx('home__bottom', single && 'home__bottom--single')}>
            <StatusBlock
              label={label}
              color={labelColor}
              headline={headline}
              compact={!!single}
              calm={!walking && mood === 'calm'}
              more={!walking && st.needs.length > 1 ? copy.more(st.needs.length - 1) : undefined}
              onMore={() => (desk ? navigate('/waiting') : st.openSheet('needs'))}
            />
            {single ? (
              <div className="home__single" data-no-swipe>
                <SwipeCard item={single} onDone={st.resolve} onLater={st.snooze} />
              </div>
            ) : (
              <div className="home__bar" style={{ opacity: st.sheet === 'chat' ? 0 : 1 }}>
                {desk ? (
                  <AskBar placeholder={copy.askPlaceholder} onSubmit={startChat} inputRef={askInput} hintKeys={[webCopy.slashHint]} onMic={listen} listening={listening} className="home__ask" />
                ) : (
                  <AskBar ref={askRef} placeholder={copy.askPlaceholder} onPress={() => st.openChat('home')} onMic={listen} listening={listening} slashHint className="home__ask" />
                )}
                <SummaryButton
                  mode={st.summaryMode}
                  playing={walking}
                  progress={st.walk.steps.length ? (st.walk.index + 1) / st.walk.steps.length : 0}
                  onPress={onSummaryButton}
                />
              </div>
            )}
            {wide && !desk ? (
              <Pressable className="home__dash-handle" onClick={openDash} title="Open the dashboard (D)" lift={false}>
                <ChevronUp size={14} aria-hidden />
                <span>{webCopy.dashHandle}</span>
                <KeyHint keys={['D']} />
              </Pressable>
            ) : null}
          </div>
        </main>
      </div>
      {desk ? null : (
        <DashboardPanel
          onOpenAgent={openAgent}
          onOpenSummary={() => st.openSheet(mood === 'urgent' ? 'needs' : 'today')}
          onAsk={() => st.openChat('home')}
          onMic={listen}
          listening={listening}
        />
      )}
      {desk ? null : (
        <>
          <TodayPanel open={active && st.sheet === 'today'} onClose={st.closeSheet} onOpenAgent={openAgent} />
          <NeedsYouPanel open={active && st.sheet === 'needs'} onClose={st.closeSheet} />
        </>
      )}
      <ChatPanel open={active && st.sheet === 'chat'} onClose={st.closeSheet} thread={st.chatThread} />
      {desk ? null : <ProfileMenu open={active && st.sheet === 'profile'} onClose={st.closeSheet} onNavigate={onMenu} onLogout={onLogout} anchor={avatar} />}
      <HelpOverlay open={active && helpOpen} onClose={() => setHelpOpen(false)} />
      <AnimatePresence>
        {chatting && active ? (
          <Suspense key="home-chat" fallback={null}>
            <HomeChat onNewChat={() => useDeskUI.getState().setHomeChat(false)} />
          </Suspense>
        ) : null}
      </AnimatePresence>
      {active && !chatting ? <ToastHost bottom={single ? 'calc(180px + env(safe-area-inset-bottom))' : 'calc(96px + env(safe-area-inset-bottom))'} /> : null}
      {reveal ? (
        <AgentReveal
          reveal={reveal}
          onCovered={() => navigate(agentPath(reveal.agent), { state: { via: 'reveal' } })}
          onDone={() => setReveal(null)}
        />
      ) : null}
    </>
  );
}
