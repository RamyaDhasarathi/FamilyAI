// Member details wizard (mobile screens/family/MemberWizardScreen.tsx,
// AGENT_CORE_AND_FAMILY.md §4.7, design.md §13.6). A full-height glass sheet
// over the member's profile, stepping through the five sections and a
// review. Six tappable progress segments in each section's colour; content
// slides between steps and the glow cross-fades to the next colour. "Skip for
// now" marks a section "needs update"; "Save and continue" validates first;
// Close, Esc and leaving the page save what was typed. The URL carries the
// step (/family/:id/details/:section), so a step can be linked to directly.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useParams } from 'react-router';
import { AnimatePresence, motion } from 'framer-motion';
import { ShieldCheck } from 'lucide-react';
import clsx from 'clsx';
import type { MemberBasics, SectionStatus } from '../../services/interfaces';
import { REVIEW_COLOR, adultsOf, ageGroupOf, ageOf, displayName, sectionMeta } from '../../family/model';
import { fieldValue, fieldsFor, validateField } from '../../family/fields';
import { withAlpha } from '../../theme/tokens';
import { springs } from '../../theme/motion';
import { T } from '../../theme/typography';
import { useFamily } from '../../store/useFamily';
import { useEscape } from '../../hooks/useEscape';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import { ClosePill, PillButton } from '../../components/Pills';
import { AMBER, MemberAvatar } from '../../components/family/MemberBits';
import { WizardFields } from './WizardFields';
import { WizardReview } from './WizardReview';
import { SectionIcon } from './SectionIcon';
import { STEPS, draftAge, sameDraft, type Step } from './wizardModel';
import './family.css';
import { API_ENABLED } from '../../services/api';
import { storageNote } from '../../family/serverFields';

