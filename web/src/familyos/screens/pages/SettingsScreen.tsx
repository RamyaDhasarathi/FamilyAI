// Settings, restyled (AGENT_WEB.md §8.8, mobile SettingsScreen): summary
// button mode, low-power graphics (remembered in this browser), the dev-only
// Demo scenario and Reset demo family, privacy notes, version and Log out.
import { useNavigate } from 'react-router';
import clsx from 'clsx';
import { copy } from '../../mocks/data';
import { pageMeta } from '../../mocks/webData';
import { SCENARIOS, scenarioThemes } from '../../theme/stateThemes';
import { T } from '../../theme/typography';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useFamily } from '../../store/useFamily';
import { storeLowPower } from '../../store/useWebUI';
import { usePageMeta } from '../../hooks/usePageMeta';
import { Dot, SectionLabel } from '../../components/Labels';
import { Pressable } from '../../components/Pressable';
import { ScreenShell } from '../../components/ScreenShell';

export default function SettingsScreen() {
  const navigate = useNavigate();
  const st = useFamilyOS();
  const resetFamily = useFamily((x) => x.reset);
  const s = copy.settings;
  usePageMeta(pageMeta.settings);
  return (
    <ScreenShell title={s.title}>
      <SectionLabel>{s.summarySection}</SectionLabel>
      <div className="list-card">
        <button type="button" className="list-row" onClick={st.toggleSummaryMode}>
          <span className={T.menu}>{copy.profileMenu.summaryButton}</span>
          <span className="chip chip--small">{copy.summaryModeLabel[st.summaryMode]}</span>
        </button>
      </div>

      <SectionLabel className="gap-top">{s.graphicsSection}</SectionLabel>
      <div className="list-card">
        <div className="list-row">
          <div className="list-row__text">
            <p id="lp-label" className={T.menu}>
              {s.reduceGraphics}
            </p>
            <p className={clsx(T.small, 'list-row__hint')}>{s.reduceGraphicsHint}</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={st.lowPower}
            aria-labelledby="lp-label"
            className="switch"
            onClick={() => {
              storeLowPower(!st.lowPower);
              st.setLowPower(!st.lowPower);
            }}
          />
        </div>
      </div>

      {import.meta.env.DEV ? (
        <>
          <SectionLabel className="gap-top">{s.devSection}</SectionLabel>
          <div className="list-card">
            <div className="list-row list-row--col">
              <p id="demo-label" className={T.menu}>
                {s.demoScenario}
              </p>
              <p className={clsx(T.small, 'list-row__hint')}>{s.demoHint.replace('Long-press', 'Hold')} Or press Shift+S on Home.</p>
              <div className="segs" role="radiogroup" aria-labelledby="demo-label">
                {SCENARIOS.map((sc) => (
                  <Pressable key={sc} role="radio" aria-checked={st.seed === sc} className="seg" onClick={() => void st.setScenario(sc)} lift={false}>
                    <Dot color={scenarioThemes[sc].dot} size={6} />
                    {copy.scenarioLabels[sc]}
                  </Pressable>
                ))}
              </div>
            </div>
            <button type="button" className="list-row" onClick={() => void resetFamily()}>
              <span className="list-row__text">
                <span className={T.menu}>{s.resetFamily}</span>
                <span className={clsx(T.small, 'list-row__hint')} style={{ display: 'block' }}>
                  {s.resetFamilyHint.replace('on this device', 'in this browser')}
                </span>
              </span>
            </button>
          </div>
        </>
      ) : null}

      <SectionLabel className="gap-top">{s.privacySection}</SectionLabel>
      <div className="list-card">
        {s.privacy.map(([h, b]) => (
          <div key={h} className="list-row list-row--col">
            <p className={T.bodyStrong}>{h.replace('this phone', 'this browser')}</p>
            <p className={clsx(T.small, 'list-row__hint')}>{b.replace('this phone', 'this browser')}</p>
          </div>
        ))}
      </div>

      <SectionLabel className="gap-top">{s.accountSection}</SectionLabel>
      <div className="list-card">
        <div className="list-row">
          <span className={T.menu}>{s.version}</span>
          <span className={T.small}>{s.versionValue}</span>
        </div>
        <button
          type="button"
          className="list-row"
          onClick={async () => {
            await st.logOut();
            navigate('/login', { replace: true });
          }}
        >
          <span className={T.menu} style={{ color: 'var(--danger)' }}>
            {copy.profileMenu.logout}
          </span>
        </button>
      </div>
    </ScreenShell>
  );
}
