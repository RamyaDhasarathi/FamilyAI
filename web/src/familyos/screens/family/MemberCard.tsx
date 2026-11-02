// One member on the Family hub (mobile screens/family/MemberCard.tsx). Click
// opens the profile; the ⋯ button, a right-click or a long-press opens the
// Edit / Remove menu; on touch, swiping left reveals Edit and Remove (the
// owner has no Remove). A just-added card glows; a removed one dissolves into
// particles and collapses.
import { useRef } from 'react';
import { animate, motion, useMotionValue, useTransform } from 'framer-motion';
import { useDrag } from '@use-gesture/react';
import { Ellipsis, Pencil, Trash } from 'lucide-react';
import clsx from 'clsx';
import type { FamilyMember } from '../../services/interfaces';
import { SECTION_IDS, ageGroupOf, ageOf, ageText, completionOf, displayName, relationshipLabel, sectionMeta, sectionsNeedingUpdate, sectionsNotStarted, stageOf } from '../../family/model';
import { colors } from '../../theme/tokens';
import { fm } from '../../theme/motion';
import { T } from '../../theme/typography';
import { AMBER, CompletionRing, GREEN, MemberAvatar, Tag } from '../../components/family/MemberBits';
import { Pressable } from '../../components/Pressable';
import { Dissolve } from './Dissolve';

/** How far the card slides to show its actions: two buttons, or Edit alone (the owner). */
const OPEN = 132;
const OPEN_ONE = 70;

function memberA11y(m: FamilyMember) {
  const n = sectionsNeedingUpdate(m).length;
  const blank = sectionsNotStarted(m).length;
  const rel = m.isOwner ? 'you' : relationshipLabel(m).toLowerCase();
  const state = n ? `${n === 1 ? 'one section needs' : `${n} sections need`} updating` : blank ? `${blank === 1 ? 'one section' : `${blank} sections`} not started` : 'all details up to date';
  return `${displayName(m)}, ${rel}, ${ageText(ageOf(m.dateOfBirth))}, ${state}. Opens their profile`;
}

interface Props {
  member: FamilyMember;
  glow: boolean;
  removing: boolean;
  onOpen: () => void;
  onEdit: () => void;
  onRemove: () => void;
  onMenu: () => void;
}

export function MemberCard({ member: m, glow, removing, onOpen, onEdit, onRemove, onMenu }: Props) {
  const x = useMotionValue(0);
  const hold = useRef<number | null>(null);
  const held = useRef(false);
  const age = ageOf(m.dateOfBirth);
  const st = stageOf(m);
  const todo = sectionsNeedingUpdate(m);
  const blank = sectionsNotStarted(m).length;
  const group = ageGroupOf(age);
  const canRemove = !m.isOwner;
  const open = canRemove ? OPEN : OPEN_ONE;
  const actionsOpacity = useTransform(x, [-open, -20, 0], [1, 0.3, 0]);
  const close = () => animate(x, 0, fm.snappy);

  // Touch: swipe left to reveal the actions (mouse users have the ⋯ button).
  const bind = useDrag(
    ({ movement: [mx], velocity: [vx], direction: [dx], last, memo = x.get(), event }) => {
      if ((event as PointerEvent).pointerType === 'mouse') return memo;
      if (hold.current) window.clearTimeout(hold.current);
      x.set(Math.min(0, Math.max(-open - 30, memo + mx)));
      if (last) animate(x, x.get() < -open / 2 || (vx > 0.5 && dx < 0) ? -open : 0, fm.snappy);
      return memo;
    },
    { axis: 'x', filterTaps: true, pointer: { touch: true } }
  );

  const meta = `${m.isOwner ? 'You' : relationshipLabel(m)} · ${ageText(age)} · ${st.name}`;
  return (
    <motion.div
      className={clsx('member-card-wrap', removing && 'is-removing')}
      animate={removing ? { opacity: 0, scale: 0.96 } : { opacity: 1, scale: 1 }}
      transition={{ duration: removing ? 0.48 : 0.22 }}
    >
      <motion.div className="member-card__actions" style={{ opacity: actionsOpacity }} aria-hidden>
        <Pressable className="member-card__act member-card__act--edit" onClick={() => { close(); onEdit(); }} aria-label={`Edit ${displayName(m)}`} tabIndex={-1}>
          <Pencil size={18} aria-hidden />
        </Pressable>
        {canRemove ? (
          <Pressable className="member-card__act member-card__act--remove" onClick={() => { close(); onRemove(); }} aria-label={`Remove ${displayName(m)} from family`} tabIndex={-1}>
            <Trash size={18} aria-hidden />
          </Pressable>
        ) : null}
      </motion.div>
      <motion.div {...(bind() as object)} className={clsx('member-card', glow && 'is-glow')} style={{ x, touchAction: 'pan-y', '--glow': st.accent } as never}>
        <button
          type="button"
          className="member-card__open"
          aria-describedby={`mc-${m.id}`}
          onClick={() => {
            if (held.current) {
              held.current = false;
              return;
            }
            if (x.get() < -4) close();
            else onOpen();
          }}
          onContextMenu={(e) => {
            e.preventDefault();
            onMenu();
          }}
          onPointerDown={(e) => {
            if (e.pointerType === 'mouse') return;
            held.current = false;
            hold.current = window.setTimeout(() => {
              held.current = true;
              onMenu();
            }, 420);
          }}
          onPointerUp={() => hold.current && window.clearTimeout(hold.current)}
          onPointerCancel={() => hold.current && window.clearTimeout(hold.current)}
        >
          <MemberAvatar member={m} size={56} animated={m.isOwner} />
          <span className="member-card__text">
            <span className="member-card__name-row">
              <span className={clsx(T.bodyStrong, 'member-card__name')}>{m.fullName}</span>
              {m.isOwner ? <span className="member-card__you t-chip">You</span> : null}
            </span>
            <span className={clsx(T.small, 'member-card__meta')}>{meta}</span>
            <span className="member-card__tags">
              {todo.length ? (
                todo.map((s) => <Tag key={s} text={sectionMeta(s, group).tag} color={AMBER} />)
              ) : blank ? (
                <Tag text={blank === SECTION_IDS.length ? 'Details not started' : `${blank} ${blank === 1 ? 'section' : 'sections'} not started`} color={colors.muted} />
              ) : (
                <Tag text="All details up to date" color={GREEN} />
              )}
            </span>
          </span>
          <CompletionRing value={completionOf(m)} size={28} stroke={3} color={todo.length ? AMBER : blank ? colors.muted : GREEN} />
        </button>
        <span id={`mc-${m.id}`} className="sr-only">
          {memberA11y(m)}. Opens their profile.
        </span>
        <Pressable className="member-card__more" onClick={onMenu} aria-label={`More options for ${displayName(m)}`} aria-haspopup="dialog" lift={false}>
          <Ellipsis size={18} aria-hidden />
        </Pressable>
      </motion.div>
      {removing ? (
        <span className="member-card__dissolve">
          <Dissolve color={st.accent} size={56} />
        </span>
      ) : null}
    </motion.div>
  );
}
