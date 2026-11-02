// Collect from a site, /collect (MASTER_AGENT.md §3.2 Collect 6:10, §7
// Phase 5; FamilyOS.mp4 ≈6:10, frames f_075–f_076). The form — What is this
// for, The site, How long you need — and Open the sitting, which records a
// sitting in the desk store (openSitting, one audit row). No backend yet
// (§1 A5): no browser opens, and the page says so. FamilyOS takes no
// password and stores no session.
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { Download } from 'lucide-react';
import { T } from '../../theme/typography';
import { Pressable } from '../../components/Pressable';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { memberName } from '../../desk/selectors';
import { DeskCard, DeskPage, StatusChip } from '../shell/DeskPage';
import { Field } from './AdminBits';
import { siteHost, SITTING_LENGTHS } from './settingsModel';
import { ADMIN_COPY } from './adminCopy';
import './admin.css';

const C = ADMIN_COPY.collect;

export default function CollectPage() {
  const sittings = useDesk((s) => s.sittings);
  const members = useDesk((s) => s.members);
  const open = useDesk((s) => s.openSitting);
  const now = useNow(30000);
  const f = useDeskFormat(now);
  const [purpose, setPurpose] = useState('');
  const [site, setSite] = useState('');
  const [minutes, setMinutes] = useState(90);
  const [tried, setTried] = useState(false);
  const host = siteHost(site);
  const errors = { purpose: purpose.trim() ? null : 'Say what this sitting is for.', site: host ? null : 'A site address, like portal.riverside-elem.example.' };
  const recent = [...sittings].sort((a, b) => b.openedAt.localeCompare(a.openedAt));

  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    setTried(true);
    if (errors.purpose || errors.site || !host) return;
    open({ purpose: purpose.trim(), site: host, minutes });
    setPurpose('');
    setSite('');
    setTried(false);
    useFamilyOS.getState().toast(`Sitting recorded for ${host}. Nothing was signed in to or kept.`, { duration: 4200 });
  };

  return (
    <DeskPage
      className="adm-page"
      icon={Download}
      title="Collect from a site"
      description={C.description}
      rail={
        <>
          <DeskCard title="Sittings" sub={recent.length ? `${recent.length} this visit` : undefined}>
            {recent.length ? (
              <ul className="adm-list">
                {recent.map((s) => {
                  const ends = new Date(new Date(s.openedAt).getTime() + s.minutes * 60000);
                  const live = ends.getTime() > now.getTime();
                  return (
                    <li key={s.id} className="adm-row adm-row--top">
                      <span className="adm-row__main">
                        <span className={clsx(T.smallStrong, 'adm-row__title')}>{s.purpose}</span>
                        <span className={clsx(T.small, 'adm-row__sub')}>
                          {s.site} · opened by {memberName({ members }, s.openedBy)} · {live ? `until ${f.time(ends.toISOString())}` : `ended ${f.ago(ends.toISOString())}`}
                        </span>
                      </span>
                      <StatusChip tone={live ? 'today' : 'neutral'}>{live ? 'open' : 'ended'}</StatusChip>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className={T.small}>None yet. A sitting you open appears here, and in the Audit.</p>
            )}
          </DeskCard>
          <DeskCard title="What a sitting is">
            <div className="adm-prose">
              <p className={T.small}>A browser of its own, for as long as you chose. You type the password yourself, on the site; FamilyOS never sees it.</p>
              <p className={T.small}>The pages you visit are collected for you to read in the Inbox. When the time is up the browser and its session are thrown away.</p>
              <p className={T.small}>
                For something that should <em>happen</em> on a site — a booking, a payment — ask for an{' '}
                <Link to="/errands" className="desk-link">
                  errand
                </Link>{' '}
                instead.
              </p>
            </div>
          </DeskCard>
        </>
      }
    >
      <DeskCard className="adm-collect">
        <form className="adm-form" onSubmit={submit} noValidate aria-label="Open a sitting">
          <Field label="What is this for" error={tried ? errors.purpose : null}>
            {({ id, describedBy, invalid }) => (
              <input id={id} className="adm-input" value={purpose} placeholder="School portal circulars" aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setPurpose(e.target.value)} />
            )}
          </Field>
          <Field label="The site" error={tried ? errors.site : null}>
            {({ id, describedBy, invalid }) => (
              <input
                id={id}
                className="adm-input"
                value={site}
                placeholder="portal.riverside-elem.example"
                inputMode="url"
                autoCapitalize="none"
                spellCheck={false}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setSite(e.target.value)}
              />
            )}
          </Field>
          <Field label="How long you need">
            {({ id }) => (
              <select id={id} className="adm-select" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
                {SITTING_LENGTHS.map((l) => (
                  <option key={l.minutes} value={l.minutes}>
                    {l.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <p className={T.small}>{C.promise}</p>
          <div className="adm-actions">
            <Pressable type="submit" className="pill pill--primary">
              Open the sitting
            </Pressable>
          </div>
          <p className={clsx(T.small, 'adm-row__sub')}>{C.preview}</p>
        </form>
      </DeskCard>
    </DeskPage>
  );
}
