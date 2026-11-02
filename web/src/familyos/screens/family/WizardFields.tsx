// Renders one wizard section from its field definitions (family/fields.ts,
// mobile WizardFields.tsx). Each field is wrapped in an element tagged with
// its key so validation can scroll to it and focus it.
import type { FamilyMember } from '../../services/interfaces';
import type { FieldDef } from '../../family/fields';
import { ChoiceChips, FieldFrame, ToggleRow } from '../../components/form/Choices';
import { AdultField, DateField, FilesField, ListField, SelectField, type FileRef } from '../../components/form/PickerFields';
import { TextField, type Keyboard } from '../../components/form/TextField';

interface Props {
  fields: FieldDef[];
  draft: Record<string, unknown>;
  member: FamilyMember;
  adults: FamilyMember[];
  errors: Record<string, string | null>;
  accent: string;
  onChange: (key: string, v: unknown) => void;
}

export function WizardFields({ fields, draft, member, adults, errors, accent, onChange }: Props) {
  // `when` sees the draft merged onto the member (relationship lives on the member).
  const view = { ...member, ...draft } as FamilyMember;
  return (
    <div className="wizard-fields">
      {fields
        .filter((f) => !f.when || f.when(draft, view))
        .map((f) => {
          const v = draft[f.key];
          const err = errors[f.key] ?? null;
          const s = typeof v === 'string' ? v : '';
          let el: React.ReactNode;
          switch (f.type) {
            case 'text':
              el = (
                <TextField
                  label={f.label} value={s} onChange={(t) => onChange(f.key, t)} accent={accent} required={f.required} error={err}
                  hint={f.hint} prefix={f.prefix} keyboard={f.keyboard as Keyboard} format={f.format} mask={f.mask}
                  autoCapitalize={f.key.toLowerCase().includes('name') || f.key === 'city' ? 'words' : 'sentences'}
                />
              );
              break;
            case 'date':
              el = (
                <DateField
                  label={f.label} value={s || undefined} onChange={(d) => onChange(f.key, d)} accent={accent} required={f.required} error={err}
                  minDate={f.minDate?.()} maxDate={f.maxDate?.()} ageNote={f.key === 'dateOfBirth'}
                />
              );
              break;
            case 'choice':
            case 'multi':
              el = (
                <FieldFrame label={f.label} required={f.required} error={err}>
                  <ChoiceChips label={f.label} options={f.options ?? []} value={v as string | string[] | undefined} multi={f.type === 'multi'} onChange={(x) => onChange(f.key, x)} accent={accent} />
                </FieldFrame>
              );
              break;
            case 'toggle':
              el = <ToggleRow label={f.label} value={!!v} onChange={(x) => onChange(f.key, x)} accent={accent} required={f.required} error={err} />;
              break;
            case 'select':
              el = <SelectField label={f.label} value={s || undefined} options={f.options ?? []} onChange={(x) => onChange(f.key, x)} accent={accent} required={f.required} error={err} />;
              break;
            case 'files':
              el = (
                <FieldFrame label={f.label}>
                  <FilesField kinds={f.kinds ?? []} value={v as FileRef[] | undefined} onChange={(x) => onChange(f.key, x)} accent={accent} />
                </FieldFrame>
              );
              break;
            case 'list':
              el = (
                <FieldFrame label={f.label} error={err}>
                  <ListField
                    columns={(f.columns ?? []).map((c) => ({ ...c, keyboard: c.keyboard as Keyboard }))}
                    value={v as Record<string, string>[] | undefined}
                    onChange={(x) => onChange(f.key, x)}
                    accent={accent}
                    addLabel={f.key === 'cards' ? 'card' : 'medicine'}
                  />
                </FieldFrame>
              );
              break;
            case 'adult':
              el = (
                <FieldFrame label={f.label} required={f.required} error={err}>
                  <AdultField adults={adults} value={v as string | undefined} onChange={(x) => onChange(f.key, x)} accent={accent} />
                </FieldFrame>
              );
              break;
          }
          return (
            <div key={f.key} className="fam-gap" data-field-key={f.key}>
              {el}
            </div>
          );
        })}
    </div>
  );
}
