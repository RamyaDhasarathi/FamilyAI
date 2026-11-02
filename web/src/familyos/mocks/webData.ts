// Web-only copy (AGENT_WEB.md §10): keyboard shortcuts, page titles and meta
// descriptions, empty states, and labels for mouse and keyboard. Everything
// the mobile app also shows lives in data.ts and is NOT repeated here.
import type { AgentId } from '../theme/tokens';
import { agentNames, copy, NAMES } from './data';

export interface Shortcut {
  keys: string[];
  label: string;
  devOnly?: boolean;
}

export const shortcuts: Shortcut[] = [
  { keys: ['/'], label: 'Ask FamilyOS' },
  { keys: ['T'], label: "Today's summary (Read) or play it (Listen)" },
  { keys: ['N'], label: 'Needs you' },
  { keys: ['D'], label: 'Your agents (dashboard)' },
  { keys: ['1', '–', '5'], label: 'Open Finance, Education, Household, Grocery, Calendar' },
  { keys: ['J', 'K'], label: 'Move between cards in Needs you' },
  { keys: ['Enter'], label: 'Run the card’s main action' },
  { keys: ['L'], label: 'Later (snooze the focused card)' },
  { keys: ['Esc'], label: 'Close the top panel, stop the summary, or go back' },
  { keys: ['?'], label: 'Show these shortcuts' },
  { keys: ['Shift', 'S'], label: 'Cycle the demo scenario', devOnly: true },
];

export const pageMeta = {
  home: { title: 'FamilyOS', description: 'Your family’s agents for money, school, home, calendar and groceries, in one calm place.' },
  login: { title: 'Log in · FamilyOS', description: 'Log in to your family pod.' },
  signup: { title: 'Create your account · FamilyOS', description: 'Create a FamilyOS account and set up your family pod.' },
  otp: { title: 'Enter your code · FamilyOS', description: 'Enter the one-time code we sent you.' },
  loading: { title: 'FamilyOS', description: 'Waking up your agents.' },
  settings: { title: 'Settings · FamilyOS', description: 'Summary, graphics, privacy and account settings.' },
  family: { title: 'Family · FamilyOS', description: 'Everyone in your family pod.' },
  agent: (a: AgentId) => ({ title: `${agentNames[a]} · FamilyOS`, description: `What your ${agentNames[a]} agent did and what is next.` }),
  member: (name: string) => ({ title: `${name} · FamilyOS`, description: `${name}’s details.` }),
  placeholder: (t: string) => ({ title: `${t} · FamilyOS`, description: copy.placeholder(t) }),
  notFound: { title: 'Not found · FamilyOS', description: 'This page does not exist.' },
};

export const webCopy = {
  skip: 'Skip to content',
  slashHint: '/',
  dashHandle: 'Your agents',
  core: {
    label: "Family core. Click to wobble, drag to spin, press and hold or press Enter to hear today's summary.",
    stopLabel: copy.core.stopLabel,
  },
  satellite: {
    hint: 'Click to hear its summary · Hold to open',
    a11y: (agent: string, n: number) =>
      `${agent} agent${n ? `, ${n} ${n === 1 ? 'item needs' : 'items need'} you` : ''}. Enter plays its summary, Shift+Enter opens it.`,
  },
  swipeHintDone: 'Done',
  swipeHintLater: 'Later',
  help: { title: 'Keyboard shortcuts', close: copy.close, note: 'Shortcuts are ignored while you type in a field.' },
  speechUnavailable: 'This browser can’t read aloud, so the summary plays silently.',
  webglFallback: 'Showing a still crystal: this browser can’t draw the live one.',
  notFound: { title: 'Nothing here', body: 'This page drifted out of orbit.', home: 'Back to Home' },
  emptyNeeds: 'Nothing needs you right now.',
  emptyToday: 'Nothing else is planned for today.',
  emptyChat: 'Ask about money, school, home, the calendar or groceries.',
  backHome: 'Back to Home',
  back: 'Back',
  more: 'More options',
  signup: {
    title: 'Create your account',
    subtitle: 'Set up your family pod in a minute',
    fullName: 'Full name',
    email: 'Email',
    mobile: 'Mobile',
    dob: 'Date of birth',
    password: 'Password',
    podName: 'Pod name (optional)',
    podHint: `For example: The ${NAMES.me}s`,
    terms: 'I agree to the terms and the privacy notice',
    submit: 'Create account',
    haveAccount: 'Already have an account?',
    login: 'Log in',
    strength: ['Too short', 'Weak', 'Fair', 'Good', 'Strong'],
    ownerAge: 'The pod owner must be 18 or older',
    note: copy.login.note,
    noteServer: 'Development sign-up: no email is sent.',
  },
  otp: {
    title: 'Enter your code',
    subtitle: (to: string) => `We sent a 6-digit code to ${to}.`,
    verify: 'Verify',
    resendIn: (s: number) => `Resend code in ${s}s`,
    resend: 'Resend code',
    resent: 'A new code is on its way',
    change: 'Change number',
    note: 'Prototype: any six digits work.',
    invalid: 'Enter all six digits',
  },
  noAccount: 'New to FamilyOS?',
  // Google came back without a session (services/landing.ts).
  signinSaid: { cancelled: 'Google sign-in was cancelled.', failed: 'Google sign-in did not work. Try again.' },
  googleOff: "Google sign-in isn't set up on this server yet.",
  createAccount: 'Create an account',
};
