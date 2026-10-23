// Settings, restyled (AGENT.md §8.8). Includes the dev-only "Demo scenario" row (§6.2).
import { StyleSheet, Switch, View } from 'react-native';
import { copy } from '../mocks/data';
import { SCENARIOS, scenarioThemes } from '../theme/stateThemes';
import { colors, radii } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { useFamilyOS } from '../store/useFamilyOS';
import { useFamily } from '../store/useFamily';
import type { ScreenProps } from '../navigation/types';
import { AppText } from '../components/AppText';
import { SectionLabel, Dot } from '../components/Labels';
import { Pressy } from '../components/Pressy';
import { ScreenShell } from '../components/ScreenShell';

function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function SettingsScreen({ navigation }: ScreenProps<'Settings'>) {
  const st = useFamilyOS();
  const resetFamily = useFamily((x) => x.reset);
  const s = copy.settings;
  return (
    <ScreenShell title={s.title} onBack={() => navigation.goBack()}>
      <SectionLabel>{s.summarySection}</SectionLabel>
      <Card>
        <Pressy onPress={st.toggleSummaryMode} pressScale={0.99} style={styles.row} accessibilityLabel={`${copy.profileMenu.summaryButton}: ${copy.summaryModeLabel[st.summaryMode]}`}>
          <AppText style={T.menu}>{copy.profileMenu.summaryButton}</AppText>
          <View style={styles.chip}>
            <AppText style={[T.chip, { fontSize: 11 }]}>{copy.summaryModeLabel[st.summaryMode]}</AppText>
          </View>
        </Pressy>
      </Card>

      <SectionLabel style={styles.gap}>{s.graphicsSection}</SectionLabel>
      <Card>
        <View style={styles.row}>
          <View style={styles.flex}>
            <AppText style={T.menu}>{s.reduceGraphics}</AppText>
            <AppText style={[T.small, styles.hint]}>{s.reduceGraphicsHint}</AppText>
          </View>
          <Switch
            value={st.lowPower}
            onValueChange={st.setLowPower}
            trackColor={{ false: 'rgba(255,255,255,0.12)', true: colors.violet }}
            thumbColor="#fff"
            accessibilityLabel={s.reduceGraphics}
          />
        </View>
      </Card>

      {__DEV__ ? (
        <>
          <SectionLabel style={styles.gap}>{s.devSection}</SectionLabel>
          <Card>
            <View style={styles.rowCol}>
              <AppText style={T.menu}>{s.demoScenario}</AppText>
              <AppText style={[T.small, styles.hint]}>{s.demoHint}</AppText>
              <View style={styles.segs}>
                {SCENARIOS.map((sc) => {
                  const on = st.seed === sc;
                  return (
                    <Pressy
                      key={sc}
                      onPress={() => void st.setScenario(sc)}
                      style={[styles.seg, on && styles.segOn]}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: on }}
                      accessibilityLabel={copy.scenarioLabels[sc]}
                    >
                      <Dot color={scenarioThemes[sc].dot} size={6} style={styles.segDot} />
                      <AppText style={[T.chip, { fontSize: 11.5 }]}>{copy.scenarioLabels[sc]}</AppText>
                    </Pressy>
                  );
                })}
              </View>
            </View>
            <Pressy
              onPress={() => void resetFamily()}
              pressScale={0.99}
              style={[styles.row, styles.divider]}
              accessibilityLabel={s.resetFamily}
            >
              <View style={styles.flex}>
                <AppText style={T.menu}>{s.resetFamily}</AppText>
                <AppText style={[T.small, styles.hint]}>{s.resetFamilyHint}</AppText>
              </View>
            </Pressy>
          </Card>
        </>
      ) : null}

      <SectionLabel style={styles.gap}>{s.privacySection}</SectionLabel>
      <Card>
        {s.privacy.map(([h, b], i) => (
          <View key={h} style={[styles.rowCol, i > 0 && styles.divider]}>
            <AppText style={T.bodyStrong}>{h}</AppText>
            <AppText style={[T.small, styles.hint]}>{b}</AppText>
          </View>
        ))}
      </Card>

      <SectionLabel style={styles.gap}>{s.accountSection}</SectionLabel>
      <Card>
        <View style={styles.row}>
          <AppText style={T.menu}>{s.version}</AppText>
          <AppText style={T.small}>{s.versionValue}</AppText>
        </View>
        <Pressy
          onPress={async () => {
            await st.logOut();
            navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
          }}
          pressScale={0.99}
          style={[styles.row, styles.divider]}
          accessibilityLabel={copy.profileMenu.logout}
        >
          <AppText style={[T.menu, { color: colors.danger }]}>{copy.profileMenu.logout}</AppText>
        </Pressy>
      </Card>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.card, backgroundColor: colors.cardFill, borderWidth: 1, borderColor: colors.glassBorder, overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, minHeight: 54, paddingVertical: 10 },
  rowCol: { paddingHorizontal: 16, paddingVertical: 14 },
  flex: { flex: 1, marginRight: 12 },
  hint: { marginTop: 4, fontSize: 12.5 },
  gap: { marginTop: 22 },
  chip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
  segs: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 12 },
  seg: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    height: 32,
    borderRadius: 999,
    backgroundColor: colors.pillSecondaryBg,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    marginRight: 8,
    marginBottom: 8,
  },
  segOn: { backgroundColor: 'rgba(255,255,255,0.18)', borderColor: 'rgba(255,255,255,0.35)' },
  segDot: { marginRight: 6 },
});
