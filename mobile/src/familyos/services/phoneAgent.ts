// The phone agent's loop (ported from Mobile-UI-Agent's AgentScreen): look at the screen, ask our backend for the one next
// action (familyos/collect/phone_agent.py, Claude or the local MAI-UI, checked there), do it, wait for the screen, again.
// It reads one app the person switched on and never buys, sends or changes anything -- the backend refuses that before
// the phone ever gets it. Waits are native (JS timers stop while FamilyOS is in the background, where this runs).
// Coming back to FamilyOS during a run stops it; at the end FamilyOS comes back by itself.
import { AppState } from 'react-native';
import * as Native from '../../../modules/familyos-collect';
import { ApiError, request } from './api';

export interface PhoneRun {
  run_id: string;
  package: string;
  label: string;
  task: string;
  model: string;
  status: 'running' | 'done' | 'needs_sign_in' | 'stopped';
  note: string;
  steps: number;
  kept: number;
  cost_usd: number;
  fallback: string | null;
}
type StepReply = PhoneRun & { action: Native.AgentAction };

export interface AppItem {
  id: string;
  title: string;
  amount: string | null;
  status: string | null;
  happened: string | null;
}

const MAX_LOOPS = 40;
// The backend out of reach for a moment (Wi-Fi, or the USB link while testing): ask again rather than end the run.
const UNREACHABLE_TRIES = 10;
const UNREACHABLE_WAIT_MS = 3000;

async function patiently<T>(call: () => Promise<T>): Promise<T> {
  for (let i = 1; ; i += 1) {
    try {
      return await call();
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 0) || i >= UNREACHABLE_TRIES) throw e;
      await Native.settle(UNREACHABLE_WAIT_MS); // native: JS timers stop while FamilyOS is in the background
    }
  }
}

export const canRunAgent = Native.canCollect;
export const agentAllowed = () => Native.agentAccess();
export const openAgentSettings = () => Native.openAccessibilitySettings();

/** What an action is, in a few words, for the progress line. */
export function said(a: Native.AgentAction): string {
  const target = a.target as { description?: string } | undefined;
  switch (a.action) {
    case 'tap':
      return target?.description ? `Tapping “${target.description}”` : 'Tapping';
    case 'swipe':
      return 'Scrolling';
    case 'type':
      return `Typing “${String(a.text ?? '')}”`;
    case 'launch_app':
      return 'Opening the app';
    case 'press_back':
      return 'Going back';
    case 'wait':
      return 'Waiting for the screen';
    case 'done':
      return 'Finished';
    default:
      return a.action;
  }
}

/** engine: 'claude' (Claude decides each step) or 'local' (Qwen3.5 plans, MAI-UI taps, on the Mac running FamilyOS). */
export type Engine = 'claude' | 'local';

export async function runPhoneAgent(pkg: string, onStep: (run: PhoneRun, doing: string) => void, engine: Engine = 'claude'): Promise<PhoneRun> {
  let run = await request<PhoneRun>('POST', '/collect/phone/runs', { package: pkg, engine });
  let left = false;
  let stopping = false;
  const sub = AppState.addEventListener('change', (state) => {
    if (state === 'background') left = true;
    else if (state === 'active' && left) stopping = true;     // the person came back: stop
  });
  try {
    for (let i = 0; i < MAX_LOOPS; i += 1) {
      if (stopping) {
        run = await patiently(() => request<PhoneRun>('POST', `/collect/phone/runs/${run.run_id}/stop`));
        break;
      }
      const screen = await Native.observe();
      const reply = await patiently(() => request<StepReply>('POST', `/collect/phone/runs/${run.run_id}/step`, screen));
      run = reply;
      onStep(reply, said(reply.action));
      if (reply.status !== 'running' || reply.action.action === 'done') break;
      await Native.act(reply.action);
      await Native.settle(reply.action.action === 'launch_app' ? 2500 : 900);
    }
  } finally {
    sub.remove();
    if (left && !stopping) Native.bringToFront();
  }
  return run;
}

export const appItems = (pkg: string) =>
  request<{ items: AppItem[]; last_run: { finished_at: string; counts: { kept?: number; cost_usd?: number; model?: string }; errors: { outcome?: string; note?: string } } | null }>(
    'GET',
    `/collect/apps/${encodeURIComponent(pkg)}/items`,
  );
