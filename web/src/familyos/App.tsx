// FamilyOS web app: routes and the persistent Home stage (AGENT_WEB.md §5, §8).
// Home is mounted the first time it is shown and then kept, paused and hidden,
// under every other page, so going back is instant. Every page is its own
// chunk; three.js loads only with Home or a mini gem.
// Desktop (MASTER_AGENT.md §5, §6): on a desktop-width window the DeskShell
// (sidebar / icon rail, floating Ask bar, ⌘K) renders beside every page except
// log in, sign up, the code page and the splash; the desk routes below render
// as one column without it on narrower windows. Nothing on mobile links to them.
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router';
import { MotionConfig } from 'framer-motion';
import { AGENT_IDS, type AgentId } from './theme/tokens';
import { applyScenarioVars } from './theme/cssVars';
import { webCopy } from './mocks/webData';
import { useFamilyOS, useMood } from './store/useFamilyOS';
import { storedLowPower } from './store/useWebUI';
import { useReducedMotion } from './hooks/useReducedMotion';
import { useIsDesktopWeb } from './hooks/useIsDesktopWeb';
import { isChromeless } from './desktop/shell/routes';
import { API_ENABLED } from './services/api';
import { landing } from './services/landing';
import { redeemLink } from './services/apiService';
import { sessionStarted } from './session';
import './components/components.css';
import './screens/panels/panels.css';
import './screens/pages/pages.css';

const HomeOrbit = lazy(() => import('./screens/home/HomeOrbit'));
const LoadingScreen = lazy(() => import('./screens/pages/LoadingScreen'));
const LoginScreen = lazy(() => import('./screens/pages/LoginScreen'));
const SignupScreen = lazy(() => import('./screens/pages/SignupScreen'));
const OtpScreen = lazy(() => import('./screens/pages/OtpScreen'));
const AgentPage = lazy(() => import('./screens/agent/AgentPage'));
const SettingsScreen = lazy(() => import('./screens/pages/SettingsScreen'));
const PlaceholderScreen = lazy(() => import('./screens/pages/PlaceholderScreen'));
const NotFound = lazy(() => import('./screens/pages/NotFound'));
const FamilyHub = lazy(() => import('./screens/family/FamilyHub'));
const MemberProfile = lazy(() => import('./screens/family/MemberProfile'));
const MemberWizard = lazy(() => import('./screens/family/MemberWizard'));
const DevGraphics = import.meta.env.DEV ? lazy(() => import('./screens/pages/DevGraphics')) : null;
// Desktop shell and desk pages (MASTER_AGENT.md §5).
const DeskShell = lazy(() => import('./desktop/shell/DeskShell'));
const TodayPage = lazy(() => import('./desktop/today/TodayPage'));
const InboxPage = lazy(() => import('./desktop/inbox/InboxPage'));
const WaitingPage = lazy(() => import('./desktop/waiting/WaitingPage'));
const AskPage = lazy(() => import('./desktop/ask/AskPage'));
const SpacePage = lazy(() => import('./desktop/spaces/SpacePage'));
const PlanPage = lazy(() => import('./desktop/spaces/PlanPage'));
const InvestmentsPage = lazy(() => import('./desktop/spaces/InvestmentsPage'));
const ErrandsPage = lazy(() => import('./desktop/admin/ErrandsPage'));
const ErrandPage = lazy(() => import('./desktop/admin/ErrandPage'));
const CollectPage = lazy(() => import('./desktop/admin/CollectPage'));
const DataSourcesPage = lazy(() => import('./desktop/admin/DataSourcesPage'));
const ConnectedServicesPage = lazy(() => import('./desktop/admin/ConnectedServicesPage'));
const QuarantinePage = lazy(() => import('./desktop/admin/QuarantinePage'));
const RevisionsPage = lazy(() => import('./desktop/admin/RevisionsPage'));
const AuditPage = lazy(() => import('./desktop/admin/AuditPage'));
const SettingsHouseholdPage = lazy(() => import('./desktop/admin/SettingsHouseholdPage'));

/** `/`: the Home stage itself is drawn by the shell; this only redirects when it shouldn't show. */
function HomeGate() {
  const loggedIn = useFamilyOS((s) => s.loggedIn);
  const booted = useFamilyOS((s) => s.booted);
  // On the backend only the server knows whether this browser is signed in: Loading asks it, then routes.
  if (API_ENABLED && !booted) return <Navigate to="/loading" replace />;
  if (!loggedIn) return <Navigate to="/login" replace />;
  if (!sessionStarted()) return <Navigate to="/loading" replace />;
  return null;
}

function AgentRoute() {
  const { pathname } = useLocation();
  const id = pathname.split('/')[2] as AgentId;
  if (!AGENT_IDS.includes(id)) return <NotFound />;
  return <AgentPage key={id} agent={id} />;
}

function Page({ children }: { children: ReactNode }) {
  return <div className="page-layer">{children}</div>;
}

