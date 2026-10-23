// Home header (date, greeting, summary line, avatar pill) and status block
// (status label, headline, "+N more"). AGENT.md §8.1.1–8.1.4.
import { StyleSheet, View } from 'react-native';
import Animated, { FadeOut, Keyframe } from 'react-native-reanimated';
import { ChevronDown, ChevronRight } from 'lucide-react-native';
import type { Profile } from '../services/interfaces';
import { colors } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { copy } from '../mocks/data';
import { AppText } from '../components/AppText';
import { Dot, StatusLine } from '../components/Labels';
import { Pressy } from '../components/Pressy';
import { formatLongDate, greetingFor } from './homeText';

interface HeaderProps {
  profile: Profile;
  summaryWord: string;
  summaryDot: string;
  onSummary: () => void;
  onAvatar: () => void;
  /** Dev-only scenario switcher (long-press the date). */
  onDateLongPress?: () => void;
}

export function HomeHeader({ profile, summaryWord, summaryDot, onSummary, onAvatar, onDateLongPress }: HeaderProps) {
  const now = new Date();
  return (
    <View style={styles.header}>
      <View style={styles.headerText}>
        <AppText
          style={T.date}
          onLongPress={onDateLongPress}
          suppressHighlighting
          accessibilityHint={onDateLongPress ? 'Developer: long-press to change the demo scenario' : undefined}
        >
          {formatLongDate(now)}
        </AppText>
        <AppText
          style={[T.greeting, styles.greeting]}
          accessibilityRole="header"
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.78}
        >
          {greetingFor(now, profile.name)}
        </AppText>
        <Pressy
          onPress={onSummary}
          pressScale={0.97}
          style={styles.summaryRow}
          accessibilityLabel={`${copy.summaryPrefix}: ${summaryWord}`}
          accessibilityHint="Opens today's summary"
        >
          <Dot color={summaryDot} size={6} style={styles.summaryDot} />
          <AppText style={T.summary}>{copy.summaryPrefix} · </AppText>
          <AppText style={T.summaryStrong}>{summaryWord}</AppText>
          <ChevronRight size={12} color={colors.muted} style={styles.chev} />
        </Pressy>
      </View>
      <Pressy onPress={onAvatar} style={styles.avatarPill} accessibilityLabel={`${profile.name}, open the profile menu`}>
        <View style={styles.avatar}>
          <AppText style={[T.chip, { color: colors.inkStrong }]}>{profile.initial}</AppText>
        </View>
        <ChevronDown size={14} color={colors.muted} style={styles.avatarChev} />
      </Pressy>
    </View>
  );
}

const headlineIn = new Keyframe({
  0: { opacity: 0, transform: [{ translateY: 8 }] },
  100: { opacity: 1, transform: [{ translateY: 0 }] },
}).duration(320);

interface StatusProps {
  label: string;
  color: string;
  headline: string;
  calm: boolean;
  more?: string;
  onMore?: () => void;
}

export function StatusBlock({ label, color, headline, calm, more, onMore }: StatusProps) {
  return (
    <View style={styles.status} pointerEvents="box-none">
      <StatusLine label={label} color={color} />
      <View style={styles.headlineBox} pointerEvents="none">
        <Animated.View key={headline} entering={headlineIn} exiting={FadeOut.duration(160)} style={styles.headlineAbs}>
          <AppText
            style={[T.headline, calm ? { color: colors.muted } : { color: colors.inkStrong }]}
            numberOfLines={2}
            accessibilityLiveRegion="polite"
          >
            {headline}
          </AppText>
        </Animated.View>
      </View>
      {more ? (
        <Pressy onPress={onMore} style={styles.more} accessibilityLabel={`${more}, open everything that needs you`}>
          <AppText style={[T.chip, { fontSize: 10.5 }]}>{more}</AppText>
        </Pressy>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-start', paddingHorizontal: 20 },
  headerText: { flex: 1 },
  greeting: { marginTop: 2 },
  summaryRow: { flexDirection: 'row', alignItems: 'center', marginTop: 8, alignSelf: 'flex-start' },
  summaryDot: { marginRight: 7 },
  chev: { marginLeft: 3 },
  avatarPill: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 38,
    paddingLeft: 5,
    paddingRight: 10,
    borderRadius: 19,
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    marginTop: 2,
  },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarChev: { marginLeft: 6 },
  status: { alignItems: 'center', paddingHorizontal: 28 },
  headlineBox: { height: 54, alignSelf: 'stretch', marginTop: 10 },
  headlineAbs: { position: 'absolute', left: 0, right: 0, top: 0, alignItems: 'center' },
  more: {
    marginTop: 6,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: colors.pillSecondaryBg,
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
});
