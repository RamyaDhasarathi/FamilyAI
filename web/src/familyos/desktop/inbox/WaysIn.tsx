// Inbox, "Other ways in · notices arrive however they arrive" (MASTER_AGENT.md
// §7 Phase 3, §1 A5 — integrations are UI over mock data; FamilyOS.mp4 4:05,
// frame f_050): Paste or upload, Forward on WhatsApp (not set up), Forward on
// Telegram, Forward by email, Connect your Gmail, From your phone. Plus the
// "Add a notice" dialog: it files the text as it came; nothing is read into
// proposals or changed until a person looks.
import { useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router';
import { AtSign, Mail, MessageCircle, PenLine, Send, Smartphone, type LucideIcon } from 'lucide-react';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import { Sheet } from '../../components/Sheet';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { StatusChip } from '../shell/DeskPage';

const toast = (t: string) => useFamilyOS.getState().toast(t);
const ADDED = 'Added to the Inbox. Nothing is read or changed until you look.';

function Way({ icon: Icon, title, chip, children, foot, off }: { icon: LucideIcon; title: string; chip?: string; children: ReactNode; foot?: ReactNode; off?: boolean }) {
  return (
    <li className={off ? 'ib-way is-off' : 'ib-way'}>
      <p className="ib-way__head">
        <span className="ib-way__icon" aria-hidden>
          <Icon size={15} strokeWidth={1.9} />
        </span>
        <span className={T.bodyStrong}>{title}</span>
        {chip ? <StatusChip tone="neutral">{chip}</StatusChip> : null}
      </p>
      <div className={`${T.small} ib-way__body`}>{children}</div>
      {foot ? <p className={`${T.small} ib-way__foot`}>{foot}</p> : null}
    </li>
  );
}

export function WaysIn({ onAdd }: { onAdd: () => void }) {
  const navigate = useNavigate();
  const file = useRef<HTMLInputElement>(null);
  const bot = useDesk((s) => s.telegram.bot);
  const devices = useDesk((s) => s.telegram.devices.length);
  const allMailboxes = useDesk((s) => s.mailboxes);
  const mailboxes = allMailboxes.filter((m) => m.status === 'connected');
  const phones = useDesk((s) => s.phoneTokens.filter((t) => !t.revokedAt).length);
  const [how, setHow] = useState(false);
  const onFile = (f: File | undefined) => {
    if (!f) return;
    const kb = Math.max(1, Math.round(f.size / 1024));
    const id = useDesk.getState().addNotice({ title: f.name, body: `${f.name} (${kb} KB), added from this browser. FamilyOS has not read it yet.`, source: 'paste', attachments: 1 });
    toast(ADDED);
    navigate(`/inbox/${id}`);
  };
  const copyBot = () => {
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(bot).then(() => toast(`Copied ${bot}.`), () => toast('Could not copy.'));
  };
  return (
    <section aria-labelledby="ib-ways" className="ib-ways-wrap">
      <h2 id="ib-ways" className="ib-label">
        <span className={T.bodyStrong}>Other ways in</span> <span className={T.small}>notices arrive however they arrive</span>
      </h2>
      <ul className="ib-ways">
        <Way icon={PenLine} title="Paste or upload" foot="Copied text reads better than a screenshot of it.">
          <p>Copy a message and paste it, or add a photo, screenshot or PDF.</p>
          <span className="ib-way__btns">
            <PillButton label="Add a notice" variant="primary" onClick={onAdd} />
            <PillButton label="Upload a file" onClick={() => file.current?.click()} />
          </span>
          <input ref={file} type="file" hidden tabIndex={-1} aria-hidden onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ''; }} />
        </Way>
        <Way icon={MessageCircle} title="Forward on WhatsApp" chip="not set up" off foot="Not set up yet: it needs a WhatsApp business number. Paste works meanwhile.">
          <p>Long-press the message, Forward, and pick the family number. Several at once is fine.</p>
        </Way>
        <Way icon={Send} title="Forward on Telegram" foot="In a group, mention the bot or reply to it; it does not read the rest of the group.">
          <p>Link your account once, then forward anything to the bot. Files up to 20 MB.</p>
          <span className="ib-way__btns">
            <code className="ib-code ib-code--small">{bot}</code>
            <PillButton label="Copy" aria-label={`Copy ${bot}`} onClick={copyBot} />
          </span>
          <p>
            Linked on {devices} {devices === 1 ? 'device' : 'devices'} ·{' '}
            <Link to="/settings/household" className="wt-notice">Link another device</Link>
          </p>
        </Way>
        <Way icon={Mail} title="Forward by email" foot="Works from inside any app, including group chats no service can read.">
          <p>Forward a notice from any mailbox to the family address above.</p>
        </Way>
        <Way icon={AtSign} title="Connect your Gmail" foot="Removes the step where somebody has to notice a notice and forward it.">
          <p>Read-only, and only mail that looks like a notice. Nothing is sent or changed.</p>
          <p>{mailboxes.length ? `Connected: ${mailboxes.map((m) => m.address).join(', ')}` : 'No mailbox connected.'}</p>
          <span className="ib-way__btns">
            <Link to="/settings/household" className="pill pill--secondary">Set up</Link>
          </span>
        </Way>
        <Way icon={Smartphone} title="From your phone" foot={`${phones} ${phones === 1 ? 'phone' : 'phones'} can send here.`}>
          <p>Share straight from WhatsApp or the school app, without opening this.</p>
          <span className="ib-way__btns">
            <PillButton label="How" aria-expanded={how} onClick={() => setHow((v) => !v)} />
            <Link to="/settings/household" className="desk-link">Phone tokens ›</Link>
          </span>
          {how ? <p>iPhone: a Shortcut in the share sheet sends what you share, with your phone’s token. Android: share to FamilyOS from any app. Revoke a phone any time in Settings.</p> : null}
        </Way>
      </ul>
    </section>
  );
}

