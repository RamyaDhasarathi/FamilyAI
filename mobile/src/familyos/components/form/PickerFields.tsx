// Picker fields (AGENT_CORE_AND_FAMILY.md §4.5, §4.8): date (inline spinner on
// iOS, native dialog on Android), a searchable select (state lists), document
// chips (expo-document-picker; only the local URI is kept), list rows
// (medicines, saved cards) and the "Paid from" adult picker.
import { useState } from 'react';
import { Platform, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeOut, LinearTransition } from 'react-native-reanimated';
import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import * as DocumentPicker from 'expo-document-picker';
import { CalendarDays, ChevronDown, Paperclip, Plus, X } from 'lucide-react-native';
import { colors } from '../../theme/tokens';
import { type as T } from '../../theme/typography';
import { ageOf, dateFromIso, displayName, isoDate, yearsText } from '../../family/model';
import type { FamilyMember } from '../../services/interfaces';
import { AppText } from '../AppText';
import { Pressy } from '../Pressy';
import { ChoiceChips } from './Choices';
import { ERROR_RED, TextField } from './TextField';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const formatDate = (iso: string) => {
  const d = dateFromIso(iso);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
};

function Box({ children, onPress, label, error, accent, open }: { children: React.ReactNode; onPress: () => void; label: string; error?: string | null; accent: string; open?: boolean }) {
  return (
    <Pressy onPress={onPress} pressScale={0.99} style={[styles.box, open && { borderColor: accent }, error && !open && { borderColor: ERROR_RED }]} accessibilityLabel={label}>
      {children}
    </Pressy>
  );
}

export function DateField({ label, value, onChange, accent, required, error, minDate, maxDate, ageNote }: {
  label: string; value?: string; onChange: (iso: string) => void; accent: string; required?: boolean; error?: string | null;
  minDate?: Date; maxDate?: Date; ageNote?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const current = value ? dateFromIso(value) : maxDate && maxDate < new Date() ? maxDate : new Date(2000, 0, 1);
  const toggle = () => {
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({
        value: current, mode: 'date', minimumDate: minDate, maximumDate: maxDate,
        onValueChange: (_e, d) => onChange(isoDate(d)),
      });
    } else setOpen((o) => !o);
  };
  const age = value && ageNote ? ageOf(value) : null;
  return (
    <View>
      <Box onPress={toggle} label={`${label}${value ? `, ${formatDate(value)}` : ''}`} error={error} accent={accent} open={open}>
        <View style={styles.flex}>
          <AppText style={[T.small, styles.small, !!value && styles.smallUp]}>
            {label}
            {required ? ' *' : ''}
          </AppText>
          {value ? <AppText style={T.input}>{formatDate(value)}</AppText> : null}
        </View>
        {age !== null ? <AppText style={[T.smallStrong, { color: accent }]}>{yearsText(age)}</AppText> : null}
        <CalendarDays size={18} color={colors.muted} style={styles.icon} />
      </Box>
      {open && Platform.OS === 'ios' ? (
        <Animated.View entering={FadeIn.duration(180)} exiting={FadeOut.duration(120)}>
          <DateTimePicker
            value={current}
            mode="date"
            display="spinner"
            themeVariant="dark"
            textColor={colors.ink}
            minimumDate={minDate}
            maximumDate={maxDate}
            onValueChange={(_e, d) => onChange(isoDate(d))}
          />
        </Animated.View>
      ) : null}
      {error ? <AppText style={[T.small, styles.error]}>{error}</AppText> : null}
    </View>
  );
}

