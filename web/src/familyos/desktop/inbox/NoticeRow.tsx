// Inbox, one notice row (MASTER_AGENT.md §7 Phase 3; FamilyOS.mp4 3:50, 9:30,
// frames f_047, f_114): source icon; sender · when · person chips · category
// chip · attachments; the title; one line of what it wants; on the right the
// earliest date still open and "N to decide". The whole row opens the
// notice drawer (/inbox/:id, keeping the filters in the URL).
import { Link } from 'react-router';
import clsx from 'clsx';
import { ClipboardPaste, Globe, Mail, MessageCircle, Send, Smartphone, type LucideIcon } from 'lucide-react';
import { T } from '../../theme/typography';
import type { NoticeSource } from '../../desk/types';
import { StatusChip } from '../shell/DeskPage';
import { CATEGORY_LABELS, type NoticeRowData } from './inboxModel';

const SOURCE_ICON: Record<NoticeSource, LucideIcon> = { email: Mail, phone: Smartphone, telegram: Send, whatsapp: MessageCircle, paste: ClipboardPaste, site: Globe };

export function SourceIcon({ source, size = 16 }: { source: NoticeSource; size?: number }) {
  const Icon = SOURCE_ICON[source];
  return (
    <span className="ib-src" aria-hidden>
      <Icon size={size} strokeWidth={1.8} />
    </span>
  );
}

interface Props {
  row: NoticeRowData;
  href: string;
  active: boolean;
  text: (s: string) => string;
  ago: (i: string) => string;
  day: (w: string) => string;
  name: (id?: string) => string;
}

export function NoticeRow({ row, href, active, text, ago, day, name }: Props) {
  const n = row.notice;
  const title = text(n.title);
  const people = (n.memberIds ?? []).map((id) => name(id)).filter(Boolean);
  const status = row.status === 'todo' ? `${row.open} to decide` : row.status === 'done' ? 'all decided' : 'nothing asked';
  return (
    <li>
      <Link to={href} className={clsx('ib-row', active && 'is-open')} aria-current={active ? 'true' : undefined} aria-label={`${title}, from ${n.sender}, ${ago(n.receivedAt)}. ${status}. Opens the notice`}>
        <SourceIcon source={n.source} />
        <span className="ib-row__main">
          <span className={clsx(T.small, 'ib-row__from')}>
            <span className="ib-row__sender">{n.sender}</span>
            <span>{ago(n.receivedAt)}</span>
            {people.map((p) => (
              <StatusChip key={p} tone="neutral">
                {p}
              </StatusChip>
            ))}
            <StatusChip tone="draft">{CATEGORY_LABELS[n.category]}</StatusChip>
            {n.attachments ? <span>{n.attachments === 1 ? '1 attachment' : `${n.attachments} attachments`}</span> : null}
          </span>
          <span className={clsx(T.bodyStrong, 'ib-row__title')}>{title}</span>
          <span className={clsx(T.small, 'ib-row__wants')}>{text(n.summary)}</span>
        </span>
        <span className="ib-row__side">
          {row.firstDue ? <span className={clsx(T.small, 'ib-row__due')}>{day(row.firstDue.due)}</span> : null}
          {row.status === 'todo' ? <StatusChip tone="proposed">{row.open} to decide</StatusChip> : null}
          {row.status === 'done' ? <StatusChip tone="approved">decided</StatusChip> : null}
        </span>
      </Link>
    </li>
  );
}
