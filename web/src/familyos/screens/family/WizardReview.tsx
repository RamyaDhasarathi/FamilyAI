// Review step of the details wizard (mobile WizardReview.tsx): one card per
// section with its status, a masked summary and an Edit link.
import { motion } from 'framer-motion';
import type { FamilyMember, SectionId } from '../../services/interfaces';
import { SECTION_IDS, type AgeGroup, sectionMeta } from '../../family/model';
import { sectionSummary } from '../../family/summary';
import { withAlpha } from '../../theme/tokens';
import { durations } from '../../theme/motion';
import { T } from '../../theme/typography';
import { StatusPill } from '../../components/family/MemberBits';

export function WizardReview({ member, members, group, onEdit }: { member: FamilyMember; members: FamilyMember[]; group: AgeGroup; onEdit: (s: SectionId) => void }) {
  const owner = members.find((m) => m.isOwner);
  return (
    <ul className="wizard-review">
      {SECTION_IDS.map((sid, i) => {
        const meta = sectionMeta(sid, group);
        return (
          <motion.li
            key={sid}
            className="wizard-review__card card"
            style={{ borderLeftColor: withAlpha(meta.color, 0.8) }}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: (i * durations.stagger) / 1000, duration: 0.28 }}
          >
            <div className="wizard-review__head">
              <h3 className={T.bodyStrong}>{meta.title}</h3>
              <button type="button" className="wizard-review__edit t-small-strong" style={{ color: meta.color }} onClick={() => onEdit(sid)} aria-label={`Edit ${meta.title}`}>
                Edit
              </button>
            </div>
            <p className={T.small}>{sectionSummary(member, sid, members, owner)}</p>
            <StatusPill status={member.sections[sid].status} />
          </motion.li>
        );
      })}
    </ul>
  );
}
