// Review step of the details wizard (AGENT_CORE_AND_FAMILY.md §4.7): one card
// per section with its status, a masked summary and an Edit link.
import { StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import type { FamilyMember, SectionId } from '../../services/interfaces';
import { SECTION_IDS, type AgeGroup, sectionMeta } from '../../family/model';
import { sectionSummary } from '../../family/summary';
import { colors, radii, withAlpha } from '../../theme/tokens';
import { durations } from '../../theme/motion';
import { type as T } from '../../theme/typography';
import { AppText } from '../../components/AppText';
import { Pressy } from '../../components/Pressy';
import { StatusPill } from '../../components/family/MemberBits';

export function WizardReview({ member, members, group, onEdit }: { member: FamilyMember; members: FamilyMember[]; group: AgeGroup; onEdit: (s: SectionId) => void }) {
  const owner = members.find((m) => m.isOwner);
  return (
    <View>
      {SECTION_IDS.map((sid, i) => {
        const meta = sectionMeta(sid, group);
        return (
          <Animated.View key={sid} entering={FadeInDown.delay(i * durations.stagger).duration(280)} style={[styles.card, { borderLeftColor: withAlpha(meta.color, 0.8) }]}>
            <View style={styles.head}>
              <AppText style={[T.bodyStrong, styles.title]}>{meta.title}</AppText>
              <Pressy onPress={() => onEdit(sid)} accessibilityLabel={`Edit ${meta.title}`} style={styles.edit}>
                <AppText style={[T.smallStrong, { color: meta.color }]}>Edit</AppText>
              </Pressy>
            </View>
            <AppText style={[T.small, styles.summary]} numberOfLines={2}>
              {sectionSummary(member, sid, members, owner)}
            </AppText>
            <View style={styles.pill}>
              <StatusPill status={member.sections[sid].status} />
            </View>
          </Animated.View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 14, borderRadius: radii.tile, backgroundColor: colors.cardFill, borderWidth: 1, borderColor: colors.glassBorder, borderLeftWidth: 3, marginBottom: 10 },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { flex: 1 },
  edit: { paddingHorizontal: 8, paddingVertical: 4 },
  summary: { marginTop: 4 },
  pill: { flexDirection: 'row' },
});
