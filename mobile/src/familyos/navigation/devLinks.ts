// Dev-only deep links for repeatable screenshots and flow checks
// (AGENT.md §13.3–13.4). Ignored in release builds.
//   familyos://dev?scenario=urgent            seed a demo scenario
//   familyos://dev?sheet=today|needs|profile|chat[&thread=finance]
//   familyos://dev?agent=finance              open an agent screen
//   familyos://dev?dash=1 | dash=0            open / close the Dashboard
//   familyos://dev?walk=today | walk=education  start a walkthrough
//   familyos://dev?home=1                     back to Home, sheets closed
//   familyos://dev?mode=listen|read           summary button mode
//   familyos://dev?screen=Settings|Family|Login|Loading
//   familyos://dev?member=<id> | wizard=<id>&section=basic|…|review | addMember=1 | resetFamily=1
//   familyos://dev?perf=1                     log UI-thread frame stats (300 frames)
//   familyos://dev?dbg=1|2|4                  profiling: skip shader | satellites | core (bitmask)
//   familyos://dev?low=1|0                    force low-power graphics on/off
import { useEffect } from 'react';
import { Linking } from 'react-native';
import type { NavigationContainerRef } from '@react-navigation/native';
import type { RootStackParamList } from './types';
import { AGENT_IDS, type AgentId } from '../theme/tokens';
import { SCENARIOS, type Scenario } from '../theme/stateThemes';
import { useFamilyOS } from '../store/useFamilyOS';
import { useFamily } from '../store/useFamily';
import type { SectionId } from '../services/interfaces';

function parse(url: string): Record<string, string> {
  const q = url.split('?')[1] ?? '';
  return Object.fromEntries(
    q
      .split('&')
      .filter(Boolean)
      .map((kv) => kv.split('=').map(decodeURIComponent) as [string, string])
  );
}

export function useDevLinks(nav: React.RefObject<NavigationContainerRef<RootStackParamList> | null>) {
  useEffect(() => {
    if (!__DEV__) return;
    const handle = async ({ url }: { url: string }) => {
      if (!url.includes('://dev')) return;
      const p = parse(url);
      const st = useFamilyOS.getState();
      if (p.home) {
        st.closeSheet();
        if (st.walk.active) st.setDevCommand({ stop: '1' });
        st.setDevCommand({ dash: '0' });
        if (nav.current?.getCurrentRoute()?.name !== 'Home') nav.current?.navigate('Home');
      }
      if (p.scenario && SCENARIOS.includes(p.scenario as Scenario)) await st.setScenario(p.scenario as Scenario);
      if (p.mode === 'listen' || p.mode === 'read') st.setSummaryMode(p.mode);
      if (p.agent && AGENT_IDS.includes(p.agent as AgentId)) nav.current?.navigate('Agent', { agent: p.agent as AgentId });
      if (p.screen === 'Settings' || p.screen === 'Family' || p.screen === 'Login' || p.screen === 'Loading') {
        nav.current?.navigate(p.screen);
      }
      if (p.member) nav.current?.navigate('MemberProfile', { id: p.member });
      if (p.wizard) nav.current?.navigate('MemberWizard', { id: p.wizard, section: (p.section as SectionId | 'review') ?? 'basic' });
      if (p.addMember) nav.current?.navigate('Family', { openAdd: true });
      if (p.resetFamily) await useFamily.getState().reset();
      if (p.sheet === 'chat') st.openChat(p.thread ?? 'home');
      else if (p.sheet === 'today' || p.sheet === 'needs' || p.sheet === 'profile') st.openSheet(p.sheet);
      const cmd: Record<string, string> = {};
      for (const k of ['dash', 'walk', 'perf', 'dbg', 'low']) if (p[k]) cmd[k] = p[k];
      if (Object.keys(cmd).length) st.setDevCommand(cmd);
    };
    const sub = Linking.addEventListener('url', handle);
    void Linking.getInitialURL().then((u) => {
      if (u) void handle({ url: u });
    });
    // Opt-in remote control for scripted checks (iOS asks before opening every
    // external URL, which a headless simulator cannot answer): start Metro with
    // EXPO_PUBLIC_DEV_REMOTE=1 and serve {"id": n, "q": "<query>"} at :8099/cmd.
    let poll: ReturnType<typeof setInterval> | undefined;
    if (process.env.EXPO_PUBLIC_DEV_REMOTE === '1') {
      let last = -1;
      poll = setInterval(() => {
        fetch('http://localhost:8099/cmd')
          .then((r) => r.json())
          .then((c: { id: number; q: string }) => {
            if (c.id === last) return;
            const first = last === -1;
            last = c.id;
            if (!first) void handle({ url: `familyos://dev?${c.q}` });
          })
          .catch(() => undefined);
      }, 700);
    }
    return () => {
      sub.remove();
      if (poll) clearInterval(poll);
    };
  }, [nav]);
}
