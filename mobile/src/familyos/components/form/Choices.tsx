// Choice controls: wrapped glass chips (selected = white with dark text,
// AGENT_CORE_AND_FAMILY.md §4.5), a toggle row, and a small label + error frame.
import type { ReactNode } from 'react';
import { StyleSheet, Switch, View } from 'react-native';
import { colors } from '../../theme/tokens';
import { type as T } from '../../theme/typography';
import { AppText } from '../AppText';
import { Pressy } from '../Pressy';
import { ERROR_RED } from './TextField';

export function FieldFrame({ label, required, error, children }: { label: string; required?: boolean; error?: string | null; children: ReactNode }) {
  return (
    <View>
      <AppText style={[T.small, styles.frameLabel]}>
        {label}
        {required ? ' *' : ''}
      </AppText>
      {children}
      {error ? <AppText style={[T.small, styles.error]}>{error}</AppText> : null}
    </View>
  );
}

interface ChipsProps {
  options: string[];
  value: string | string[] | undefined;
  onChange: (v: string | string[]) => void;
  multi?: boolean;
  accent: string;
  label: string;
}

export function ChoiceChips({ options, value, onChange, multi, accent, label }: ChipsProps) {
  const selected = (o: string) => (multi ? Array.isArray(value) && value.includes(o) : value === o);
  return (
    <View style={styles.wrap} accessibilityRole={multi ? undefined : 'radiogroup'} accessibilityLabel={label}>
      {options.map((o) => {
        const on = selected(o);
        return (
          <Pressy
            key={o}
            onPress={() => {
              if (!multi) onChange(o);
              else {
                const cur = Array.isArray(value) ? value : [];
                onChange(on ? cur.filter((x) => x !== o) : [...cur, o]);
              }
            }}
            style={[styles.chip, on ? styles.chipOn : null, on && multi ? { borderColor: accent } : null]}
            accessibilityRole={multi ? 'checkbox' : 'radio'}
            accessibilityState={multi ? { checked: on } : { selected: on }}
            accessibilityLabel={o}
            pressScale={0.95}
          >
            <AppText style={[T.chip, styles.chipText, on && styles.chipTextOn]}>{o}</AppText>
          </Pressy>
        );
      })}
    </View>
  );
}

export function ToggleRow({ label, value, onChange, accent, required, error }: { label: string; value: boolean; onChange: (v: boolean) => void; accent: string; required?: boolean; error?: string | null }) {
  return (
    <View>
      <View style={styles.toggle}>
        <AppText style={[T.small, styles.toggleText]}>
          {label}
          {required ? ' *' : ''}
        </AppText>
        <Switch
          value={value}
          onValueChange={onChange}
          trackColor={{ false: 'rgba(255,255,255,0.12)', true: accent }}
          thumbColor="#FFFFFF"
          accessibilityLabel={label}
        />
      </View>
      {error ? <AppText style={[T.small, styles.error]}>{error}</AppText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  frameLabel: { fontSize: 13, color: colors.muted, marginBottom: 8, marginLeft: 2 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap' },
  chip: {
    height: 34,
    paddingHorizontal: 14,
    borderRadius: 999,
    justifyContent: 'center',
    backgroundColor: colors.pillSecondaryBg,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    marginRight: 8,
    marginBottom: 8,
  },
  chipOn: { backgroundColor: colors.pillPrimaryBg, borderColor: colors.pillPrimaryBg },
  chipText: { fontSize: 12.5 },
  chipTextOn: { color: colors.pillPrimaryInk },
  toggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 54,
    paddingHorizontal: 14,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    backgroundColor: 'rgba(255,255,255,0.05)',
  },
  toggleText: { color: colors.ink, flex: 1, marginRight: 12, fontSize: 14 },
  error: { color: ERROR_RED, fontSize: 12, marginTop: 5, marginLeft: 4 },
});
