// Loading (design.md §13.2, mobile LoadingScreen): the gem with the five
// agent colours orbiting as glowing dots on a faint ring, the wordmark, a
// status line that steps through messages and an agent-colour progress bar
// exposed to assistive technology. ~2.6 s, once per browser session, then
// Home (or Log in when signed out).
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { AnimatePresence, motion } from 'framer-motion';
import { AGENT_IDS, colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { copy } from '../../mocks/data';
import { pageMeta } from '../../mocks/webData';
import { useFamilyOS } from '../../store/useFamilyOS';
import { usePageMeta } from '../../hooks/usePageMeta';
import { markSessionStarted } from '../../session';
import { MiniGem } from '../../components/MiniGem';
import { OnboardingBackdrop } from '../../components/OnboardingBackdrop';

const DURATION = 2600;
const RING = 150;

export default function LoadingScreen() {
  const navigate = useNavigate();
  const boot = useFamilyOS((s) => s.boot);
  const [msg, setMsg] = useState(0);
  const [pct, setPct] = useState(0);
  usePageMeta(pageMeta.loading);

  useEffect(() => {
    const t0 = Date.now();
    const tick = window.setInterval(() => {
      const k = Math.min(1, (Date.now() - t0) / DURATION);
      setPct(Math.round(k * 100));
      setMsg(Math.min(copy.loading.length - 1, Math.floor(k * copy.loading.length)));
    }, 120);
    let live = true;
    void Promise.all([boot(), new Promise((r) => setTimeout(r, DURATION))]).then(() => {
      if (!live) return;
      markSessionStarted();
      navigate(useFamilyOS.getState().loggedIn ? '/' : '/login', { replace: true });
    });
    return () => {
      live = false;
      window.clearInterval(tick);
    };
  }, [boot, navigate]);

  return (
    <div className="loading">
      <OnboardingBackdrop />
      <main id="main" className="loading__center">
        <div className="loading__gem" style={{ width: RING * 2, height: RING * 2 }}>
          <span className="loading__track" aria-hidden />
          <span className="loading__ring" aria-hidden>
            {AGENT_IDS.map((id, i) => {
              const a = (i / AGENT_IDS.length) * Math.PI * 2;
              return (
                <i
                  key={id}
                  style={{
                    left: RING + Math.cos(a) * RING - 5,
                    top: RING + Math.sin(a) * RING - 5,
                    background: colors.agents[id],
                    boxShadow: `0 0 10px ${colors.agents[id]}, 0 0 18px ${colors.agents[id]}88`,
                  }}
                />
              );
            })}
          </span>
          <MiniGem size={220} />
        </div>
        <h1 className="loading__word">{copy.appName}</h1>
        <div className="loading__msg" aria-hidden>
          <AnimatePresence mode="wait">
            <motion.p key={msg} className={T.small} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.26 }}>
              {copy.loading[msg]}
            </motion.p>
          </AnimatePresence>
        </div>
        <div className="loading__bar" role="progressbar" aria-label={copy.loading[msg]} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <span className="loading__fill" style={{ width: `${pct}%` }}>
            {AGENT_IDS.map((id) => (
              <i key={id} style={{ background: colors.agents[id] }} />
            ))}
          </span>
        </div>
      </main>
    </div>
  );
}
