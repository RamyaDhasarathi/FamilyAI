// Member profile (mobile screens/family/MemberProfileScreen.tsx,
// AGENT_CORE_AND_FAMILY.md §4.6): floating avatar hero in stage-tinted dust,
// completion, one row per details section (opens the wizard there), Edit
// basics and Remove from family. The details wizard renders on top of this
// page at /family/:id/details/:section.
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import { motion, useAnimationControls } from 'framer-motion';
import { ChevronRight, Ellipsis } from 'lucide-react';
import clsx from 'clsx';
import { SECTION_IDS, ageGroupOf, ageOf, ageText, completeCount, displayName, relationshipLabel, sectionMeta, stageOf } from '../../family/model';
import { sectionSummary } from '../../family/summary';
import { colors, hexToRgb, withAlpha } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { pageMeta, webCopy } from '../../mocks/webData';
import { useFamily } from '../../store/useFamily';
import { useEscape } from '../../hooks/useEscape';
import { useHotkeys } from '../../hooks/useHotkeys';
import { usePageMeta } from '../../hooks/usePageMeta';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import { SectionLabel } from '../../components/Labels';
import { OnboardingBackdrop } from '../../components/OnboardingBackdrop';
import { Pressable } from '../../components/Pressable';
import { BackButton } from '../../components/ScreenShell';
import { goBack } from '../../components/navigation';
import { ToastHost } from '../../components/Toast';
import { AMBER, CompletionRing, GREEN, MemberAvatar, StatusPill } from '../../components/family/MemberBits';
import { MemberBasicsSheet } from './MemberBasicsSheet';
import { MemberMenu } from './MemberMenu';
import { RemoveDialog } from './RemoveDialog';
import { queueRemoval } from './removalQueue';
import { SectionIcon } from './SectionIcon';
import './family.css';

const HERO = 140;
const DUST = 260;

/** Dust halo in the member's stage colour, drawn by the shared mini renderer. */
function HeroDust({ accent }: { accent: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    let alive = true;
    let off = () => {};
    const tint = hexToRgb(accent);
    let clock = 0;
    void import('../../engine/miniRenderer').then((m) => {
      if (!alive || m.miniFailed()) return;
      off = m.register({
        canvas: c,
        visible: true,
        frame(dt) {
          if (!reduced) clock += dt;
          return {
            w: DUST,
            h: DUST,
            ambient: {
              ph: ((clock / 72) * Math.PI * 2) % (Math.PI * 2),
              center: [DUST / 2, DUST / 2],
              radius: HERO / 2 + 6,
              halo: tint,
              haloAmt: 0.55,
              dustAmt: 1.4,
              dustCol: [tint[0] * 0.7 + 0.25, tint[1] * 0.7 + 0.25, tint[2] * 0.7 + 0.25],
            },
          };
        },
      });
    });
    return () => {
      alive = false;
      off();
    };
  }, [accent, reduced]);
  return <canvas ref={ref} className="profile-hero__dust" style={{ width: DUST, height: DUST }} aria-hidden />;
}

