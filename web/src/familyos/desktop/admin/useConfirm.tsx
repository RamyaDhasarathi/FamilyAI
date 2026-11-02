// `const [dialog, ask] = useConfirm()` — render {dialog}, call
// ask({ title, body, confirm, danger, run }) from a click. `run` happens only
// on the Confirm button (MASTER_AGENT.md §0.3.3).
import { useState, type ReactNode } from 'react';
import { AdminConfirm, type ConfirmProps } from './AdminConfirm';

export type ConfirmRequest = Omit<ConfirmProps, 'onConfirm' | 'onCancel'> & { run: () => void };

export function useConfirm(): [ReactNode, (r: ConfirmRequest) => void] {
  const [req, setReq] = useState<ConfirmRequest | null>(null);
  const node = req ? (
    <AdminConfirm
      {...req}
      onCancel={() => setReq(null)}
      onConfirm={() => {
        setReq(null);
        req.run();
      }}
    />
  ) : null;
  return [node, setReq];
}
