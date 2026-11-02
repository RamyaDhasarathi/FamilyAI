// Quarantine, /quarantine (MASTER_AGENT.md §3.2 Inbox 3:50–4:20 "strangers go
// to Quarantine", §7 Phase 5 "notices from unknown senders, Release /
// Delete"). Each held notice: who sent it (name and address), when, why it
// was held, and — folded away — what it says, as plain text with no live
// links. Release moves it to the Inbox to be read like any other notice;
// Delete removes it for good. Both ask for a confirm, and both write an
// audit row (the store does that).
import { Link } from 'react-router';
import clsx from 'clsx';
import { Paperclip, ShieldAlert } from 'lucide-react';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { MiniGem } from '../../components/MiniGem';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { memberName } from '../../desk/selectors';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { useConfirm } from './useConfirm';
import { ADMIN_COPY } from './adminCopy';
import './admin.css';

const C = ADMIN_COPY.quarantine;

export default function QuarantinePage() {
  const held = useDesk((s) => s.quarantine);
  const notices = useDesk((s) => s.notices);
  const members = useDesk((s) => s.members);
  const address = useDesk((s) => s.settings.familyAddress);
  const release = useDesk((s) => s.releaseQuarantine);
  const remove = useDesk((s) => s.deleteQuarantine);
  const now = useNow();
  const f = useDeskFormat(now);
  const [dialog, ask] = useConfirm();
  const rows = [...held].sort((a, b) => b.heldAt.localeCompare(a.heldAt)).map((q) => ({ q, n: notices.find((x) => x.id === q.noticeId) }));
  const toast = (t: string) => useFamilyOS.getState().toast(t, { duration: 4200 });

  return (
    <DeskPage
      className="adm-page"
      icon={ShieldAlert}
      title="Quarantine"
      description={C.description}
      rail={
        <>
          <DeskCard title="Why a notice waits here">
            <div className="adm-prose">
              <p className={T.small}>It came to the family address from a sender nobody in the household has heard from, or it asks for money through a link.</p>
              <p className={T.small}>While it waits, FamilyOS does not read it into proposals, open its links or look at its attachments.</p>
              <p className={T.small}>
                <strong>Release</strong> moves it to the Inbox, read like any other notice. <strong>Delete</strong> removes it for good; the Audit keeps one row saying so.
              </p>
            </div>
          </DeskCard>
          <DeskCard title="Your family address">
            <p className={clsx(T.smallStrong, 'adm-row__title')}>{address}</p>
            <p className={clsx(T.small, 'adm-row__sub')} style={{ marginTop: 4 }}>
              Give it to schools and clinics so their notices skip Quarantine.
            </p>
            <Link to="/inbox" className="desk-link" style={{ marginTop: 10 }}>
              The Inbox ›
            </Link>
          </DeskCard>
        </>
      }
    >
      {rows.length === 0 ? (
        <div className="desk-empty card adm-note">
          <MiniGem size={36} still />
          <p className={T.small}>{C.empty}</p>
        </div>
      ) : (
        <DeskCard title="Held" sub={`${rows.length} from unknown senders`}>
          <ul className="adm-list">
            {rows.map(({ q, n }) =>
              n ? (
                <li key={q.id} className="adm-row adm-row--top">
                  <span className="adm-row__main">
                    <span className={clsx(T.small, 'adm-row__title')}>
                      <span className={T.smallStrong}>{n.sender}</span>
                      {n.senderAddress ? <span>{n.senderAddress}</span> : null}
                      <span>· {f.ago(n.receivedAt)}</span>
                      {n.memberIds?.map((m) => (
                        <StatusChip key={m} tone="neutral">
                          {memberName({ members }, m)}
                        </StatusChip>
                      ))}
                      {n.attachments ? (
                        <StatusChip tone="neutral">
                          <Paperclip size={10} aria-hidden /> {n.attachments} unopened
                        </StatusChip>
                      ) : null}
                    </span>
                    <span className={clsx(T.bodyStrong, 'adm-row__title')}>{f.text(n.title)}</span>
                    <span className={clsx(T.small, 'adm-row__sub')}>
                      <StatusChip tone="overdue">held</StatusChip> {q.reason}
                    </span>
                    <details className="adm-details">
                      <summary className="desk-link">What it says</summary>
                      <p className={clsx(T.small, 'adm-quote')}>{f.text(n.body)}</p>
                      <p className={clsx(T.small, 'adm-row__sub')}>Shown as plain text: links in it are not clickable here.</p>
                    </details>
                  </span>
                  <span className="adm-row__actions">
                    <PillButton
                      label="Release"
                      aria-label={`Release ${n.title} to the Inbox`}
                      onClick={() =>
                        ask({
                          title: `Release “${f.text(n.title)}”?`,
                          body: `It moves to the Inbox and FamilyOS reads it like any other notice, so it may propose things from it. ${n.senderAddress ?? n.sender} is not added to any trusted list.`,
                          confirm: 'Release to the Inbox',
                          run: () => {
                            release(q.id);
                            toast('Released to the Inbox. Nothing was accepted.');
                          },
                        })
                      }
                    />
                    <PillButton
                      label="Delete"
                      className="adm-pill--soft-danger"
                      aria-label={`Delete ${n.title}`}
                      onClick={() =>
                        ask({
                          title: `Delete “${f.text(n.title)}”?`,
                          body: 'The notice is gone for good, along with its attachments. The Audit keeps one row saying it was deleted, not what it said.',
                          confirm: 'Delete for good',
                          cancel: 'Keep it held',
                          danger: true,
                          run: () => {
                            remove(q.id);
                            toast('Deleted. The Audit notes it.');
                          },
                        })
                      }
                    />
                  </span>
                </li>
              ) : null
            )}
          </ul>
        </DeskCard>
      )}
      {dialog}
    </DeskPage>
  );
}
