// Region-specific formats, validation and masking for family details
// (AGENT_CORE_AND_FAMILY.md §4.8, design.md §13.6). The active region is
// REGION in mocks/data.ts.
import { CURRENCY, REGION } from '../mocks/data';

export type Region = 'IN' | 'US';
export const region: Region = REGION;

export const digits = (s: string) => s.replace(/\D/g, '');

export const US_STATES = [
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware', 'District of Columbia',
  'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine',
  'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
  'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
  'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia',
  'Washington', 'West Virginia', 'Wisconsin', 'Wyoming',
];

export const IN_STATES = [
  'Andaman and Nicobar Islands', 'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chandigarh', 'Chhattisgarh',
  'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir',
  'Jharkhand', 'Karnataka', 'Kerala', 'Ladakh', 'Lakshadweep', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya',
  'Mizoram', 'Nagaland', 'Odisha', 'Puducherry', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
  'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
];

export const STATES = region === 'IN' ? IN_STATES : US_STATES;

/** Two-letter postal codes, for short summaries ("Austin, TX"). */
const US_ABBR: Record<string, string> = {
  Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA', Colorado: 'CO', Connecticut: 'CT',
  Delaware: 'DE', 'District of Columbia': 'DC', Florida: 'FL', Georgia: 'GA', Hawaii: 'HI', Idaho: 'ID', Illinois: 'IL',
  Indiana: 'IN', Iowa: 'IA', Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA', Maine: 'ME', Maryland: 'MD', Massachusetts: 'MA',
  Michigan: 'MI', Minnesota: 'MN', Mississippi: 'MS', Missouri: 'MO', Montana: 'MT', Nebraska: 'NE', Nevada: 'NV',
  'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC',
  'North Dakota': 'ND', Ohio: 'OH', Oklahoma: 'OK', Oregon: 'OR', Pennsylvania: 'PA', 'Rhode Island': 'RI',
  'South Carolina': 'SC', 'South Dakota': 'SD', Tennessee: 'TN', Texas: 'TX', Utah: 'UT', Vermont: 'VT', Virginia: 'VA',
  Washington: 'WA', 'West Virginia': 'WV', Wisconsin: 'WI', Wyoming: 'WY',
};
export const stateShort = (s: string) => (region === 'US' ? US_ABBR[s] ?? s : s);

// ── Validation (each returns an error message or null) ─────────────────────

type Check = (v: string) => string | null;

