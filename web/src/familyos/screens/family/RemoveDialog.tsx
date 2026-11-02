// Remove-member dialog (mobile RemoveDialog.tsx, AGENT_CORE_AND_FAMILY.md §4.9).
// If the member pays any child's allowance, those children are listed and
// the user picks another adult or "Decide later".
import { useId, useState } from 'react';
import type { FamilyMember } from '../../services/interfaces';
import { adultsOf, dependentsOf, displayName } from '../../family/model';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { MemberAvatar } from '../../components/family/MemberBits';
import { ChoiceChips } from '../../components/form/Choices';
import { PillButton } from '../../components/Pills';
import { Dialog } from './Dialog';

const LATER = 'Decide later';

interface Props {
  member: FamilyMember;
  members: FamilyMember[];
  /** reassign: undefined = no dependents; an adult id; or null = decide later. */
  onConfirm: (reassign?: string | null) => void;
  onCancel: () => void;
}

export function RemoveDialog({ member, members, onConfirm, onCancel }: Props) {
  const id = useId();
  const deps = dependentsOf(members, member.id);
  const others = adultsOf(members).filter((a) => a.id !== member.id);
  const [choice, setChoice] = useState<string>(others[0] ? displayName(others[0]) : LATER);
  const name = displayName(member);
  const confirm = () => {
    if (deps.length === 0) return onConfirm(undefined);
    const a = others.find((x) => displayName(x) === choice);
    onConfirm(a ? a.id : null);
  };
  return (
    <Dialog labelledBy={id} onCancel={onCancel}>
      <MemberAvatar member={member} size={64} className="fam-dialog__avatar" />
      <h2 id={id} className={`${T.sheetTitle} t-center`}>
        Remove {name} from your family?
      </h2>
      <p className={`${T.small} t-center`} style={{ marginTop: 8 }}>
        Their profile and saved details will be deleted from this browser. Your agents will stop planning for them.
      </p>
      {deps.length > 0 ? (
        <div className="fam-dialog__deps">
          <p className={T.small} style={{ color: 'var(--ink)', marginBottom: 10 }}>
            {name} pays the allowance for {deps.map(displayName).join(' and ')}. Who should pay it now?
          </p>
          <ChoiceChips label="New payer" options={[...others.map(displayName), LATER]} value={choice} onChange={(v) => setChoice(v as string)} accent={colors.danger} />
        </div>
      ) : null}
      <div className="fam-dialog__buttons">
        <PillButton label="Cancel" onClick={onCancel} className="fam-dialog__btn" />
        <PillButton label="Remove" variant="danger" onClick={confirm} className="fam-dialog__btn" aria-label={`Remove ${name} from family`} />
      </div>
    </Dialog>
  );
}
