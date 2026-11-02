// Settings → Household, right rail: Connected mailboxes and Telegram
// (MASTER_AGENT.md §3.2 Settings 7:30–9:30, §1 A5; frames f_097, f_100,
// f_113). Mailboxes: each address with when it connected and last read, a
// "reading" chip, Disconnect (confirm). "Connect a Gmail account" asks for
// the address and records it; in this build no Google window opens, and the
// card says so. Telegram: the household bot, linked devices, and "Link
// another device", which shows a one-time code to send from that device —
// nothing is linked until it does.
import { useState, type FormEvent } from 'react';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { Pressable } from '../../components/Pressable';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { memberName } from '../../desk/selectors';
import { DeskCard, StatusChip } from '../shell/DeskPage';
import { Field } from './AdminBits';
import { useConfirm } from './useConfirm';
import { readableCode, validEmail } from './settingsModel';
import { ADMIN_COPY } from './adminCopy';

const C = ADMIN_COPY.settings;

interface Fmt {
  ago: (i: string) => string;
  date: (i: string) => string;
}

export function MailboxesCard({ ago, date }: Fmt) {
  const mailboxes = useDesk((s) => s.mailboxes);
  const connect = useDesk((s) => s.connectMailbox);
  const disconnect = useDesk((s) => s.disconnectMailbox);
  const [dialog, ask] = useConfirm();
  const [adding, setAdding] = useState<string | null>(null);
  const [tried, setTried] = useState(false);
  const live = mailboxes.filter((m) => m.status === 'connected');
  const error = adding !== null && !validEmail(adding) ? 'A full Gmail address, like name@gmail.com.' : null;

  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    setTried(true);
    if (adding === null || error) return;
    connect(adding.trim().toLowerCase());
    useFamilyOS.getState().toast(`Connected ${adding.trim()}, read-only.`, { duration: 3600 });
    setAdding(null);
    setTried(false);
  };

  return (
    <DeskCard id="mailboxes" title="Connected mailboxes" sub="read-only">
      <p className={T.small}>{C.mailboxes}</p>
      <ul className="adm-list adm-boxes">
        {mailboxes.map((m) => (
          <li key={m.id} className="adm-row adm-box">
            <span className="adm-row__main">
              <span className={clsx(T.smallStrong, 'adm-row__title')}>{m.address}</span>
              <span className={clsx(T.small, 'adm-row__sub')}>
                connected {date(m.connectedAt)}
                {m.status === 'connected' && m.lastSync ? ` · last read ${ago(m.lastSync)}` : ''}
              </span>
            </span>
            <span className="adm-row__actions">
              <StatusChip tone={m.status === 'connected' ? 'approved' : 'neutral'}>{m.status === 'connected' ? 'reading' : 'disconnected'}</StatusChip>
              {m.status === 'connected' ? (
                <PillButton
                  label="Disconnect"
                  aria-label={`Disconnect ${m.address}`}
                  onClick={() =>
                    ask({
                      title: `Disconnect ${m.address}?`,
                      body: 'FamilyOS stops reading it and forgets its token. Notices already read stay in the Inbox.',
                      confirm: 'Disconnect',
                      danger: true,
                      run: () => disconnect(m.id),
                    })
                  }
                />
              ) : null}
            </span>
          </li>
        ))}
      </ul>
      {adding === null ? (
        <PillButton label="Connect a Gmail account" variant="primary" onClick={() => setAdding('')} />
      ) : (
        <form className="adm-form" onSubmit={submit} noValidate>
          <Field label="Gmail address" error={tried ? error : null} hint="In this preview no Google window opens; the mailbox is recorded as connected, read-only.">
            {({ id, describedBy, invalid }) => (
              <input id={id} className="adm-input" type="email" autoComplete="email" value={adding} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setAdding(e.target.value)} />
            )}
          </Field>
          <div className="adm-actions">
            <Pressable type="submit" className="pill pill--primary">
              Connect read-only
            </Pressable>
            <PillButton label="Cancel" onClick={() => setAdding(null)} />
          </div>
        </form>
      )}
      <p className={clsx(T.small, 'adm-row__sub')} style={{ marginTop: 10 }}>
        {live.length} {live.length === 1 ? 'mailbox' : 'mailboxes'} reading. A connection that stops working says so in the Inbox, rather than quietly reading nothing.
      </p>
      {dialog}
    </DeskCard>
  );
}

export function TelegramCard({ date }: Fmt) {
  const telegram = useDesk((s) => s.telegram);
  const members = useDesk((s) => s.members);
  const [code, setCode] = useState<string | null>(null);
  return (
    <DeskCard id="telegram" title="Telegram" action={<StatusChip tone={telegram.devices.length ? 'approved' : 'neutral'}>{telegram.devices.length ? 'linked' : 'not linked'}</StatusChip>}>
      <p className={T.small}>{C.telegram(telegram.bot)}</p>
      {telegram.devices.length ? (
        <ul className="adm-list">
          {telegram.devices.map((d) => (
            <li key={d.id} className="adm-row">
              <span className="adm-row__main">
                <span className={T.smallStrong}>{d.label}</span>
                <span className={clsx(T.small, 'adm-row__sub')}>
                  {memberName({ members }, d.ownerId)} · linked {date(d.linkedAt)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {code ? (
        <div className="adm-note" role="status" style={{ marginTop: 8 }}>
          <p className={T.small}>
            From the new device, send <span className="adm-code adm-code--ink">/link {code}</span> to {telegram.bot} within ten minutes. Nothing is linked until it does.
          </p>
          <div className="adm-actions" style={{ marginTop: 10 }}>
            <PillButton label="Done" onClick={() => setCode(null)} />
          </div>
        </div>
      ) : (
        <PillButton label="Link another device" onClick={() => setCode(readableCode(Math.random().toString(36).slice(2), 'tg').slice(3, 12))} />
      )}
    </DeskCard>
  );
}
