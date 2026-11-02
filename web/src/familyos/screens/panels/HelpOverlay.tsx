// Keyboard shortcuts (AGENT_WEB.md §9): `?` opens this small overlay.
import { shortcuts, webCopy } from '../../mocks/webData';
import { T } from '../../theme/typography';
import { Sheet } from '../../components/Sheet';

export function ShortcutList() {
  return (
    <dl className="shortcuts">
      {shortcuts
        .filter((s) => !s.devOnly || import.meta.env.DEV)
        .map((s) => (
          <div key={s.label} className="shortcuts__row">
            <dt>
              {s.keys.map((k) => (k === '–' ? <span key={k} className={T.small}> – </span> : <kbd key={k} className="kbd">{k}</kbd>))}
            </dt>
            <dd className={T.small} style={{ color: 'var(--ink)' }}>
              {s.label}
            </dd>
          </div>
        ))}
    </dl>
  );
}

export function HelpOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const header = (
    <div className="sheet-title-row">
      <h2 id="help-title" className={T.sheetTitle}>
        {webCopy.help.title}
      </h2>
    </div>
  );
  return (
    <Sheet open={open} onClose={onClose} labelledBy="help-title" header={header} desktop="center">
      <div className="help-body">
        <ShortcutList />
        <p className={T.small} style={{ marginTop: 14 }}>
          {webCopy.help.note}
        </p>
      </div>
    </Sheet>
  );
}