function Shell() {
  const { pathname } = useLocation();
  const loggedIn = useFamilyOS((s) => s.loggedIn);
  const booted = useFamilyOS((s) => s.booted);
  const mood = useMood();
  const desk = useIsDesktopWeb();
  const onHome = pathname === '/';
  const [homeMounted, setHomeMounted] = useState(false);
  if (onHome && loggedIn && sessionStarted() && !homeMounted) setHomeMounted(true);
  if (!loggedIn && homeMounted) setHomeMounted(false);
  const navigate = useNavigate();
  const [landingBusy, setLandingBusy] = useState(landing !== null);

  // A return from the backend (a mailed link, a founding ticket, Google): handled before anything boots.
  useEffect(() => {
    if (!landing) return;
    const st = useFamilyOS.getState();
    void (async () => {
      if (landing.kind === 'link') {
        const r = await redeemLink(landing.link);
        if (r.ok) {
          useFamilyOS.setState({ loggedIn: true, booted: false });
          navigate('/loading', { replace: true });
        } else {
          st.toast(r.message, { duration: 5000 });
          navigate('/login', { replace: true });
        }
      } else if (landing.kind === 'goto') {
        navigate(landing.path, { replace: true });
      } else if (landing.kind === 'found') {
        navigate('/signup', { replace: true, state: { founding: landing.founding, email: landing.email } });
      } else {
        st.toast(webCopy.signinSaid[landing.signin], { duration: 5000 });
        navigate('/login', { replace: true });
      }
      setLandingBusy(false);
    })();
  }, [navigate]);

  // Deep links skip the Loading screen, so boot the store here when needed.
  useEffect(() => {
    if (!booted && !landingBusy && pathname !== '/loading') void useFamilyOS.getState().boot();
  }, [booted, landingBusy, pathname]);
  // The focus ring, panel tint and summary dot follow the mood everywhere.
  useEffect(() => {
    applyScenarioVars(mood);
  }, [mood]);
  // Low-power graphics: the user's choice, else weak hardware (§11.2).
  useEffect(() => {
    const stored = storedLowPower();
    const weak = (navigator.hardwareConcurrency ?? 8) <= 4;
    if (stored ?? weak) useFamilyOS.getState().setLowPower(true);
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <>
      <a href="#main" className="skip-link">
        {webCopy.skip}
      </a>
      {homeMounted ? (
        <Suspense fallback={null}>
          <HomeOrbit active={onHome} />
        </Suspense>
      ) : null}
      {desk && loggedIn && !isChromeless(pathname) && !(onHome && !homeMounted) ? (
        <Suspense fallback={null}>
          <DeskShell />
        </Suspense>
      ) : null}
      {/* On the backend a page needs a session: once the server has said there is none, Log in. */}
      {API_ENABLED && booted && !loggedIn && !landingBusy && !onHome && !isChromeless(pathname) ? <Navigate to="/login" replace /> : null}
      {landingBusy ? (
        <div className="page-layer page-loading" />
      ) : (
      <Suspense fallback={onHome ? null : <div className="page-layer page-loading" />}>
        <Routes>
          <Route path="/" element={<HomeGate />} />
          <Route path="/loading" element={<Page><LoadingScreen /></Page>} />
          <Route path="/login" element={<Page><LoginScreen /></Page>} />
          <Route path="/signup" element={<Page><SignupScreen /></Page>} />
          <Route path="/verify" element={<Page><OtpScreen /></Page>} />
          <Route path="/agent/:id" element={<Page><AgentRoute /></Page>} />
          <Route path="/settings" element={<Page><SettingsScreen /></Page>} />
          <Route path="/family" element={<Page><FamilyHub /></Page>} />
          <Route path="/family/:id" element={<Page><MemberProfile /></Page>} />
          <Route
            path="/family/:id/details/:section?"
            element={
              <Page>
                <MemberProfile />
                <MemberWizard />
              </Page>
            }
          />
          <Route path="/page/:slug" element={<Page><PlaceholderScreen /></Page>} />
          {/* Desktop routes (§5): /agents/:id is the same AgentPage as /agent/:id. */}
          <Route path="/today" element={<Page><TodayPage /></Page>} />
          <Route path="/agents/finance/investments" element={<Page><InvestmentsPage /></Page>} />
          <Route path="/agents/:id" element={<Page><AgentRoute /></Page>} />
          <Route path="/memories" element={<Page><SpacePage key="memories" space="memories" /></Page>} />
          <Route path="/health" element={<Page><SpacePage key="health" space="health" /></Page>} />
          <Route path="/travel" element={<Page><SpacePage key="travel" space="travel" /></Page>} />
          <Route path="/plans/:id" element={<Page><PlanPage /></Page>} />
          <Route path="/inbox/:noticeId?" element={<Page><InboxPage /></Page>} />
          <Route path="/waiting" element={<Page><WaitingPage /></Page>} />
          <Route path="/ask" element={<Page><AskPage /></Page>} />
          <Route path="/errands" element={<Page><ErrandsPage /></Page>} />
          <Route path="/errands/:id" element={<Page><ErrandPage /></Page>} />
          <Route path="/quarantine" element={<Page><QuarantinePage /></Page>} />
          <Route path="/revisions" element={<Page><RevisionsPage /></Page>} />
          <Route path="/collect" element={<Page><CollectPage /></Page>} />
          <Route path="/sources" element={<Page><DataSourcesPage /></Page>} />
          <Route path="/services" element={<Page><ConnectedServicesPage /></Page>} />
          <Route path="/audit" element={<Page><AuditPage /></Page>} />
          <Route path="/settings/household" element={<Page><SettingsHouseholdPage /></Page>} />
          <Route path="/settings/privacy" element={<Page><SettingsHouseholdPage section="privacy" /></Page>} />
          {DevGraphics ? <Route path="/dev/graphics" element={<Page><DevGraphics /></Page>} /> : null}
          <Route path="*" element={<Page><NotFound /></Page>} />
        </Routes>
      </Suspense>
      )}
    </>
  );
}

export function App() {
  const reduced = useReducedMotion();
  return (
    <MotionConfig reducedMotion={reduced ? 'always' : 'never'}>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || undefined}>
        <Shell />
      </BrowserRouter>
    </MotionConfig>
  );
}
