// Demo family seeded on a fresh install or "Reset demo family"
// (AGENT_CORE_AND_FAMILY.md §4.3). Names and ages come from FAMILY_SEED in
// data.ts; statuses are mixed so the amber "needs update" states show at once:
// Michael complete, Sarah banking, Ethan IDs, Mia complete, Linda IDs + banking.
// All numbers are made up.
import type { FamilyMember, SectionId, SectionStatus } from '../services/interfaces';
import { emptySections, isoDate } from '../family/model';
import { region } from '../family/region';
import { FAMILY_SEED } from './data';

const R = <T,>(us: T, inn: T): T => (region === 'IN' ? inn : us);

/** A date of birth that makes `age` today (birthday fixed per member). */
function dobFor(age: number, month: number, day: number) {
  const now = new Date();
  const d = new Date(now.getFullYear() - age, month - 1, day);
  if (d > new Date(now.getFullYear() - age, now.getMonth(), now.getDate())) d.setFullYear(d.getFullYear() - 1);
  return isoDate(d);
}

const ADDRESS = R(
  { address: '1408 Oak Hollow Drive', area: '', city: 'Austin', postcode: '78704', state: 'Texas' },
  { address: '14, 2nd Cross, Indiranagar', area: 'HAL 2nd Stage', city: 'Bengaluru', postcode: '560038', state: 'Karnataka' }
);
const phone = (d: string) => R(`(512) 555-${d}`, `98450 1${d}`);

type SeedSections = Partial<Record<SectionId, { status: SectionStatus; data: Record<string, unknown> }>>;

function sectionsFor(key: string, ownerId: string): SeedSections {
  const done = (data: Record<string, unknown>) => ({ status: 'complete' as const, data });
  const todo = (data: Record<string, unknown>) => ({ status: 'needsUpdate' as const, data });
  const adultIds = (n: string, pan: string, passport: string) =>
    R(
      { licence: `TX${n}`, licenceState: 'Texas', passport, passportExpiry: '2031-04-12', ssnLast4: n.slice(-4), authorised: true, documents: [] },
      { aadhaar: `4521 8830 ${n.slice(-4)}`, pan, passport, passportExpiry: '2031-04-12', authorised: true, documents: [] }
    );
  const bank = (holder: string, acct: string) =>
    R(
      { bank: 'Chase', holder, routing: '111000614', account: acct, cards: [{ nickname: 'Everyday', network: 'Visa', last4: '4417' }], autopay: ['Utilities', 'Insurance'], approvalLimit: '500' },
      { bank: 'HDFC Bank', holder, account: acct, ifsc: 'HDFC0001234', upi: 'michael@okhdfc', cards: [{ nickname: 'Everyday', network: 'Visa', last4: '4417' }], autopay: ['Utilities', 'Insurance'], approvalLimit: '20000' }
    );
  const contact = (mobile: string, email: string, same: boolean) => ({ mobile: phone(mobile), email, sameAddress: same, ...(same ? {} : ADDRESS) });
  switch (key) {
    case 'michael':
      return {
        basic: done({ gender: 'Male', occupation: 'Product manager', languages: 'English' }),
        contact: done(contact('4417', 'michael@example.com', false)),
        ids: done(adultIds('48120193', 'AFKPC4821Q', R('P41827365', 'K4182736'))),
        health: done({ bloodGroup: 'O+', weight: R('176', '80'), allergies: 'None', medicines: [], emergencyName: 'Sarah Carter', emergencyMobile: phone('2210') }),
        banking: done(bank('Michael Carter', '000123456789')),
      };
    case 'sarah':
      return {
        basic: done({ gender: 'Female', occupation: 'Architect', languages: 'English, French' }),
        contact: done(contact('2210', 'sarah@example.com', true)),
        ids: done(adultIds('77341208', 'BQRPC7734L', R('P77341208', 'M7734120'))),
        health: done({ bloodGroup: 'A+', allergies: 'Penicillin', medicines: [], emergencyName: 'Michael Carter', emergencyMobile: phone('4417') }),
        banking: todo({ bank: R('Chase', 'HDFC Bank'), holder: 'Sarah Carter' }),
      };
    case 'ethan':
      return {
        basic: done({ gender: 'Male', school: 'Lakeside High', grade: '11', languages: 'English, Spanish' }),
        contact: done(contact('3391', 'ethan@example.com', true)),
        ids: todo(R({ ssnLast4: '' }, { aadhaar: '' })),
        health: done({ bloodGroup: 'O+', allergies: 'Peanuts', medicines: [], emergencyName: 'Michael Carter', emergencyMobile: phone('4417'), vaccinations: true }),
        banking: done({ weeklyAllowance: R('20', '500'), paidFrom: ownerId, approvalThreshold: R('40', '1000'), blocked: ['In-app purchases'] }),
      };
    case 'mia':
      return {
        basic: done({ gender: 'Female', school: 'Riverside Elementary', grade: '5', languages: 'English' }),
        contact: done(contact('', '', true)),
        ids: done(R({ passport: 'P93120455', passportExpiry: '2030-08-01', authorised: true, documents: [] }, { aadhaar: '6612 0934 0193', authorised: true, documents: [] })),
        health: done({ bloodGroup: 'A+', allergies: 'None', medicines: [], emergencyName: 'Sarah Carter', emergencyMobile: phone('2210'), vaccinations: true }),
        banking: done({ weeklyAllowance: R('10', '200'), paidFrom: ownerId, approvalThreshold: R('15', '300'), blocked: ['Games', 'In-app purchases'] }),
      };
    case 'linda':
      return {
        basic: done({ gender: 'Female', occupation: 'Retired teacher', languages: 'English' }),
        contact: done(contact('7720', 'linda@example.com', false)),
        ids: todo(R({ passport: '' }, { pan: '' })),
        health: done({ bloodGroup: 'B+', conditions: 'Type 2 diabetes', medicines: [{ name: 'Metformin', dose: '500 mg', when: 'Twice daily' }], emergencyName: 'Michael Carter', emergencyMobile: phone('4417') }),
        banking: todo({}),
      };
    default:
      return {};
  }
}

const BIRTHDAYS: Record<string, [number, number]> = {
  michael: [3, 14], sarah: [7, 2], ethan: [1, 23], mia: [9, 9], linda: [5, 30],
};

export function seedFamily(): FamilyMember[] {
  const now = new Date().toISOString();
  const ownerId = 'm_michael';
  return FAMILY_SEED.map((s) => {
    const [mo, day] = BIRTHDAYS[s.key] ?? [6, 15];
    const sections = { ...emptySections(), ...sectionsFor(s.key, ownerId) };
    return {
      id: `m_${s.key}`,
      isOwner: s.relationship === 'Self',
      fullName: s.fullName,
      relationship: s.relationship,
      dateOfBirth: dobFor(s.age, mo, day),
      sections,
      createdAt: now,
      updatedAt: now,
    };
  });
}
