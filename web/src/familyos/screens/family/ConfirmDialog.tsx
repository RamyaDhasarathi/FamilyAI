// Small confirmation ("Discard this new member?"), mobile ConfirmDialog.tsx.
import { useId } from 'react';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { Dialog } from './Dialog';

export function ConfirmDialog({ title, body, confirm, cancel, destructive = true, onConfirm, onCancel }: {
  title: string; body?: string; confirm: string; cancel: string; destructive?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const id = useId();
  return (
    <Dialog labelledBy={id} onCancel={onCancel} className="fam-dialog__card--small">
      <h2 id={id} className={`${T.bodyStrong} t-center`} style={{ fontSize: '1rem' }}>
        {title}
      </h2>
      {body ? <p className={`${T.small} t-center`} style={{ marginTop: 6 }}>{body}</p> : null}
      <div className="fam-dialog__buttons">
        <PillButton label={cancel} onClick={onCancel} className="fam-dialog__btn" />
        <PillButton label={confirm} variant={destructive ? 'danger' : 'primary'} onClick={onConfirm} className="fam-dialog__btn" />
      </div>
    </Dialog>
  );
}
