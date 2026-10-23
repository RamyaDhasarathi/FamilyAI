// Field definitions for each details section (design.md §13.6 with the
// region rules of AGENT_CORE_AND_FAMILY.md §4.8). The wizard renders these,
// validates them, and builds the masked one-line summaries from them.
import type { FamilyMember, SectionId } from '../services/interfaces';
import { CURRENCY } from '../mocks/data';
import { type AgeGroup, RELATIONSHIPS, dateFromIso, isoDate } from './model';
import { checks, formatters, maskers, postcodeLabel, region, STATES, weightUnit } from './region';

export type FieldType =
  | 'text' | 'date' | 'choice' | 'multi' | 'toggle' | 'select' | 'files' | 'list' | 'adult';

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean;
  hint?: string;
  keyboard?: 'default' | 'number-pad' | 'decimal-pad' | 'email-address' | 'phone-pad';
  /** Prefix shown inside the field (+1, $). */
  prefix?: string;
  /** As-you-type formatting. */
  format?: (v: string) => string;
  /** Shown instead of the value whenever the field isn't focused. */
  mask?: (v: string) => string;
  validate?: (v: string) => string | null;
  options?: string[];
  /** Document kinds for a 'files' field. */
  kinds?: string[];
  /** Columns of a 'list' field (medicines, saved cards). */
  columns?: FieldDef[];
  /** Date limits for a 'date' field. */
  minDate?: () => Date;
  maxDate?: () => Date;
  /** Bound to a top-level member field instead of the section data. */
  basics?: 'fullName' | 'preferredName' | 'relationship' | 'relationshipOther' | 'dateOfBirth';
  /** Only shown when this returns true (e.g. address fields when not "same address"). */
  when?: (data: Record<string, unknown>, member: FamilyMember) => boolean;
}

const yearsAgo = (n: number) => {
  const d = new Date();
  d.setFullYear(d.getFullYear() - n);
  return d;
};
const today = () => new Date();

