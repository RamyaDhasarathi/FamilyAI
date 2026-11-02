// Notice detail drawer, /inbox/:noticeId — also opened over Ask by a citation
// chip (MASTER_AGENT.md §7 Phase 3, §3.3.2; FamilyOS.mp4 2:55, 9:50–10:40,
// frames f_121–f_123). About: sender, when, how it came, people, category;
// "Not right?" (a note on the notice, audited); who handles it; "Open the
// original" (audited as artifact.original_read). Then Read from this notice
// (highlighted source) and Proposed for the family (Accept / ✕).
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { Sheet } from '../../components/Sheet';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { memberName, proposalsFor } from '../../desk/selectors';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { assignNotice, handlerOf } from '../../desk/ext/phase3';
import { API_ENABLED } from '../../services/api';
import { loadNoticeDetail } from '../../desk/api/server';
import type { Notice } from '../../desk/types';
import { StatusChip } from '../shell/DeskPage';
import { CATEGORY_LABELS, sourceWord } from './inboxModel';
import { SourceIcon } from './NoticeRow';
import { ProposedList, ReadFromNotice } from './NoticeClaims';
import './inbox.css';

export default function NoticeDrawer({ noticeId, onClose }: { noticeId: string | null; onClose: () => void }) {
  const notice = useDesk((s) => (noticeId ? s.notices.find((n) => n.id === noticeId) : undefined));
  const title = notice ? notice.title : 'Notice not found';
  const f = useDeskFormat();
  // On the backend a notice's text and what was read from it come when it is opened.
  useEffect(() => {
    if (API_ENABLED && noticeId) void loadNoticeDetail(noticeId);
  }, [noticeId]);
  return (
    <Sheet
      open={!!noticeId}
      onClose={onClose}
      labelledBy="notice-title"
      drawerWidth={540}
      bodyClassName="ib-drawer__scroll"
      header={
        <div className="sheet-title-row ib-drawer__head">
          <div>
            <p className={T.section}>Notice{notice ? ` · ${CATEGORY_LABELS[notice.category]}` : ''}</p>
            <h2 id="notice-title" className={T.sheetTitle}>{f.text(title)}</h2>
          </div>
        </div>
      }
    >
      {notice ? <DrawerBody key={notice.id} notice={notice} /> : <p className={`${T.small} ib-drawer`}>It may have been deleted from Quarantine or erased.</p>}
    </Sheet>
  );
}

function DrawerBody({ notice }: { notice: Notice }) {
  const now = useNow();
  const f = useDeskFormat(now);
  const all = useDesk((s) => s.proposals);
  const members = useDesk((s) => s.members);
  const actor = useDesk((s) => s.actor);
  const flagNotice = useDesk((s) => s.flagNotice);
  const openOriginal = useDesk((s) => s.openOriginal);
  const proposals = useMemo(() => proposalsFor({ proposals: all }, notice.id), [all, notice.id]);
  const [flagging, setFlagging] = useState(false);
  const [note, setNote] = useState('');
  const [original, setOriginal] = useState(false);
  const name = (id?: string) => memberName({ members }, id);
  const handler = handlerOf(notice);
  const canHandle = members.filter((m) => m.hasAccount);

  const sendFlag = (e: FormEvent) => {
    e.preventDefault();
    if (!note.trim()) return;
    flagNotice(notice.id, note.trim());
    setNote('');
    setFlagging(false);
    useFamilyOS.getState().toast('Thanks. The note is on the notice; nothing else changed.');
  };
  const showOriginal = () => {
    if (!original) openOriginal(notice.id);
    setOriginal((v) => !v);
  };
  const assign = (id: string | null) => {
    if (assignNotice(notice.id, id)) useFamilyOS.getState().toast(id ? (id === actor ? 'You are handling it.' : `Asked ${name(id)} to handle it.`) : 'Nobody is handling it now.');
  };

  return (
    <div className="ib-drawer">
      <section className="ib-about" aria-label="About this notice">
        <p className={clsx(T.small, 'ib-about__from')}>
          <SourceIcon source={notice.source} size={14} />
          <span className={T.smallStrong}>{notice.sender}</span>
          {notice.senderAddress ? <span>{notice.senderAddress}</span> : null}
        </p>
        <p className="ib-about__chips">
          <span className={T.small}>
            {f.ago(notice.receivedAt)} · via {sourceWord(notice.source)}
            {notice.attachments ? ` · ${notice.attachments === 1 ? '1 attachment' : `${notice.attachments} attachments`}` : ''}
          </span>
          {(notice.memberIds ?? []).map((id) => <StatusChip key={id} tone="neutral">{name(id)}</StatusChip>)}
          <StatusChip tone="draft">{CATEGORY_LABELS[notice.category]}</StatusChip>
        </p>
        <p className={clsx(T.small, 'ib-about__wants')}>{f.text(notice.summary)}</p>
        <div className="ib-about__actions">
          <PillButton label="Not right?" aria-expanded={flagging} onClick={() => setFlagging((v) => !v)} />
          <PillButton label={original ? 'Hide the original' : 'Open the original'} aria-expanded={original} onClick={showOriginal} />
        </div>
        {flagging ? (
          <form className="ib-flag" onSubmit={sendFlag}>
            <label htmlFor="ib-flag-note" className={T.small}>What did FamilyOS read wrong?</label>
            <textarea id="ib-flag-note" className="ib-input ib-input--area" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="The date is the 6th, not the 9th." />
            <span className="ib-way__btns">
              <PillButton label="Send the note" variant="primary" type="submit" disabled={!note.trim()} />
              <PillButton label="Cancel" onClick={() => setFlagging(false)} />
            </span>
          </form>
        ) : null}
        {(notice.flags ?? []).map((fl) => (
          <p key={`${fl.at}-${fl.note}`} className={clsx(T.small, 'ib-flag__note')}>
            Not right, said {name(fl.by)} {f.ago(fl.at)}: “{fl.note}”
          </p>
        ))}
        {original ? (
          <div className="ib-original" role="region" aria-label="The original">
            <p className={T.small}>From {notice.senderAddress ?? notice.sender} · received {new Date(notice.receivedAt).toLocaleString('en-US', { timeZone: f.tz, dateStyle: 'medium', timeStyle: 'short' })} · via {sourceWord(notice.source)}</p>
            <pre className="ib-original__text">{f.text(notice.body)}</pre>
          </div>
        ) : null}
        <div className="ib-handler" role="group" aria-label="Who handles it">
          <span className={T.small}>Handled by</span>
          {canHandle.map((m) => (
            <button key={m.id} type="button" className={clsx('ib-seg', handler === m.id && 'is-on')} aria-pressed={handler === m.id} onClick={() => assign(m.id)}>
              {m.name}
            </button>
          ))}
          <button type="button" className={clsx('ib-seg', handler === null && 'is-on')} aria-pressed={handler === null} onClick={() => assign(null)}>
            Nobody yet
          </button>
        </div>
      </section>
      <ReadFromNotice notice={notice} proposals={proposals} f={f} />
      <ProposedList proposals={proposals} f={f} now={now} />
    </div>
  );
}
