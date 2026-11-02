// Settings → Household, /settings/household and /settings/privacy
// (MASTER_AGENT.md §3.2 Settings 0:35–1:20 and 7:30–9:30, §7 Phase 5;
// FamilyOS.mp4 frames f_008–f_017, f_091–f_115). The household's name as the
// title, "Add a member" (the existing Add family member flow). Main column:
// Members, Consent for the children, Notifications, Agents and permissions,
// Where we live, Privacy and data (Download everything, Erase everything).
// Rail: Connected mailboxes, Telegram, From your phone, Pages you are
// watching. Every section has an anchor; the avatar menu's desktop links land
// on #permissions, #notifications and #privacy, and /settings/privacy opens
// here scrolled to #privacy. Nothing changes without a click, most behind a
// confirm, and every change is written to the Audit by the store.
import { useEffect } from 'react';
import { Link, useLocation } from 'react-router';
import { Settings } from 'lucide-react';
import { useDesk } from '../../desk/store';
import { useDeskFormat, useNow } from '../../desk/hooks';
import { dayKey, fmtShortDay } from '../../desk/format';
import { DeskPage } from '../shell/DeskPage';
import { ConsentCard, MembersCard } from './SettingsPeople';
import { PlaceCard, RulesCard } from './SettingsRules';
import { MailboxesCard, TelegramCard } from './SettingsConnections';
import { PhoneCard, WatchingCard } from './SettingsPhone';
import { PrivacyCard } from './SettingsData';
import { NOTIFY_TOGGLES, PERMISSION_TOGGLES, SECTIONS, type SectionId } from './settingsModel';
import { ADMIN_COPY } from './adminCopy';
import './admin.css';

export default function SettingsHouseholdPage({ section }: { section?: SectionId }) {
  const { pathname, hash } = useLocation();
  const name = useDesk((s) => s.settings.name);
  const now = useNow();
  const f = useDeskFormat(now);
  const fmt = { ago: f.ago, date: (i: string) => fmtShortDay(dayKey(i, f.tz)) };

  // Land on the anchor after the shell's own scroll-to-top for a new route.
  useEffect(() => {
    const id = hash.slice(1) || section;
    if (!id) return;
    const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }), 60);
    return () => window.clearTimeout(t);
  }, [hash, section]);

  return (
    <DeskPage
      className="adm-page adm-settings"
      icon={Settings}
      title={name}
      metaTitle="Household · Settings · FamilyOS"
      description={ADMIN_COPY.settings.description}
      actions={
        <>
          <Link to="/settings" className="pill pill--secondary">
            App settings
          </Link>
          <Link to="/family?add=1" className="pill pill--primary">
            Add a member
          </Link>
        </>
      }
      rail={
        <>
          <MailboxesCard {...fmt} />
          <TelegramCard {...fmt} />
          <PhoneCard {...fmt} />
          <WatchingCard {...fmt} />
        </>
      }
    >
      <nav className="adm-jump" aria-label="On this page">
        {SECTIONS.map(([id, label]) => (
          <Link key={id} to={{ pathname, hash: id }} className="adm-filter" replace onClick={() => document.getElementById(id)?.scrollIntoView({ block: 'start' })}>
            {label}
          </Link>
        ))}
      </nav>
      <MembersCard />
      <ConsentCard ago={f.ago} />
      <RulesCard id="notifications" title="Notifications" sub="who hears what, and when" ids={NOTIFY_TOGGLES} />
      <RulesCard id="permissions" title="Agents and permissions" sub="what FamilyOS may do on its own" ids={PERMISSION_TOGGLES} />
      <PlaceCard />
      <PrivacyCard />
    </DeskPage>
  );
}
