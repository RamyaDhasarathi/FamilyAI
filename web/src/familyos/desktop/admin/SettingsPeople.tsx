// Settings → Household: members and consent (MASTER_AGENT.md §3.2 Settings
// 0:35–1:20 and 7:30–9:30; frames f_009, f_012, f_097–f_105). Members with
// guardian / adult / child chips ("you" on the signed-in one); a child has
// "no account — a data subject only", their school, the consent chip, and
// Erase (the existing Remove from family flow on their profile, which asks
// again). Adults: Sign out everywhere (confirm). Consent for the children:
// who verified it, the notice date, Withdraw — with the warning that it
// starts an erasure — behind a confirm.
import { Link } from 'react-router';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { fmtShortDay } from '../../desk/format';
import { memberName } from '../../desk/selectors';
import { DeskCard, StatusChip } from '../shell/DeskPage';
import { Initial } from './AdminBits';
import { useConfirm } from './useConfirm';
import { ADMIN_COPY } from './adminCopy';

const C = ADMIN_COPY.settings;
const toast = (t: string) => useFamilyOS.getState().toast(t, { duration: 4200 });

export function MembersCard() {
  const members = useDesk((s) => s.members);
  const children = useDesk((s) => s.children);
  const consents = useDesk((s) => s.consents);
  const actor = useDesk((s) => s.actor);
  const signOut = useDesk((s) => s.signOutEverywhere);
  const [dialog, ask] = useConfirm();
  return (
    <DeskCard id="members" title="Members" sub={`${members.length} people · ${members.filter((m) => m.hasAccount).length} sign in`}>
      <ul className="adm-list">
        {members.map((m) => {
          const kid = children.find((c) => c.memberId === m.id);
          const consent = consents.find((c) => c.childId === m.id);
          return (
            <li key={m.id} className="adm-row">
              <Initial letter={m.initial} />
              <span className="adm-row__main">
                <span className={clsx(T.bodyStrong, 'adm-row__title')}>
                  {m.name}
                  <StatusChip tone={m.role}>{m.role}</StatusChip>
                  {m.id === actor ? <StatusChip tone="neutral">you</StatusChip> : null}
                </span>
                <span className={clsx(T.small, 'adm-row__sub')}>
                  {m.hasAccount ? (m.email ?? 'signs in with a family account') : 'no account — a data subject only'}
                  {kid ? ` · ${kid.school}, ${kid.grade.toLowerCase()}` : ''}
                </span>
              </span>
              <span className="adm-row__actions">
                {m.role === 'child' ? (
                  <>
                    {consent ? <StatusChip tone={consent.withdrawnAt ? 'neutral' : 'consented'}>{consent.withdrawnAt ? 'consent withdrawn' : 'consented'}</StatusChip> : <StatusChip tone="overdue">no consent</StatusChip>}
                    <Link to="/agents/education" className="pill pill--secondary" aria-label={`School: ${m.name}'s school space`}>
                      School
                    </Link>
                    <Link
                      to={`/family/${m.id}`}
                      className="pill adm-pill--soft-danger"
                      aria-label={`Erase ${m.name}: opens ${m.name}'s profile, where Remove from family asks you to confirm`}
                      title="Opens the profile; Remove from family asks you to confirm"
                    >
                      Erase…
                    </Link>
                  </>
                ) : (
                  <PillButton
                    label="Sign out everywhere"
                    aria-label={`Sign ${m.name} out everywhere`}
                    onClick={() =>
                      ask({
                        title: `Sign ${m.name} out everywhere?`,
                        body: `Every browser and phone where ${m.name} is signed in is signed out${m.id === actor ? ', including this one the next time it checks' : ''}. Nothing else changes.`,
                        confirm: 'Sign out everywhere',
                        run: () => {
                          signOut(m.id);
                          toast(`${m.name} is signed out everywhere. Written to the Audit.`);
                        },
                      })
                    }
                  />
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {dialog}
    </DeskCard>
  );
}

export function ConsentCard({ ago }: { ago: (i: string) => string }) {
  const members = useDesk((s) => s.members);
  const consents = useDesk((s) => s.consents);
  const withdraw = useDesk((s) => s.withdrawConsent);
  const [dialog, ask] = useConfirm();
  const name = (id: string) => memberName({ members }, id);
  return (
    <DeskCard id="consent" title="Consent for the children" sub="kept as evidence even after it ends">
      {consents.length ? (
        <ul className="adm-list">
          {consents.map((c) => {
            const child = members.find((m) => m.id === c.childId);
            return (
              <li key={c.childId} className="adm-row">
                <Initial letter={child?.initial ?? '?'} />
                <span className="adm-row__main">
                  <span className={T.bodyStrong}>{name(c.childId)}</span>
                  <span className={clsx(T.small, 'adm-row__sub')}>
                    by {name(c.verifiedBy)} · verified as guardian · notice of {fmtShortDay(c.noticeDate)}
                    {c.withdrawnAt ? ` · withdrawn ${ago(c.withdrawnAt)}` : ''}
                  </span>
                </span>
                <span className="adm-row__actions">
                  <StatusChip tone={c.withdrawnAt ? 'neutral' : 'consented'}>{c.withdrawnAt ? 'withdrawn' : 'active'}</StatusChip>
                  {c.withdrawnAt ? null : (
                    <PillButton
                      label="Withdraw"
                      className="adm-pill--soft-danger"
                      aria-label={`Withdraw consent for ${name(c.childId)}`}
                      onClick={() =>
                        ask({
                          title: `Withdraw consent for ${name(c.childId)}?`,
                          body: C.consentWarning.replace('that child', name(c.childId)),
                          confirm: 'Withdraw and erase',
                          cancel: 'Keep consent',
                          danger: true,
                          run: () => {
                            withdraw(c.childId);
                            toast(`Consent for ${name(c.childId)} withdrawn. The erasure has started.`);
                          },
                        })
                      }
                    />
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className={T.small}>No consent on record.</p>
      )}
      <p className="adm-note adm-note--danger t-small" style={{ marginTop: 12 }}>
        {C.consentWarning}
      </p>
      {dialog}
    </DeskCard>
  );
}
