// Household and Grocery dashboards, desktop sections (MASTER_AGENT.md §4,
// §7 Phases 4–5; FamilyOS.mp4 5:50 Errands, 1:50 "Order again · from your
// receipts"). Household: the Errands list (rows → /errands/:id, status chips
// with text, "Ask for one" → /ask?q=…). Grocery: Order again (item, store,
// last date, price); Order ↗ only proposes — it writes the reorder down as an
// errand for a guardian to approve, after a Confirm click. Nothing is bought.
import { useId, useMemo, useState } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { ArrowUpRight, ChevronRight } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { Dot } from '../../components/Labels';
import { PillButton } from '../../components/Pills';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useDeskFormat } from '../../desk/hooks';
import { dayKey, fmtShortDay, m } from '../../desk/format';
import { memberName } from '../../desk/selectors';
import type { ErrandTerms, OrderAgainItem } from '../../desk/types';
import { StatusChip } from '../shell/DeskPage';
import { askPath } from '../shell/routes';
import { ExtrasLayout, Explainer, Section } from './SpaceParts';
import { hostOf, reorderCap, sortErrands } from './listModels';
import { extrasCopy, orderTitle, spaceCopy } from './copy';

const X = extrasCopy;
const TONE = { proposed: 'proposed', approved: 'approved', done: 'done', cancelled: 'cancelled' } as const;

export function HouseholdExtras({ now }: { now: Date }) {
  const errands = useDesk((s) => s.errands);
  const members = useDesk((s) => s.members);
  const f = useDeskFormat(now);
  const list = useMemo(() => sortErrands(errands), [errands]);
  const action = (
    <Link className="pill pill--secondary sp-pill-sm" to={askPath(X.askForOneQ)}>
      {X.askForOne}
    </Link>
  );
  return (
    <ExtrasLayout
      main={
        <Section title={X.errands} sub={list.length ? X.errandsSub(list.length) : undefined} action={action}>
          {list.length ? (
            <ul className="sp-errands">
              {list.map((e) => (
                <li key={e.id}>
                  <Link to={`/errands/${e.id}`} className="sp-row-link sp-errand">
                    <Dot color={colors.agents[e.agent]} size={7} />
                    <span className="sp-errand__text">
                      <span className="sp-errand__title">
                        <span className={T.smallStrong}>{e.title}</span>
                        <StatusChip tone={TONE[e.status]}>{X.errandStatus[e.status]}</StatusChip>
                      </span>
                      <span className={T.small}>{X.errandLine(f.money(e.atMost), f.text(e.when))}</span>
                      <span className={T.small}>{X.errandBy(memberName({ members }, e.requestedBy), fmtShortDay(dayKey(e.createdAt, f.tz)))}</span>
                    </span>
                    <ChevronRight size={16} className="sp-chev" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className={clsx(T.small, 'desk-empty')}>{X.errandsEmpty}</p>
          )}
        </Section>
      }
      rail={
        <Explainer title={X.howErrands}>
          <p className={T.small}>{X.howErrandsText}</p>
          <Link to="/errands" className="desk-link">
            {X.allErrands} ›
          </Link>
        </Explainer>
      }
    />
  );
}

export function GroceryExtras({ now }: { now: Date }) {
  const items = useDesk((s) => s.orderAgain);
  return (
    <ExtrasLayout
      main={
        <Section title={X.orderAgain} sub={X.orderAgainSub}>
          {items.length ? (
            <ul className="sp-orders">
              {items.map((o) => (
                <OrderRow key={o.id} o={o} now={now} />
              ))}
            </ul>
          ) : (
            <p className={clsx(T.small, 'desk-empty')}>{X.orderEmpty}</p>
          )}
        </Section>
      }
      rail={
        <Explainer title={X.howOrder}>
          <p className={T.small}>{X.howOrderText}</p>
          <Link to="/errands" className="desk-link">
            {X.allErrands} ›
          </Link>
        </Explainer>
      }
    />
  );
}

function OrderRow({ o, now }: { o: OrderAgainItem; now: Date }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  const f = useDeskFormat(now);
  const errands = useDesk((s) => s.errands);
  const members = useDesk((s) => s.members);
  const actor = useDesk((s) => s.actor);
  const request = useDesk((s) => s.requestErrand);
  const cancel = useDesk((s) => s.cancelErrand);
  const title = orderTitle(o.item);
  const pending = errands.find((e) => e.title === title && (e.status === 'proposed' || e.status === 'approved'));
  const cap = reorderCap(o.price);
  const card = [...errands].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).find((e) => e.card)?.card ?? X.orderCard;
  const terms: ErrandTerms = {
    what: X.orderWhat(o.item), when: X.orderWhen, where: X.orderWhere(hostOf(o.url), memberName({ members }, actor)),
    atMost: cap, paidBy: X.orderPaid, card, stopsIf: X.orderStops(m(cap)),
  };
  const confirm = () => {
    const id = request({ title, agent: 'grocery', noticeId: o.noticeId, ...terms });
    setOpen(false);
    useFamilyOS.getState().toast(X.orderAsked, { action: { label: spaceCopy.undo, onPress: () => cancel(id, 'Undone right after asking') }, duration: 5000 });
  };
  const rows: [string, string][] = [
    [X.terms.what, terms.what], ['When', terms.when], [X.terms.where, terms.where], [X.terms.atMost, f.money(cap)],
    [X.terms.paid, terms.paidBy], [X.terms.card, terms.card], [X.terms.stops, f.text(terms.stopsIf)],
  ];
  return (
    <li className="sp-order">
      <div className="sp-order__row">
        <span className="sp-avatar sp-avatar--sq" style={{ color: colors.agents.grocery }} aria-hidden>
          {o.item.charAt(0)}
        </span>
        <span className="sp-order__text">
          <span className={T.smallStrong}>{o.item}</span>
          <span className={T.small}>
            <Link to={`/inbox/${o.noticeId}`} className="sp-order__store">
              {o.store}
            </Link>{' '}
            · last {fmtShortDay(o.lastDate)} · {f.money(o.price)}
          </span>
        </span>
        {pending ? (
          <Link to={`/errands/${pending.id}`} className="desk-link sp-order__pending">
            <StatusChip tone={TONE[pending.status]}>{X.errandStatus[pending.status]}</StatusChip>›
          </Link>
        ) : (
          <button type="button" className="pill pill--secondary sp-pill-sm" aria-expanded={open} aria-controls={panel} aria-label={X.orderLabel(o.item)} onClick={() => setOpen((v) => !v)}>
            {X.order}
            <ArrowUpRight size={13} aria-hidden />
          </button>
        )}
      </div>
      {open && !pending ? (
        <div id={panel} className="sp-proposal" role="group" aria-label={`${X.orderProposal}: ${title}`}>
          <p className={T.meta}>{X.orderProposal}</p>
          <dl className="sp-kv sp-kv--terms">
            {rows.map(([k, v]) => (
              <div key={k}>
                <dt className={T.small}>{k}</dt>
                <dd className={T.smallStrong}>{v}</dd>
              </div>
            ))}
          </dl>
          <div className="sp-confirm__actions">
            <PillButton label={X.orderConfirm} variant="primary" onClick={confirm} />
            <PillButton label={X.notNow} onClick={() => setOpen(false)} />
            <a className="desk-link" href={o.url} target="_blank" rel="noopener noreferrer">
              {X.openStore(o.store)} ↗
            </a>
          </div>
        </div>
      ) : null}
    </li>
  );
}