const nameCheck = (v: string) =>
  /^[\p{L} .'-]{2,60}$/u.test(v.trim()) ? null : 'Use 2–60 letters, spaces or . \' -';

const phoneField = (key: string, label: string, required: boolean): FieldDef => ({
  key, label, type: 'text', required, keyboard: 'phone-pad', prefix: region === 'IN' ? '+91' : '+1',
  format: formatters.phone, validate: checks.mobile,
});

// ── Basic information ─────────────────────────────────────────────────────

function basic(group: AgeGroup, member: FamilyMember): FieldDef[] {
  const f: FieldDef[] = [
    { key: 'fullName', basics: 'fullName', label: 'Full name', type: 'text', required: true, validate: nameCheck },
    { key: 'preferredName', basics: 'preferredName', label: 'Preferred name', type: 'text' },
  ];
  if (!member.isOwner) {
    f.push(
      { key: 'relationship', basics: 'relationship', label: 'Relationship', type: 'choice', required: true, options: RELATIONSHIPS },
      {
        key: 'relationshipOther', basics: 'relationshipOther', label: 'Relationship (other)', type: 'text', required: true,
        when: (_d, m) => m.relationship === 'Other',
      }
    );
  }
  f.push(
    {
      key: 'dateOfBirth', basics: 'dateOfBirth', label: 'Date of birth', type: 'date', required: true,
      maxDate: today, minDate: () => yearsAgo(120),
    },
    { key: 'gender', label: 'Gender', type: 'choice', required: true, options: ['Female', 'Male', 'Non-binary', 'Prefer not to say'] }
  );
  if (group === 'adult') f.push({ key: 'occupation', label: 'Occupation', type: 'text' });
  else
    f.push(
      { key: 'school', label: 'School', type: 'text' },
      { key: 'grade', label: 'Grade', type: 'text', keyboard: 'default' }
    );
  f.push({ key: 'languages', label: 'Languages', type: 'text', hint: 'For example: English, Spanish' });
  return f;
}

// ── Contact and address ───────────────────────────────────────────────────

function contact(group: AgeGroup, age: number, member: FamilyMember): FieldDef[] {
  const notSame = (d: Record<string, unknown>) => !d.sameAddress;
  const f: FieldDef[] = [
    phoneField('mobile', 'Mobile', age >= 13),
    { key: 'email', label: 'Email', type: 'text', required: group === 'adult', keyboard: 'email-address', validate: checks.email },
  ];
  if (!member.isOwner) f.push({ key: 'sameAddress', label: 'Lives at the same address as you', type: 'toggle' });
  f.push(
    { key: 'address', label: 'Address line', type: 'text', required: true, when: notSame },
    { key: 'area', label: region === 'IN' ? 'Area / locality' : 'Apartment, suite (optional)', type: 'text', when: notSame },
    { key: 'city', label: 'City', type: 'text', required: true, when: notSame },
    {
      key: 'postcode', label: postcodeLabel, type: 'text', required: true, when: notSame, keyboard: 'number-pad',
      format: formatters.zip, validate: checks.postcode,
    },
    { key: 'state', label: 'State', type: 'select', required: true, options: STATES, when: notSame }
  );
  return f;
}

// ── Government ID and documents ───────────────────────────────────────────

function ids(group: AgeGroup): FieldDef[] {
  const upper = formatters.upper;
  const passport: FieldDef[] = [
    { key: 'passport', label: 'Passport number', type: 'text', format: upper, validate: checks.passport, mask: maskers.tail },
    {
      key: 'passportExpiry', label: 'Passport expiry', type: 'date', minDate: today, maxDate: () => yearsAgo(-15),
      when: (d) => !!d.passport,
    },
  ];
  const auth: FieldDef = {
    key: 'authorised', label: 'I’m authorised to keep these details for this person', type: 'toggle', required: true,
  };
  if (region === 'IN') {
    const aadhaar: FieldDef = {
      key: 'aadhaar', label: 'Aadhaar', type: 'text', required: true, keyboard: 'number-pad',
      format: formatters.aadhaar, validate: checks.aadhaar, mask: maskers.aadhaar,
    };
    if (group === 'adult')
      return [
        aadhaar,
        { key: 'pan', label: 'PAN', type: 'text', required: true, format: upper, validate: checks.pan, mask: maskers.tail },
        { key: 'voterId', label: 'Voter ID', type: 'text', format: upper, validate: checks.voterId, mask: maskers.tail },
        ...passport,
        { key: 'licence', label: 'Driving licence', type: 'text', format: upper, validate: checks.licence, mask: maskers.tail },
        { key: 'documents', label: 'Documents', type: 'files', kinds: ['Aadhaar', 'PAN', 'Passport', 'Driving licence'] },
        auth,
      ];
    return [
      aadhaar,
      ...passport,
      { key: 'documents', label: 'Documents', type: 'files', kinds: ['Aadhaar', 'Birth certificate', 'School ID', 'Passport'] },
      auth,
    ];
  }
  const ssn: FieldDef = {
    key: 'ssnLast4', label: 'SSN (last 4 digits only)', type: 'text', keyboard: 'number-pad',
    format: formatters.digits(4), validate: checks.last4, mask: () => '••••', hint: 'Never the full number',
  };
  if (group === 'adult')
    return [
      { key: 'licence', label: 'Driver’s licence number', type: 'text', format: upper, validate: checks.licence, mask: maskers.tail },
      { key: 'licenceState', label: 'Licence state', type: 'select', options: STATES, when: (d) => !!d.licence },
      ...passport,
      ssn,
      { key: 'documents', label: 'Documents', type: 'files', kinds: ['Driver’s licence', 'Passport'] },
      auth,
    ];
  return [
    ...passport,
    ssn,
    { key: 'documents', label: 'Documents', type: 'files', kinds: ['Birth certificate', 'School ID', 'Passport'] },
    auth,
  ];
}

// ── Health ────────────────────────────────────────────────────────────────

function health(group: AgeGroup): FieldDef[] {
  const f: FieldDef[] = [
    { key: 'bloodGroup', label: 'Blood group', type: 'choice', required: true, options: ['A+', 'A−', 'B+', 'B−', 'AB+', 'AB−', 'O+', 'O−', 'Not sure'] },
    { key: 'weight', label: `Weight (${weightUnit})`, type: 'text', keyboard: 'decimal-pad', format: formatters.money, validate: checks.weight },
    { key: 'allergies', label: 'Allergies', type: 'text' },
    { key: 'conditions', label: 'Ongoing conditions', type: 'text' },
    {
      key: 'medicines', label: 'Current medicines', type: 'list',
      columns: [
        { key: 'name', label: 'Medicine', type: 'text' },
        { key: 'dose', label: 'Dose', type: 'text' },
        { key: 'when', label: 'When', type: 'text' },
      ],
    },
    { key: 'doctor', label: 'Family doctor', type: 'text' },
    { key: 'insurer', label: 'Insurer', type: 'text' },
    { key: 'policy', label: 'Policy number', type: 'text', format: formatters.upper, mask: maskers.tail },
    { key: 'emergencyName', label: 'Emergency contact name', type: 'text', required: true, validate: nameCheck },
    phoneField('emergencyMobile', 'Emergency contact mobile', true),
  ];
  if (group !== 'adult') f.push({ key: 'vaccinations', label: 'Vaccinations up to date', type: 'toggle' });
  return f;
}

// ── Banking and payments / Allowance and payments ─────────────────────────

function banking(group: AgeGroup, age: number): FieldDef[] {
  const money = (key: string, label: string): FieldDef => ({
    key, label, type: 'text', keyboard: 'decimal-pad', prefix: CURRENCY, format: formatters.money, validate: checks.money,
  });
  if (group !== 'adult') {
    const f: FieldDef[] = [
      money('weeklyAllowance', 'Weekly allowance'),
      { key: 'paidFrom', label: 'Paid from', type: 'adult', required: true },
    ];
    if (region === 'IN' && age >= 13) f.push({ key: 'upi', label: 'UPI ID', type: 'text', validate: checks.upi });
    f.push(
      money('approvalThreshold', 'Ask an adult above'),
      {
        key: 'blocked', label: 'Blocked categories', type: 'multi',
        options: ['Games', 'In-app purchases', 'Food delivery', 'Shopping', 'Streaming'],
      }
    );
    return f;
  }
  const digitsOnly = (max: number) => formatters.digits(max);
  const f: FieldDef[] = [
    { key: 'bank', label: region === 'IN' ? 'Bank' : 'Bank name', type: 'text', required: true },
    { key: 'holder', label: 'Account holder', type: 'text', required: true, validate: nameCheck },
  ];
  if (region === 'US')
    f.push({
      key: 'routing', label: 'Routing number', type: 'text', required: true, keyboard: 'number-pad',
      format: digitsOnly(9), validate: checks.routing,
    });
  f.push({
    key: 'account', label: 'Account number', type: 'text', required: true, keyboard: 'number-pad',
    format: digitsOnly(region === 'IN' ? 18 : 17), validate: checks.account, mask: maskers.tail,
  });
  if (region === 'IN')
    f.push(
      { key: 'ifsc', label: 'IFSC', type: 'text', required: true, format: formatters.upper, validate: checks.ifsc },
      { key: 'upi', label: 'UPI ID', type: 'text', validate: checks.upi }
    );
  f.push(
    {
      key: 'cards', label: 'Saved cards (last 4 digits only)', type: 'list',
      columns: [
        { key: 'nickname', label: 'Nickname', type: 'text' },
        { key: 'network', label: 'Network', type: 'choice', options: region === 'IN' ? ['Visa', 'Mastercard', 'RuPay', 'Amex'] : ['Visa', 'Mastercard', 'Amex', 'Discover'] },
        { key: 'last4', label: 'Last 4', type: 'text', keyboard: 'number-pad', format: digitsOnly(4), validate: checks.last4 },
      ],
    },
    {
      key: 'autopay', label: 'Auto-pay allowed for', type: 'multi',
      options: ['Utilities', 'School fees', 'Subscriptions', 'Insurance', region === 'IN' ? 'Rent / EMI' : 'Rent / mortgage'],
    },
    money('approvalLimit', 'Approval limit')
  );
  return f;
}

export function fieldsFor(section: SectionId, member: FamilyMember, age: number, group: AgeGroup): FieldDef[] {
  switch (section) {
    case 'basic':
      return basic(group, member);
    case 'contact':
      return contact(group, age, member);
    case 'ids':
      return ids(group);
    case 'health':
      return health(group);
    case 'banking':
      return banking(group, age);
  }
}

/** Value of a field for editing: basics fields come from the member, others from the section data. */
export function fieldValue(f: FieldDef, member: FamilyMember, data: Record<string, unknown>): unknown {
  return f.basics ? member[f.basics] : data[f.key];
}

export const isEmpty = (v: unknown) =>
  v === undefined || v === null || v === '' || v === false || (Array.isArray(v) && v.length === 0);

/** Validate one field; `null` = fine. */
export function validateField(f: FieldDef, v: unknown): string | null {
  if (isEmpty(v)) {
    if (!f.required) return null;
    if (f.type === 'toggle') return 'Please confirm to continue';
    if (f.type === 'choice' || f.type === 'select' || f.type === 'adult') return 'Choose one';
    return 'Required';
  }
  if (f.type === 'date' && typeof v === 'string') {
    const d = dateFromIso(v);
    if (f.maxDate && d > f.maxDate()) return f.key === 'dateOfBirth' ? 'Can’t be in the future' : 'That date is too far ahead';
    if (f.minDate && isoDate(d) < isoDate(f.minDate())) return f.key === 'passportExpiry' ? 'This passport has expired' : 'That date is too long ago';
  }
  if (f.type === 'list' && Array.isArray(v) && f.columns) {
    for (const row of v as Record<string, string>[])
      for (const c of f.columns) {
        const e = c.validate && row[c.key] ? c.validate(String(row[c.key])) : null;
        if (e) return `${c.label}: ${e}`;
      }
  }
  if (typeof v === 'string' && f.validate) return f.validate(v);
  return null;
}
