// Inbox, setup (MASTER_AGENT.md §7 Phase 3; FamilyOS.mp4 3:55–4:10, frames
// f_048–f_050): the family address (Copy / Choose a name; strangers wait in
// Quarantine), Where we live (country · timezone · currency — Change sets the
// household currency through the store, so USD and INR both work
// everywhere), and Schools (add a portal = a read-only page watcher).
// Every change is a click on Save and writes an audit row.
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { addPortal, schoolPages } from '../../desk/ext/phase3';
import type { HouseholdSettings } from '../../desk/types';

const toast = (t: string) => useFamilyOS.getState().toast(t);

/** Country → the usual zone and currency, offered when the country changes (both stay editable). */
const PLACES: { country: string; code: string; tz: string; currency: string }[] = [
  { country: 'United States', code: 'US', tz: 'America/New_York', currency: 'USD' },
  { country: 'India', code: 'IN', tz: 'Asia/Kolkata', currency: 'INR' },
  { country: 'United Kingdom', code: 'GB', tz: 'Europe/London', currency: 'GBP' },
  { country: 'Canada', code: 'CA', tz: 'America/Toronto', currency: 'CAD' },
  { country: 'Australia', code: 'AU', tz: 'Australia/Sydney', currency: 'AUD' },
  { country: 'Ireland', code: 'IE', tz: 'Europe/Dublin', currency: 'EUR' },
];
const ZONES = ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Toronto', 'Europe/London', 'Europe/Dublin', 'Asia/Kolkata', 'Australia/Sydney', 'UTC'];
const CURRENCIES = ['USD', 'INR', 'GBP', 'EUR', 'CAD', 'AUD'];
const NAME_OK = /^[a-z0-9](?:[a-z0-9.-]{1,28}[a-z0-9])$/;

export function FamilyAddress({ quarantined }: { quarantined: number }) {
  const address = useDesk((s) => s.settings.familyAddress);
  const setSetting = useDesk((s) => s.setSetting);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [local, domain] = address.split('@');
  const copy = () => {
    const done = () => toast('Copied the family address.');
    const fail = () => toast('Could not copy. Select the address and copy it.');
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(address).then(done, fail);
    else fail();
  };
  const save = (e: FormEvent) => {
    e.preventDefault();
    const n = name.trim().toLowerCase();
    if (!NAME_OK.test(n)) return setError('Use 3 to 30 letters, digits, dots or dashes.');
    if (n === local) return setError('That is already the address.');
    setSetting('familyAddress', `${n}@${domain}`);
    setNaming(false);
    toast(`The family address is now ${n}@${domain}.`);
  };
  return (
    <div className="ib-addr">
      <p className="ib-label">
        <span className={T.bodyStrong}>Your family address</span> <span className={T.small}>give this to the school</span>
      </p>
      <div className="ib-addr__row">
        <code className="ib-code" aria-label="Family address">
          {address}
        </code>
        <PillButton label="Copy" variant="primary" aria-label="Copy the family address" onClick={copy} />
        <PillButton label="Choose a name" aria-expanded={naming} onClick={() => { setNaming((v) => !v); setName(local); setError(''); }} />
      </div>
      {naming ? (
        <form className="ib-inline" onSubmit={save}>
          <label className="sr-only" htmlFor="ib-addr-name">Name for the family address</label>
          <input id="ib-addr-name" className="ib-input ib-input--mono" value={name} onChange={(e) => { setName(e.target.value); setError(''); }} autoComplete="off" spellCheck={false} aria-invalid={!!error} aria-describedby={error ? 'ib-addr-err' : undefined} />
          <span className={T.small}>@{domain}</span>
          <PillButton label="Save" variant="primary" type="submit" />
          <PillButton label="Cancel" onClick={() => setNaming(false)} />
          {error ? <p id="ib-addr-err" role="alert" className={`${T.small} ib-error`}>{error}</p> : null}
        </form>
      ) : null}
      <p className={T.small}>Pick a name a person can say down a phone before you give it to a school. Addresses you used before keep working.</p>
      <p className={T.small}>
        Anything sent here reaches the household. Mail from a member whose provider vouched for it is read; <strong className="ib-strong">anything from a stranger waits in Quarantine</strong> until a guardian looks, so the address is safe to hand out.{' '}
        <Link to="/quarantine" className="wt-notice">Quarantine · {quarantined} waiting</Link>
      </p>
    </div>
  );
}