export function SelectField({ label, value, options, onChange, accent, required, error }: {
  label: string; value?: string; options: string[]; onChange: (v: string) => void; accent: string; required?: boolean; error?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const shown = options.filter((o) => o.toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <Animated.View layout={LinearTransition.duration(200)}>
      <Box onPress={() => setOpen((o) => !o)} label={`${label}${value ? `, ${value}` : ''}`} error={error} accent={accent} open={open}>
        <View style={styles.flex}>
          <AppText style={[T.small, styles.small, !!value && styles.smallUp]}>
            {label}
            {required ? ' *' : ''}
          </AppText>
          {value ? <AppText style={T.input}>{value}</AppText> : null}
        </View>
        <ChevronDown size={18} color={colors.muted} />
      </Box>
      {open ? (
        <View style={styles.list}>
          <TextField label="Search" value={q} onChange={setQ} accent={accent} compact autoCapitalize="words" />
          <ScrollView style={styles.listScroll} nestedScrollEnabled keyboardShouldPersistTaps="handled">
            {shown.map((o) => (
              <Pressy
                key={o}
                onPress={() => {
                  onChange(o);
                  setOpen(false);
                  setQ('');
                }}
                style={[styles.option, o === value && { backgroundColor: 'rgba(255,255,255,0.08)' }]}
                pressScale={0.99}
                accessibilityLabel={o}
              >
                <AppText style={[T.small, styles.optionText]}>{o}</AppText>
              </Pressy>
            ))}
          </ScrollView>
        </View>
      ) : null}
      {error ? <AppText style={[T.small, styles.error]}>{error}</AppText> : null}
    </Animated.View>
  );
}

export interface FileRef {
  kind: string;
  name: string;
  uri: string;
}

export function FilesField({ kinds, value, onChange, accent }: { kinds: string[]; value?: FileRef[]; onChange: (v: FileRef[]) => void; accent: string }) {
  const files = value ?? [];
  const pick = async (kind: string) => {
    const r = await DocumentPicker.getDocumentAsync({ type: ['image/*', 'application/pdf'], copyToCacheDirectory: true });
    if (r.canceled || !r.assets?.[0]) return;
    const a = r.assets[0];
    onChange([...files.filter((f) => f.kind !== kind), { kind, name: a.name, uri: a.uri }]);
  };
  return (
    <View>
      {kinds.map((k) => {
        const f = files.find((x) => x.kind === k);
        return (
          <View key={k} style={styles.fileRow}>
            <AppText style={[T.small, styles.fileKind]}>{k}</AppText>
            {f ? (
              <View style={styles.fileChip}>
                <Paperclip size={12} color={accent} />
                <AppText style={[T.chip, styles.fileName]} numberOfLines={1}>{f.name}</AppText>
                <Pressy onPress={() => onChange(files.filter((x) => x !== f))} accessibilityLabel={`Remove ${k} document`} style={styles.fileX}>
                  <X size={13} color={colors.muted} />
                </Pressy>
              </View>
            ) : (
              <Pressy onPress={() => void pick(k)} style={styles.attach} accessibilityLabel={`Attach ${k}`}>
                <AppText style={[T.chip, { fontSize: 12 }]}>Attach</AppText>
              </Pressy>
            )}
          </View>
        );
      })}
    </View>
  );
}

export function ListField({ columns, value, onChange, accent, addLabel }: {
  columns: { key: string; label: string; type: string; options?: string[]; format?: (v: string) => string; keyboard?: 'default' | 'number-pad' }[];
  value?: Record<string, string>[]; onChange: (v: Record<string, string>[]) => void; accent: string; addLabel: string;
}) {
  const rows = value ?? [];
  const set = (i: number, k: string, v: string) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <View>
      {rows.map((r, i) => (
        <Animated.View key={i} entering={FadeIn.duration(200)} layout={LinearTransition.duration(200)} style={styles.listRow}>
          {columns.map((c) =>
            c.type === 'choice' && c.options ? (
              <ChoiceChips key={c.key} label={c.label} options={c.options} value={r[c.key]} onChange={(v) => set(i, c.key, v as string)} accent={accent} />
            ) : (
              <TextField key={c.key} compact label={c.label} value={r[c.key] ?? ''} onChange={(v) => set(i, c.key, v)} accent={accent} format={c.format} keyboard={c.keyboard} style={styles.listCell} />
            )
          )}
          <Pressy onPress={() => onChange(rows.filter((_, j) => j !== i))} style={styles.removeRow} accessibilityLabel={`Remove ${addLabel} ${i + 1}`}>
            <X size={14} color={colors.muted} />
          </Pressy>
        </Animated.View>
      ))}
      <Pressy onPress={() => onChange([...rows, {}])} style={styles.add} accessibilityLabel={`Add ${addLabel}`}>
        <Plus size={14} color={colors.ink} />
        <AppText style={[T.chip, styles.addText]}>Add {addLabel}</AppText>
      </Pressy>
    </View>
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

const styles = StyleSheet.create({
  box: {
    minHeight: 56, borderWidth: 1, borderColor: colors.glassBorder, borderRadius: 14, paddingHorizontal: 14,
    backgroundColor: 'rgba(255,255,255,0.05)', flexDirection: 'row', alignItems: 'center',
  },
  flex: { flex: 1, paddingVertical: 8 },
  small: { fontSize: 14, color: colors.muted },
  smallUp: { fontSize: 11.5 },
  icon: { marginLeft: 10 },
  error: { color: ERROR_RED, fontSize: 12, marginTop: 5, marginLeft: 4 },
  list: { marginTop: 8, borderRadius: 14, borderWidth: 1, borderColor: colors.glassBorder, padding: 8, backgroundColor: 'rgba(20,22,28,0.9)' },
  listScroll: { maxHeight: 220, marginTop: 6 },
  option: { paddingVertical: 10, paddingHorizontal: 10, borderRadius: 10 },
  optionText: { color: colors.ink, fontSize: 14 },
  fileRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 44, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider },
  fileKind: { color: colors.ink, fontSize: 14, flex: 1 },
  fileChip: { flexDirection: 'row', alignItems: 'center', maxWidth: '60%', paddingLeft: 10, paddingRight: 4, height: 30, borderRadius: 15, backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder },
  fileName: { fontSize: 11.5, marginHorizontal: 6, flexShrink: 1 },
  fileX: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
  attach: { paddingHorizontal: 14, height: 30, borderRadius: 15, justifyContent: 'center', backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder },
  listRow: { borderRadius: 14, borderWidth: 1, borderColor: colors.glassBorder, padding: 10, paddingRight: 40, marginBottom: 8, backgroundColor: 'rgba(255,255,255,0.03)' },
  listCell: { marginBottom: 8 },
  removeRow: { position: 'absolute', right: 6, top: 6, width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  add: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', paddingHorizontal: 14, height: 34, borderRadius: 17, backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder },
  addText: { marginLeft: 6, fontSize: 12.5 },
});
