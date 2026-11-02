// Settings → Household: the rules (MASTER_AGENT.md §3.2 Settings 7:30–9:30,
// "toggles with explanation + Turn on/off"; frames f_012, f_015–f_016). Each
// rule: its name, an on/off chip (text, not colour alone), one line saying
// what it does, and a Turn on / Turn off button — the click is the decision,
// written to the Audit, with Undo in the toast. Grouped as Notifications
// (#notifications) and What FamilyOS may do (#permissions), the anchors the
// avatar menu links to. Where we live: country · timezone · currency, changed
// only on Save; the currency re-formats every amount in the app.
import { useState } from 'react';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import type { HouseholdSettings, ToggleId } from '../../desk/types';
import { DeskCard, StatusChip } from '../shell/DeskPage';
import { Field } from './AdminBits';
import { CURRENCIES, timezoneOptions } from './settingsModel';

export function RulesCard({ id, title, sub, ids }: { id: string; title: string; sub: string; ids: ToggleId[] }) {
  const toggles = useDesk((s) => s.toggles);
  const setToggle = useDesk((s) => s.setToggle);
  const rows = ids.map((t) => toggles.find((x) => x.id === t)).filter((t): t is NonNullable<typeof t> => !!t);
  const flip = (t: ToggleId, label: string, on: boolean) => {
    setToggle(t, on);
    useFamilyOS.getState().toast(`${label} is ${on ? 'on' : 'off'}. Written to the Audit.`, { action: { label: 'Undo', onPress: () => setToggle(t, !on) }, duration: 5000 });
  };
  return (
    <DeskCard id={id} title={title} sub={sub}>
      <ul className="adm-list">
        {rows.map((t) => (
          <li key={t.id} className="adm-row adm-row--top">
            <span className="adm-row__main">
              <span className={clsx(T.bodyStrong, 'adm-row__title')}>
                {t.label}
                <StatusChip tone={t.on ? 'approved' : 'neutral'}>{t.on ? 'on' : 'off'}</StatusChip>
              </span>
              <span className={clsx(T.small, 'adm-row__sub')}>{t.explain}</span>
            </span>
            <span className="adm-row__actions">
              <PillButton label={t.on ? 'Turn off' : 'Turn on'} aria-label={`${t.on ? 'Turn off' : 'Turn on'} ${t.label}`} onClick={() => flip(t.id, t.label, !t.on)} />
            </span>
          </li>
        ))}
      </ul>
    </DeskCard>
  );
}

type Place = Pick<HouseholdSettings, 'country' | 'timezone' | 'currency'>;

export function PlaceCard() {
  const settings = useDesk((s) => s.settings);
  const setSetting = useDesk((s) => s.setSetting);
  const [draft, setDraft] = useState<Place | null>(null);
  const save = () => {
    if (!draft) return;
    const keys = (['country', 'timezone', 'currency'] as const).filter((k) => draft[k].trim() && draft[k] !== settings[k]);
    keys.forEach((k) => setSetting(k, draft[k].trim()));
    setDraft(null);
    if (keys.length) useFamilyOS.getState().toast('Saved. Written to the Audit.', { duration: 3600 });
  };
  return (
    <DeskCard
      id="place"
      title="Where we live"
      sub="dates, times and amounts follow this"
      action={draft ? null : <PillButton label="Change" aria-label="Change where we live" onClick={() => setDraft({ country: settings.country, timezone: settings.timezone, currency: settings.currency })} />}
    >
      {draft ? (
        <div className="adm-form adm-place">
          <div className="adm-grid3">
            <Field label="Country">
              {({ id }) => <input id={id} className="adm-input" value={draft.country} onChange={(e) => setDraft({ ...draft, country: e.target.value })} />}
            </Field>
            <Field label="Timezone">
              {({ id }) => (
                <select id={id} className="adm-select" value={draft.timezone} onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}>
                  {timezoneOptions(settings.timezone).map((z) => (
                    <option key={z} value={z}>
                      {z.replace(/_/g, ' ')}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="Currency">
              {({ id }) => (
                <select id={id} className="adm-select" value={draft.currency} onChange={(e) => setDraft({ ...draft, currency: e.target.value })}>
                  {CURRENCIES.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <p className={T.small}>Changing the currency re-formats every amount in FamilyOS; it converts nothing.</p>
          <div className="adm-actions">
            <PillButton label="Save" variant="primary" onClick={save} />
            <PillButton label="Cancel" onClick={() => setDraft(null)} />
          </div>
        </div>
      ) : (
        <p className={T.body}>
          {settings.country} · {settings.timezone.replace(/_/g, ' ')} · {CURRENCIES.find((c) => c.code === settings.currency)?.label ?? settings.currency}
        </p>
      )}
    </DeskCard>
  );
}
