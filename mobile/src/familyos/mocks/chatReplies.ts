// Canned chat replies chosen by keyword (AGENT.md §8.6, §10). The real
// backend replaces this with the agent's answer.
import type { AgentId } from '../theme/tokens';
import type { Scenario } from '../theme/stateThemes';
import { CURRENCY as C, NAMES, agentNames } from './data';

interface Context {
  scenario: Scenario;
  openCount: number;
  topText?: string;
}

type Rule = [RegExp, string | ((ctx: Context) => string)];

const TELL_ME_MORE = 'Here is what I did and why. Nothing else changed, and you can undo it from this page at any time.';

const rules: Record<'home' | AgentId, Rule[]> = {
  home: [
    [
      /need(s)? me|needs you|today\?/i,
      (ctx) =>
        ctx.openCount === 0
          ? 'Nothing needs you right now.'
          : `${ctx.openCount} ${ctx.openCount === 1 ? 'thing needs' : 'things need'} you. First up: ${ctx.topText ?? ''}`,
    ],
    [/money|finance|budget|doing on/i, `Finance is on track. Reserve is ${C}12,450, up 4.2% this month.`],
    [/dinner|grocer|food|cart/i, "Got it. I'll check with the right agent and update you here."],
  ],
  finance: [
    [/bill/i, `Next up: the mortgage, ${C}2,150 on Oct 28, and car insurance, ${C}184 on Nov 2. Both are covered by checking.`],
    [/saving|move/i, `I can move ${C}500 to savings today. It keeps checking above your ${C}4,000 buffer. Want me to do it?`],
    [/saved/i, `Since September I've saved you ${C}620: ${C}120 a month on ${NAMES.son}'s coaching, an ${C}85 refund on a duplicate charge, and ${C}25 in late fees avoided.`],
  ],
  calendar: [
    [/move|2 pm/i, 'I can move your client call to 3:30 pm. Everyone on the invite is free. Want me to send the update?'],
    [/today|on today/i, `You have 3 events today: the dentist at 9:30 am, your client call at 2 pm and ${NAMES.son}'s final at 2 pm. The call and the final overlap.`],
    [/free|slot/i, "You're free Thursday from 1 to 3:30 pm. Want me to hold it?"],
  ],
  grocery: [
    [/cart|what's in/i, `14 items, ${C}86.40: milk, eggs, bread, fruit, pasta, sauce and the usual snacks. Delivery at 6:00 pm.`],
    [/add|milk/i, `Added a gallon of milk. The cart is now 15 items, ${C}90.10.`],
    [/deliver|when/i, 'Delivery is booked for today at 6:00 pm. I will tell you when the driver is close.'],
  ],
  education: [
    [/how is|doing/i, `${NAMES.son} is ahead in math this month, and his final is tomorrow. I shared a short study plan.`],
    [/due|week/i, `Three things: ${NAMES.son}'s field trip form on Wednesday, ${NAMES.daughter}'s science project on Friday, and a reading log on Monday.`],
    [/tutor/i, 'I found two math tutors free this weekend, both rated 4.8 or higher. Want me to book one?'],
  ],
  household: [
    [/electrician|coming/i, 'The electrician arrives at 4 pm to fix the hallway circuit. I approved the quote within your limit.'],
    [/clean/i, 'A cleaner is free Saturday at 10 am for 3 hours. Want me to book it?'],
    [/alert|sensor/i, 'All home sensors are steady right now. The furnace service is booked for Nov 9.'],
  ],
};

const fallback: Record<'home' | AgentId, string> = {
  home: 'I can help with money, school, home, the calendar and groceries. Try asking about one of those.',
  finance: 'I can check bills, savings and spending. Try "Show upcoming bills".',
  calendar: 'I can check your day, move events or find free time.',
  grocery: 'I can check your cart, add items or change the delivery time.',
  education: 'I can check grades, deadlines and school events.',
  household: 'I can check visits, bookings and home sensors.',
};

export function greetingFor(thread: string, name: string): string {
  if (thread === 'home') return `Hi ${name}. Ask me anything about the family: money, school, home, calendar or groceries.`;
  return `Hi ${name}. Ask me anything about ${agentNames[thread as AgentId].toLowerCase()}.`;
}

export function suggestionsFor(thread: string): string[] {
  if (thread === 'home') return ['What needs me today?', 'How are we doing on money?', "What's for dinner groceries?"];
  return [];
}

export function replyTo(thread: string, text: string, ctx: Context): string {
  if (/^tell me more about/i.test(text.trim())) return TELL_ME_MORE;
  const key = (thread in rules ? thread : 'home') as 'home' | AgentId;
  for (const [re, reply] of rules[key]) {
    if (re.test(text)) return typeof reply === 'function' ? reply(ctx) : reply;
  }
  return fallback[key];
}
