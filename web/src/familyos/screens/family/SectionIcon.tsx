// Icons for the five details sections and the review step (mobile MemberProfileScreen.tsx).
import { ClipboardCheck, HeartPulse, IdCard, Landmark, MapPin, PiggyBank, User, type LucideProps } from 'lucide-react';
import type { SectionId } from '../../services/interfaces';
import type { AgeGroup } from '../../family/model';

/** Children and teens see "Allowance and payments" with a piggy bank. */
export function SectionIcon({ id, group, ...p }: { id: SectionId | 'review'; group: AgeGroup } & LucideProps) {
  switch (id) {
    case 'basic':
      return <User {...p} aria-hidden />;
    case 'contact':
      return <MapPin {...p} aria-hidden />;
    case 'ids':
      return <IdCard {...p} aria-hidden />;
    case 'health':
      return <HeartPulse {...p} aria-hidden />;
    case 'banking':
      return group === 'adult' ? <Landmark {...p} aria-hidden /> : <PiggyBank {...p} aria-hidden />;
    case 'review':
      return <ClipboardCheck {...p} aria-hidden />;
  }
}