export function WhereWeLive() {
  const settings = useDesk((s) => s.settings);
  const setSetting = useDesk((s) => s.setSetting);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Pick<HouseholdSettings, 'country' | 'timezone' | 'currency'>>(settings);
  const code = PLACES.find((p) => p.country === settings.country)?.code ?? settings.country;
  const zones = ZONES.includes(draft.timezone) ? ZONES : [draft.timezone, ...ZONES];
  const pickCountry = (country: string) => {
    const p = PLACES.find((x) => x.country === country);
    setDraft(p ? { country, timezone: p.tz, currency: p.currency } : { ...draft, country });
  };
  const save = (e: FormEvent) => {
    e.preventDefault();
    (['country', 'timezone', 'currency'] as const).forEach((k) => setSetting(k, draft[k]));
    setOpen(false);
    toast(`Saved. Amounts now show in ${draft.currency}; nothing is converted or paid.`);
  };
  return (
    <div className="ib-where">
      <p className="ib-label">
        <span className={T.bodyStrong}>Where we live</span>{' '}
        <span className={T.small}>
          {code} · {settings.timezone} · {settings.currency}
        </span>
        <PillButton label="Change" aria-expanded={open} aria-label="Change where we live" onClick={() => { setDraft(settings); setOpen((v) => !v); }} />
      </p>
      {open ? (
        <form className="ib-inline ib-inline--grid" onSubmit={save}>
          <label className={T.small}>
            Country
            <select className="ib-input" value={draft.country} onChange={(e) => pickCountry(e.target.value)}>
              {PLACES.map((p) => <option key={p.code} value={p.country}>{p.country}</option>)}
            </select>
          </label>
          <label className={T.small}>
            Time zone
            <select className="ib-input" value={draft.timezone} onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}>
              {zones.map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </label>
          <label className={T.small}>
            Currency
            <select className="ib-input" value={draft.currency} onChange={(e) => setDraft({ ...draft, currency: e.target.value })}>
              {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <span className="ib-inline__btns">
            <PillButton label="Save" variant="primary" type="submit" />
            <PillButton label="Cancel" onClick={() => setOpen(false)} />
          </span>
          <p className={`${T.small} ib-inline__note`}>Dates follow the time zone, and every amount switches to the currency you pick. Nothing is converted or paid.</p>
        </form>
      ) : null}
    </div>
  );
}

export function Schools() {
  const children = useDesk((s) => s.children);
  const members = useDesk((s) => s.members);
  const watchers = useDesk((s) => s.watchers);
  const [adding, setAdding] = useState<string | null>(null);
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const save = (e: FormEvent, school: string) => {
    e.preventDefault();
    if (!addPortal(school, url)) return setError('That does not look like a web address.');
    setAdding(null);
    toast(`Added the ${school} portal. FamilyOS only reads it.`);
  };
  return (
    <div className="ib-schools">
      <p className={T.bodyStrong}>Schools</p>
      <ul>
        {children.map((c) => {
          const pages = schoolPages(watchers, c.school);
          const child = members.find((m) => m.id === c.memberId)?.name ?? '';
          return (
            <li key={c.memberId} className="ib-school">
              <p className="ib-label">
                <span className={T.bodyStrong}>{c.school}</span> <span className={T.small}>{child} · {c.grade}</span>
                <PillButton label="add portal" aria-label={`Add a portal for ${c.school}`} aria-expanded={adding === c.school} onClick={() => { setAdding(adding === c.school ? null : c.school); setUrl(''); setError(''); }} />
              </p>
              {pages.length ? (
                <p className={`${T.small} ib-school__pages`}>
                  watching: {pages.map((w) => w.label.split('·').slice(1).join('·').trim() || new URL(w.url).hostname).join(', ')}
                </p>
              ) : null}
              {adding === c.school ? (
                <form className="ib-inline" onSubmit={(e) => save(e, c.school)}>
                  <label className="sr-only" htmlFor={`ib-portal-${c.memberId}`}>{`${c.school} portal address`}</label>
                  <input id={`ib-portal-${c.memberId}`} className="ib-input" placeholder="portal.school.example" value={url} onChange={(e) => { setUrl(e.target.value); setError(''); }} autoComplete="off" aria-invalid={!!error} />
                  <PillButton label="Save" variant="primary" type="submit" />
                  <PillButton label="Cancel" onClick={() => setAdding(null)} />
                  {error ? <p role="alert" className={`${T.small} ib-error`}>{error}</p> : null}
                  <p className={`${T.small} ib-inline__note`}>Read-only: FamilyOS looks at the page for dates and changes. It never signs in or submits anything there.</p>
                </form>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
