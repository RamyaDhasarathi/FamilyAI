// Picker fields (mobile components/form/PickerFields.tsx): date (the
// browser's own date picker, styled), a searchable select (state lists),
// document chips (only the file name and a local object URL are kept), list
// rows (medicines, saved cards) and the "Paid from" adult picker.
import { useId, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CalendarDays, ChevronDown, Paperclip, Plus, X } from 'lucide-react';
import clsx from 'clsx';
import { T } from '../../theme/typography';
import { ageOf, displayName, isoDate, yearsText } from '../../family/model';
import type { FamilyMember } from '../../services/interfaces';
import { Pressable } from '../Pressable';
import { ChoiceChips } from './Choices';
import { TextField, type Keyboard } from './TextField';

export function DateField({ label, value, onChange, accent, required, error, minDate, maxDate, ageNote }: {
  label: string; value?: string; onChange: (iso: string) => void; accent: string; required?: boolean; error?: string | null;
  minDate?: Date; maxDate?: Date; ageNote?: boolean;
}) {
  const id = useId();
  const age = value && ageNote ? ageOf(value) : null;
  return (
    <div className="text-field" style={{ '--accent': accent } as CSSProperties}>
      <div className={clsx('text-field__box date-field', error && 'is-error', 'is-up')}>
        <label htmlFor={id} className={clsx(T.small, 'text-field__label')}>
          {label}
          {required ? ' *' : ''}
        </label>
        <div className="text-field__row">
          <input
            id={id}
            type="date"
            className={clsx(T.input, 'text-field__input date-field__input')}
            value={value ?? ''}
            min={minDate ? isoDate(minDate) : undefined}
            max={maxDate ? isoDate(maxDate) : undefined}
            onChange={(e) => e.target.value && onChange(e.target.value)}
            aria-required={required}
            aria-invalid={!!error}
            data-field-input
          />
          {age !== null ? (
            <span className={T.smallStrong} style={{ color: accent }}>
              {yearsText(age)}
            </span>
          ) : null}
          <CalendarDays size={18} className="date-field__icon" aria-hidden />
        </div>
      </div>
      {error ? (
        <p className={clsx(T.small, 'field-error')} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function SelectField({ label, value, options, onChange, accent, required, error }: {
  label: string; value?: string; options: string[]; onChange: (v: string) => void; accent: string; required?: boolean; error?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const button = useRef<HTMLButtonElement>(null);
  const listId = useId();
  const shown = options.filter((o) => o.toLowerCase().includes(q.trim().toLowerCase()));
  const close = () => {
    setOpen(false);
    setQ('');
    button.current?.focus();
  };
  const onKey = (e: KeyboardEvent) => {
    // Esc closes the list only (not the wizard behind it).
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  };
  return (
    <div className="text-field" style={{ '--accent': accent } as CSSProperties} onKeyDown={onKey}>
      <button
        ref={button}
        type="button"
        className={clsx('text-field__box select-field', open && 'is-focused', error && !open && 'is-error', value && 'is-up')}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        data-field-input
      >
        <span className="select-field__text">
          <span className={clsx(T.small, 'text-field__label')}>
            {label}
            {required ? ' *' : ''}
          </span>
          {value ? <span className={T.input}>{value}</span> : null}
        </span>
        <ChevronDown size={18} className="date-field__icon" aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div className="select-field__panel" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.16 }}>
            <TextField label="Search" value={q} onChange={setQ} accent={accent} compact autoCapitalize="words" autoFocus />
            <ul id={listId} role="listbox" aria-label={label} className="select-field__list scroll-y">
              {shown.map((o) => (
                <li key={o} role="option" aria-selected={o === value}>
                  <button
                    type="button"
                    className={clsx('select-field__option', T.small, o === value && 'is-on')}
                    onClick={() => {
                      onChange(o);
                      close();
                    }}
                  >
                    {o}
                  </button>
                </li>
              ))}
            </ul>
          </motion.div>
        ) : null}
      </AnimatePresence>
      {error ? (
        <p className={clsx(T.small, 'field-error')} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export interface FileRef {
  kind: string;
  name: string;
  uri: string;
}

export function FilesField({ kinds, value, onChange, accent }: { kinds: string[]; value?: FileRef[]; onChange: (v: FileRef[]) => void; accent: string }) {
  const files = value ?? [];
  const input = useRef<HTMLInputElement>(null);
  const pending = useRef<string | null>(null);
  return (
    <div>
      <input
        ref={input}
        type="file"
        accept="image/*,application/pdf"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          const kind = pending.current;
          e.target.value = '';
          if (!f || !kind) return;
          onChange([...files.filter((x) => x.kind !== kind), { kind, name: f.name, uri: URL.createObjectURL(f) }]);
        }}
      />
      {kinds.map((k) => {
        const f = files.find((x) => x.kind === k);
        return (
          <div key={k} className="file-row">
            <span className={clsx(T.small, 'file-row__kind')}>{k}</span>
            {f ? (
              <span className="file-chip">
                <Paperclip size={12} color={accent} aria-hidden />
                <span className="t-chip file-chip__name">{f.name}</span>
                <button type="button" className="file-chip__x" onClick={() => onChange(files.filter((x) => x !== f))} aria-label={`Remove ${k} document`}>
                  <X size={13} aria-hidden />
                </button>
              </span>
            ) : (
              <Pressable
                className="chip"
                lift={false}
                onClick={() => {
                  pending.current = k;
                  input.current?.click();
                }}
                aria-label={`Attach ${k}`}
              >
                Attach
              </Pressable>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface Column {
  key: string;
  label: string;
  type: string;
  options?: string[];
  format?: (v: string) => string;
  keyboard?: Keyboard;
}

export function ListField({ columns, value, onChange, accent, addLabel }: {
  columns: Column[]; value?: Record<string, string>[]; onChange: (v: Record<string, string>[]) => void; accent: string; addLabel: string;
}) {
  const rows = value ?? [];
  const set = (i: number, k: string, v: string) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div>
      <AnimatePresence initial={false}>
        {rows.map((r, i) => (
          <motion.div key={i} className="list-field-row" layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }}>
            {columns.map((c) =>
              c.type === 'choice' && c.options ? (
                <ChoiceChips key={c.key} label={c.label} options={c.options} value={r[c.key]} onChange={(v) => set(i, c.key, v as string)} accent={accent} />
              ) : (
                <TextField key={c.key} compact label={c.label} value={r[c.key] ?? ''} onChange={(v) => set(i, c.key, v)} accent={accent} format={c.format} keyboard={c.keyboard} className="list-field-cell" />
              )
            )}
            <button type="button" className="list-field-row__x" onClick={() => onChange(rows.filter((_, j) => j !== i))} aria-label={`Remove ${addLabel} ${i + 1}`}>
              <X size={14} aria-hidden />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
      <Pressable className="chip" onClick={() => onChange([...rows, {}])} lift={false} aria-label={`Add ${addLabel}`}>
        <Plus size={14} aria-hidden />
        <span style={{ marginLeft: 6 }}>Add {addLabel}</span>
      </Pressable>
    </div>
  );
}

export function AdultField({ adults, value, onChange, accent }: { adults: FamilyMember[]; value?: string; onChange: (id: string) => void; accent: string }) {
  const names = adults.map((a) => displayName(a));
  const selected = adults.find((a) => a.id === value);
  return (
    <ChoiceChips
      label="Paid from"
      options={names}
      value={selected ? displayName(selected) : undefined}
      onChange={(n) => {
        const a = adults[names.indexOf(n as string)];
        if (a) onChange(a.id);
      }}
      accent={accent}
    />
  );
}
