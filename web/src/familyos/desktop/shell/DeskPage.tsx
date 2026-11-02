// Page template for every desktop page (MASTER_AGENT.md §8 "Layout",
// FamilyOS.mp4 2:40, 4:20, 6:20): optional back button and mini gem on top,
// an icon + title with a thin coloured underline, one honest sentence about
// what the page is (and never does), actions on the right, then the content
// column (max ≈1100 px with the rail) and an optional right rail (≈300 px).
// Below 1024 px the same page renders as one column (rail under the content)
// with no sidebar.
//
//   <DeskPage icon={Inbox} color={colors.agents.calendar} title="Inbox"
//     description="Everything that arrived…" actions={<PillButton …/>}
//     rail={<DeskCard title="Dates spotted">…</DeskCard>}>
//     …sections…
//   </DeskPage>
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';
import { T } from '../../theme/typography';
import { withAlpha } from '../../theme/tokens';
import { usePageMeta } from '../../hooks/usePageMeta';
import { useEscape } from '../../hooks/useEscape';
import { MiniGem } from '../../components/MiniGem';
import { BackButton } from '../../components/ScreenShell';
import { goBack } from '../../components/navigation';
import { ToastHost } from '../../components/Toast';
import './page.css';

export interface DeskPageProps {
  title: string;
  /** One honest sentence: what this page is, and what it never does. */
  description: ReactNode;
  icon?: LucideIcon;
  /** Accent: icon, underline and the faint glow (defaults to a neutral white). */
  color?: string;
  /** CSS background for the title underline (e.g. the five-agent gradient on Today). */
  underline?: string;
  actions?: ReactNode;
  rail?: ReactNode;
  /** Back button with the fallback path for deep links (Esc also goes back). */
  back?: string;
  /** Mini gem at the top centre: true = the family core, a colour = that agent. */
  gem?: boolean | string;
  /** Browser tab title; defaults to "{title} · FamilyOS". */
  metaTitle?: string;
  className?: string;
  children: ReactNode;
}

export function DeskPage({ title, description, icon: Icon, color, underline, actions, rail, back, gem, metaTitle, className, children }: DeskPageProps) {
  const navigate = useNavigate();
  const accent = color ?? '#FFFFFF';
  usePageMeta({ title: metaTitle ?? `${title} · FamilyOS`, description: typeof description === 'string' ? description : title });
  const onBack = () => goBack(navigate, back ?? '/');
  useEscape(!!back, onBack);
  return (
    <div className={clsx('desk-page', rail ? 'desk-page--rail' : null, className)} style={{ ['--desk-accent' as string]: accent }}>
      <div className="desk-page__glow" style={{ background: `radial-gradient(60vmax 32vmax at 60% -8%, ${withAlpha(color ?? '#8073FF', color ? 0.12 : 0.1)}, transparent 62%)` }} aria-hidden />
      {back || gem ? (
        <div className="desk-page__top">
          {back ? <BackButton onClick={onBack} /> : <span className="desk-page__spacer" />}
          {gem ? (
            <span className="desk-page__gem">
              <MiniGem size={56} agentColor={typeof gem === 'string' ? gem : undefined} />
            </span>
          ) : null}
          <span className="desk-page__spacer" />
        </div>
      ) : null}
      <header className="desk-page__head">
        <div className="desk-page__titles">
          <h1 className={clsx(T.agentTitle, 'desk-page__title')}>
            {Icon ? (
              <span className="desk-page__icon" style={{ color: accent }} aria-hidden>
                <Icon size={22} strokeWidth={1.9} />
              </span>
            ) : null}
            {title}
          </h1>
          <span className="title-underline" style={{ background: underline ?? `linear-gradient(90deg, ${accent}, ${withAlpha(accent.startsWith('#') ? accent : '#FFFFFF', 0)})` }} aria-hidden />
          <p className={clsx(T.small, 'desk-page__desc')}>{description}</p>
        </div>
        {actions ? <div className="desk-page__actions">{actions}</div> : null}
      </header>
      <div className="desk-page__body">
        <main id="main" className="desk-page__main">
          {children}
        </main>
        {rail ? <aside className="desk-page__rail">{rail}</aside> : null}
      </div>
      <ToastHost bottom={24} />
    </div>
  );
}

/** A glass section card with an optional small-caps label and action (rails, sections). */
export function DeskCard({ title, sub, action, children, className, id }: { title?: ReactNode; sub?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section className={clsx('desk-card card', className)} id={id} aria-label={typeof title === 'string' ? title : undefined}>
      {title || action ? (
        <div className="desk-card__head">
          {title ? <h2 className={clsx(T.bodyStrong, 'desk-card__title')}>{title}</h2> : null}
          {sub ? <span className={clsx(T.small, 'desk-card__sub')}>{sub}</span> : null}
          {action ? <span className="desk-card__action">{action}</span> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** Status chip with text (colour is never the only signal, §8). */
export type ChipTone = 'missed' | 'overdue' | 'today' | 'changed' | 'draft' | 'approved' | 'done' | 'cancelled' | 'proposed' | 'consented' | 'guardian' | 'adult' | 'child' | 'neutral';

export function StatusChip({ tone, children, className }: { tone: ChipTone; children: ReactNode; className?: string }) {
  return <span className={clsx('desk-chip', `desk-chip--${tone}`, className)}>{children}</span>;
}
