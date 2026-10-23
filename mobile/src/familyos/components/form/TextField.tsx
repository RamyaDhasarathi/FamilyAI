// Glass text field (AGENT_CORE_AND_FAMILY.md §4.10): 1 px border that
// brightens and takes the section colour on focus, a floating label, optional
// prefix (+1, $), as-you-type formatting, and a mask shown whenever the field
// isn't focused (XXXX XXXX 0193, ••••••••6789).
import { useEffect, useRef, useState, type ComponentRef } from 'react';
import { StyleSheet, TextInput, View, type StyleProp, type ViewStyle } from 'react-native';
import Animated, { interpolate, interpolateColor, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { colors } from '../../theme/tokens';
import { fonts, MAX_FONT_SCALE, type as T } from '../../theme/typography';
import { AppText } from '../AppText';

export const ERROR_RED = '#FF7A85';

interface Props {
  label: string;
  value: string;
  onChange: (v: string) => void;
  accent: string;
  required?: boolean;
  error?: string | null;
  hint?: string;
  prefix?: string;
  keyboard?: 'default' | 'number-pad' | 'decimal-pad' | 'email-address' | 'phone-pad';
  format?: (v: string) => string;
  mask?: (v: string) => string;
  autoCapitalize?: 'none' | 'words' | 'characters' | 'sentences';
  autoFocus?: boolean;
  style?: StyleProp<ViewStyle>;
  onFocus?: () => void;
  compact?: boolean;
}

export function TextField({
  label, value, onChange, accent, required, error, hint, prefix, keyboard = 'default', format, mask,
  autoCapitalize = 'sentences', autoFocus, style, onFocus, compact,
}: Props) {
  const [focused, setFocused] = useState(false);
  const input = useRef<ComponentRef<typeof TextInput>>(null);
  const f = useSharedValue(0);
  const up = useSharedValue(value ? 1 : 0);
  useEffect(() => {
    f.set(withTiming(focused ? 1 : 0, { duration: 160 }));
    up.set(withTiming(focused || !!value ? 1 : 0, { duration: 160 }));
  }, [focused, value, f, up]);
  const box = useAnimatedStyle(() => ({
    borderColor: interpolateColor(f.value, [0, 1], [error ? ERROR_RED : colors.glassBorder, accent]),
    backgroundColor: interpolateColor(f.value, [0, 1], ['rgba(255,255,255,0.05)', 'rgba(255,255,255,0.08)']),
  }));
  const lbl = useAnimatedStyle(() => ({
    transform: [{ translateY: interpolate(up.value, [0, 1], [compact ? 0 : 9, compact ? -8 : -1]) }, { scale: interpolate(up.value, [0, 1], [1, 0.8]) }],
  }));
  const shown = !focused && mask && value ? mask(value) : value;
  const showPrefix = !!prefix && (focused || !!value);
  return (
    <View style={style}>
      <Animated.View style={[styles.box, compact && styles.compact, box]}>
        <Animated.View style={[styles.labelWrap, lbl]} pointerEvents="none">
          <AppText style={[T.small, styles.label, focused && { color: accent }]} numberOfLines={1}>
            {label}
            {required ? ' *' : ''}
          </AppText>
        </Animated.View>
        <View style={styles.row}>
          {showPrefix ? <AppText style={[T.input, styles.prefix]}>{prefix}</AppText> : null}
          <TextInput
            ref={input}
            value={shown}
            onChangeText={(t) => onChange(format ? format(t) : t)}
            onFocus={() => {
              setFocused(true);
              onFocus?.();
            }}
            onBlur={() => setFocused(false)}
            keyboardType={keyboard}
            autoCapitalize={format ? 'none' : autoCapitalize}
            autoCorrect={false}
            autoFocus={autoFocus}
            style={[styles.input, compact && styles.inputCompact]}
            selectionColor={accent}
            maxFontSizeMultiplier={MAX_FONT_SCALE}
            accessibilityLabel={`${label}${required ? ', required' : ''}`}
            accessibilityHint={error ?? hint}
          />
        </View>
      </Animated.View>
      {error ? (
        <AppText style={[T.small, styles.error]} accessibilityLiveRegion="polite">
          {error}
        </AppText>
      ) : hint && focused ? (
        <AppText style={[T.small, styles.hint]}>{hint}</AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderWidth: 1, borderRadius: 14, minHeight: 56, paddingHorizontal: 14, justifyContent: 'flex-end', paddingBottom: 8 },
  compact: { minHeight: 46, paddingBottom: 6 },
  labelWrap: { position: 'absolute', left: 14, right: 14, top: 8, transformOrigin: 'left center' },
  label: { fontSize: 14, color: colors.muted },
  row: { flexDirection: 'row', alignItems: 'center' },
  prefix: { color: colors.muted, marginRight: 6, fontSize: 15 },
  input: { flex: 1, color: colors.ink, fontFamily: fonts.medium, fontSize: 15, paddingVertical: 0, minHeight: 22 },
  inputCompact: { fontSize: 14 },
  error: { color: ERROR_RED, fontSize: 12, marginTop: 5, marginLeft: 4 },
  hint: { fontSize: 12, marginTop: 5, marginLeft: 4 },
});
