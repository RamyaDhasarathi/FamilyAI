// Small menu for a member (mobile MemberCard.tsx MemberMenu): Edit details /
// Remove from family. Opened by the ⋯ button, a right-click or a long-press.
import { useId } from 'react';
import { Pencil, Trash } from 'lucide-react';
import type { FamilyMember } from '../../services/interfaces';
import { displayName } from '../../family/model';
import { T } from '../../theme/typography';
import { Pressable } from '../../components/Pressable';
import { Dialog } from './Dialog';

export function MemberMenu({ member, onEdit, onRemove, onClose }: { member: FamilyMember; onEdit: () => void; onRemove: () => void; onClose: () => void }) {
  const id = useId();
  return (
    <Dialog labelledBy={id} onCancel={onClose} className="fam-menu">
      <p id={id} className={`${T.smallStrong} fam-menu__title`}>
        {displayName(member)}
      </p>
      <Pressable className="fam-menu__row" onClick={onEdit} lift={false} pressScale={0.98}>
        <Pencil size={16} aria-hidden />
        <span className={T.menu}>Edit details</span>
      </Pressable>
      {!member.isOwner ? (
        <Pressable className="fam-menu__row" onClick={onRemove} lift={false} pressScale={0.98} aria-label={`Remove ${displayName(member)} from family`}>
          <Trash size={16} color="var(--danger)" aria-hidden />
          <span className={T.menu} style={{ color: 'var(--danger)' }}>
            Remove from family
          </span>
        </Pressable>
      ) : null}
    </Dialog>
  );
}
