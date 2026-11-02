// Settings → Household: Privacy and data (MASTER_AGENT.md §3.2 Settings
// 7:30–9:30, §3.3.6 "append-only audit and full export/erase", §11
// "Download everything produces an export; Erase everything requires typed
// confirmation"). Take everything with you → Download everything (the
// store's exportAll writes one JSON file and an audit row). Erase everything:
// danger styling, the exact phrase from eraseConfirmPhrase() to type, and an
// Erase button that stays disabled until the text matches.
import { useId, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { Pressable } from '../../components/Pressable';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { DeskCard } from '../shell/DeskPage';
import { eraseReady } from './settingsModel';
import { ADMIN_COPY } from './adminCopy';

const C = ADMIN_COPY.settings;

export function PrivacyCard() {
  const name = useDesk((s) => s.settings.name);
  const exportAll = useDesk((s) => s.exportAll);
  const phrase = useDesk((s) => s.eraseConfirmPhrase());
  const eraseAll = useDesk((s) => s.eraseAll);
  const [typed, setTyped] = useState('');
  const id = useId();
  const ready = eraseReady(typed, phrase);

  const download = () => {
    const out = exportAll();
    useFamilyOS.getState().toast(`Downloaded everything as of ${out.exportedAt.slice(0, 10)}. Written to the Audit.`, { duration: 4200 });
  };

  const erase = (ev: FormEvent) => {
    ev.preventDefault();
    if (!ready || !eraseAll(typed.trim())) return;
    setTyped('');
    useFamilyOS.getState().toast('The household’s data is erased. One Audit row records it.', { duration: 6000 });
  };

  return (
    <section id="privacy" className="adm-privacy" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className={clsx(T.section, 'adm-section-label')}>
        Privacy and data
      </h2>
      <DeskCard title="Take everything with you">
        <p className={T.small}>{C.takeAll(name)}</p>
        <div className="adm-actions" style={{ marginTop: 12 }}>
          <PillButton label="Download everything" variant="primary" onClick={download} />
          <Link to="/audit" className="desk-link">
            See the Audit ›
          </Link>
          <Link to="/revisions" className="desk-link">
            Revisions ›
          </Link>
        </div>
      </DeskCard>
      <DeskCard title="Erase everything" className="adm-erase">
        <p className={T.small}>{C.eraseAll}</p>
        <form className="adm-form" onSubmit={erase} style={{ marginTop: 12 }}>
          <div className="adm-field">
            <label htmlFor={`${id}-erase`} className="adm-label">
              Type <span className="adm-code adm-code--ink">{phrase}</span> to confirm
            </label>
            <input
              id={`${id}-erase`}
              className="adm-input"
              value={typed}
              autoComplete="off"
              spellCheck={false}
              aria-describedby={`${id}-erase-state`}
              onChange={(e) => setTyped(e.target.value)}
            />
            <p id={`${id}-erase-state`} className={clsx(T.small, 'adm-row__sub')} aria-live="polite">
              {ready ? 'The phrase matches. Erasing cannot be undone.' : typed ? 'Not yet: type the phrase exactly, capitals included.' : 'The button stays off until the phrase matches.'}
            </p>
          </div>
          <div className="adm-actions">
            <Pressable type="submit" className="pill pill--danger" disabled={!ready}>
              Erase the household
            </Pressable>
          </div>
        </form>
      </DeskCard>
    </section>
  );
}