export const checks = {
  email: ((v) => (/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()) ? null : 'Enter an email like name@example.com')) as Check,
  mobile: ((v) => {
    const d = digits(v);
    if (region === 'IN') return /^[6-9]\d{9}$/.test(d) ? null : 'Enter a 10-digit mobile number starting with 6–9';
    return /^\d{10}$/.test(d) ? null : 'Enter a 10-digit phone number, like (555) 123-4567';
  }) as Check,
  postcode: ((v) => {
    if (region === 'IN') return /^\d{6}$/.test(v.trim()) ? null : 'PIN codes have 6 digits';
    return /^\d{5}(-\d{4})?$/.test(v.trim()) ? null : 'Enter a 5-digit ZIP code (or ZIP+4)';
  }) as Check,
  aadhaar: ((v) => (/^\d{12}$/.test(digits(v)) ? null : 'Aadhaar numbers have 12 digits')) as Check,
  pan: ((v) => (/^[A-Z]{5}\d{4}[A-Z]$/.test(v) ? null : 'PAN looks like ABCDE1234F')) as Check,
  voterId: ((v) => (/^[A-Z]{3}\d{7}$/.test(v) ? null : 'Voter ID looks like ABC1234567')) as Check,
  passport: ((v) =>
    region === 'IN'
      ? /^[A-Z]\d{7}$/.test(v)
        ? null
        : 'Passport numbers look like A1234567'
      : /^[A-Z0-9]{9}$/.test(v)
        ? null
        : 'US passport numbers have 9 letters or digits') as Check,
  licence: ((v) => (/^[A-Z0-9-]{5,20}$/.test(v) ? null : 'Use letters and digits only')) as Check,
  ifsc: ((v) => (/^[A-Z]{4}0[A-Z0-9]{6}$/.test(v) ? null : 'IFSC looks like HDFC0001234')) as Check,
  upi: ((v) => (/^[a-zA-Z0-9._-]{2,256}@[a-zA-Z]{2,64}$/.test(v.trim()) ? null : 'UPI IDs look like name@bank')) as Check,
  last4: ((v) => (/^\d{4}$/.test(v) ? null : 'Enter the last 4 digits only')) as Check,
  routing: ((v) => {
    const d = digits(v);
    if (!/^\d{9}$/.test(d)) return 'Routing numbers have 9 digits';
    // ABA checksum: 3·(d1+d4+d7) + 7·(d2+d5+d8) + (d3+d6+d9) ≡ 0 (mod 10).
    const n = d.split('').map(Number);
    const sum = 3 * (n[0] + n[3] + n[6]) + 7 * (n[1] + n[4] + n[7]) + (n[2] + n[5] + n[8]);
    return sum % 10 === 0 ? null : 'That routing number doesn’t look right';
  }) as Check,
  account: ((v) => {
    const d = digits(v);
    if (region === 'IN') return /^\d{9,18}$/.test(d) ? null : 'Account numbers have 9–18 digits';
    return /^\d{4,17}$/.test(d) ? null : 'Account numbers have 4–17 digits';
  }) as Check,
  money: ((v) => (/^\d+(\.\d{1,2})?$/.test(v.trim()) ? null : 'Enter an amount, like 250')) as Check,
  weight: ((v) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 && n < 700 ? null : 'Enter a weight';
  }) as Check,
};

// ── As-you-type formatting ─────────────────────────────────────────────────

export const formatters = {
  /** (555) 123-4567 in the US, 98765 43210 in India. */
  phone(v: string) {
    const d = digits(v).slice(0, 10);
    if (region === 'IN') return d.length > 5 ? `${d.slice(0, 5)} ${d.slice(5)}` : d;
    if (d.length <= 3) return d;
    if (d.length <= 6) return `(${d.slice(0, 3)}) ${d.slice(3)}`;
    return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;
  },
  aadhaar(v: string) {
    const d = digits(v).slice(0, 12);
    return d.replace(/(\d{4})(?=\d)/g, '$1 ');
  },
  upper(v: string) {
    return v.toUpperCase().replace(/\s/g, '');
  },
  digits(max: number) {
    return (v: string) => digits(v).slice(0, max);
  },
  money(v: string) {
    const clean = v.replace(/[^\d.]/g, '');
    const [a, b] = clean.split('.');
    return b === undefined ? a : `${a}.${b.slice(0, 2)}`;
  },
  zip(v: string) {
    if (region === 'IN') return digits(v).slice(0, 6);
    const d = digits(v).slice(0, 9);
    return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
  },
};

// ── Masks shown whenever a field isn't focused ─────────────────────────────

export const maskers = {
  /** XXXX XXXX 0193 */
  aadhaar: (v: string) => {
    const d = digits(v);
    return d.length > 4 ? `XXXX XXXX ${d.slice(-4)}` : d;
  },
  /** ••••••••6789 */
  tail: (v: string) => {
    const s = v.replace(/\s/g, '');
    return s.length > 4 ? `${'•'.repeat(Math.min(8, s.length - 4))}${s.slice(-4)}` : s;
  },
  /** Mobile ••••••4417 */
  phone: (v: string) => {
    const d = digits(v);
    return d.length > 4 ? `${'•'.repeat(6)}${d.slice(-4)}` : d;
  },
};

export const phonePrefix = region === 'IN' ? '+91' : '+1';
export const postcodeLabel = region === 'IN' ? 'PIN code' : 'ZIP code';
export const currency = CURRENCY;
export const weightUnit = region === 'IN' ? 'kg' : 'lb';
