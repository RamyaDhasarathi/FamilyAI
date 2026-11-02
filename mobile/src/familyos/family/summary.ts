// One-line, masked summaries of each section ("Mobile ••••••4417 · Austin, TX"),
// for the member profile rows and the wizard's review step (§4.6, §4.7).
import type { FamilyMember, SectionId } from '../services/interfaces';
import { CURRENCY } from '../mocks/data';
import { maskers, region, stateShort } from './region';

const join = (parts: (string | false | undefined | null)[]) => parts.filter(Boolean).join(' · ');

export function sectionSummary(
  m: FamilyMember,
  section: SectionId,
  members: FamilyMember[],
  owner: FamilyMember | undefined
): string {
  const d = m.sections[section].data as Record<string, string | boolean | unknown[] | undefined>;
  const s = (k: string) => (typeof d[k] === 'string' ? (d[k] as string).trim() : '');
  switch (section) {
    case 'basic':
      return join([s('gender'), s('occupation') || s('school'), s('grade') && `Grade ${s('grade')}`]) || 'Not filled in yet';
    case 'contact': {
      const src = d.sameAddress && owner ? (owner.sections.contact.data as Record<string, string>) : (d as Record<string, string>);
      const place = src.city ? `${src.city}${src.state ? `, ${stateShort(src.state)}` : ''}` : '';
      return join([s('mobile') && `Mobile ${maskers.phone(s('mobile'))}`, d.sameAddress ? 'Lives with you' : place]) || 'Not filled in yet';
    }
    case 'ids': {
      const docs = Array.isArray(d.documents) ? d.documents.length : 0;
      const ids =
        region === 'IN'
          ? [s('aadhaar') && `Aadhaar ${maskers.aadhaar(s('aadhaar'))}`, s('pan') && `PAN ${maskers.tail(s('pan'))}`]
          : [s('licence') && `Licence ${maskers.tail(s('licence'))}`, s('ssnLast4') && 'SSN ••••'];
      return join([...ids, s('passport') && `Passport ${maskers.tail(s('passport'))}`, docs > 0 && `${docs} document${docs > 1 ? 's' : ''}`]) || 'Not filled in yet';
    }
    case 'health':
      return join([s('bloodGroup') && `Blood ${s('bloodGroup')}`, s('emergencyName') && `Emergency: ${s('emergencyName').split(' ')[0]}`]) || 'Not filled in yet';
    case 'banking': {
      if (d.paidFrom !== undefined || d.weeklyAllowance !== undefined) {
        const payer = members.find((x) => x.id === d.paidFrom);
        return (
          join([
            s('weeklyAllowance') && `${CURRENCY}${s('weeklyAllowance')} a week`,
            payer ? `from ${payer.preferredName || payer.fullName.split(' ')[0]}` : d.paidFrom ? '' : 'payer not chosen',
          ]) || 'Not filled in yet'
        );
      }
      return join([s('bank'), s('account') && maskers.tail(s('account'))]) || 'Not filled in yet';
    }
  }
}
