// Settings → Household, right rail: From your phone and Pages you are
// watching (MASTER_AGENT.md §3.2 Settings 7:30–9:30 and Phone capture
// 7:40–10:30; frames f_097–f_105, f_016–f_017). Phone tokens: device, last
// used, added, Revoke (confirm); "New phone token" names the device and shows
// its token once; "How to set up the shortcut" unfolds the steps. Watchers:
// read-only page watchers with what they look at and when they last looked,
// Stop (confirm).
import { useState, type FormEvent } from 'react';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { Pressable } from '../../components/Pressable';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { DeskCard, StatusChip } from '../shell/DeskPage';
import { Field } from './AdminBits';
import { useConfirm } from './useConfirm';
import { readableCode, siteHost } from './settingsModel';
import { ADMIN_COPY } from './adminCopy';
import { API_ENABLED } from '../../services/api';
import { createPhoneToken } from '../../desk/api/server';

const C = ADMIN_COPY.settings;

interface Fmt {
  ago: (i: string) => string;
  date: (i: string) => string;
}

export function PhoneCard({ ago, date }: Fmt) {
  const tokens = useDesk((s) => s.phoneTokens);
  const make = useDesk((s) => s.newPhoneToken);
  const revoke = useDesk((s) => s.revokeToken);
  const [dialog, ask] = useConfirm();
  const [naming, setNaming] = useState<string | null>(null);
  const [shown, setShown] = useState<{ device: string; code: string } | null>(null);
  const sorted = [...tokens].sort((a, b) => Number(!!a.revokedAt) - Number(!!b.revokedAt) || b.createdAt.localeCompare(a.createdAt));

  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    const device = naming?.trim();
    if (!device) return;
    if (API_ENABLED) {
      // The server makes the token and shows it this once (POST /v1/devices).
      const made = await createPhoneToken(device);
      if (made) setShown({ device, code: made.token });
      setNaming(null);
      return;
    }
    const id = make(device);
    setShown({ device, code: readableCode(id.replace(/^tk_/, '') + Math.random().toString(36).slice(2)) });
    setNaming(null);
  };

  return (
    <DeskCard id="phone" title="From your phone" sub="share sheet · shortcut">
      <p className={T.small}>{C.phone}</p>
      <ul className="adm-list adm-boxes">
        {sorted.map((t) => (
          <li key={t.id} className="adm-row adm-box">
            <span className="adm-row__main">
              <span className={T.smallStrong}>{t.device}</span>
              <span className={clsx(T.small, 'adm-row__sub')}>
                {t.revokedAt ? `revoked ${date(t.revokedAt)}` : t.lastUsed ? `last used ${ago(t.lastUsed)}` : 'not used yet'} · added {date(t.createdAt)}
              </span>
            </span>
            <span className="adm-row__actions">
              {t.revokedAt ? (
                <StatusChip tone="neutral">revoked</StatusChip>
              ) : (
                <PillButton
                  label="Revoke"
                  aria-label={`Revoke the phone token for ${t.device}`}
                  onClick={() =>
                    ask({
                      title: `Revoke the token for ${t.device}?`,
                      body: 'The shortcut on that phone stops working at once. What it already sent stays in the Inbox.',
                      confirm: 'Revoke',
                      danger: true,
                      run: () => revoke(t.id),
                    })
                  }
                />
              )}
            </span>
          </li>
        ))}
      </ul>
      {shown ? (
        <div className="adm-note adm-note--ok" role="status">
          <p className={T.small}>
            Token for <strong>{shown.device}</strong>, shown once — paste it into the shortcut now:
          </p>
          <p className="adm-code adm-code--ink adm-token">{shown.code}</p>
          <div className="adm-actions" style={{ marginTop: 8 }}>
            <PillButton label="Copy" onClick={() => void navigator.clipboard?.writeText(shown.code).then(() => useFamilyOS.getState().toast('Copied.'), () => undefined)} />
            <PillButton label="Done — hide it" onClick={() => setShown(null)} />
          </div>
        </div>
      ) : naming !== null ? (
        <form className="adm-form" onSubmit={submit}>
          <Field label="Which phone is it for?">
            {({ id }) => <input id={id} className="adm-input" value={naming} placeholder="Linda’s iPhone" onChange={(e) => setNaming(e.target.value)} />}
          </Field>
          <div className="adm-actions">
            <Pressable type="submit" className="pill pill--primary" disabled={!naming.trim()}>
              Make the token
            </Pressable>
            <PillButton label="Cancel" onClick={() => setNaming(null)} />
          </div>
        </form>
      ) : (
        <PillButton label="New phone token" variant="primary" onClick={() => setNaming('')} />
      )}
      <details className="adm-details" style={{ marginTop: 10 }}>
        <summary className="desk-link">How to set up the shortcut (iPhone, two minutes)</summary>
        <ol className="adm-howto t-small">
          <li>Make a token here for that phone and keep this page open.</li>
          <li>On the phone, open Shortcuts, add “Send to FamilyOS”, and paste the token when it asks.</li>
          <li>In any app, tap Share → Send to FamilyOS. What you send arrives in the Inbox as a notice; nothing is read into proposals until you look.</li>
          <li>On Android, share to the FamilyOS app instead; it asks for the same token once.</li>
        </ol>
      </details>
      {dialog}
    </DeskCard>
  );
}

export function WatchingCard({ ago }: Fmt) {
  const watchers = useDesk((s) => s.watchers);
  const stop = useDesk((s) => s.stopWatcher);
  const [dialog, ask] = useConfirm();
  const live = watchers.filter((w) => w.status === 'watching').length;
  return (
    <DeskCard id="watching" title="Pages you are watching" sub={`${live} · read-only`}>
      <p className={T.small}>{C.watching}</p>
      <ul className="adm-list adm-boxes">
        {watchers.map((w) => (
          <li key={w.id} className="adm-row adm-box">
            <span className="adm-row__main">
              <span className={T.smallStrong}>{w.label}</span>
              <span className={clsx(T.small, 'adm-row__sub')}>
                {siteHost(w.url) ?? w.url} · every 24 h · {w.status === 'stopped' ? 'stopped' : w.lastChecked ? `checked ${ago(w.lastChecked)}` : 'not checked yet'}
              </span>
            </span>
            <span className="adm-row__actions">
              {w.status === 'stopped' ? (
                <StatusChip tone="neutral">stopped</StatusChip>
              ) : (
                <PillButton
                  label="Stop"
                  aria-label={`Stop watching ${w.label}`}
                  onClick={() =>
                    ask({
                      title: `Stop watching “${w.label}”?`,
                      body: 'FamilyOS stops reading this page. What it already noticed stays where it is.',
                      confirm: 'Stop watching',
                      run: () => stop(w.id),
                    })
                  }
                />
              )}
            </span>
          </li>
        ))}
      </ul>
      {dialog}
    </DeskCard>
  );
}
