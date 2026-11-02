// Inbox, /inbox and /inbox/:noticeId (MASTER_AGENT.md §7 Phase 3, §3.3;
// FamilyOS.mp4 3:50–4:20 and 9:30, frames f_047–f_052, f_114). Filter chips
// with counts (status: To do / Done / Nothing asked / All; category:
// Everything + each category), kept in the URL (?show=&cat=&who=) so refresh
// and Back work; notice rows that open the drawer (/inbox/:id) over the
// list; promotions that ask nothing kept out of the way and counted; the
// setup card (family address, where we live, schools, other ways in). Right
// rail: Dates spotted (✓ / ✕) and Handling. Unknown senders wait in
// Quarantine, linked from the header and the address card.
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import clsx from 'clsx';
import { Inbox } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { memberName } from '../../desk/selectors';
import { DeskPage } from '../shell/DeskPage';
import NoticeDrawer from './NoticeDrawer';
import { NoticeRow } from './NoticeRow';
import { DatesSpotted, Handling } from './InboxRail';
import { FamilyAddress, Schools, WhereWeLive } from './InboxSetup';
import { AddNoticeDialog, WaysIn } from './WaysIn';
import { STATUS_LABELS, STATUS_ORDER, datesSpotted, handling, inboxView, parseQuery, spottedLine, type CategoryFilter, type StatusFilter } from './inboxModel';
import './inbox.css';

export default function InboxPage() {
  const { noticeId } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const now = useNow();
  const f = useDeskFormat(now);
  const notices = useDesk((s) => s.notices);
  const proposals = useDesk((s) => s.proposals);
  const members = useDesk((s) => s.members);
  const actor = useDesk((s) => s.actor);
  const quarantined = useDesk((s) => s.quarantine.length);
  const qy = useMemo(() => parseQuery(params), [params]);
  const view = useMemo(() => inboxView({ notices, proposals }, qy, actor), [notices, proposals, qy, actor]);
  const spotted = useMemo(() => datesSpotted({ notices, proposals }, now, f.tz, actor), [notices, proposals, now, f.tz, actor]);
  const hands = useMemo(() => handling({ notices, proposals, members }, actor), [notices, proposals, members, actor]);
  const name = (id?: string) => memberName({ members }, id);
  const search = params.toString() ? `?${params.toString()}` : '';

  const setFilter = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  };
  const whoName = qy.who ? (qy.who === 'nobody' ? 'nobody yet' : name(qy.who)) : '';

  return (
    <DeskPage
      icon={Inbox}
      color={colors.dust}
      title="Inbox"
      className="ib-page"
      description="Everything that arrived, kept exactly as it came. To do until every date on it is decided; nothing here is accepted, sent or paid on its own."
      actions={
        <>
          <Link to="/quarantine" className="pill pill--secondary">
            Quarantine · {quarantined}
          </Link>
          <PillButton label="Add a notice" variant="primary" onClick={() => setAdding(true)} />
        </>
      }
      rail={
        <>
          <DatesSpotted items={spotted} text={f.text} day={f.day} slot={f.slot} line={(p) => spottedLine(p, p.forMemberId ? name(p.forMemberId) : '', now, f.tz)} />
          <Handling rows={hands} who={qy.who ?? null} onPick={(id) => setFilter({ who: id, show: id ? 'todo' : qy.show })} />
        </>
      }
    >
      <section className="ib-filters" aria-label="Filter the notices">
        <div className="ib-chips" role="group" aria-label="Show">
          {STATUS_ORDER.map((s: StatusFilter) => (
            <button key={s} type="button" className={clsx('ib-chip', qy.show === s && 'is-on')} aria-pressed={qy.show === s} onClick={() => setFilter({ show: s })}>
              {STATUS_LABELS[s]} <span className="ib-chip__n">{view.statusCounts[s]}</span>
            </button>
          ))}
        </div>
        <div className="ib-chips" role="group" aria-label="Category">
          <button type="button" className={clsx('ib-chip', qy.cat === 'everything' && 'is-on')} aria-pressed={qy.cat === 'everything'} onClick={() => setFilter({ cat: null })}>
            Everything
          </button>
          {view.categories.map((c) => (
            <button key={c.id} type="button" className={clsx('ib-chip', qy.cat === c.id && 'is-on')} aria-pressed={qy.cat === c.id} onClick={() => setFilter({ cat: c.id as CategoryFilter })}>
              {c.label} <span className="ib-chip__n">{c.count}</span>
            </button>
          ))}
        </div>
        {qy.who ? (
          <p className={clsx(T.small, 'ib-who')}>
            Handled by {whoName} ·{' '}
            <button type="button" className="desk-link" onClick={() => setFilter({ who: null })}>
              show everyone’s
            </button>
          </p>
        ) : null}
      </section>

      <section className="ib-list card" aria-label="Notices">
        {view.rows.length === 0 ? (
          <p className={clsx(T.small, 'desk-empty')}>
            {qy.show === 'todo' ? 'Nothing here needs a decision.' : 'No notices match these filters.'}
          </p>
        ) : (
          <ul>
            {view.rows.map((r) => (
              <NoticeRow key={r.notice.id} row={r} href={`/inbox/${r.notice.id}${search}`} active={r.notice.id === noticeId} text={f.text} ago={f.ago} day={f.day} name={name} />
            ))}
          </ul>
        )}
      </section>
      {view.kept ? (
        <p className={clsx(T.small, 'ib-kept')}>
          {view.kept} {view.kept === 1 ? 'promotion or newsletter' : 'promotions and newsletters'} kept out of the way. Pick Promo or Newsletter above to see them.
        </p>
      ) : null}

      <section className="ib-setup card" aria-label="How notices reach the family">
        <FamilyAddress quarantined={quarantined} />
        <WhereWeLive />
        <Schools />
        <WaysIn onAdd={() => setAdding(true)} />
      </section>

      <NoticeDrawer noticeId={noticeId ?? null} onClose={() => navigate(`/inbox${search}`, { replace: true })} />
      <AddNoticeDialog open={adding} onClose={() => setAdding(false)} />
    </DeskPage>
  );
}
