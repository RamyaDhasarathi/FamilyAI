// Add family member / Edit basics (mobile MemberBasicsSheet.tsx,
// AGENT_CORE_AND_FAMILY.md §4.5–§4.6): a glass sheet with a live avatar
// preview for the age entered, name, relationship chips (no "Self"), date of
// birth, and (when editing) preferred name and photo. Closing with unsaved
// input asks first.
import { useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import clsx from 'clsx';
import type { FamilyMember, MemberBasics, Relationship } from '../../services/interfaces';
import { RELATIONSHIPS, ageOf, yearsText } from '../../family/model';
import { avatarForAge, stageAccent } from '../../graphics/avatars';
import { T } from '../../theme/typography';
import { useFamilyOS } from '../../store/useFamilyOS';
import { ClosePill, PillButton } from '../../components/Pills';
import { Sheet } from '../../components/Sheet';
import { ChoiceChips, FieldFrame } from '../../components/form/Choices';
import { DateField } from '../../components/form/PickerFields';
import { TextField } from '../../components/form/TextField';
import { ConfirmDialog } from './ConfirmDialog';
import { Dissolve } from './Dissolve';

const ACCENT = '#61B8FF';
const yearsAgo = (n: number) => {
  const d = new Date();
  d.setFullYear(d.getFullYear() - n);
  return d;
};

type Key = 'fullName' | 'relationship' | 'relationshipOther' | 'dateOfBirth';
type Errors = Partial<Record<Key, string>>;

function validate(b: Partial<MemberBasics>, owner: boolean): Errors {
  const e: Errors = {};
  if (!b.fullName?.trim()) e.fullName = 'Required';
  else if (!/^[\p{L} .'-]{2,60}$/u.test(b.fullName.trim())) e.fullName = 'Use 2–60 letters, spaces or . \' -';
  if (!owner && !b.relationship) e.relationship = 'Choose one';
  if (b.relationship === 'Other' && !b.relationshipOther?.trim()) e.relationshipOther = 'Required';
  if (!b.dateOfBirth) e.dateOfBirth = 'Required';
  return e;
}

/** A square, small JPEG data URL (keeps localStorage well under quota). */
function shrinkPhoto(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const s = 256;
      const c = document.createElement('canvas');
      c.width = s;
      c.height = s;
      const k = Math.max(s / img.width, s / img.height);
      c.getContext('2d')!.drawImage(img, (s - img.width * k) / 2, (s - img.height * k) / 2, img.width * k, img.height * k);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/jpeg', 0.85));
    };
    img.onerror = reject;
    img.src = url;
  });
}

interface Props {
  open: boolean;
  /** Edit mode when a member is given. */
  member?: FamilyMember;
  onClose: () => void;
  /** finishLater: "Add now, finish later" (add mode only). */
  onSubmit: (basics: MemberBasics, finishLater: boolean) => Promise<void>;
}

