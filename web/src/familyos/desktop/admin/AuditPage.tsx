// Audit, /audit (MASTER_AGENT.md §3.2 Audit 6:20–7:20, §3.3.6, §10, §11
// "Audit has no edit/delete"; FamilyOS.mp4 ≈6:20–7:15, frames f_077–f_088).
// Title with an append-only badge; "Who did what to which record. Nothing
// here can be edited or deleted."; Show the raw rows reveals each event code
// (`member.signed_in via "google"`, `calendar.synced kept 17 dropped 0`);
// rows newest first in day groups: time, sentence, actor chip (a person or
// FamilyOS). Filters by actor, kind and text only narrow the view. There is
// no edit or delete control anywhere on this page, and the store has none.
import { useDeferredValue, useMemo, useState } from 'react';
import clsx from 'clsx';
import { ScrollText, Search } from 'lucide-react';
import { T } from '../../theme/typography';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { fmtLongDay, fmtRelDay } from '../../desk/format';
import { actorName } from '../../desk/selectors';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { ActorChip } from './AdminBits';
import { actorOptions, filterAudit, groupByDay, isFiltered, kindOptions, NO_FILTER, rawLine, type AuditFilter } from './auditModel';
import { ADMIN_COPY } from './adminCopy';
import './admin.css';

export default function AuditPage() {
  const audit = useDesk((s) => s.audit);
  const members = useDesk((s) => s.members);
  const now = useNow();
  const f = useDeskFormat(now);
  const [raw, setRaw] = useState(false);
  const [filter, setFilter] = useState<AuditFilter>(NO_FILTER);
  const text = useDeferredValue(filter.text);
  const shown = useMemo(() => filterAudit(audit, { ...filter, text }), [audit, filter, text]);
  const days = useMemo(() => groupByDay(shown, f.tz), [shown, f.tz]);
  const actors = useMemo(() => actorOptions(audit), [audit]);
  const kinds = useMemo(() => kindOptions(audit), [audit]);
  const set = (p: Partial<AuditFilter>) => setFilter((x) => ({ ...x, ...p }));

  return (
    <DeskPage
      className="adm-page"
      icon={ScrollText}
      title="Audit"
      description={
        <>
          <StatusChip tone="neutral" className="adm-badge">
            append-only
          </StatusChip>{' '}
          {ADMIN_COPY.audit.description}
        </>
      }
    >
      <div className="adm-toolbar" role="toolbar" aria-label="Audit view">
        <button type="button" className={clsx('adm-filter', raw && 'is-on')} aria-pressed={raw} onClick={() => setRaw((r) => !r)}>
          {raw ? 'Hide the raw rows' : 'Show the raw rows'}
        </button>
        <label className="sr-only" htmlFor="audit-actor">
          Who
        </label>
        <select id="audit-actor" className="adm-select adm-select--small" value={filter.actor} onChange={(e) => set({ actor: e.target.value })}>
          <option value="all">Everyone</option>
          {actors.map((a) => (
            <option key={a} value={a}>
              {actorName({ members }, a) || 'Someone'}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="audit-kind">
          Kind
        </label>
        <select id="audit-kind" className="adm-select adm-select--small" value={filter.kind} onChange={(e) => set({ kind: e.target.value })}>
          <option value="all">Every kind</option>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <span className="adm-search">
          <Search size={14} className="adm-search__icon" aria-hidden />
          <input className="adm-input" type="search" value={filter.text} placeholder="Find in the audit" aria-label="Find in the audit" onChange={(e) => set({ text: e.target.value })} />
        </span>
        {isFiltered(filter) ? (
          <button type="button" className="desk-link" onClick={() => setFilter(NO_FILTER)}>
            Clear
          </button>
        ) : null}
        <span className={clsx(T.small, 'adm-toolbar__count')} aria-live="polite">
          {isFiltered(filter) ? `${shown.length} of ${audit.length} rows` : `${audit.length} rows · newest first`}
        </span>
      </div>

      {days.length === 0 ? (
        <DeskCard>
          <p className={clsx(T.small, 'desk-empty')}>{audit.length ? 'No row matches. The log itself is unchanged.' : 'Nothing has been recorded yet.'}</p>
        </DeskCard>
      ) : (
        <section className="desk-card card adm-log" aria-label="Audit rows">
          {days.map((d) => (
            <div key={d.day} className="adm-day">
              <h2 className={clsx(T.section, 'adm-day__label')}>
                {fmtRelDay(d.day, f.today)} · {fmtLongDay(d.day)}
              </h2>
              <ol className="adm-list">
                {d.rows.map((r) => (
                  <li key={r.id} className="adm-log__row">
                    <time className={clsx(T.small, 'adm-log__time')} dateTime={r.at}>
                      {f.time(r.at, false)}
                    </time>
                    <span className="adm-log__main">
                      <span className={clsx(T.body, 'adm-log__sentence')}>{f.text(r.sentence)}</span>
                      {raw ? <code className="adm-code">{rawLine(r)}</code> : null}
                    </span>
                    <ActorChip actor={r.actor} className="adm-log__actor" />
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </section>
      )}
    </DeskPage>
  );
}
