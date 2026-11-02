// The desk dataset (MASTER_AGENT.md §9): one coherent Carter household for
// every desktop phase, built relative to the moment the app loads, in the
// household's timezone, so "today" always has something in it.
//
// Built from the mobile mocks (mocks/data.ts, unchanged): the electrician at
// 4 pm, the reserve at $12,450 (+4.2%), the cart of 14 items for $86.40 with
// delivery at 6 pm, the $2,150 mortgage, the furnace service, Mia's recital
// on Saturday at 2 pm, the dentist at 9:30 am, Ms. Alvarez, the card ending
// 4417, the commute and weather lines.
//
// Where the mobile mocks disagree with each other, this dataset chooses:
//  • Ethan's math final is TOMORROW at 2 pm (Today sheet: "is tomorrow").
//    Today carries a reminder created this morning ("Reminder · tomorrow").
//  • The 2 pm clash (needs-you n1, Calendar timeline) is therefore TOMORROW:
//    Michael's client call vs. the final, where Michael drives Ethan for a
//    1:45 pm drop-off. "Fix for me" proposes moving the call to 3:30 pm
//    (needs-you n1's "Move call to 3:30"); it waits for Confirm.
//  • The mortgage "due Oct 28" (the recording's date) is due TODAY.
//  • The furnace "Nov 9" is 12 days out; the conference "Nov 6" is 9 days
//    out; car insurance "renews Nov 2" is 5 days out.
//  • The dentist is TOMORROW at 9:30 am (needs-you n5, Today sheet's first
//    event); Calendar's "3 events today" are Linda's physical therapy, Mia's
//    rehearsal and Ethan's soccer practice.
//  • "Saturday" (recital) and "Friday" (science project) are the next ones
//    strictly after today.
// All names, senders and addresses are fictional (`.example` domains).
import { localTimeZone } from './format';
import type { DeskData } from './types';
import { makeCtx } from './seed/ctx';
import {
  seedChildren, seedConsents, seedMailboxes, seedMembers, seedSettings, seedSpaces, seedTelegram, seedToggles, seedTokens, seedWatchers, seedWeather,
} from './seed/people';
import { seedNotices, seedQuarantine } from './seed/notices';
import { seedAgenda, seedConflicts, seedProposals, seedTodos } from './seed/day';
import { seedOrderAgain, seedPlans, seedRecurring, seedStatements } from './seed/money';
import { seedAudit, seedErrands, seedRevisions } from './seed/admin';

export { ID as MEMBER_IDS } from './seed/people';

/** A fresh copy of the whole household, dated around `now` in `tz`. */
export function buildDeskData(now: Date = new Date(), tz: string = localTimeZone()): DeskData {
  const c = makeCtx(now, tz);
  return {
    settings: seedSettings(tz),
    members: seedMembers(),
    children: seedChildren(),
    spaces: seedSpaces(),
    notices: seedNotices(c),
    quarantine: seedQuarantine(c),
    proposals: seedProposals(c),
    agenda: seedAgenda(c),
    todos: seedTodos(c),
    conflicts: seedConflicts(c),
    errands: seedErrands(c),
    plans: seedPlans(c),
    recurring: seedRecurring(c),
    statements: seedStatements(c),
    orderAgain: seedOrderAgain(c),
    revisions: seedRevisions(c),
    audit: seedAudit(c),
    mailboxes: seedMailboxes(c),
    phoneTokens: seedTokens(c),
    watchers: seedWatchers(c),
    toggles: seedToggles(),
    consents: seedConsents(c),
    telegram: seedTelegram(c),
    sittings: [],
    weather: seedWeather(),
  };
}