export default function MemberWizard() {
  const { id = '', section } = useParams();
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const members = useFamily((s) => s.members);
  const saveSection = useFamily((s) => s.saveSection);
  const updateBasics = useFamily((s) => s.updateBasics);
  const member = members.find((m) => m.id === id);
  const step: Step = STEPS.includes(section as Step) ? (section as Step) : 'basic';
  const panel = useRef<HTMLDivElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const busy = useRef(false);
  const closing = useRef(false);
  // 0 until the first step change: the sheet slides up, so the first step needs no slide of its own.
  const [dir, setDir] = useState(0);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [base, setBase] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  // Focus lands on the sheet itself, so no control shows a ring until the user tabs.
  useFocusTrap(panel, !!member, { initial: panel });

  // Fresh draft whenever the step changes (adjusted during render, not in an effect).
  const [draftFor, setDraftFor] = useState<string | null>(null);
  const key = member ? `${member.id}:${step}` : null;
  if (member && key !== draftFor) {
    setDraftFor(key);
    if (step !== 'review') {
      const a = ageOf(member.dateOfBirth);
      const d: Record<string, unknown> = { ...member.sections[step].data };
      for (const f of fieldsFor(step, member, a, ageGroupOf(a))) d[f.key] = fieldValue(f, member, member.sections[step].data);
      setDraft(d);
      setBase(d);
    }
    setErrors({});
  }
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0 });
  }, [step]);

  const age = member ? draftAge(draft.dateOfBirth, ageOf(member.dateOfBirth)) : 0;
  const group = ageGroupOf(age);
  const fields = useMemo(() => (member && step !== 'review' ? fieldsFor(step, { ...member, ...(draft as object) }, age, group) : []), [member, step, draft, age, group]);
  const adults = member ? adultsOf(members).filter((a) => a.id !== member.id) : [];
  const visible = useCallback(() => fields.filter((f) => !f.when || f.when(draft, { ...member!, ...(draft as object) })), [fields, draft, member]);
  const check = useCallback(() => {
    const e: Record<string, string | null> = {};
    for (const f of visible()) e[f.key] = validateField(f, draft[f.key]);
    return e;
  }, [visible, draft]);

  /** Write the current step: basics to the member, the rest to the section. */
  const persist = useCallback(
    async (status: SectionStatus) => {
      if (!member || step === 'review') return;
      const patch: Partial<MemberBasics> = {};
      const data: Record<string, unknown> = { ...member.sections[step].data };
      for (const f of fields) {
        if (f.basics) {
          const v = draft[f.key];
          if (v !== (member as unknown as Record<string, unknown>)[f.basics]) (patch as Record<string, unknown>)[f.basics] = typeof v === 'string' ? v.trim() || undefined : v;
        } else data[f.key] = draft[f.key];
      }
      if (Object.keys(patch).length) await updateBasics(member.id, patch);
      await saveSection(member.id, step, data, status);
    },
    [member, step, fields, draft, updateBasics, saveSection]
  );

  /** Keep edits when leaving a step without its buttons: complete if valid, else needing an update. */
  const saveCurrent = useCallback(async () => {
    if (!member || step === 'review' || busy.current || sameDraft(draft, base)) return;
    busy.current = true;
    const e = check();
    await persist(visible().every((f) => !e[f.key]) ? 'complete' : 'needsUpdate');
    busy.current = false;
  }, [member, step, draft, base, check, persist, visible]);
  // Leaving the page another way (browser back) still saves the step.
  const latestSave = useRef(saveCurrent);
  useEffect(() => {
    latestSave.current = saveCurrent;
  });
  useEffect(
    () => () => {
      if (!closing.current) void latestSave.current();
    },
    []
  );

  const go = (to: Step) => {
    setDir(STEPS.indexOf(to) >= STEPS.indexOf(step) ? 1 : -1);
    navigate(`/family/${id}/details/${to}`, { replace: true });
  };
  const next = () => go(STEPS[Math.min(STEPS.length - 1, STEPS.indexOf(step) + 1)]);
  const close = async () => {
    closing.current = true;
    await saveCurrent();
    navigate(`/family/${id}`, { replace: true });
  };
  useEscape(!!member, () => void close());

  const saveAndContinue = async () => {
    if (busy.current) return;
    const e = check();
    setErrors(e);
    const first = visible().find((f) => e[f.key]);
    if (first) {
      const el = scroll.current?.querySelector<HTMLElement>(`[data-field-key="${first.key}"]`);
      el?.scrollIntoView({ block: 'center', behavior: reduced ? 'auto' : 'smooth' });
      el?.querySelector<HTMLElement>('[data-field-input]')?.focus({ preventScroll: true });
      return;
    }
    busy.current = true;
    await persist('complete');
    busy.current = false;
    next();
  };
  const skip = async () => {
    if (busy.current) return;
    busy.current = true;
    await persist('needsUpdate');
    busy.current = false;
    next();
  };

  if (!member) return null;
  const meta = step === 'review' ? null : sectionMeta(step, group);
  const color = meta?.color ?? REVIEW_COLOR;
  const idx = STEPS.indexOf(step);
  const title = meta?.title ?? 'Review';
  const slide = reduced || dir === 0 ? 0 : 40;

  return createPortal(
    <div className="wizard-root">
      <motion.div className="wizard-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }} aria-hidden onClick={() => void close()} />
      <motion.div
        ref={panel}
        className="wizard"
        role="dialog"
        aria-modal="true"
        aria-label={`${displayName(member)}'s details`}
        tabIndex={-1}
        initial={{ opacity: 0, y: reduced ? 0 : 60 }}
        animate={{ opacity: 1, y: 0 }}
        transition={reduced ? { duration: 0.15 } : { type: 'spring', ...springs.soft }}
      >
        <AnimatePresence initial={false}>
          <motion.span
            key={color}
            className="wizard__glow"
            style={{ background: `linear-gradient(${withAlpha(color, 0.2)}, ${withAlpha(color, 0)} 60%)` }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.45 }}
            aria-hidden
          />
        </AnimatePresence>
        <header className="wizard__head">
          <MemberAvatar member={member} size={40} />
          <span className="wizard__who">
            <span className={T.bodyStrong}>{displayName(member)}</span>
            <span className={T.small} aria-live="polite">
              Step {idx + 1} of 6 · {title}
            </span>
          </span>
          <ClosePill onClick={() => void close()} />
        </header>
        <nav className="wizard__progress" aria-label="Sections">
          {STEPS.map((s) => {
            const c = s === 'review' ? REVIEW_COLOR : sectionMeta(s, group).color;
            const state = s === 'review' ? 'review' : member.sections[s].status;
            const fill = s === step || state === 'complete' ? c : state === 'needsUpdate' ? AMBER : 'rgba(255,255,255,0.14)';
            return (
              <button
                key={s}
                type="button"
                className={clsx('wizard__seg', s === step && 'is-current')}
                onClick={() => {
                  if (s === step) return;
                  void saveCurrent();
                  go(s);
                }}
                aria-label={`Go to ${s === 'review' ? 'Review' : sectionMeta(s, group).title}`}
                aria-current={s === step ? 'step' : undefined}
              >
                <span style={{ background: fill }} />
              </button>
            );
          })}
        </nav>
        <div ref={scroll} className="wizard__body scroll-y">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={step} initial={{ opacity: 0, x: slide * dir }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -slide * dir }} transition={{ duration: 0.22 }}>
              <div className="wizard__intro">
                <span className="wizard__icon" style={{ background: withAlpha(color, 0.16), borderColor: withAlpha(color, 0.5) }}>
                  <SectionIcon id={step} group={group} size={22} color={color} />
                </span>
                <h2 className={T.sheetTitle}>{title}</h2>
                <p className={T.small}>{meta?.why ?? 'Check each section, then finish. You can come back any time.'}</p>
              </div>
              {meta?.sensitive ? (
                <p className="wizard__note" style={{ borderColor: withAlpha(color, 0.5) }}>
                  <ShieldCheck size={16} color={color} aria-hidden />
                  <span className={T.small}>{API_ENABLED ? storageNote(step, 'this browser') : 'Demo app: these details are stored only in this browser.'}</span>
                </p>
              ) : null}
              {step === 'review' ? (
                <WizardReview member={member} members={members} group={group} onEdit={go} />
              ) : (
                <WizardFields
                  fields={fields}
                  draft={draft}
                  member={member}
                  adults={adults}
                  errors={errors}
                  accent={color}
                  onChange={(k, v) => {
                    setDraft({ ...draft, [k]: v });
                    if (errors[k]) {
                      const f = fields.find((x) => x.key === k);
                      if (f) setErrors({ ...errors, [k]: validateField(f, v) });
                    }
                  }}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
        <footer className="wizard__foot">
          {step === 'review' ? (
            <PillButton label="Done" variant="primary" block onClick={() => void close()} />
          ) : (
            <>
              <PillButton label="Skip for now" block onClick={() => void skip()} />
              <PillButton label="Save and continue" variant="primary" block onClick={() => void saveAndContinue()} />
            </>
          )}
        </footer>
      </motion.div>
    </div>,
    document.body
  );
}
