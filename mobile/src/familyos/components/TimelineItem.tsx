// "WHAT I DID" entry (AGENT.md §8.7). Tap to expand in place: key/value
// rows fade in and Undo / Ask-about-this pills appear. Undone entries are
// struck through.
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { FadeIn, LinearTransition, useAnimatedStyle, withTiming } from 'react-native-reanimated';
import { ChevronDown } from 'lucide-react-native';
import type { TimelineEntry } from '../services/interfaces';
import { copy } from '../mocks/data';
import { GlowDot } from '../graphics/GlowDot';
import { colors } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';
import { PillButton } from './Pills';
import { Pressy } from './Pressy';

interface Props {
  entry: TimelineEntry;
  color: string;
  undone: boolean;
  onUndo: () => void;
  onAsk: () => void;
  last?: boolean;
}

export function TimelineItem({ entry, color, undone, onUndo, onAsk, last }: Props) {
  const [open, setOpen] = useState(false);
  const canUndo = !!entry.undoable && !undone;
  const chevron = useAnimatedStyle(() => ({ transform: [{ rotate: withTiming(open ? '180deg' : '0deg', { duration: 220 }) }] }));
  return (
    <Animated.View layout={LinearTransition.duration(260)} style={[styles.item, !last && styles.divider]}>
      <Pressy
        onPress={() => setOpen((o) => !o)}
        pressScale={0.99}
        accessibilityLabel={`${entry.when}. ${entry.title}. ${entry.description}`}
        accessibilityHint={open ? 'Collapses the details' : 'Shows the details'}
        accessibilityState={{ expanded: open }}
      >
        <View style={styles.head}>
          <View style={styles.dot}>
            <GlowDot color={undone ? colors.dim : color} size={7} />
          </View>
          <AppText style={[T.small, styles.when]}>{entry.when}</AppText>
          <View style={styles.link}>
            <AppText style={[T.smallStrong, { color: canUndo ? color : color, opacity: undone ? 0.5 : 1 }]}>
              {undone ? 'Undone' : canUndo ? copy.undo : copy.details}
            </AppText>
            {!canUndo && !undone ? (
              <Animated.View style={[styles.chev, chevron]}>
                <ChevronDown size={13} color={color} />
              </Animated.View>
            ) : null}
          </View>
        </View>
        <AppText style={[T.bodyStrong, styles.title, undone && styles.struck]}>{entry.title}</AppText>
        <AppText style={[T.small, styles.desc]}>{entry.description}</AppText>
      </Pressy>
      {open ? (
        <Animated.View entering={FadeIn.duration(260).delay(80)} style={styles.expanded}>
          {entry.rows?.map(([k, v]) => (
            <View key={k} style={styles.row}>
              <AppText style={T.small}>{k}</AppText>
              <AppText style={[T.smallStrong, styles.rowValue]}>{v}</AppText>
            </View>
          ))}
          <View style={styles.pills}>
            {canUndo ? <PillButton label={copy.undo} variant="primary" onPress={onUndo} /> : null}
            <PillButton label={copy.askAboutThis} onPress={onAsk} style={canUndo ? styles.pillGap : undefined} />
          </View>
        </Animated.View>
      ) : null}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  item: { paddingVertical: 14 },
  divider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider },
  head: { flexDirection: 'row', alignItems: 'center' },
  dot: { width: 22, marginLeft: -6, marginRight: 4, alignItems: 'center' },
  when: { flex: 1, fontSize: 12 },
  link: { flexDirection: 'row', alignItems: 'center' },
  chev: { marginLeft: 2 },
  title: { marginTop: 4, marginLeft: 20 },
  struck: { textDecorationLine: 'line-through', color: colors.muted },
  desc: { marginTop: 3, marginLeft: 20 },
  expanded: { marginTop: 10, marginLeft: 20 },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 9,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  rowValue: { textAlign: 'right', flexShrink: 1, marginLeft: 12 },
  pills: { flexDirection: 'row', marginTop: 12 },
  pillGap: { marginLeft: 8 },
});
