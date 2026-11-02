// Family hub (mobile screens/family/FamilyHubScreen.tsx, AGENT_CORE_AND_FAMILY.md
// §4.4): orbit header, completion summary, one card per member (owner first,
// then oldest), and a fixed "+ Add family member" button. Hosts the Add / Edit
// sheets, the member menu and the remove dialog. `/family?add=1` (Profile
// menu → "Add family member") opens the Add sheet at once; a removal
// confirmed on a profile arrives in the navigation state and animates here.
// Desktop (useIsDesktopWeb): FamilyDesktopExtras (MASTER_AGENT.md §7 Phase 4)
// renders under the hub; the mobile layout is untouched.
import { lazy, Suspense, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { AnimatePresence, motion } from 'framer-motion';
import { Plus } from 'lucide-react';
import clsx from 'clsx';
import type { FamilyMember } from '../../services/interfaces';
import { completeCount, sectionsNeedingUpdate, sectionsNotStarted, todoText } from '../../family/model';
import { AGENT_IDS, colors } from '../../theme/tokens';
import { durations } from '../../theme/motion';
import { T } from '../../theme/typography';
import { pageMeta } from '../../mocks/webData';
import { useFamily } from '../../store/useFamily';
import { useEscape } from '../../hooks/useEscape';
import { useHotkeys } from '../../hooks/useHotkeys';
import { usePageMeta } from '../../hooks/usePageMeta';
import { useIsDesktopWeb } from '../../hooks/useIsDesktopWeb';
import { TaskRing, useCountUp } from '../../graphics/Charts';
import { SectionLabel } from '../../components/Labels';
import { OnboardingBackdrop } from '../../components/OnboardingBackdrop';
import { Pressable } from '../../components/Pressable';
import { BackButton } from '../../components/ScreenShell';
import { goBack } from '../../components/navigation';
import { ToastHost } from '../../components/Toast';
import { FamilyOrbit } from './FamilyOrbit';
import { MemberCard } from './MemberCard';
import { MemberMenu } from './MemberMenu';
import { MemberBasicsSheet } from './MemberBasicsSheet';
import { RemoveDialog } from './RemoveDialog';
import { takeRemoval } from './removalQueue';
import './family.css';

const FamilyDesktopExtras = lazy(() => import('../../desktop/spaces/FamilyDesktopExtras'));

const UNDERLINE = `linear-gradient(90deg, ${AGENT_IDS.map((id) => colors.agents[id]).join(', ')})`;

function SummaryCard({ members }: { members: FamilyMember[] }) {
  const done = members.filter((m) => completeCount(m) === 5).length;
  const todo = members.reduce((n, m) => n + sectionsNeedingUpdate(m).length, 0);
  const blank = members.reduce((n, m) => n + sectionsNotStarted(m).length, 0);
  const pct = members.length ? members.reduce((s, m) => s + completeCount(m), 0) / (members.length * 5) : 0;
  const shown = Math.round(useCountUp(pct * 100));
  const sub = todo ? `${todo} ${todo === 1 ? 'section still needs' : 'sections still need'} updating` : (todoText(0, blank) ?? 'Everyone’s details are up to date');
  return (
    <section className="fam-summary card" aria-label={`${done} of ${members.length} profiles complete. ${sub}.`}>
      <TaskRing pct={pct} color={todo || blank ? '#FFB23F' : '#4DD98C'} size={76}>
        <span className={T.stat} style={{ fontSize: '1rem' }} aria-hidden>
          {shown}%
        </span>
      </TaskRing>
      <span className="fam-summary__text" aria-hidden>
        <span className={T.bodyStrong}>
          {done} of {members.length} profiles complete
        </span>
        <span className={T.small}>{sub}</span>
      </span>
    </section>
  );
}

export default function FamilyHub() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const fam = useFamily();
  const desk = useIsDesktopWeb();
  // "Add family member" from the Profile menu arrives as ?add=1.
  const [adding, setAdding] = useState(() => params.get('add') === '1');
  const [editing, setEditing] = useState<FamilyMember | null>(null);
  const [menu, setMenu] = useState<FamilyMember | null>(null);
  const [removing, setRemoving] = useState<FamilyMember | null>(null);
  usePageMeta(pageMeta.family);
  const back = () => goBack(navigate, '/');
  const quiet = !adding && !editing && !menu && !removing;
  useEscape(quiet, back);
  useHotkeys({ Backspace: back }, quiet);

  // Load the family; a removal confirmed on a profile animates here once the cards are in.
  useEffect(() => {
    if (!useFamily.getState().loaded) void fam.load();
    const r = takeRemoval();
    if (r) window.setTimeout(() => void useFamily.getState().remove(r.id, r.reassign), 350);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (params.get('add') === '1') navigate('/family', { replace: true });
  }, [params, navigate]);
  useEffect(() => {
    if (!fam.highlight) return;
    const id = window.setTimeout(fam.clearHighlight, 1800);
    return () => window.clearTimeout(id);
  }, [fam.highlight, fam.clearHighlight]);

  const members = fam.members;
  const n = members.length;
  const todo = members.reduce((k, m) => k + sectionsNeedingUpdate(m).length, 0);
  const blank = members.reduce((k, m) => k + sectionsNotStarted(m).length, 0);

  return (
    <div className="shell fam-page">
      <OnboardingBackdrop />
      <main id="main" className="fam-column">
        <BackButton onClick={back} />
        <h1 className={clsx(T.agentTitle, 'fam-title')}>Family</h1>
        <span className="title-underline" style={{ background: UNDERLINE }} aria-hidden />
        <p className={clsx(T.small, 'fam-subtitle')}>
          {!fam.loaded ? ' ' : todo || blank ? `${n} members · ${todoText(todo, blank)}` : 'Everyone’s details are up to date'}
        </p>
        <FamilyOrbit members={members} />
        {/* Wait for the stored family, so the empty state never flashes and the cards enter once. */}
        {!fam.loaded ? null : n <= 1 ? (
          <p className={`${T.small} t-center fam-empty`}>Add your family so your agents can plan for everyone.</p>
        ) : (
          <SummaryCard members={members} />
        )}
        <SectionLabel className="fam-section">YOUR FAMILY</SectionLabel>
        <ul className="fam-cards">
          <AnimatePresence initial={false}>
            {fam.loaded
              ? members.map((m, i) => (
                  <motion.li key={m.id} layout transition={{ layout: { type: 'spring', stiffness: 120, damping: 22 } }} exit={{ opacity: 0, height: 0, transition: { duration: 0.25 } }}>
                    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: (i * durations.stagger) / 1000, duration: 0.32 }}>
                      <MemberCard
                        member={m}
                        glow={fam.highlight === m.id}
                        removing={fam.removing.includes(m.id)}
                        onOpen={() => navigate(`/family/${m.id}`)}
                        onEdit={() => setEditing(m)}
                        onRemove={() => setRemoving(m)}
                        onMenu={() => setMenu(m)}
                      />
                    </motion.div>
                  </motion.li>
                ))
              : null}
          </AnimatePresence>
        </ul>
      </main>

      <div className="fam-footer">
        <Pressable className="fam-add" onClick={() => setAdding(true)} aria-label="Add family member">
          <Plus size={18} strokeWidth={2.4} aria-hidden />
          <span className={T.bodyStrong} style={{ color: 'inherit' }}>
            Add family member
          </span>
        </Pressable>
      </div>
      {desk ? (
        <Suspense fallback={null}>
          <FamilyDesktopExtras />
        </Suspense>
      ) : null}

      {menu ? (
        <MemberMenu
          member={menu}
          onClose={() => setMenu(null)}
          onEdit={() => {
            setEditing(menu);
            setMenu(null);
          }}
          onRemove={() => {
            setRemoving(menu);
            setMenu(null);
          }}
        />
      ) : null}
      <MemberBasicsSheet
        open={adding}
        onClose={() => setAdding(false)}
        onSubmit={async (b, later) => {
          const m = await fam.add(b);
          setAdding(false);
          if (!later) navigate(`/family/${m.id}/details/basic`);
        }}
      />
      <MemberBasicsSheet
        open={!!editing}
        member={editing ?? undefined}
        onClose={() => setEditing(null)}
        onSubmit={async (b) => {
          if (editing) await fam.updateBasics(editing.id, b);
          setEditing(null);
        }}
      />
      {removing ? (
        <RemoveDialog
          member={removing}
          members={members}
          onCancel={() => setRemoving(null)}
          onConfirm={(reassign) => {
            const id = removing.id;
            setRemoving(null);
            void fam.remove(id, reassign);
          }}
        />
      ) : null}
      <ToastHost bottom="calc(84px + env(safe-area-inset-bottom))" />
    </div>
  );
}
