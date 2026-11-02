// "The run" and "How it runs" (MASTER_AGENT.md §3.2 Errands 6:00–6:10;
// frames f_071–f_074). Numbered steps with the time each happened and, where
// the run kept a screenshot, a generated placeholder picture (a drawn browser
// frame — never a real screenshot, §0.3.5). Before a run there is one honest
// line instead: waiting for a guardian, approved and about to start, or
// cancelled before it ran.
import { Link } from 'react-router';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { useDesk } from '../../desk/store';
import type { Errand, ErrandStep } from '../../desk/types';
import { DeskCard, StatusChip } from '../shell/DeskPage';
import { siteOf } from './errandModel';
import { ADMIN_COPY } from './adminCopy';

const C = ADMIN_COPY.errands;

export function ErrandRun({ errand: e, text, ago }: { errand: Errand; text: (s: string) => string; ago: (i: string) => string }) {
  const site = siteOf(e.where);
  if (e.status !== 'done' || !e.steps.length) {
    const [title, line] =
      e.status === 'proposed'
        ? ['The run', 'Not started. It runs only after a guardian approves exactly what is written down.']
        : e.status === 'approved'
          ? ['Approved', `Starting in a fresh browser with your signed-in session on ${site}. Steps appear here as they happen.`]
          : e.status === 'cancelled'
            ? ['The run', `Cancelled before it ran.${e.cancelledReason ? ` ${e.cancelledReason}` : ''} Nothing was bought or booked.`]
            : ['The run', 'Done. No steps were kept for this run.'];
    return (
      <DeskCard title={title}>
        <p className={T.small}>{line}</p>
      </DeskCard>
    );
  }
  return (
    <DeskCard title="The run" sub={`${e.steps.length} steps · ${site}`}>
      <ol className="adm-steps">
        {e.steps.map((s, i) => (
          <li key={i} className="adm-step">
            <span className="adm-step__n" aria-hidden>
              {i + 1}
            </span>
            <div>
              <p className={T.body}>
                <span className="sr-only">Step {i + 1}: </span>
                {text(s.text)}
              </p>
              <p className={clsx(T.small, 'adm-row__sub')}>{ago(s.at)}</p>
              {s.image ? <Shot step={s} n={i + 1} site={site} /> : null}
            </div>
          </li>
        ))}
      </ol>
    </DeskCard>
  );
}

/** A drawn stand-in for the screenshot kept at a step. */
function Shot({ step, n, site }: { step: ErrandStep; n: number; site: string }) {
  const kind = step.image?.includes('receipt') ? 'receipt' : step.image?.includes('fee') ? 'row' : 'list';
  const line = (x: number, y: number, w: number, o = 0.12) => <rect x={x} y={y} width={w} height="7" rx="3.5" fill={`rgba(255,255,255,${o})`} />;
  return (
    <figure className="adm-shot" role="img" aria-label={`Placeholder for the screenshot kept at step ${n} on ${site}. This demo keeps no real screenshots.`}>
      <div className="adm-shot__bar" aria-hidden>
        <span className="adm-shot__dot" />
        <span className="adm-shot__dot" />
        <span className="adm-shot__dot" />
        <span className="adm-shot__url">{site}</span>
      </div>
      <svg viewBox="0 0 440 150" aria-hidden>
        <rect x="0" y="0" width="440" height="150" fill="rgba(255,255,255,0.015)" />
        {line(20, 18, 120, 0.22)}
        {kind === 'receipt' ? (
          <>
            <circle cx="220" cy="62" r="20" fill="rgba(63,203,126,0.16)" stroke="rgba(63,203,126,0.7)" strokeWidth="2" />
            <path d="M211 62 l6 6 l12 -13" fill="none" stroke="#3FCB7E" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            {line(160, 96, 120, 0.18)}
            {line(180, 112, 80)}
          </>
        ) : (
          [0, 1, 2, 3].map((r) => (
            <g key={r}>
              <rect x="20" y={40 + r * 26} width="400" height="20" rx="6" fill={kind === 'row' && r === 1 ? 'rgba(97,184,255,0.16)' : 'rgba(255,255,255,0.04)'} stroke={kind === 'row' && r === 1 ? 'rgba(97,184,255,0.6)' : 'none'} />
              {line(30, 46 + r * 26, 150 - r * 18, kind === 'row' && r === 1 ? 0.3 : 0.12)}
              {line(360, 46 + r * 26, 48, 0.1)}
            </g>
          ))
        )}
      </svg>
      <span className="adm-shot__tag">
        <StatusChip tone="neutral">placeholder</StatusChip>
      </span>
    </figure>
  );
}

/** Rail: How it runs, the errand's own history from the Audit, and its source. */
export function HowItRuns({ errand: e, money, text, stamp }: { errand: Errand; money: (n: number) => string; text: (s: string) => string; stamp: (i: string) => string }) {
  const audit = useDesk((s) => s.audit);
  const rows = audit.filter((a) => a.raw?.errandId === e.id).slice(-6).reverse();
  return (
    <>
      <DeskCard title="How it runs">
        <div className="adm-prose">
          {C.howItRuns.map((p) => (
            <p key={p} className={T.small}>
              {p}
            </p>
          ))}
          <p className={T.small}>
            Here: <strong>{siteOf(e.where)}</strong>, never more than <strong>{money(e.atMost)}</strong>. Paid: {text(e.paidBy)}.
          </p>
        </div>
      </DeskCard>
      <DeskCard title="What happened" sub="from the Audit">
        {rows.length ? (
          <ul className="adm-list">
            {rows.map((a) => (
              <li key={a.id} className="adm-row adm-row--top">
                <span className={clsx(T.small, 'adm-row__main')}>
                  <span style={{ color: 'var(--ink)' }}>{text(a.sentence)}</span>
                  <span className="adm-row__sub">{stamp(a.at)}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={T.small}>Nothing recorded yet.</p>
        )}
        <div className="adm-links" style={{ marginTop: 10 }}>
          <Link to="/audit" className="desk-link">
            The Audit ›
          </Link>
          {e.noticeId ? (
            <Link to={`/inbox/${e.noticeId}`} className="desk-link">
              The notice ›
            </Link>
          ) : null}
        </div>
      </DeskCard>
    </>
  );
}