export default function MemberProfile() {
  const { id = '' } = useParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const members = useFamily((s) => s.members);
  const loaded = useFamily((s) => s.loaded);
  const load = useFamily((s) => s.load);
  const updateBasics = useFamily((s) => s.updateBasics);
  const m = members.find((x) => x.id === id);
  const owner = members.find((x) => x.isOwner);
  const [editing, setEditing] = useState(false);
  const [menu, setMenu] = useState(false);
  const [removing, setRemoving] = useState(false);
  const squash = useAnimationControls();
  const overlay = pathname.includes('/details');
  usePageMeta(pageMeta.member(m ? displayName(m) : 'Family member'));
  const back = () => goBack(navigate, '/family');
  const quiet = !overlay && !editing && !menu && !removing;
  useEscape(quiet, back);
  useHotkeys({ Backspace: back }, quiet);
  useEffect(() => {
    if (!loaded) void load();
  }, [loaded, load]);

  if (!m) {
    return (
      <div className="shell fam-page">
        <OnboardingBackdrop />
        <main id="main" className="fam-column">
          <BackButton onClick={back} />
          {loaded ? <p className={`${T.small} fam-subtitle`}>{webCopy.notFound.body}</p> : null}
        </main>
      </div>
    );
  }
  const age = ageOf(m.dateOfBirth);
  const group = ageGroupOf(age);
  const st = stageOf(m);
  const done = completeCount(m);
  const wobble = () => {
    void squash.start(
      reduced
        ? { scaleX: [1, 1.04, 1], scaleY: [1, 0.96, 1], transition: { duration: 0.3 } }
        : { scaleX: [1, 1.12, 0.95, 1.02, 1], scaleY: [1, 0.88, 1.05, 0.98, 1], transition: { duration: 0.7, ease: 'easeOut' } }
    );
  };

  return (
    <div className="shell fam-page">
      <OnboardingBackdrop />
      <main id="main" className="fam-column profile">
        <div className="profile__bar">
          <BackButton onClick={back} label="Back to Family" />
          <Pressable className="round-btn" onClick={() => setMenu(true)} aria-label={webCopy.more} aria-haspopup="dialog">
            <Ellipsis size={20} aria-hidden />
          </Pressable>
        </div>
        <div className="profile-hero">
          <HeroDust accent={st.accent} />
          <motion.div className="profile-hero__bob" animate={reduced ? undefined : { y: [0, -5, 0, 5, 0] }} transition={{ duration: 5.7, repeat: Infinity, ease: 'easeInOut' }}>
            <motion.button type="button" className="profile-hero__btn" animate={squash} onClick={wobble} aria-label={`${displayName(m)}'s avatar, stage ${st.stage}, ${st.name}`}>
              <MemberAvatar member={m} size={HERO} animated />
            </motion.button>
          </motion.div>
        </div>
        <h1 className={`${T.greeting} t-center`}>{m.fullName}</h1>
        <p className={`${T.small} t-center profile__sub`}>
          {relationshipLabel(m)} · {ageText(age)}
        </p>
        <p className="profile__stage t-chip" style={{ color: st.accent, borderColor: withAlpha(st.accent, 0.5) }}>
          Stage {st.stage} · {st.name}
        </p>
        <div className="profile__completion card">
          <CompletionRing value={done / 5} size={44} stroke={4} color={done === 5 ? GREEN : AMBER} />
          <span className={T.bodyStrong}>{done} of 5 sections complete</span>
        </div>

        <SectionLabel className="fam-section">DETAILS</SectionLabel>
        <ul className="profile__rows">
          {SECTION_IDS.map((sid) => {
            const meta = sectionMeta(sid, group);
            const sec = m.sections[sid];
            return (
              <li key={sid}>
                <Pressable
                  className="profile-row card hoverable"
                  onClick={() => navigate(`/family/${m.id}/details/${sid}`, { replace: true })}
                  pressScale={0.98}
                >
                  <span className="profile-row__icon" style={{ background: withAlpha(meta.color, 0.16), borderColor: withAlpha(meta.color, 0.45) }}>
                    <SectionIcon id={sid} group={group} size={18} color={meta.color} />
                  </span>
                  <span className="profile-row__text">
                    <span className={T.bodyStrong}>{meta.title}</span>
                    <span className={clsx(T.small, 'profile-row__sub')}>{sectionSummary(m, sid, members, owner)}</span>
                    <span>
                      <StatusPill status={sec.status} />
                    </span>
                  </span>
                  <ChevronRight size={18} color={colors.muted} aria-hidden />
                </Pressable>
              </li>
            );
          })}
        </ul>
        {!m.isOwner ? (
          <Pressable className="profile__remove" onClick={() => setRemoving(true)} lift={false}>
            <span className={T.bodyStrong} style={{ color: 'var(--danger)' }}>
              Remove from family
            </span>
          </Pressable>
        ) : null}
      </main>

      {menu ? (
        <MemberMenu
          member={m}
          onClose={() => setMenu(false)}
          onEdit={() => {
            setMenu(false);
            setEditing(true);
          }}
          onRemove={() => {
            setMenu(false);
            setRemoving(true);
          }}
        />
      ) : null}
      <MemberBasicsSheet
        open={editing}
        member={m}
        onClose={() => setEditing(false)}
        onSubmit={async (b) => {
          await updateBasics(m.id, b);
          setEditing(false);
        }}
      />
      {removing ? (
        <RemoveDialog
          member={m}
          members={members}
          onCancel={() => setRemoving(false)}
          onConfirm={(reassign) => {
            setRemoving(false);
            // Back to the hub first; the removal animates there (§4.9).
            queueRemoval({ id: m.id, reassign });
            back();
          }}
        />
      ) : null}
      <ToastHost bottom={24} />
    </div>
  );
}
