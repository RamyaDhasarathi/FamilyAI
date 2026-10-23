// Frosted-glass surface (AGENT.md §6.4): translucent fill + 1px border + a
// soft inner highlight along the top edge. The blur itself comes from the
// scene behind (the Home canvas blurs under sheets), which keeps Android
// smooth; cards inside a sheet do not need their own blur.
import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, radii } from '../theme/tokens';

interface Props {
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
  radius?: number;
  strong?: boolean;
  /** Optional faint gradient wash (e.g. the scenario tint on sheets). */
  tint?: [string, string];
  fill?: string;
}

export function Glass({ children, style, radius = radii.card, strong, tint, fill }: Props) {
  return (
    <View
      style={[
        styles.base,
        { borderRadius: radius, backgroundColor: fill ?? (strong ? colors.glassFillStrong : colors.glassFill) },
        style,
      ]}
    >
      {tint ? (
        <LinearGradient
          colors={tint}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
          pointerEvents="none"
        />
      ) : null}
      <LinearGradient
        colors={['rgba(255,255,255,0)', colors.glassHighlight, 'rgba(255,255,255,0)']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        style={[styles.highlight, { left: radius * 0.6, right: radius * 0.6 }]}
        pointerEvents="none"
      />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    borderWidth: 1,
    borderColor: colors.glassBorder,
    overflow: 'hidden',
  },
  highlight: { position: 'absolute', top: 0, height: 1 },
});