export function MemberBasicsSheet({ open, member, onClose, onSubmit }: Props) {
  const edit = !!member;
  const initial: Partial<MemberBasics> = member
    ? { fullName: member.fullName, preferredName: member.preferredName, relationship: member.relationship, relationshipOther: member.relationshipOther, dateOfBirth: member.dateOfBirth, photoUri: member.photoUri }
    : {};
  const [b, setB] = useState<Partial<MemberBasics>>(initial);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const refs = useRef<Partial<Record<Key, HTMLDivElement | null>>>({});
  const photoInput = useRef<HTMLInputElement>(null);
  const toast = useFamilyOS((s) => s.toast);
  // Reset the form each time the sheet opens (adjusted during render).
  const [openKey, setOpenKey] = useState(open);
  if (open !== openKey) {
    setOpenKey(open);
    if (open) {
      setB(initial);
      setErrors({});
    }
  }

  const age = b.dateOfBirth ? ageOf(b.dateOfBirth) : null;
  const stage = age !== null ? avatarForAge(age) : null;
  const dirty = JSON.stringify(b) !== JSON.stringify(initial);
  const set = (patch: Partial<MemberBasics>) => {
    const next = { ...b, ...patch };
    setB(next);
    // Messages clear as soon as the field is fixed.
    if (Object.keys(errors).length) setErrors(validate(next, !!member?.isOwner));
  };
  const requestClose = () => (dirty ? setConfirm(true) : onClose());

  const submit = async (finishLater: boolean) => {
    const e = validate(b, !!member?.isOwner);
    setErrors(e);
    const first = (['fullName', 'relationship', 'relationshipOther', 'dateOfBirth'] as const).find((k) => e[k]);
    if (first) {
      const el = refs.current[first];
      el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      el?.querySelector<HTMLElement>('[data-field-input]')?.focus({ preventScroll: true });
      return;
    }
    setBusy(true);
    try {
      await onSubmit(
        {
          fullName: b.fullName!.trim(),
          preferredName: b.preferredName?.trim() || undefined,
          relationship: (b.relationship ?? 'Self') as Relationship,
          relationshipOther: b.relationship === 'Other' ? b.relationshipOther?.trim() : undefined,
          dateOfBirth: b.dateOfBirth!,
          photoUri: b.photoUri,
        },
        finishLater
      );
    } finally {
      setBusy(false);
    }
  };

  const header = (
    <div className="fam-sheet-head">
      <h2 id="basics-title" className={T.sheetTitle}>
        {edit ? 'Edit details' : 'Add family member'}
      </h2>
      <ClosePill onClick={requestClose} />
    </div>
  );

  return (
    <>
      <Sheet open={open} onClose={requestClose} labelledBy="basics-title" header={header} close="none" fixedFrac={0.9} opaque desktop="center">
        <div className="fam-sheet-body">
          <div className="basics-preview card" aria-live="polite">
            <span className="basics-preview__img">
              {b.photoUri ? (
                <img src={b.photoUri} alt="" />
              ) : stage ? (
                <AnimatePresence mode="popLayout">
                  <motion.img key={stage.stage} src={stage.gif} alt="" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.38 }} />
                </AnimatePresence>
              ) : (
                <span className="basics-preview__empty" />
              )}
              {stage ? (
                <span className="basics-preview__dissolve">
                  <Dissolve key={stage.stage} color={stageAccent[stage.stage]} size={72} reverse />
                </span>
              ) : null}
            </span>
            <span className="basics-preview__text">
              <span className={T.bodyStrong} style={{ color: stage ? stageAccent[stage.stage] : 'var(--muted)' }}>
                {stage ? `Stage ${stage.stage} · ${stage.name}` : 'Avatar'}
              </span>
              <span className={clsx(T.small, 'basics-preview__sub')}>
                {stage ? `Ages ${stage.ages}${age !== null ? ` · ${yearsText(age)}` : ''}` : 'Appears when you add a date of birth'}
              </span>
            </span>
          </div>

          <div ref={(el) => { refs.current.fullName = el; }} className="fam-gap">
            <TextField label="Full name" required value={b.fullName ?? ''} onChange={(v) => set({ fullName: v })} accent={ACCENT} error={errors.fullName} autoCapitalize="words" />
          </div>
          {edit ? (
            <div className="fam-gap">
              <TextField label="Preferred name" value={b.preferredName ?? ''} onChange={(v) => set({ preferredName: v })} accent={ACCENT} autoCapitalize="words" />
            </div>
          ) : null}
          {!member?.isOwner ? (
            <div ref={(el) => { refs.current.relationship = el; }} className="fam-gap">
              <FieldFrame label="Relationship" required error={errors.relationship}>
                <ChoiceChips label="Relationship" options={RELATIONSHIPS} value={b.relationship} onChange={(v) => set({ relationship: v as Relationship })} accent={ACCENT} />
              </FieldFrame>
            </div>
          ) : null}
          {b.relationship === 'Other' ? (
            <div ref={(el) => { refs.current.relationshipOther = el; }} className="fam-gap">
              <TextField label="Relationship (other)" required value={b.relationshipOther ?? ''} onChange={(v) => set({ relationshipOther: v })} accent={ACCENT} error={errors.relationshipOther} />
            </div>
          ) : null}
          <div ref={(el) => { refs.current.dateOfBirth = el; }} className="fam-gap">
            <DateField label="Date of birth" required value={b.dateOfBirth} onChange={(v) => set({ dateOfBirth: v })} accent={ACCENT} error={errors.dateOfBirth} maxDate={new Date()} minDate={yearsAgo(120)} ageNote />
          </div>
          {edit ? (
            <div className="fam-gap fam-photo-row">
              <input
                ref={photoInput}
                type="file"
                accept="image/*"
                className="sr-only"
                tabIndex={-1}
                aria-hidden
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  e.target.value = '';
                  if (!f) return;
                  try {
                    set({ photoUri: await shrinkPhoto(f) });
                  } catch {
                    toast('Couldn’t open that photo');
                  }
                }}
              />
              <PillButton
                label="Choose photo"
                onClick={() => {
                  photoInput.current?.removeAttribute('capture');
                  photoInput.current?.click();
                }}
              />
              <PillButton
                label="Take photo"
                onClick={() => {
                  photoInput.current?.setAttribute('capture', 'user');
                  photoInput.current?.click();
                }}
              />
              {b.photoUri ? <PillButton label="Remove photo" onClick={() => set({ photoUri: undefined })} /> : null}
            </div>
          ) : null}

          <div className="fam-actions">
            {edit ? (
              <PillButton label={busy ? 'Saving…' : 'Save'} variant="primary" block onClick={() => void submit(false)} />
            ) : (
              <>
                <PillButton label={busy ? 'Adding…' : 'Add and fill details'} variant="primary" block onClick={() => void submit(false)} />
                <PillButton label="Add now, finish later" block onClick={() => void submit(true)} />
              </>
            )}
          </div>
        </div>
      </Sheet>
      {confirm ? (
        <ConfirmDialog
          title={edit ? 'Discard your changes?' : 'Discard this new member?'}
          confirm="Discard"
          cancel="Keep editing"
          onConfirm={() => {
            setConfirm(false);
            onClose();
          }}
          onCancel={() => setConfirm(false)}
        />
      ) : null}
    </>
  );
}