export function AddNoticeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [from, setFrom] = useState('');
  const [error, setError] = useState('');
  const first = useRef<HTMLInputElement>(null);
  const save = (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim()) return setError('Paste the message as it came.');
    const t = title.trim() || body.trim().split('\n')[0].slice(0, 80);
    const id = useDesk.getState().addNotice({ title: t, body: body.trim(), sender: from.trim() || undefined, source: 'paste' });
    setTitle('');
    setBody('');
    setFrom('');
    onClose();
    toast(ADDED);
    navigate(`/inbox/${id}`);
  };
  return (
    <Sheet open={open} onClose={onClose} labelledBy="ib-add-title" desktop="center" initialFocus={first} header={<div className="sheet-title-row"><h2 id="ib-add-title" className={T.sheetTitle}>Add a notice</h2></div>}>
      <form className="ib-add" onSubmit={save}>
        <label className={T.small}>
          <span>
            What is it? <span className="ib-optional">(optional)</span>
          </span>
          <input ref={first} className="ib-input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Field trip permission form" autoComplete="off" />
        </label>
        <label className={T.small}>
          The message, as it came
          <textarea className="ib-input ib-input--area" rows={6} value={body} onChange={(e) => { setBody(e.target.value); setError(''); }} aria-invalid={!!error} aria-describedby={error ? 'ib-add-err' : undefined} />
        </label>
        {error ? <p id="ib-add-err" role="alert" className={`${T.small} ib-error`}>{error}</p> : null}
        <label className={T.small}>
          <span>
            Who sent it? <span className="ib-optional">(optional)</span>
          </span>
          <input className="ib-input" value={from} onChange={(e) => setFrom(e.target.value)} placeholder="Lakeside High School" autoComplete="off" />
        </label>
        <p className={T.small}>It is kept exactly as you paste it. Nothing is accepted, sent or paid from here.</p>
        <span className="ib-way__btns">
          <PillButton label="Add to the Inbox" variant="primary" type="submit" />
          <PillButton label="Cancel" onClick={onClose} />
        </span>
      </form>
    </Sheet>
  );
}
